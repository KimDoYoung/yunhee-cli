"""
yunhee-cli L1 Declarative Rules Memory
프로젝트별 영구 코딩 컨벤션 및 핵심 규칙을 .yunhee/memory.md에 저장하고
로컬 14B 모델의 16k 토큰 제약을 보호하기 위해 40라인 상한 가드를 적용합니다.
"""

from __future__ import annotations

from pathlib import Path

from yunhee import config

MAX_RULE_LINES = 40
DEFAULT_MEMORY_FILENAME = "memory.md"


def get_memory_file_path() -> Path:
    """현재 작업 대상 프로젝트(WORK_DIR)의 .yunhee/memory.md 경로 반환."""
    return Path(config.WORK_DIR) / ".yunhee" / DEFAULT_MEMORY_FILENAME


def load_rules() -> list[str]:
    """
    memory.md 파일에서 실제 유효한 규칙 목록(글머리 기호 제외)을 파싱하여 반환합니다.
    """
    path = get_memory_file_path()
    if not path.is_file():
        return []

    rules: list[str] = []
    try:
        content = path.read_text(encoding="utf-8")
        for line in content.splitlines():
            clean = line.strip()
            # 빈 줄이나 마크다운 헤더는 제외
            if not clean or clean.startswith("#"):
                continue
            # 글머리 기호(-, *, 숫자 등) 제거
            if clean.startswith(("- ", "* ")) or (
                len(clean) > 2 and clean[0].isdigit() and clean[1] in (".", ")")
            ):
                clean = clean[2:].strip()
            if clean:
                rules.append(clean)
    except Exception:  # noqa: BLE001
        return []

    return rules


def save_rule(rule: str) -> str:
    """
    새로운 핵심 규칙을 .yunhee/memory.md에 저장합니다.
    중복된 규칙은 배제하며, 최대 40라인 상한을 엄격히 강제합니다.
    """
    clean_rule = rule.strip()
    if not clean_rule:
        return "error: 저장할 규칙 내용이 비어 있습니다."

    # 시작 부호 정리
    if clean_rule.startswith(("- ", "* ")):
        clean_rule = clean_rule[2:].strip()

    existing_rules = load_rules()

    # 중복 체크
    for r in existing_rules:
        if r.lower() == clean_rule.lower():
            return f"안내: 이미 등록되어 있는 규칙입니다: '{clean_rule}'"

    # 라인 수 상한 가드
    if len(existing_rules) >= MAX_RULE_LINES:
        return (
            f"경고: 규칙 수가 최대 한도({MAX_RULE_LINES}개)에 도달하여 추가할 수 없습니다. "
            "16k 토큰 한계를 보호하기 위해 더 이상 사용하지 않는 이전 규칙을 .yunhee/memory.md에서 정리해주세요."
        )

    path = get_memory_file_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    # 신규 파일이면 헤더 생성
    if not path.is_file():
        header = "# Project Rules & Conventions\n\n"
        path.write_text(header + f"- {clean_rule}\n", encoding="utf-8")
    else:
        with path.open("a", encoding="utf-8") as f:
            f.write(f"- {clean_rule}\n")

    return f"✔ 규칙이 성공적으로 저장되었습니다 ({len(existing_rules) + 1}/{MAX_RULE_LINES}): '{clean_rule}'"


def get_rules_prompt_section() -> str:
    """
    시스템 프롬프트에 상시 주입할 마크다운 섹션 생성.
    규칙이 없으면 빈 문자열을 반환합니다.
    """
    rules = load_rules()
    if not rules:
        return ""

    lines = ["[프로젝트 핵심 규칙 및 컨벤션 (Rules of Engagement)]"]
    for r in rules:
        lines.append(f"- {r}")
    lines.append("")
    return "\n".join(lines)


def list_rules_text() -> str:
    """터미널 및 슬래시 커맨드 출력용 규칙 요약 텍스트."""
    path = get_memory_file_path()
    rules = load_rules()
    if not rules:
        return f"현재 등록된 핵심 규칙이 없습니다. ({path})"

    lines = [f"[bold cyan]📌 프로젝트 핵심 규칙 ({len(rules)}/{MAX_RULE_LINES})[/bold cyan] [dim]{path}[/dim]"]
    for idx, r in enumerate(rules, 1):
        lines.append(f"  {idx}. {r}")
    return "\n".join(lines)
