"""trace-term: 용어 교차 참조 — 화면 라벨 ↔ DB 컬럼(코멘트) ↔ 공통 코드명.

같은 업무 용어가 화면에서는 라벨('성명'), DB에서는 컬럼(`emp01_kor_nm`, 코멘트 '한글성명'), 코드에서는 이름('국가코드')으로
다르게 쓰인다. 용어가 들어 있는 곳을 세 쪽에서 모으고, 화면 라벨의 속성 이름(`korNm`)이 컬럼명에서 만든 속성 이름과 같으면
라벨 ↔ 컬럼을 이어서 보여 준다 (그 규칙으로 이은 것임을 근거에 밝힌다).
"""

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

from yunhee import config
from yunhee.tools.as_is.events import col_to_tobe_prop
from yunhee.tools.schema_snapshot import load_snapshot
from yunhee.tools.trace import db
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import TraceContext, wants_asis, wants_tobe
from yunhee.tools.trace.table import BACKUP_TABLE
from yunhee.tools.trace.tobe import build_index, find_layout

MAX_HITS = 12
MAX_LINKED = 3  # 속성 이름 하나에 이만큼 이하의 컬럼이 대응할 때만 이어서 보여 준다 (그보다 많으면 이름이 너무 흔하다)
_GRID = re.compile(r"gb\.\w+\(\s*'([^']+)'\s*,\s*[^,]+,\s*'([^']*)'")
_BUTTON = re.compile(r"<Button\b[^>]*>\s*([^<{][^<]*?)\s*</Button>")


def _shown(items: list[str], limit: int = MAX_HITS) -> str:
    return ", ".join(items[:limit]) + (f" … 외 {len(items) - limit}개" if len(items) > limit else "")


def asis_labels(src_index: Path, term: str) -> dict[str, list[tuple[str, str]]]:
    """ASIS 색인 화면 문서의 라벨 중 term이 들어간 것: {라벨: [(화면, 속성 이름 또는 '')]}. 그리드(Grid Spec)와 버튼."""
    low = term.lower()
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for path in sorted(src_index.glob("*/screens/*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        if low not in text.lower():
            continue
        for prop, label in _GRID.findall(text):
            if low in label.lower():
                out[label].append((path.stem, prop))
        for label in _BUTTON.findall(text):
            if low in label.lower():
                out[label.strip()].append((path.stem, ""))
    return {k: list(dict.fromkeys(v)) for k, v in out.items()}


def trace_term(term: str | None, ctx: TraceContext, tobe: Path | None = None, schema_env: str | None = None) -> TraceResult:
    res = TraceResult(
        command="trace-term",
        description="용어 교차 참조: 화면 라벨 ↔ 컬럼 ↔ 코드명",
        side=ctx.side,
        params={"term": term},
    )
    res.unresolved += ctx.unresolved
    if not term or not term.strip():
        res.facts.append("용어를 지정하세요 — 예: `trace-term 성명`, `trace-term 결재` (화면 라벨·컬럼 코멘트·공통 코드명에서 찾는다)")
        return res
    term = term.strip()
    low = term.lower()

    snap = load_snapshot(schema_env or config.SCHEMA_ENV)
    cols: list[tuple[str, str, str]] = []  # (테이블, 컬럼, 코멘트)
    tables: list[tuple[str, str]] = []
    prop_to_cols: dict[str, list[str]] = defaultdict(list)
    skipped_backup = 0
    if snap.ok:
        for t in snap.data.get("tables", []):
            if BACKUP_TABLE.search(t["name"]) or re.search(r"_?bak\d*_", t["name"]):
                skipped_backup += 1
                continue
            if low in (t.get("note") or "").lower() or low in t["name"].lower():
                tables.append((t["name"], t.get("note") or ""))
            for c in t.get("columns", []):
                prop_to_cols[col_to_tobe_prop(c["name"])].append(f"{t['name']}.{c['name']}")
                if low in (c.get("note") or "").lower() or low in c["name"].lower():
                    cols.append((t["name"], c["name"], c.get("note") or ""))
        res.evidence.append(f"스키마 스냅샷: {schema_env or config.SCHEMA_ENV} ({snap.data.get('generated_at', '?')})")
        if skipped_backup:
            res.unresolved.append(f"백업·임시 테이블 {skipped_backup}개는 컬럼 검색에서 뺐다")
    else:
        res.unresolved.append("스키마 스냅샷을 읽지 못해 컬럼·테이블 코멘트는 건너뜀")

    labels: dict[str, list[tuple[str, str]]] = {}
    if wants_asis(ctx.side) and ctx.src_index:
        labels = asis_labels(ctx.src_index, term)
    tobe_labels: dict[str, list[tuple[str, str]]] = defaultdict(list)
    if wants_tobe(ctx.side):
        layout = find_layout(tobe)
        if layout.usable:
            for t in build_index(str(layout.root)).tsx.values():
                for prop, label in t.grid_cols:
                    if low in label.lower():
                        tobe_labels[label].append((t.name, prop))
                for label in t.buttons:
                    if low in label.lower():
                        tobe_labels[label].append((t.name, ""))
        else:
            res.unresolved.append(f"TOBE 소스를 찾지 못해 TOBE 라벨은 건너뜀 ({layout.root}) — --tobe로 지정")

    res.facts.append(f"용어 '{term}': 컬럼 {len(cols)}, 테이블 {len(tables)}, ASIS 라벨 {len(labels)}종, TOBE 라벨 {len(tobe_labels)}종")
    if cols:
        res.facts.append(f"컬럼 이름·코멘트에 포함({len(cols)}):\n" + "\n".join(f"  - {t}.{c}" + (f" — {n}" if n else "") for t, c, n in cols[:MAX_HITS]) + (f"\n  … 외 {len(cols) - MAX_HITS}개" if len(cols) > MAX_HITS else ""))
    if tables:
        res.facts.append(f"테이블 이름·설명에 포함({len(tables)}):\n" + "\n".join(f"  - {t} — {n}" for t, n in tables[:MAX_HITS]))
    for side, found in (("ASIS", labels), ("TOBE", tobe_labels)):
        if not found:
            continue
        lines = []
        for label, hits in sorted(found.items(), key=lambda kv: -len(kv[1]))[:MAX_HITS]:
            screens = _shown(sorted({s for s, _ in hits}), 4)
            props = sorted({p for _, p in hits if p})
            line = f"  - '{label}' ← {screens}"
            for p in props[:4]:
                cands = prop_to_cols.get(p, [])
                if 1 <= len(cands) <= MAX_LINKED:
                    line += f"\n      {p} ↔ 컬럼 {', '.join(cands)}  [근거: 속성 이름이 컬럼명에서 만든 이름과 같음]"
                elif cands:
                    line += f"\n      {p}: 같은 이름을 만드는 컬럼이 {len(cands)}개라 이어지 않음"
                else:
                    line += f"\n      {p}: 대응하는 컬럼 이름 없음 (속성이 컬럼명과 다르게 지어짐)"
            lines.append(line)
        res.facts.append(f"{side} 화면 라벨 {len(found)}종 (사용 화면 수 순):\n" + "\n".join(lines))

    try:
        like = f"%{term}%"
        codes = db.fetch(
            "SELECT k.sys08_kind_cd, k.sys08_kind_nm, count(c.sys09_code_id) FROM sys08_code_kind k LEFT JOIN sys09_code c ON c.sys09_code_kind_id = k.sys08_code_kind_id "
            "WHERE k.sys08_kind_nm ILIKE %s OR k.sys08_kind_cd ILIKE %s GROUP BY 1, 2 ORDER BY 1",
            (like, like),
        )
        values = db.fetch(
            "SELECT k.sys08_kind_cd, c.sys09_code, c.sys09_name FROM sys09_code c JOIN sys08_code_kind k ON k.sys08_code_kind_id = c.sys09_code_kind_id "
            "WHERE c.sys09_name ILIKE %s GROUP BY 1, 2, 3 ORDER BY 1, 2",
            (like,),
        )
        res.facts.append(f"공통 코드: 그룹 {len(codes)}개, 코드값 이름에 포함 {len(values)}건")
        if codes:
            res.facts.append("코드 그룹 이름에 포함:\n" + "\n".join(f"  - {cd} — {nm} (코드 {n}개)" for cd, nm, n in codes[:MAX_HITS]) + "\n  → `trace-code <그룹>`으로 값과 사용처")
        if values:
            res.facts.append("코드값 이름에 포함:\n" + "\n".join(f"  - {g}: {c} {n}" for g, c, n in values[:MAX_HITS]) + (f"\n  … 외 {len(values) - MAX_HITS}건" if len(values) > MAX_HITS else ""))
    except db.DbUnavailable as exc:
        res.unresolved.append(f"DB를 쓸 수 없어 공통 코드 이름은 건너뜀 ({exc})")
    return res
