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
from yunhee.tools.as_is.sql_checker import Node, parse_xml
from yunhee.tools.as_is.sql_porter import find_mapper_file
from yunhee.tools.base import ToolResult
from yunhee.tools.sql_runner import get_connection_string


def _eval_test_condition(test: str, params: dict[str, str]) -> bool:
    """MyBatis <if test="..."> 또는 <when test="..."> 조건을 평가한다."""
    test = test.strip()
    if not test:
        return True

    # DBMS 구분 플래그
    if "isPostgreSql" in test:
        return True
    if "isTibero" in test or "isOracle" in test:
        return False

    # var != null
    m_not_null = re.match(r"^(\w+)\s*!=\s*null$", test)
    if m_not_null:
        var = m_not_null.group(1)
        return var in params and params[var] is not None

    # var == null
    m_null = re.match(r"^(\w+)\s*==\s*null$", test)
    if m_null:
        var = m_null.group(1)
        return var not in params or params[var] is None

    # var != ''
    m_not_empty = re.match(r"^(\w+)\s*!=\s*['\"]['\"]$", test)
    if m_not_empty:
        var = m_not_empty.group(1)
        return bool(params.get(var))

    # var == 'val'
    m_eq = re.match(r"^(\w+)\s*==\s*['\"]([^'\"]*)['\"]$", test)
    if m_eq:
        var, val = m_eq.group(1), m_eq.group(2)
        return str(params.get(var)) == val

    # 기본: 변수가 params에 존재하면 True
    var_match = re.search(r"(\w+)", test)
    if var_match:
        var = var_match.group(1)
        return var in params

    return True


def _render_node_with_params(
    node: Any,
    params: dict[str, str],
    sql_fragments: dict[str, str],
) -> str:
    """MyBatis XML 트리를 params 파라미터 값으로 평가하여 실제 SQL 텍스트로 렌더링한다."""
    if isinstance(node, str):
        return node

    tag = node.tag
    if tag == "root":
        return "".join(_render_node_with_params(c, params, sql_fragments) for c in node.children)

    if tag == "include":
        ref = node.attrs.get("refid", "")
        frag_text = sql_fragments.get(ref) or sql_fragments.get(ref.split(".")[-1], "")
        if frag_text:
            frag_node = parse_xml(frag_text)
            return _render_node_with_params(frag_node, params, sql_fragments)
        return ""

    if tag == "if":
        test = node.attrs.get("test", "")
        if _eval_test_condition(test, params):
            return "".join(_render_node_with_params(c, params, sql_fragments) for c in node.children)
        return ""

    if tag == "choose":
        whens = [c for c in node.children if isinstance(c, Node) and c.tag == "when"]
        other = next((c for c in node.children if isinstance(c, Node) and c.tag == "otherwise"), None)
        for w in whens:
            test = w.attrs.get("test", "")
            if _eval_test_condition(test, params):
                return "".join(_render_node_with_params(c, params, sql_fragments) for c in w.children)
        if other:
            return "".join(_render_node_with_params(c, params, sql_fragments) for c in other.children)
        return ""

    if tag == "where":
        body = "".join(_render_node_with_params(c, params, sql_fragments) for c in node.children).strip()
        if body:
            body = re.sub(r"^(AND|OR)\b", "", body, flags=re.IGNORECASE).strip()
            return f" WHERE {body} "
        return ""

    if tag == "set":
        body = "".join(_render_node_with_params(c, params, sql_fragments) for c in node.children).strip()
        body = body.rstrip(",")
        return f" SET {body} " if body else ""

    return "".join(_render_node_with_params(c, params, sql_fragments) for c in node.children)


def render_mybatis_sql(
    xml_text: str,
    sql_id: str,
    params: dict[str, str],
) -> tuple[str, list[str]]:
    """매퍼 XML에서 대상 select 문을 찾아 params를 대입한 실행 SQL을 생성한다."""
    # <sql> 조각 수집
    sql_fragments = dict(re.findall(r'<sql\s+id="([^"]+)"[^>]*>(.*?)</sql>', xml_text, re.DOTALL))

    # 대상 select 찾기
    m_sel = re.search(rf'<select\s+id="{re.escape(sql_id)}"[^>]*>(.*?)</select>', xml_text, re.DOTALL)
    if not m_sel:
        raise ValueError(f"<select id=\"{sql_id}\">를 찾을 수 없습니다.")

    sbody = m_sel.group(1)
    node = parse_xml(sbody)
    rendered = _render_node_with_params(node, params, sql_fragments)

    # 파라미터 대입
    def replace_sharp(m: re.Match) -> str:
        var = m.group(1).strip()
        if var in params:
            val = params[var]
            # 이미 따옴표가 있거나 숫자인 경우 처리
            val_escaped = str(val).replace("'", "''")
            return f"'{val_escaped}'"
        return "NULL"

    def replace_dollar(m: re.Match) -> str:
        var = m.group(1).strip()
        if var in params:
            return str(params[var])
        return "1"

    sql = re.sub(r"#\{([^}]+)\}", replace_sharp, rendered)
    sql = re.sub(r"\$\{([^}]+)\}", replace_dollar, sql)

    # 주석 제거 및 정리
    sql = re.sub(r"<!--.*?-->", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", " ", sql)
    sql = sql.strip().rstrip(";")

    param_keys = sorted(set(re.findall(r"[#$]\{([^}]+)\}", sbody)))
    return sql, param_keys


def find_screen_grid_cols(sql_ref: str, src_root: Path | None = None) -> set[str]:
    """AS-IS 화면 색인에서 해당 SQL을 사용하는 화면의 Grid 컬럼(TOBE 프로퍼티)을 찾는다."""
    cand_dirs = [
        find_as_is_dir("src"),
        config.WORK_DIR / "docs" / "as-is" / "src",
        Path("/home/kdy987/work/framework-sprt/docs/as-is/src"),
    ]
    roots: list[Path] = []
    if src_root and src_root.is_dir():
        roots.append(src_root)
    if config.ASIS_SRC_DIR and config.ASIS_SRC_DIR.is_dir():
        roots.append(config.ASIS_SRC_DIR)
    roots.append(config.WORK_DIR)

    ns = sql_ref.split(".")[0]
    pfx_m = re.match(r"^([a-z]+\d*)", ns)
    target_prefix = pfx_m.group(1).lower() if pfx_m else ns.lower()

    all_screens: list[Path] = []
    for c_dir in cand_dirs:
        if c_dir.is_dir():
            all_screens.extend(c_dir.glob("**/screens/*.md"))

    all_screens.sort(
        key=lambda p: (
            0 if p.stem.lower().startswith(target_prefix) else 1,
            0 if "_Tab_" in p.stem else 1,
            len(p.stem),
        )
    )

    for screen_file in all_screens:
        try:
            text = screen_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if sql_ref not in text:
            continue

        m = re.search(r'-\s+그리드[^\n]*\(buildGrid[^\n]*\):\n((?:\s+-\s+[^\n]+\n)+)', text)
        if not m:
            continue
        grid_props = [
            re.search(r'^\s*-\s+([a-zA-Z0-9_]+)', line).group(1)
            for line in m.group(1).strip().splitlines()
            if re.search(r'^\s*-\s+([a-zA-Z0-9_]+)', line)
        ]
        if not grid_props:
            continue

        mod_m = re.search(r"Grid<([A-Z]\w+Model)>|GridBuilder<([A-Z]\w+)>|\b([A-Z]\w*_\w*Model)\b", text)
        model_name = next((g for g in mod_m.groups() if g), "") if mod_m else ""
        if not model_name:
            model_name = screen_file.stem.replace("_Tab_", "_").replace("_TabPage_", "_") + "Model"

        prop_to_col, _ns, _tbl, _aliases = find_mapper_for_model(model_name, roots)
        tbl_pfx = (re.match(r"^([a-z]+\d*)_", _tbl).group(1) + "_") if (_tbl and re.match(r"^([a-z]+\d*)_", _tbl)) else ""
        tobe_props = set()
        for p in grid_props:
            col = prop_to_col.get(p, "")
            tobe_props.add(col_to_tobe_prop(col, tbl_pfx) if col else p)
        if tobe_props:
            return tobe_props

    return set()


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
) -> ToolResult:
    """조회 API와 AS-IS SQL의 결과 행 수 및 필드 커버리지를 비교 검증한다."""
    if not api_params:
        api_params = {}
    if not sql_params:
        sql_params = {}

    if "." not in sql_ref:
        return ToolResult(ok=False, error=f"올바른 형식(namespace.sqlId)으로 입력해 주세요: {sql_ref}")

    ns, sid = sql_ref.split(".", 1)
    xml_path = find_mapper_file(ns, src_root)
    if not xml_path:
        return ToolResult(ok=False, error=f"매퍼 XML을 찾을 수 없습니다: namespace={ns}")

    try:
        xml_text = xml_path.read_text(encoding="utf-8", errors="replace")
        sql, _ = render_mybatis_sql(xml_text, sid, sql_params)
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
    grid_cols = find_screen_grid_cols(sql_ref, src_root)
    if grid_cols:
        expected_fields = grid_cols
    else:
        expected_fields = {col_to_tobe_prop(c, tbl_prefix) for c in sql_cols}

    # 3. 비교 판정
    rows_match = (api_row_count == sql_row_count)
    rows_mark = "✅" if rows_match else "❌"

    missing_fields = expected_fields - api_fields
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
