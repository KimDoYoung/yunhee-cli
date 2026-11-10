"""통합 화면·모달·그리드·백엔드 카탈로그 (TOBE 기본, FE+BE+메뉴번호 자동 연결).

로컬 LLM(Qwen 14B) 에이전트가 `execute_python` 도구에서 호출하거나,
`yunhee trace-grid` CLI 명령어가 화면/모달/그리드/버튼/API 조건을 고속 탐색할 때 사용한다.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import deque
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.trace.resolve import TraceContext, load_context, load_menus
from yunhee.tools.trace.tobe import (
    GridCol,
    TobeIndex,
    TobeLayout,
    build_index,
    find_layout,
    parse_tsx,
)

_IMPORT_RE = re.compile(
    r"""^\s*import\s+([^;'"]+?)\s+from\s+['"]([^'"]+)['"]""",
    re.MULTILINE,
)

_MODAL_TAG_RE = re.compile(r"<(LookupModal|Modal|EditModal)\b")
_MODAL_CALL_RE = re.compile(
    r"\bModal\.(confirm|info|warning|error|success)\s*\(\s*\{([\s\S]{1,600}?)\}"
)
_ASIS_GRID_COL_RE = re.compile(
    r'^\s+-\s+([A-Za-z_]\w*)\s+(\d+)\s+"([^"]*)"\s+(\w+)',
    re.MULTILINE,
)
_ASIS_MODAL_HEADING_RE = re.compile(r'제목="([^"]+)"|setHeading\(\s*"([^"]+)"\s*\)')


@dataclass
class ModalInfo:
    kind: str  # 'Modal', 'LookupModal', 'EditModal', 'Modal.confirm' 등
    title: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "title": self.title, "line": self.line}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ModalInfo:
        return cls(kind=d.get("kind", "Modal"), title=d.get("title", ""), line=int(d.get("line", 0)))


@dataclass
class ScreenRecord:
    name: str
    side: str  # 'tobe' 또는 'asis'
    file: str  # 프로젝트 루트 기준 상대 경로
    menu_no: str = ""  # 예: '1001'
    menu_path: str = ""  # 예: '회계관리 > 기본정보 > 계정과목관리'
    menu_name: str = ""  # 말단 메뉴명 (예: '계정과목관리')
    role: str = ""  # 'Tab', 'TabPage', 'Grid', 'Lookup', 'Edit', 'Popup', 'Move', 'Component'
    page_style: str = ""  # 'SG', 'SGP', 'MF' 등 SID
    opening_tabs: list[str] = field(default_factory=list)  # 이 컴포넌트를 여는 상위 _Tab_ 화면들
    child_components: list[str] = field(default_factory=list)  # 이 화면이 사용하는 하위 모달/그리드/컴포넌트들
    search_fields: list[str] = field(default_factory=list)  # 조회바(SearchBar.Field) 라벨 목록
    modals: list[ModalInfo] = field(default_factory=list)
    grid_cols: list[GridCol] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)
    apis: list[str] = field(default_factory=list)  # ['GET /api/v1/...']
    backend_files: list[str] = field(default_factory=list)  # 연결된 Controller/Service/Mapper 파일들
    sql_ids: list[str] = field(default_factory=list)  # 연결된 MyBatis SQL ID 목록
    tables: list[str] = field(default_factory=list)  # 연결된 DB 테이블 목록
    mtime: float = 0.0
    content_hash: str = ""
    _text: str = field(default="", repr=False)
    _root_dir: str = field(default="", repr=False)

    def __init__(
        self,
        name: str,
        side: str,
        file: str,
        menu_no: str = "",
        menu_path: str = "",
        menu_name: str = "",
        opening_tabs: list[str] | None = None,
        modals: list[ModalInfo] | None = None,
        grid_cols: list[GridCol] | None = None,
        buttons: list[str] | None = None,
        apis: list[str] | None = None,
        backend_files: list[str] | None = None,
        sql_ids: list[str] | None = None,
        text: str = "",
        role: str = "",
        page_style: str = "",
        child_components: list[str] | None = None,
        search_fields: list[str] | None = None,
        tables: list[str] | None = None,
        mtime: float = 0.0,
        content_hash: str = "",
        root_dir: str = "",
    ) -> None:
        self.name = name
        self.side = side
        self.file = file
        self.menu_no = menu_no
        self.menu_path = menu_path
        self.menu_name = menu_name
        self.role = role or _infer_role(name)
        self.page_style = page_style
        self.opening_tabs = list(opening_tabs or [])
        self.child_components = list(child_components or [])
        self.search_fields = list(search_fields or [])
        self.modals = list(modals or [])
        self.grid_cols = list(grid_cols or [])
        self.buttons = list(buttons or [])
        self.apis = list(apis or [])
        self.backend_files = list(backend_files or [])
        self.sql_ids = list(sql_ids or [])
        self.tables = list(tables or [])
        self.mtime = mtime
        self.content_hash = content_hash
        self._text = text
        self._root_dir = root_dir

    @property
    def text(self) -> str:
        if not self._text and self._root_dir and self.file:
            p = Path(self._root_dir) / self.file
            if p.is_file():
                self._text = p.read_text(encoding="utf-8", errors="replace")
        return self._text

    @text.setter
    def text(self, val: str) -> None:
        self._text = val

    @property
    def raw_text(self) -> str:
        """LLM이 s.text 또는 s.raw_text 어느 쪽으로 접근해도 동작하도록 별칭 제공."""
        return self.text

    def format_hit(self, detail: str = "") -> str:
        """표준 출력 포맷: #화면번호 | 메뉴명(경로) | 컴포넌트명 (열어주는 탭) | 파일경로 | 일치상세"""
        no_str = f"#{self.menu_no}" if self.menu_no else "-"
        menu_str = self.menu_path or self.menu_name or "-"
        comp_str = self.name
        if self.opening_tabs and self.name not in self.opening_tabs:
            comp_str = f"{self.name} (← {', '.join(self.opening_tabs[:2])})"
        if detail:
            return f"{no_str} | {menu_str} | {comp_str} | {self.file} | {detail}"
        return f"{no_str} | {menu_str} | {comp_str} | {self.file}"

    def to_card_text(self) -> str:
        """ChromaDB 시맨틱 임베딩 및 에이전트 Prefetch 주입용 요약 카드 텍스트."""
        no_part = f"#{self.menu_no}" if self.menu_no else "메뉴번호 없음"
        menu_part = self.menu_path or self.menu_name or "-"
        style_part = f", 스타일: {self.page_style}" if self.page_style else ""
        lines = [
            f"[TOBE {self.role or '화면'} {no_part} | {menu_part} | {self.name}{style_part}]",
            f"- 프론트엔드 파일: {self.file}",
        ]
        if self.opening_tabs and self.name not in self.opening_tabs:
            lines.append(f"- 상위 오픈 탭 화면: {', '.join(self.opening_tabs)}")
        if self.child_components:
            lines.append(f"- 하위 연결 컴포넌트/모달: {', '.join(self.child_components)}")
        if self.search_fields:
            lines.append(f"- 조회 조건(SearchBar): {', '.join(self.search_fields)}")
        if self.buttons:
            lines.append(f"- 버튼 목록: {', '.join(self.buttons)}")
        if self.modals:
            m_strs = [f"{m.kind}({m.title})" for m in self.modals if not m.title.startswith("{")]
            if m_strs:
                lines.append(f"- 모달 창: {', '.join(dict.fromkeys(m_strs))}")
        if self.grid_cols:
            c_strs = [f"{c.label}({c.field}:{c.col_type})" for c in self.grid_cols[:20]]
            lines.append(f"- 그리드 컬럼: {', '.join(c_strs)}")
        if self.apis:
            lines.append(f"- 호출 API: {', '.join(self.apis)}")
        if self.backend_files:
            lines.append(f"- 백엔드 파일: {', '.join(self.backend_files)}")
        if self.sql_ids:
            lines.append(f"- 매퍼 SQL ID: {', '.join(self.sql_ids)}")
        if self.tables:
            lines.append(f"- 참조 DB 테이블: {', '.join(self.tables)}")
        return "\n".join(lines)

    def compute_hash(self) -> str:
        card = self.to_card_text()
        self.content_hash = hashlib.sha256(card.encode("utf-8")).hexdigest()[:16]
        return self.content_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "side": self.side,
            "file": self.file,
            "menu_no": self.menu_no,
            "menu_path": self.menu_path,
            "menu_name": self.menu_name,
            "role": self.role,
            "page_style": self.page_style,
            "opening_tabs": self.opening_tabs,
            "child_components": self.child_components,
            "search_fields": self.search_fields,
            "modals": [m.to_dict() for m in self.modals],
            "grid_cols": [
                {"field": c.field, "label": c.label, "col_type": c.col_type, "width": c.width}
                for c in self.grid_cols
            ],
            "buttons": self.buttons,
            "apis": self.apis,
            "backend_files": self.backend_files,
            "sql_ids": self.sql_ids,
            "tables": self.tables,
            "mtime": self.mtime,
            "content_hash": self.content_hash or self.compute_hash(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any], root_dir: str = "") -> ScreenRecord:
        return cls(
            name=d["name"],
            side=d.get("side", "tobe"),
            file=d.get("file", ""),
            menu_no=d.get("menu_no", ""),
            menu_path=d.get("menu_path", ""),
            menu_name=d.get("menu_name", ""),
            role=d.get("role", ""),
            page_style=d.get("page_style", ""),
            opening_tabs=d.get("opening_tabs", []),
            child_components=d.get("child_components", []),
            search_fields=d.get("search_fields", []),
            modals=[ModalInfo.from_dict(m) for m in d.get("modals", [])],
            grid_cols=[
                GridCol(
                    c["field"],
                    c["label"],
                    col_type=c.get("col_type", "text"),
                    width=int(c.get("width", 0)),
                )
                for c in d.get("grid_cols", [])
            ],
            buttons=d.get("buttons", []),
            apis=d.get("apis", []),
            backend_files=d.get("backend_files", []),
            sql_ids=d.get("sql_ids", []),
            tables=d.get("tables", []),
            mtime=float(d.get("mtime", 0.0)),
            content_hash=d.get("content_hash", ""),
            root_dir=root_dir,
        )


def _infer_role(name: str) -> str:
    if "_Tab_" in name:
        return "Tab"
    if "_TabPage_" in name or "_Page_" in name:
        return "TabPage"
    if "_Grid_" in name:
        return "Grid"
    if "_Lookup_" in name:
        return "Lookup"
    if "_Edit_" in name:
        return "Edit"
    if "_Popup_" in name:
        return "Popup"
    if "_Move_" in name:
        return "Move"
    return "Component"


def _extract_page_style(text: str) -> str:
    m = re.search(r"스타일\s*:\s*([A-Z]{2,4})\b", text[:1500])
    return m.group(1) if m else ""


def _extract_search_fields(text: str) -> list[str]:
    fields: list[str] = []
    for m in re.finditer(r"<(?:SearchBar\.Field|SearchField)\b[^>]*?\blabel\s*=\s*(['\"])(.*?)\1", text):
        lbl = m.group(2).strip()
        if lbl and lbl not in fields:
            fields.append(lbl)
    return fields


def _extract_jsx_tag_props(text: str, tag_start: int) -> str:
    """`<Modal` 등 여는 태그 시작 위치에서 중괄호 깊이를 고려해 여는 태그의 속성 문자열만 추출한다."""
    i = tag_start
    n = len(text)
    brace_depth = 0
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
            elif brace_depth == 0 and ch == ">":
                return text[tag_start : i + 1]
        i += 1
    return text[tag_start : min(n, tag_start + 800)]


def _extract_title_brace_expr(props: str) -> str | None:
    """`title={...}`에서 중첩 중괄호(`style={{ ... }}`)를 고려해 전체 표현식을 추출한다."""
    m = re.search(r"\btitle\s*=\s*\{", props)
    if not m:
        return None
    i = m.end()
    n = len(props)
    depth = 1
    in_str: str | None = None
    while i < n:
        ch = props[i]
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
                    return props[m.end() : i].strip()
        i += 1
    return None


def extract_modals_from_tsx(text: str) -> list[ModalInfo]:
    """TSX 텍스트에서 `<Modal title=...>`, `<LookupModal title=...>`, `Modal.confirm({ title: ... })`를 추출한다."""
    modals: list[ModalInfo] = []
    seen: set[tuple[str, str, int]] = set()
    has_dynamic_modal_tag = False
    dynamic_modal_kind = "Modal"

    for m in _MODAL_TAG_RE.finditer(text):
        kind = m.group(1)
        line = text.count("\n", 0, m.start()) + 1
        props = _extract_jsx_tag_props(text, m.start())
        # 1) title="계정과목" 또는 title='계정과목'
        m_str = re.search(r'\btitle\s*=\s*(["\'])(.*?)\1', props)
        if m_str:
            key = (kind, m_str.group(2), line)
            if key not in seen:
                seen.add(key)
                modals.append(ModalInfo(kind=kind, title=m_str.group(2), line=line))
            continue
        # 2) title={...} 표현식 내 JSX 텍스트 또는 문자열 리터럴 추출
        expr = _extract_title_brace_expr(props)
        if expr is not None:
            # 2-a) title={<b ...>점검방법</b>} 형태 JSX 태그 내부 텍스트
            if expr.startswith("<") and ">" in expr:
                jsx_inner = re.sub(r"<[^>]+>", "", expr).strip()
                if jsx_inner and "{" not in jsx_inner and "}" not in jsx_inner:
                    key = (kind, jsx_inner, line)
                    if key not in seen:
                        seen.add(key)
                        modals.append(ModalInfo(kind=kind, title=jsx_inner, line=line))
                    continue

            # 2-b) 조건 비교식(=== 'insert', !== '1') 및 style={{...}} 제거 후 문자열 리터럴 추출
            cleaned_expr = re.sub(r"style\s*=\s*\{\{[^}]*\}\}", "", expr)
            cleaned_expr = re.sub(r"(?:===|!==|==|!=)\s*(['\"])[^'\"]*\1", "", cleaned_expr)
            lits = [lit[1].strip() for lit in re.findall(r'(["\'])(.*?)\1', cleaned_expr) if lit[1].strip()]
            if lits:
                for lit in dict.fromkeys(lits):
                    key = (kind, lit, line)
                    if key not in seen:
                        seen.add(key)
                        modals.append(ModalInfo(kind=kind, title=lit, line=line))
            else:
                has_dynamic_modal_tag = True
                dynamic_modal_kind = kind
                key = (kind, f"{{{expr}}}", line)
                if key not in seen:
                    seen.add(key)
                    modals.append(ModalInfo(kind=kind, title=f"{{{expr}}}", line=line))

    # 동적 title={target?.titleName} 등을 쓰는 모달 컴포넌트라면 JSDoc 헤더 설명도 후보로 추가
    if has_dynamic_modal_tag:
        hdr = _extract_header_title(text)
        if hdr:
            key = (dynamic_modal_kind, hdr, 1)
            if key not in seen:
                seen.add(key)
                modals.insert(0, ModalInfo(kind=dynamic_modal_kind, title=hdr, line=1))

    for m in _MODAL_CALL_RE.finditer(text):
        kind = f"Modal.{m.group(1)}"
        line = text.count("\n", 0, m.start()) + 1
        body = m.group(2)
        m_title = re.search(r'\btitle\s*:\s*(["\'])(.*?)\1', body)
        if m_title:
            key = (kind, m_title.group(2), line)
            if key not in seen:
                seen.add(key)
                modals.append(ModalInfo(kind=kind, title=m_title.group(2), line=line))

    return modals


def _load_full_menu_map(ctx: TraceContext, layout: TobeLayout) -> dict[str, list[tuple[str, str, str, bool]]]:
    """화면 클래스명 → [(메뉴번호, 전체경로, 말단메뉴명, 활성여부), ...] 매핑."""
    by_screen: dict[str, list[tuple[str, str, str, bool]]] = {}

    def _add(no: str, full_path: str, screen: str | None, use_str: str) -> None:
        if not screen:
            return
        full_clean = full_path.strip()
        leaf = full_clean.split(">")[-1].strip()
        active = use_str.strip().lower() in ("true", "y", "1", "사용") and not leaf.startswith("(X)") and not leaf.startswith("(구)")
        entry = (no.strip(), full_clean, leaf, active)
        lst = by_screen.setdefault(screen.strip(), [])
        if entry not in lst:
            lst.append(entry)

    # 1. WORK_DIR / TOBE_SRC_DIR / YUNHEE_DIR 아래의 docs/as-is/menus.tsv 탐색
    candidate_roots = [layout.root, Path(config.WORK_DIR)]
    if getattr(config, "TOBE_SRC_DIR", None):
        candidate_roots.append(Path(config.TOBE_SRC_DIR))
    if getattr(config, "YUNHEE_DIR", None):
        candidate_roots.append(Path(config.YUNHEE_DIR))

    for root in dict.fromkeys(candidate_roots):
        tsv = root / "docs" / "as-is" / "menus.tsv"
        if tsv.is_file():
            for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
                parts = line.split("\t")
                if len(parts) >= 4:
                    _add(parts[0], parts[1], parts[2], parts[3])
        menus_md = root / "docs" / "as-is" / "src" / "menus.md"
        if menus_md.is_file():
            row_re = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$")
            link_re = re.compile(r"\[`([^`]+)`\]")
            for line in menus_md.read_text(encoding="utf-8", errors="replace").splitlines():
                m = row_re.match(line)
                if m:
                    lk = link_re.search(m.group(4))
                    _add(m.group(2), m.group(1), lk.group(1) if lk else None, m.group(3))

    for m in load_menus(ctx):
        _add(m.no, m.path, m.screen, m.use)

    return by_screen


def _symbol_uses_child(target_text: str, sym: str, child: str) -> bool:
    if sym == child or sym == Path(child).stem:
        return True
    m = re.search(rf"export\s+(?:const|function)\s+{re.escape(sym)}\b", target_text)
    if not m:
        return True
    rest = target_text[m.start() :]
    nxt = re.search(r"\nexport\s+(?:const|function|type|interface)\s+", rest[10:])
    block = rest[: nxt.start() + 10] if nxt else rest
    return child in block


def _build_reverse_imports(front: Path) -> tuple[set[str], dict[str, str], dict[str, Path], dict[str, list[tuple[str, list[str]]]]]:
    screens_file = front / "pages" / "screens.ts"
    reg_tabs: set[str] = set()
    if screens_file.is_file():
        cleaned = re.sub(r"//.*", "", screens_file.read_text(encoding="utf-8", errors="replace"))
        reg_tabs = set(re.findall(r"\b([A-Za-z0-9]+_Tab_[A-Za-z0-9_]+)\b", cleaned))

    file_texts: dict[str, str] = {}
    file_paths: dict[str, Path] = {}
    if front.is_dir():
        for p in sorted(front.rglob("*.tsx")):
            if p.name == "screens.ts":
                continue
            file_texts[p.stem] = p.read_text(encoding="utf-8", errors="replace")
            file_paths.setdefault(p.stem, p)

    rev: dict[str, list[tuple[str, list[str]]]] = {}
    for stem, text in file_texts.items():
        for m in _IMPORT_RE.finditer(text):
            spec, src = m.group(1), m.group(2)
            target = Path(src).stem
            if target not in file_texts:
                continue
            syms = [s.strip().split(" as ")[0].strip() for s in re.sub(r"[{}]", "", spec).split(",") if s.strip()]
            rev.setdefault(target, []).append((stem, syms))

    return reg_tabs, file_texts, file_paths, rev


def _find_opening_tabs(
    stem: str,
    reg_tabs: set[str],
    file_texts: dict[str, str],
    rev: dict[str, list[tuple[str, list[str]]]],
) -> list[str]:
    if stem in reg_tabs:
        return [stem]
    visited: dict[str, int] = {stem: 0}
    q: deque[tuple[str, int, str | None]] = deque([(stem, 0, None)])
    tabs: dict[str, int] = {}
    fallback_tabs: dict[str, int] = {}
    while q:
        cur, dist, prev_child = q.popleft()
        cur_text = file_texts.get(cur, "")
        check_target = prev_child if prev_child is not None else cur
        for parent, syms in rev.get(cur, ()):
            if cur not in syms and not any(_symbol_uses_child(cur_text, s, check_target) for s in syms):
                continue
            if parent in visited:
                continue
            visited[parent] = dist + 1
            if parent in reg_tabs:
                tabs[parent] = dist + 1
            else:
                if "_Tab_" in parent:
                    fallback_tabs[parent] = dist + 1
                q.append((parent, dist + 1, cur))
    chosen = tabs or fallback_tabs
    if not chosen and "_Tab_" in stem:
        return [stem]
    return sorted(chosen, key=lambda k: (chosen[k], k))


def _extract_header_title(text: str) -> str:
    """파일 첫머리 /** ... */ 주석의 첫 줄에서 화면/모달 제목 설명을 추출한다."""
    m = re.match(r"\s*/\*\*+([\s\S]*?)\*/", text)
    if not m:
        return ""
    for line in m.group(1).splitlines():
        clean = line.strip().lstrip("*").strip()
        if not clean or clean.startswith(("AS-IS", "레이아웃", "스타일")):
            continue
        clean = re.sub(r"^\[?\d{3,4}\]?\s*", "", clean)
        clean = re.split(r"\s+[—–-]\s+|\s*\((?:[A-Z]{1,3}\d+|1단계|2단계)", clean)[0].strip()
        return clean
    return ""


def _pick_full_menu(
    tab: str,
    menu_lookup: dict[str, list[tuple[str, str, str, bool]]],
    file_texts: dict[str, str],
) -> tuple[str, str, str]:
    """tab 클래스에 대응하는 (메뉴번호, 전체경로, 말단메뉴명)을 반환한다."""
    entries = menu_lookup.get(tab, [])
    full_text = file_texts.get(tab, "")
    head_text = full_text[:2000]
    head_nos = re.findall(r"\[(\d{3,4})\]", head_text.split("*/")[0] if "*/" in head_text else head_text)
    if entries:
        for hno in head_nos:
            for no, full_path, leaf, active in entries:
                if no == hno and active:
                    return no, full_path, leaf
        for no, full_path, leaf, active in entries:
            if active:
                return no, full_path, leaf
        return entries[0][0], entries[0][1], entries[0][2]
    fallback_title = _extract_header_title(full_text)
    if head_nos:
        return head_nos[0], fallback_title, fallback_title
    return "", fallback_title, fallback_title


def _normalize_asis_col_type(raw_type: str) -> str:
    low = raw_type.lower()
    if "boolean" in low or "check" in low:
        return "boolean"
    if "date" in low:
        return "date"
    if "long" in low or "double" in low or "money" in low:
        return low
    return raw_type[0].lower() + raw_type[1:] if raw_type else "text"


_TABLE_NAME_RE = re.compile(r"\b(?:from|join|update|into)\s+([a-z]{2,5}\d{2}_[a-z0-9_]+)\b")


def _connect_backend_info(
    api_calls: list[tuple[str, str]],
    idx: TobeIndex,
    xml_tables_cache: dict[str, list[str]] | None = None,
) -> tuple[list[str], list[str], list[str], list[str]]:
    """TSX의 api_calls로부터 (apis, backend_files, sql_ids, tables)를 연결한다."""
    apis: list[str] = []
    be_files: list[str] = []
    sql_ids: list[str] = []
    tables: list[str] = []
    for obj, fn_name in api_calls:
        fns = getattr(idx, "api_fns_multi", {}).get((obj, fn_name)) or ([idx.api_fns[(obj, fn_name)]] if (obj, fn_name) in idx.api_fns else [])
        if not fns:
            continue
        for fn in fns:
            apis.append(f"{fn.verb} {fn.url}")
        eps = idx.endpoints_of_fn((obj, fn_name)) if hasattr(idx, "endpoints_of_fn") else idx.endpoint_of(fns[0])
        for ep in eps:
            be_files.append(idx.rel(ep.file))
            ctrl_fields = idx.service_fields.get(ep.controller, {})
            for s_field, s_method in ep.service_calls:
                svc_type = ctrl_fields.get(s_field)
                svc = idx.services.get((svc_type, s_method)) if svc_type else None
                if svc:
                    be_files.append(idx.rel(svc.file))
            for st in idx.statements_of(ep):
                sql_ids.append(st.key)
                rel_xml = idx.rel(st.file)
                be_files.append(rel_xml)
                st_tbls = getattr(st, "tables", None)
                if st_tbls is not None:
                    tables.extend(st_tbls)
                elif xml_tables_cache is not None:
                    if st.file not in xml_tables_cache:
                        xml_p = Path(st.file)
                        if xml_p.is_file():
                            raw_xml = xml_p.read_text(encoding="utf-8", errors="replace").lower()
                            xml_tables_cache[st.file] = list(dict.fromkeys(_TABLE_NAME_RE.findall(raw_xml)))
                        else:
                            xml_tables_cache[st.file] = []
                    tables.extend(xml_tables_cache[st.file])
    return (
        list(dict.fromkeys(apis)),
        list(dict.fromkeys(be_files)),
        list(dict.fromkeys(sql_ids)),
        list(dict.fromkeys(tables)),
    )


_GENERIC_CONFIRM_TITLES = {"확인", "삭제", "삭제확인", "취소", "복구", "배포", "업데이트 예정", "작성 Tip", "알림", "경고"}
_NON_TITLE_CODE_RE = re.compile(
    r"^(?:[A-Z]\d{2}|%|insert|edit|update|delete|view|[A-Za-z0-9]+_(?:Tab|TabPage|Grid|Lookup|Edit|Popup|Page|Move)_[A-Za-z0-9_]+)$"
)


def _is_valid_propagated_title(val: str) -> bool:
    if not val or len(val) < 2 or val in _GENERIC_CONFIRM_TITLES:
        return False
    return not _NON_TITLE_CODE_RE.match(val)


def _propagate_caller_modal_titles(
    records: list[ScreenRecord],
    file_texts: dict[str, str],
    rev: dict[str, list[tuple[str, list[str]]]],
) -> None:
    """동적 title={target?.titleName} 등을 받는 모달 컴포넌트에 호출부(부모 화면)의 실제 타이틀 문자열을 연결한다."""
    for rec in records:
        if rec.side != "tobe":
            continue
        dyn_modals = [m for m in rec.modals if m.title.startswith("{")]
        is_modal_comp = bool(dyn_modals) or any(k in rec.name for k in ("_Edit_", "_Lookup_", "_Popup_", "_Move_"))
        if not is_modal_comp:
            continue
        base_kind = dyn_modals[0].kind if dyn_modals else (rec.modals[0].kind if rec.modals else "Modal")
        existing_titles = {m.title for m in rec.modals}

        for parent_stem, _syms in rev.get(rec.name, ()):
            p_text = file_texts.get(parent_stem, "")
            if not p_text:
                continue
            # 1) <ChildComponent ... title="타이틀" />
            for m in re.finditer(rf"<{re.escape(rec.name)}\b[^>]*?\btitle\s*=\s*(['\"])([^'\"]+)\1", p_text):
                t_val = m.group(2).strip()
                if _is_valid_propagated_title(t_val) and t_val not in existing_titles:
                    existing_titles.add(t_val)
                    ln = p_text.count("\n", 0, m.start()) + 1
                    rec.modals.append(ModalInfo(kind=base_kind, title=t_val, line=ln))

            # 동적 타이틀 모달인 경우 부모의 setEditTarget({ titleName: '법규분류 수정' }) 등 추출
            # (범용 공통 모달이 수십 개 화면에서 import될 때 부모의 무관한 문자열이 섞이지 않도록 호출처 5개 이하인 전용 모달에 한정)
            if dyn_modals and len(rev.get(rec.name, ())) <= 5:
                for m in re.finditer(r"\b(?:titleName|modalTitle|popupTitle)\s*:\s*(['\"])([^'\"]+)\1", p_text):
                    t_val = m.group(2).strip()
                    if _is_valid_propagated_title(t_val) and t_val not in existing_titles:
                        existing_titles.add(t_val)
                        ln = p_text.count("\n", 0, m.start()) + 1
                        rec.modals.append(ModalInfo(kind=base_kind, title=t_val, line=ln))
                for m in re.finditer(r"\b(?:insert\w*|editData)\s*\([^)\n]*,\s*(['\"])([^'\"]+)\1", p_text):
                    t_val = m.group(2).strip()
                    if _is_valid_propagated_title(t_val) and t_val not in existing_titles:
                        existing_titles.add(t_val)
                        ln = p_text.count("\n", 0, m.start()) + 1
                        rec.modals.append(ModalInfo(kind=base_kind, title=t_val, line=ln))


def get_catalog_snapshot_path(layout: TobeLayout | None = None) -> Path:
    """TOBE 카탈로그 스냅샷(.yunhee/tobe_catalog.json) 경로를 반환한다."""
    lay = layout or find_layout()
    return lay.root / ".yunhee" / "tobe_catalog.json"


def _collect_tobe_tsx_files(layout: TobeLayout) -> list[Path]:
    target_dirs = [layout.pages_dir, layout.frontend / "components" / "lookup"]
    tsx_files: list[Path] = []
    seen_paths: set[Path] = set()
    for d in target_dirs:
        if d.is_dir():
            for p in sorted(d.rglob("*.tsx")):
                if p not in seen_paths:
                    seen_paths.add(p)
                    tsx_files.append(p)
    return tsx_files


def _try_load_fresh_snapshot(layout: TobeLayout) -> list[ScreenRecord] | None:
    """스냅샷이 존재하고 모든 TSX 파일의 mtime 및 개수가 일치하면 즉시(0.01초) 로드한다."""
    snap_path = get_catalog_snapshot_path(layout)
    if not snap_path.is_file():
        return None
    try:
        data = json.loads(snap_path.read_text(encoding="utf-8"))
        raw_screens = data.get("screens", [])
        if not raw_screens:
            return None
        tsx_files = _collect_tobe_tsx_files(layout)
        if len(tsx_files) != len(raw_screens):
            return None
        by_stem = {item["name"]: item for item in raw_screens}
        for p in tsx_files:
            item = by_stem.get(p.stem)
            if not item:
                return None
            if abs(p.stat().st_mtime - float(item.get("mtime", 0.0))) > 0.01:
                return None
        root_str = str(layout.root)
        return [ScreenRecord.from_dict(item, root_dir=root_str) for item in raw_screens]
    except Exception:  # noqa: BLE001
        return None


def _save_snapshot(layout: TobeLayout, records: list[ScreenRecord]) -> None:
    """TOBE 카탈로그 레코드 목록을 .yunhee/tobe_catalog.json에 저장한다."""
    try:
        snap_path = get_catalog_snapshot_path(layout)
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": 1,
            "tobe_root": str(layout.root),
            "screen_count": len(records),
            "screens": [s.to_dict() for s in records],
        }
        snap_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:  # noqa: BLE001, S110
        pass


def _load_or_update_snapshot(layout: TobeLayout) -> list[ScreenRecord] | None:
    """TOBE 카탈로그 스냅샷을 로드하며, 변경된 파일만 증분 갱신(0.01~0.3초)하여 최신 상태를 유지한다."""
    snap_records = _try_load_fresh_snapshot(layout)
    if snap_records is not None:
        return snap_records

    snap_path = get_catalog_snapshot_path(layout)
    existing_map: dict[str, dict[str, Any]] = {}
    if snap_path.is_file():
        try:
            data = json.loads(snap_path.read_text(encoding="utf-8"))
            for item in data.get("screens", []):
                existing_map[item["name"]] = item
        except Exception:  # noqa: BLE001
            existing_map.clear()

    tsx_files = _collect_tobe_tsx_files(layout)
    disk_stems = {p.stem for p in tsx_files}

    # 스냅샷이 일부 존재하면 변경된 파일만 증분 갱신
    if existing_map:
        stale_files: list[Path] = []
        for p in tsx_files:
            item = existing_map.get(p.stem)
            if not item or abs(p.stat().st_mtime - float(item.get("mtime", 0.0))) > 0.01:
                stale_files.append(p)

        # 삭제된 파일 제거
        for del_stem in [s for s in list(existing_map.keys()) if s not in disk_stems]:
            existing_map.pop(del_stem, None)

        if stale_files:
            idx = build_index(str(layout.root))
            reg_tabs, file_texts, _file_paths, rev = _build_reverse_imports(layout.frontend)
            ctx = load_context("tobe")
            menu_lookup = _load_full_menu_map(ctx, layout)
            xml_tables_cache: dict[str, list[str]] = {}
            root_str = str(layout.root)

            for p in stale_files:
                stem = p.stem
                text = file_texts.get(stem) or p.read_text(encoding="utf-8", errors="replace")
                info = idx.tsx.get(stem) or parse_tsx(text, str(p))
                tabs = _find_opening_tabs(stem, reg_tabs, file_texts, rev)
                primary_tab = tabs[0] if tabs else (stem if "_Tab_" in stem else "")
                menu_no, menu_path, menu_name = _pick_full_menu(primary_tab or stem, menu_lookup, file_texts)
                if not menu_no and info.header_menu_nos:
                    menu_no = info.header_menu_nos[0]
                apis, be_files, sql_ids, tables = _connect_backend_info(info.api_calls, idx, xml_tables_cache)
                try:
                    mtime = p.stat().st_mtime
                except OSError:
                    mtime = 0.0
                rec = ScreenRecord(
                    name=stem,
                    side="tobe",
                    file=idx.rel(p),
                    menu_no=menu_no,
                    menu_path=menu_path,
                    menu_name=menu_name,
                    role=_infer_role(stem),
                    page_style=_extract_page_style(text),
                    opening_tabs=tabs,
                    search_fields=_extract_search_fields(text),
                    modals=extract_modals_from_tsx(text),
                    grid_cols=info.grid_cols,
                    buttons=info.buttons,
                    apis=apis,
                    backend_files=be_files,
                    sql_ids=sql_ids,
                    tables=tables,
                    mtime=mtime,
                    text=text,
                    root_dir=root_str,
                )
                existing_map[stem] = rec.to_dict()

        root_str = str(layout.root)
        records = [ScreenRecord.from_dict(item, root_dir=root_str) for item in existing_map.values()]
        _save_snapshot(layout, records)
        return records

    return None


def _populate_children_and_hashes(records: list[ScreenRecord], file_texts: dict[str, str]) -> None:
    """상위 탭 ↔ 하위 컴포넌트 양방향 연결 및 content_hash 계산."""
    by_name = {r.name: r for r in records if r.side == "tobe"}
    for r in records:
        if r.side != "tobe":
            continue
        # 1) 직접 import한 내부 컴포넌트
        text = file_texts.get(r.name, "")
        children: list[str] = list(r.child_components)
        for m in _IMPORT_RE.finditer(text):
            target = Path(m.group(2)).stem
            if target in by_name and target != r.name and target not in children:
                children.append(target)
        r.child_components = children
        # 2) opening_tabs 역방향 등록
        for tab_name in r.opening_tabs:
            if tab_name != r.name and tab_name in by_name:
                tab_rec = by_name[tab_name]
                if r.name not in tab_rec.child_components:
                    tab_rec.child_components.append(r.name)
    for r in records:
        if r.side == "tobe":
            r.compute_hash()


@lru_cache(maxsize=4)
def _cached_catalog(side: str, tobe_root_str: str, src_index_str: str) -> list[ScreenRecord]:
    tobe_path = Path(tobe_root_str) if tobe_root_str else None
    src_index_path = Path(src_index_str) if src_index_str else None
    layout = find_layout(tobe_path)

    # TOBE 단독 조회 시 신선한 스냅샷 또는 증분 갱신이 가능하면 즉시 반환 (~0.01s - 0.2s)
    if side == "tobe" and layout.usable:
        snap_records = _load_or_update_snapshot(layout)
        if snap_records is not None:
            return snap_records

    ctx = load_context(side, src_index=src_index_path)
    menu_lookup = _load_full_menu_map(ctx, layout)
    records: list[ScreenRecord] = []

    if side in ("tobe", "both") and layout.usable:
        idx = build_index(str(layout.root))
        reg_tabs, file_texts, _file_paths, rev = _build_reverse_imports(layout.frontend)
        tsx_files = _collect_tobe_tsx_files(layout)
        xml_tables_cache: dict[str, list[str]] = {}
        root_str = str(layout.root)

        for p in tsx_files:
            stem = p.stem
            text = file_texts.get(stem) or p.read_text(encoding="utf-8", errors="replace")
            info = idx.tsx.get(stem) or parse_tsx(text, str(p))
            tabs = _find_opening_tabs(stem, reg_tabs, file_texts, rev)
            primary_tab = tabs[0] if tabs else (stem if "_Tab_" in stem else "")
            menu_no, menu_path, menu_name = _pick_full_menu(primary_tab or stem, menu_lookup, file_texts)
            if not menu_no and info.header_menu_nos:
                menu_no = info.header_menu_nos[0]
            apis, be_files, sql_ids, tables = _connect_backend_info(info.api_calls, idx, xml_tables_cache)
            try:
                mtime = p.stat().st_mtime
            except OSError:
                mtime = 0.0
            records.append(
                ScreenRecord(
                    name=stem,
                    side="tobe",
                    file=idx.rel(p),
                    menu_no=menu_no,
                    menu_path=menu_path,
                    menu_name=menu_name,
                    role=_infer_role(stem),
                    page_style=_extract_page_style(text),
                    opening_tabs=tabs,
                    search_fields=_extract_search_fields(text),
                    modals=extract_modals_from_tsx(text),
                    grid_cols=info.grid_cols,
                    buttons=info.buttons,
                    apis=apis,
                    backend_files=be_files,
                    sql_ids=sql_ids,
                    tables=tables,
                    mtime=mtime,
                    text=text,
                    root_dir=root_str,
                )
            )
        _propagate_caller_modal_titles(records, file_texts, rev)
        _populate_children_and_hashes(records, file_texts)
        _save_snapshot(layout, records)

    if side in ("asis", "both") and ctx.src_index and ctx.src_index.is_dir():
        for md_path in sorted(ctx.src_index.glob("*/*/*.md")):
            if md_path.parent.name not in ("screens", "components"):
                continue
            stem = md_path.stem
            text = md_path.read_text(encoding="utf-8", errors="replace")
            java_file_m = re.search(r"^- 파일:\s*`([^`]+)`", text, re.MULTILINE)
            java_rel = java_file_m.group(1) if java_file_m else str(md_path.relative_to(ctx.src_index))

            # 메뉴 매핑 (자신이 _Tab_이거나 문서 내 상위 화면 참조)
            entries = menu_lookup.get(stem, [])
            menu_no, menu_path, menu_name = ("", "", "")
            if entries:
                active_entries = [e for e in entries if e[3]]
                chosen = active_entries[0] if active_entries else entries[0]
                menu_no, menu_path, menu_name = chosen[0], chosen[1], chosen[2]

            # AS-IS 그리드 컬럼 파싱
            gcols: list[GridCol] = []
            for gm in _ASIS_GRID_COL_RE.finditer(text):
                field_n, w_s, label_s, raw_t = gm.group(1), gm.group(2), gm.group(3), gm.group(4)
                gcols.append(GridCol(field_n, label_s, col_type=_normalize_asis_col_type(raw_t), width=int(w_s)))

            # AS-IS 모달/윈도우 제목 파싱
            modals: list[ModalInfo] = []
            for mm in _ASIS_MODAL_HEADING_RE.finditer(text):
                t_val = mm.group(1) or mm.group(2)
                line_no = text.count("\n", 0, mm.start()) + 1
                modals.append(ModalInfo(kind="Window", title=t_val, line=line_no))

            records.append(
                ScreenRecord(
                    name=stem,
                    side="asis",
                    file=java_rel,
                    menu_no=menu_no,
                    menu_path=menu_path,
                    menu_name=menu_name,
                    opening_tabs=[stem] if "_Tab_" in stem else [],
                    modals=modals,
                    grid_cols=gcols,
                    buttons=[],
                    text=text,
                )
            )

    return records


def iter_screens(
    side: str = "tobe",
    tobe: Path | str | None = None,
    src_index: Path | str | None = None,
) -> list[ScreenRecord]:
    """화면·팝업·모달·그리드 통합 카탈로그를 반환한다 (기본값: side='tobe')."""
    norm_side = (side or "tobe").strip().lower()
    if norm_side not in ("tobe", "asis", "both"):
        norm_side = "tobe"
    tobe_str = str(Path(tobe).resolve()) if tobe else ""
    src_idx_str = str(Path(src_index).resolve()) if src_index else ""
    return list(_cached_catalog(norm_side, tobe_str, src_idx_str))


def resolve_menu_info(
    name_or_path: str,
    tobe: Path | str | None = None,
) -> dict[str, Any]:
    """화면/컴포넌트 이름이나 파일 경로를 받아 메뉴 번호, 메뉴 경로, 상위 탭 정보를 반환한다."""
    stem = Path(name_or_path).stem
    for s in iter_screens(side="both", tobe=tobe):
        if s.name == stem or s.file.endswith(name_or_path):
            return {
                "name": s.name,
                "side": s.side,
                "file": s.file,
                "menu_no": s.menu_no,
                "menu_path": s.menu_path,
                "menu_name": s.menu_name,
                "opening_tabs": s.opening_tabs,
            }
    return {
        "name": stem,
        "side": "unknown",
        "file": name_or_path,
        "menu_no": "",
        "menu_path": "",
        "menu_name": "",
        "opening_tabs": [],
    }
