"""trace-* 명령용 읽기 전용 DB 조회. DB는 사무실에서만 접근할 수 있으므로 실패는 예외가 아니라 unresolved로 다룬다."""

from __future__ import annotations

from typing import Any

MAX_ROWS = 200


class DbUnavailable(Exception):
    """DB 접속 정보가 없거나 접속·조회에 실패했을 때."""


def fetch(sql: str, params: tuple[Any, ...] = (), limit: int = MAX_ROWS, timeout_ms: int = 10_000) -> list[tuple]:
    """읽기 전용 세션에서 SELECT만 실행한다. 값은 반드시 params로 넘긴다 (문자열 이어 붙이기 금지)."""
    import psycopg

    from yunhee.tools.sql_runner import get_connection_string

    if not sql.lstrip().lower().startswith(("select", "with")):
        raise ValueError("SELECT 문만 실행할 수 있습니다")
    url = get_connection_string(None)
    if not url:
        raise DbUnavailable("DB 접속 정보(YUNHEE_DB)가 없음")
    try:
        with psycopg.connect(url, connect_timeout=5) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(f"SET statement_timeout = {int(timeout_ms)}")
                cur.execute(sql, params)
                return cur.fetchmany(limit)
    except Exception as exc:
        raise DbUnavailable(f"{type(exc).__name__}: {str(exc)[:100]}") from exc
