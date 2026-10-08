"""모델 속성 → @Path → SQL 컬럼 매핑 분석 도구."""

import json
import re
from pathlib import Path
from typing import Any

from yunhee.tools.analysis.common import resolve_as_is_paths
from yunhee.tools.as_is.mybatis_render import Node, get_all_statements, parse_xml
from yunhee.tools.as_is.src_indexer import find_app

NAME = "model"
DESCRIPTION = "모델 속성 → @Path → SQL 컬럼 매핑 분석"
TARGET_HELP = "<모델클래스|Properties클래스>"
FORMATS = ("md", "json")
EXAMPLES = [
    "yunhee analysis model Sys05_UserRoleModel --sql sys05_user_role.selectByRoleId",
    "yunhee analysis model Emp00_TransInfoModel",
    "yunhee analysis model Emp01_PersonModel",
]


def _parse_properties_file(path: Path) -> dict[str, str]:
    """ModelProperties.java에서 @Path("...") 매핑을 파싱한다."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}

    path_map: dict[str, str] = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        m_path = re.search(r'@Path\(\s*"([^"]+)"\s*\)', line)
        if m_path:
            path_val = m_path.group(1)
            # 다음 1~2줄에서 메서드명 추출
            for j in range(i, min(len(lines), i + 3)):
                m_meth = re.search(r"ValueProvider<[^>]+>\s+(\w+)\s*\(", lines[j])
                if m_meth:
                    path_map[m_meth.group(1)] = path_val
                    break
    return path_map


def _parse_model_file(path: Path) -> tuple[dict[str, str], dict[str, tuple[int, int]]]:
    """Model.java에서 필드 타입 및 계산 getter를 파싱한다.

    반환: (필드별 타입 사전, getter 속성명 -> (시작줄, 끝줄))
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}, {}

    fields: dict[str, str] = {}
    lines = text.splitlines()
    for line in lines:
        m_field = re.search(r"(?:private|protected)\s+([\w<>\[\], ?]+)\s+(\w+)\s*;", line)
        if m_field:
            fields[m_field.group(2)] = m_field.group(1)

    # getter 분석 (필드가 없는 getter는 계산 속성)
    getters: dict[str, tuple[int, int]] = {}
    for i, line in enumerate(lines):
        m_get = re.search(r"public\s+[\w<>\[\], ?]+\s+get([A-Z]\w*)\s*\(\s*\)", line)
        if m_get:
            raw_name = m_get.group(1)
            prop_name = raw_name[0].lower() + raw_name[1:]
            if prop_name not in fields:
                # 시작줄과 끝줄 추적
                start_l = i + 1
                end_l = start_l
                for j in range(i, min(len(lines), i + 30)):
                    if "}" in lines[j]:
                        end_l = j + 1
                        break
                getters[prop_name] = (start_l, end_l)

    return fields, getters


def _find_all_result_maps(app: Path) -> dict[str, dict[str, Any]]:
    """모든 XML에서 resultMap 정보를 수집한다."""
    result_maps: dict[str, dict[str, Any]] = {}
    for f in app.rglob("*.xml"):
        if "target" in f.parts:
            continue
        try:
            raw = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        ns_m = re.search(r"<mapper\s+namespace\s*=\s*\"([^\"]+)\"", raw)
        ns = ns_m.group(1) if ns_m else ""
        root = parse_xml(raw)
        mapper = next((c for c in root.children if isinstance(c, Node) and c.tag == "mapper"), None)
        if not mapper:
            continue
        for child in mapper.children:
            if isinstance(child, Node) and child.tag == "resultMap" and "id" in child.attrs:
                rm_id = child.attrs["id"]
                full_id = f"{ns}.{rm_id}" if ns else rm_id
                model_type = child.attrs.get("type", "")
                mappings: dict[str, str] = {}
                associations: dict[str, str] = {}
                for sub in child.children:
                    if isinstance(sub, Node):
                        if sub.tag in ("result", "id"):
                            c = sub.attrs.get("column", "")
                            p = sub.attrs.get("property", "")
                            if c and p:
                                mappings[p] = c
                        elif sub.tag == "association":
                            p = sub.attrs.get("property", "")
                            rm_ref = sub.attrs.get("resultMap", "")
                            if p and rm_ref:
                                associations[p] = rm_ref
                result_maps[full_id] = {
                    "ns": ns,
                    "id": rm_id,
                    "type": model_type,
                    "mappings": mappings,
                    "associations": associations,
                }
                result_maps[rm_id] = result_maps[full_id]
    return result_maps


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """모델 및 Properties 클래스를 찾아 매핑 정보를 해석한다."""
    target_clean = target.strip()
    # Properties 접미사 처리
    base_name = target_clean
    if base_name.endswith("ModelProperties"):
        base_name = base_name[:-10]
    elif base_name.endswith("Properties"):
        base_name = base_name[:-10] + "Model" if not base_name.endswith("Model") else base_name

    model_cls_name = base_name if base_name.endswith("Model") else f"{base_name}Model"
    props_cls_name = f"{model_cls_name}Properties"

    src_root, _ = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    if not src_root or not src_root.is_dir():
        raise ValueError("AS-IS 소스 디렉터리를 찾을 수 없습니다. --src 옵션을 지정하세요.")

    app = find_app(src_root) or src_root

    # 파일 탐색
    model_file = next(app.rglob(f"{model_cls_name}.java"), None)
    props_file = next(app.rglob(f"{props_cls_name}.java"), None)

    if not model_file and not props_file:
        raise ValueError(f"모델 클래스를 찾을 수 없습니다: {model_cls_name} / {props_cls_name}")

    path_map = _parse_properties_file(props_file) if props_file else {}
    fields_map, getters_map = _parse_model_file(model_file) if model_file else ({}, {})

    # resultMap 매핑 수집
    all_rms = _find_all_result_maps(app)

    # 해당 모델을 type으로 가지는 resultMap 찾기
    matched_rm = None
    for rm_info in all_rms.values():
        if model_cls_name in rm_info["type"]:
            matched_rm = rm_info
            break

    # SQL 파라미터가 주어진 경우
    sql_opt = opts.get("sql")
    sql_select_cols: set[str] = set()
    sql_tables: set[str] = set()
    if sql_opt:
        stmts = get_all_statements(src_root)
        st = stmts.get(sql_opt) or next((s for s in stmts.values() if s.sid == sql_opt), None)
        if st:
            raw_xml = st.raw
            m_s = re.search(rf'<{st.kind}\b[^>]*\bid="{re.escape(st.sid)}"[^>]*>(.*?)</{st.kind}>', raw_xml, re.DOTALL)
            sbody = m_s.group(1) if m_s else raw_xml
            # 테이블 탐색
            for t in re.findall(r"\bFROM\s+([a-zA-Z0-9_]+)|\bJOIN\s+([a-zA-Z0-9_]+)", sbody, re.IGNORECASE):
                sql_tables.add((t[0] or t[1]).lower())
            # 컬럼/별칭 탐색
            for c in re.findall(r"\b([a-zA-Z0-9_]+)\b", sbody):
                sql_select_cols.add(c.lower())

    # 속성 통합 목록 작성
    all_prop_keys = sorted(set(list(path_map.keys()) + list(fields_map.keys()) + list(getters_map.keys())))

    rows = []
    for prop in all_prop_keys:
        path_val = path_map.get(prop, prop)
        field_type = fields_map.get(prop, "")
        is_calc = prop in getters_map

        # resultMap 컬럼 추적
        db_col = ""
        if is_calc:
            start_l, end_l = getters_map[prop]
            db_col = f"계산(getter L{start_l}-{end_l})"
        elif matched_rm:
            # 1. 직속 mapping 확인
            if prop in matched_rm["mappings"]:
                db_col = matched_rm["mappings"][prop]
            # 2. @Path 경로로 association 추적
            elif "." in path_val:
                assoc_part, sub_prop = path_val.split(".", 1)
                sub_prop_leaf = sub_prop.split(".")[-1]
                assoc_rm_ref = matched_rm["associations"].get(assoc_part)
                if assoc_rm_ref and assoc_rm_ref in all_rms:
                    sub_rm = all_rms[assoc_rm_ref]
                    db_col = sub_rm["mappings"].get(sub_prop_leaf, "")

        # SQL 존재 여부 판정
        sql_status = ""
        if sql_opt:
            if is_calc:
                sql_status = "계산"
            elif db_col:
                col_lower = db_col.lower()
                prefix = col_lower.split("_")[0] if "_" in col_lower else ""
                if col_lower in sql_select_cols:
                    sql_status = "✅"
                elif any(t.startswith(prefix) for t in sql_tables):
                    tbl_match = next((t for t in sql_tables if t.startswith(prefix)), "")
                    sql_status = f"✅({tbl_match}.*)"
                else:
                    sql_status = "❌"
            else:
                sql_status = "❌"

        rows.append({
            "prop": prop,
            "path": path_val,
            "type": field_type,
            "col": db_col,
            "sql_status": sql_status,
        })

    return {
        "model": model_cls_name,
        "props_cls": props_cls_name,
        "sql": sql_opt,
        "rows": rows,
    }


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    if fmt == "json":
        return json.dumps(obj, ensure_ascii=False, indent=2)

    model_name = obj["model"]
    sql_name = obj["sql"]
    rows = obj["rows"]

    has_sql = bool(sql_name)

    lines = [f"### 모델 `{model_name}` 매핑"]
    if has_sql:
        lines.append(f"- **대조 SQL**: `{sql_name}`\n")
        lines.append("| 속성 | @Path | 타입 | resultMap 컬럼 | SQL 존재 |")
        lines.append("|:---|:---|:---|:---|:---|")
        for r in rows:
            lines.append(f"| {r['prop']} | {r['path']} | {r['type']} | {r['col']} | {r['sql_status']} |")
    else:
        lines.append("\n| 속성 | @Path | 타입 | resultMap 컬럼 |")
        lines.append("|:---|:---|:---|:---|")
        for r in rows:
            lines.append(f"| {r['prop']} | {r['path']} | {r['type']} | {r['col']} |")

    return "\n".join(lines)
