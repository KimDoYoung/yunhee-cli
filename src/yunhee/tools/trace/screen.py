"""trace-screen: 화면 팩트 시트 (필드·그리드·버튼·이벤트·RPC/API·SQL·테이블·DB 함수).

ASIS는 `yunhee index-src`가 만든 화면 색인 문서(`<도메인>/screens/<클래스>.md`)를 읽어 재구성한다 (새 파서 없음).
TOBE는 같은 클래스명의 TSX를 찾아 `analysis/tobe`의 요약을 재사용한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.as_is.drift import parse_frontmatter
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import (
    TraceContext,
    find_class_doc,
    load_menus,
    resolve_screen,
    wants_asis,
    wants_tobe,
)

MAX_LISTED_CLASSES = 12


@dataclass
class ServiceRow:
    key: str  # emp.Emp00_TransInfo.selectByText
    callers: list[str]  # Emp00_Tab_TransInfo:418
    server: str  # Emp00_TransInfo.java:33
    sql_ids: list[str]  # emp00_trans_info.selectByText
    note: str = ""  # SQL 칸이 링크가 아닌 설명(예: UpdateDataModel ...)일 때


@dataclass
class EventRow:
    id: str  # E3
    text: str  # 원문 한 줄
    desc: str  # transName[재직].Collapse (L225)
    guard: str  # 이벤트 조건 대괄호 (예: Enter, 선택>0). 없으면 ""
    handlers: str  # → 뒤의 핸들러 설명
    handler_methods: list[str] = field(default_factory=list)  # retrieve, insert
    ranges: list[tuple[int, int]] = field(default_factory=list)  # 인라인·생성자 줄 범위
    unreachable: bool = False


@dataclass
class MethodRow:
    name: str
    signature: str
    start: int
    end: int
    callers: list[str]  # E1, 생성자, insert
    does: str
    kind: str


@dataclass
class ClassUi:
    name: str
    java: str = ""
    layout: str = ""
    toolbar: list[str] = field(default_factory=list)
    inputs: str = ""
    grids: list[tuple[str, list[str]]] = field(default_factory=list)  # (그리드 이름, 컬럼 줄들)
    events: list[str] = field(default_factory=list)
    events_note: str = ""
    buttons: list[str] = field(default_factory=list)
    event_rows: list[EventRow] = field(default_factory=list)
    methods: list[MethodRow] = field(default_factory=list)


@dataclass
class ScreenDoc:
    name: str
    kind: str = ""
    menus: list[str] = field(default_factory=list)
    file: str = ""
    classes: list[str] = field(default_factory=list)
    services: list[ServiceRow] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    unresolved_calls: list[str] = field(default_factory=list)
    servlets: list[str] = field(default_factory=list)
    ui: dict[str, ClassUi] = field(default_factory=dict)
    frontmatter: dict[str, Any] | None = None


def _section(text: str, title: str) -> str:
    """`## 제목` 절의 본문 (다음 `## `까지)."""
    m = re.search(rf"^## {re.escape(title)}\s*$", text, re.MULTILINE)
    if not m:
        return ""
    rest = text[m.end():]
    nxt = re.search(r"^## ", rest, re.MULTILINE)
    return rest[: nxt.start()] if nxt else rest


def _cells(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def _names(body: str) -> list[str]:
    return re.findall(r"`([^`]+)`", body)


def _parse_services(body: str) -> list[ServiceRow]:
    rows: list[ServiceRow] = []
    for line in body.splitlines():
        if not line.startswith("| `") or line.startswith("|:"):
            continue
        cells = _cells(line)
        if len(cells) < 4:
            continue
        key = cells[0].strip("`")
        callers = [c.strip() for c in cells[1].split(",") if c.strip()]
        server = (re.search(r"\[`([^`]+)`\]", cells[2]) or re.search(r"`([^`]+)`", cells[2]))
        sql_cell = cells[3]
        sql_ids = re.findall(r"\[`([^`]+)`\]\([^)]*\)", sql_cell)
        note = "" if sql_ids else re.sub(r"\s+", " ", sql_cell)
        rows.append(ServiceRow(key, callers, server.group(1) if server else cells[2], sql_ids, note))
    return rows


_LINE_RANGE = re.compile(r"L(\d+)(?:-(\d+))?")
_EVENT_LINE = re.compile(r"^\[(E\d+)\]\s+(.*?)\s+→\s+(.*)$")
_GUARD = re.compile(r"\.\w+ \[([^\]]+)\] \(")


def _ranges(text: str) -> list[tuple[int, int]]:
    return [(int(a), int(b or a)) for a, b in _LINE_RANGE.findall(text)]


def parse_event_line(line: str) -> EventRow | None:
    """`[E3] transName[재직].Collapse (L225) → retrieve()` 한 줄을 구조화한다."""
    m = _EVENT_LINE.match(line.strip())
    if not m:
        m0 = re.match(r"^\[(E\d+)\]\s+(.*)$", line.strip())  # 핸들러가 없는 이벤트
        return EventRow(m0.group(1), line.strip(), m0.group(2), "", "") if m0 else None
    ev_id, desc, handlers = m.groups()
    guard = _GUARD.search(desc)
    row = EventRow(ev_id, line.strip(), desc, guard.group(1) if guard else "", handlers)
    row.unreachable = "도달 불가" in handlers
    # 핸들러 설명: `a(), b()` 또는 `인라인 L243-248 (...)`. 인라인·생성자는 줄 범위가 곧 코드 위치다
    row.handler_methods = re.findall(r"(?<![\w.])([A-Za-z_]\w*)\(\)", re.sub(r"인라인 L[\d-]+ \(.*", "", handlers))
    if "생성자" in desc:
        row.ranges += _ranges(desc)
    for inline in re.findall(r"인라인 (L\d+(?:-\d+)?)", handlers):
        row.ranges += _ranges(inline)
    return row


def _parse_methods(block: str) -> list[MethodRow]:
    rows: list[MethodRow] = []
    m = re.search(r"^#### 메서드\s*$", block, re.MULTILINE)
    if not m:
        return rows
    for line in block[m.end():].splitlines()[1:]:
        if line.startswith("#") or not line.strip():
            break
        if not line.startswith("|") or line.startswith(("| ---", "| 메서드")):
            continue
        cells = _cells(line)
        if len(cells) < 3:
            continue
        name = re.search(r"([A-Za-z_]\w*)\(", cells[0])
        rng = _ranges(cells[1])
        if not name or not rng:
            continue
        callers = [c.strip() for c in cells[2].split(",") if c.strip() and c.strip() != "-"]
        rows.append(MethodRow(name.group(1), cells[0], rng[0][0], rng[0][1], callers,
                              cells[3] if len(cells) > 3 else "", cells[4] if len(cells) > 4 else ""))
    return rows


def _handler_text(raw: str) -> str:
    """버튼 onClick 식을 짧게: 인라인 핸들러는 줄 범위만, 그 밖은 식 그대로."""
    inline = re.search(r"인라인 (L[\d-]+)", raw)
    return f"인라인 {inline.group(1)}" if inline else raw.strip()[:60]


def _parse_ui_class(name: str, block: str, head: str) -> ClassUi:
    ui = ClassUi(name=name)
    m = re.search(r"`([^`]+)`", head)
    ui.java = m.group(1) if m else ""
    if m_layout := re.search(r"^- 레이아웃: (.+)$", block, re.MULTILINE):
        ui.layout = m_layout.group(1).strip()
    ui.toolbar = [t.strip() for t in re.findall(r"^- 툴바 `[^`]+`: (.+)$", block, re.MULTILINE)]
    if m_in := re.search(r"^- 입력·하위 화면: (.+)$", block, re.MULTILINE):
        ui.inputs = m_in.group(1).strip()

    lines = block.splitlines()
    i = 0
    while i < len(lines):
        g = re.match(r"^- 그리드 `([^`]+)`", lines[i])
        if g:
            cols: list[str] = []
            i += 1
            while i < len(lines) and re.match(r"^\s+- ", lines[i]):
                cols.append(lines[i].strip()[2:])
                i += 1
            ui.grids.append((g.group(1), cols))
            continue
        i += 1

    if m_ev := re.search(r"^#### 이벤트(?: \(([^)]*)\))?\s*$", block, re.MULTILINE):
        ui.events_note = m_ev.group(1) or ""
        for line in block[m_ev.end():].splitlines()[1:]:
            if line.startswith("#") or not line.strip():
                break
            ui.events.append(line.strip())
            if (row := parse_event_line(line)) is not None:
                ui.event_rows.append(row)
    ui.methods = _parse_methods(block)
    if m_bt := re.search(r"^#### 사용된 버튼들\s*$", block, re.MULTILINE):
        for line in block[m_bt.end():].splitlines()[1:]:
            if line.startswith("#") or not line.strip():
                break
            label = re.search(r">([^<>]*)</Button>\s*$", line.strip())
            btype = re.search(r'type="([^"]+)"', line)
            handler = re.search(r"onClick=\{(.*)\}>[^<>]*</Button>", line)
            ui.buttons.append(
                f"{label.group(1) if label else '?'} [{btype.group(1) if btype else '?'}]"
                + (f" → {_handler_text(handler.group(1))}" if handler else "")
            )
    return ui


def parse_screen_doc(name: str, text: str) -> ScreenDoc:
    """색인 화면 마크다운을 구조화한다."""
    fm, body = parse_frontmatter(text)
    doc = ScreenDoc(name=name, frontmatter=fm)
    if m := re.search(r"^- 종류: (.+)$", body, re.MULTILINE):
        doc.kind = m.group(1).strip()
    doc.menus = [m.strip() for m in re.findall(r"^- 메뉴: (.+)$", body, re.MULTILINE)]
    if m := re.search(r"^- 파일: `([^`]+)`", body, re.MULTILINE):
        doc.file = m.group(1)
    doc.classes = re.findall(r"^  - `([^`]+)` `[^`]+`$", body, re.MULTILINE)
    doc.services = _parse_services(_section(body, "서비스"))
    doc.tables = _names(_section(body, "테이블"))
    doc.functions = _names(_section(body, "DB 함수"))
    doc.unresolved_calls = [
        re.sub(r"\s+", " ", ln[2:]).strip() for ln in _section(body, "해석 못 한 서비스 호출").splitlines() if ln.startswith("- ")
    ]
    doc.servlets = [re.sub(r"\s+", " ", ln[2:]).strip() for ln in _section(body, "서블릿 호출").splitlines() if ln.startswith("- ")]

    ui_text = _section(body, "UI")
    parts = re.split(r"^### (.+)$", ui_text, flags=re.MULTILINE)
    for head, block in zip(parts[1::2], parts[2::2], strict=False):
        cls = head.split(" ", 1)[0].strip()
        doc.ui[cls] = _parse_ui_class(cls, block, head)
    return doc


def _index_statements(ctx: TraceContext) -> dict[str, Any]:
    return (ctx.index_data or {}).get("statements", {})


def _asis_result(doc: ScreenDoc, ctx: TraceContext, detail_class: str | None, res: TraceResult) -> None:
    facts, evidence, unresolved = res.facts, res.evidence, res.unresolved
    facts.append(f"종류: {doc.kind or '?'}")
    facts += [f"메뉴: {m}" for m in doc.menus]
    if doc.file:
        facts.append(f"소스: {doc.file}")
    if doc.classes:
        shown = ", ".join(doc.classes[:MAX_LISTED_CLASSES])
        more = f" … 외 {len(doc.classes) - MAX_LISTED_CLASSES}개" if len(doc.classes) > MAX_LISTED_CLASSES else ""
        facts.append(f"함께 쓰는 클래스({len(doc.classes)}): {shown}{more}")

    target = detail_class or doc.name
    ui = doc.ui.get(target)
    if detail_class and ui is None:
        unresolved.append(f"--class {detail_class}: 이 화면의 UI 절에 없는 클래스 (가능: {', '.join(doc.ui)})")
    if ui is not None:
        if ui.layout:
            facts.append(f"레이아웃({ui.name}): {ui.layout}")
        facts += [f"툴바({ui.name}): {t}" for t in ui.toolbar]
        if ui.inputs:
            facts.append(f"입력·하위 화면({ui.name}): {ui.inputs}")
        for gname, cols in ui.grids:
            facts.append(f"그리드 {gname}({ui.name}, {len(cols)}열):\n" + "\n".join(f"  - {c}" for c in cols))
        if ui.events:
            note = f" ⚠ {ui.events_note}" if ui.events_note else ""
            facts.append(f"이벤트({ui.name}, {len(ui.events)}){note}:\n" + "\n".join(f"  {e}" for e in ui.events))
        if ui.buttons:
            facts.append(f"버튼({ui.name}, {len(ui.buttons)}):\n" + "\n".join(f"  - {b}" for b in ui.buttons))
        if ui.java:
            evidence.append(f"{ui.java} (UI 클래스 {ui.name})")
    if not detail_class:
        others = [u for n, u in doc.ui.items() if n != doc.name]
        if others:
            facts.append(
                f"하위 클래스 UI 요약({len(others)}) — `--class <이름>`으로 상세:\n"
                + "\n".join(f"  - {u.name}: 이벤트 {len(u.events)}, 버튼 {len(u.buttons)}, 그리드 {len(u.grids)}" for u in others)
            )

    services = doc.services
    if detail_class:
        services = [s for s in services if any(c.startswith(f"{detail_class}:") for c in s.callers)]
    if services:
        lines = []
        for s in services:
            target_sql = ", ".join(s.sql_ids) if s.sql_ids else (s.note or "(SQL ID 없음)")
            lines.append(f"  - {s.key} → {target_sql}")
            evidence.append(f"{s.key} 호출: {', '.join(s.callers)} / 서버 {s.server}")
        scope = f"{detail_class}이(가) 호출하는 " if detail_class else ""
        facts.append(f"{scope}서비스(RPC) {len(services)}개:\n" + "\n".join(lines))
    statements = _index_statements(ctx)
    for sql_id in dict.fromkeys(i for s in services for i in s.sql_ids):
        info = statements.get(sql_id)
        if info:
            evidence.append(f"SQL {sql_id} → {info['file']}:{info['line']}")
    if doc.tables:
        facts.append(f"테이블({len(doc.tables)}): {', '.join(doc.tables)}")
    if doc.functions:
        facts.append(f"DB 함수({len(doc.functions)}): {', '.join(doc.functions)}")
    if doc.servlets:
        facts.append(f"서블릿 호출({len(doc.servlets)}):\n" + "\n".join(f"  - {s}" for s in doc.servlets))
    unresolved += [f"해석 못 한 서비스 호출 {c}" for c in doc.unresolved_calls]
    if doc.ui.get(doc.name) and doc.ui[doc.name].events_note and not detail_class:
        unresolved.append(f"이벤트 주의({doc.name}): {doc.ui[doc.name].events_note}")

    if doc.frontmatter:
        evidence.append(
            f"색인: {doc.name}.md (source_commit {str(doc.frontmatter.get('source_commit', ''))[:8]}, indexed_at {doc.frontmatter.get('indexed_at', '?')})"
        )


def _find_tobe(name: str, tobe_dir: Path | None) -> Path | None:
    roots = [tobe_dir] if tobe_dir else [config.WORK_DIR / "frontend" / "src", config.WORK_DIR / "src"]
    for root in roots:
        if root and root.is_dir():
            found = sorted(root.rglob(f"{name}.tsx"))
            if found:
                return found[0]
    return None


def _tobe_result(name: str, tobe_dir: Path | None, res: TraceResult) -> None:
    from yunhee.tools.analysis import tobe

    path = _find_tobe(name, tobe_dir)
    if path is None:
        res.unresolved.append(f"TOBE 화면 {name}.tsx를 찾지 못함 (--tobe로 frontend/src 경로 지정)")
        return
    summary = tobe._summarize_tsx(path, path.read_text(encoding="utf-8", errors="replace"))
    res.facts.append(f"TOBE 소스: {path}")
    if summary.get("hooks"):
        res.facts.append("TOBE 훅: " + ", ".join(summary["hooks"]))
    if summary.get("apis"):
        res.facts.append("TOBE API 호출: " + ", ".join(summary["apis"]))
    if summary.get("events"):
        res.facts.append(f"TOBE 이벤트 주석({len(summary['events'])}): " + ", ".join(summary["events"][:12]))
    if summary.get("tree"):
        res.facts.append("TOBE 렌더 트리 뼈대:\n" + "\n".join(f"  {t}" for t in summary["tree"][:30]))
    res.evidence.append(f"TOBE {path}")


def trace_screen(
    target: str,
    ctx: TraceContext,
    detail_class: str | None = None,
    tobe_dir: Path | None = None,
) -> TraceResult:
    """화면 하나의 팩트 시트를 만든다. target은 화면 클래스명, 접두사, 또는 메뉴 번호(#1029)."""
    res = TraceResult(
        command="trace-screen",
        description="화면 팩트 시트: 필드·라벨, 그리드 컬럼, 버튼, 이벤트, 호출 RPC/API, SQL, 테이블, DB 함수",
        side=ctx.side,
        params={"screen_id": target, "class": detail_class},
    )
    res.unresolved += ctx.unresolved
    name: str | None = None
    if wants_asis(ctx.side) and ctx.has_index:
        name = resolve_screen(target, ctx)
        res.params["resolved"] = name
        doc_path = find_class_doc(ctx, name)
        if doc_path is None:
            res.unresolved.append(f"색인 문서를 찾지 못함: {name}.md")
        else:
            doc = parse_screen_doc(name, doc_path.read_text(encoding="utf-8", errors="replace"))
            _asis_result(doc, ctx, detail_class, res)
            res.evidence.append(f"색인 파일: {doc_path}")
    if wants_tobe(ctx.side):
        tobe_name = name or detail_class or target
        _tobe_result(tobe_name, tobe_dir, res)
    return res


def screens_of_menu(ctx: TraceContext) -> dict[str, list[str]]:
    """화면 클래스 → 메뉴 경로(#번호) 목록. trace-table이 화면을 메뉴로 표시할 때 쓴다."""
    out: dict[str, list[str]] = {}
    for m in load_menus(ctx):
        if m.screen:
            out.setdefault(m.screen, []).append(f"{m.path} (#{m.no})")
    return out

