"""trace-gap: ASIS에만 있는 것, TOBE에만 있는 것, 추적하지 못한 지점 (도메인 단위 집계).

대응 판정은 trace-pair와 같은 근거를 쓴다: 화면은 같은 클래스명·TSX 헤더의 AS-IS, 서비스는 TOBE 주석의 AS-IS 서비스 키,
SQL은 TOBE 문장 주석의 AS-IS id. 근거가 없으면 "대응 없음"이 아니라 "추적하지 못함"으로 따로 센다.
"""

from __future__ import annotations

import re
from pathlib import Path

from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import TraceContext, load_menus
from yunhee.tools.trace.tobe import TobeIndex, build_index, find_layout

MAX_LISTED = 25


def _listing(label: str, items: list[str]) -> str:
    items = sorted(items)
    shown = "\n".join(f"  - {i}" for i in items[:MAX_LISTED])
    more = f"\n  … 외 {len(items) - MAX_LISTED}개" if len(items) > MAX_LISTED else ""
    return f"{label}({len(items)}):\n{shown}{more}" if items else f"{label}(0)"


def _tsx_domain(tsx_file: str, idx: TobeIndex) -> str:
    try:
        return Path(tsx_file).relative_to(idx.layout.pages_dir).parts[0]
    except (ValueError, IndexError):
        return ""


def _screen_gap(ctx: TraceContext, idx: TobeIndex, domain: str | None, res: TraceResult) -> None:
    index = ctx.index_data or {}
    src_index = ctx.src_index
    asis_screens: dict[str, str] = {}  # 화면 클래스 → 도메인
    if src_index:
        for p in src_index.glob("*/screens/*.md"):
            asis_screens[p.stem] = p.parent.parent.name
    asis_screens = {c: d for c, d in asis_screens.items() if not domain or d == domain}
    menu_no = {m.screen: m.no for m in load_menus(ctx) if m.screen}

    tobe_by_header = {Path(t.as_is_file).stem for t in idx.tsx.values() if t.as_is_file}
    a_only = [f"{c}" + (f" (#{menu_no[c]})" if c in menu_no else "") for c in asis_screens if c not in idx.tsx and c not in tobe_by_header]
    all_asis = set(index.get("client_classes", {})) | set(asis_screens)
    tobe_tsx = {n: t for n, t in idx.tsx.items() if not domain or _tsx_domain(t.file, idx) == domain}
    t_only = [n for n, t in tobe_tsx.items() if n not in all_asis and Path(t.as_is_file).stem not in all_asis]
    no_header = [n for n, t in tobe_tsx.items() if not t.as_is_file]
    covered = len(asis_screens) - len(a_only)
    res.facts.append(f"화면: ASIS {len(asis_screens)} / TOBE {len(tobe_tsx)} — TOBE에 대응 TSX가 있는 ASIS 화면 {covered}")
    res.facts.append(_listing("ASIS에만 있는 화면(TOBE에 같은 이름의 TSX도, 헤더 AS-IS도 없음)", a_only))
    res.facts.append(_listing("TOBE에만 있는 화면(ASIS 색인에 같은 이름의 클래스가 없음)", t_only))
    if no_header:
        res.unresolved.append(_listing("TSX 헤더에 AS-IS가 없어 ASIS 출처를 추적하지 못한 화면", no_header))


def _service_gap(ctx: TraceContext, idx: TobeIndex, domain: str | None, res: TraceResult) -> None:
    index = ctx.index_data or {}
    asis_keys: set[str] = set()
    for cls, info in index.get("server_classes", {}).items():
        for m in info.get("methods", []):
            if m.get("is_service"):
                asis_keys.add(f"{cls}.{m['name']}")
    asis_keys = {k for k in asis_keys if not domain or k.split(".")[0] == domain}
    tobe_keys = {k for ep in idx.endpoints for k in ep.keys} | {k for fn in idx.api_fns.values() for k in fn.keys}
    scoped_tobe = {k for k in tobe_keys if not domain or k.split(".")[0] == domain}
    res.facts.append(f"서비스(RPC): ASIS {len(asis_keys)} / TOBE 주석에 적힌 서비스 키 {len(scoped_tobe)} — 대응 {len(asis_keys & scoped_tobe)}")
    res.facts.append(_listing("ASIS에만 있는 서비스(TOBE 컨트롤러·api 주석에 이 서비스 키가 없음)", list(asis_keys - scoped_tobe)))
    res.facts.append(_listing("TOBE 주석에만 있는 서비스 키(ASIS 색인에 없음 — 오기·삭제된 서비스 가능)", list(scoped_tobe - asis_keys)))
    bare = [f"{ep.verb} {ep.path} ({ep.controller}.{ep.method})" for ep in idx.endpoints
            if not ep.keys and (not domain or ep.path.startswith(f"/api/v1/{domain}/"))]
    if bare:
        res.unresolved.append(_listing("AS-IS 서비스 키 주석이 없어 ASIS 출처를 추적하지 못한 TOBE 엔드포인트", bare))


def _sql_gap(ctx: TraceContext, idx: TobeIndex, domain: str | None, res: TraceResult) -> None:
    statements = (ctx.index_data or {}).get("statements", {})
    asis = {k for k, v in statements.items() if not domain or f"server/{domain}/" in v.get("file", "")}
    referenced = {i for st in idx.statements.values() for i in st.as_is_ids}
    scoped_ref = {i for i in referenced if i in statements}
    res.facts.append(f"SQL: ASIS {len(asis)} — TOBE 문장 주석이 가리키는 것 {len(asis & scoped_ref)}")
    res.facts.append(_listing("ASIS에만 있는 SQL(어느 TOBE 문장 주석도 가리키지 않음)", list(asis - scoped_ref)))
    dangling = [i for i in referenced if i not in statements and not i.startswith("common.")]
    if dangling:
        res.unresolved.append(_listing("TOBE 문장 주석이 가리키는데 ASIS 색인에 없는 SQL id", dangling))
    no_ref = [st.key.split(".")[-2] + "." + st.id for st in idx.statements.values()
              if not st.as_is_ids and (not domain or Path(st.file).name[: len(domain)].lower() == domain)]
    if no_ref:
        res.unresolved.append(_listing("AS-IS 주석이 없어 ASIS 출처를 추적하지 못한 TOBE mapper 문장", no_ref))


def _api_gap(idx: TobeIndex, domain: str | None, res: TraceResult) -> None:
    ep_keys = {(ep.verb, ep.path) for ep in idx.endpoints}
    dangling = []
    for t in idx.tsx.values():
        if domain and _tsx_domain(t.file, idx) != domain:
            continue
        for obj, fn in t.api_calls:
            api = idx.api_fns.get((obj, fn))
            if api is None:
                dangling.append(f"{t.name}: {obj}.{fn} (api/*.ts에서 찾지 못함)")
            elif (api.verb, api.url) not in ep_keys:
                dangling.append(f"{t.name}: {obj}.{fn} → {api.verb} {api.url} (컨트롤러에 없음)")
    if dangling:
        res.unresolved.append(_listing("TSX가 부르는 API가 컨트롤러까지 이어지지 않음", dangling))


def trace_gap(ctx: TraceContext, tobe: Path | None = None, domain: str | None = None) -> TraceResult:
    res = TraceResult(
        command="trace-gap",
        description="ASIS에만 있는 것, TOBE에만 있는 것, 추적하지 못한 지점 전체",
        side="both",
        params={"domain": domain},
    )
    res.unresolved += ctx.unresolved
    idx = build_index(str(find_layout(tobe).root))
    if not idx.layout.usable:
        res.unresolved.append(f"TOBE 소스를 찾지 못함 ({idx.layout.root}) — --tobe로 프로젝트 루트(또는 frontend/src)를 지정")
        return res
    if not ctx.has_index:
        return res
    if domain and not re.fullmatch(r"[a-z][a-z0-9]{1,5}", domain):
        raise ValueError(f"--domain은 소문자 도메인 코드여야 합니다 (예: emp, sys, fnd): {domain}")
    _screen_gap(ctx, idx, domain, res)
    _service_gap(ctx, idx, domain, res)
    _sql_gap(ctx, idx, domain, res)
    _api_gap(idx, domain, res)
    res.evidence.append(f"TOBE 색인: TSX {len(idx.tsx)}, api 함수 {len(idx.api_fns)}, 엔드포인트 {len(idx.endpoints)}, mapper 문장 {len(idx.statements)} ({idx.layout.root})")
    return res
