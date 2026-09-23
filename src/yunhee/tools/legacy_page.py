import os

from yunhee.config import ASIS_SRC_DIR
from yunhee.tools.base import ToolResult

SOURCE_EXTENSIONS = (".java", ".xml")
PER_FILE_CHAR_LIMIT = 6000
TOTAL_CHAR_LIMIT = 40000


def find_page_files(page_code: str) -> ToolResult:
    """ASIS_SRC_DIR 아래에서 파일명이 `<page_code>_`로 시작하는 소스 파일을 전부 찾는다.

    페이지 코드는 GXT 소스의 파일명 접두사로 인코딩되어 있다 (예: Ast01_Tab_InfoManagement.java,
    ast01_class_tree.xml). Maven 빌드 산출물(target/)은 제외한다.
    """
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

    # 예산이 부족해 일부만 담기게 될 때, 부수적인 client 팝업/룩업 파일보다
    # 실제 비즈니스 로직이 들어있는 mapper XML(SQL) → server 클래스 → 메인 화면(Tab_) 순으로 채우고
    # Edit_/Grid_/Lookup_/Move_ 같은 보조 팝업 컴포넌트는 가장 나중에 잘리게 한다.
    def _priority(path: str) -> tuple[int, str]:
        normalized = path.replace(os.sep, "/")
        basename = normalized.rsplit("/", 1)[-1].lower()
        if "/mapper/" in normalized:
            tier = 0
        elif "/server/" in normalized:
            tier = 1
        elif "_tab_" in basename:
            tier = 2
        else:
            tier = 3
        return (tier, normalized)

    matches.sort(key=_priority)

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
