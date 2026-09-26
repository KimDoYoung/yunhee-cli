import os
import re

from yunhee.config import ASIS_SRC_DIR
from yunhee.tools.base import ToolResult

SOURCE_EXTENSIONS = (".java", ".xml")
PER_FILE_CHAR_LIMIT = 6000
TOTAL_CHAR_LIMIT = 40000

# page_code allowlist: 영문자·숫자·밑줄·하이픈만 허용 (path traversal 방지)
_PAGE_CODE_RE = re.compile(r'^[a-zA-Z0-9_-]+$')


def validate_page_code(page_code: str) -> str | None:
    """유효하지 않으면 오류 메시지 반환, 유효하면 None."""
    if not _PAGE_CODE_RE.match(page_code):
        return "page_code는 영문자·숫자·밑줄·하이픈만 허용합니다 (경로 문자 불가)."
    return None


def _priority(path: str) -> tuple[int, str]:
    normalized = path.replace(os.sep, "/")
    basename = normalized.rsplit("/", 1)[-1].lower()
    if "/mapper/" in normalized:
        tier = 0
    elif "/server/" in normalized:
        tier = 1
    elif "/model/" in normalized:
        # VO/데이터 모델 클래스 — Spring Boot DTO/Entity 구조 파악에 필수
        tier = 1
    elif "_tab_" in basename:
        tier = 2
    else:
        tier = 3
    return (tier, normalized)


def _collect_matches(page_code: str) -> list[str] | ToolResult:
    if not ASIS_SRC_DIR.is_dir():
        return ToolResult(ok=False, error=f"ASIS 소스 경로를 찾을 수 없습니다: {ASIS_SRC_DIR}")

    prefix = f"{page_code}_".lower()
    matches: list[str] = []
    for root, dirs, files in os.walk(ASIS_SRC_DIR):
        dirs[:] = [d for d in dirs if d != "target"]
        for filename in files:
            if not filename.lower().endswith(SOURCE_EXTENSIONS):
                continue
            if not filename.lower().startswith(prefix):
                continue
            matches.append(os.path.join(root, filename))

    if not matches:
        return ToolResult(ok=False, error=f"페이지 코드 '{page_code}'에 해당하는 파일을 찾지 못했습니다.")

    matches.sort(key=_priority)
    return matches


def find_page_files(page_code: str) -> ToolResult:
    """ASIS_SRC_DIR 아래에서 파일명이 `<page_code>_`로 시작하는 소스 파일을 찾아 예산 내에서 반환한다.

    페이지 코드는 GXT 소스의 파일명 접두사로 인코딩되어 있다 (예: Ast01_Tab_InfoManagement.java,
    ast01_class_tree.xml). Maven 빌드 산출물(target/)은 제외한다.
    우선순위: mapper XML(0) → server/model 클래스(1) → Tab_ 메인화면(2) → 나머지 팝업(3).
    """
    result = _collect_matches(page_code)
    if isinstance(result, ToolResult):
        return result
    matches = result

    truncated = False
    total = 0
    files_data = []
    for path in matches:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > PER_FILE_CHAR_LIMIT:
            content = content[:PER_FILE_CHAR_LIMIT]
            truncated = True

        remaining = TOTAL_CHAR_LIMIT - total
        if remaining <= 0:
            truncated = True
            break
        if len(content) > remaining:
            content = content[:remaining]
            truncated = True

        total += len(content)
        files_data.append({"path": os.path.relpath(path, ASIS_SRC_DIR), "content": content})

    return ToolResult(ok=True, data=files_data, truncated=truncated)


def find_all_page_files(page_code: str) -> ToolResult:
    """예산 제한 없이 해당 페이지의 모든 파일을 반환한다 (2단계 요약용).

    파일별 PER_FILE_CHAR_LIMIT는 유지하되 총량 제한은 없음.
    """
    result = _collect_matches(page_code)
    if isinstance(result, ToolResult):
        return result
    matches = result

    files_data = []
    for path in matches:
        with open(path, encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > PER_FILE_CHAR_LIMIT:
            content = content[:PER_FILE_CHAR_LIMIT]
        files_data.append({"path": os.path.relpath(path, ASIS_SRC_DIR), "content": content})

    return ToolResult(ok=True, data=files_data, truncated=False)
