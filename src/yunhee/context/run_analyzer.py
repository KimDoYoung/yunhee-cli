import sys

from yunhee import ollama_client

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
) -> str:
    """명령어 실행 결과를 상용 AI 에이전트 및 사용자가 소비하기 좋은 압축 마크다운으로 가공한다."""
    duration_sec = f"{duration_ms / 1000:.2f}s"

    # 1. 성공 케이스 (exit_code == 0)
    if exit_code == 0:
        total_len = len(stdout.strip())
        lines = [
            f"### ✅ Execution Succeeded ({duration_sec})",
            f"- **Command**: `{command}`",
            f"- **Log File**: `{log_path}`",
        ]
        if total_len <= 500:
            if total_len > 0:
                lines.append("\n```text")
                lines.append(stdout.strip())
                lines.append("```")
        else:
            lines.append("\n**Output Summary (Tail):**")
            lines.append("```text")
            lines.append(_extract_tail_lines(stdout, n=15))
            lines.append("```")
            lines.append(f"_Full output ({total_len} chars) saved to log file._")
        return "\n".join(lines)

    # 2. 실패 케이스 (exit_code != 0)
    lines = [
        f"### ❌ Execution Failed (exit code: {exit_code}, {duration_sec})",
        f"- **Command**: `{command}`",
        f"- **Log File**: `{log_path}`",
    ]

    combined_output = ""
    if stderr.strip():
        combined_output += f"[STDERR]\n{stderr.strip()}\n\n"
    if stdout.strip():
        combined_output += f"[STDOUT]\n{stdout.strip()}\n"

    if not combined_output.strip():
        lines.append("\n_No output was produced by the command._")
        return "\n".join(lines)

    # LLM 요약 시도
    llm_summary = None
    if use_llm:
        truncated_output = combined_output
        if len(truncated_output) > MAX_LLM_INPUT_CHARS:
            # 뒷부분(보통 에러의 핵심이 있는 tail 부분) 위주로 자름
            truncated_output = "... [TRUNCATED FRONT]\n" + truncated_output[-MAX_LLM_INPUT_CHARS:]

        prompt = (
            f"다음은 명령어 `{command}`의 실행 실패 로그입니다.\n"
            "AI 코딩 에이전트(Claude, Antigravity)가 토큰 낭비 없이 에러를 즉시 파악하고 수정할 수 있도록 핵심만 간결하게 요약해 주세요.\n\n"
            "반드시 다음 3가지 항목 형식으로 작성해 주세요:\n"
            "1. **실패 원인**: 1~2줄로 명확한 원인 설명\n"
            "2. **관련 파일**: 발견된 파일 경로 및 라인 (`경로/파일명:라인번호`), 없으면 '없음'\n"
            "3. **핵심 에러**: 실제 에러 메시지 2~5줄 발췌 (장황한 스택트레이스는 생략)\n\n"
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
