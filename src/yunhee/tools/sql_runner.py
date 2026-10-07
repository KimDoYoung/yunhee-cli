"""PostgreSQL 읽기 전용 조회 및 롤백 실행 도구."""

import os
import re
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

from yunhee import config
from yunhee.tools.base import ToolResult

# 두 모드 모두 막는 문장 (첫 키워드 기준). COMMIT/END/PREPARE TRANSACTION은 실제 저장, DDL은 롤백 대상이 아니라고 본다.
BLOCKED_ALWAYS = {
    "COMMIT", "END", "PREPARE", "CREATE", "ALTER", "DROP", "TRUNCATE",
    "GRANT", "REVOKE", "COMMENT", "REINDEX", "VACUUM", "CLUSTER", "REFRESH",
}
# 기본(읽기 전용) 모드에서 추가로 막는 문장. CALL·DO는 안에서 무엇을 할지 모르므로 무조건 막는다.
WRITE_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "MERGE", "CALL", "DO", "COPY", "LOCK"}
# 기본 모드에서 막는 트랜잭션 제어문 (ROLLBACK·SAVEPOINT·SET은 허용)
TX_CONTROL = {"BEGIN", "START", "RELEASE"}
WITH_WRITE_RE = re.compile(r"[()]\s*(INSERT|UPDATE|DELETE|MERGE)\b", re.IGNORECASE)
READ_WRITE_SET_RE = re.compile(r"read_only|READ\s+WRITE|SESSION\s+CHARACTERISTICS", re.IGNORECASE)
PROC_TX_RE = re.compile(r"\b(COMMIT|ROLLBACK)\b", re.IGNORECASE)
READ_ONLY_HINT = "읽기 전용 모드입니다. 쓰기 시험은 --rollback"


def split_statements(sql: str) -> list[str]:
    """주석과 문자열을 고려하여 세미콜론 및 \\gset 기준으로 SQL 문장들을 분리한다."""
    statements: list[str] = []
    cur: list[str] = []
    i = 0
    n = len(sql)
    in_str = None
    in_line_comment = False
    in_block_comment = False

    while i < n:
        c = sql[i]
        c2 = sql[i:i + 2]

        if in_line_comment:
            if c == "\n":
                in_line_comment = False
            cur.append(c)
            i += 1
            continue

        if in_block_comment:
            if c2 == "*/":
                in_block_comment = False
                cur.append(c2)
                i += 2
                continue
            cur.append(c)
            i += 1
            continue

        if in_str:
            if c == in_str:
                if i + 1 < n and sql[i + 1] == in_str:
                    cur.append(in_str * 2)
                    i += 2
                    continue
                in_str = None
            cur.append(c)
            i += 1
            continue

        if c2 == "--":
            in_line_comment = True
            cur.append(c2)
            i += 2
            continue

        if c2 == "/*":
            in_block_comment = True
            cur.append(c2)
            i += 2
            continue

        if c in ("'", '"'):
            in_str = c
            cur.append(c)
            i += 1
            continue

        if c == "\n":
            buf_str = "".join(cur)
            if "\\gset" in buf_str:
                stmt = buf_str.strip()
                if stmt:
                    statements.append(stmt)
                cur = []
                i += 1
                continue

        if c == ";":
            stmt = "".join(cur).strip()
            if stmt:
                statements.append(stmt)
            cur = []
            i += 1
            continue

        cur.append(c)
        i += 1

    last = "".join(cur).strip()
    if last:
        statements.append(last)

    return statements


def strip_sql_comments(sql: str) -> str:
    """주석을 제거한 순수 SQL 텍스트를 반환한다."""
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    return sql.strip()


def first_keyword(stmt: str) -> str:
    """주석·여는 괄호를 건너뛴 문장의 첫 키워드(대문자)."""
    bare = strip_sql_comments(re.sub(r"\\gset\b.*", "", stmt, flags=re.DOTALL)).lstrip("( \t\r\n")
    m = re.match(r"[A-Za-z_]+", bare)
    return m.group(0).upper() if m else ""


def _mask_strings(sql: str) -> str:
    """'...' 문자열 리터럴 내용을 비워 키워드 오탐을 막는다."""
    return re.sub(r"'(?:[^']|'')*'", "''", sql)


def guard_statement(stmt: str, rollback: bool) -> str | None:
    """실행 전 안전 가드. 막아야 하면 오류 문구, 아니면 None."""
    kw = first_keyword(stmt)
    if not kw:
        return None
    if kw in BLOCKED_ALWAYS:
        mode = "--rollback 모드" if rollback else "읽기 전용 모드"
        return f"안전 가드: {mode}에서는 '{kw}' 문장(COMMIT/END/DDL)을 실행할 수 없습니다."
    if rollback:
        return None
    if kw in WRITE_KEYWORDS:
        return f"안전 가드: '{kw}' — {READ_ONLY_HINT}"
    if kw in TX_CONTROL:
        return f"안전 가드: 읽기 전용 모드에서는 '{kw}' 트랜잭션 제어문을 실행할 수 없습니다 (ROLLBACK·SAVEPOINT·SET만 허용)."
    bare = _mask_strings(strip_sql_comments(stmt))
    if kw == "SET" and READ_WRITE_SET_RE.search(bare):
        return f"안전 가드: 읽기 전용 설정을 바꾸는 SET은 실행할 수 없습니다 — {READ_ONLY_HINT}"
    if kw == "WITH":
        m = WITH_WRITE_RE.search(bare)
        if m:
            return f"안전 가드: WITH 안의 '{m.group(1).upper()}' — {READ_ONLY_HINT}"
    return None


def proc_has_tx_control(cur: Any, stmt: str) -> str | None:
    """CALL 대상 프로시저 본문(pg_proc.prosrc)에 COMMIT/ROLLBACK이 있으면 프로시저 이름을 반환한다.

    프로시저 안의 COMMIT은 바깥 ROLLBACK으로 되돌릴 수 없으므로 --rollback 모드에서 실행 전에 거부한다.
    """
    m = re.match(r"\s*CALL\s+(?:\"?(\w+)\"?\.)?\"?(\w+)\"?", strip_sql_comments(stmt), re.IGNORECASE)
    if not m:
        return None
    schema, name = m.group(1), m.group(2).lower()
    query = "SELECT p.prosrc FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace WHERE p.proname = %s"
    params: list[Any] = [name]
    if schema:
        query += " AND n.nspname = %s"
        params.append(schema.lower())
    cur.execute(query, params)
    for row in cur.fetchall():
        src = row["prosrc"] if isinstance(row, dict) else row[0]
        if src and PROC_TX_RE.search(strip_sql_comments(src)):
            return name
    return None


def get_connection_string(db_name: str | None = None) -> str | None:
    """DB 연결 문자열을 환경변수 또는 config에서 가져온다."""
    db_url = None
    if db_name:
        db_url = os.getenv(db_name) or (db_name if "://" in db_name else None)
    if not db_url:
        db_url = config.LOCAL_DB or os.getenv("LOCAL_DB") or os.getenv("TEST_DB")
    return db_url


def run_sql(
    query: str | None = None,
    file_path: Path | None = None,
    rollback: bool = False,
    limit: int = 5,
    timeout: float = 10.0,
    vars_dict: dict[str, Any] | None = None,
    db_name: str | None = None,
) -> ToolResult:
    """PostgreSQL 쿼리를 읽기 전용 또는 롤백 모드로 안전하게 실행한다."""
    if not query and not file_path:
        return ToolResult(ok=False, error="실행할 SQL 쿼리 문자열이나 파일(-f)을 지정해야 합니다.")

    raw_script = query or ""
    if file_path:
        if not file_path.is_file():
            return ToolResult(ok=False, error=f"SQL 파일을 찾을 수 없습니다: {file_path}")
        raw_script = file_path.read_text(encoding="utf-8", errors="replace")

    raw_script = raw_script.strip()
    if not raw_script:
        return ToolResult(ok=False, error="실행할 SQL 내용이 비어 있습니다.")

    db_url = get_connection_string(db_name)
    if not db_url:
        return ToolResult(
            ok=False,
            error="DB 접속 URL이 설정되지 않았습니다. .env.local의 LOCAL_DB를 확인하세요.",
        )

    stmts = split_statements(raw_script)
    if not stmts:
        return ToolResult(ok=False, error="실행할 유효한 SQL 문장이 없습니다.")

    # 안전 가드 (두 모드 공통): DB에 맡기기 전에 실행 전 거부한다.
    for stmt in stmts:
        err = guard_statement(stmt, rollback)
        if err:
            return ToolResult(ok=False, error=err)

    variables: dict[str, Any] = dict(vars_dict or {})

    output_lines: list[str] = []
    last_table_data: dict[str, Any] | None = None

    try:
        conn = psycopg.connect(db_url, autocommit=False)
    except Exception as exc:  # noqa: BLE001
        # 비밀번호 등 접속 정보 마스킹
        return ToolResult(ok=False, error=f"DB 접속 실패: {exc}")

    # 첫 execute 전에 걸어야 첫 트랜잭션부터 BEGIN READ ONLY로 열린다.
    # (SET default_transaction_read_only는 이미 열린 트랜잭션에는 적용되지 않는다)
    if not rollback:
        conn.read_only = True

    try:
        with conn.cursor(row_factory=dict_row) as cur:
            # 타임아웃 설정
            timeout_ms = int(timeout * 1000)
            cur.execute(f"SET statement_timeout = '{timeout_ms}ms'")

            # 사전 변수 정의 중 쿼리인 것 실행 (예: cid="select f_create_seq()")
            for v_name, v_val in list(variables.items()):
                if isinstance(v_val, str) and re.match(r"^\s*select\b", v_val, re.IGNORECASE):
                    cur.execute(v_val)
                    row = cur.fetchone()
                    if row:
                        variables[v_name] = next(iter(row.values()))

            for stmt in stmts:
                is_gset = False
                gset_m = re.search(r"\\gset\b", stmt)
                clean_stmt = stmt
                if gset_m:
                    is_gset = True
                    clean_stmt = stmt[:gset_m.start()].strip()

                # 변수 치환 (:name 형태)
                for v_name, v_val in variables.items():
                    clean_stmt = re.sub(rf":{re.escape(v_name)}\b", str(v_val), clean_stmt)

                bare = strip_sql_comments(clean_stmt)
                if not bare:
                    continue

                if rollback and first_keyword(bare) == "CALL":
                    proc = proc_has_tx_control(cur, bare)
                    if proc:
                        return ToolResult(
                            ok=False,
                            error=f"안전 가드: 프로시저 {proc} 안에 COMMIT/ROLLBACK이 있어 --rollback으로 되돌릴 수 없습니다. 실행하지 않았습니다.",
                        )

                cur.execute(clean_stmt)

                if is_gset:
                    row = cur.fetchone()
                    if row:
                        for col_k, col_v in row.items():
                            variables[col_k] = col_v
                            output_lines.append(f"\\gset: {col_k}={col_v}")
                    continue

                upper = bare.split(None, 1)[0].upper()
                if upper == "INSERT":
                    output_lines.append(f"INSERT {cur.rowcount}")
                elif upper == "UPDATE":
                    output_lines.append(f"UPDATE {cur.rowcount}")
                elif upper == "DELETE":
                    output_lines.append(f"DELETE {cur.rowcount}")
                elif upper == "CALL":
                    output_lines.append("CALL ok")
                elif upper == "SELECT" or cur.description:
                    rows = cur.fetchall()
                    total_rows = len(rows)
                    preview_rows = rows[:limit]
                    cols = [desc.name for desc in cur.description] if cur.description else []
                    last_table_data = {
                        "total_rows": total_rows,
                        "columns": cols,
                        "rows": preview_rows,
                        "limit": limit,
                    }
                else:
                    output_lines.append(f"{upper} ok")

    except Exception as exc:  # noqa: BLE001
        try:
            conn.rollback()
        except Exception:  # noqa: BLE001, S110
            pass
        return ToolResult(ok=False, error=f"SQL 실행 오류: {exc}")
    finally:
        try:
            conn.rollback()
            conn.close()
        except Exception:  # noqa: BLE001, S110
            pass

    # 결과 표 렌더링
    table_str = ""
    if last_table_data:
        tot = last_table_data["total_rows"]
        cols = last_table_data["columns"]
        p_rows = last_table_data["rows"]

        if len(stmts) == 1 and tot == 1 and len(cols) == 1:
            # rows=1 count=12 형태의 단발성 요약
            col_name = cols[0]
            val = p_rows[0][col_name]
            table_str = f"rows=1  {col_name}={val}"
        else:
            # 마크다운 표 형태
            hdr = "| " + " | ".join(cols) + " |"
            sep = "| " + " | ".join(["---"] * len(cols)) + " |"
            r_lines = [hdr, sep]
            for r in p_rows:
                r_lines.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
            if tot > len(p_rows):
                r_lines.append(f"(총 {tot}행 중 {len(p_rows)}행만 표시)")
            table_str = f"rows={tot}\n" + "\n".join(r_lines)

    result_parts = []
    if rollback:
        result_parts.append("BEGIN … ROLLBACK")
    if output_lines:
        result_parts.extend(output_lines)
    if table_str:
        result_parts.append(table_str)
    if rollback:
        result_parts.append("남은 변경 없음")

    return ToolResult(
        ok=True,
        data={
            "summary": "\n".join(result_parts),
            "table": last_table_data,
        },
    )
