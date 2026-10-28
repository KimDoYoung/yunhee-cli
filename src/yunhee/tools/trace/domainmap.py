"""trace-map: 업무 영역별 화면 수, 테이블 수, ASIS↔TOBE 매핑 상태 요약.

ASIS는 색인(화면·컴포넌트·서비스·SQL)과 스키마 스냅샷(테이블 접두사), TOBE는 TSX·컨트롤러·mapper 소스를 센다.
화면이 이식됐는지는 같은 클래스명의 TSX가 있거나 TSX 헤더의 AS-IS가 그 클래스를 가리키는지로 본다 (trace-pair와 같은 기준).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from yunhee import config
from yunhee.tools.schema_snapshot import load_snapshot
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import TargetNotFoundError, TraceContext, load_menus
from yunhee.tools.trace.tobe import TobeIndex, build_index, find_layout

MAX_LISTED = 15


@dataclass
class DomainStats:
    code: str
    label: str = ""
    screens: list[str] = field(default_factory=list)
    components: int = 0
    services: int = 0
    sql: int = 0
    tables: int = 0
    tobe_tsx: int = 0
    ported: list[str] = field(default_factory=list)
    endpoints: int = 0
    tobe_stmts: int = 0


def _label(domain_screens: list[str], menus_by_screen: dict[str, list[str]]) -> str:
    """영역의 대표 메뉴 이름: 그 영역 화면들이 가장 많이 속한 최상위 메뉴."""
    top = Counter(m.split(" > ")[0] for s in domain_screens for m in menus_by_screen.get(s, []))
    return top.most_common(1)[0][0] if top else ""


def compute(ctx: TraceContext, idx: TobeIndex | None, schema_env: str | None = None) -> dict[str, DomainStats]:
    src = ctx.src_index
    stats: dict[str, DomainStats] = {}
    if src is None:
        return stats
    for p in sorted(src.glob("*/screens/*.md")):
        stats.setdefault(p.parent.parent.name, DomainStats(p.parent.parent.name)).screens.append(p.stem)
    for p in src.glob("*/components/*.md"):
        stats.setdefault(p.parent.parent.name, DomainStats(p.parent.parent.name)).components += 1

    menus_by_screen: dict[str, list[str]] = defaultdict(list)
    for m in load_menus(ctx):
        if m.screen:
            menus_by_screen[m.screen].append(m.path)
    data = ctx.index_data or {}
    for key, info in data.get("server_classes", {}).items():
        d = stats.setdefault(key.split(".")[0], DomainStats(key.split(".")[0]))
        d.services += sum(1 for m in info.get("methods", []) if m.get("is_service"))
    for info in data.get("statements", {}).values():
        parts = info.get("file", "").split("/")
        if len(parts) > 2 and parts[0] == "server":
            stats.setdefault(parts[1], DomainStats(parts[1])).sql += 1

    snap = load_snapshot(schema_env or config.SCHEMA_ENV)
    if snap.ok:
        for t in snap.data.get("tables", []):
            m = re.match(r"([a-z]+)\d", t["name"])
            if m and m.group(1) in stats:
                stats[m.group(1)].tables += 1

    for d in stats.values():
        d.label = _label(d.screens, menus_by_screen)
    if idx is not None:
        headers = {Path(t.as_is_file).stem for t in idx.tsx.values() if t.as_is_file}
        for d in stats.values():
            d.ported = [s for s in d.screens if s in idx.tsx or s in headers]
        for t in idx.tsx.values():
            try:
                dom = Path(t.file).relative_to(idx.layout.pages_dir).parts[0]
            except (ValueError, IndexError):
                continue
            stats.setdefault(dom, DomainStats(dom)).tobe_tsx += 1
        for ep in idx.endpoints:
            m = re.match(r"/api/v1/([a-z0-9]+)/", ep.path)
            if m:
                stats.setdefault(m.group(1), DomainStats(m.group(1))).endpoints += 1
        for code, d in stats.items():
            d.tobe_stmts = sum(1 for st in idx.statements.values() if Path(st.file).name[: len(code)].lower() == code)
    # pages/ 바로 아래 파일(LoginPage.tsx)이나 도메인이 없는 서버 클래스는 업무 영역이 아니다
    return {code: d for code, d in stats.items() if re.fullmatch(r"_?[a-z][a-z0-9]{1,5}", code)}


def _line(d: DomainStats, with_tobe: bool) -> str:
    label = f" ({d.label})" if d.label else ""
    asis = f"ASIS 화면 {len(d.screens)}, 컴포넌트 {d.components}, 서비스 {d.services}, SQL {d.sql}, 테이블 {d.tables}"
    if not with_tobe:
        return f"{d.code}{label}: {asis}"
    pct = f" ({len(d.ported) * 100 // len(d.screens)}%)" if d.screens else ""
    return f"{d.code}{label}: {asis} | TOBE 이식 {len(d.ported)}/{len(d.screens)}{pct}, TSX {d.tobe_tsx}, 엔드포인트 {d.endpoints}, mapper 문장 {d.tobe_stmts}"


def trace_map(ctx: TraceContext, tobe: Path | None = None, domain: str | None = None) -> TraceResult:
    res = TraceResult(
        command="trace-map",
        description="업무 영역별 화면 수, 테이블 수, ASIS↔TOBE 매핑 상태 요약",
        side=ctx.side,
        params={"domain": domain},
    )
    res.unresolved += ctx.unresolved
    if not ctx.has_index:
        return res
    layout = find_layout(tobe)
    idx = build_index(str(layout.root)) if layout.usable else None
    if idx is None:
        res.unresolved.append(f"TOBE 소스를 찾지 못해 ASIS만 낸다 ({layout.root}) — --tobe로 지정")
    stats = compute(ctx, idx)
    if domain:
        if domain not in stats:
            raise TargetNotFoundError(domain, sorted(stats)[:12])
        d = stats[domain]
        res.facts.append(_line(d, idx is not None))
        if idx is not None and d.screens:
            todo = [s for s in d.screens if s not in d.ported]
            res.facts.append(f"아직 TOBE에 없는 화면({len(todo)}): " + ", ".join(todo[:MAX_LISTED]) + (" …" if len(todo) > MAX_LISTED else ""))
        res.facts.append(f"다음 단계: `trace-gap --domain {domain}`(빠진 것), `trace-crud --domain {domain}`(테이블 작업), `trace-doc {domain}`(문서 골격)")
    else:
        rows = sorted(stats.values(), key=lambda d: (-len(d.screens), d.code))
        res.facts.append(f"업무 영역 {len(rows)}개 (화면 수 순)")
        res.facts += [_line(d, idx is not None) for d in rows]
        if idx is not None:
            tot_s, tot_p = sum(len(d.screens) for d in rows), sum(len(d.ported) for d in rows)
            res.facts.insert(1, f"전체: ASIS 화면 {tot_s}, TOBE 이식 {tot_p}" + (f" ({tot_p * 100 // tot_s}%)" if tot_s else ""))
    res.evidence.append(f"ASIS 색인: {ctx.src_index}")
    if idx is not None:
        res.evidence.append(f"TOBE 소스: {layout.root} (TSX {len(idx.tsx)}, 엔드포인트 {len(idx.endpoints)}, mapper 문장 {len(idx.statements)})")
    res.unresolved.append("테이블 수는 테이블 이름 접두사(영문 약어+숫자)가 영역 코드와 같은 것만 센다 — 접두사가 다른 공용·백업 테이블은 빠진다")
    return res
