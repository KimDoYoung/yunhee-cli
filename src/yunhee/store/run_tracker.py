import sqlite3
from datetime import UTC, datetime

from yunhee.store.db import get_connection


def init_db(conn: sqlite3.Connection | None = None) -> None:
    close = False
    if conn is None:
        conn = get_connection()
        close = True

    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS runs (
                id TEXT PRIMARY KEY,
                project TEXT NOT NULL,
                command TEXT NOT NULL,
                exit_code INTEGER NOT NULL,
                duration_ms INTEGER NOT NULL,
                log_path TEXT NOT NULL,
                summary TEXT,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_runs_project_created
            ON runs (project, created_at DESC);
            """
        )
        conn.commit()
    finally:
        if close:
            conn.close()


def save_run(
    run_id: str,
    project: str,
    command: str,
    exit_code: int,
    duration_ms: int,
    log_path: str,
    summary: str | None = None,
    created_at: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> str:
    close = False
    if conn is None:
        conn = get_connection()
        close = True

    init_db(conn)
    ts = created_at or datetime.now(UTC).isoformat()
    try:
        conn.execute(
            """
            INSERT INTO runs (id, project, command, exit_code, duration_ms, log_path, summary, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """,
            (run_id, project, command, exit_code, duration_ms, log_path, summary, ts),
        )
        conn.commit()
        return run_id
    finally:
        if close:
            conn.close()


def get_last_run(project: str, conn: sqlite3.Connection | None = None) -> dict | None:
    close = False
    if conn is None:
        conn = get_connection()
        close = True

    init_db(conn)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT id, project, command, exit_code, duration_ms, log_path, summary, created_at
            FROM runs
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT 1;
            """,
            (project,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if close:
            conn.close()


def list_runs(project: str, limit: int = 10, conn: sqlite3.Connection | None = None) -> list[dict]:
    close = False
    if conn is None:
        conn = get_connection()
        close = True

    init_db(conn)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT id, project, command, exit_code, duration_ms, log_path, summary, created_at
            FROM runs
            WHERE project = ?
            ORDER BY created_at DESC
            LIMIT ?;
            """,
            (project, limit),
        )
        return [dict(row) for row in cur.fetchall()]
    finally:
        if close:
            conn.close()


def get_run(run_id: str, conn: sqlite3.Connection | None = None) -> dict | None:
    close = False
    if conn is None:
        conn = get_connection()
        close = True

    init_db(conn)
    conn.row_factory = sqlite3.Row
    try:
        cur = conn.execute(
            """
            SELECT id, project, command, exit_code, duration_ms, log_path, summary, created_at
            FROM runs
            WHERE id = ?;
            """,
            (run_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None
    finally:
        if close:
            conn.close()
