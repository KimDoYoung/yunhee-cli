"""TOBE MyBatis 매퍼 statement 실행 및 AS-IS SQL 비교 도구."""

import sys
from pathlib import Path

import psycopg

from yunhee import config
from yunhee.tools.as_is.mybatis_render import (
    STATEMENT_TAGS,
    Node,
    get_all_statements,
    parse_xml,
    render_from_xml,
)
from yunhee.tools.as_is.mybatis_render import (
    render as mr_render,
)
from yunhee.tools.as_is.sql_porter import find_mapper_file
from yunhee.tools.base import ToolResult
from yunhee.tools.sql_runner import get_connection_string


def run_mapper_statement(
    target: str,
    params: dict[str, str] | None = None,
    db_name: str = "asseterpdb",
    compare_sql: str | None = None,
    count_only: bool = False,
    limit_rows: int | None = None,
    rollback: bool = False,
    src_root: Path | None = None,
) -> ToolResult:
    """TOBE 매퍼 statement를 실행하고 필요한 경우 AS-IS SQL과 결과를 비교한다."""
    if "#" not in target:
        return ToolResult(
            ok=False,
            error=f"매퍼 파일과 statement id는 #으로 구분해야 합니다. 예: mapper.xml#statementId (입력: {target})",
        )

    file_part, sid = target.split("#", 1)
    file_part = file_part.strip()
    sid = sid.strip()

    # 파일 경로 해결 (절대 경로 또는 WORK_DIR 상대)
    mapper_path = Path(file_part)
    if not mapper_path.is_absolute():
        cand1 = config.WORK_DIR / file_part
        cand2 = Path.cwd() / file_part
        cand3 = config.TOBE_SRC_DIR / file_part if getattr(config, "TOBE_SRC_DIR", None) else None
        cand4 = config.ASIS_SRC_DIR / file_part if getattr(config, "ASIS_SRC_DIR", None) else None
        if cand1.is_file():
            mapper_path = cand1
        elif cand2.is_file():
            mapper_path = cand2
        elif cand3 and cand3.is_file():
            mapper_path = cand3
        elif cand4 and cand4.is_file():
            mapper_path = cand4
        else:
            mapper_path = cand1

    if not mapper_path.is_file():
        return ToolResult(ok=False, error=f"매퍼 파일을 찾을 수 없습니다: {mapper_path}")

    raw_xml = mapper_path.read_text(encoding="utf-8", errors="replace")
    root = parse_xml(raw_xml)
    mapper_node = next((c for c in root.children if isinstance(c, Node) and c.tag == "mapper"), None)
    if not mapper_node:
        return ToolResult(ok=False, error=f"유효한 <mapper> 태그가 없습니다: {mapper_path}")

    target_node: Node | None = None
    target_tag = ""
    for child in mapper_node.children:
        if isinstance(child, Node) and child.tag in STATEMENT_TAGS and child.attrs.get("id") == sid:
            target_node = child
            target_tag = child.tag
            break

    if not target_node:
        return ToolResult(ok=False, error=f"statement '{sid}'를 찾을 수 없습니다: {mapper_path}")

    # 쓰기 statement 안전 가드
    if target_tag in ("insert", "update", "delete") and not rollback:
        return ToolResult(
            ok=False,
            error="쓰기 statement(insert/update/delete)는 --rollback 옵션이 필요합니다.",
        )

    params_dict = dict(params or {})

    # TOBE SQL 렌더링
    try:
        tobe_sql, missing = render_from_xml(raw_xml, sid, params=params_dict, mode="params")
        for m_p in missing:
            sys.stderr.write(f"⚠ 값 없음: {m_p}\n")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"TOBE SQL 렌더링 실패: {exc}")

    conn_str = get_connection_string(db_name)
    if not conn_str:
        return ToolResult(ok=False, error="DB 접속 정보를 찾을 수 없습니다.")

    # TOBE 실행
    tobe_rows: list[tuple] = []
    tobe_cols: list[str] = []
    tobe_affected = 0
    try:
        with psycopg.connect(conn_str, autocommit=False) as conn:
            if not rollback:
                conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(tobe_sql)
                if target_tag == "select":
                    tobe_rows = cur.fetchall()
                    tobe_cols = [desc[0] for desc in cur.description] if cur.description else []
                else:
                    tobe_affected = cur.rowcount
            if rollback:
                conn.rollback()
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"TOBE SQL 실행 실패: {exc}\n실행 SQL: {tobe_sql}")

    tobe_count = len(tobe_rows) if target_tag == "select" else tobe_affected

    # --compare 처리
    if compare_sql:
        if "." not in compare_sql:
            return ToolResult(ok=False, error=f"AS-IS SQL ID는 namespace.sqlId 형식이어야 합니다: {compare_sql}")

        c_ns, c_sid = compare_sql.split(".", 1)
        try:
            stmts = get_all_statements(src_root)
            if compare_sql in stmts or any(s.sid == c_sid for s in stmts.values()):
                asis_sql, c_missing = mr_render(compare_sql, params=params_dict, mode="params", statements=stmts)
                for m_p in c_missing:
                    sys.stderr.write(f"⚠ AS-IS 값 없음: {m_p}\n")
            else:
                xml_path = find_mapper_file(c_ns, src_root)
                if not xml_path:
                    return ToolResult(ok=False, error=f"AS-IS 매퍼 XML을 찾을 수 없습니다: namespace={c_ns}")
                xml_text = xml_path.read_text(encoding="utf-8", errors="replace")
                asis_sql, c_missing = render_from_xml(xml_text, c_sid, params=params_dict, mode="params")
                for m_p in c_missing:
                    sys.stderr.write(f"⚠ AS-IS 값 없음: {m_p}\n")
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"AS-IS SQL 렌더링 실패: {exc}")

        asis_rows: list[tuple] = []
        try:
            with psycopg.connect(conn_str, autocommit=False) as conn:
                conn.read_only = True
                with conn.cursor() as cur:
                    cur.execute(asis_sql)
                    asis_rows = cur.fetchall()
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"AS-IS SQL 실행 실패: {exc}\n실행 SQL: {asis_sql}")

        asis_count = len(asis_rows)
        match = (tobe_count == asis_count)
        mark = "✅" if match else "❌"

        col_str = " ".join(tobe_cols)
        summary = f"TOBE rows={tobe_count}, AS-IS rows={asis_count} {mark}  열: {col_str} (TOBE ⊇ 그리드 열)"
        return ToolResult(
            ok=match,
            data={
                "summary": summary,
                "tobe_rows": tobe_count,
                "asis_rows": asis_count,
                "match": match,
                "cols": tobe_cols,
                "tobe_sql": tobe_sql,
                "asis_sql": asis_sql,
            },
        )

    # compare가 없는 경우 단독 실행 결과 출력
    if target_tag != "select":
        summary = f"{target_tag.upper()} {tobe_affected}{' (롤백됨)' if rollback else ''}"
        return ToolResult(
            ok=True,
            data={"summary": summary, "affected": tobe_affected, "sql": tobe_sql},
        )

    if count_only:
        summary = f"rows={tobe_count}"
        return ToolResult(ok=True, data={"summary": summary, "count": tobe_count, "sql": tobe_sql})

    # select 결과 포맷팅
    lines = [f"rows={tobe_count}"]
    if tobe_cols:
        lines.append("| " + " | ".join(tobe_cols) + " |")
        lines.append("| " + " | ".join(["---"] * len(tobe_cols)) + " |")
        limit = limit_rows if limit_rows is not None else 10
        for r in tobe_rows[:limit]:
            row_vals = [str(v) if v is not None else "None" for v in r]
            lines.append("| " + " | ".join(row_vals) + " |")
        if tobe_count > limit:
            lines.append(f"(총 {tobe_count}행 중 {limit}행만 표시)")

    summary = "\n".join(lines)
    return ToolResult(
        ok=True,
        data={
            "summary": summary,
            "rows": tobe_count,
            "cols": tobe_cols,
            "sql": tobe_sql,
        },
    )
