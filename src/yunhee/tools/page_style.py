"""화면 파일(.tsx / .java)의 페이지 스타일 ID(SID) 판별기.

SID 정의는 docs/page-style.md 참조:
19개 스타일:
SG · SGP · SGVF · SGEF · SGTP · SGT · TG · GG · CG · STP · TP · SR · GCG · SGHF · TO · GO · DSBRD · GDP · IN
판별 불가 시 '미분류'.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.base import ToolResult

DEFAULT_SIDS: tuple[str, ...] = (
    "SG",
    "SGP",
    "SGVF",
    "SGEF",
    "SGTP",
    "SGT",
    "TG",
    "GG",
    "CG",
    "STP",
    "TP",
    "SR",
    "GCG",
    "SGHF",
    "TO",
    "GO",
    "DSBRD",
    "GDP",
    "IN",
)
SIDS: tuple[str, ...] = DEFAULT_SIDS
UNKNOWN: str = "미분류"

# 정규식 패턴
GRID_TAG = re.compile(r"<(?:\w*Grid|\w+_Grid_\w+)\b")
TREE_MARK = re.compile(r"useTreeGrid|<Tree\b|treeData\b|<TreeGrid\b")
CHILD_IMPORT = re.compile(
    r"""from\s+['"](?:\./|\.\./\w+/)?(\w+_(?:Edit|TabPage|Page|Grid|Rd|Tab)_\w+)['"]"""
)

JAVA_GRID = re.compile(r"(?<![\w.])Grid<[^>]*>\s+\w+\s*[=;]")
JAVA_TREE = re.compile(r"(?<![\w.])(?:TreeGrid|Tree)<[^>]*>\s+\w+\s*[=;]")
JAVA_CHILD = re.compile(r"\bnew\s+(\w+_(?:Edit|TabPage|Page|Grid|Rd|Tab)_\w+)\s*\(")


def load_valid_sids() -> tuple[str, ...]:
    """docs/page-style.md 의 '## 스타일 목록' 표 첫 열에서 유효한 SID 목록을 로드한다."""
    cand_paths = [
        config.WORK_DIR / "docs" / "page-style.md",
        config.WORK_DIR / "AssetERP" / "docs" / "page-style.md",
        config.YUNHEE_DIR / "docs" / "page-style.md",
    ]
    for p in cand_paths:
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
                m = re.search(
                    r"##\s*스타일\s*목록.*?\n(\|.*?\n\|[-:\s|]+\n)(.*?\n\s*\n)",
                    text,
                    flags=re.DOTALL,
                )
                if m:
                    table_rows = m.group(2).strip().splitlines()
                    loaded: list[str] = []
                    for row in table_rows:
                        cols = [c.strip() for c in row.split("|") if c.strip()]
                        if cols:
                            sid_cand = cols[0]
                            if re.match(r"^[A-Z0-9_]{2,10}$", sid_cand):
                                loaded.append(sid_cand)
                    if loaded:
                        return tuple(loaded)
            except (OSError, UnicodeDecodeError):
                continue
    return DEFAULT_SIDS


def extract_declared(
    raw: str, valid_sids: tuple[str, ...] | None = None
) -> tuple[str | None, str | None]:
    """화면 소스에서 '스타일: XXX' 선언을 추출한다.

    머리 주석 '스타일: XXX (설명)' 에서 괄호 앞 SID만 추출하며,
    한 줄 주석(//) 및 블록 주석(/* */) 모두 지원한다.
    유효한 SID 목록에 없으면 (raw_declared, warning_message)를 반환한다.
    """
    m = re.search(r"(?:/\*|\*|//)[^\n]*?스타일:\s*([A-Za-z0-9_]{2,20})\b", raw)
    if not m:
        m = re.search(r"스타일:\s*([A-Za-z0-9_]{2,20})\b", raw)
    if not m:
        return None, None

    decl = m.group(1).upper()
    valid = valid_sids or load_valid_sids()
    if decl == "DB":
        warn = "선언된 스타일 'DB'는 'DSBRD'로 변경되었습니다."
        return "DSBRD", warn
    if decl not in valid:
        warn = f"선언된 스타일 '{decl}'은 유효한 SID 목록에 없습니다."
        return decl, warn
    return decl, None


def read_text(path: Path | str) -> str:
    """파일을 UTF-8(대체 허용)으로 읽는다."""
    p = Path(path)
    return p.read_text(encoding="utf-8", errors="replace")


def strip_comments(text: str) -> str:
    """/* */ 와 // 주석을 제거한다."""
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.DOTALL)
    return re.sub(r"(?<![:'\"])//[^\n]*", " ", text)


def find_sibling(path: Path | str, name: str, exts: tuple[str, ...]) -> Path | None:
    """같은 디렉토리의 자식 파일(예: _Edit_, _Page_, _Grid_)을 찾는다."""
    parent = Path(path).resolve().parent
    for ext in exts:
        cand = parent / f"{name}{ext}"
        if cand.is_file():
            return cand
    # 상위 디렉토리 하위 재귀 탐색 (../ 상대 참조 대응)
    if parent.parent.is_dir():
        for ext in exts:
            matches = list(parent.parent.rglob(f"{name}{ext}"))
            if matches:
                return matches[0]
    return None


def count_grids_trees(code: str) -> tuple[int, int]:
    """TSX 코드에서 (그리드 수, 트리 수)를 계산한다."""
    n = len(GRID_TAG.findall(code))
    if TREE_MARK.search(code):
        return 0, max(n, 1)
    return n, 0


def tsx_child_features(path: Path | str) -> dict[str, Any]:
    """TSX 자식 컴포넌트(_Edit_, _TabPage_, _Page_, _Grid_, _Rd_)의 특징을 추출한다."""
    p = Path(path)
    code = strip_comments(read_text(p))
    base = p.name
    raw_g, raw_t = count_grids_trees(code)
    g, t = raw_g, raw_t

    is_popup = bool(
        re.search(r"<(?:Modal|Drawer)\b|<\w*Modal\b|<\w*Dialog\b", code)
        or (re.search(r"\bopen\b\s*[:,}]", code) and "onClose" in code)
        or ("onCancel" in code and "Modal" in code)
        or re.search(r"<Modal\s+open\b", code)
    )
    has_tabs = bool(re.search(r"<(?:Tabs|PageTabs)\b", code))
    has_calendar = bool(re.search(r"<Calendar\b", code))
    has_rd = bool(re.search(r"<iframe\b|from\s+['\"][^'\"]*_Rd_[^'\"]*['\"]", code))

    kind = "Grid"
    edit = None
    if "_Edit_" in base:
        kind = "Edit"
        if is_popup:
            edit = "popup"
            g, t = 0, 0
        else:
            view = len(re.findall(r"\breadOnly\b", code)) >= 1 and not re.search(
                r'type=["\']save["\']|\bButton\b.*저장', code
            )
            edit = "view" if view else "edit"
            g, t = 0, 0
    elif "_TabPage_" in base:
        kind = "TabPage"
        g, t = 0, 0
    elif "_Page_" in base:
        kind = "Page"
    elif "_Rd_" in base:
        kind = "Rd"
        has_rd = True
    elif "_Tab_" in base:
        kind = "Tab"

    return {
        "kind": kind,
        "grids": g,
        "trees": t,
        "raw_grids": raw_g,
        "raw_trees": raw_t,
        "edit": edit,
        "popup": (edit == "popup"),
        "tabs": has_tabs,
        "calendar": has_calendar,
        "rd": has_rd,
    }


def extract_tsx(path: Path | str) -> tuple[dict[str, Any], str | None]:
    """TSX 화면 파일에서 특징과 선언된 스타일(declared), 경고를 추출한다."""
    p = Path(path)
    raw = read_text(p)
    valid_sids = load_valid_sids()
    declared, warning = extract_declared(raw, valid_sids)
    code = strip_comments(raw)

    g0, t0 = count_grids_trees(code)
    search = "<SearchBar" in code
    custom_search = bool(
        not search
        and (
            re.search(
                r'type=["\'](?:search|reset)["\']|<Button\b[^>]*>(?:조회|검색)',
                code,
            )
            or (
                re.search(
                    r"<(?:DatePicker|MonthPicker|RangePicker|Select|Input|Space|Typography\.Text|QuickMoveField|Radio|Checkbox|LookupInput)\b",
                    code,
                )
                and re.search(
                    r'type=["\'](?:search|reset)["\']|\b조회\b|onSearch|\bretrieve\b',
                    code,
                )
            )
        )
    )

    features: dict[str, Any] = {
        "search": search,
        "custom_search": custom_search,
        "grids": g0,
        "trees": t0,
        "edit": None,
        "popup": False,
        "tabs": bool(
            re.search(r"<(?:Tabs|PageTabs)\b", code)
            or "@/components/tabs" in code
        ),
        "tabpage": False,
        "tabpage_count": 0,
        "tabpage_has_tabs": False,
        "tabpage_has_grid": False,
        "calendar": bool(re.search(r"<Calendar\b", code)),
        "rd": bool(re.search(r"<iframe\b|from\s+['\"][^'\"]*_Rd_[^'\"]*['\"]", code)),
        "api_calls": bool(
            re.search(
                r"\b\w+Api\.\w+|\bclient\.\w+|\baxios\.\w+|\bfetch\(|\brdApi\b|\brdDownload\b",
                code,
            )
        ),
        "menu_link": bool(re.search(r"\bopenMenuByNo\b|\bnavigateMenu\b", code)),
        "layout": "none",
        "top_search": False,
        "editable_grid": False,
        "children": [],
        "delegate_to": None,
    }

    sp = re.search(r"<Splitter\b([^>]*)>", code)
    if sp:
        features["layout"] = (
            "vertical"
            if re.search(r'layout=["\']vertical["\']', sp.group(1))
            else "horizontal"
        )
        sb = code.find("<SearchBar")
        features["top_search"] = features["search"] and sb < sp.start()
    else:
        features["top_search"] = features["search"]

    # 껍데기 화면 위임 검사: 단일 _Tab_ 컴포넌트만 렌더링하고 자체 그리드/분할이 없는 경우
    tab_renders = re.findall(r"<(\w+_Tab_\w+)\b", code)
    tab_renders = [t for t in tab_renders if t != p.stem]
    if len(tab_renders) == 1 and g0 == 0 and t0 == 0 and not sp and not features["tabs"]:
        features["delegate_to"] = tab_renders[0]

    for name in CHILD_IMPORT.findall(code):
        if name == "Apr01_Edit_ApprDoc" and not p.name.startswith("Apr01_"):
            continue  # 전자결재 공통 팝업은 화면 자체의 편집 팝업(SGP)으로 치지 않는다
        sib = find_sibling(p, name, (".tsx",))
        if not sib:
            continue
        c = tsx_child_features(sib)
        features["children"].append(name)
        if c["kind"] != "TabPage" and not features["tabs"]:
            features["grids"] += c["grids"]
            features["trees"] += c["trees"]
        if c["popup"]:
            features["popup"] = True
        if c["kind"] in ("TabPage", "PageGrid") or c["tabs"]:
            features["tabpage"] = True
        if "_TabPage_" in name:
            features["tabpage_count"] += 1
            if c.get("tabs"):
                features["tabpage_has_tabs"] = True
            if c.get("raw_grids", 0) > 0:
                features["tabpage_has_grid"] = True
        if c["calendar"]:
            features["calendar"] = True
        if c["rd"]:
            features["rd"] = True
        if c["kind"] == "Edit" and c["edit"] in ("view", "edit") and features["edit"] is None:
            features["edit"] = c["edit"]

    # CG 판정: 셀 편집 전용 그리드 컴포넌트나 editable: true 가 있어야 함 (Button type='save' 단독 제외)
    features["editable_grid"] = features["edit"] is None and bool(
        re.search(
            r"<CellEditGrid\b|<ModalEditGrid\b|<EditGrid\b|<CrudGrid\b|useGridCrud\b|\beditable\s*:\s*true\b",
            code,
        )
    )
    if warning:
        features["warning"] = warning
    return features, declared


def java_child_features(path: Path | str) -> dict[str, Any]:
    """Java 자식 컴포넌트의 특징을 추출한다."""
    p = Path(path)
    code = strip_comments(read_text(p))
    base = p.name
    raw_grids = len(JAVA_GRID.findall(code))
    raw_trees = len(JAVA_TREE.findall(code))
    grids, trees = raw_grids, raw_trees
    has_tabs = bool(re.search(r"\b(?:TabPanel|PlainTabPanel)\b", code))
    has_calendar = bool(re.search(r"\b(?:Calendar|DatePicker)\b", code))
    has_rd = bool(re.search(r"\b(?:RDClient|RdViewer|RdReport)\b|_Rd_", code))

    is_popup = bool(re.search(r"\bclass\s+\w+\s+extends\s+\w*(?:Window|Dialog)\b", code))
    kind = "Grid"
    edit = None
    if "_Edit_" in base:
        kind = "Edit"
        if is_popup:
            edit = "popup"
            grids, trees = 0, 0
        else:
            view = len(re.findall(r"\.setReadOnly\(\s*true\s*\)", code)) >= 5
            edit = "view" if view else "edit"
            grids, trees = 0, 0
    elif "_TabPage_" in base:
        kind = "TabPage"
        grids, trees = 0, 0
    elif "_Page_" in base:
        kind = "Page"
    elif "_Rd_" in base:
        kind = "Rd"
        has_rd = True
    elif "_Tab_" in base:
        kind = "Tab"

    return {
        "kind": kind,
        "grids": grids,
        "trees": trees,
        "raw_grids": raw_grids,
        "raw_trees": raw_trees,
        "edit": edit,
        "popup": (edit == "popup"),
        "tabs": has_tabs,
        "calendar": has_calendar,
        "rd": has_rd,
    }


def extract_java(path: Path | str) -> tuple[dict[str, Any], str | None]:
    """Java GXT 화면 파일에서 특징과 선언된 스타일(declared)을 추출한다."""
    p = Path(path)
    raw = read_text(p)
    valid_sids = load_valid_sids()
    declared, warning = extract_declared(raw, valid_sids)
    code = strip_comments(raw)

    regions = {
        r: f"set{r}Widget(" in code
        for r in ("North", "South", "West", "East", "Center")
    }
    search = bool(re.search(r'retrieveButton|"조회"|ColorButtonBar', code))
    custom_search = bool(re.search(r'retrieveButton|"조회"', code))

    features: dict[str, Any] = {
        "search": search,
        "custom_search": custom_search,
        "grids": len(JAVA_GRID.findall(code)),
        "trees": len(JAVA_TREE.findall(code)),
        "edit": None,
        "popup": False,
        "tabs": bool(re.search(r"\b(?:TabPanel|PlainTabPanel)\b", code)),
        "tabpage": False,
        "tabpage_count": 0,
        "tabpage_has_tabs": False,
        "tabpage_has_grid": False,
        "calendar": bool(re.search(r"\b(?:Calendar|DatePicker)\b", code)),
        "rd": bool(re.search(r"\b(?:RDClient|RdViewer|RdReport)\b|_Rd_", code)),
        "api_calls": bool(
            re.search(
                r"\b(?:GridRetrieveData|ServiceRequest|GridInsertRow|GridUpdateData|GridDeleteData)\b",
                code,
            )
        ),
        "menu_link": bool(re.search(r"\bMenuOpener\b|\bopenMenu\b", code)),
        "layout": "none",
        "top_search": False,
        "editable_grid": False,
        "children": [],
        "regions": [r for r, v in regions.items() if v],
        "delegate_to": None,
    }

    if regions["South"] and not (regions["West"] or regions["East"]):
        features["layout"] = "vertical"
    elif regions["West"] or regions["East"]:
        features["layout"] = "horizontal"

    features["top_search"] = features["search"] and regions.get("North", False)

    # 껍데기 화면 위임 검사 (extends Other_Tab_)
    m_ext = re.search(r"\bclass\s+\w+\s+extends\s+(\w+_Tab_\w+)\b", code)
    if m_ext and features["grids"] == 0 and features["trees"] == 0:
        features["delegate_to"] = m_ext.group(1)

    for name in JAVA_CHILD.findall(code):
        if name == "Apr01_Edit_ApprDoc" and not p.name.startswith("Apr01_"):
            continue  # 전자결재 공통 팝업은 화면 자체의 편집 팝업(SGP)으로 치지 않는다
        sib = find_sibling(p, name, (".java",))
        if not sib:
            continue
        c = java_child_features(sib)
        features["children"].append(name)
        if c["kind"] != "TabPage" and not features["tabs"]:
            features["grids"] += c["grids"]
            features["trees"] += c["trees"]
        if c["popup"]:
            features["popup"] = True
        if c["kind"] in ("TabPage", "PageGrid") or c["tabs"]:
            features["tabpage"] = True
        if "_TabPage_" in name:
            features["tabpage_count"] += 1
            if c.get("tabs"):
                features["tabpage_has_tabs"] = True
            if c.get("raw_grids", 0) > 0:
                features["tabpage_has_grid"] = True
        if c["calendar"]:
            features["calendar"] = True
        if c["rd"]:
            features["rd"] = True
        if c["kind"] == "Edit" and c["edit"] in ("view", "edit") and features["edit"] is None:
            features["edit"] = c["edit"]

    features["editable_grid"] = features["edit"] is None and bool(
        re.search(
            r"GridInlineEditing|GridRowEditing|GridEditing|InterfaceGridOperate",
            code,
        )
    )
    if warning:
        features["warning"] = warning
    return features, declared


def classify(features: dict[str, Any], declared: str | None = None) -> tuple[str, str]:
    """추출된 특징으로부터 SID와 판별 근거를 결정한다."""
    g = features.get("grids", 0)
    t = features.get("trees", 0)
    e = features.get("edit")
    layout = features.get("layout", "none")
    popup = features.get("popup", False)
    search = features.get("search", False)
    top_search = features.get("top_search", False)
    custom_search = features.get("custom_search", False)
    has_any_search = search or top_search or custom_search
    editable_grid = features.get("editable_grid", False)
    tabs = features.get("tabs", False)
    tabpage = features.get("tabpage", False)
    has_tabs = tabs or tabpage
    calendar = features.get("calendar", False)
    rd = features.get("rd", False)
    api_calls = features.get("api_calls", False)
    menu_link = features.get("menu_link", False)

    # 1. 캘린더 + 그리드 (GCG)
    if calendar and g >= 1:
        return "GCG", "위아래 분할 + 그리드 둘 + 달력(Calendar)"

    # 2. RD 보고서 영역 (SR)
    if rd and has_any_search and g == 0 and t == 0 and not has_tabs:
        return "SR", "조회 툴바 + RD 보고서 영역(iframe)"

    # 3. 트리 관련 스타일 (SGT, TG, TO)
    if t >= 1:
        if layout == "horizontal":
            if top_search and g >= 1:
                return "SGT", "툴바 전체 폭 + 좌(그리드)·우(트리) 분할"
            return "TG", "트리 + 오른쪽 내용이 좌우 분할"
        return "TO", "트리 중심, 오른쪽이 일반 그리드가 아님/없음"

    # 4. GDP (Grid+DetailPage)
    has_detail_page = any(
        "_Page_" in c or "_TabPage_" in c for c in features.get("children", [])
    )
    if (
        (
            declared == "GDP"
            or (layout == "horizontal" and not search and not top_search and has_detail_page)
        )
        and g >= 1
    ):
        return "GDP", "좌우 분할 + 버튼 줄 + 그리드 + 오른쪽 상세 페이지"

    # 5. 폼(Edit/View Form)이 있는 경우 (SGVF, SGEF, SGHF)
    if e:
        if layout == "horizontal":
            return "SGHF", "조회 줄 + 그리드 + 편집 폼을 좌우로 배치"
        # SGEF vs SGVF 선언 우선 해소 (§2-1)
        if declared in ("SGEF", "SGVF"):
            kind_str = "읽기 전용" if declared == "SGVF" else "편집"
            return declared, f"위아래 분할 + 그리드 + {kind_str} 폼"
        if e == "view":
            return "SGVF", "위아래 분할 + 그리드 + 읽기 전용 폼"
        return "SGEF", "위아래 분할 + 그리드 + 편집 폼"

    # 6. 탭 / 대시보드 영역 관련 (DSBRD, SGTP, STP, TP)
    if (
        (
            declared == "DSBRD"
            or (not has_any_search and api_calls and not tabpage and not search and not menu_link)
        )
        and g == 0
        and t == 0
    ):
        return "DSBRD", "그리드·트리·툴바 없이 카드/요약 영역(조회 API 호출)"

    if has_tabs and g == 0 and t == 0:
        # STP vs TP 선언 우선 해소 (§2-1)
        if declared in ("STP", "TP"):
            if declared == "STP":
                return "STP", "툴바 + 탭 컨테이너, 그리드·트리 없음"
            return "TP", "탭 컨테이너만 있고 툴바·그리드·트리 없음"
        if has_any_search:
            return "STP", "툴바 + 탭 컨테이너, 그리드·트리 없음"
        return "TP", "탭 컨테이너만 있고 툴바·그리드·트리 없음"

    if has_tabs and layout == "vertical":
        if declared == "GG":
            return "GG", "그리드 2개(마스터·상세)"
        if declared == "SGTP":
            return "SGTP", "위아래 분할 + 그리드 + 아래 탭 영역"
        if g == 1:
            if features.get("tabs"):
                return "SGTP", "위아래 분할 + 그리드 + 아래 탭 영역(자체 탭)"
            if features.get("tabpage_has_tabs"):
                return "SGTP", "위아래 분할 + 그리드 + 아래 탭 영역(자식 탭 컨테이너)"
            if features.get("tabpage_count", 0) >= 2:
                return "SGTP", "위아래 분할 + 그리드 + 아래 탭 영역(다중 탭 전환)"
            if features.get("tabpage_count", 0) == 1 and features.get("tabpage_has_grid"):
                return "GG", "위아래 분할 + 그리드 둘(자식 TabPage에 그리드 포함)"
            return "SGTP", "위아래 분할 + 그리드 + 아래 탭 영역"
        return "GG", f"그리드 {g}개(마스터·상세)"

    # 7. 그리드 2개 이상 (GG)
    if g >= 2:
        return "GG", f"그리드 {g}개(마스터·상세)"

    # 8. 단일 그리드 (SGP, CG, SG, GO)
    if g == 1:
        if popup:
            return "SGP", "조회 툴바 + 그리드 하나 + 편집 팝업"
        if editable_grid:
            return "CG", "편집 가능한 그리드 하나"
        if search or top_search:
            return "SG", "조회 툴바 + 그리드 하나"
        return "GO", "그리드 하나 + 직접 만든 조건 줄 또는 조건 줄 없음"

    # 9. 그리드 0개, 트리 0개인 경우 (IN, DSBRD, STP, TP)
    if declared == "IN" or (not api_calls and menu_link and not has_tabs):
        return "IN", "조회·저장 없는 안내 문서(안내 문구 + 링크/HTML)"

    if declared == "DSBRD" or (api_calls and not has_tabs and not menu_link):
        return "DSBRD", "그리드·트리·툴바 없이 카드/요약 영역(조회 API 호출)"

    if has_tabs:
        if declared in ("STP", "TP"):
            return declared, f"선언된 스타일 ({declared})"
        if has_any_search:
            return "STP", "툴바 + 탭 컨테이너, 그리드·트리 없음"
        return "TP", "탭 컨테이너만 있고 툴바·그리드·트리 없음"

    if declared and declared in DEFAULT_SIDS:
        return declared, f"선언된 스타일 ({declared})"

    return UNKNOWN, "그리드 없음"


def analyze(path: Path | str) -> dict[str, Any]:
    """화면 파일(.tsx / .java)을 분석하여 판별 결과를 반환한다."""
    p = Path(path).resolve()
    if not p.is_file():
        raise FileNotFoundError(f"파일을 찾을 수 없습니다: {path}")

    ext = p.suffix.lower()
    if ext == ".tsx":
        features, declared = extract_tsx(p)
        side = "TOBE"
    elif ext == ".java":
        features, declared = extract_java(p)
        side = "AS-IS"
    else:
        raise ValueError(f"지원하지 않는 확장자: {ext} (.tsx / .java 만 지원)")

    warning = features.get("warning")

    # 껍데기 화면 위임 처리
    if features.get("delegate_to"):
        del_name = features["delegate_to"]
        parent_file = find_sibling(p, del_name, (ext,))
        if parent_file:
            parent_res = analyze(parent_file)
            sid = declared if declared else parent_res["sid"]
            why = f"{del_name} 위임 (상속 화면)"
            return {
                "file": p.name,
                "path": str(p),
                "side": side,
                "sid": sid,
                "declared": declared,
                "warning": warning,
                "why": why,
                "features": features,
            }

    sid, why = classify(features, declared=declared)
    return {
        "file": p.name,
        "path": str(p),
        "side": side,
        "sid": sid,
        "declared": declared,
        "warning": warning,
        "why": why,
        "features": features,
    }


def format_line(r: dict[str, Any]) -> str:
    """분석 결과를 한 줄 텍스트로 포맷팅한다."""
    s = f"{r['file']}  {r['sid']}  ({r['why']})"
    if r.get("warning"):
        s += f"  ⚠ {r['warning']}"
    if r.get("declared") and r["declared"] != r["sid"]:
        s += f"  ⚠ 선언 {r['declared']} ≠ 판별 {r['sid']}"
    return s


def compare_pages(path_a: Path | str, path_b: Path | str) -> dict[str, Any]:
    """두 화면(AS-IS, TOBE)을 분석하고 SID 일치 여부를 비교한다."""
    a = analyze(path_a)
    b = analyze(path_b)

    # AS-IS는 머리 주석 선언이 없는 레거시 파일이 대부분이므로,
    # TOBE의 선언된 스타일(b['declared'])을 바탕으로 AS-IS의 구조적 호환성을 재판별한다.
    if a.get("declared") is None and b.get("declared") and a["sid"] != b["sid"]:
        cand_sid, cand_why = classify(a["features"], declared=b["declared"])
        if cand_sid == b["sid"]:
            a["sid"] = cand_sid
            a["why"] = cand_why

    same = (a["sid"] == b["sid"]) and (a["sid"] != UNKNOWN)
    if same:
        msg = "일치"
    else:
        msg = f"⚠ 불일치: AS-IS {a['sid']} / TOBE {b['sid']}"
        if b.get("declared") and b["declared"] != b["sid"]:
            msg += f" (TOBE 선언 {b['declared']} ≠ 판별 {b['sid']})"
        elif a.get("declared") and a["declared"] != a["sid"]:
            msg += f" (AS-IS 선언 {a['declared']} ≠ 판별 {a['sid']})"

    return {
        "a": a,
        "b": b,
        "same": same,
        "message": msg,
    }


def scan_tab_files(dir_path: Path | str) -> list[Path]:
    """디렉토리 내의 모든 *_Tab_* 화면 파일(.tsx, .java)을 재귀적으로 검색한다."""
    root_dir = Path(dir_path).resolve()
    if not root_dir.is_dir():
        return []

    ignore_dirs = {
        ".git",
        "node_modules",
        "target",
        ".venv",
        "build",
        "dist",
        "__pycache__",
        ".yunhee",
    }
    found: list[Path] = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for name in files:
            if "_Tab_" in name and name.endswith((".tsx", ".java")):
                found.append(Path(root) / name)
    return sorted(found)


def resolve_target_path(
    target: str | Path, prefer_ext: str | None = None
) -> Path | None:
    """상대 경로, 절대 경로, 현재 작업 디렉토리, WORK_DIR, ASIS_SRC_DIR 등에서 대상 파일을 찾는다."""
    p = Path(target)
    if p.is_file():
        return p.resolve()

    # 1. 현재 디렉토리 기준
    cwd_cand = Path.cwd() / p
    if cwd_cand.is_file():
        return cwd_cand.resolve()

    # 2. WORK_DIR 기준
    work_cand = config.WORK_DIR / p
    if work_cand.is_file():
        return work_cand.resolve()

    target_name = p.name
    # 3. 확장자가 없는 경우 보정
    names_to_try = [target_name]
    if not target_name.endswith((".tsx", ".java")):
        if prefer_ext:
            names_to_try = [f"{target_name}{prefer_ext}"]
        else:
            names_to_try = [f"{target_name}.tsx", f"{target_name}.java"]

    for name in names_to_try:
        # WORK_DIR 하위 glob 탐색
        found = list(config.WORK_DIR.glob(f"**/{name}"))
        if found:
            return found[0].resolve()

        # ASIS_SRC_DIR 하위 glob 탐색
        if config.ASIS_SRC_DIR and config.ASIS_SRC_DIR.is_dir():
            found = list(config.ASIS_SRC_DIR.glob(f"**/{name}"))
            if found:
                return found[0].resolve()

    return None


def analyze_page_tool(target: str | Path) -> ToolResult:
    """ToolResult 규격을 만족하는 단일 화면 판별 도구 함수."""
    p = resolve_target_path(target)
    if not p:
        return ToolResult(ok=False, error=f"화면 파일을 찾을 수 없습니다: {target}")
    try:
        res = analyze(p)
        return ToolResult(ok=True, data=res)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))
