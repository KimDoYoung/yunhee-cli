"""PostgreSQL 시스템 카탈로그를 읽어 스키마 구조(테이블/인덱스/FK/enum/view/function/sequence/trigger)를 수집한다.

읽기 전용 세션(`conn.read_only = True`)에서 카탈로그 SELECT만 수행한다.
결과는 파일(DBML 스냅샷) 출력용이므로 truncation하지 않는다 — 토큰 예산은 그 파일을 소비하는 쪽에서 다룬다.
"""

import psycopg

from yunhee.tools.base import ToolResult

_SCHEMAS_SQL = """
SELECT nspname FROM pg_namespace
WHERE nspname NOT IN ('pg_catalog', 'information_schema')
  AND nspname NOT LIKE 'pg\\_toast%' AND nspname NOT LIKE 'pg\\_temp%'
ORDER BY 1
"""

# 확장(extension)이 소유한 객체는 제외 (pgcrypto 함수 등이 섞이지 않게)
_NOT_EXTENSION = """
NOT EXISTS (SELECT 1 FROM pg_depend d
            WHERE d.classid = '{catalog}'::regclass AND d.objid = {oid} AND d.deptype = 'e')
"""

_TABLES_SQL = f"""
SELECT n.nspname, c.relname, obj_description(c.oid, 'pg_class')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p') AND NOT c.relispartition AND n.nspname = ANY(%s)
  AND {_NOT_EXTENSION.format(catalog='pg_class', oid='c.oid')}
ORDER BY 1, 2
"""

_COLUMNS_SQL = """
SELECT n.nspname, c.relname, a.attname, format_type(a.atttypid, a.atttypmod), a.attnotnull,
       pg_get_expr(d.adbin, d.adrelid), a.attidentity, a.attgenerated,
       col_description(a.attrelid, a.attnum)
FROM pg_attribute a
JOIN pg_class c ON c.oid = a.attrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
WHERE c.relkind IN ('r', 'p') AND n.nspname = ANY(%s) AND a.attnum > 0 AND NOT a.attisdropped
ORDER BY 1, 2, a.attnum
"""

_CONSTRAINTS_SQL = """
SELECT n.nspname, c.relname, con.conname, con.contype,
       ARRAY(SELECT a.attname::text FROM unnest(con.conkey) WITH ORDINALITY k(attnum, ord)
             JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.attnum ORDER BY k.ord),
       fn.nspname, fc.relname,
       ARRAY(SELECT a.attname::text FROM unnest(con.confkey) WITH ORDINALITY k(attnum, ord)
             JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.attnum ORDER BY k.ord),
       con.confdeltype, con.confupdtype
FROM pg_constraint con
JOIN pg_class c ON c.oid = con.conrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
LEFT JOIN pg_class fc ON fc.oid = con.confrelid
LEFT JOIN pg_namespace fn ON fn.oid = fc.relnamespace
WHERE con.contype IN ('p', 'u', 'f') AND c.relkind IN ('r', 'p') AND n.nspname = ANY(%s)
ORDER BY 1, 2, 3
"""

# PK/UNIQUE 제약조건이 만든 인덱스는 제약조건 쪽에서 표현하므로 제외
_INDEXES_SQL = """
SELECT n.nspname, t.relname, i.relname, ix.indisunique, am.amname,
       ARRAY(SELECT pg_get_indexdef(ix.indexrelid, k, true) FROM generate_series(1, ix.indnkeyatts) k ORDER BY k),
       ARRAY(SELECT ix.indkey[k - 1] = 0 FROM generate_series(1, ix.indnkeyatts) k ORDER BY k),
       pg_get_expr(ix.indpred, ix.indrelid)
FROM pg_index ix
JOIN pg_class i ON i.oid = ix.indexrelid
JOIN pg_class t ON t.oid = ix.indrelid
JOIN pg_namespace n ON n.oid = t.relnamespace
JOIN pg_am am ON am.oid = i.relam
WHERE t.relkind IN ('r', 'p') AND n.nspname = ANY(%s) AND NOT ix.indisprimary
  AND NOT EXISTS (SELECT 1 FROM pg_constraint con
                  WHERE con.conindid = ix.indexrelid AND con.contype IN ('p', 'u'))
ORDER BY 1, 2, 3
"""

_ENUMS_SQL = """
SELECT n.nspname, t.typname, array_agg(e.enumlabel::text ORDER BY e.enumsortorder)
FROM pg_type t
JOIN pg_enum e ON e.enumtypid = t.oid
JOIN pg_namespace n ON n.oid = t.typnamespace
WHERE n.nspname = ANY(%s)
GROUP BY 1, 2
ORDER BY 1, 2
"""

_VIEWS_SQL = f"""
SELECT n.nspname, c.relname, c.relkind, pg_get_viewdef(c.oid, true), obj_description(c.oid, 'pg_class')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('v', 'm') AND n.nspname = ANY(%s)
  AND {_NOT_EXTENSION.format(catalog='pg_class', oid='c.oid')}
ORDER BY 1, 2
"""

_ROUTINES_SQL = f"""
SELECT n.nspname, p.proname, p.prokind, pg_get_function_identity_arguments(p.oid),
       pg_get_functiondef(p.oid), obj_description(p.oid, 'pg_proc')
FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE p.prokind IN ('f', 'p') AND n.nspname = ANY(%s)
  AND {_NOT_EXTENSION.format(catalog='pg_proc', oid='p.oid')}
ORDER BY 1, 2, 4
"""

# owned by: serial은 deptype 'a', identity는 'i'
_SEQUENCES_SQL = """
SELECT s.schemaname, s.sequencename, s.data_type::text, s.start_value, s.increment_by,
       s.min_value, s.max_value, s.cycle,
       (SELECT dn.nspname || '.' || dc.relname || '.' || a.attname
        FROM pg_depend d
        JOIN pg_class dc ON dc.oid = d.refobjid
        JOIN pg_namespace dn ON dn.oid = dc.relnamespace
        JOIN pg_attribute a ON a.attrelid = d.refobjid AND a.attnum = d.refobjsubid
        WHERE d.classid = 'pg_class'::regclass
          AND d.objid = (quote_ident(s.schemaname) || '.' || quote_ident(s.sequencename))::regclass
          AND d.deptype IN ('a', 'i')
        LIMIT 1)
FROM pg_sequences s
WHERE s.schemaname = ANY(%s)
ORDER BY 1, 2
"""

_TRIGGERS_SQL = """
SELECT n.nspname, c.relname, t.tgname, pg_get_triggerdef(t.oid, true)
FROM pg_trigger t
JOIN pg_class c ON c.oid = t.tgrelid
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE NOT t.tgisinternal AND n.nspname = ANY(%s)
ORDER BY 1, 2, 3
"""


def fetch_schema(dsn: str, schemas: list[str] | None = None) -> ToolResult:
    """dsn(postgresql URL)에 읽기 전용으로 접속해 스키마 구조를 dict로 반환한다.

    schemas가 None이면 시스템 스키마(pg_catalog, information_schema, pg_toast*, pg_temp*)를 제외한 전체.
    """
    try:
        with psycopg.connect(dsn, connect_timeout=10) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                return _fetch(cur, schemas)
    except psycopg.Error as e:
        # psycopg 오류 메시지에는 비밀번호가 포함되지 않는다
        return ToolResult(ok=False, error=f"DB 조회 실패: {str(e).strip()}")


def _fetch(cur: psycopg.Cursor, schemas: list[str] | None) -> ToolResult:
    cur.execute(_SCHEMAS_SQL)
    available = [r[0] for r in cur.fetchall()]
    if schemas:
        missing = [s for s in schemas if s not in available]
        if missing:
            return ToolResult(ok=False, error=f"존재하지 않는 스키마: {', '.join(missing)}")
        target = list(schemas)
    else:
        target = available

    cur.execute("SELECT current_database(), current_setting('server_version')")
    database, server_version = cur.fetchone()

    tables: dict[tuple[str, str], dict] = {}
    cur.execute(_TABLES_SQL, (target,))
    for schema, name, note in cur.fetchall():
        tables[(schema, name)] = {
            "schema": schema, "name": name, "note": note,
            "columns": [], "pk": [], "uniques": [], "indexes": [],
        }

    cur.execute(_COLUMNS_SQL, (target,))
    for schema, table, name, type_, notnull, default, identity, generated, note in cur.fetchall():
        t = tables.get((schema, table))
        if t is None:  # 파티션 자식, 확장 소유 테이블
            continue
        t["columns"].append({
            "name": name, "type": type_, "not_null": notnull, "default": default,
            "identity": identity or None, "generated": generated or None, "note": note,
        })

    refs = []
    cur.execute(_CONSTRAINTS_SQL, (target,))
    for schema, table, conname, contype, cols, fschema, ftable, fcols, ondelete, onupdate in cur.fetchall():
        t = tables.get((schema, table))
        if t is None:
            continue
        if contype == "p":
            t["pk"] = cols
        elif contype == "u":
            t["uniques"].append({"name": conname, "columns": cols})
        else:
            refs.append({
                "name": conname, "schema": schema, "table": table, "columns": cols,
                "ref_schema": fschema, "ref_table": ftable, "ref_columns": fcols,
                "on_delete": ondelete, "on_update": onupdate,
            })

    cur.execute(_INDEXES_SQL, (target,))
    for schema, table, name, unique, method, exprs, is_expr, predicate in cur.fetchall():
        t = tables.get((schema, table))
        if t is None:
            continue
        t["indexes"].append({
            "name": name, "unique": unique, "method": method,
            "columns": [{"expr": e, "is_expression": x} for e, x in zip(exprs, is_expr)],
            "where": predicate,
        })

    cur.execute(_ENUMS_SQL, (target,))
    enums = [{"schema": s, "name": n, "values": v} for s, n, v in cur.fetchall()]

    cur.execute(_VIEWS_SQL, (target,))
    views = [
        {"schema": s, "name": n, "materialized": kind == "m", "definition": d, "note": note}
        for s, n, kind, d, note in cur.fetchall()
    ]

    cur.execute(_ROUTINES_SQL, (target,))
    routines = [
        {"schema": s, "name": n, "kind": "procedure" if kind == "p" else "function",
         "arguments": args, "definition": d, "note": note}
        for s, n, kind, args, d, note in cur.fetchall()
    ]

    cur.execute(_SEQUENCES_SQL, (target,))
    sequences = [
        {"schema": s, "name": n, "type": t, "start": start, "increment": inc,
         "min": mn, "max": mx, "cycle": cyc, "owned_by": owned}
        for s, n, t, start, inc, mn, mx, cyc, owned in cur.fetchall()
    ]

    cur.execute(_TRIGGERS_SQL, (target,))
    triggers = [
        {"schema": s, "table": t, "name": n, "definition": d}
        for s, t, n, d in cur.fetchall()
    ]

    return ToolResult(ok=True, data={
        "database": database,
        "server_version": server_version,
        "schemas": target,
        "tables": list(tables.values()),
        "refs": refs,
        "enums": enums,
        "views": views,
        "routines": routines,
        "sequences": sequences,
        "triggers": triggers,
    })
