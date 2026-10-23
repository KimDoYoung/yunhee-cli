"""yunhee-cli Agent DB SQL Tool.
PostgreSQL 데이터베이스(asseterpdb)에서 SELECT 쿼리를 안전하게 실행하거나
테이블(DBML DDL), 함수/프로시저(PL/pgSQL 본체), 뷰(View DDL) 등 DB 객체 정의를 조회하여 마크다운으로 반환하는 에이전트 도구.
"""

from __future__ import annotations

from yunhee import config
from yunhee.tools.schema_snapshot import load_snapshot, slice_tables
from yunhee.tools.sql_runner import run_sql as _run_sql


def get_db_definition(name: str) -> str:
    """테이블(DBML DDL), 스토어드 함수/프로시저(PL/pgSQL 본체 소스), 뷰 정의 등 PostgreSQL DB 객체의 전체 정의를 조회합니다."""
    clean_name = name.strip().strip("'\"`;")
    if not clean_name:
        return "error: 객체 이름이 비어 있습니다."

    lower_name = clean_name.lower()

    # 1. 오프라인 스냅샷(LOCAL_DB.json)에서 1차 탐색
    try:
        snap = load_snapshot(config.SCHEMA_ENV)
        if snap.ok and snap.data:
            data = snap.data

            # 1-1. 스토어드 함수/프로시저 (routines) 검색
            routines = data.get("routines", [])
            matched_routines = [r for r in routines if r.get("name", "").lower() == lower_name]
            if matched_routines:
                lines = []
                for r in matched_routines:
                    comment = f"\n-- 설명: {r['comment']}" if r.get("comment") else ""
                    lines.append(f"### ⚙ 함수/프로시저 정의: `{r.get('name')}` ({r.get('schema', 'public')}){comment}")
                    lines.append("```sql")
                    lines.append(r.get("definition", "").strip())
                    lines.append("```")
                return "\n\n".join(lines)

            # 1-2. 뷰 (views) 검색
            views = data.get("views", [])
            matched_views = [v for v in views if v.get("name", "").lower() == lower_name]
            if matched_views:
                v = matched_views[0]
                comment = f"\n-- 설명: {v['comment']}" if v.get("comment") else ""
                return f"### 👁 뷰 정의: `{v.get('name')}` ({v.get('schema', 'public')}){comment}\n```sql\n{v.get('definition', '').strip()}\n```"

            # 1-3. 테이블 (tables) 검색
            sliced = slice_tables(data, [clean_name])
            if sliced.ok and sliced.data and sliced.data.get("tables") and sliced.data.get("dbml"):
                return f"```dbml\n{sliced.data['dbml'].strip()}\n```"
    except Exception:  # noqa: BLE001, S110
        pass

    # 2. 오프라인 스냅샷에 없거나 실시간 DB 조회가 필요한 경우 카탈로그 직접 쿼리
    # 2-1. 함수/프로시저인지 확인 (pg_proc)
    func_query = f"""
    SELECT p.proname, n.nspname, pg_get_functiondef(p.oid) as src
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE p.proname = '{clean_name}'
    """
    func_res = _run_sql(query=func_query, output_fmt="table")
    if func_res.ok and func_res.data and func_res.data.get("table", {}).get("rows"):
        rows = func_res.data["table"]["rows"]
        lines = []
        for r in rows:
            lines.append(f"### ⚙ 함수/프로시저 정의: `{r.get('proname')}` ({r.get('nspname')})")
            lines.append("```sql")
            lines.append(r.get("src", "").strip())
            lines.append("```")
        return "\n\n".join(lines)

    # 2-2. 뷰인지 확인 (pg_class relkind in ('v', 'm'))
    view_query = f"""
    SELECT c.relname, n.nspname, pg_get_viewdef(c.oid, true) as src
    FROM pg_class c
    JOIN pg_namespace n ON n.oid = c.relnamespace
    WHERE c.relkind IN ('v', 'm') AND c.relname = '{clean_name}'
    """
    view_res = _run_sql(query=view_query, output_fmt="table")
    if view_res.ok and view_res.data and view_res.data.get("table", {}).get("rows"):
        rows = view_res.data["table"]["rows"]
        r = rows[0]
        return f"### 👁 뷰 정의: `{r.get('relname')}` ({r.get('nspname')})\n```sql\n{r.get('src', '').strip()}\n```"

    # 2-3. 테이블 컬럼 정보 fallback
    cols_sql = f"""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_name = '{clean_name}'
    ORDER BY ordinal_position
    """
    return execute_sql(cols_sql, limit=100)


def get_table_schema(table_name: str) -> str:
    """하위 호환성을 위한 별칭: get_db_definition을 호출합니다."""
    return get_db_definition(table_name)


def execute_sql(query: str, limit: int = 20) -> str:
    """PostgreSQL 데이터베이스(asseterpdb)에서 SELECT 쿼리를 안전하게 실행하고 결과를 반환합니다."""
    clean_query = query.strip()
    if not clean_query:
        return "error: 쿼리가 비어 있습니다."

    # psql 메타 커맨드(\\d, \\df, \\ef, \\sf, \\dv 등) 또는 DESCRIBE/DESC 가로채기 (DDL/본체 반환)
    norm = clean_query.rstrip(";")
    lower_norm = norm.lower()
    if lower_norm.startswith(("\\d+", "\\d", "\\df+", "\\df", "\\sf", "\\ef", "\\dv", "describe ", "desc ")):
        parts = norm.split(maxsplit=1)
        if len(parts) > 1:
            obj_name = parts[1].strip()
            return get_db_definition(obj_name)

    res = _run_sql(query=clean_query, limit=limit, output_fmt="table")
    if not res.ok:
        return f"SQL 실행 실패: {res.error}"

    data = res.data or {}
    summary = data.get("summary", "")
    table = data.get("table", {})
    if not table:
        return summary or "조회 결과가 없습니다."

    rows = table.get("rows", [])
    columns = table.get("columns", [])
    total_rows = table.get("total_rows", len(rows))

    if not rows:
        return f"{summary} (조회 결과 0건)"

    # Markdown 테이블 형식으로 렌더링
    header = "| " + " | ".join(str(c) for c in columns) + " |"
    sep = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [f"**쿼리 요약:** `{summary}`", "", header, sep]
    for row in rows:
        row_vals = [str(row.get(c, "")).replace("\n", " ").replace("|", "\\|") for c in columns]
        lines.append("| " + " | ".join(row_vals) + " |")

    if total_rows > len(rows):
        lines.append(f"\n*(총 {total_rows}건 중 상위 {len(rows)}건 표시됨)*")

    return "\n".join(lines)

