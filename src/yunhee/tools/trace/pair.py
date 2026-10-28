"""trace-pair: ASIS↔TOBE 짝지어진 항목과 매칭 근거.

짝은 TOBE 소스에 적힌 `AS-IS` 주석(서비스 키, SQL id, TSX 헤더)과 같은 이름·같은 테이블 조합을 근거로 짓고,
항목마다 **어떤 근거인지** 함께 낸다. 근거가 약한 짝(테이블 조합만 같음)은 따로 표시하고, 짝이 없으면 없다고 낸다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import TraceContext, find_class_doc, resolve_screen
from yunhee.tools.trace.screen import ScreenDoc, ServiceRow, parse_screen_doc
from yunhee.tools.trace.tobe import (
    ApiFn,
    Endpoint,
    MapperStatement,
    TobeIndex,
    TsxInfo,
    build_index,
    find_layout,
)

BUSINESS_SKIP = ("dbConfig.",)  # 채번·암호화 같은 공통 SQL은 짝짓기 대상이 아니다


@dataclass
class ServicePair:
    service: ServiceRow
    endpoints: list[Endpoint] = field(default_factory=list)
    via: list[str] = field(default_factory=list)  # 근거
    tsx_calls: list[str] = field(default_factory=list)  # "Emp00_Tab_TransInfo ← empApi.searchTransInfos"


def tobe_statements(idx: TobeIndex) -> dict[str, Any]:
    """TOBE mapper XML 전체를 mybatis_render 형식으로 로드한다 (SQL 해석용)."""
    from yunhee.tools.as_is.mybatis_render import load_statements

    return load_statements(idx.layout.mapper_dir) if idx.layout.mapper_dir.is_dir() else {}


def asis_statements(ctx: TraceContext) -> dict[str, Any] | None:
    if not ctx.src_root or not Path(ctx.src_root).is_dir():
        return None
    from yunhee.tools.as_is.mybatis_render import get_all_statements

    return get_all_statements(Path(ctx.src_root)) or None


def tables_of(key: str, statements: dict[str, Any] | None) -> list[str] | None:
    if not statements:
        return None
    from yunhee.tools.sql_parse import parse_statement

    res = parse_statement(key, statements)
    return list(res.data.tables) if res.ok else None


def load_asis_screen(target: str, ctx: TraceContext) -> tuple[str, ScreenDoc | None, Path | None]:
    name = resolve_screen(target, ctx)
    path = find_class_doc(ctx, name)
    doc = parse_screen_doc(name, path.read_text(encoding="utf-8", errors="replace")) if path else None
    return name, doc, path


def screen_tsx(idx: TobeIndex, name: str, doc: ScreenDoc | None) -> tuple[list[TsxInfo], list[str]]:
    """ASIS 화면과 하위 클래스에 대응하는 TOBE TSX들과 그 근거."""
    names = [name] + [c for c in (doc.ui if doc else {}) if c != name]
    found: list[TsxInfo] = []
    notes: list[str] = []
    for cls in names:
        tsx = idx.tsx.get(cls)
        basis = "같은 클래스명"
        if tsx is None:  # 이름이 바뀐 경우: TSX 헤더의 AS-IS가 이 클래스를 가리키는지
            tsx = next((t for t in idx.tsx.values() if t.as_is_file.endswith(f"/{cls}.java")), None)
            basis = "TSX 헤더 AS-IS가 이 클래스를 가리킴"
        if tsx is None:
            continue
        found.append(tsx)
        extra = []
        if tsx.as_is_file.endswith(f"/{cls}.java"):
            extra.append("TSX 헤더 AS-IS 일치")
        if cls == name and doc and doc.menus and tsx.header_menu_nos:
            asis_nos = set(re.findall(r"#(\d+)", " ".join(doc.menus)))
            both = sorted(asis_nos & set(tsx.header_menu_nos))
            if both:
                extra.append("메뉴 번호 일치 " + ",".join(f"#{n}" for n in both))
            else:
                notes.append(f"메뉴 번호 불일치: ASIS {sorted(asis_nos)} / TOBE 헤더 {tsx.header_menu_nos}")
        notes.append(f"{cls} ↔ {idx.rel(tsx.file)} (근거: {basis}{'; ' + '; '.join(extra) if extra else ''})")
    return found, notes


def pair_services(doc: ScreenDoc, idx: TobeIndex, tsx_list: list[TsxInfo]) -> tuple[list[ServicePair], list[tuple[Endpoint, str]]]:
    """ASIS 서비스 ↔ TOBE 엔드포인트. 두 번째 값은 TOBE 화면이 부르지만 짝이 없는 엔드포인트."""
    # api 함수의 주석에 적힌 서비스 키 → api 함수
    fn_by_key: dict[str, list[ApiFn]] = {}
    for fn in idx.api_fns.values():
        for k in fn.keys:
            fn_by_key.setdefault(k, []).append(fn)
    called: dict[tuple[str, str], list[str]] = {}
    for t in tsx_list:
        for obj, fn in t.api_calls:
            called.setdefault((obj, fn), []).append(t.name)

    pairs: list[ServicePair] = []
    matched_eps: set[int] = set()
    for svc in doc.services:
        sp = ServicePair(svc)
        eps = idx.endpoints_for_key(svc.key)
        if eps:
            sp.via.append("컨트롤러 주석의 AS-IS 서비스 키")
        for fn in fn_by_key.get(svc.key, []):
            for ep in idx.endpoint_of(fn):
                if ep not in eps:
                    eps.append(ep)
                    sp.via.append("api 함수 주석의 AS-IS 서비스 키")
        sp.endpoints = eps
        for ep in eps:
            matched_eps.add(id(ep))
        for fn in list(idx.api_fns.values()):
            if any(ep in idx.endpoint_of(fn) for ep in eps) and (fn.obj, fn.name) in called:
                for owner in called[(fn.obj, fn.name)]:
                    sp.tsx_calls.append(f"{owner}({fn.obj}.{fn.name})")
        pairs.append(sp)

    tobe_only: list[tuple[Endpoint, str]] = []
    for (obj, name), owners in called.items():
        fn = idx.api_fns.get((obj, name))
        if fn is None:
            continue
        for ep in idx.endpoint_of(fn):
            if id(ep) not in matched_eps:
                tobe_only.append((ep, f"{owners[0]}({obj}.{name})"))
    return pairs, list({id(e): (e, w) for e, w in tobe_only}.values())


def pair_sql(sql_id: str, idx: TobeIndex, reached: list[MapperStatement], asis_tables: list[str] | None, tobe_stmts: dict[str, Any]) -> tuple[list[MapperStatement], str]:
    """ASIS SQL id에 대응하는 TOBE 문장과 근거. 근거 순서: 문장 주석의 AS-IS id → 테이블 조합이 같음(약함)."""
    by_comment = [s for s in idx.statements.values() if sql_id in s.as_is_ids]
    in_chain = [s for s in by_comment if s.key in {r.key for r in reached}]
    if in_chain:
        return in_chain, "문장 주석의 AS-IS id"
    if by_comment:  # 같은 ASIS SQL을 다른 화면 쪽에서 이식한 경우
        return by_comment, "문장 주석의 AS-IS id — 이 화면의 API 체인 밖 문장"
    if asis_tables:
        same = [s for s in reached if sorted(tables_of(s.key, tobe_stmts) or []) == sorted(asis_tables)]
        if len(same) == 1:
            return same, "테이블 조합이 같음 (약한 근거)"
    return [], ""


def compute_sql_pairs(
    pairs: list[ServicePair], idx: TobeIndex, reached: list[MapperStatement], a_stmts: dict[str, Any] | None, t_stmts: dict[str, Any]
) -> tuple[list[tuple[str, list[MapperStatement], str]], list[str]]:
    """짝지어진 서비스의 ASIS SQL id마다 TOBE 문장을 찾는다. 반환: ([(SQL id, 문장들, 근거)], 짝이 없는 SQL id)."""
    matches: list[tuple[str, list[MapperStatement], str]] = []
    unmatched: list[str] = []
    seen: set[str] = set()
    for p in pairs:
        for sql_id in p.service.sql_ids:
            if sql_id in seen or sql_id.startswith(BUSINESS_SKIP):
                continue
            seen.add(sql_id)
            found, basis = pair_sql(sql_id, idx, reached, tables_of(sql_id, a_stmts), t_stmts)
            if found:
                matches.append((sql_id, found, basis))
            else:
                unmatched.append(sql_id)
    return matches, unmatched


def reached_statements(pairs: list[ServicePair], idx: TobeIndex) -> list[MapperStatement]:
    """짝지어진 엔드포인트가 서비스를 거쳐 닿는 TOBE mapper 문장들."""
    out: list[MapperStatement] = []
    for p in pairs:
        for ep in p.endpoints:
            out += idx.statements_of(ep)
    return list({s.key: s for s in out}.values())


def trace_pair(target: str, ctx: TraceContext, tobe: Path | None = None) -> TraceResult:
    res = TraceResult(
        command="trace-pair",
        description="ASIS↔TOBE 짝지어진 항목과 매칭 근거 (AS-IS 주석, 같은 테이블 조합, 같은 이름)",
        side="both",
        params={"screen_id": target},
    )
    res.unresolved += ctx.unresolved
    if not ctx.has_index:
        return res
    idx = build_index(str(find_layout(tobe).root))
    if not idx.layout.usable:
        res.unresolved.append(f"TOBE 소스를 찾지 못함 ({idx.layout.root}) — --tobe로 프로젝트 루트(또는 frontend/src)를 지정")
        return res

    name, doc, _ = load_asis_screen(target, ctx)
    res.params["resolved"] = name
    if doc is None:
        res.unresolved.append(f"ASIS 색인 문서를 찾지 못함: {name}.md")
        return res

    tsx_list, notes = screen_tsx(idx, name, doc)
    if tsx_list:
        res.facts.append(f"화면 짝({len(tsx_list)}/{len(doc.ui) or 1}):\n" + "\n".join(f"  - {n}" for n in notes if "↔" in n))
        res.unresolved += [n for n in notes if "↔" not in n]
        res.evidence += [f"TOBE {idx.rel(t.file)}" for t in tsx_list]
    else:
        res.facts.append(f"화면 짝: 없음 ⚠ — TOBE에 {name}.tsx가 없고, TSX 헤더의 AS-IS도 이 클래스를 가리키지 않음")

    pairs, tobe_only = pair_services(doc, idx, tsx_list)
    done = [p for p in pairs if p.endpoints]
    lines = []
    for p in done:
        for ep in p.endpoints:
            who = f" — TOBE 호출: {', '.join(dict.fromkeys(p.tsx_calls))}" if p.tsx_calls else ""
            lines.append(f"  - {p.service.key} ↔ {ep.verb} {ep.path} ({ep.controller}.{ep.method}){who} [근거: {'; '.join(dict.fromkeys(p.via))}]")
            res.evidence.append(f"TOBE {idx.rel(ep.file)}:{ep.line} {ep.controller}.{ep.method}")
    res.facts.append(f"서비스(RPC) ↔ API 짝({len(done)}/{len(pairs)}):\n" + ("\n".join(lines) if lines else "  (짝 없음)"))
    missing = [p for p in pairs if not p.endpoints]
    if missing:
        res.facts.append(
            f"ASIS에만 있음 — TOBE에 대응 API 없음({len(missing)}):\n"
            + "\n".join(f"  - {p.service.key} (호출 {', '.join(p.service.callers[:3])})" for p in missing)
        )
    if tobe_only:
        res.facts.append(
            f"TOBE에만 있음 — 화면이 부르는데 이 ASIS 화면의 서비스와 짝이 없는 API({len(tobe_only)}):\n"
            + "\n".join(f"  - {ep.verb} {ep.path} ({ep.controller}.{ep.method}) — TOBE 호출: {who}" + (f" [AS-IS 주석: {', '.join(ep.keys)}]" if ep.keys else " [AS-IS 주석 없음]") for ep, who in tobe_only)
        )

    # SQL 짝
    a_stmts, t_stmts = asis_statements(ctx), tobe_statements(idx)
    reached = reached_statements(done, idx)
    matches, unmatched_sql = compute_sql_pairs(pairs, idx, reached, a_stmts, t_stmts)
    sql_lines: list[str] = []
    for sql_id, found, basis in matches:
        for st in found:
            sql_lines.append(f"  - {sql_id} ↔ {st.key.split('.')[-2]}.{st.id} [근거: {basis}]")
            res.evidence.append(f"TOBE {idx.rel(st.file)}:{st.line} {st.id}")
    res.facts.append(f"SQL ↔ mapper 문장 짝({len(sql_lines)}):\n" + ("\n".join(sql_lines) if sql_lines else "  (짝 없음)"))
    if unmatched_sql:
        res.facts.append(f"ASIS에만 있음 — TOBE 문장 주석에 AS-IS id가 없는 SQL({len(unmatched_sql)}): " + ", ".join(unmatched_sql[:15]) + (" …" if len(unmatched_sql) > 15 else ""))

    # 테이블 비교
    asis_t = set(doc.tables)
    tobe_t: set[str] = set()
    for st in reached:
        tobe_t.update(tables_of(st.key, t_stmts) or [])
    same, a_only, t_only = sorted(asis_t & tobe_t), sorted(asis_t - tobe_t), sorted(tobe_t - asis_t)
    res.facts.append(
        f"테이블 비교: 같음 {len(same)} / ASIS만 {len(a_only)} / TOBE만 {len(t_only)}"
        + (f"\n  ASIS에만: {', '.join(a_only[:20])}" if a_only else "")
        + (f"\n  TOBE에만: {', '.join(t_only[:20])}" if t_only else "")
    )
    if a_stmts is None:
        res.unresolved.append("ASIS 소스를 찾지 못해 ASIS SQL의 테이블 조합 기반 짝(약한 근거)은 건너뜀")
    if len(reached) == 0 and done:
        res.unresolved.append("짝지어진 TOBE 엔드포인트에서 mapper 문장까지 이어지지 않음 (서비스·mapper 호출을 찾지 못함)")
    return res
