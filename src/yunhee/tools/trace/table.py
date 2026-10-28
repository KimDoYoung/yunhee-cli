"""trace-table: 테이블 팩트 시트 (컬럼·코멘트, C/R/U/D SQL과 화면, 같은 이름 컬럼을 가진 테이블, 행 수).

스키마 스냅샷(`make-dbml`)에 mapper 전체를 `sql_parse`로 해석한 결과와 색인(`_index.json`)을 얹는다.
"""

from __future__ import annotations

import difflib
import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.schema_snapshot import load_snapshot
from yunhee.tools.sql_parse import parse_statement
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import (
    TargetNotFoundError,
    TraceContext,
    load_menus,
    wants_asis,
    wants_tobe,
)

MAX_LIST = 15  # 한 목록에 풀어 쓰는 항목 수 (더 많으면 "외 N개")
MAX_SHARED_TABLES = 8
MAX_SCREEN_DEPTH = 3
MAX_HOSTS = 3  # 클래스 하나당 보여 주는 소속 화면 수
BACKUP_TABLE = re.compile(r"bak|_back$|_backup$|_\d{6,8}$", re.IGNORECASE)


@dataclass
class SqlUse:
    key: str  # emp00_trans_info.selectByText
    ops: str  # 예: "R", "CU"
    approx: bool = False  # AST 해석에 실패해 정규식으로 추정한 결과


def _ops(parsed: Any, table: str) -> str:
    ops = ""
    flag = parsed.tables.get(table, "")
    if "R" in flag:
        ops += "R"
    writes = {act for act, tbl in parsed.writes if tbl == table}
    if "INSERT" in writes:
        ops += "C"
    if "UPDATE" in writes:
        ops += "U"
    if "DELETE" in writes:
        ops += "D"
    if "W" in flag and not writes:
        ops += "W"  # 쓰기 대상인데 작업 종류를 알 수 없음
    return ops


@lru_cache(maxsize=2)
def _usage_by_table(src_root: str) -> tuple[dict[str, list[SqlUse]], int]:
    """mapper 전체를 해석해 테이블 → [SqlUse]. 두 번째 값은 정규식 추정으로 되돌린 statement 수."""
    from yunhee.tools.as_is.mybatis_render import get_all_statements

    statements = get_all_statements(Path(src_root))
    usage: dict[str, list[SqlUse]] = defaultdict(list)
    approx = 0
    for key in sorted({s.key for s in statements.values() if s.kind != "sql"}):
        res = parse_statement(key, statements)
        if not res.ok:
            continue
        parsed = res.data
        approx += parsed.fallback
        for table in parsed.tables:
            ops = _ops(parsed, table) or "R"
            usage[table].append(SqlUse(key, "R" if parsed.fallback else ops, parsed.fallback))
    return dict(usage), approx


def _service_index(index_data: dict[str, Any]) -> tuple[dict[str, list[str]], dict[str, list[tuple[str, str]]]]:
    """(SQL ID → 서비스 키들, 테이블 → [(서비스 키, 동적 작업)]). 동적 작업은 UpdateDataModel의 updateModel/deleteModel."""
    by_sql: dict[str, list[str]] = defaultdict(list)
    dynamic: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for cls, info in index_data.get("server_classes", {}).items():
        for method in info.get("methods", []):
            svc = f"{cls}.{method['name']}"
            for sql_id in method.get("sqls", []):
                by_sql[sql_id].append(svc)
            for call, table in method.get("udm_calls", []):
                dynamic[table.lower()].append((svc, "D" if call == "deleteModel" else "CU"))
    return by_sql, dynamic


def _client_screens(ctx: TraceContext, service_keys: set[str]) -> dict[str, str]:
    """서비스 키를 쓰는 클라이언트 클래스 → 그 클래스를 포함하는 화면(없으면 자기 자신). 값은 사람이 읽는 표기."""
    data = ctx.index_data or {}
    classes: dict[str, Any] = data.get("client_classes", {})
    menus: dict[str, list[str]] = defaultdict(list)
    for m in load_menus(ctx):
        if m.screen:
            menus[m.screen].append(f"#{m.no}")
    reverse: dict[str, set[str]] = defaultdict(set)
    for name, info in classes.items():
        for ref in info.get("refs", []):
            reverse[ref].add(name)

    def hosts(cls: str) -> list[str]:
        """cls를 포함하는 가장 가까운 화면들. 화면을 만나면 그 위로는 더 올라가지 않는다 (화면을 여는 화면은 호스트가 아니다)."""
        if cls in menus:
            return [cls]
        found: list[str] = []
        seen = {cls}
        frontier = {cls}
        for _ in range(MAX_SCREEN_DEPTH):
            nxt: set[str] = set()
            for c in frontier:
                for parent in sorted(reverse.get(c, ())):
                    if parent in seen:
                        continue
                    seen.add(parent)
                    if parent in menus:
                        found.append(parent)
                    else:
                        nxt.add(parent)
            if found or not nxt:
                break
            frontier = nxt
        return found

    def label(screen: str) -> str:
        return f"{screen}({' '.join(menus[screen])})" if screen in menus else screen

    out: dict[str, str] = {}
    for name, info in classes.items():
        if not service_keys.intersection(info.get("services", [])):
            continue
        screens = hosts(name)
        if not screens:
            out[name] = "(소속 화면 없음)"
            continue
        shown = ", ".join(label(x) for x in screens[:MAX_HOSTS])
        out[name] = shown + (f" … 외 {len(screens) - MAX_HOSTS}개 화면" if len(screens) > MAX_HOSTS else "")
    return out


def _find_table(snapshot: dict[str, Any], name: str) -> dict[str, Any] | None:
    key = name.strip().lower()
    schema, _, bare = key.rpartition(".")
    for t in snapshot.get("tables", []):
        if t["name"].lower() == bare and (not schema or t["schema"].lower() == schema):
            return t
    return None


def _shared_columns(snapshot: dict[str, Any], table: dict[str, Any]) -> list[str]:
    owners: dict[str, list[str]] = defaultdict(list)
    for t in snapshot.get("tables", []):
        if t["name"] == table["name"]:
            continue
        for c in t.get("columns", []):
            owners[c["name"].lower()].append(t["name"])
    lines = []
    skipped: set[str] = set()
    for col in table.get("columns", []):
        names = owners.get(col["name"].lower(), [])
        others = [n for n in names if not BACKUP_TABLE.search(n)]
        skipped.update(n for n in names if BACKUP_TABLE.search(n))
        if others:
            shown = ", ".join(others[:MAX_SHARED_TABLES])
            more = f" … 외 {len(others) - MAX_SHARED_TABLES}개" if len(others) > MAX_SHARED_TABLES else ""
            lines.append(f"  - {col['name']}: {shown}{more}")
    if lines and skipped:
        lines.append(f"  (백업·임시 테이블 {len(skipped)}개 제외)")
    return lines


def _row_count(table: str, res: TraceResult) -> None:
    import psycopg

    from yunhee.tools.sql_runner import get_connection_string

    url = get_connection_string(None)
    if not url:
        res.unresolved.append("--stats: DB 접속 정보(YUNHEE_DB)가 없어 행 수를 구하지 못함")
        return
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute("SET statement_timeout = 10000")
                cur.execute(f'SELECT count(*) FROM "{table}"')  # table은 스냅샷에서 확인한 이름만 들어온다
                res.facts.append(f"행 수: {cur.fetchone()[0]}")
    except Exception as exc:  # noqa: BLE001 - DB는 사무실에서만 접근 가능하므로 실패는 정상 경로다
        res.unresolved.append(f"--stats: 행 수를 구하지 못함 ({type(exc).__name__}: {str(exc)[:80]})")
    res.unresolved.append("--stats: 최근 갱신일은 갱신 일시 컬럼 규칙이 확정되지 않아 구하지 않음")


def _listing(label: str, items: list[str]) -> str:
    shown = ", ".join(items[:MAX_LIST])
    more = f" … 외 {len(items) - MAX_LIST}개" if len(items) > MAX_LIST else ""
    return f"{label}({len(items)}): {shown}{more}"


def trace_table(name: str, ctx: TraceContext, schema_env: str | None = None, stats: bool = False, tobe: Path | None = None) -> TraceResult:
    """테이블 하나의 팩트 시트. name은 `테이블` 또는 `스키마.테이블`."""
    res = TraceResult(
        command="trace-table",
        description="테이블 컬럼·코멘트, 이 테이블을 C/R/U/D 하는 SQL과 화면, 같은 이름 컬럼을 가진 테이블, 행 수",
        side=ctx.side,
        params={"table_name": name},
    )
    res.unresolved += ctx.unresolved
    env = schema_env or config.SCHEMA_ENV
    snap = load_snapshot(env)
    if not snap.ok:
        res.unresolved.append(f"스키마 스냅샷 {env}를 읽지 못함: {snap.error}")
        return res
    snapshot = snap.data
    table = _find_table(snapshot, name)
    if table is None:
        names = [t["name"] for t in snapshot.get("tables", [])]
        raise TargetNotFoundError(name, difflib.get_close_matches(name.lower(), names, n=5, cutoff=0.6))
    tname = table["name"].lower()
    res.params["resolved"] = tname

    facts, evidence = res.facts, res.evidence
    note = f" — {table['note']}" if table.get("note") else ""
    facts.append(f"테이블: {table['schema']}.{table['name']}{note}")
    if table.get("pk"):
        facts.append(f"PK: {', '.join(table['pk'])}")
    for u in table.get("uniques", []):
        facts.append(f"UNIQUE {u['name']}: {', '.join(u['columns'])}")
    cols = []
    pk = set(table.get("pk", []))
    for c in table.get("columns", []):
        flags = ("PK " if c["name"] in pk else "") + ("NN " if c.get("not_null") else "")
        default = f" default {c['default']}" if c.get("default") else ""
        cnote = f" — {c['note']}" if c.get("note") else ""
        cols.append(f"  - {c['name']} {c['type']} {flags.strip()}{default}{cnote}".rstrip())
    facts.append(f"컬럼({len(cols)}):\n" + "\n".join(cols))
    shared = _shared_columns(snapshot, table)
    if shared:
        facts.append("같은 이름의 컬럼을 가진 테이블(FK가 정의돼 있지 않아 조인 후보로 본다):\n" + "\n".join(shared))
    else:
        facts.append("같은 이름의 컬럼을 가진 테이블: 없음 (컬럼명에 테이블 접두사가 붙어 있어 조인 후보를 이름으로 찾을 수 없다)")
    views = [v["name"] for v in snapshot.get("views", []) if isinstance(v, dict) and tname in (v.get("definition") or "").lower()]
    if views:
        facts.append(_listing("이 테이블을 참조하는 뷰", views))
    triggers = [t.get("name", "?") for t in snapshot.get("triggers", []) if isinstance(t, dict) and str(t.get("table", "")).lower().endswith(tname)]
    if triggers:
        facts.append(_listing("트리거", triggers))
    evidence.append(f"스키마 스냅샷: {env} ({snapshot.get('generated_at', '?')})")

    if wants_asis(ctx.side):
        _asis_usage(tname, ctx, res)
    if wants_tobe(ctx.side):
        _tobe_usage(tname, tobe, res)
    if stats:
        _row_count(tname, res)
    return res


def _tobe_usage(tname: str, tobe: Path | None, res: TraceResult) -> None:
    """TOBE mapper 문장이 이 테이블을 어떻게 쓰는지(C/R/U/D)와, 그 문장에 닿는 TOBE 화면(TSX → api → 컨트롤러 → 서비스 → mapper)."""
    from yunhee.tools.trace.sqlscan import scan_tobe
    from yunhee.tools.trace.tobe import build_index, find_layout

    layout = find_layout(tobe)
    if not layout.mapper_dir.is_dir():
        res.unresolved.append(f"TOBE mapper를 찾지 못해 TOBE 사용처를 구하지 못함 ({layout.root}) — --tobe로 지정")
        return
    scan = scan_tobe(str(layout.mapper_dir))
    by_op: dict[str, list[str]] = {"C": [], "R": [], "U": [], "D": [], "W": []}
    used: dict[str, str] = {}
    for key, parsed in scan.items():
        if tname not in parsed.tables:
            continue
        ops = _ops(parsed, tname) or "R"
        used[key] = ops
        for op in ops:
            by_op[op].append(_short_key(key) + ("*" if parsed.fallback else ""))
    lines = [_listing(f"  {op}", ids) for op, ids in by_op.items() if ids]
    res.facts.append(f"TOBE SQL 사용 {len(used)}개 (C 등록 / R 조회 / U 수정 / D 삭제):\n" + "\n".join(lines) if lines else "TOBE SQL 사용: 없음 (TOBE mapper에서 이 테이블을 참조하는 문장을 찾지 못함)")
    if any(p.fallback for p in scan.values()):
        res.unresolved.append("TOBE mapper 일부는 PostgreSQL 문법이 아니라 정규식으로 추정해 R로만 집계함 (* 표시)")
    if not used or not layout.usable:
        return
    idx = build_index(str(layout.root))
    screens: dict[str, set[str]] = defaultdict(set)  # TSX → 작업
    for fn in idx.api_fns.values():
        for ep in idx.endpoint_of(fn):
            hit = {k: used[k] for st in idx.statements_of(ep) if (k := st.key) in used}
            if not hit:
                continue
            for t in idx.tsx.values():
                if (fn.obj, fn.name) in t.api_calls:
                    screens[t.name] |= {op for ops in hit.values() for op in ops}
    if screens:
        rows = [f"{n}[{''.join(sorted(o))}]" for n, o in sorted(screens.items())]
        res.facts.append(_listing("TOBE 화면(이 테이블에 닿는 API를 부름)", rows))
    else:
        res.unresolved.append("이 테이블을 쓰는 TOBE 문장에 닿는 TSX를 찾지 못함 (api 함수 → 컨트롤러 연결이 끊겼거나 화면이 없음)")


def _short_key(key: str) -> str:
    parts = key.split(".")
    return ".".join(parts[-2:]) if len(parts) > 2 else key


def _asis_usage(tname: str, ctx: TraceContext, res: TraceResult) -> None:
    facts, evidence, unresolved = res.facts, res.evidence, res.unresolved
    if not ctx.src_root or not Path(ctx.src_root).is_dir():
        unresolved.append("ASIS 소스를 찾지 못해 이 테이블을 쓰는 SQL을 구하지 못함 (YUNHEE_ASIS_SRC_DIR)")
        return
    usage, approx = _usage_by_table(str(ctx.src_root))
    uses = usage.get(tname, [])
    by_op: dict[str, list[str]] = {"C": [], "R": [], "U": [], "D": [], "W": []}
    for u in uses:
        for op in u.ops:
            by_op[op].append(u.key + ("*" if u.approx else ""))
    lines = [_listing(f"  {op}", ids) for op, ids in by_op.items() if ids]
    if lines:
        facts.append(f"SQL 사용 {len(uses)}개 (C 등록 / R 조회 / U 수정 / D 삭제):\n" + "\n".join(lines))
    else:
        facts.append("SQL 사용: 없음 (mapper에서 이 테이블을 참조하는 statement를 찾지 못함)")
    if approx:
        unresolved.append(f"mapper {approx}개는 PostgreSQL 문법이 아니라 정규식으로 추정해 R로만 집계함 (* 표시)")

    statements = (ctx.index_data or {}).get("statements", {})
    for u in uses[:MAX_LIST * 2]:
        info = statements.get(u.key)
        if info:
            evidence.append(f"SQL {u.key} → {info['file']}:{info['line']}")

    if not ctx.has_index:
        unresolved.append("ASIS 색인이 없어 SQL → 서비스 → 화면 연결을 구하지 못함 (`yunhee index-src`)")
        return
    by_sql, dynamic = _service_index(ctx.index_data)
    services: dict[str, set[str]] = defaultdict(set)  # 서비스 키 → 작업들
    for u in uses:
        for svc in by_sql.get(u.key, []):
            services[svc].update(u.ops)
    for svc, op in dynamic.get(tname, []):
        services[svc].update(op)
        evidence.append(f"서비스 {svc}: UpdateDataModel({tname}) 동적 {'삭제' if op == 'D' else '등록/수정'}")
    if not services:
        return
    facts.append(_listing("이 테이블을 쓰는 서비스", [f"{s}[{''.join(sorted(o))}]" for s, o in sorted(services.items())]))
    screens = _client_screens(ctx, set(services))
    if screens:
        lines = [f"  - {cls} → {hosts}" for cls, hosts in sorted(screens.items())]
        shown = lines[: MAX_LIST * 2]
        more = [f"  … 외 {len(lines) - len(shown)}개"] if len(lines) > len(shown) else []
        facts.append(f"서비스를 호출하는 클래스와 소속 화면({len(lines)}):\n" + "\n".join(shown + more))
    else:
        unresolved.append("이 테이블의 서비스를 호출하는 클라이언트 클래스를 색인에서 찾지 못함")
