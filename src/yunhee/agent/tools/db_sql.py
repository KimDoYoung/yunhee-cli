"""yunhee-cli Agent DB SQL Tool.
PostgreSQL 데이터베이스(asseterpdb)에서 SELECT 쿼리를 안전하게 실행하여 결과를 마크다운 표로 반환하는 에이전트 전용 도구.
"""

from __future__ import annotations

from yunhee.tools.sql_runner import run_sql as _run_sql


def execute_sql(query: str, limit: int = 20) -> str:
    """PostgreSQL 데이터베이스(asseterpdb)에서 SELECT 쿼리를 안전하게 실행하고 결과를 반환합니다."""
    clean_query = query.strip()
    if not clean_query:
        return "error: 쿼리가 비어 있습니다."

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
