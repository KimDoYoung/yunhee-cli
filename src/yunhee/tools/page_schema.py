"""ASIS 페이지 → 그 페이지 mapper SQL이 참조하는 테이블 목록 (mapper_index 기반, qwen 호출 없음)."""

import sqlite3
from collections import Counter

from yunhee.store.db import DB_PATH
from yunhee.tools.base import ToolResult
from yunhee.tools.legacy_page import find_page_mapper_paths


def page_tables(page_code: str) -> ToolResult:
    """페이지의 mapper XML들에 속한 statement의 `tables`를 모아, 많이 참조된 순으로 반환한다.

    `tables`는 parse_mapper.py의 정규식 휴리스틱 결과라 CTE 별칭 등 실존하지 않는 이름이 섞일 수 있다
    — 스키마 스냅샷과 대조해서 걸러내는 건 호출하는 쪽 몫.
    """
    paths = find_page_mapper_paths(page_code)
    if not paths.ok:
        return paths
    if not paths.data:
        return ToolResult(ok=False, error=f"페이지 '{page_code}'에 mapper XML이 없습니다.")
    if not DB_PATH.exists():
        return ToolResult(ok=False, error="mapper_index 없음 — `uv run tools/parse_mapper.py` 실행 필요.")

    conn = sqlite3.connect(DB_PATH)
    try:
        placeholders = ",".join("?" * len(paths.data))
        rows = conn.execute(
            f"SELECT tables FROM mapper_index WHERE file_path IN ({placeholders})", paths.data
        ).fetchall()
    except sqlite3.OperationalError:
        return ToolResult(ok=False, error="mapper_index 없음 — `uv run tools/parse_mapper.py` 실행 필요.")
    finally:
        conn.close()

    counter = Counter(name for (tables,) in rows if tables for name in tables.split(","))
    ranked = sorted(counter, key=lambda name: (-counter[name], name))
    return ToolResult(ok=True, data=ranked)
