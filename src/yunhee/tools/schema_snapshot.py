"""`make-dbml`이 저장한 스키마 스냅샷(JSON)을 읽어 필요한 테이블만 DBML로 잘라낸다 (DB 접속 없음).

스냅샷 위치는 WORK_DIR이 아니라 YUNHEE_DIR/data/schema/<ENV_NAME>.json — AssetERP DB 스키마는 작업 대상 프로젝트와
무관하게 하나라서, 어느 폴더에서 yunhee를 실행하든 같은 스냅샷을 찾을 수 있어야 한다.
"""

import json
import re
from datetime import datetime
from fnmatch import fnmatchcase
from pathlib import Path

from yunhee.config import WORK_DIR, YUNHEE_DIR
from yunhee.dbml import render_dbml
from yunhee.tools.base import ToolResult

SNAPSHOT_DIR = YUNHEE_DIR / "data" / "schema"

# 잘라낸 DBML의 문자 예산. 한 테이블 블록이 보통 1~3천 자(한글 코멘트 포함)라 10~20개 테이블 분량.
SCHEMA_CHAR_LIMIT = 30000


def snapshot_path(env_name: str) -> Path:
    return SNAPSHOT_DIR / f"{env_name}.json"


def save_snapshot(env_name: str, schema: dict) -> Path:
    data = {**schema, "env_name": env_name, "generated_at": datetime.now().astimezone().isoformat(timespec="seconds")}
    json_text = json.dumps(data, ensure_ascii=False, default=str)

    # 1. 전역 SNAPSHOT_DIR 저장 (기본/fallback)
    path = snapshot_path(env_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json_text)

    # 2. 현재 작업 폴더(WORK_DIR/.yunhee)가 있으면 로컬 .yunhee/ 에도 저장
    local_dot_yunhee = WORK_DIR / ".yunhee"
    if local_dot_yunhee.is_dir():
        local_path = local_dot_yunhee / f"{env_name}.json"
        local_path.write_text(json_text)
        return local_path

    return path


def load_snapshot(env_name: str) -> ToolResult:
    # 1. 로컬 프로젝트(.yunhee) 우선 탐색 -> 2. 전역 SNAPSHOT_DIR 탐색
    candidates = [
        WORK_DIR / ".yunhee" / f"{env_name}.json",
        WORK_DIR / ".yunhee" / "schema" / f"{env_name}.json",
        snapshot_path(env_name),
    ]

    fallback_env = "LOCAL_DB" if env_name == "YUNHEE_DB" else ("YUNHEE_DB" if env_name == "LOCAL_DB" else None)
    if fallback_env:
        candidates.extend([
            WORK_DIR / ".yunhee" / f"{fallback_env}.json",
            WORK_DIR / ".yunhee" / "schema" / f"{fallback_env}.json",
            snapshot_path(fallback_env),
        ])

    for cand in candidates:
        if cand.is_file():
            return ToolResult(ok=True, data=json.loads(cand.read_text()))

    return ToolResult(
        ok=False, error=f"스키마 스냅샷이 없습니다: {snapshot_path(env_name)} (먼저 'yunhee make-dbml {env_name}' 실행)"
    )


def _matches(table: dict, pattern: str) -> bool:
    """pattern: 'table' 또는 'schema.table', glob(*, ?) 허용, 대소문자 무시."""
    pattern = pattern.lower()
    target = f"{table['schema']}.{table['name']}" if "." in pattern else table["name"]
    return fnmatchcase(target.lower(), pattern)


# 가상 테이블/모델명 -> DB 테이블 반환 함수 매핑 (#10)
_MODEL_TO_FUNC = {
    "emp00_trans_info": "getperson",
    "emp00_trans_infomodel": "getperson",
    "org00_org": "getorg",
    "org00_orgmodel": "getorg",
    "tdm30_role_allc": "gettdm30roleallc",
}


def _routine_to_virtual_table(snapshot: dict, pattern: str) -> dict | None:
    """스냅샷의 routines 또는 docs/as-is/db/functions/*.md에서 RETURNS TABLE 함수를 찾아 가상 테이블 dict로 변환한다 (#10)."""
    pat_clean = pattern.strip().lower().removeprefix("public.")
    target_fn = _MODEL_TO_FUNC.get(pat_clean, pat_clean)

    routines = snapshot.get("routines") or []
    matched_r = None
    for r in routines:
        if r.get("name", "").lower() == target_fn and "returns table" in r.get("definition", "").lower():
            matched_r = r
            break

    definition = matched_r.get("definition", "") if matched_r else ""
    fn_name = matched_r.get("name", target_fn) if matched_r else target_fn
    fn_schema = matched_r.get("schema", "public") if matched_r else "public"
    fn_args = matched_r.get("arguments", "") if matched_r else ""

    if not definition:
        from yunhee.tools.as_is import find_as_is_dir

        db_dir = find_as_is_dir("db")
        if db_dir and (db_dir / "functions").is_dir():
            for f_md in (db_dir / "functions").glob("*.md"):
                if f_md.stem.lower() == target_fn:
                    definition = f_md.read_text(encoding="utf-8", errors="replace")
                    fn_name = f_md.stem
                    break

    if not definition:
        return None

    m_ret = re.search(r"RETURNS\s+TABLE\s*\((.*?)\)\s*(?:LANGUAGE|AS|\$)", definition, re.DOTALL | re.IGNORECASE)
    if not m_ret:
        return None

    cols_raw = m_ret.group(1)
    columns = []
    for part in cols_raw.split(","):
        tokens = part.strip().split(None, 1)
        if len(tokens) == 2:
            col_name = tokens[0].strip('"')
            col_type = tokens[1].strip()
            columns.append({
                "name": col_name,
                "type": col_type,
                "not_null": False,
                "default": None,
                "identity": None,
                "generated": None,
                "note": None,
            })

    if not columns:
        return None

    note_str = f"FUNCTION {fn_schema}.{fn_name}({fn_args}) RETURNS TABLE ({len(columns)} columns)"
    if pat_clean != target_fn:
        note_str += f" — 매핑: {pattern}"

    return {
        "schema": fn_schema,
        "name": fn_name,
        "columns": columns,
        "pk": [],
        "uniques": [],
        "indexes": [],
        "note": note_str,
    }


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
            vt = _routine_to_virtual_table(snapshot, pattern)
            if vt:
                hits = [vt]
            else:
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
