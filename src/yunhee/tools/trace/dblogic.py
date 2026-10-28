"""trace-dblogic: DB 함수·프로시저·트리거의 본문과 이를 호출하는 SQL.

본문은 스키마 스냅샷(`make-dbml`)의 정의를 그대로 읽는다 (DB 접속 없음). 호출처는 mapper 전체를 해석한 결과(`sqlscan`)에서
함수 호출(`FuncCall`)을 찾고, DB 안의 다른 함수·트리거가 부르는 곳은 본문의 `이름(` 표기로 찾는다.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.analysis.common import AmbiguousTargetError
from yunhee.tools.schema_snapshot import load_snapshot
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import (
    TargetNotFoundError,
    TraceContext,
    wants_asis,
    wants_tobe,
)
from yunhee.tools.trace.sqlscan import scan_asis, scan_tobe
from yunhee.tools.trace.tobe import find_layout

MAX_BODY_LINES = 80
MAX_LIST = 15
_HEADER = re.compile(r"RETURNS\s+(.+?)\s*$", re.MULTILINE)
_LANG = re.compile(r"LANGUAGE\s+(\w+)", re.IGNORECASE)
_EXECUTES = re.compile(r"EXECUTE\s+(?:FUNCTION|PROCEDURE)\s+([\w.]+)\s*\(", re.IGNORECASE)


def _bare(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower()


def _short(key: str) -> str:
    parts = key.split(".")
    return ".".join(parts[-2:]) if len(parts) > 2 else key


def _callers(scan: dict, name: str) -> list[str]:
    n = name.lower()
    return sorted(_short(k) for k, p in scan.items() if n in p.functions or n in p.table_functions)


def _body_view(definition: str) -> str:
    lines = definition.splitlines()
    shown = "\n".join(f"  {i:>4}  {ln}" for i, ln in enumerate(lines[:MAX_BODY_LINES], 1))
    more = f"\n  … 본문 {len(lines)}줄 중 {MAX_BODY_LINES}줄까지 ({len(definition):,}자). 전체는 스냅샷 `data/schema/<스냅샷>.json`의 definition" if len(lines) > MAX_BODY_LINES else ""
    return shown + more


def _used_tables(definition: str, table_names: list[str]) -> list[str]:
    low = definition.lower()
    return sorted(t for t in table_names if re.search(rf"\b{re.escape(t)}\b", low))


def _called_routines(definition: str, routine_names: set[str], self_name: str) -> list[str]:
    low = definition.lower()
    return sorted(n for n in routine_names if n != self_name and re.search(rf"\b{re.escape(n)}\s*\(", low))


def _summary(snapshot: dict, asis: dict | None, tobe: dict | None, res: TraceResult) -> None:
    routines, triggers = snapshot.get("routines", []), snapshot.get("triggers", [])
    kinds = Counter(r["kind"] for r in routines)
    res.facts.append(f"DB 로직: 함수 {kinds['function']}, 프로시저 {kinds['procedure']}, 트리거 {len(triggers)} — 이름을 주면 본문과 호출처 (예: `trace-dblogic f_cdnm`)")
    for label, scan in (("ASIS", asis), ("TOBE", tobe)):
        if not scan:
            continue
        names = {r["name"].lower() for r in routines}
        calls = Counter(f for p in scan.values() for f in set(p.functions) | set(p.table_functions) if f in names)
        top = ", ".join(f"{n}({c})" for n, c in calls.most_common(MAX_LIST))
        res.facts.append(f"{label} SQL에서 가장 많이 호출되는 DB 함수(문장 수): {top}" if calls else f"{label} SQL이 호출하는 DB 함수 없음")
        unused = sorted(names - set(calls))
        res.facts.append(f"{label} SQL이 호출하지 않는 함수·프로시저 {len(unused)}개 (트리거·DB 안 호출이나 미사용일 수 있음): " + ", ".join(unused[:MAX_LIST]) + (" …" if len(unused) > MAX_LIST else ""))
    by_table = Counter(t["table"] for t in triggers)
    res.facts.append("트리거가 많은 테이블: " + ", ".join(f"{t}({n})" for t, n in by_table.most_common(8)))


def trace_dblogic(name: str | None, ctx: TraceContext, tobe: Path | None = None, schema_env: str | None = None) -> TraceResult:
    res = TraceResult(
        command="trace-dblogic",
        description="함수·프로시저·트리거 본문과 이를 호출하는 SQL",
        side=ctx.side,
        params={"name": name},
    )
    res.unresolved += ctx.unresolved
    snap = load_snapshot(schema_env or config.SCHEMA_ENV)
    if not snap.ok:
        res.unresolved.append(f"스키마 스냅샷을 읽지 못함: {snap.error} (`yunhee make-dbml`)")
        return res
    snapshot: dict[str, Any] = snap.data
    res.evidence.append(f"스키마 스냅샷: {schema_env or config.SCHEMA_ENV} ({snapshot.get('generated_at', '?')})")

    asis = scan_asis(str(ctx.src_root)) if wants_asis(ctx.side) and ctx.src_root and Path(ctx.src_root).is_dir() else None
    if wants_asis(ctx.side) and asis is None:
        res.unresolved.append("ASIS 소스를 찾지 못해 ASIS 호출처를 구하지 못함 (YUNHEE_ASIS_SRC_DIR)")
    layout = find_layout(tobe)
    tobe_scan = scan_tobe(str(layout.mapper_dir)) if wants_tobe(ctx.side) and layout.mapper_dir.is_dir() else None
    if wants_tobe(ctx.side) and tobe_scan is None:
        res.unresolved.append(f"TOBE mapper를 찾지 못해 TOBE 호출처를 구하지 못함 ({layout.root}) — --tobe로 지정")

    if not name:
        _summary(snapshot, asis, tobe_scan, res)
        return res

    key = _bare(name)
    routines = [r for r in snapshot.get("routines", []) if r["name"].lower() == key]
    triggers = [t for t in snapshot.get("triggers", []) if t["name"].lower() == key]
    if not routines and not triggers:
        like = sorted({r["name"] for r in snapshot.get("routines", []) if key in r["name"].lower()} | {t["name"] for t in snapshot.get("triggers", []) if key in t["name"].lower()})
        if len(like) == 1:
            return trace_dblogic(like[0], ctx, tobe, schema_env)
        if like:
            raise AmbiguousTargetError(like[:10], name)
        raise TargetNotFoundError(name, sorted(r["name"] for r in snapshot.get("routines", []))[:5])
    res.params["resolved"] = key

    all_routines = {r["name"].lower() for r in snapshot.get("routines", [])}
    tables = [t["name"].lower() for t in snapshot.get("tables", [])]
    for r in routines:
        d = r["definition"]
        ret = (_HEADER.search(d) or [None, ""])[1]
        lang = (_LANG.search(d) or [None, ""])[1]
        sig = f"{r['name']}({r['arguments']})"
        res.facts.append(f"{r['kind']} {sig}" + (f" RETURNS {ret}" if ret else "") + (f" [{lang}]" if lang else "") + (f" — {r['note']}" if r.get("note") and r["note"] != "None" else ""))
        res.facts.append("본문:\n" + _body_view(d))
        used = _used_tables(d, tables)
        if used:
            res.facts.append(f"본문이 참조하는 테이블({len(used)}): " + ", ".join(used[:MAX_LIST]) + (" …" if len(used) > MAX_LIST else ""))
        inner = _called_routines(d, all_routines, key)
        if inner:
            res.facts.append(f"본문이 부르는 다른 DB 함수({len(inner)}): " + ", ".join(inner[:MAX_LIST]))
        res.evidence.append(f"{r['schema']}.{r['name']}({r['arguments']}) 정의 {len(d.splitlines())}줄")
    for t in triggers:
        m = _EXECUTES.search(t["definition"])
        res.facts.append(f"트리거 {t['name']} — 테이블 {t['table']}\n  {t['definition']}")
        if m:
            res.facts.append(f"이 트리거가 실행하는 함수: {_bare(m.group(1))} (`trace-dblogic {_bare(m.group(1))}`로 본문)")
        res.evidence.append(f"{t['schema']}.{t['name']} on {t['table']}")

    if routines:
        runs = [t for t in snapshot.get("triggers", []) if (m := _EXECUTES.search(t["definition"])) and _bare(m.group(1)) == key]
        if runs:
            res.facts.append(f"이 함수를 실행하는 트리거({len(runs)}): " + ", ".join(f"{t['name']}({t['table']})" for t in runs[:MAX_LIST]))
        db_callers = sorted(
            r["name"] for r in snapshot.get("routines", []) if r["name"].lower() != key and re.search(rf"\b{re.escape(key)}\s*\(", r["definition"].lower())
        )
        if db_callers:
            res.facts.append(f"DB 안에서 이 함수를 부르는 다른 함수({len(db_callers)}): " + ", ".join(db_callers[:MAX_LIST]))
        for label, scan in (("ASIS", asis), ("TOBE", tobe_scan)):
            if scan is None:
                continue
            callers = _callers(scan, key)
            res.facts.append(
                f"{label} SQL 호출처 {len(callers)}개" + (": " + ", ".join(callers[:MAX_LIST]) + (f" … 외 {len(callers) - MAX_LIST}개" if len(callers) > MAX_LIST else "") if callers else " (mapper에서 이 함수를 부르는 곳이 없음)")
            )
        if asis is not None and sum(1 for p in asis.values() if p.fallback):
            res.unresolved.append(f"ASIS mapper {sum(1 for p in asis.values() if p.fallback)}개는 PostgreSQL 문법이 아니라 함수 호출을 읽지 못함 — 호출처가 더 있을 수 있음")
    res.unresolved.append("Java·TS 소스에서 DB 함수를 직접 부르는 곳(JDBC `{call …}`)과 동적 SQL(`${}`)은 찾지 못한다")
    return res
