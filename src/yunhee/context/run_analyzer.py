import sys
from pathlib import Path

from yunhee import ollama_client
from yunhee.tools.runner import extract_test_results

MAX_LLM_INPUT_CHARS = 10000


def _extract_tail_lines(text: str, n: int = 25) -> str:
    lines = text.strip().splitlines()
    if len(lines) <= n:
        return text.strip()
    return "\n".join(lines[-n:])


def summarize_run(
    command: str,
    exit_code: int,
    duration_ms: int,
    log_path: str,
    stdout: str,
    stderr: str,
    use_llm: bool = True,
    cwd: Path | None = None,
) -> str:
    """명령어 실행 결과를 상용 AI 에이전트 및 사용자가 소비하기 좋은 압축 마크다운으로 가공한다."""
    duration_sec = f"{duration_ms / 1000:.2f}s"
    test_info = extract_test_results(command, cwd=cwd, stdout=stdout, stderr=stderr)

    # 1. 성공 케이스 (exit_code == 0): 정확히 1줄로 단축하여 토큰 낭비 제거
    if exit_code == 0:
        test_suffix = ""
        if test_info:
            test_suffix = f" · tests {test_info['total']} (fail {test_info['failures']}, skip {test_info['skipped']})"
        return f"✅ Execution Succeeded in {duration_sec}: `{command}` (log: {log_path}){test_suffix}"

    # 2. 실패 케이스 (exit_code != 0)
    lines = []
    # C-3: 실패면 실패 테스트 이름을 LLM 요약보다 먼저 낸다 (맨 위)
    if test_info and test_info.get("failed_cases"):
        for fc in test_info["failed_cases"]:
            lines.append(f"❌ {fc}")

    lines.extend([
        f"### ❌ Execution Failed (exit code: {exit_code}, {duration_sec})",
        f"- **Command**: `{command}`",
        f"- **Log File**: `{log_path}`",
    ])
    if test_info:
        lines.append(f"- **Tests**: 전체 {test_info['total']} · 실패 {test_info['failures']} · 건너뜀 {test_info['skipped']}")

    combined_output = ""
    if stderr.strip():
        combined_output += f"[STDERR]\n{stderr.strip()}\n\n"
    if stdout.strip():
        combined_output += f"[STDOUT]\n{stdout.strip()}\n"

    if not combined_output.strip():
        lines.append("\n_No output was produced by the command._")
        return "\n".join(lines)

    # LLM 요약 시도 (지어내지 않고 원본 로그의 실제 에러 라인을 그대로 발췌하도록 지시)
    llm_summary = None
    if use_llm:
        truncated_output = combined_output
        if len(truncated_output) > MAX_LLM_INPUT_CHARS:
            # 뒷부분(보통 에러의 핵심이 있는 tail 부분) 위주로 자름
            truncated_output = "... [TRUNCATED FRONT]\n" + truncated_output[-MAX_LLM_INPUT_CHARS:]

        prompt = (
            f"다음은 명령어 `{command}`의 실행 실패 로그입니다.\n"
            "AI 코딩 에이전트(Claude, Antigravity)가 즉시 원인을 파악할 수 있도록, 원본 로그에서 핵심 줄을 골라 원문 그대로 발췌하세요.\n"
            "임의로 문장을 지어내거나 추정하지 말고, 로그에 실제로 적힌 내용을 바탕으로만 아래 형식으로 작성해 주세요:\n\n"
            "1. **실패 원인**: 1줄 요약\n"
            "2. **관련 파일**: 발견된 파일 경로 및 라인 (`경로/파일명:라인번호`), 없으면 '없음'\n"
            "3. **핵심 에러 (원문 발췌)**:\n```text\n(실제 에러가 발생한 핵심 로그 원문 3~5줄 그대로 인용)\n```\n\n"
            f"[실행 로그]\n{truncated_output}"
        )
        try:
            llm_summary = ollama_client.chat(prompt)
        except Exception as exc:  # noqa: BLE001
            print(f"[yunhee] LLM 요약 실패 (fallback 적용): {exc}", file=sys.stderr)
            llm_summary = None

    if llm_summary and llm_summary.strip():
        lines.append("\n#### 🔍 압축 에러 분석 (Qwen 14B)")
        lines.append(llm_summary.strip())
    else:
        lines.append("\n#### 🔍 에러 출력 (Tail)")
        target_text = stderr.strip() if stderr.strip() else stdout.strip()
        lines.append("```text")
        lines.append(_extract_tail_lines(target_text, n=25))
        lines.append("```")

    lines.append(f"\n_전체 로그는 `{log_path}`에 저장되어 있습니다._")
    return "\n".join(lines)
