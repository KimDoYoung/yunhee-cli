"""mapper 전체를 한 번 해석해 문장 키 → ParsedSql로 캐시한다 (trace-column·trace-crud가 공유).

스키마 스냅샷을 넘겨 한정자 없는 컬럼의 귀속을 풀고, 파라미터 이름은 남긴다(`keep_params`).
디스크 캐시(.yunhee/cache/)와 프로세스 메모리 LRU 캐시를 모두 활용하여 수 초대의 파싱을 밀리초 단위로 단축한다.
"""

from __future__ import annotations

import pickle
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


def _cache_dir() -> Path:
    d = config.WORK_DIR / ".yunhee" / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _dir_stats(path: Path, pattern: str = "*.xml", recursive: bool = True) -> tuple[int, float]:
    """디렉터리 내 패턴 파일들의 (개수, 최신 mtime)."""
    if not path.is_dir():
        return 0, 0.0
    iterator = path.rglob(pattern) if recursive else path.glob(pattern)
    count = 0
    max_mtime = 0.0
    for p in iterator:
        if "target" in p.parts:
            continue
        count += 1
        try:
            m = p.stat().st_mtime
            max_mtime = max(max_mtime, m)
        except OSError:
            pass
    return count, max_mtime


@lru_cache(maxsize=2)
def scan_asis(src_root: str) -> dict[str, ParsedSql]:
    root = Path(src_root)
    count, max_mtime = _dir_stats(root, "*.xml", recursive=True)
    cache_file = _cache_dir() / "scan_asis.pickle"

    if count > 0 and cache_file.is_file():
        try:
            with open(cache_file, "rb") as f:
                cached_meta, cached_data = pickle.load(f)
            if (
                cached_meta.get("count") == count
                and cached_meta.get("max_mtime") == max_mtime
                and cached_meta.get("schema_env") == config.SCHEMA_ENV
            ):
                return cached_data
        except Exception:  # noqa: BLE001, S110
            pass

    from yunhee.tools.as_is.mybatis_render import get_all_statements

    data = _scan(get_all_statements(root))
    if count > 0 and data:
        try:
            meta = {"count": count, "max_mtime": max_mtime, "schema_env": config.SCHEMA_ENV}
            with open(cache_file, "wb") as f:
                pickle.dump((meta, data), f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:  # noqa: BLE001, S110
            pass
    return data


@lru_cache(maxsize=2)
def scan_tobe(mapper_dir: str) -> dict[str, ParsedSql]:
    mdir = Path(mapper_dir)
    if not mdir.is_dir():
        return {}
    count, max_mtime = _dir_stats(mdir, "*.xml", recursive=False)
    cache_file = _cache_dir() / "scan_tobe.pickle"

    if count > 0 and cache_file.is_file():
        try:
            with open(cache_file, "rb") as f:
                cached_meta, cached_data = pickle.load(f)
            if (
                cached_meta.get("count") == count
                and cached_meta.get("max_mtime") == max_mtime
                and cached_meta.get("schema_env") == config.SCHEMA_ENV
            ):
                return cached_data
        except Exception:  # noqa: BLE001, S110
            pass

    from yunhee.tools.as_is.mybatis_render import load_statements

    data = _scan(load_statements(mdir))
    if count > 0 and data:
        try:
            meta = {"count": count, "max_mtime": max_mtime, "schema_env": config.SCHEMA_ENV}
            with open(cache_file, "wb") as f:
                pickle.dump((meta, data), f, protocol=pickle.HIGHEST_PROTOCOL)
        except Exception:  # noqa: BLE001, S110
            pass
    return data


def clear_caches() -> None:
    snapshot_schema.cache_clear()
    scan_asis.cache_clear()
    scan_tobe.cache_clear()
