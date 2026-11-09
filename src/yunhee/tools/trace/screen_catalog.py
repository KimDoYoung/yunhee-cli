"""통합 화면·모달·그리드·백엔드 카탈로그 (TOBE 기본, FE+BE+메뉴번호 자동 연결).

로컬 LLM(Qwen 14B) 에이전트가 `execute_python` 도구에서 호출하거나,
`yunhee trace-grid` CLI 명령어가 화면/모달/그리드/버튼/API 조건을 고속 탐색할 때 사용한다.
"""

from __future__ import annotations

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


@dataclass
class ScreenRecord:
    name: str
    side: str  # 'tobe' 또는 'asis'
    file: str  # 프로젝트 루트 기준 상대 경로
    menu_no: str = ""  # 예: '1001'
    menu_path: str = ""  # 예: '회계관리 > 기본정보 > 계정과목관리'
    menu_name: str = ""  # 말단 메뉴명 (예: '계정과목관리')
    opening_tabs: list[str] = field(default_factory=list)  # 이 컴포넌트를 여는 상위 _Tab_ 화면들
    modals: list[ModalInfo] = field(default_factory=list)
    grid_cols: list[GridCol] = field(default_factory=list)
    buttons: list[str] = field(default_factory=list)
    apis: list[str] = field(default_factory=list)  # ['GET /api/v1/...']
    backend_files: list[str] = field(default_factory=list)  # 연결된 Controller/Service/Mapper 파일들
    sql_ids: list[str] = field(default_factory=list)  # 연결된 MyBatis SQL ID 목록
    text: str = field(default="", repr=False)

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


def _connect_backend_info(
    api_calls: list[tuple[str, str]],
    idx: TobeIndex,
) -> tuple[list[str], list[str], list[str]]:
    """TSX의 api_calls로부터 (apis, backend_files, sql_ids)를 연결한다."""
    apis: list[str] = []
    be_files: list[str] = []
    sql_ids: list[str] = []
    for obj, fn_name in api_calls:
        fn = idx.api_fns.get((obj, fn_name))
        if not fn:
            continue
        apis.append(f"{fn.verb} {fn.url}")
        for ep in idx.endpoint_of(fn):
            be_files.append(idx.rel(ep.file))
            ctrl_fields = idx.service_fields.get(ep.controller, {})
            for s_field, s_method in ep.service_calls:
                svc_type = ctrl_fields.get(s_field)
                svc = idx.services.get((svc_type, s_method)) if svc_type else None
                if svc:
                    be_files.append(idx.rel(svc.file))
            for st in idx.statements_of(ep):
                sql_ids.append(st.key)
                be_files.append(idx.rel(st.file))
    return (
        list(dict.fromkeys(apis)),
        list(dict.fromkeys(be_files)),
        list(dict.fromkeys(sql_ids)),
    )


_GENERIC_CONFIRM_TITLES = {"확인", "삭제", "삭제확인", "취소", "복구", "배포", "업데이트 예정", "작성 Tip", "알림", "경고"}


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
                if t_val and t_val not in existing_titles:
                    existing_titles.add(t_val)
                    ln = p_text.count("\n", 0, m.start()) + 1
                    rec.modals.append(ModalInfo(kind=base_kind, title=t_val, line=ln))

            # 동적 타이틀 모달인 경우 부모의 setEditTarget({ titleName: '법규분류 수정' }) 등 추출
            if dyn_modals:
                for m in re.finditer(r"\b(?:titleName|title|heading)\s*:\s*(['\"])([^'\"]+)\1", p_text):
                    t_val = m.group(2).strip()
                    if t_val and t_val not in _GENERIC_CONFIRM_TITLES and t_val not in existing_titles:
                        existing_titles.add(t_val)
                        ln = p_text.count("\n", 0, m.start()) + 1
                        rec.modals.append(ModalInfo(kind=base_kind, title=t_val, line=ln))
                for m in re.finditer(r"\b(?:insert\w*|editData)\s*\([^)\n]*,\s*(['\"])([^'\"]+)\1", p_text):
                    t_val = m.group(2).strip()
                    if t_val and t_val not in ("insert", "edit", "update") and t_val not in existing_titles:
                        existing_titles.add(t_val)
                        ln = p_text.count("\n", 0, m.start()) + 1
                        rec.modals.append(ModalInfo(kind=base_kind, title=t_val, line=ln))


@lru_cache(maxsize=4)
def _cached_catalog(side: str, tobe_root_str: str, src_index_str: str) -> list[ScreenRecord]:
    tobe_path = Path(tobe_root_str) if tobe_root_str else None
    src_index_path = Path(src_index_str) if src_index_str else None
    ctx = load_context(side, src_index=src_index_path)
    layout = find_layout(tobe_path)
    menu_lookup = _load_full_menu_map(ctx, layout)
    records: list[ScreenRecord] = []

    if side in ("tobe", "both") and layout.usable:
        idx = build_index(str(layout.root))
        reg_tabs, file_texts, _file_paths, rev = _build_reverse_imports(layout.frontend)

        # pages/** 및 components/lookup/** 아래의 TSX 파일들을 대상으로 수집
        target_dirs = [layout.pages_dir, layout.frontend / "components" / "lookup"]
        tsx_files: list[Path] = []
        seen_paths: set[Path] = set()
        for d in target_dirs:
            if d.is_dir():
                for p in sorted(d.rglob("*.tsx")):
                    if p not in seen_paths:
                        seen_paths.add(p)
                        tsx_files.append(p)

        for p in tsx_files:
            stem = p.stem
            text = file_texts.get(stem) or p.read_text(encoding="utf-8", errors="replace")
            info = idx.tsx.get(stem) or parse_tsx(text, str(p))
            tabs = _find_opening_tabs(stem, reg_tabs, file_texts, rev)
            primary_tab = tabs[0] if tabs else (stem if "_Tab_" in stem else "")
            menu_no, menu_path, menu_name = _pick_full_menu(primary_tab or stem, menu_lookup, file_texts)
            if not menu_no and info.header_menu_nos:
                menu_no = info.header_menu_nos[0]
            apis, be_files, sql_ids = _connect_backend_info(info.api_calls, idx)
            records.append(
                ScreenRecord(
                    name=stem,
                    side="tobe",
                    file=idx.rel(p),
                    menu_no=menu_no,
                    menu_path=menu_path,
                    menu_name=menu_name,
                    opening_tabs=tabs,
                    modals=extract_modals_from_tsx(text),
                    grid_cols=info.grid_cols,
                    buttons=info.buttons,
                    apis=apis,
                    backend_files=be_files,
                    sql_ids=sql_ids,
                    text=text,
                )
            )
        _propagate_caller_modal_titles(records, file_texts, rev)

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
