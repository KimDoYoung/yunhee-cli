"""화면 파일(.tsx / .java)의 페이지 스타일 ID(SID) 판별기.

SID 정의는 docs/page-type.md 참조:
SG · SGP · SGVF · SGEF · SGT · TG · GG · CG, 판별 불가 시 '미분류'.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.base import ToolResult

SIDS: tuple[str, ...] = ("SG", "SGP", "SGVF", "SGEF", "SGTP", "SGT", "TG", "GG", "CG")
UNKNOWN: str = "미분류"

# 정규식 패턴
GRID_TAG = re.compile(r"<(?:\w*Grid|\w+_Grid_\w+)\b")
TREE_MARK = re.compile(r"useTreeGrid|<Tree\b|treeData\b")
CHILD_IMPORT = re.compile(r"""from\s+['"]\./(\w+_(?:Edit|TabPage|Page|Grid)_\w+)['"]""")

JAVA_GRID = re.compile(r"(?<![\w.])Grid<[^>]*>\s+\w+\s*[=;]")
JAVA_TREE = re.compile(r"(?<![\w.])(?:TreeGrid|Tree)<[^>]*>\s+\w+\s*[=;]")
JAVA_CHILD = re.compile(r"\bnew\s+(\w+_(?:Edit|TabPage|Page|Grid)_\w+)\s*\(")


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
    return None


def count_grids_trees(code: str) -> tuple[int, int]:
    """TSX 코드에서 (그리드 수, 트리 수)를 계산한다."""
    n = len(GRID_TAG.findall(code))
    if TREE_MARK.search(code):
        return 0, max(n, 1)
    return n, 0


def tsx_child_features(path: Path | str) -> tuple[str, int, int, str | None]:
    """TSX 자식 컴포넌트(_Edit_, _Page_, _Grid_)의 특징을 추출한다."""
    p = Path(path)
    code = strip_comments(read_text(p))
    base = p.name
    grids, trees = count_grids_trees(code)
    if "_Edit_" in base:
        if (
            re.search(r"<(?:Modal|Drawer)\b|<\w*Modal\b|<\w*Dialog\b", code)
            or (re.search(r"\bopen\b\s*[:,}]", code) and "onClose" in code)
        ):
            return "Edit", grids, trees, "popup"
        view = len(re.findall(r"\breadOnly\b", code)) >= 1 and not re.search(r'type=["\']save["\']', code)
        return "Edit", grids, trees, ("view" if view else "edit")
    if "_TabPage_" in base:
        return "TabPage", 0, 0, None  # 탭 안의 그리드·폼은 이 화면의 구조로 세지 않는다
    if "_Page_" in base:
        return "Page", grids, trees, None
    return "Grid", grids, trees, None


def extract_tsx(path: Path | str) -> tuple[dict[str, Any], str | None]:
    """TSX 화면 파일에서 특징과 선언된 스타일(declared)을 추출한다."""
    p = Path(path)
    raw = read_text(p)
    declared: str | None = None
    m = re.search(r"스타일:\s*([A-Z]{2,4})\b", raw)
    if m:
        declared = m.group(1)
    code = strip_comments(raw)

    g0, t0 = count_grids_trees(code)
    features: dict[str, Any] = {
        "search": "<SearchBar" in code,
        "grids": g0,
        "trees": t0,
        "edit": None,
        "popup": False,
        "tabpage": False,
        "layout": "none",
        "top_search": False,
        "editable_grid": False,
        "children": [],
    }

    sp = re.search(r"<Splitter\b([^>]*)>", code)
    if sp:
        features["layout"] = "vertical" if re.search(r'layout=["\']vertical["\']', sp.group(1)) else "horizontal"
        sb = code.find("<SearchBar")
        features["top_search"] = features["search"] and sb < sp.start()
    else:
        features["top_search"] = features["search"]

    for name in CHILD_IMPORT.findall(code):
        sib = find_sibling(p, name, (".tsx",))
        if not sib:
            continue
        kind, g, t, edit = tsx_child_features(sib)
        features["children"].append(name)
        features["grids"] += g
        features["trees"] += t
        if kind == "Edit" and edit == "popup":
            features["popup"] = True
        elif kind == "TabPage":
            features["tabpage"] = True
        elif kind == "Edit" and features["edit"] is None:
            features["edit"] = edit

    features["editable_grid"] = features["edit"] is None and bool(
        re.search(r'<Button\s+type=["\']save["\']', code)
        or re.search(r"\beditable\s*:\s*true|<EditGrid|<CrudGrid|GridInsertRow", code)
    )
    return features, declared


def java_child_features(path: Path | str) -> tuple[str, int, int, str | None]:
    """Java 자식 컴포넌트의 특징을 추출한다."""
    p = Path(path)
    code = strip_comments(read_text(p))
    base = p.name
    grids = len(JAVA_GRID.findall(code))
    trees = len(JAVA_TREE.findall(code))
    if "_Edit_" in base:
        if re.search(r"\bclass\s+\w+\s+extends\s+\w*(?:Window|Dialog)\b", code):
            return "Edit", grids, trees, "popup"
        view = len(re.findall(r"\.setReadOnly\(\s*true\s*\)", code)) >= 5
        return "Edit", grids, trees, ("view" if view else "edit")
    if "_TabPage_" in base:
        return "TabPage", 0, 0, None
    if "_Page_" in base:
        return "Page", grids, trees, None
    return "Grid", grids, trees, None


def extract_java(path: Path | str) -> tuple[dict[str, Any], str | None]:
    """Java GXT 화면 파일에서 특징과 선언된 스타일(declared)을 추출한다."""
    p = Path(path)
    raw = read_text(p)
    declared: str | None = None
    m = re.search(r"스타일:\s*([A-Z]{2,4})\b", raw)
    if m:
        declared = m.group(1)
    code = strip_comments(raw)

    regions = {r: f"set{r}Widget(" in code for r in ("North", "South", "West", "East", "Center")}
    features: dict[str, Any] = {
        "search": bool(re.search(r'retrieveButton|"조회"|ColorButtonBar', code)),
        "grids": len(JAVA_GRID.findall(code)),
        "trees": len(JAVA_TREE.findall(code)),
        "edit": None,
        "popup": False,
        "tabpage": False,
        "layout": "none",
        "top_search": False,
        "editable_grid": False,
        "children": [],
        "regions": [r for r, v in regions.items() if v],
    }

    if regions["South"] and not (regions["West"] or regions["East"]):
        features["layout"] = "vertical"
    elif regions["West"] or regions["East"]:
        features["layout"] = "horizontal"

    features["top_search"] = features["search"] and regions["North"]

    for name in JAVA_CHILD.findall(code):
        sib = find_sibling(p, name, (".java",))
        if not sib:
            continue
        kind, g, t, edit = java_child_features(sib)
        features["children"].append(name)
        features["grids"] += g
        features["trees"] += t
        if kind == "Edit" and edit == "popup":
            features["popup"] = True
        elif kind == "TabPage":
            features["tabpage"] = True
        elif kind == "Edit" and features["edit"] is None:
            features["edit"] = edit

    features["editable_grid"] = features["edit"] is None and bool(
        re.search(
            r'GridInsertRow|InterfaceGridOperate|GridInlineEditing|GridRowEditing|GridEditing|ColorButtonBar\("저장"\)',
            code,
        )
    )
    return features, declared


def classify(features: dict[str, Any]) -> tuple[str, str]:
    """추출된 특징으로부터 SID와 판별 근거를 결정한다."""
    g, t, e = features.get("grids", 0), features.get("trees", 0), features.get("edit")
    layout = features.get("layout", "none")

    if e and t == 0 and layout == "vertical":
        sid = "SGVF" if e == "view" else "SGEF"
        kind_str = "읽기 전용" if e == "view" else "편집"
        return sid, f"위아래 분할 + 그리드 + {kind_str} 폼"

    if features.get("tabpage") and g == 1 and t == 0 and layout == "vertical":
        return "SGTP", "위아래 분할 + 그리드 + 아래 탭 영역"

    if e:
        return UNKNOWN, f"편집 폼이 있으나 위아래 분할이 아니다 (layout={layout}, trees={t})"

    if t >= 1 and g >= 1 and layout == "horizontal":
        if features.get("top_search"):
            return "SGT", "툴바 전체 폭 + 좌우 분할(그리드·트리)"
        return "TG", "좌우 분할(트리·그리드), 툴바가 전체 폭이 아니다"

    if t >= 1:
        return UNKNOWN, "트리가 있으나 그리드와 좌우 분할이 아니다"

    if g >= 2:
        return "GG", f"그리드 {g}개"

    if g == 1:
        if features.get("popup"):
            return "SGP", "조회 툴바 + 그리드 하나 + 편집 팝업"
        if features.get("editable_grid"):
            return "CG", "편집 가능한 그리드 하나"
        if features.get("search"):
            return "SG", "조회 툴바 + 그리드 하나"
        return UNKNOWN, "그리드 하나, 조회 툴바 없음"

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

    sid, why = classify(features)
    return {
        "file": p.name,
        "path": str(p),
        "side": side,
        "sid": sid,
        "declared": declared,
        "why": why,
        "features": features,
    }


def format_line(r: dict[str, Any]) -> str:
    """분석 결과를 한 줄 텍스트로 포맷팅한다."""
    s = f"{r['file']}  {r['sid']}  ({r['why']})"
    if r.get("declared") and r["declared"] != r["sid"]:
        s += f"  ⚠ 선언 {r['declared']} ≠ 판별 {r['sid']}"
    return s


def compare_pages(path_a: Path | str, path_b: Path | str) -> dict[str, Any]:
    """두 화면(AS-IS, TOBE)을 분석하고 SID 일치 여부를 비교한다."""
    a = analyze(path_a)
    b = analyze(path_b)
    same = (a["sid"] == b["sid"]) and (a["sid"] != UNKNOWN)
    msg = "일치" if same else f"⚠ 불일치: AS-IS {a['sid']} / TOBE {b['sid']}"
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

    ignore_dirs = {".git", "node_modules", "target", ".venv", "build", "dist", "__pycache__", ".yunhee"}
    found: list[Path] = []
    for root, dirs, files in os.walk(root_dir):
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        for name in files:
            if "_Tab_" in name and name.endswith((".tsx", ".java")):
                found.append(Path(root) / name)
    return sorted(found)


def resolve_target_path(target: str | Path, prefer_ext: str | None = None) -> Path | None:
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
