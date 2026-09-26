"""ASIS(AssetERP) MyBatis mapper XML 전체를 스캔해서 mapperName+sqlId+참조 테이블 인덱스를 sqlite에 만든다.

한 번(혹은 ASIS 소스가 바뀔 때마다) 실행해두면, context/analyzer.py의 요약 grounding 검증 패스가
qwen이 만들어낸 mapperName/sqlId/테이블명이 실제로 존재하는지 이 인덱스로 조회할 수 있다.

실행: uv run tools/parse_mapper.py
"""

import os
import re
import xml.etree.ElementTree as ET

from yunhee.config import ASIS_SRC_DIR
from yunhee.store.db import get_connection

STATEMENT_TAGS = {"select", "insert", "update", "delete", "sql"}

TABLE_RE = re.compile(r"\b(?:from|join|into|update)\s+([a-zA-Z_][a-zA-Z0-9_]*)", re.IGNORECASE)


def _extract_tables(sql_text: str) -> list[str]:
    names = {m.group(1).lower() for m in TABLE_RE.finditer(sql_text)}
    # 테이블은 이 프로젝트 관례상 전부 밑줄 포함 소문자(act01_journal 등) - SQL 키워드/별칭 노이즈를 걸러낸다.
    return sorted(n for n in names if "_" in n)


def _parse_mapper_file(path: str) -> list[tuple[str, str, str, str]]:
    root = ET.parse(path).getroot()
    namespace = root.get("namespace", "")
    rows = []
    for el in root.iter():
        if el.tag not in STATEMENT_TAGS:
            continue
        sql_id = el.get("id")
        if not sql_id:
            continue
        sql_text = "".join(el.itertext())
        tables = _extract_tables(sql_text)
        rows.append((namespace, sql_id, el.tag, ",".join(tables)))
    return rows


def build_index() -> int:
    if not ASIS_SRC_DIR.is_dir():
        raise SystemExit(f"ASIS 소스 경로를 찾을 수 없습니다: {ASIS_SRC_DIR}")

    conn = get_connection()
    conn.execute("DROP TABLE IF EXISTS mapper_index")
    conn.execute(
        """
        CREATE TABLE mapper_index (
            mapper_name TEXT NOT NULL,
            sql_id      TEXT NOT NULL,
            sql_type    TEXT NOT NULL,
            tables      TEXT,
            file_path   TEXT NOT NULL,
            PRIMARY KEY (mapper_name, sql_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mapper_index_meta (
            key   TEXT PRIMARY KEY,
            built_at REAL NOT NULL
        )
        """
    )

    count = 0
    skipped = 0
    for root_dir, dirs, files in os.walk(ASIS_SRC_DIR):
        dirs[:] = [d for d in dirs if d != "target"]
        if os.path.basename(root_dir) != "mapper":
            continue
        for filename in files:
            if not filename.endswith(".xml"):
                continue
            path = os.path.join(root_dir, filename)
            try:
                rows = _parse_mapper_file(path)
            except ET.ParseError as e:
                print(f"경고: 파싱 실패, 건너뜀 - {path} ({e})")
                skipped += 1
                continue

            rel_path = os.path.relpath(path, ASIS_SRC_DIR)
            for namespace, sql_id, sql_type, tables in rows:
                conn.execute(
                    "INSERT OR REPLACE INTO mapper_index VALUES (?, ?, ?, ?, ?)",
                    (namespace, sql_id, sql_type, tables, rel_path),
                )
                count += 1
    import time
    conn.execute(
        "INSERT OR REPLACE INTO mapper_index_meta (key, built_at) VALUES ('built_at', ?)",
        (time.time(),),
    )
    conn.commit()
    conn.close()

    if skipped:
        print(f"파싱 실패 {skipped}개 파일 건너뜀")
    return count


if __name__ == "__main__":
    total = build_index()
    print(f"인덱싱 완료: SQL statement {total}개")
