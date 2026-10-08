"""조회 HTTP API와 AS-IS MyBatis SQL의 실행 결과를 비교 검증하는 도구."""

import json
import re
from pathlib import Path
from typing import Any

import psycopg

from yunhee import config
from yunhee.tools.api_client import request_api
from yunhee.tools.as_is.events import (
    col_to_tobe_prop,
    find_as_is_dir,
    find_mapper_for_model,
)
from yunhee.tools.as_is.sql_checker import parse_xml
from yunhee.tools.as_is.sql_porter import find_mapper_file
from yunhee.tools.base import ToolResult
from yunhee.tools.sql_runner import get_connection_string


def _eval_test_condition(test: str, params: dict[str, Any]) -> bool:
    from yunhee.tools.as_is.mybatis_render import eval_test_condition

    return eval_test_condition(test, params)


def _render_node_with_params(
    node: Any,
    params: dict[str, str],
    sql_fragments: dict[str, str],
) -> str:
    from yunhee.tools.as_is.mybatis_render import Statement, render_node

    statements: dict[str, Statement] = {}
    for sid, text in sql_fragments.items():
        st_node = parse_xml(text)
        statements[sid] = Statement("common", sid, "sql", st_node, Path("fragment.xml"), 1)
    return render_node(node, "common", statements, dict(params), mode="params")


def render_mybatis_sql(
    xml_text: str,
    sql_id: str,
    params: dict[str, str],
) -> tuple[str, list[str]]:
    """매퍼 XML에서 대상 select 문을 찾아 params를 대입한 실행 SQL을 생성한다."""
    from yunhee.tools.as_is.mybatis_render import render_from_xml

    return render_from_xml(xml_text, sql_id, params=params, mode="params")


def _field_covered(expected_col: str, api_fields: set[str]) -> bool:
    if expected_col in api_fields:
        return True
    cand_nm = re.sub(r"Name$", "Nm", expected_col)
    cand_name = re.sub(r"Nm$", "Name", expected_col)
    if cand_nm in api_fields or cand_name in api_fields:
        return True
    unprefixed = re.sub(r"^[a-z]{3,4}", "", expected_col)
    if unprefixed:
        unprefixed_camel = unprefixed[0].lower() + unprefixed[1:]
        cand_u_nm = re.sub(r"Name$", "Nm", unprefixed_camel)
        cand_u_name = re.sub(r"Nm$", "Name", unprefixed_camel)
        if unprefixed_camel in api_fields or cand_u_nm in api_fields or cand_u_name in api_fields:
            return True
    return False


def find_screen_grid_cols(
    sql_ref: str,
    src_root: Path | None = None,
    grid_class: str | None = None,
    src_index: Path | None = None,
) -> set[str]:
    """AS-IS 화면 색인에서 해당 SQL을 사용하는 화면의 Grid 컬럼(TOBE 프로퍼티)을 찾는다."""
    src_index_dir = (
        src_index
        or (Path(config.TOML_CONFIG.get("as_is", {}).get("src_index")) if config.TOML_CONFIG.get("as_is", {}).get("src_index") else None)
        or find_as_is_dir("src")
    )
    roots: list[Path] = []
    if src_root and src_root.is_dir():
        roots.append(src_root)
    if config.ASIS_SRC_DIR and config.ASIS_SRC_DIR.is_dir():
        roots.append(config.ASIS_SRC_DIR)
    roots.append(config.WORK_DIR)

    all_screens: list[Path] = []
    if src_index_dir and src_index_dir.is_dir():
        all_screens.extend(src_index_dir.glob("**/screens/*.md"))

    ns = sql_ref.split(".")[0]
    pfx_m = re.match(r"^([a-z]+\d*)", ns)
    target_prefix = pfx_m.group(1).lower() if pfx_m else ns.lower()
    all_screens.sort(
        key=lambda p: (
            0 if p.stem.lower().startswith(target_prefix) else 1,
            0 if "_Tab_" in p.stem else 1,
            len(p.stem),
        )
    )

    # grid_class가 직접 지정된 경우
    if grid_class:
        for sf in all_screens:
            if sf.stem.lower() == grid_class.lower() or f"{grid_class.lower()}.md" in sf.name.lower():
                try:
                    text = sf.read_text(encoding="utf-8", errors="replace")
                    props = _extract_grid_props(text, sf.stem, roots)
                    if props:
                        return props
                except OSError:
                    pass

    # SQL을 부르는 서비스의 클래스 탐색
    calling_class = None
    matched_screen = None
    for sf in all_screens:
        try:
            text = sf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if sql_ref not in text:
            continue
        matched_screen = sf
        for line in text.splitlines():
            if sql_ref in line and "|" in line:
                parts = [p.strip() for p in line.split("|")]
                # 보통 | 서비스 | 호출 위치 | SQL |
                for part in parts:
                    m_call = re.search(r"\b([A-Z]\w+)\.(retrieve\w*|select\w*|search\w*|on\w+)\b", part)
                    if m_call:
                        calling_class = m_call.group(1)
                        break
            if calling_class:
                break
        if calling_class:
            break

    if calling_class:
        # 호출 클래스의 화면 파일 우선 탐색
        for sf in all_screens:
            if sf.stem.lower() == calling_class.lower():
                try:
                    props = _extract_grid_props(sf.read_text(encoding="utf-8", errors="replace"), sf.stem, roots)
                    if props:
                        return props
                except OSError:
                    pass

    # fallback: matched_screen에서 추출
    if matched_screen:
        try:
            return _extract_grid_props(matched_screen.read_text(encoding="utf-8", errors="replace"), matched_screen.stem, roots)
        except OSError:
            pass

    return set()


def _extract_grid_props(text: str, stem: str, roots: list[Path]) -> set[str]:
    m = re.search(r'-\s+그리드[^\n]*\(buildGrid[^\n]*\):\n((?:\s+-\s+[^\n]+\n)+)', text)
    if not m:
        # Grid Spec 코드 블록 내의 컬럼 탐색
        m_spec = re.search(r'## Grid Spec.*?(const buildGrid\b.*?\];)', text, re.DOTALL)
        if m_spec:
            code = m_spec.group(1)
            props = set(re.findall(r'gb\.\w+\(["\'](\w+)["\']', code))
            if props:
                return props
        return set()

    grid_props = [
        re.search(r'^\s*-\s+([a-zA-Z0-9_]+)', line).group(1)
        for line in m.group(1).strip().splitlines()
        if re.search(r'^\s*-\s+([a-zA-Z0-9_]+)', line)
    ]
    if not grid_props:
        return set()

    mod_m = re.search(r"Grid<([A-Z]\w+Model)>|GridBuilder<([A-Z]\w+)>|\b([A-Z]\w*_\w*Model)\b", text)
    model_name = next((g for g in mod_m.groups() if g), "") if mod_m else ""
    if not model_name:
        model_name = stem.replace("_Tab_", "_").replace("_TabPage_", "_") + "Model"

    prop_to_col, _ns, _tbl, _aliases = find_mapper_for_model(model_name, roots)
    tbl_pfx = (re.match(r"^([a-z]+\d*)_", _tbl).group(1) + "_") if (_tbl and re.match(r"^([a-z]+\d*)_", _tbl)) else ""
    tobe_props = set()
    for p in grid_props:
        col = prop_to_col.get(p, "")
        tobe_props.add(col_to_tobe_prop(col, tbl_pfx) if col else p)
    return tobe_props


def compare_api_sql(
    method: str,
    path: str,
    sql_ref: str,
    api_params: dict[str, Any] | None = None,
    sql_params: dict[str, str] | None = None,
    base_url: str = config.API_BASE_URL,
    tenant: str | None = None,
    company: str | None = None,
    db_name: str = "asseterpdb",
    src_root: Path | None = None,
    grid: str | None = None,
) -> ToolResult:
    """조회 API와 AS-IS SQL의 결과 행 수 및 필드 커버리지를 비교 검증한다."""
    import sys

    from yunhee.tools.as_is.mybatis_render import get_all_statements
    from yunhee.tools.as_is.mybatis_render import render as mr_render

    if not api_params:
        api_params = {}
    if not sql_params:
        sql_params = {}

    if "." not in sql_ref:
        return ToolResult(ok=False, error=f"올바른 형식(namespace.sqlId)으로 입력해 주세요: {sql_ref}")

    ns, sid = sql_ref.split(".", 1)

    try:
        stmts = get_all_statements(src_root)
        if sql_ref in stmts or any(s.sid == sid for s in stmts.values()):
            sql, missing = mr_render(sql_ref, params=sql_params, mode="params", statements=stmts)
            for m_p in missing:
                sys.stderr.write(f"⚠ 값 없음: {m_p}\n")
        else:
            xml_path = find_mapper_file(ns, src_root)
            if not xml_path:
                return ToolResult(ok=False, error=f"매퍼 XML을 찾을 수 없습니다: namespace={ns}")
            xml_text = xml_path.read_text(encoding="utf-8", errors="replace")
            sql, missing = render_mybatis_sql(xml_text, sid, sql_params)
            for m_p in missing:
                sys.stderr.write(f"⚠ 값 없음: {m_p}\n")
    except Exception as e:  # noqa: BLE001
        return ToolResult(ok=False, error=f"SQL 렌더링 실패: {e}")

    # 1. API 호출
    api_res = request_api(
        method=method,
        path=path,
        base_url=base_url,
        company_code=company,
        tenant=tenant,
        params=api_params if method.upper() == "GET" else None,
        json_body=api_params if method.upper() != "GET" else None,
    )
    if not api_res.ok:
        return ToolResult(ok=False, error=f"API 호출 실패: {api_res.error}")

    api_data = api_res.data
    raw_json = {}
    if isinstance(api_data, dict):
        text_str = api_data.get("text", "")
        if text_str:
            try:
                raw_json = json.loads(text_str)
            except Exception:  # noqa: BLE001
                raw_json = {}
        elif "data" in api_data:
            raw_json = api_data["data"]

    raw_data = raw_json.get("data") if isinstance(raw_json, dict) else raw_json
    if raw_data is None and isinstance(raw_json, list):
        raw_data = raw_json

    # API 응답에서 행 목록 추출
    api_rows_list: list[Any] = []
    if isinstance(raw_data, list):
        api_rows_list = raw_data
    elif isinstance(raw_data, dict):
        if "data" in raw_data and isinstance(raw_data["data"], list):
            api_rows_list = raw_data["data"]
        elif "list" in raw_data and isinstance(raw_data["list"], list):
            api_rows_list = raw_data["list"]
        elif "items" in raw_data and isinstance(raw_data["items"], list):
            api_rows_list = raw_data["items"]
        else:
            api_rows_list = [raw_data]

    api_row_count = len(api_rows_list)
    api_fields: set[str] = set()
    for row in api_rows_list:
        if isinstance(row, dict):
            api_fields.update(row.keys())

    # 2. SQL 실행 (Read-Only)
    conn_str = get_connection_string(db_name)
    try:
        with psycopg.connect(conn_str, autocommit=False) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                cur.execute(sql)
                sql_rows = cur.fetchall()
                sql_row_count = len(sql_rows)
                sql_cols = [desc[0] for desc in cur.description] if cur.description else []
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"SQL 실행 실패: {exc}\n실행 SQL: {sql}")

    # 테이블 접두어 추출
    tbl_pfx_m = re.match(r"^([a-z]+\d*)_", ns)
    tbl_prefix = (tbl_pfx_m.group(1) + "_") if tbl_pfx_m else ""

    # Grid Spec 컬럼 우선 매핑, 없으면 SQL 컬럼 사용
    grid_cols = find_screen_grid_cols(sql_ref, src_root, grid_class=grid)
    if grid_cols:
        expected_fields = grid_cols
    else:
        expected_fields = {col_to_tobe_prop(c, tbl_prefix) for c in sql_cols}

    # 3. 비교 판정
    rows_match = (api_row_count == sql_row_count)
    rows_mark = "✅" if rows_match else "❌"

    missing_fields = {f for f in expected_fields if not _field_covered(f, api_fields)}
    cols_covered = (len(missing_fields) == 0)
    cols_mark = "✅" if cols_covered else "⚠️"

    summary_parts = [
        f"API rows={api_row_count}, SQL rows={sql_row_count} {rows_mark}",
        f"fields ⊇ grid cols {cols_mark}",
    ]
    if not cols_covered and api_fields:
        summary_parts.append(f"(missing: {', '.join(sorted(missing_fields))})")

    summary_line = "  ".join(summary_parts)

    return ToolResult(
        ok=True,
        data={
            "summary": summary_line,
            "api_rows": api_row_count,
            "sql_rows": sql_row_count,
            "rows_match": rows_match,
            "cols_covered": cols_covered,
            "api_fields": sorted(api_fields),
            "expected_fields": sorted(expected_fields),
            "missing_fields": sorted(missing_fields),
            "rendered_sql": sql,
        },
    )
