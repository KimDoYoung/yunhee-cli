"""test-gen-screen: 화면번호 → 화면 시험 단계 목록(.gen.cjs) 정적 생성기.

로컬 LLM을 사용하지 않고 TSX 소스와 카탈로그, 버튼 타입 규칙(docs/button-types.md 및 screen-test-rules.json),
프론트 공통 부품 규칙(docs/1-변환/11-프론트부품.md)만을 사용해 결정적(deterministic)으로
브라우저 단계 목록(.gen.cjs)을 생성한다.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yunhee import config, project
from yunhee.tools.base import ToolResult
from yunhee.tools.page_style import UNKNOWN as SID_UNKNOWN
from yunhee.tools.page_style import analyze as analyze_page_style
from yunhee.tools.trace.resolve import TraceContext, load_context
from yunhee.tools.trace.screen_catalog import (
    _IMPORT_RE,
    ScreenRecord,
    _is_valid_propagated_title,
    _load_full_menu_map,
    iter_screens,
)
from yunhee.tools.trace.screen_desc import (
    describe_single_screen,
    parse_screen_targets,
)
from yunhee.tools.trace.tobe import TobeLayout, find_layout
from yunhee.tools.trace.tobe_rag import _load_menus_from_snapshot

# AntD 기본 Button type (button-types.md의 의미론적 type이 아님 → type 없음/위험으로 취급)
_ANTD_NATIVE_BUTTON_TYPES = {"primary", "default", "dashed", "text", "link", "ghost"}

# 인라인 하위 컴포넌트로 순회하지 않을 공통 UI/프리미티브 컴포넌트 이름 집합
_PRIMITIVE_COMPONENTS = {
    "Button",
    "ExpandCollapseButtons",
    "TreeListToggle",
    "TreeListControlButtons",
    "SearchBar",
    "SearchPanel",
    "LookupInput",
    "CompanyPopupField",
    "LookupModal",
    "EditModal",
    "EditField",
    "EditRow",
    "SingleGrid",
    "MultiGrid",
    "CellEditGrid",
    "ModalEditGrid",
    "BaseGrid",
    "TreeGrid",
    "PagingToolBar",
    "PageTabs",
    "SystemCodeComboBox",
    "QuickMoveField",
    "QuickMoveDateField",
    "FileUpdownForm",
    "HtmlEditor",
    "TiptapEditor",
    "HtmlView",
    "PDFViewer",
    "Sys95_PDFViewer",
    "RdViewer",
    "AreaMessage",
    "SettingPopup",
}

_MODAL_JSX_RE = re.compile(r"<(?:LookupModal|EditModal|Modal|PDFViewer|Sys95_PDFViewer|RdViewer)\b")
_POPUP_NAME_RE = re.compile(r"_(?:Lookup|Popup|Move)_")


@dataclass
class ScreenTestRules:
    safe_button_types: set[str] = field(default_factory=set)
    danger_button_types: set[str] = field(default_factory=set)
    implicit_components: dict[str, Any] = field(default_factory=dict)
    icon_safe_kinds: set[str] = field(default_factory=set)
    icon_danger_kinds: set[str] = field(default_factory=set)

    def is_known_button_type(self, btn_type: str | None) -> bool:
        if not btn_type or btn_type in _ANTD_NATIVE_BUTTON_TYPES:
            return False
        return btn_type in self.safe_button_types or btn_type in self.danger_button_types

    def is_safe_button_type(self, btn_type: str | None) -> bool:
        if not btn_type or btn_type in _ANTD_NATIVE_BUTTON_TYPES:
            return False
        return btn_type in self.safe_button_types


@dataclass
class ScreenGenItem:
    screen_no: str
    menu_path: str
    sid: str
    main_component: str
    rel_file: str
    file_hash: str
    steps: list[dict[str, Any]]
    unknown: list[dict[str, str]]
    out_path: Path | None = None
    status: str = "generated"  # created | updated | unchanged | forced | stdout
    diff_summary: str = ""

    @property
    def danger_count(self) -> int:
        return sum(1 for s in self.steps if s.get("danger"))

    @property
    def enabled_count(self) -> int:
        return sum(1 for s in self.steps if s.get("enabled", True) is not False)


def _find_rules_path(tobe_root: Path, custom_path: Path | None = None) -> Path | None:
    if custom_path and custom_path.is_file():
        return custom_path
    candidates = [
        tobe_root / "tools" / "tests" / "screen-test" / "rules.json",
        tobe_root / ".yunhee" / "screen-test-rules.json",
        Path(config.WORK_DIR) / "tools" / "tests" / "screen-test" / "rules.json",
        Path(config.WORK_DIR) / ".yunhee" / "screen-test-rules.json",
        Path(config.YUNHEE_DIR) / "data" / "screen-test-rules.json",
        Path(__file__).resolve().parent.parent.parent / "data" / "screen-test-rules.json",
    ]
    for cand in candidates:
        if cand.is_file():
            return cand
    return None


def _parse_button_types_md(md_path: Path) -> set[str]:
    """docs/button-types.md의 `## type 표`에서 백틱으로 감싼 type 이름들을 추출한다."""
    types: set[str] = set()
    if not md_path.is_file():
        return types
    try:
        text = md_path.read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"^\|\s*`([a-zA-Z][a-zA-Z0-9_]*)`\s*\|", text, re.MULTILINE):
            types.add(m.group(1))
    except OSError:
        pass
    return types


def load_screen_test_rules(tobe_root: Path, custom_path: Path | None = None) -> ScreenTestRules:
    rules_path = _find_rules_path(tobe_root, custom_path)
    raw: dict[str, Any] = {}
    if rules_path:
        try:
            raw = json.loads(rules_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            raw = {}

    bt = raw.get("buttonTypes") or {}
    safe_set = set(
        bt.get("safe")
        or [
            "search", "view", "expand", "collapse", "close", "cancel",
            "reset", "select", "selectNone", "org", "settings", "shortcut",
            "goto", "print", "download",
        ]
    )
    danger_set = set(
        bt.get("danger")
        or [
            "save", "delete", "removeRow", "send", "register", "generate",
            "calculate", "assign", "unassign", "change", "move", "upload",
            "attach", "bookmark", "plus", "minus", "group", "addRow",
        ]
    )

    # docs/button-types.md에 새로 등록된 type이 있고 safe에 없으면 danger에 편입
    for md_cand in (
        tobe_root / "docs" / "button-types.md",
        Path(config.WORK_DIR) / "docs" / "button-types.md",
    ):
        for t in _parse_button_types_md(md_cand):
            if t not in safe_set and t not in danger_set:
                danger_set.add(t)

    ic = raw.get("iconCell") or {}
    icon_safe = set(ic.get("safeKinds") or ["view", "history", "down", "edit"])
    icon_danger = set(ic.get("dangerKinds") or ["delete", "send", "upload", "add", "check", "move"])

    return ScreenTestRules(
        safe_button_types=safe_set,
        danger_button_types=danger_set,
        implicit_components=raw.get("implicitComponents") or {},
        icon_safe_kinds=icon_safe,
        icon_danger_kinds=icon_danger,
    )


def _line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, max(0, pos)) + 1


def _strip_comments_preserve_newlines(text: str) -> str:
    """줄 번호를 보존하면서 주석(/* ... */, // ..., {/* ... */})을 공백으로 치환한다."""
    out = list(text)
    i = 0
    n = len(text)
    in_str: str | None = None
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'", "`"):
            in_str = ch
            i += 1
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            if end == -1:
                end = n
            else:
                end += 2
            for k in range(i, end):
                if out[k] != "\n":
                    out[k] = " "
            i = end
            continue
        if ch == "/" and i + 1 < n and text[i + 1] == "/":
            end = text.find("\n", i + 2)
            if end == -1:
                end = n
            for k in range(i, end):
                out[k] = " "
            i = end
            continue
        i += 1
    return "".join(out)


def _find_tag_end(text: str, tag_start: int) -> tuple[int, bool]:
    """JSX 여는 태그 `<Tag ...`의 시작 위치에서 닫는 `>` 위치를 찾는다.

    반환: (닫는 `>` 다음 인덱스, self_closing 여부)
    """
    i = tag_start + 1
    n = len(text)
    brace_depth = 0
    paren_depth = 0
    in_str: str | None = None
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", "`"):
                in_str = ch
            elif ch == "{":
                brace_depth += 1
            elif ch == "}":
                brace_depth = max(0, brace_depth - 1)
            elif ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth = max(0, paren_depth - 1)
            elif brace_depth == 0 and paren_depth == 0 and ch == ">":
                # `=>` 화살표 연산자는 제외
                if i > 0 and text[i - 1] == "=":
                    i += 1
                    continue
                self_close = i > tag_start and text[i - 1] == "/"
                return i + 1, self_close
        i += 1
    return min(n, tag_start + 500), True


def _find_matching_close_tag(text: str, tag_name: str, open_end: int) -> int:
    """동일 태그 이름의 중첩을 고려하여 닫는 태그 `</tag_name>`의 시작 위치를 찾는다."""
    esc = re.escape(tag_name)
    pat = re.compile(rf"<(/?){esc}\b")
    depth = 1
    pos = open_end
    while depth > 0:
        m = pat.search(text, pos)
        if not m:
            return -1
        is_close = bool(m.group(1))
        if is_close:
            depth -= 1
            if depth == 0:
                return m.start()
            pos = m.end()
        else:
            t_end, self_closing = _find_tag_end(text, m.start())
            if not self_closing:
                depth += 1
            pos = t_end
    return -1


def _extract_brace_attr(attrs: str, attr_name: str) -> str | None:
    """`attr_name={...}`에서 중첩 중괄호를 고려해 내부 표현식 문자열을 반환한다."""
    m = re.search(rf"\b{re.escape(attr_name)}\s*=\s*\{{", attrs)
    if not m:
        return None
    i = m.end()
    n = len(attrs)
    depth = 1
    in_str: str | None = None
    while i < n:
        ch = attrs[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", "`"):
                in_str = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return attrs[m.end() : i].strip()
        i += 1
    return None


def _extract_str_attr(attrs: str, attr_name: str) -> str | None:
    """`attr_name="값"` 또는 `attr_name={'값'}`에서 문자열 리터럴 값을 추출한다."""
    m = re.search(rf'\b{re.escape(attr_name)}\s*=\s*(["\'])(.*?)\1', attrs)
    if m:
        return m.group(2).strip()
    expr = _extract_brace_attr(attrs, attr_name)
    if expr:
        m_lit = re.fullmatch(r'(["\'])(.*?)\1', expr.strip())
        if m_lit:
            return m_lit.group(2).strip()
    return None


def _has_bool_attr(attrs: str, attr_name: str) -> bool:
    """`readOnly` 또는 `readOnly={true}` 존재 여부를 확인한다 (`readOnly={false}`나 `readOnly={!editable}`은 제외)."""
    m = re.search(rf"\b{re.escape(attr_name)}\b(?:\s*=\s*(\{{[^}}]*\}}|['\"][^'\"]*['\"]))?", attrs)
    if not m:
        return False
    val = m.group(1)
    if val is None:
        return True
    clean = val.strip("{} '\"").lower()
    return clean in ("true", "1")


def _clean_jsx_text(inner: str) -> str:
    """JSX 태그 내부의 순수 텍스트만 추출한다."""
    # HTML 엔티티 복원
    txt = inner.replace("&gt;", ">").replace("&lt;", "<").replace("&amp;", "&").replace("&nbsp;", " ")
    # 내부 JSX 태그 제거
    txt = re.sub(r"<[^>]+>", "", txt)
    # 중괄호 표현식 제거 (단, 문자열 리터럴 `{'조회'}` 형태는 살림)
    txt = re.sub(r"\{\s*(['\"])(.*?)\1\s*\}", r"\2", txt)
    txt = re.sub(r"\{[^{}]*\}", "", txt)
    txt = re.sub(r"\s+", " ", txt).strip()
    # 앞쪽 `>> ` 같은 장식 기호 정리
    txt = re.sub(r"^(?:>>|▶|※)\s*", "", txt).strip()
    return txt


def _is_conditional_at(clean_text: str, pos: int, jsx_base: int = 0) -> bool:
    """`pos` 위치의 JSX 요소가 조건부 렌더링(`{cond && <...>}` 또는 `{cond ? <...> : ...}`) 안에 있는지 판별한다."""
    # jsx_base부터 pos까지 열려 있는 중괄호 스택 추적
    stack: list[int] = []
    i = max(0, jsx_base)
    in_str: str | None = None
    while i < pos:
        ch = clean_text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", "`"):
                in_str = ch
            elif ch == "{":
                stack.append(i)
            elif ch == "}" and stack:
                stack.pop()
        i += 1

    for brace_pos in reversed(stack):
        # 속성 값 `prop={...}`인지 확인
        before = clean_text[max(0, brace_pos - 30) : brace_pos].rstrip()
        if before.endswith("="):
            continue
        segment = clean_text[brace_pos + 1 : pos]
        # `.map(` 루프는 조건부가 아님
        if ".map(" in segment:
            continue
        # `!saving &&` 또는 `!loading &&` 같은 단순 로딩 가드는 상시 표시 버튼이므로 제외
        if re.match(r"^\s*!\s*(?:saving|loading|busy)\s*&&", segment):
            continue
        if "&&" in segment or "?" in segment:
            return True
    return False


def _is_modal_component(
    rec: ScreenRecord,
    parent_clean_text: str | None = None,
) -> bool:
    """해당 컴포넌트가 모달(팝업)인지 인라인 하위 컴포넌트(Page/TabPage/Grid/하단Edit폼)인지 판별한다."""
    if _POPUP_NAME_RE.search(rec.name):
        return True
    if rec.role in ("Tab", "TabPage", "Page", "Grid"):
        return False
    txt = rec.text
    if _MODAL_JSX_RE.search(_strip_comments_preserve_newlines(txt)):
        return True
    if parent_clean_text:
        for m in re.finditer(rf"<{re.escape(rec.name)}\b", parent_clean_text):
            t_end, _ = _find_tag_end(parent_clean_text, m.start())
            attrs = parent_clean_text[m.start() : t_end]
            if re.search(r"\b(?:open|onClose|onCancel)\s*=", attrs):
                return True
    return False


def resolve_modal_title(rec: ScreenRecord | None, comp_name: str = "") -> str | bool:
    """모달 컴포넌트의 기대 타이틀(expectModal)을 정적으로 추출한다.
    글자 상수가 아니면(title={변수}, JSX, 템플릿 문자열 등) True를 반환한다.
    모달을 식별할 수 없으면 ""를 반환한다.
    """
    if comp_name in ("PDFViewer", "Sys95_PDFViewer"):
        return "PDF Viewer"
    if not rec:
        return ""
    txt = rec.text
    clean_txt = _strip_comments_preserve_newlines(txt)

    modal_tag_pat = re.compile(r"<(LookupModal|EditModal|Modal)\b")
    has_modal_tag = False
    for m in modal_tag_pat.finditer(clean_txt):
        has_modal_tag = True
        t_end, _ = _find_tag_end(clean_txt, m.start())
        attrs = clean_txt[m.start() : t_end]

        # 1. title="문자열" 또는 title='문자열'
        m_str = re.search(r'\btitle\s*=\s*(["\'])(.*?)\1', attrs)
        if m_str:
            val = m_str.group(2).strip()
            if val and _is_valid_propagated_title(val):
                return val

        # 2. title={'문자열'} 또는 title={"문자열"}
        m_brace_str = re.search(r'\btitle\s*=\s*\{\s*(["\'])(.*?)\1\s*\}', attrs)
        if m_brace_str:
            val = m_brace_str.group(2).strip()
            if val and _is_valid_propagated_title(val):
                return val

        # 3. title={...} 표현식 (변수, JSX, 템플릿 등)
        if re.search(r'\btitle\s*=', attrs):
            return True

    # 모달 태그가 있었지만 title 속성이 없거나 상수가 아닌 경우
    if has_modal_tag:
        return True

    return ""


def _find_component_record(
    comp_name: str,
    by_name: dict[str, ScreenRecord],
    layout: TobeLayout,
    current_file: Path | None = None,
) -> ScreenRecord | None:
    """카탈로그 또는 디스크에서 컴포넌트의 ScreenRecord를 찾는다."""
    if comp_name in by_name:
        return by_name[comp_name]
    candidates: list[Path] = []
    if current_file:
        candidates.append(current_file.parent / f"{comp_name}.tsx")
    if layout.frontend.is_dir():
        candidates.append(layout.frontend / "components" / "lookup" / f"{comp_name}.tsx")
        candidates.extend(layout.frontend.rglob(f"{comp_name}.tsx"))
    for cand in candidates:
        if cand.is_file():
            try:
                rel = str(cand.relative_to(layout.root))
            except ValueError:
                rel = str(cand)
            rec = ScreenRecord(
                name=comp_name,
                side="tobe",
                file=rel,
                text=cand.read_text(encoding="utf-8", errors="replace"),
                root_dir=str(layout.root),
            )
            by_name[comp_name] = rec
            return rec
    return None


def _build_modal_trigger_map(
    raw_text: str,
    clean_text: str,
    by_name: dict[str, ScreenRecord],
    layout: TobeLayout,
    current_file: Path | None,
) -> tuple[dict[str, str], dict[str, str]]:
    """컴포넌트 내 state setter 및 로컬 함수가 여는 모달 타이틀 매핑을 구축한다.

    반환: (setter_or_state_to_modal_title, local_fn_bodies)
    """
    state_pairs: list[tuple[str, str]] = []
    for m in re.finditer(r"\bconst\s+\[\s*(\w+)\s*,\s*(\w+)\s*\]\s*=\s*useState\b", clean_text):
        state_pairs.append((m.group(1), m.group(2)))

    # import된 심볼 및 동일 파일 내 모달 후보 수집
    imported_names: list[str] = []
    for m in _IMPORT_RE.finditer(raw_text):
        stem = Path(m.group(2)).stem
        if stem not in imported_names:
            imported_names.append(stem)

    setter_to_title: dict[str, str | bool] = {}

    # JSX에 렌더링된 모달 컴포넌트 태그 `<ModalComp ... />` 탐색
    for m in re.finditer(r"<([A-Z][A-Za-z0-9_]*)\b", clean_text):
        tag_name = m.group(1)
        if tag_name in _PRIMITIVE_COMPONENTS and tag_name not in ("PDFViewer", "Sys95_PDFViewer", "RdViewer", "LookupModal", "EditModal", "Modal"):
            continue
        t_end, _ = _find_tag_end(clean_text, m.start())
        attrs = clean_text[m.start() : t_end]

        modal_title: str | bool = ""
        if tag_name in ("PDFViewer", "Sys95_PDFViewer"):
            modal_title = "PDF Viewer"
        elif tag_name in ("LookupModal", "EditModal", "Modal"):
            m_str = re.search(r'\btitle\s*=\s*(["\'])(.*?)\1', attrs)
            if m_str:
                modal_title = m_str.group(2).strip()
            elif re.search(r'\btitle\s*=\s*\{\s*(["\'])(.*?)\1\s*\}', attrs):
                m_b = re.search(r'\btitle\s*=\s*\{\s*(["\'])(.*?)\1\s*\}', attrs)
                modal_title = m_b.group(2).strip() if m_b else True
            elif re.search(r'\btitle\s*=', attrs):
                modal_title = True
        else:
            rec = _find_component_record(tag_name, by_name, layout, current_file)
            if rec and _is_modal_component(rec, clean_text):
                modal_title = resolve_modal_title(rec, tag_name)

        if not modal_title:
            continue

        for st_var, setter_var in state_pairs:
            if re.search(rf"\b{re.escape(st_var)}\b", attrs) or re.search(rf"\b{re.escape(setter_var)}\b", attrs):
                setter_to_title.setdefault(setter_var, modal_title)
                setter_to_title.setdefault(st_var, modal_title)

    # 로컬 함수 정의 추출: `const fn = (...) => ...` 또는 `function fn(...) { ... }`
    local_fns: dict[str, str] = {}
    for m in re.finditer(
        r"\bconst\s+([a-zA-Z_]\w*)\s*=\s*(?:useCallback\s*\(\s*)?(?:async\s*)?(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>",
        clean_text,
    ):
        fn_name = m.group(1)
        rhs_start = m.end()
        while rhs_start < len(clean_text) and clean_text[rhs_start].isspace():
            rhs_start += 1
        if rhs_start < len(clean_text) and clean_text[rhs_start] == "{":
            # 중괄호 블록 추출
            depth = 1
            i = rhs_start + 1
            while i < len(clean_text) and depth > 0:
                if clean_text[i] == "{":
                    depth += 1
                elif clean_text[i] == "}":
                    depth -= 1
                i += 1
            local_fns[fn_name] = clean_text[rhs_start:i]
        else:
            end_line = clean_text.find("\n", rhs_start)
            local_fns[fn_name] = clean_text[rhs_start : end_line if end_line != -1 else rhs_start + 200]

    return setter_to_title, local_fns


def _resolve_handler_modal(
    handler_expr: str | None,
    setter_to_title: dict[str, str | bool],
    local_fns: dict[str, str],
) -> str | bool:
    """핸들러 표현식에서 호출하는 state setter 또는 로컬 함수를 최대 3단계 추적해 기대 모달 타이틀을 반환한다."""
    if not handler_expr:
        return ""

    visited: set[str] = set()
    queue: list[str] = [handler_expr]
    for _ in range(4):
        next_queue: list[str] = []
        for snippet in queue:
            for setter_name, title in setter_to_title.items():
                if not setter_name.startswith("set"):
                    continue
                # setXxx(false) 나 setXxx(null) 호출만 있는 경우는 닫기 동작이므로 제외
                for call_m in re.finditer(rf"\b{re.escape(setter_name)}\s*\(\s*([^)]*)\)", snippet):
                    arg = call_m.group(1).strip()
                    if arg not in ("false", "null", "undefined", "''", '""'):
                        return title
                # onOpen={setFundOpen} 처럼 직접 참조하는 경우
                if re.fullmatch(rf"\s*{re.escape(setter_name)}\s*", snippet):
                    return title

            for ident in re.findall(r"\b([a-zA-Z_]\w*)\b", snippet):
                if ident in local_fns and ident not in visited:
                    visited.add(ident)
                    next_queue.append(local_fns[ident])
        queue = next_queue
        if not queue:
            break
    return ""


def _handler_may_warn(handler_code: str | None, local_fns: dict[str, str]) -> bool:
    """핸들러(인라인 화살표 함수, 또는 같은 파일의 함수) 안에 `message.warning|info`나 `Modal.warning|info`가 있는지 검사한다.

    072: `message.error`·`Modal.error`는 넣지 않는다 — 실행기가 mayWarn을 "메시지가 떠도 통과"로 보므로,
    error까지 넣으면 실제 실패(조회 실패·다운로드 실패)가 PASS로 덮인다.
    """
    if not handler_code:
        return False
    warn_pat = re.compile(r"\b(?:message\.(?:warning|info)|Modal\.(?:warning|info))\b")
    if warn_pat.search(handler_code):
        return True
    visited: set[str] = set()
    queue = [handler_code]
    for _ in range(3):
        next_queue: list[str] = []
        for snippet in queue:
            for ident in re.findall(r"\b([a-zA-Z_]\w*)\b", snippet):
                if ident in local_fns and ident not in visited:
                    visited.add(ident)
                    fn_body = local_fns[ident]
                    if warn_pat.search(fn_body):
                        return True
                    next_queue.append(fn_body)
        queue = next_queue
        if not queue:
            break
    return False


_INPUT_CONTAINER_TAGS = {"SearchBar", "SearchPanel", "Space", "Toolbar", "Form", "Card", "Panel"}
_INPUT_CONTROL_TAGS_PAT = re.compile(
    r"<(Select|SystemCodeComboBox|LookupInput|CompanyPopupField|QuickMoveField|QuickMoveDateField|DatePicker\.RangePicker|RangePicker|DatePicker|SearchBar\.Input|SearchPanel\.Input|Input|Checkbox|Radio\.Group)\b"
)
_FIELD_CONTAINER_PAT = re.compile(
    r"<(SearchBar\.Field|SearchPanel\.Field|EditField|Form\.Item)\b"
)


_PRECEDING_TEXT_LABEL_PAT = re.compile(
    r"<(Typography\.Text|Text|span|label|b|strong)\b[^<>]*>\s*([^<>{}]+?)\s*</\1>(?:\s|\{\s*\})*$"
)


def _preceding_text_label(jsx_text: str, rel_start: int) -> str | None:
    """컨트롤 바로 앞에 화면에 보이는 글자 태그(`<Typography.Text>적용상품</Typography.Text>` 등)가 있으면 그 글자를 label로 쓴다.

    072: 주석이 아니라 실제로 화면에 그려지는 글자다. 사이에는 공백과 주석 자리(`{ }`, 주석 제거 뒤 남는 빈 중괄호)만 허용한다.
    """
    head = jsx_text[max(0, rel_start - 400):rel_start]
    m = _PRECEDING_TEXT_LABEL_PAT.search(head)
    if not m:
        return None
    lbl = re.sub(r"\s+", " ", m.group(2)).strip().rstrip(":：").strip()
    return lbl or None


def _compute_control_index_in_container(container_inner_jsx: str, target_rel_offset: int) -> int:
    """컨테이너 내부에서 `target_rel_offset` 이전까지의 탑레벨 입력 요소 개수(0부터 시작하는 index)를 센다.

    세는 규칙(실행기와의 계약 — .gen.cjs 머리 주석과 docs/help에도 적는다):
    - Field 계열(`SearchBar.Field`·`SearchPanel.Field`·`EditField`·`Form.Item`) 하나 = 1칸(안에 DatePicker 두 개가 있어도 1칸)
    - Field 밖에 직접 놓인 입력 요소(`_INPUT_CONTROL_TAGS_PAT`) 하나 = 1칸
    - 버튼·글자·그 밖의 태그는 세지 않는다
    """
    idx = 0
    pos = 0
    limit = min(target_rel_offset, len(container_inner_jsx))
    while pos < limit:
        m_field = _FIELD_CONTAINER_PAT.search(container_inner_jsx, pos)
        m_input = _INPUT_CONTROL_TAGS_PAT.search(container_inner_jsx, pos)

        if not m_field and not m_input:
            break

        if m_field and m_input:
            use_field = m_field.start() < m_input.start()
        elif m_field:
            use_field = True
        else:
            use_field = False

        if use_field:
            assert m_field is not None
            f_start = m_field.start()
            if f_start >= limit:
                break
            idx += 1
            f_tag = m_field.group(1)
            t_end, self_closing = _find_tag_end(container_inner_jsx, f_start)
            if self_closing:
                pos = t_end
            else:
                c_pos = _find_matching_close_tag(container_inner_jsx, f_tag, t_end)
                pos = (c_pos + len(f_tag) + 3) if c_pos != -1 else t_end
        else:
            assert m_input is not None
            i_start = m_input.start()
            if i_start >= limit:
                break
            idx += 1
            i_tag = m_input.group(1)
            t_end, self_closing = _find_tag_end(container_inner_jsx, i_start)
            if self_closing:
                pos = t_end
            else:
                c_pos = _find_matching_close_tag(container_inner_jsx, i_tag, t_end)
                pos = (c_pos + len(i_tag) + 3) if c_pos != -1 else t_end

    return idx


def _find_enclosing_container(
    jsx_text: str,
    rel_start: int,
    search_containers: list[tuple[int, int, str]],
) -> tuple[str, int] | None:
    """`rel_start` 위치를 감싸는 컨테이너 태그 이름과 컨테이너 내 0-based 입력 요소 index를 반환한다."""
    # 1. SearchBar / SearchPanel 내부인지 먼저 확인
    for s, e, tag in search_containers:
        if s <= rel_start <= e:
            t_end, _ = _find_tag_end(jsx_text, s)
            inner_jsx = jsx_text[t_end:e]
            offset = max(0, rel_start - t_end)
            idx = _compute_control_index_in_container(inner_jsx, offset)
            return tag, idx

    # 2. JSX 앞부분에서 아직 닫히지 않은 가장 가까운 지원 컨테이너 탐색 (예: Space, Toolbar)
    best_candidate: tuple[str, int, int] | None = None
    for m in re.finditer(r"<([A-Z][A-Za-z0-9_.]*)\b", jsx_text[:rel_start]):
        c_tag = m.group(1)
        if c_tag not in _INPUT_CONTAINER_TAGS:
            continue
        c_start = m.start()
        t_end, self_closing = _find_tag_end(jsx_text, c_start)
        if self_closing:
            continue
        c_pos = _find_matching_close_tag(jsx_text, c_tag, t_end)
        if c_pos != -1 and c_pos > rel_start and (best_candidate is None or c_start > best_candidate[1]):
            best_candidate = (c_tag, c_start, c_pos)

    if best_candidate:
        c_tag, c_start, c_pos = best_candidate
        t_end, _ = _find_tag_end(jsx_text, c_start)
        inner_jsx = jsx_text[t_end:c_pos]
        offset = max(0, rel_start - t_end)
        idx = _compute_control_index_in_container(inner_jsx, offset)
        return c_tag, idx

    return None


def _extract_tabs_list(raw_text: str, clean_text: str, tabs_attrs: str) -> list[str]:
    """`<PageTabs items={...}>` 또는 `<Tabs items={...}>`에서 탭 라벨 목록을 추출한다."""
    items_expr = _extract_brace_attr(tabs_attrs, "items")
    if not items_expr:
        return []
    # 1. items 표현식 자체에 `{ key: ..., label: '...' }` 리터럴이 있는 경우
    direct = [m.group(2).strip() for m in re.finditer(r"\blabel\s*:\s*(['\"])(.*?)\1", items_expr) if m.group(2).strip()]
    if direct:
        return list(dict.fromkeys(direct))

    # 2. `TABS.map(...)` 등 상수 배열을 참조하는 경우
    m_arr = re.match(r"^\s*([A-Za-z_]\w*)", items_expr)
    if m_arr:
        arr_name = m_arr.group(1)
        m_def = re.search(rf"\bconst\s+{re.escape(arr_name)}\b[^=]*=\s*\[([\s\S]*?)\]\s*(?:as\s+const)?\s*;", clean_text)
        if m_def:
            arr_body = m_def.group(1)
            labels = [m.group(2).strip() for m in re.finditer(r"\blabel\s*:\s*(['\"])(.*?)\1", arr_body) if m.group(2).strip()]
            if labels:
                return list(dict.fromkeys(labels))
    return []


def _find_main_return_span(clean_text: str) -> tuple[int, int]:
    """컴포넌트의 메인 JSX 반환 영역 `(start, end)`를 반환한다.

    파일 상단의 보조 컴포넌트(`const Cell = ...`, `const Row = ...`) 내부 `<Input>`이
    중복 추출되지 않도록 `export const ...` 이후의 마지막 `return (` 또는 화살표 반환 본문을 찾는다.
    """
    m_exp = re.search(r"\bexport\s+(?:const|function)\s+[A-Z]\w*", clean_text)
    search_from = m_exp.start() if m_exp else 0
    sub = clean_text[search_from:]
    returns = list(re.finditer(r"\breturn\s*\(", sub))
    if returns:
        last_ret = returns[-1]
        return search_from + last_ret.start(), len(clean_text)
    return search_from, len(clean_text)


def _extract_helper_input_kinds(clean_text: str, jsx_start: int) -> dict[str, str]:
    """컴포넌트 본문 내 `const text = (key) => <Input ... />`, `const date = (key) => <DatePicker ... />` 헬퍼를 감지한다."""
    helpers: dict[str, str] = {}
    body = clean_text[:jsx_start]
    for m in re.finditer(
        r"\bconst\s+([a-zA-Z_]\w*)\s*=\s*\([^)]*\)\s*=>\s*\(?([\s\S]{1,300}?)(?:\)\s*;|\n\s*\n)",
        body,
    ):
        fn_name = m.group(1)
        snippet = m.group(2)
        if "<DatePicker.RangePicker" in snippet or "<RangePicker" in snippet:
            helpers[fn_name] = "dateRange"
        elif "<DatePicker" in snippet:
            helpers[fn_name] = "date"
        elif "<InputNumber" in snippet:
            helpers[fn_name] = "number"
        elif "<Input" in snippet and not _has_bool_attr(snippet, "readOnly"):
            helpers[fn_name] = "text"
    return helpers


def _extract_grid_cell_icons(
    raw_text: str,
    clean_text: str,
    grid_idx: int,
    grid_tag_name: str,
    grid_attrs: str,
    src_file: str,
    setter_to_title: dict[str, str | bool],
    local_fns: dict[str, str],
    rules: ScreenTestRules,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """그리드에 연결된 `columnDefs`와 `ModalEditGrid` 속성에서 `cellIcon` 단계들을 추출한다."""
    steps: list[dict[str, Any]] = []
    unknowns: list[dict[str, str]] = []

    col_def_name = _extract_brace_attr(grid_attrs, "columnDefs") or "columnDefs"
    # columnDefs 정의 영역 찾기 (단일 그리드면 파일 전체, 복수면 해당 변수 블록)
    col_block = clean_text
    col_block_offset = 0
    if re.fullmatch(r"[A-Za-z_]\w*", col_def_name):
        m_col = re.search(rf"\bconst\s+{re.escape(col_def_name)}\b[\s\S]*?\]\s*(?:,\s*\[[^\]]*\]\s*\))?\s*;", clean_text)
        if m_col:
            col_block = m_col.group(0)
            col_block_offset = m_col.start()

    # 직전 일반 컬럼 헤더 추적 (iconCell 제목이 빈칸 ' '인 경우 보조용)
    col_headers_by_pos: list[tuple[int, str]] = []
    for m_gb in re.finditer(r"\bgb\.\w+\(\s*[^,]+,\s*[^,]+,\s*(['\"])(.*?)\1", col_block):
        hdr = re.sub(r"<br\s*/?>", " ", m_gb.group(2)).strip()
        if hdr:
            col_headers_by_pos.append((m_gb.start(), hdr))

    # 1. iconCell / dynamicIconCell 호출 추출
    icon_pat = re.compile(
        r"\b(iconCell|dynamicIconCell)\s*(?:<[^>]*>)?\s*\(\s*(['\"])(\w+)\2\s*,\s*(['\"])([^'\"]*)\4\s*,\s*([^,]+)\s*,\s*(['\"])(.*?)\7\s*,\s*"
    )
    for m in icon_pat.finditer(col_block):
        kind = m.group(3).strip()
        col_id = m.group(5).strip()
        raw_header = re.sub(r"<br\s*/?>", " ", m.group(8)).strip()
        abs_pos = col_block_offset + m.start()
        line = _line_of(raw_text, abs_pos)
        src_ref = f"{src_file}:{line}"

        # 핸들러 표현식 추출 (괄호 균형)
        h_start = m.end()
        i = h_start
        depth = 1
        in_str: str | None = None
        while i < len(col_block) and depth > 0:
            ch = col_block[i]
            if in_str:
                if ch == "\\":
                    i += 2
                    continue
                if ch == in_str:
                    in_str = None
            else:
                if ch in ('"', "'", "`"):
                    in_str = ch
                elif ch == "(":
                    depth += 1
                elif ch == ")":
                    depth -= 1
            i += 1
        handler_code = col_block[h_start : max(h_start, i - 1)]

        col_label = raw_header
        if not col_label:
            # 직전 컬럼 헤더 탐색 (예: Est03_TabPage_PfHistoryList의 '증빙자료' 다음 빈 제목 아이콘 열)
            prev_hdrs = [h for p, h in col_headers_by_pos if p < m.start()]
            col_label = prev_hdrs[-1] if prev_hdrs else (col_id or kind)

        expect_modal = _resolve_handler_modal(handler_code, setter_to_title, local_fns)
        is_danger = kind in rules.icon_danger_kinds
        # 핸들러가 openMenuByNo(다른 메뉴 탭 이동)나 다운로드 등을 호출하는지 확인
        calls_non_modal = bool(re.search(r"\b(?:openMenuByNo|rdDownload|download)\b", handler_code))
        if not calls_non_modal:
            for ident in re.findall(r"\b([a-zA-Z_]\w*)\b", handler_code):
                if ident in local_fns and re.search(r"\b(?:openMenuByNo|rdDownload|download)\b", local_fns[ident]):
                    calls_non_modal = True
                    break

        step: dict[str, Any] = {
            "do": "cellIcon",
            "grid": grid_idx,
            "col": col_label,
        }
        if expect_modal:
            step["expectModal"] = expect_modal
            if expect_modal is True:
                unknowns.append({"src": src_ref, "reason": "모달 제목이 동적 — expectModal:true"})
        elif not is_danger and kind != "down" and not calls_non_modal:
            unknowns.append({"src": src_ref, "reason": f"cellIcon '{col_label}' expectModal 미상"})

        if _handler_may_warn(handler_code, local_fns):
            step["mayWarn"] = True

        if is_danger:
            step["danger"] = True
            step["enabled"] = False
        step["src"] = src_ref
        steps.append(step)

    # 2. ColDef 직접 정의에서 onCellClicked 액션 열 추출 (예: Apr31_Page_ApprStepGroupMember의 위로/아래로)
    for m_cd in re.finditer(r"\bheaderName\s*:\s*(['\"])(.*?)\1[^\n]*?\bonCellClicked\s*:\s*([^\n]+)", col_block):
        hdr = m_cd.group(2).strip()
        handler_code = m_cd.group(3).strip()
        abs_pos = col_block_offset + m_cd.start()
        line = _line_of(raw_text, abs_pos)
        src_ref = f"{src_file}:{line}"
        expect_modal = _resolve_handler_modal(handler_code, setter_to_title, local_fns)
        step = {
            "do": "cellIcon",
            "grid": grid_idx,
            "col": hdr,
        }
        if expect_modal:
            step["expectModal"] = expect_modal
            if expect_modal is True:
                unknowns.append({"src": src_ref, "reason": "모달 제목이 동적 — expectModal:true"})
        else:
            step["danger"] = True
            step["enabled"] = False
        if _handler_may_warn(handler_code, local_fns):
            step["mayWarn"] = True
        step["src"] = src_ref
        steps.append(step)

    # 3. ModalEditGrid의 editButton 속성
    if grid_tag_name == "ModalEditGrid" and re.search(r"\beditButton\b", grid_attrs):
        eb_str = _extract_str_attr(grid_attrs, "editButton")
        eb_brace = _extract_brace_attr(grid_attrs, "editButton")
        if eb_brace == "false":
            pass
        else:
            col_label = eb_str if eb_str else "수정"
            on_edit_expr = _extract_brace_attr(grid_attrs, "onEdit")
            expect_modal = _resolve_handler_modal(on_edit_expr, setter_to_title, local_fns)
            line = _line_of(raw_text, _get_attr_offset(clean_text, grid_attrs))
            src_ref = f"{src_file}:{line}"
            step = {
                "do": "cellIcon",
                "grid": grid_idx,
                "col": col_label,
                "via": "ModalEditGrid",
            }
            if expect_modal:
                step["expectModal"] = expect_modal
                if expect_modal is True:
                    unknowns.append({"src": src_ref, "reason": "모달 제목이 동적 — expectModal:true"})
            else:
                unknowns.append({"src": src_ref, "reason": f"ModalEditGrid '{col_label}' expectModal 미상"})
            if _handler_may_warn(on_edit_expr, local_fns):
                step["mayWarn"] = True
            step["src"] = src_ref
            steps.append(step)

    return steps, unknowns


def _get_attr_offset(clean_text: str, sub: str) -> int:
    idx = clean_text.find(sub)
    return max(idx, 0)


def _extract_controls_from_region(
    region_text: str,
    region_offset: int,
    raw_text: str,
    clean_text: str,
    jsx_start: int,
    src_file: str,
    field_label: str | None,
    search_step_id: str | None,
    setter_to_title: dict[str, str | bool],
    local_fns: dict[str, str],
    helper_kinds: dict[str, str],
    position_fallback: tuple[str, int] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """특정 JSX 영역(Field 내부 또는 독립 컨트롤)에서 lookup / selectEach / fill 단계를 추출한다."""
    steps: list[dict[str, Any]] = []
    unknowns: list[dict[str, str]] = []

    # 1. CompanyPopupField (공통 고객사 조회창 트리거)
    for m in re.finditer(r"<CompanyPopupField\b", region_text):
        abs_pos = region_offset + m.start()
        line = _line_of(raw_text, abs_pos)
        lbl = field_label or "고객사"
        step: dict[str, Any] = {
            "do": "lookup",
            "label": lbl,
            "expectModal": "고객사 찾기",
            "via": "CompanyPopupField",
            "src": f"{src_file}:{line}",
        }
        if _is_conditional_at(clean_text, abs_pos, jsx_start):
            step["conditional"] = True
        steps.append(step)
        return steps, unknowns

    # 2. LookupInput (공통 돋보기 입력칸)
    for m in re.finditer(r"<LookupInput\b", region_text):
        abs_pos = region_offset + m.start()
        t_end, _ = _find_tag_end(region_text, m.start())
        attrs = region_text[m.start() : t_end]
        if _has_bool_attr(attrs, "disabled"):
            continue
        line = _line_of(raw_text, abs_pos)
        src_ref = f"{src_file}:{line}"
        on_open = _extract_brace_attr(attrs, "onOpen")
        expect_modal = _resolve_handler_modal(on_open, setter_to_title, local_fns)
        ph = _extract_str_attr(attrs, "placeholder")
        modal_name = expect_modal if isinstance(expect_modal, str) else ""
        lbl = (field_label if field_label and field_label != "검색" else None) or ph or field_label or modal_name or ""
        if not lbl:
            unknowns.append({"src": src_ref, "reason": "LookupInput label 미상"})
            continue
        step = {
            "do": "lookup",
            "label": lbl,
        }
        if expect_modal:
            step["expectModal"] = expect_modal
            if expect_modal is True:
                unknowns.append({"src": src_ref, "reason": "모달 제목이 동적 — expectModal:true"})
        else:
            unknowns.append({"src": src_ref, "reason": f"LookupInput '{lbl}' expectModal 미상"})
        if _handler_may_warn(on_open, local_fns):
            step["mayWarn"] = True
        step["via"] = "LookupInput"
        if _is_conditional_at(clean_text, abs_pos, jsx_start):
            step["conditional"] = True
        step["src"] = src_ref
        steps.append(step)
        return steps, unknowns

    # 3. Select / SystemCodeComboBox / QuickMoveField (콤보박스 -> selectEach)
    for m in re.finditer(r"<(Select|SystemCodeComboBox|QuickMoveField)\b", region_text):
        tag_name = m.group(1)
        abs_pos = region_offset + m.start()
        t_end, _ = _find_tag_end(region_text, m.start())
        attrs = region_text[m.start() : t_end]
        if _has_bool_attr(attrs, "disabled"):
            continue
        line = _line_of(raw_text, abs_pos)
        src_ref = f"{src_file}:{line}"
        ph = (
            _extract_str_attr(attrs, "placeholder")
            or _extract_str_attr(attrs, "aria-label")
            or _extract_str_attr(attrs, "title")
        )
        lbl = field_label or ph or ""
        if not lbl and tag_name == "QuickMoveField":
            lbl = "기준년월"
        if not lbl and position_fallback:
            container_tag, ctrl_idx = position_fallback
            pos_step: dict[str, Any] = {
                "base_id": f"selectEach:#{ctrl_idx}",
                "do": "selectEach",
                "in": container_tag,
                "index": ctrl_idx,
            }
            if search_step_id:
                pos_step["then"] = search_step_id
            if tag_name == "QuickMoveField":
                pos_step["via"] = "QuickMoveField"
            if _is_conditional_at(clean_text, abs_pos, jsx_start):
                pos_step["conditional"] = True
            pos_step["src"] = src_ref
            steps.append(pos_step)
            unknowns.append({"src": src_ref, "reason": "label 없음 — 위치로 대신"})
            return steps, unknowns
        if not lbl:
            unknowns.append({"src": src_ref, "reason": f"{tag_name} label 미상"})
            continue
        step = {
            "do": "selectEach",
            "label": lbl,
        }
        if search_step_id:
            step["then"] = search_step_id
        if tag_name == "QuickMoveField":
            step["via"] = "QuickMoveField"
        if _is_conditional_at(clean_text, abs_pos, jsx_start):
            step["conditional"] = True
        step["src"] = src_ref
        steps.append(step)
        return steps, unknowns

    # 4. DatePicker / RangePicker / QuickMoveDateField (날짜 -> fill: date | dateRange)
    range_m = re.search(r"<(?:DatePicker\.RangePicker|RangePicker)\b", region_text)
    date_matches = list(re.finditer(r"<(DatePicker|QuickMoveDateField)\b", region_text))
    if range_m or date_matches:
        first_m = range_m or date_matches[0]
        abs_pos = region_offset + first_m.start()
        t_end, _ = _find_tag_end(region_text, first_m.start())
        attrs = region_text[first_m.start() : t_end]
        if _has_bool_attr(attrs, "disabled"):
            return steps, unknowns
        line = _line_of(raw_text, abs_pos)
        src_ref = f"{src_file}:{line}"
        kind = "dateRange" if (range_m or len(date_matches) >= 2) else "date"
        ph = _extract_str_attr(attrs, "placeholder")
        lbl = field_label or ph or ("일자" if "QuickMoveDateField" in first_m.group(0) else "")
        if not lbl:
            unknowns.append({"src": src_ref, "reason": f"DatePicker({kind}) label 미상"})
            return steps, unknowns
        step = {
            "do": "fill",
            "label": lbl,
            "kind": kind,
        }
        if search_step_id:
            step["then"] = search_step_id
        if "QuickMoveDateField" in first_m.group(0):
            step["via"] = "QuickMoveDateField"
        if _is_conditional_at(clean_text, abs_pos, jsx_start):
            step["conditional"] = True
        step["src"] = src_ref
        steps.append(step)
        return steps, unknowns

    # 5. InputNumber (숫자 입력 -> fill: number)
    num_m = re.search(r"<InputNumber\b", region_text)
    if num_m:
        abs_pos = region_offset + num_m.start()
        t_end, _ = _find_tag_end(region_text, num_m.start())
        attrs = region_text[num_m.start() : t_end]
        if _has_bool_attr(attrs, "disabled") or _has_bool_attr(attrs, "readOnly"):
            return steps, unknowns
        line = _line_of(raw_text, abs_pos)
        src_ref = f"{src_file}:{line}"
        ph = _extract_str_attr(attrs, "placeholder")
        lbl = field_label or ph or ""
        if not lbl:
            unknowns.append({"src": src_ref, "reason": "InputNumber label 미상"})
            return steps, unknowns
        step = {
            "do": "fill",
            "label": lbl,
            "kind": "number",
        }
        if search_step_id:
            step["then"] = search_step_id
        if _is_conditional_at(clean_text, abs_pos, jsx_start):
            step["conditional"] = True
        step["src"] = src_ref
        steps.append(step)
        return steps, unknowns

    # 6. SearchBar.Input / SearchPanel.Input / Input / Input.TextArea
    inp_m = re.search(r"<(SearchBar\.Input|SearchPanel\.Input|Input\.TextArea|Input)\b", region_text)
    if inp_m:
        tag_name = inp_m.group(1)
        abs_pos = region_offset + inp_m.start()
        t_end, _ = _find_tag_end(region_text, inp_m.start())
        attrs = region_text[inp_m.start() : t_end]
        line = _line_of(raw_text, abs_pos)
        src_ref = f"{src_file}:{line}"

        # suffix 또는 addonAfter에 <SearchOutlined onClick={...} /> 가 붙은 경우 lookup 단계 추가
        for trig_prop in ("suffix", "addonAfter"):
            trig_expr = _extract_brace_attr(attrs, trig_prop)
            if trig_expr and "SearchOutlined" in trig_expr and "onClick" in trig_expr:
                clk_expr = _extract_brace_attr(trig_expr, "onClick") or trig_expr
                expect_modal = _resolve_handler_modal(clk_expr, setter_to_title, local_fns)
                aria = _extract_str_attr(trig_expr, "aria-label")
                modal_name = expect_modal if isinstance(expect_modal, str) else ""
                l_lbl = field_label or aria or modal_name or ""
                if l_lbl:
                    l_step: dict[str, Any] = {
                        "do": "lookup",
                        "label": l_lbl,
                    }
                    if expect_modal:
                        l_step["expectModal"] = expect_modal
                        if expect_modal is True:
                            unknowns.append({"src": src_ref, "reason": "모달 제목이 동적 — expectModal:true"})
                    else:
                        unknowns.append({"src": src_ref, "reason": f"SearchOutlined '{l_lbl}' expectModal 미상"})
                    if _handler_may_warn(clk_expr, local_fns):
                        l_step["mayWarn"] = True
                    if _is_conditional_at(clean_text, abs_pos, jsx_start):
                        l_step["conditional"] = True
                    l_step["src"] = src_ref
                    steps.append(l_step)

        if _has_bool_attr(attrs, "disabled") or _has_bool_attr(attrs, "readOnly"):
            return steps, unknowns

        ph = _extract_str_attr(attrs, "placeholder")
        # 9.1절 규칙: SearchBar.Input은 placeholder가 있으면 그것을 label로 쓴다 (예: fill:제목)
        is_generic_ph = bool(ph and ph in ("선택하여 주세요", "검색어를 입력하세요", "입력하세요"))
        if tag_name in ("SearchBar.Input", "SearchPanel.Input") and ph and not is_generic_ph:
            lbl = ph
        elif field_label and field_label != "검색":
            lbl = field_label
        else:
            lbl = (ph if not is_generic_ph else None) or field_label or ph or ""

        if not lbl:
            unknowns.append({"src": src_ref, "reason": f"{tag_name} label/placeholder 미상"})
            return steps, unknowns

        step = {
            "do": "fill",
            "label": lbl,
            "kind": "text",
        }
        if search_step_id:
            step["then"] = search_step_id
        if _is_conditional_at(clean_text, abs_pos, jsx_start):
            step["conditional"] = True
        step["src"] = src_ref
        steps.append(step)
        return steps, unknowns

    # 7. 로컬 헬퍼 함수 호출 (예: Adv02_Edit_Account의 `<Cell label="관리코드">{text('manageCode')}</Cell>`)
    if field_label and helper_kinds:
        for h_name, h_kind in helper_kinds.items():
            m_call = re.search(rf"\{{\s*{re.escape(h_name)}\s*\(", region_text)
            if m_call:
                abs_pos = region_offset + m_call.start()
                line = _line_of(raw_text, abs_pos)
                step = {
                    "do": "fill",
                    "label": field_label,
                    "kind": h_kind,
                    "src": f"{src_file}:{line}",
                }
                if search_step_id:
                    step["then"] = search_step_id
                steps.append(step)
                return steps, unknowns

    return steps, unknowns


def _extract_component_steps(
    comp_rec: ScreenRecord,
    scope_name: str,
    grid_counter: list[int],
    by_name: dict[str, ScreenRecord],
    layout: TobeLayout,
    rules: ScreenTestRules,
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[tuple[ScreenRecord, str]]]:
    """단일 컴포넌트(메인 Tab 또는 인라인 하위 Page/TabPage/Grid/Edit)의 단계 목록과 하위 인라인 컴포넌트들을 추출한다."""
    raw_text = comp_rec.text
    clean_text = _strip_comments_preserve_newlines(raw_text)
    src_file = Path(comp_rec.file).name if comp_rec.file else f"{comp_rec.name}.tsx"
    current_path = (layout.root / comp_rec.file) if comp_rec.file else None

    jsx_start, jsx_end = _find_main_return_span(clean_text)
    jsx_text = clean_text[jsx_start:jsx_end]

    setter_to_title, local_fns = _build_modal_trigger_map(
        raw_text, clean_text, by_name, layout, current_path
    )
    helper_kinds = _extract_helper_input_kinds(clean_text, jsx_start)

    search_steps: list[dict[str, Any]] = []
    reset_steps: list[dict[str, Any]] = []
    input_steps: list[dict[str, Any]] = []
    tab_steps: list[dict[str, Any]] = []
    grid_steps: list[dict[str, Any]] = []
    button_steps: list[dict[str, Any]] = []
    unknowns: list[dict[str, str]] = []

    search_step_id: str | None = None
    consumed_button_spans: list[tuple[int, int]] = []

    # 1. SearchBar / SearchPanel 조회 버튼(및 초기화 버튼) 추출 (9.1절)
    for m_sb in re.finditer(r"<(SearchBar|SearchPanel)\b", jsx_text):
        sb_tag = m_sb.group(1)
        rel_start = m_sb.start()
        abs_start = jsx_start + rel_start
        t_end, self_closing = _find_tag_end(jsx_text, rel_start)
        attrs = jsx_text[rel_start:t_end]
        if not re.search(r"\bonSearch\s*=", attrs):
            continue
        btn_label = _extract_str_attr(attrs, "searchText") or "조회"
        line = _line_of(raw_text, abs_start)
        s_id = f"{scope_name}/click:{btn_label}"
        if search_step_id is None:
            search_step_id = s_id
        search_steps.append(
            {
                "base_id": s_id,
                "do": "click",
                "button": btn_label,
                "type": "search",
                "via": sb_tag,
                "src": f"{src_file}:{line}",
            }
        )
        # SearchBar의 onReset (조건 3개 이상일 때 초기화 버튼 자동 렌더링)
        if sb_tag == "SearchBar" and re.search(r"\bonReset\s*=", attrs) and not self_closing:
            close_pos = _find_matching_close_tag(jsx_text, sb_tag, t_end)
            inner_sb = jsx_text[t_end : close_pos if close_pos != -1 else len(jsx_text)]
            # extra={...} 내부는 children 개수에서 제외
            child_count = len(
                re.findall(
                    r"<(?:SearchBar\.Field|SearchField|Select|SystemCodeComboBox|DatePicker|Checkbox|Radio\.Group|LookupInput|CompanyPopupField)\b",
                    inner_sb,
                )
            )
            if child_count >= 3:
                reset_steps.append(
                    {
                        "base_id": f"{scope_name}/click:초기화",
                        "do": "click",
                        "button": "초기화",
                        "type": "reset",
                        "via": "SearchBar",
                        "src": f"{src_file}:{line}",
                    }
                )

    # 2. 만약 SearchBar/SearchPanel이 없고 `<Button type="search">`가 있는 경우 첫 조회 버튼을 먼저 확보
    if search_step_id is None:
        for m_btn in re.finditer(r"<Button\b", jsx_text):
            rel_start = m_btn.start()
            t_end, self_closing = _find_tag_end(jsx_text, rel_start)
            if self_closing:
                continue
            close_pos = jsx_text.find("</Button>", t_end)
            if close_pos == -1:
                continue
            attrs = jsx_text[rel_start:t_end]
            b_type = _extract_str_attr(attrs, "type")
            if b_type == "search":
                b_label = _clean_jsx_text(jsx_text[t_end:close_pos]) or _extract_str_attr(attrs, "title") or "조회"
                on_click_expr = _extract_brace_attr(attrs, "onClick")
                if b_label in ("조회", "검색", "찾기", "기간조회") and not _resolve_handler_modal(
                    on_click_expr, setter_to_title, local_fns
                ):
                    line = _line_of(raw_text, jsx_start + rel_start)
                    s_id = f"{scope_name}/click:{b_label}"
                    search_step_id = s_id
                    consumed_button_spans.append((rel_start, close_pos + len("</Button>")))
                    s_step: dict[str, Any] = {
                        "base_id": s_id,
                        "do": "click",
                        "button": b_label,
                        "type": "search",
                        "src": f"{src_file}:{line}",
                    }
                    if _is_conditional_at(clean_text, jsx_start + rel_start, jsx_start):
                        s_step["conditional"] = True
                    search_steps.append(s_step)
                    break

    # 3. SearchBar/SearchPanel 범위 파악 (then 연결 및 컨테이너 판단용)
    search_containers: list[tuple[int, int, str]] = []
    for m_sc in re.finditer(r"<(SearchBar|SearchPanel)\b", jsx_text):
        t_end, self_closing = _find_tag_end(jsx_text, m_sc.start())
        if not self_closing:
            c_pos = _find_matching_close_tag(jsx_text, m_sc.group(1), t_end)
            if c_pos != -1:
                search_containers.append((m_sc.start(), c_pos, m_sc.group(1)))

    def _in_search_container(rel_pos: int) -> bool:
        return any(s <= rel_pos <= e for s, e, _ in search_containers)

    # 4. Field 컨테이너(`<SearchBar.Field>`, `<SearchPanel.Field>`, `<EditField>`, `<Form.Item>`, `<Field>`, `<Cell>`, `<Row>`) 및 독립 입력 요소 스캔
    field_spans: list[tuple[int, int]] = []
    field_tag_pat = re.compile(
        r"<(SearchBar\.Field|SearchPanel\.Field|SearchField|EditField|Form\.Item|Field|Cell|Row)\b"
    )
    pos = 0
    while True:
        m_f = field_tag_pat.search(jsx_text, pos)
        if not m_f:
            break
        f_tag = m_f.group(1)
        f_start = m_f.start()
        t_end, self_closing = _find_tag_end(jsx_text, f_start)
        attrs = jsx_text[f_start:t_end]
        f_label = _extract_str_attr(attrs, "label")
        if self_closing or not f_label:
            pos = t_end
            continue
        c_pos = _find_matching_close_tag(jsx_text, f_tag, t_end)
        if c_pos == -1:
            pos = t_end
            continue
        f_end = c_pos + len(f_tag) + 3
        field_spans.append((f_start, f_end))

        then_id = search_step_id if _in_search_container(f_start) else None
        c_steps, c_unk = _extract_controls_from_region(
            region_text=jsx_text[t_end:c_pos],
            region_offset=jsx_start + t_end,
            raw_text=raw_text,
            clean_text=clean_text,
            jsx_start=jsx_start,
            src_file=src_file,
            field_label=f_label,
            search_step_id=then_id,
            setter_to_title=setter_to_title,
            local_fns=local_fns,
            helper_kinds=helper_kinds,
            position_fallback=None,
        )
        for st in c_steps:
            if "base_id" not in st:
                lbl_val = st.get("label", "")
                st["base_id"] = f"{scope_name}/{st['do']}:{lbl_val}"
            else:
                st["base_id"] = f"{scope_name}/{st['base_id']}"
            input_steps.append(st)
        unknowns.extend(c_unk)
        pos = f_end

    def _inside_field_span(rel_pos: int) -> bool:
        return any(s <= rel_pos < e for s, e in field_spans)

    # Field 컨테이너 밖에 직접 놓인 Select / SystemCodeComboBox / LookupInput / CompanyPopupField / QuickMoveField / QuickMoveDateField / SearchBar.Input
    standalone_pat = re.compile(
        r"<(CompanyPopupField|LookupInput|Select|SystemCodeComboBox|QuickMoveField|QuickMoveDateField|DatePicker\.RangePicker|RangePicker|SearchBar\.Input|SearchPanel\.Input)\b"
    )
    for m_st in standalone_pat.finditer(jsx_text):
        rel_start = m_st.start()
        if _inside_field_span(rel_start):
            continue
        t_end, _ = _find_tag_end(jsx_text, rel_start)
        attrs = jsx_text[rel_start:t_end]

        # 071: 이름은 JSX 속성(placeholder, aria-label, title)에서만 가져온다. 주석이나 이전 JSX 텍스트는 보지 않는다.
        direct_lbl = (
            _extract_str_attr(attrs, "placeholder")
            or _extract_str_attr(attrs, "aria-label")
            or _extract_str_attr(attrs, "title")
        )
        if not direct_lbl:
            direct_lbl = _preceding_text_label(jsx_text, rel_start)
        pos_fallback = None
        if not direct_lbl:
            pos_fallback = _find_enclosing_container(jsx_text, rel_start, search_containers)

        then_id = search_step_id if _in_search_container(rel_start) else None
        c_steps, c_unk = _extract_controls_from_region(
            region_text=jsx_text[rel_start:t_end],
            region_offset=jsx_start + rel_start,
            raw_text=raw_text,
            clean_text=clean_text,
            jsx_start=jsx_start,
            src_file=src_file,
            field_label=direct_lbl,
            search_step_id=then_id,
            setter_to_title=setter_to_title,
            local_fns=local_fns,
            helper_kinds={},
            position_fallback=pos_fallback,
        )
        for st in c_steps:
            if "base_id" not in st:
                lbl_val = st.get("label", "")
                st["base_id"] = f"{scope_name}/{st['do']}:{lbl_val}"
            else:
                st["base_id"] = f"{scope_name}/{st['base_id']}"
            input_steps.append(st)
        unknowns.extend(c_unk)

    # 5. PageTabs / Tabs (`tabEach`)
    for m_tab in re.finditer(r"<(PageTabs|Tabs)\b", jsx_text):
        rel_start = m_tab.start()
        t_end, _ = _find_tag_end(jsx_text, rel_start)
        attrs = jsx_text[rel_start:t_end]
        line = _line_of(raw_text, jsx_start + rel_start)
        tabs_list = _extract_tabs_list(raw_text, clean_text, attrs)
        t_step: dict[str, Any] = {
            "base_id": f"{scope_name}/tabEach",
            "do": "tabEach",
        }
        if tabs_list:
            t_step["tabs"] = tabs_list
        t_step["src"] = f"{src_file}:{line}"
        tab_steps.append(t_step)

    # 6. 그리드 (`rowClick` 및 `cellIcon`)
    for m_grid in re.finditer(r"<(SingleGrid|MultiGrid|CellEditGrid|ModalEditGrid|BaseGrid|TreeGrid)\b", jsx_text):
        g_tag = m_grid.group(1)
        rel_start = m_grid.start()
        t_end, _ = _find_tag_end(jsx_text, rel_start)
        attrs = jsx_text[rel_start:t_end]
        line = _line_of(raw_text, jsx_start + rel_start)
        g_idx = grid_counter[0]
        grid_counter[0] += 1

        grid_steps.append(
            {
                "base_id": f"{scope_name}/rowClick:{g_idx}",
                "do": "rowClick",
                "grid": g_idx,
                "row": 0,
                "src": f"{src_file}:{line}",
            }
        )
        ci_steps, ci_unk = _extract_grid_cell_icons(
            raw_text=raw_text,
            clean_text=clean_text,
            grid_idx=g_idx,
            grid_tag_name=g_tag,
            grid_attrs=attrs,
            src_file=src_file,
            setter_to_title=setter_to_title,
            local_fns=local_fns,
            rules=rules,
        )
        for ci in ci_steps:
            ci["base_id"] = f"{scope_name}/cellIcon:{g_idx}.{ci['col']}"
            grid_steps.append(ci)
        unknowns.extend(ci_unk)

    # 7. 공통 펼치기/접기 버튼 묶음 (`ExpandCollapseButtons` / `TreeListControlButtons`)
    for m_ec in re.finditer(r"<(ExpandCollapseButtons|TreeListControlButtons)\b", jsx_text):
        ec_tag = m_ec.group(1)
        rel_start = m_ec.start()
        t_end, _ = _find_tag_end(jsx_text, rel_start)
        attrs = jsx_text[rel_start:t_end]
        line = _line_of(raw_text, jsx_start + rel_start)
        exp_text = _extract_str_attr(attrs, "expandText") or "모두펼치기"
        col_text = _extract_str_attr(attrs, "collapseText") or "모두접기"
        for b_lbl, b_type in ((exp_text, "expand"), (col_text, "collapse")):
            button_steps.append(
                {
                    "base_id": f"{scope_name}/click:{b_lbl}",
                    "do": "click",
                    "button": b_lbl,
                    "type": b_type,
                    "via": ec_tag,
                    "src": f"{src_file}:{line}",
                }
            )

    # 8. 일반 `<Button ...>` 스캔
    for m_btn in re.finditer(r"<Button\b", jsx_text):
        rel_start = m_btn.start()
        if any(s <= rel_start < e for s, e in consumed_button_spans):
            continue
        abs_pos = jsx_start + rel_start
        t_end, self_closing = _find_tag_end(jsx_text, rel_start)
        attrs = jsx_text[rel_start:t_end]
        line = _line_of(raw_text, abs_pos)
        src_ref = f"{src_file}:{line}"

        inner_text = ""
        if not self_closing:
            close_pos = jsx_text.find("</Button>", t_end)
            if close_pos != -1:
                inner_text = _clean_jsx_text(jsx_text[t_end:close_pos])

        raw_type = _extract_str_attr(attrs, "type")
        fallback_lbl = (
            _extract_str_attr(attrs, "title")
            or _extract_str_attr(attrs, "aria-label")
            or _extract_str_attr(attrs, "label")
        )
        if not inner_text and not fallback_lbl:
            if raw_type == "plus":
                fallback_lbl = "+"
            elif raw_type == "minus":
                fallback_lbl = "-"
            elif raw_type == "shortcut":
                fallback_lbl = "바로가기"

        b_label = inner_text or fallback_lbl or ""
        if not b_label:
            unknowns.append({"src": src_ref, "reason": "버튼 글자·라벨 없음"})
            continue

        is_known = rules.is_known_button_type(raw_type)
        is_safe = rules.is_safe_button_type(raw_type)
        is_danger = not is_safe

        on_click_expr = _extract_brace_attr(attrs, "onClick")
        expect_modal = _resolve_handler_modal(on_click_expr, setter_to_title, local_fns)
        may_warn = _handler_may_warn(on_click_expr, local_fns)

        # 안전한 버튼이 모달을 여는 경우 modalOpen으로 생성; 위험 버튼은 click으로 생성하되 expectModal 보존
        if expect_modal and is_safe:
            b_step: dict[str, Any] = {
                "base_id": f"{scope_name}/modalOpen:{b_label}",
                "do": "modalOpen",
                "button": b_label,
                "type": raw_type,
                "expectModal": expect_modal,
            }
            if expect_modal is True:
                unknowns.append({"src": src_ref, "reason": "모달 제목이 동적 — expectModal:true"})
        else:
            b_step = {
                "base_id": f"{scope_name}/click:{b_label}",
                "do": "click",
                "button": b_label,
            }
            if is_known and raw_type:
                b_step["type"] = raw_type
            if expect_modal:
                b_step["expectModal"] = expect_modal
                if expect_modal is True:
                    unknowns.append({"src": src_ref, "reason": "모달 제목이 동적 — expectModal:true"})
            if is_danger:
                b_step["danger"] = True
                b_step["enabled"] = False

        if may_warn:
            b_step["mayWarn"] = True

        if _is_conditional_at(clean_text, abs_pos, jsx_start):
            b_step["conditional"] = True
        b_step["src"] = src_ref
        button_steps.append(b_step)

    # 8-b. 모달을 여는 `<a ... onClick={...}>텍스트</a>` 링크 (예: Pay10_Tab_Retire의 '잔여연차 미리보기')
    for m_a in re.finditer(r"<a\b", jsx_text):
        rel_start = m_a.start()
        abs_pos = jsx_start + rel_start
        t_end, self_closing = _find_tag_end(jsx_text, rel_start)
        if self_closing:
            continue
        attrs = jsx_text[rel_start:t_end]
        on_click_expr = _extract_brace_attr(attrs, "onClick")
        if not on_click_expr:
            continue
        close_pos = jsx_text.find("</a>", t_end)
        if close_pos == -1:
            continue
        a_label = _clean_jsx_text(jsx_text[t_end:close_pos])
        if not a_label or a_label in ("◀", "▶"):
            continue
        expect_modal = _resolve_handler_modal(on_click_expr, setter_to_title, local_fns)
        if expect_modal:
            line = _line_of(raw_text, abs_pos)
            a_src = f"{src_file}:{line}"
            a_step: dict[str, Any] = {
                "base_id": f"{scope_name}/modalOpen:{a_label}",
                "do": "modalOpen",
                "button": a_label,
                "expectModal": expect_modal,
                "src": a_src,
            }
            if expect_modal is True:
                unknowns.append({"src": a_src, "reason": "모달 제목이 동적 — expectModal:true"})
            if _handler_may_warn(on_click_expr, local_fns):
                a_step["mayWarn"] = True
            if _is_conditional_at(clean_text, abs_pos, jsx_start):
                a_step["conditional"] = True
            button_steps.append(a_step)

    # input_steps를 TSX 줄 번호 순서대로 정렬 (Field 밖 단독 Select 등이 원래 위치에 오도록)
    def _src_line_key(st: dict[str, Any]) -> int:
        s = str(st.get("src", ""))
        if ":" in s:
            tail = s.rsplit(":", 1)[-1]
            if tail.isdigit():
                return int(tail)
        return 0

    input_steps.sort(key=_src_line_key)

    # 9. 인라인 하위 컴포넌트(Page, TabPage, Grid, 하단 Edit 폼) 탐색 (렌더링 순서대로)
    # import된 컴포넌트 중 모달·프리미티브가 아닌 것들을 JSX(또는 TABS switch 함수) 등장 순서대로 수집
    imported_candidates: list[tuple[str, list[str]]] = []
    seen_stems: set[str] = set()
    for m_imp in _IMPORT_RE.finditer(raw_text):
        spec, src_mod = m_imp.group(1), m_imp.group(2)
        stem = Path(src_mod).stem
        if stem == comp_rec.name or stem in _PRIMITIVE_COMPONENTS or stem in seen_stems:
            continue
        seen_stems.add(stem)
        syms = [
            s.strip().split(" as ")[-1].strip()
            for s in re.sub(r"[{}]", "", spec).split(",")
            if s.strip()
        ]
        tag_syms = [s for s in ([stem] + syms) if s and s[0].isupper() and s not in _PRIMITIVE_COMPONENTS]
        imported_candidates.append((stem, list(dict.fromkeys(tag_syms))))

    child_usages: list[tuple[int, ScreenRecord, str]] = []
    for cand_name, tag_syms in imported_candidates:
        c_rec = _find_component_record(cand_name, by_name, layout, current_path)
        if not c_rec or _is_modal_component(c_rec, clean_text):
            continue
        # clean_text(switch문 포함)에서 `<CandName ...>` 또는 명명된 뷰 심볼 등장 위치 모두 찾기
        sym_alt = "|".join(re.escape(s) for s in tag_syms)
        matches = list(re.finditer(rf"<(?:{sym_alt})\b", clean_text))
        if not matches:
            continue
        if len(matches) == 1:
            child_usages.append((matches[0].start(), c_rec, c_rec.name))
        else:
            # 9.2절: 같은 하위 컴포넌트가 한 화면에 두 번 쓰이면 JSX의 key·title·탭 이름을 붙인다 (없으면 #2)
            for idx_u, mu in enumerate(matches, start=1):
                t_end, _ = _find_tag_end(clean_text, mu.start())
                u_attrs = clean_text[mu.start() : t_end]
                disc = (
                    _extract_str_attr(u_attrs, "key")
                    or _extract_str_attr(u_attrs, "title")
                    or _extract_str_attr(u_attrs, "label")
                )
                if disc:
                    sub_scope = f"{c_rec.name}[{disc}]"
                else:
                    sub_scope = c_rec.name if idx_u == 1 else f"{c_rec.name}#{idx_u}"
                child_usages.append((mu.start(), c_rec, sub_scope))

    child_usages.sort(key=lambda x: x[0])
    ordered_children = [(r, sc) for _, r, sc in child_usages]

    # 안전 버튼과 위험 버튼 정렬: 켜진 버튼(reset, download, modalOpen 등) 먼저, 위험 버튼(꺼짐) 나중
    safe_btns = [b for b in button_steps if not b.get("danger")]
    danger_btns = [b for b in button_steps if b.get("danger")]

    combined = search_steps + reset_steps + input_steps + tab_steps + grid_steps + safe_btns + danger_btns
    return combined, unknowns, ordered_children


def generate_screen_spec(
    target: str,
    layout: TobeLayout,
    tobe_screens: list[ScreenRecord],
    menus_summary: list[dict[str, Any]],
    full_menu_map: dict[str, list[tuple[str, str, str, bool]]],
    ctx: TraceContext,
    rules: ScreenTestRules,
) -> ScreenGenItem:
    """단일 화면번호/화면명에 대한 `.gen.cjs` 명세 객체(`ScreenGenItem`)를 생성한다."""
    desc = describe_single_screen(target, layout, tobe_screens, menus_summary, full_menu_map, ctx)
    menu_info = desc.get("menu") or {}
    tobe_info = desc.get("tobe")

    if not tobe_info or not tobe_info.get("main_file"):
        raise ValueError(f"화면 '{target}'에 대응하는 TOBE TSX 파일을 찾을 수 없습니다.")

    screen_no = str(menu_info.get("no") or target.lstrip("#"))
    menu_path = str(menu_info.get("path") or menu_info.get("name") or "")
    main_comp = str(tobe_info.get("main_screen") or Path(tobe_info["main_file"]).stem)
    rel_file = str(tobe_info["main_file"])
    full_path = layout.root / rel_file
    if not full_path.is_file():
        raise ValueError(f"TOBE 화면 파일이 디스크에 존재하지 않습니다: {full_path}")

    raw_bytes = full_path.read_bytes()
    file_hash = hashlib.sha1(raw_bytes).hexdigest()

    sid = str(tobe_info.get("page_style") or "")
    if not sid or sid == SID_UNKNOWN:
        try:
            sid = analyze_page_style(full_path).get("sid", SID_UNKNOWN)
        except Exception:  # noqa: BLE001
            sid = SID_UNKNOWN

    by_name = {s.name: s for s in tobe_screens}
    main_rec = by_name.get(main_comp) or _find_component_record(main_comp, by_name, layout, full_path)
    if not main_rec:
        raise ValueError(f"화면 레코드를 로드할 수 없습니다: {main_comp}")

    raw_steps: list[dict[str, Any]] = []
    unknowns: list[dict[str, str]] = []
    grid_counter = [0]

    # BFS/DFS로 메인 컴포넌트 + 인라인 하위 컴포넌트(최대 깊이 2) 단계 수집
    visited_scopes: set[str] = set()

    def _visit(rec: ScreenRecord, scope: str, depth: int) -> None:
        if scope in visited_scopes or depth > 2:
            return
        visited_scopes.add(scope)
        comp_steps, comp_unk, children = _extract_component_steps(
            comp_rec=rec,
            scope_name=scope,
            grid_counter=grid_counter,
            by_name=by_name,
            layout=layout,
            rules=rules,
        )
        raw_steps.extend(comp_steps)
        unknowns.extend(comp_unk)
        for child_rec, child_scope in children:
            _visit(child_rec, child_scope, depth + 1)

    _visit(main_rec, main_rec.name, 0)

    # 최종 단계 조립 및 9.2절 ID 중복 검사
    final_steps: list[dict[str, Any]] = [{"id": "open", "do": "open"}]
    seen_ids: dict[str, int] = {}

    for st in raw_steps:
        base_id = st.pop("base_id")
        cnt = seen_ids.get(base_id, 0) + 1
        seen_ids[base_id] = cnt
        if cnt == 1:
            final_id = base_id
        else:
            final_id = f"{base_id}#{cnt}"
            unknowns.append(
                {
                    "src": str(st.get("src", f"{Path(rel_file).name}:1")),
                    "reason": "id 중복",
                }
            )
        ordered_step: dict[str, Any] = {"id": final_id}
        for k, v in st.items():
            ordered_step[k] = v
        final_steps.append(ordered_step)

    return ScreenGenItem(
        screen_no=screen_no,
        menu_path=menu_path,
        sid=sid,
        main_component=main_comp,
        rel_file=rel_file,
        file_hash=file_hash,
        steps=final_steps,
        unknown=unknowns,
    )


def _format_js_prop_key(k: str) -> str:
    if re.fullmatch(r"[a-zA-Z_$][a-zA-Z0-9_$]*", k):
        return k
    return json.dumps(k, ensure_ascii=False)


def _format_js_inline_obj(d: dict[str, Any]) -> str:
    parts: list[str] = []
    for k, v in d.items():
        val_str = json.dumps(v, ensure_ascii=False)
        parts.append(f"{_format_js_prop_key(k)}: {val_str}")
    return "{ " + ", ".join(parts) + " }"


def render_gen_cjs(item: ScreenGenItem) -> str:
    """`ScreenGenItem`을 `.gen.cjs` JavaScript CommonJS 소스 문자열로 렌더링한다."""
    ver = project.current_version()
    lines = [
        f"// AUTO-GENERATED by yunhee test-gen-screen {ver} — DO NOT EDIT",
        f"// [{item.screen_no}] {item.menu_path}  SID={item.sid}  file={item.rel_file}",
    ]
    if any("index" in st for st in item.steps):
        lines.append(
            "// index: 컨테이너(in) 안 최상위 입력 칸 순서(0부터) — Field 하나(DatePicker 둘이 있어도) = 1칸, Field 밖 입력 요소 하나 = 1칸, 버튼·글자는 안 셈"
        )
    lines += [
        "module.exports = {",
        f'  screenNo: {json.dumps(item.screen_no, ensure_ascii=False)},',
        f'  sid: {json.dumps(item.sid, ensure_ascii=False)},',
        f'  source: {{ file: {json.dumps(item.rel_file, ensure_ascii=False)}, hash: {json.dumps(item.file_hash, ensure_ascii=False)} }},',
        "  steps: [",
    ]
    for st in item.steps:
        lines.append(f"    {_format_js_inline_obj(st)},")
    lines.append("  ],")
    if not item.unknown:
        lines.append("  unknown: [],")
    else:
        lines.append("  unknown: [")
        for u in item.unknown:
            lines.append(f"    {_format_js_inline_obj(u)},")
        lines.append("  ],")
    lines.append("};\n")
    return "\n".join(lines)


def _parse_existing_gen_cjs(content: str) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """기존 `.gen.cjs` 파일에서 steps와 unknown 배열을 파싱해 diff 요약에 쓴다."""
    steps: list[dict[str, Any]] = []
    unknowns: list[dict[str, str]] = []
    in_steps = False
    in_unknown = False
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("steps: ["):
            in_steps = True
            in_unknown = False
            continue
        if stripped.startswith("unknown: ["):
            in_steps = False
            in_unknown = True
            continue
        if stripped == "],":
            in_steps = False
            in_unknown = False
            continue
        if (in_steps or in_unknown) and stripped.startswith("{") and stripped.endswith("},"):
            obj_txt = stripped[:-1]
            # JS identifier key를 JSON key로 변환 (`{ id: "open" }` -> `{"id": "open"}`)
            json_txt = re.sub(r"([{,]\s*)([a-zA-Z_]\w*)\s*:", r'\1"\2":', obj_txt)
            try:
                parsed = json.loads(json_txt)
                if in_steps:
                    steps.append(parsed)
                else:
                    unknowns.append(parsed)
            except Exception:  # noqa: BLE001, S110
                pass
    return steps, unknowns


def _strip_version_comment(content: str) -> str:
    """첫 줄 버전 번호 차이만 있는 경우 동일 내용으로 판정하기 위해 정규화한다."""
    return re.sub(
        r"^// AUTO-GENERATED by yunhee test-gen-screen \S+ — DO NOT EDIT",
        "// AUTO-GENERATED by yunhee test-gen-screen — DO NOT EDIT",
        content,
        count=1,
    )


def _compute_diff_summary(old_content: str, new_item: ScreenGenItem) -> str:
    old_steps, old_unk = _parse_existing_gen_cjs(old_content)
    old_by_id = {s.get("id", ""): s for s in old_steps if s.get("id")}
    new_by_id = {s.get("id", ""): s for s in new_item.steps if s.get("id")}

    added = [sid for sid in new_by_id if sid not in old_by_id]
    removed = [sid for sid in old_by_id if sid not in new_by_id]
    modified = [sid for sid in new_by_id if sid in old_by_id and new_by_id[sid] != old_by_id[sid]]

    parts: list[str] = [f"단계 {len(old_steps)}→{len(new_item.steps)}"]
    detail_parts: list[str] = []
    if added:
        preview = ", ".join(added[:3]) + ("…" if len(added) > 3 else "")
        detail_parts.append(f"+{len(added)}({preview})")
    if removed:
        preview = ", ".join(removed[:3]) + ("…" if len(removed) > 3 else "")
        detail_parts.append(f"-{len(removed)}({preview})")
    if modified:
        preview = ", ".join(modified[:3]) + ("…" if len(modified) > 3 else "")
        detail_parts.append(f"변경 {len(modified)}({preview})")
    if detail_parts:
        parts.append("[" + ", ".join(detail_parts) + "]")
    if len(old_unk) != len(new_item.unknown):
        parts.append(f"unknown {len(old_unk)}→{len(new_item.unknown)}")
    return " ".join(parts)


def run_test_gen_screen(
    targets: list[str] | None = None,
    target_dir: Path | None = None,
    tobe: Path | None = None,
    stdout: bool = False,
    force: bool = False,
    all_screens: bool = False,
    summary: bool = False,
    rules_path: Path | None = None,
) -> ToolResult:
    """화면 시험 단계 목록(`.gen.cjs`) 정적 생성 실행."""
    layout = find_layout(tobe)
    if not layout.usable:
        return ToolResult(ok=False, error=f"TOBE 프로젝트 경로를 찾을 수 없습니다: {layout.root}")

    ctx = load_context("both")
    tobe_screens = iter_screens(side="tobe", tobe=layout.root)
    menus_summary = _load_menus_from_snapshot(layout)
    full_menu_map = _load_full_menu_map(ctx, layout)

    if not menus_summary:
        by_name = {s.name: s for s in tobe_screens}
        seen_nos: set[str] = set()
        for screen_cls, entries in full_menu_map.items():
            for no, full_path, leaf, active in entries:
                if no in seen_nos:
                    continue
                seen_nos.add(no)
                tobe_rec = by_name.get(screen_cls)
                menus_summary.append(
                    {
                        "no": no,
                        "path": full_path,
                        "name": leaf,
                        "active": active,
                        "asis_screen": screen_cls,
                        "tobe_screen": tobe_rec.name if tobe_rec else "",
                        "migrated": tobe_rec is not None,
                    }
                )

    parsed_targets = parse_screen_targets(targets or [])
    if all_screens:
        all_nos: list[str] = []
        for s in tobe_screens:
            if s.role == "Tab" and s.menu_no and s.menu_no not in all_nos:
                all_nos.append(s.menu_no)
        all_nos.sort(key=lambda x: (0, int(x)) if x.isdigit() else (1, x))
        parsed_targets = all_nos

    if not parsed_targets:
        return ToolResult(
            ok=False,
            error="생성할 화면번호(예: 1023, 1282)를 지정하거나 --all 옵션을 사용하세요.",
        )

    out_folder = target_dir or (layout.root / "tools" / "tests" / "screen-test" / "gen")
    if not out_folder.is_absolute():
        out_folder = (Path(config.WORK_DIR) / out_folder).resolve()

    rules = load_screen_test_rules(layout.root, custom_path=rules_path)

    items: list[ScreenGenItem] = []
    errors: list[str] = []

    for tgt in parsed_targets:
        try:
            item = generate_screen_spec(
                target=tgt,
                layout=layout,
                tobe_screens=tobe_screens,
                menus_summary=menus_summary,
                full_menu_map=full_menu_map,
                ctx=ctx,
                rules=rules,
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"[{tgt}] {exc}")
            continue

        rendered = render_gen_cjs(item)
        if stdout:
            item.status = "stdout"
            items.append(item)
            continue

        out_folder.mkdir(parents=True, exist_ok=True)
        file_path = out_folder / f"screen-test-{item.screen_no}.gen.cjs"
        item.out_path = file_path

        if not file_path.is_file():
            file_path.write_text(rendered, encoding="utf-8")
            item.status = "created"
        else:
            old_text = file_path.read_text(encoding="utf-8", errors="replace")
            is_same = _strip_version_comment(old_text) == _strip_version_comment(rendered)
            if is_same and not force:
                item.status = "unchanged"
            elif is_same and force:
                file_path.write_text(rendered, encoding="utf-8")
                item.status = "forced"
            else:
                item.diff_summary = _compute_diff_summary(old_text, item)
                file_path.write_text(rendered, encoding="utf-8")
                item.status = "updated"

        items.append(item)

    if stdout:
        stdout_text = "\n".join(render_gen_cjs(it).rstrip() for it in items)
        return ToolResult(
            ok=len(items) > 0 and not errors,
            data={"items": items, "errors": errors, "output": stdout_text},
            error="\n".join(errors) if errors and not items else None,
        )

    summary_text = format_gen_screen_summary(items, errors, summary_mode=summary)
    return ToolResult(
        ok=len(items) > 0 and not errors,
        data={"items": items, "errors": errors, "output": summary_text},
        error="\n".join(errors) if errors and not items else None,
    )


def format_gen_screen_summary(
    items: list[ScreenGenItem],
    errors: list[str],
    summary_mode: bool = False,
) -> str:
    lines: list[str] = []
    if not summary_mode:
        for it in items:
            status_badge = {
                "created": "신규",
                "updated": "갱신",
                "unchanged": "동일",
                "forced": "재작성(--force)",
            }.get(it.status, it.status)
            diff_part = f" — {it.diff_summary}" if it.diff_summary else ""
            unk_part = f", unknown={len(it.unknown)}" if it.unknown else ""
            lines.append(
                f"✔ [{it.screen_no}] {it.main_component} (SID={it.sid}): "
                f"단계 {len(it.steps)}개(켜짐 {it.enabled_count}, 위험/꺼짐 {it.danger_count}{unk_part}) "
                f"→ {it.out_path} [{status_badge}]{diff_part}"
            )
            for u in it.unknown:
                lines.append(f"  ⚠ unknown: {u['src']} — {u['reason']}")

    if summary_mode or len(items) > 1:
        total_steps = sum(len(it.steps) for it in items)
        total_danger = sum(it.danger_count for it in items)
        total_unk = sum(len(it.unknown) for it in items)
        unk_screens = sum(1 for it in items if it.unknown)
        ratio = (total_unk / (total_steps + total_unk) * 100.0) if (total_steps + total_unk) > 0 else 0.0

        if lines:
            lines.append("")
        lines.append(
            f"📊 요약: 화면 {len(items)}개 | 총 단계 {total_steps}개 (위험/꺼짐 {total_danger}개) | "
            f"unknown {total_unk}건 ({ratio:.1f}%, {unk_screens}/{len(items)}개 화면)"
        )
        if summary_mode and items:
            lines.append("")
            lines.append("| 화면번호 | 화면 클래스 | SID | 단계 수 | 켜짐 | 위험(꺼짐) | unknown | 비율 | 상태 |")
            lines.append("|:---|:---|:---|---:|---:|---:|---:|---:|:---|")
            for it in items:
                denom = len(it.steps) + len(it.unknown)
                r_it = (len(it.unknown) / denom * 100.0) if denom > 0 else 0.0
                lines.append(
                    f"| {it.screen_no} | `{it.main_component}` | {it.sid} | {len(it.steps)} | "
                    f"{it.enabled_count} | {it.danger_count} | {len(it.unknown)} | {r_it:.1f}% | {it.status} |"
                )

    for err in errors:
        lines.append(f"✖ 오류: {err}")

    return "\n".join(lines)
