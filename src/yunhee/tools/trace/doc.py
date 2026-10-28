"""trace-doc: 카탈로그(trace-rule)와 팩트를 신규 인원용 문서 골격으로 조립한다.

서술은 에이전트의 몫이다. 이 명령은 표와 목록(사실)을 채우고, 사람이 읽을 설명이 들어갈 자리에는
`<!-- 서술(에이전트): … -->` 표지를 남긴다. 표지를 채운 뒤 `trace-rule verify`로 근거가 유효한지 다시 확인할 수 있다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

from yunhee import config
from yunhee.store import trace_rules as store
from yunhee.tools.schema_snapshot import load_snapshot
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import TargetNotFoundError, TraceContext, load_menus
from yunhee.tools.trace.screen import ScreenDoc, parse_screen_doc
from yunhee.tools.trace.tobe import build_index, find_layout

MAX_TABLE_ROWS = 60
_SLOT = "<!-- 서술(에이전트): {} -->"


def _cell(text: str) -> str:
    return re.sub(r"\s+", " ", text).replace("|", "\\|").strip()


def _table(header: list[str], rows: list[list[str]], limit: int = MAX_TABLE_ROWS) -> str:
    body = [f"| {' | '.join(_cell(c) for c in r)} |" for r in rows[:limit]]
    if len(rows) > limit:
        body.append(f"| … 외 {len(rows) - limit}행 |" + " |" * (len(header) - 1))
    return "\n".join([f"| {' | '.join(header)} |", "|" + ":---|" * len(header), *body]) if rows else "(없음)"


def _domain_screens(ctx: TraceContext, domain: str) -> list[tuple[str, ScreenDoc]]:
    out = []
    if ctx.src_index:
        for p in sorted((ctx.src_index / domain / "screens").glob("*.md")):
            out.append((p.stem, parse_screen_doc(p.stem, p.read_text(encoding="utf-8", errors="replace"))))
    return out


def _domain_rules(domain: str, classes: set[str], menu_nos: set[str]) -> list[store.Rule]:
    mine = []
    for r in store.list_rules():
        t = r.target.strip().lower()
        if t.startswith(domain) or r.target in classes or t.lstrip("#") in menu_nos or any(r.target.startswith(c) for c in classes):
            mine.append(r)
    return mine


def trace_doc(domain: str, ctx: TraceContext, tobe: Path | None = None, schema_env: str | None = None) -> TraceResult:
    if not re.fullmatch(r"[a-z][a-z0-9]{1,5}", domain):
        raise ValueError(f"업무 영역은 소문자 도메인 코드여야 합니다 (예: emp, sys, fnd): {domain}")
    res = TraceResult(
        command="trace-doc",
        description="카탈로그와 팩트를 신규 인원용 문서 골격으로 조립 (서술은 에이전트)",
        side=ctx.side,
        options={"document": True},
        params={"domain": domain},
    )
    res.unresolved += ctx.unresolved
    if not ctx.has_index or not ctx.src_index:
        return res
    screens = _domain_screens(ctx, domain)
    if not screens:
        known = sorted(p.name for p in ctx.src_index.iterdir() if (p / "screens").is_dir())
        raise TargetNotFoundError(domain, known[:12])

    menus: dict[str, list[str]] = defaultdict(list)
    for m in load_menus(ctx):
        if m.screen:
            menus[m.screen].append(f"{m.path} (#{m.no})")
    menu_nos = {n for names in menus.values() for n in re.findall(r"#(\d+)", " ".join(names))}
    classes = {name for name, _ in screens}

    layout = find_layout(tobe)
    tobe_idx = build_index(str(layout.root)) if layout.usable else None
    if tobe_idx is None:
        res.unresolved.append(f"TOBE 소스를 찾지 못해 이식 현황을 건너뜀 ({layout.root}) — --tobe로 지정")
    snap = load_snapshot(schema_env or config.SCHEMA_ENV)
    notes = {t["name"].lower(): t.get("note") or "" for t in snap.data.get("tables", [])} if snap.ok else {}
    if not snap.ok:
        res.unresolved.append("스키마 스냅샷을 읽지 못해 테이블 설명을 채우지 못함")

    rules = _domain_rules(domain, {c.lower() for c in classes} | classes, menu_nos)
    src = (ctx.index_data or {}).get("src_root", "")
    sections: list[str] = []

    sections.append(
        f"# {domain} 업무 영역 — 신규 인원용 개요\n\n"
        f"> 이 문서는 `yunhee trace-doc {domain}`이 {datetime.now(UTC).date().isoformat()}에 만든 **골격**이다. 표는 사실이고, `서술(에이전트)` 표지는 사람이 읽을 설명으로 채운다.\n\n"
        + _SLOT.format("이 영역이 회사 업무에서 맡는 역할과 주요 사용자를 3~5문장으로. 근거는 아래 화면·규칙 표에서 고른다")
    )

    ported = [n for n, _ in screens if tobe_idx and n in tobe_idx.tsx]
    rows = []
    for name, doc in screens:
        status = "—" if tobe_idx is None else ("이식됨" if name in tobe_idx.tsx else "미이식")
        rows.append([", ".join(menus.get(name, ["(메뉴 없음)"])), name, status, str(len(doc.services)), ", ".join(doc.tables[:4]) + (" …" if len(doc.tables) > 4 else "")])
    sections.append(
        f"## 1. 화면\n\n화면 {len(screens)}개" + (f", TOBE로 이식된 화면 {len(ported)}개" if tobe_idx else "") + "\n\n"
        + _table(["메뉴(번호)", "화면", "TOBE", "서비스 수", "주요 테이블"], rows)
        + "\n\n" + _SLOT.format("화면들을 업무 흐름 순서로 묶어 소개 (예: 조회 → 등록 → 승인). 화면 사이의 선후 관계를 적는다")
    )

    usage: dict[str, int] = defaultdict(int)
    for _, doc in screens:
        for t in doc.tables:
            usage[t] += 1
    trows = [[t, notes.get(t, "") or "(설명 없음)", str(n)] for t, n in sorted(usage.items(), key=lambda kv: (-kv[1], kv[0]))]
    sections.append(
        f"## 2. 테이블\n\n이 영역의 화면이 쓰는 테이블 {len(trows)}개 (사용 화면 수 순)\n\n"
        + _table(["테이블", "설명", "사용 화면 수"], trows)
        + "\n\n" + _SLOT.format("핵심 테이블 3~5개의 관계(누가 누구를 참조하는가)와 상태 컬럼의 의미. 상태 컬럼은 `trace-state <테이블.컬럼>`으로 확인")
    )

    services: dict[str, set[str]] = defaultdict(set)
    for name, doc in screens:
        for svc in doc.services:
            services[svc.key].add(name)
    srows = [[k, ", ".join(sorted(v)[:3]) + (" …" if len(v) > 3 else "")] for k, v in sorted(services.items())]
    sections.append(
        f"## 3. 서비스(RPC)\n\n서비스 {len(srows)}개\n\n" + _table(["서비스", "쓰는 화면"], srows)
        + "\n\n" + _SLOT.format("조회/등록/수정/삭제로 나눠 업무 규칙이 걸린 서비스를 골라 설명. 분기는 `trace-branch`, 호출 사슬은 `trace-flow`로 확인")
    )

    if rules:
        rrows = [[r.rule_id, r.target, r.verdict, r.note, "; ".join(e.ref for e in r.evidence[:3])] for r in rules]
        body = _table(["ID", "대상", "판정", "사유", "근거"], rrows)
    else:
        body = "(저장된 규칙 없음 — `trace-rule add`로 판정을 남기면 여기에 모인다)"
    sections.append(
        f"## 4. 규칙 카탈로그\n\n이 영역과 관련된 규칙 {len(rules)}건 (프로젝트 {store.project_name()})\n\n{body}\n\n"
        + _SLOT.format("판정이 '변경'·'의도적 변경'인 규칙을 업무 언어로 풀어 쓴다. 근거가 깨졌는지 `trace-rule verify`로 먼저 확인")
    )

    if tobe_idx:
        miss = [n for n, _ in screens if n not in tobe_idx.tsx]
        sections.append(
            f"## 5. ASIS↔TOBE 대응 현황\n\n- 화면: ASIS {len(screens)} / TOBE 이식 {len(ported)}\n"
            + (f"- 아직 TOBE에 없는 화면: {', '.join(miss[:20])}{' …' if len(miss) > 20 else ''}\n" if miss else "- 모든 화면이 TOBE에 있음\n")
            + "- 상세: `yunhee trace-gap --domain " + domain + "`, 화면별 짝: `yunhee trace-pair <화면>`\n\n"
            + _SLOT.format("이식 우선순위와 남은 위험을 한 문단으로")
        )

    sections.append("## 6. 채워야 할 서술\n\n" + "\n".join(f"- [ ] {t}" for t in (
        "영역 개요 (1절 위)", "화면 흐름 (1절 아래)", "테이블 관계와 상태 컬럼 (2절)", "핵심 서비스 설명 (3절)", "규칙 풀이 (4절)", "이식 우선순위 (5절)")))

    res.facts = sections
    res.evidence += [f"ASIS 색인: {ctx.src_index} ({len(screens)}개 화면)", f"ASIS 소스: {src}"]
    if snap.ok:
        res.evidence.append(f"스키마 스냅샷: {schema_env or config.SCHEMA_ENV} ({snap.data.get('generated_at', '?')})")
    if tobe_idx:
        res.evidence.append(f"TOBE 소스: {layout.root}")
    return res
