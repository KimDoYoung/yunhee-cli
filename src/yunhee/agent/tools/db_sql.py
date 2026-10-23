"""yunhee-cli Agent DB SQL Tool.
PostgreSQL 데이터베이스(asseterpdb)에서 SELECT 쿼리를 안전하게 실행하거나
테이블의 DDL 스키마(DBML)를 조회하여 마크다운으로 반환하는 에이전트 전용 도구.
"""

from __future__ import annotations

from yunhee import config
from yunhee.tools.schema_snapshot import load_snapshot, slice_tables
from yunhee.tools.sql_runner import run_sql as _run_sql


def get_table_schema(table_name: str) -> str:
    """지정한 테이블의 DDL 스키마(DBML: 컬럼 목록, 데이터 타입, PK/FK/인덱스, 한글 주석)를 조회합니다."""
    clean_name = table_name.strip().strip("'\"`;")
    if not clean_name:
        return "error: 테이블 이름이 비어 있습니다."

    try:
        snap = load_snapshot(config.SCHEMA_ENV)
        if snap.ok and snap.data:
            res = slice_tables(snap.data, [clean_name])
            if res.ok and res.data and res.data.get("dbml"):
                return f"```dbml\n{res.data['dbml'].strip()}\n```"
    except Exception:  # noqa: BLE001, S110
        pass

    # 스냅샷에 없거나 실패 시 DB information_schema.columns 조회 fallback
    cols_sql = f"""
    SELECT column_name, data_type, is_nullable, column_default
    FROM information_schema.columns
    WHERE table_name = '{clean_name}'
    ORDER BY ordinal_position
    """
    return execute_sql(cols_sql, limit=100)


def execute_sql(query: str, limit: int = 20) -> str:
    """PostgreSQL 데이터베이스(asseterpdb)에서 SELECT 쿼리를 안전하게 실행하고 결과를 반환합니다."""
    clean_query = query.strip()
    if not clean_query:
        return "error: 쿼리가 비어 있습니다."

    # psql 메타 커맨드(\\d, \\d+) 또는 DESCRIBE/DESC 가로채기 (DDL 반환)
    norm = clean_query.rstrip(";")
    lower_norm = norm.lower()
    if lower_norm.startswith(("\\d+", "\\d", "describe ", "desc ")):
        parts = norm.split(maxsplit=1)
        if len(parts) > 1:
            tbl = parts[1].strip()
            return get_table_schema(tbl)

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

