"""trace-column: 컬럼을 읽는/쓰는/조건에 쓰는 SQL, 화면에 표시되는 라벨, 값 분포.

읽기·조건·정렬 구분은 SQL AST의 절(SELECT / WHERE / JOIN / ORDER …)로 한다. 쓰기는 INSERT/UPDATE 대입이다.
`SELECT *`로 읽는 SQL은 컬럼 단위로 알 수 없어 집계에서 빠진다 (unresolved에 밝힌다).
"""

from __future__ import annotations

import re
from pathlib import Path

from yunhee import config
from yunhee.tools.as_is.events import col_to_tobe_prop
from yunhee.tools.schema_snapshot import load_snapshot
from yunhee.tools.trace import db
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import (
    TargetNotFoundError,
    TraceContext,
    wants_asis,
    wants_tobe,
)
from yunhee.tools.trace.sqlscan import scan_asis, scan_tobe
from yunhee.tools.trace.state import split_ref
from yunhee.tools.trace.tobe import build_index, find_layout

MAX_LIST = 12
MAX_DISTINCT = 30  # 값 분포는 코드성 컬럼(고유 값이 이 이하)에만 낸다. 이름·주민번호 같은 개인정보가 컨텍스트에 새지 않게 한다
GROUPS = {
    "읽기(SELECT·SET 식·RETURNING)": {"SELECT", "SET", "RETURNING", "VALUES"},
    "조건(WHERE·JOIN·HAVING)": {"WHERE", "JOIN", "HAVING"},
    "정렬·그룹(ORDER·GROUP)": {"ORDER", "GROUP"},
}
_TABLES_SECTION = re.compile(r"^## 테이블\s*$(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)


def _short(key: str) -> str:
    """TOBE 문장 키 `kr.co.…mapper.AprAltApprMapper.selectByEmpId` → `AprAltApprMapper.selectByEmpId`. ASIS `ns.id`는 그대로."""
    parts = key.split(".")
    return ".".join(parts[-2:]) if len(parts) > 2 else key


def _classify(scan: dict, table: str, column: str) -> tuple[dict[str, list[str]], list[str]]:
    """(읽기·조건·정렬별 SQL 키, 쓰기 SQL `키(작업)`)."""
    groups: dict[str, list[str]] = {g: [] for g in GROUPS}
    writes: list[str] = []
    for key, parsed in scan.items():
        clauses = set(parsed.column_usage.get(table, {}).get(column, []))
        for name, members in GROUPS.items():
            if clauses & members:
                groups[name].append(_short(key))
        acts = sorted({a.action for a in parsed.assignments if a.table == table and a.column == column})
        if acts:
            writes.append(f"{_short(key)}({'/'.join(acts)})")
    return groups, writes


def _list(label: str, items: list[str]) -> str:
    items = sorted(items)
    shown = ", ".join(items[:MAX_LIST])
    more = f" … 외 {len(items) - MAX_LIST}개" if len(items) > MAX_LIST else ""
    return f"{label}({len(items)}): {shown}{more}" if items else f"{label}(0)"


def _report(side: str, scan: dict, table: str, column: str, res: TraceResult) -> None:
    groups, writes = _classify(scan, table, column)
    lines = [_list(f"  {name}", keys) for name, keys in groups.items()] + [_list("  쓰기(INSERT/UPDATE)", writes)]
    total = len({k for keys in groups.values() for k in keys} | {w.split("(")[0] for w in writes})
    res.facts.append(f"{side}: 이 컬럼을 쓰는 SQL {total}개\n" + "\n".join(lines))
    fallback = sum(1 for p in scan.values() if p.fallback)
    if fallback:
        res.unresolved.append(f"{side} mapper {fallback}개는 PostgreSQL 문법이 아니라 컬럼 사용을 읽지 못함 — 위 집계에 빠질 수 있음")


def _asis_labels(ctx: TraceContext, table: str, prop: str) -> list[str]:
    """ASIS 색인의 Grid Spec(`gb.text('korNm', 100, '성명')`)에서, 이 테이블을 쓰는 화면의 라벨."""
    if not ctx.src_index:
        return []
    field = re.compile(rf"gb\.\w+\(\s*'{re.escape(prop)}'\s*,\s*[^,]+,\s*'([^']*)'")
    out: list[str] = []
    for path in sorted(ctx.src_index.glob("*/screens/*.md")):
        text = path.read_text(encoding="utf-8", errors="replace")
        m = _TABLES_SECTION.search(text)
        if not m or f"`{table}`" not in m.group(1):
            continue
        for label in field.findall(text):
            out.append(f"{path.stem}: '{label}'")
    return list(dict.fromkeys(out))


def _tobe_labels(root: str, prop: str) -> list[str]:
    idx = build_index(root)
    return list(dict.fromkeys(f"{t.name}: '{lab}'" for t in idx.tsx.values() for f, lab in t.grid_cols if f == prop))


def trace_column(col_ref: str, ctx: TraceContext, tobe: Path | None = None, schema_env: str | None = None, stats: bool = False) -> TraceResult:
    table, column = split_ref(col_ref)
    res = TraceResult(
        command="trace-column",
        description="이 컬럼을 읽는/쓰는/WHERE에 쓰는 SQL, 표시되는 화면 라벨, 값 분포",
        side=ctx.side,
        params={"col_ref": f"{table}.{column}"},
    )
    res.unresolved += ctx.unresolved
    snap = load_snapshot(schema_env or config.SCHEMA_ENV)
    if not snap.ok:
        res.unresolved.append(f"스키마 스냅샷을 읽지 못해 {col_ref}가 실제 컬럼인지 확인하지 못함")
    else:
        tbl = next((t for t in snap.data.get("tables", []) if t["name"].lower() == table), None)
        col = next((c for c in (tbl or {}).get("columns", []) if c["name"].lower() == column), None)
        if tbl is None or col is None:
            names = [f"{table}.{c['name']}" for c in (tbl or {}).get("columns", []) if column[:5] in c["name"].lower()][:5]
            raise TargetNotFoundError(col_ref, names)
        flags = ("PK " if column in [p.lower() for p in tbl.get("pk", [])] else "") + ("NOT NULL" if col.get("not_null") else "")
        res.facts.append(f"컬럼: {table}.{column} {col['type']} {flags}".rstrip() + (f" — {col['note']}" if col.get("note") else ""))
        res.evidence.append(f"스키마 스냅샷: {schema_env or config.SCHEMA_ENV} ({snap.data.get('generated_at', '?')})")

    prop = col_to_tobe_prop(column)
    if wants_asis(ctx.side):
        if not ctx.src_root or not Path(ctx.src_root).is_dir():
            res.unresolved.append("ASIS 소스를 찾지 못해 ASIS SQL을 구하지 못함 (YUNHEE_ASIS_SRC_DIR)")
        else:
            _report("ASIS", scan_asis(str(ctx.src_root)), table, column, res)
    if wants_tobe(ctx.side):
        layout = find_layout(tobe)
        if not layout.mapper_dir.is_dir():
            res.unresolved.append(f"TOBE mapper를 찾지 못함 ({layout.root}) — --tobe로 지정")
        else:
            _report("TOBE", scan_tobe(str(layout.mapper_dir)), table, column, res)

    labels = _asis_labels(ctx, table, prop) if wants_asis(ctx.side) and ctx.has_index else []
    tobe_labels = _tobe_labels(str(find_layout(tobe).root), prop) if wants_tobe(ctx.side) and find_layout(tobe).usable else []
    res.facts.append(
        f"화면 표시 라벨(속성 이름 `{prop}`): ASIS {len(labels)}건 / TOBE {len(tobe_labels)}건"
        + ("\n  ASIS: " + ", ".join(labels[:MAX_LIST]) if labels else "")
        + ("\n  TOBE: " + ", ".join(tobe_labels[:MAX_LIST]) if tobe_labels else "")
    )
    res.unresolved.append("화면 라벨은 DB 컬럼명에서 만든 속성 이름(접두사를 뗀 camelCase)이 그리드 필드명과 같을 때만 찾는다 — 이름이 다르게 매핑된 화면은 빠질 수 있음")

    if stats:
        try:
            if not re.fullmatch(r"[a-z_][a-z0-9_]*", table) or not re.fullmatch(r"[a-z_][a-z0-9_]*", column):
                raise ValueError("식별자 형식이 아님")
            n_distinct, n_null, total = db.fetch(f'SELECT count(DISTINCT "{column}"), count(*) FILTER (WHERE "{column}" IS NULL), count(*) FROM "{table}"')[0]  # 식별자는 스냅샷 확인·형식 검사를 마쳤다
            head = f"행 {total}, NULL {n_null}, 고유 값 {n_distinct}종"
            if n_distinct > MAX_DISTINCT:
                res.facts.append(f"값 분포: {head} — 코드성 컬럼({MAX_DISTINCT}종 이하)이 아니라 값은 내지 않음 (개인정보·식별자 노출 방지)")
            else:
                rows = db.fetch(f'SELECT "{column}", count(*) AS n FROM "{table}" GROUP BY 1 ORDER BY n DESC, 1 LIMIT {MAX_DISTINCT}')
                res.facts.append(f"값 분포({head}):\n  " + ", ".join(f"{('NULL' if v is None else v)}: {n}" for v, n in rows))
        except (db.DbUnavailable, ValueError) as exc:
            res.unresolved.append(f"--stats: 값 분포를 구하지 못함 ({exc})")
    return res
