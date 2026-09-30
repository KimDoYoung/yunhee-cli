"""`make-dbml`이 저장한 스키마 스냅샷(JSON)을 읽어 필요한 테이블만 DBML로 잘라낸다 (DB 접속 없음).

스냅샷 위치는 WORK_DIR이 아니라 YUNHEE_DIR/data/schema/<ENV_NAME>.json — AssetERP DB 스키마는 작업 대상 프로젝트와
무관하게 하나라서, 어느 폴더에서 yunhee를 실행하든 같은 스냅샷을 찾을 수 있어야 한다.
"""

import json
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import Path

from yunhee.config import YUNHEE_DIR
from yunhee.dbml import render_dbml
from yunhee.tools.base import ToolResult

SNAPSHOT_DIR = YUNHEE_DIR / "data" / "schema"

# 잘라낸 DBML의 문자 예산. 한 테이블 블록이 보통 1~3천 자(한글 코멘트 포함)라 10~20개 테이블 분량.
SCHEMA_CHAR_LIMIT = 30000


def snapshot_path(env_name: str) -> Path:
    return SNAPSHOT_DIR / f"{env_name}.json"


def save_snapshot(env_name: str, schema: dict) -> Path:
    path = snapshot_path(env_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {**schema, "env_name": env_name, "generated_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    path.write_text(json.dumps(data, ensure_ascii=False, default=str))
    return path


def load_snapshot(env_name: str) -> ToolResult:
    path = snapshot_path(env_name)
    if not path.exists():
        return ToolResult(
            ok=False, error=f"스키마 스냅샷이 없습니다: {path} (먼저 'yunhee make-dbml {env_name}' 실행)"
        )
    return ToolResult(ok=True, data=json.loads(path.read_text()))


def _matches(table: dict, pattern: str) -> bool:
    """pattern: 'table' 또는 'schema.table', glob(*, ?) 허용, 대소문자 무시."""
    pattern = pattern.lower()
    target = f"{table['schema']}.{table['name']}" if "." in pattern else table["name"]
    return fnmatchcase(target.lower(), pattern)


def slice_tables(snapshot: dict, patterns: list[str], char_limit: int = SCHEMA_CHAR_LIMIT) -> ToolResult:
    """patterns 순서대로 매칭되는 테이블을 모아 DBML로 렌더링한다.

    순서가 곧 우선순위 — 예산(char_limit)을 넘으면 뒤쪽 테이블부터 빠지고 truncated=True.
    data: {"dbml", "tables"(포함된 이름), "omitted"(예산 초과로 빠진 이름), "missing"(매칭 0건인 패턴)}
    """
    selected: list[dict] = []
    seen: set[tuple[str, str]] = set()
    missing: list[str] = []
    for pattern in patterns:
        hits = [t for t in snapshot["tables"] if _matches(t, pattern)]
        if not hits:
            missing.append(pattern)
        for t in hits:
            key = (t["schema"], t["name"])
            if key not in seen:
                seen.add(key)
                selected.append(t)

    def outgoing(t: dict) -> list[dict]:
        return [r for r in snapshot["refs"] if (r["schema"], r["table"]) == (t["schema"], t["name"])]

    included: list[dict] = []
    omitted: list[str] = []
    total = 0
    for t in selected:
        # 테이블 블록 + 그 테이블에서 나가는 Ref 줄까지 예산에 포함
        size = len(render_dbml({"enums": [], "tables": [t], "refs": outgoing(t)}))
        if total + size > char_limit:
            omitted.append(t["name"])
            continue
        included.append(t)
        total += size

    # 포함된 테이블에서 나가는 FK만. 대상이 slice 밖이면 render_dbml이 주석으로 남긴다.
    refs = [r for t in included for r in outgoing(t)]
    types = {c["type"] for t in included for c in t["columns"]}
    enums = [e for e in snapshot["enums"] if e["name"] in types or f"{e['schema']}.{e['name']}" in types]

    dbml = render_dbml({"enums": enums, "tables": included, "refs": refs}) if included else ""
    return ToolResult(
        ok=True,
        data={"dbml": dbml, "tables": [t["name"] for t in included], "omitted": omitted, "missing": missing},
        truncated=bool(omitted),
    )
