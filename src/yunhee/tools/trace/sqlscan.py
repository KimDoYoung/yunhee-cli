"""mapper 전체를 한 번 해석해 문장 키 → ParsedSql로 캐시한다 (trace-column·trace-crud가 공유).

스키마 스냅샷을 넘겨 한정자 없는 컬럼의 귀속을 풀고, 파라미터 이름은 남긴다(`keep_params`).
mapper 3,000여 개 해석에 4초쯤 걸리므로 프로세스 안에서 캐시한다.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from yunhee import config
from yunhee.tools.schema_snapshot import load_snapshot
from yunhee.tools.sql_parse import ParsedSql, parse_statement, schema_from_snapshot


@lru_cache(maxsize=2)
def snapshot_schema(env: str) -> dict[str, list[str]] | None:
    snap = load_snapshot(env)
    return schema_from_snapshot(snap.data) if snap.ok else None


def _scan(statements: dict) -> dict[str, ParsedSql]:
    schema = snapshot_schema(config.SCHEMA_ENV)
    out: dict[str, ParsedSql] = {}
    for key in sorted({s.key for s in statements.values() if s.kind != "sql"}):
        res = parse_statement(key, statements, schema, keep_params=True)
        if res.ok:
            out[key] = res.data
    return out


@lru_cache(maxsize=2)
def scan_asis(src_root: str) -> dict[str, ParsedSql]:
    from yunhee.tools.as_is.mybatis_render import get_all_statements

    return _scan(get_all_statements(Path(src_root)))


@lru_cache(maxsize=2)
def scan_tobe(mapper_dir: str) -> dict[str, ParsedSql]:
    from yunhee.tools.as_is.mybatis_render import load_statements

    return _scan(load_statements(Path(mapper_dir))) if Path(mapper_dir).is_dir() else {}


def clear_caches() -> None:
    snapshot_schema.cache_clear()
    scan_asis.cache_clear()
    scan_tobe.cache_clear()
