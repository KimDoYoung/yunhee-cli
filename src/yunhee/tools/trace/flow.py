"""trace-flow: 이벤트 하나의 끝까지 이어진 사슬 (이벤트 → 핸들러 → 서비스(RPC) → 서버 메서드 → SQL → 테이블).

화면 색인 문서에서 이벤트·메서드(줄 범위)·서비스 호출 위치(`클래스:줄`)를 읽어 **줄 범위로** 잇고,
SQL의 테이블은 `sql_parse`로 해석한다. 사슬이 끊기는 곳(동적 서비스 키, 다른 클래스에서 여는 동작)은 거기서 멈추고 unresolved로 남긴다.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import (
    TraceContext,
    find_class_doc,
    resolve_screen,
    wants_tobe,
)
from yunhee.tools.trace.screen import (
    ClassUi,
    EventRow,
    MethodRow,
    ScreenDoc,
    ServiceRow,
    parse_screen_doc,
)
from yunhee.tools.trace.table import _ops

MAX_SQL_PER_SERVICE = 12
_OPENS = re.compile(r"(?:팝업|조회창|화면)\s+([A-Za-z]\w+)\s+열기")
_DYNAMIC = re.compile(r"UpdateDataModel\((\w+)\).*?동적\s+(\w+(?:/\w+)?)")


def normalize_event(event: str) -> str:
    """`e3`, `3`, `E3` → `E3`."""
    e = event.strip().upper()
    return e if e.startswith("E") else f"E{e}"


def handler_closure(ui: ClassUi, ev: EventRow) -> list[tuple[MethodRow, list[str]]]:
    """이벤트가 직접·간접으로 부르는 메서드와 그 호출 경로. 메서드 표의 호출처(이벤트 ID·메서드 이름·생성자)를 따라간다.

    반환: [(메서드, [중간 메서드 이름…])] — 이벤트가 바로 부르면 경로는 비어 있다.
    """
    tokens = {ev.id}
    if "생성자" in ev.desc:
        tokens.add("생성자")
    chosen: dict[str, MethodRow] = {}
    parent: dict[str, str | None] = {}
    for m in ui.methods:
        if tokens & set(m.callers) or m.name in ev.handler_methods:
            chosen[m.name] = m
            parent[m.name] = None
    grew = True
    while grew:
        grew = False
        for m in ui.methods:
            via = next((c for c in m.callers if c in chosen), None)
            if m.name not in chosen and via:
                chosen[m.name] = m
                parent[m.name] = via
                grew = True

    def path(name: str) -> list[str]:
        out: list[str] = []
        cur = parent.get(name)
        while cur:
            out.append(cur)
            cur = parent.get(cur)
        return list(reversed(out))

    return [(m, path(m.name)) for m in sorted(chosen.values(), key=lambda m: m.start)]


def _in_ranges(line: int, ranges: list[tuple[int, int]]) -> bool:
    return any(a <= line <= b for a, b in ranges)


def _calls_in(svc: ServiceRow, cls: str, ranges: list[tuple[int, int]]) -> list[int]:
    lines = []
    for c in svc.callers:
        name, _, ln = c.partition(":")
        if name == cls and ln.isdigit() and _in_ranges(int(ln), ranges):
            lines.append(int(ln))
    return lines


def _statements(ctx: TraceContext) -> dict[str, Any] | None:
    if not ctx.src_root or not Path(ctx.src_root).is_dir():
        return None
    from yunhee.tools.as_is.mybatis_render import get_all_statements

    return get_all_statements(Path(ctx.src_root)) or None


def _sql_tables(sql_id: str, statements: dict[str, Any] | None) -> tuple[list[str], str]:
    """(`테이블(RW)` 표기들, 해석 방식 메모). 해석할 수 없으면 빈 목록과 사유."""
    if statements is None:
        return [], "ASIS 소스 없음"
    from yunhee.tools.sql_parse import parse_statement

    res = parse_statement(sql_id, statements)
    if not res.ok:
        return [], "mapper에 없음"
    parsed = res.data
    items = [f"{t}({_ops(parsed, t) or 'R'})" for t in parsed.tables]
    return items, "정규식 추정" if parsed.fallback else ""


def _chain_for_service(svc: ServiceRow, statements: dict[str, Any] | None, res: TraceResult, tables: dict[str, set[str]]) -> list[str]:
    lines = [f"→ 서비스 {svc.key} → 서버 {svc.server}"]
    sql_ids = svc.sql_ids
    for sql_id in sql_ids[:MAX_SQL_PER_SERVICE]:
        items, note = _sql_tables(sql_id, statements)
        suffix = f" [{note}]" if note else ""
        lines.append(f"    SQL {sql_id}: {', '.join(items) if items else '(테이블 없음)'}{suffix}")
        for item in items:
            name, _, ops = item.partition("(")
            tables.setdefault(name, set()).update(ops.rstrip(")"))
    if len(sql_ids) > MAX_SQL_PER_SERVICE:
        lines.append(f"    … SQL {len(sql_ids) - MAX_SQL_PER_SERVICE}개 더")
    if not sql_ids:
        dyn = _DYNAMIC.search(svc.note)
        if dyn:
            table, op = dyn.group(1), dyn.group(2)
            lines.append(f"    UpdateDataModel({table}) 동적 {op}")
            tables.setdefault(table, set()).update("D" if "DELETE" in op else "CU")
        else:
            res.unresolved.append(f"서비스 {svc.key}: 연결된 SQL ID가 없음 ({svc.note or '서버 메서드가 SQL을 직접 부르지 않음'})")
    return lines


def _event_summary(ui: ClassUi) -> str:
    return "\n".join(
        f"  {e.id} {e.desc}" + (f" → {', '.join(e.handler_methods) or ('인라인' if e.ranges else '')}" if e.handlers else "")
        + (" ⚠도달 불가" if e.unreachable else "")
        for e in ui.event_rows
    )


def trace_flow(target: str, ctx: TraceContext, event: str | None = None, class_name: str | None = None) -> TraceResult:
    res = TraceResult(
        command="trace-flow",
        description="이벤트 하나의 사슬: 이벤트 → 핸들러 → 서비스(RPC) → 서버 → SQL → 테이블",
        side=ctx.side,
        params={"screen_id": target, "event": event, "class": class_name},
    )
    res.unresolved += ctx.unresolved
    if wants_tobe(ctx.side):
        res.unresolved.append("TOBE 쪽 사슬(컨트롤러 → 서비스 → mapper)은 아직 지원하지 않음 (trace-pair 단계에서 추가)")
    if not ctx.has_index:
        return res

    screen = resolve_screen(target, ctx)
    res.params["resolved"] = screen
    doc_path = find_class_doc(ctx, screen)
    if doc_path is None:
        res.unresolved.append(f"색인 문서를 찾지 못함: {screen}.md")
        return res
    doc: ScreenDoc = parse_screen_doc(screen, doc_path.read_text(encoding="utf-8", errors="replace"))
    cls = class_name or screen
    ui = doc.ui.get(cls)
    if ui is None:
        res.unresolved.append(f"--class {cls}: 이 화면의 UI 절에 없는 클래스 (가능: {', '.join(doc.ui)})")
        return res
    res.params["class"] = cls

    if event is None:
        res.facts.append(f"이벤트 목록({cls}, {len(ui.event_rows)}) — `--event <En>`으로 사슬을 추적:\n{_event_summary(ui)}")
        res.evidence.append(f"색인 파일: {doc_path}")
        return res

    ev_id = normalize_event(event)
    ev = next((e for e in ui.event_rows if e.id == ev_id), None)
    if ev is None:
        others = [name for name, u in doc.ui.items() if any(e.id == ev_id for e in u.event_rows)]
        hint = f" ({ev_id}가 있는 클래스: {', '.join(others)} — --class로 지정)" if others else ""
        res.unresolved.append(f"{cls}에 이벤트 {ev_id}가 없음{hint}. 가능: {', '.join(e.id for e in ui.event_rows)}")
        return res

    res.facts.append(f"이벤트({cls}): [{ev.id}] {ev.desc}" + (f" — 조건 [{ev.guard}]" if ev.guard else ""))
    closure = handler_closure(ui, ev)
    methods = [m for m, _ in closure]
    via = {m.name: p for m, p in closure}
    if methods:
        res.facts.append(
            "핸들러 메서드:\n" + "\n".join(f"  - {m.signature} L{m.start}-{m.end} (호출처 {', '.join(m.callers)})" for m in methods)
        )
    if ev.ranges:
        res.facts.append("인라인·생성자 코드: " + ", ".join(f"L{a}-{b}" for a, b in ev.ranges))
    ranges = [(m.start, m.end) for m in methods] + ev.ranges
    if ev.unreachable:
        res.unresolved.append(f"이벤트 {ev.id}는 도달 불가로 표시됨: {ev.handlers.split('⚠')[-1].strip()}")
    if not ranges:
        res.unresolved.append(f"{ev.id}의 핸들러 코드 범위를 찾지 못함 — 메서드 표에 없는 핸들러")
        return res

    statements = _statements(ctx)
    if statements is None:
        res.unresolved.append("ASIS 소스(YUNHEE_ASIS_SRC_DIR)를 찾지 못해 SQL의 테이블을 해석하지 못함")
    tables: dict[str, set[str]] = {}
    chain: list[str] = []
    seen_svc: set[str] = set()
    for m in methods or [None]:
        scope = [(m.start, m.end)] if m else ev.ranges
        label = " → ".join([ev.id, *[f"{n}()" for n in via[m.name]], f"{m.name}()"]) if m else f"{ev.id} → 인라인"
        for svc in doc.services:
            lines = _calls_in(svc, cls, scope)
            if not lines or svc.key in seen_svc:
                continue
            seen_svc.add(svc.key)
            body = _chain_for_service(svc, statements, res, tables)
            chain.append(f"{label} (L{lines[0]}) " + body[0] + ("\n" + "\n".join(body[1:]) if len(body) > 1 else ""))
            res.evidence.append(f"{cls}:{lines[0]} 서비스 {svc.key} 호출 / 서버 {svc.server}")
    inline_only = [svc for svc in doc.services if svc.key not in seen_svc and _calls_in(svc, cls, ev.ranges)]
    for svc in inline_only:  # 메서드 없이 인라인 범위에서만 부르는 서비스
        seen_svc.add(svc.key)
        body = _chain_for_service(svc, statements, res, tables)
        chain.append(f"{ev.id} → 인라인 " + body[0] + ("\n" + "\n".join(body[1:]) if len(body) > 1 else ""))
        res.evidence.append(f"{cls} 인라인 서비스 {svc.key} / 서버 {svc.server}")
    if chain:
        res.facts.append(f"사슬({len(chain)}):\n" + "\n".join("  " + c.replace("\n", "\n  ") for c in chain))
    else:
        res.facts.append("이 이벤트의 핸들러 범위에서 서비스(RPC) 호출을 찾지 못함 — 화면 안에서 끝나는 동작이거나 다른 클래스로 이어짐")

    opened = sorted({n for m in methods for n in _OPENS.findall(m.does)})
    if opened:
        res.facts.append("이 이벤트가 여는 하위 화면: " + ", ".join(opened) + " (`--class <이름>`으로 이어서 추적)")
    if tables:
        by_op: dict[str, list[str]] = {}
        for name, ops in sorted(tables.items()):
            for op in sorted(ops):
                by_op.setdefault(op, []).append(name)
        res.facts.append("쓰는 테이블: " + " / ".join(f"{op}: {', '.join(v)}" for op, v in by_op.items()))
    for m in methods:
        res.evidence.append(f"{ui.java or doc.file}:{m.start}-{m.end} 메서드 {m.name}")
    res.evidence.append(f"색인 파일: {doc_path}")
    for call in doc.unresolved_calls:
        name, _, rest = call.strip("`").partition(":")
        ln = re.match(r"(\d+)", rest.strip("`"))
        if name == cls and ln and _in_ranges(int(ln.group(1)), ranges):
            res.unresolved.append(f"해석 못 한 서비스 호출 {call}")
    return res
