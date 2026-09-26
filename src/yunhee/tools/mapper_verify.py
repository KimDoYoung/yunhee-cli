"""mapper_index 기반 grounding 검증 + staleness 체크.

grounding: qwen 요약에서 추출한 (mapper_name, sql_id) 쌍이 실제 DB에 존재하는지 확인.
staleness: 마지막 인덱싱 이후 ASIS 소스가 변경됐는지 확인.

mapper_index가 없을 때는 조용히 skip (None 반환) — DB 미빌드 환경에서도 동작 유지.
"""

import os
import re
import sqlite3

from yunhee.config import ASIS_SRC_DIR
from yunhee.store.db import DB_PATH

# "## 이벤트 및 서버 호출" 섹션에서 namespace.sqlId 패턴 추출
# GXT 관례: mapper_name = 소문자+밑줄 (ast01_class_tree), sql_id = camelCase or underscore
_MAPPER_REF_RE = re.compile(
    r'\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\.([a-zA-Z][a-zA-Z0-9_]*)\b'
)


def _open_db() -> sqlite3.Connection | None:
    """mapper_index 테이블이 있는 DB 연결 반환. 없으면 None."""
    if not DB_PATH.exists():
        return None
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='mapper_index'"
    )
    if cur.fetchone() is None:
        conn.close()
        return None
    return conn


def extract_mapper_refs(summary: str) -> list[tuple[str, str]]:
    """요약 텍스트에서 (mapper_name, sql_id) 쌍을 추출한다.

    "이벤트 및 서버 호출" 섹션에 국한하지 않고 전체에서 추출해 노이즈를 최소화.
    중복 제거 후 반환.
    """
    refs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for m in _MAPPER_REF_RE.finditer(summary):
        pair = (m.group(1), m.group(2))
        if pair not in seen:
            seen.add(pair)
            refs.append(pair)
    return refs


def verify_mapper_refs(
    refs: list[tuple[str, str]],
) -> list[tuple[str, str, list[str]]]:
    """refs 중 mapper_index에 없는 항목을 반환한다.

    반환: list of (mapper_name, sql_id, actual_sql_ids)
      actual_sql_ids: 해당 mapper_name에 실제로 존재하는 sql_id 목록.
                      mapper_name 자체가 없으면 빈 리스트.
    mapper_index가 없으면 빈 리스트 반환 (grounding 패스 skip).
    """
    if not refs:
        return []
    conn = _open_db()
    if conn is None:
        return []

    invalid: list[tuple[str, str, list[str]]] = []
    try:
        cur = conn.cursor()
        for mapper_name, sql_id in refs:
            cur.execute(
                "SELECT COUNT(*) FROM mapper_index WHERE mapper_name=? AND sql_id=?",
                (mapper_name, sql_id),
            )
            if cur.fetchone()[0] == 0:
                cur.execute(
                    "SELECT sql_id FROM mapper_index WHERE mapper_name=? ORDER BY sql_id",
                    (mapper_name,),
                )
                actual = [row[0] for row in cur.fetchall()]
                invalid.append((mapper_name, sql_id, actual))
    finally:
        conn.close()

    return invalid


def check_staleness() -> tuple[bool, str]:
    """mapper_index가 ASIS 소스보다 오래됐으면 (True, 경고 메시지) 반환.

    stale 기준: ASIS mapper/*.xml 중 가장 최근 mtime > 마지막 인덱싱 시각.
    mapper_index_meta 테이블이 없으면 (True, "인덱스 미빌드") 반환.
    """
    conn = _open_db()
    if conn is None:
        return True, "mapper_index 없음 — `uv run tools/parse_mapper.py` 실행 필요."

    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='mapper_index_meta'"
        )
        if cur.fetchone() is None:
            return True, "mapper_index_meta 없음 — `uv run tools/parse_mapper.py` 재실행 필요."

        cur.execute("SELECT built_at FROM mapper_index_meta WHERE key='built_at'")
        row = cur.fetchone()
        if row is None:
            return True, "빌드 타임스탬프 없음 — `uv run tools/parse_mapper.py` 재실행 필요."
        built_at: float = row[0]
    finally:
        conn.close()

    if not ASIS_SRC_DIR.is_dir():
        return False, ""

    newest_mtime = 0.0
    for root, dirs, files in os.walk(ASIS_SRC_DIR):
        dirs[:] = [d for d in dirs if d != "target"]
        if os.path.basename(root) != "mapper":
            continue
        for filename in files:
            if filename.endswith(".xml"):
                mtime = os.path.getmtime(os.path.join(root, filename))
                newest_mtime = max(newest_mtime, mtime)

    if newest_mtime > built_at:
        import datetime
        built_dt = datetime.datetime.fromtimestamp(built_at, tz=datetime.UTC).strftime("%Y-%m-%d %H:%M")
        return True, f"ASIS 소스가 인덱스({built_dt} UTC) 이후 변경됨 — `uv run tools/parse_mapper.py` 재실행 권장."

    return False, ""
