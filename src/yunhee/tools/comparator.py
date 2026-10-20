"""조회 HTTP API와 AS-IS MyBatis SQL의 실행 결과를 비교 검증하는 도구."""

import json
import re
from pathlib import Path
from typing import Any

import psycopg

from yunhee import config
from yunhee.tools.analysis.common import GRID_METHOD_NAME_PATTERN
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
    cand_addr = re.sub(r"Address$", "Addr", expected_col)
    cand_address = re.sub(r"Addr$", "Address", expected_col)
    if cand_addr in api_fields or cand_address in api_fields:
        return True
    unprefixed = re.sub(r"^[a-z]{3,4}", "", expected_col)
    if unprefixed:
        unprefixed_camel = unprefixed[0].lower() + unprefixed[1:]
        cand_u_nm = re.sub(r"Name$", "Nm", unprefixed_camel)
        cand_u_name = re.sub(r"Nm$", "Name", unprefixed_camel)
        cand_u_addr = re.sub(r"Address$", "Addr", unprefixed_camel)
        cand_u_address = re.sub(r"Addr$", "Address", unprefixed_camel)
        if (
            unprefixed_camel in api_fields
            or cand_u_nm in api_fields
            or cand_u_name in api_fields
            or cand_u_addr in api_fields
            or cand_u_address in api_fields
        ):
            return True
    return False


def extract_trace_sql_params(trace_id: str, sql_ref: str, req_path: str = "") -> dict[str, str]:
    """로그 trace에서 특정 SQL statement의 바인딩 파라미터를 이름과 함께 추출한다."""
    from yunhee.tools import log_reader

    sid = sql_ref.split(".")[-1]

    raw = ""
    try:
        if config.LOG_DOCKER:
            raw = log_reader.read_logs_docker(
                config.LOG_DOCKER, config.LOG_DIR, config.LOG_APP, trace_id=trace_id
            )
        else:
            raw = log_reader.read_logs_local(
                Path(config.LOG_DIR), config.LOG_APP, trace_id=trace_id
            )
    except Exception:  # noqa: BLE001
        return {}

    lines = raw.splitlines()
    raw_params = None
    for i, line in enumerate(lines):
        if "==>  Preparing:" in line and sid in line:
            for j in range(i + 1, min(i + 10, len(lines))):
                if "==> Parameters:" in lines[j]:
                    m_p = re.search(r"==>\s+Parameters:\s*(.*)$", lines[j])
                    if m_p:
                        raw_params = m_p.group(1)
                    break
            if raw_params is not None:
                break

    if not raw_params:
        return {}

    param_vals = [re.sub(r"\([A-Za-z]+\)$", "", p.strip()) for p in raw_params.split(",") if p.strip()]

    # statement에서 파라미터 이름 추출 (#{} 목록)
    param_names = []
    ns, sid = sql_ref.split(".", 1) if "." in sql_ref else ("", sql_ref)

    # 1. find_mapper_file(ns)로 해당 매퍼 XML 우선 탐색
    if ns:
        try:
            mf = find_mapper_file(ns)
            if mf and mf.is_file():
                content = mf.read_text(encoding="utf-8", errors="replace")
                m = re.search(
                    rf'<(?:select|insert|update|delete)\b[^>]*\bid=["\x27]{re.escape(sid)}["\x27][^>]*>(.*?)</(?:select|insert|update|delete)>',
                    content,
                    re.DOTALL,
                )
                if m:
                    body = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.DOTALL)
                    param_names = re.findall(r"#\{\s*([a-zA-Z0-9_.]+)(?:[,\s:][^}]*)?\}", body)
        except Exception:  # noqa: BLE001, S110
            pass

    # 2. TOBE mapper XML 검색
    if not param_names:
        search_dirs = [
            config.WORK_DIR / "backend/src/main/resources/mapper",
            config.WORK_DIR / "src/main/resources/mapper",
            config.WORK_DIR,
        ]
        for sdir in search_dirs:
            if sdir.is_dir():
                for mf in sdir.rglob("*.xml"):
                    try:
                        content = mf.read_text(encoding="utf-8", errors="replace")
                        m = re.search(
                            rf'<(?:select|insert|update|delete)\b[^>]*\bid=["\x27]{re.escape(sid)}["\x27][^>]*>(.*?)</(?:select|insert|update|delete)>',
                            content,
                            re.DOTALL,
                        )
                        if m:
                            body = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.DOTALL)
                            names = re.findall(r"#\{\s*([a-zA-Z0-9_.]+)(?:[,\s:][^}]*)?\}", body)
                            if len(names) == len(param_vals):
                                param_names = names
                                break
                    except Exception:  # noqa: BLE001, S110
                        pass
                if param_names:
                    break

    if not param_names and config.ASIS_SRC_DIR and config.ASIS_SRC_DIR.is_dir():
        for mf in config.ASIS_SRC_DIR.rglob("*.xml"):
            try:
                content = mf.read_text(encoding="utf-8", errors="replace")
                m = re.search(
                    rf'<(?:select|insert|update|delete)\b[^>]*\bid=["\x27]{re.escape(sid)}["\x27][^>]*>(.*?)</(?:select|insert|update|delete)>',
                    content,
                    re.DOTALL,
                )
                if m:
                    body = re.sub(r"<!--.*?-->", "", m.group(1), flags=re.DOTALL)
                    param_names = re.findall(r"#\{\s*([a-zA-Z0-9_.]+)(?:[,\s:][^}]*)?\}", body)
                    if param_names:
                        break
            except Exception:  # noqa: BLE001, S110
                pass

    res = {}
    if param_names and len(param_names) == len(param_vals):
        for name, val in zip(param_names, param_vals):
            res[name] = val
    return res


def find_screen_grid_info(
    sql_ref: str,
    src_root: Path | None = None,
    grid_class: str | None = None,
    api_fields: set[str] | None = None,
) -> dict[str, Any]:
    src_index_dir = (
        Path(config.SRC_INDEX_DIR)
        if hasattr(config, "SRC_INDEX_DIR") and config.SRC_INDEX_DIR and Path(config.SRC_INDEX_DIR).is_dir()
        else None
    ) or (
        Path(config.TOML_CONFIG.get("as_is", {}).get("src_index"))
        if config.TOML_CONFIG.get("as_is", {}).get("src_index")
        else None
    ) or find_as_is_dir("src")

    roots: list[Path] = []
    if src_root and src_root.is_dir():
        roots.append(src_root)
    if config.ASIS_SRC_DIR and config.ASIS_SRC_DIR.is_dir():
        roots.append(config.ASIS_SRC_DIR)
    roots.append(config.WORK_DIR)

    all_screens: list[Path] = []
    if src_index_dir and src_index_dir.is_dir():
        all_screens.extend(src_index_dir.glob("**/screens/*.md"))
        all_screens.extend(src_index_dir.glob("**/components/*.md"))

    # grid_class가 직접 지정된 경우
    if grid_class:
        search_dir_str = str(src_index_dir) if src_index_dir else "알 수 없음"
        if "#" in grid_class:
            cls_name, target_meth = grid_class.split("#", 1)
        elif "." in grid_class:
            cls_name, target_meth = grid_class.split(".", 1)
        else:
            cls_name, target_meth = grid_class, None

        for sf in all_screens:
            try:
                text = sf.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if sf.stem.lower() == cls_name.lower() or f"### {cls_name}" in text:
                grids = _extract_all_grids(text, sf.stem, roots, target_section=cls_name)
                if not grids:
                    return {"cols": set(), "label": "", "not_found": True, "class_name": grid_class, "search_dir": search_dir_str}
                if target_meth:
                    matched = next(
                        (
                            g
                            for g in grids
                            if g["method"].lower() == target_meth.lower()
                            or g.get("var", "").lower() == target_meth.lower()
                        ),
                        None,
                    )
                    if matched:
                        return {
                            "cols": matched["cols"],
                            "label": f"{cls_name}#{matched['method']}",
                            "not_found": False,
                        }
                    return {"cols": set(), "label": "", "not_found": True, "class_name": grid_class, "search_dir": search_dir_str}

                if len(grids) == 1:
                    chosen = grids[0]
                else:
                    if api_fields:
                        chosen = max(grids, key=lambda g: len(g["cols"] & api_fields))
                    else:
                        chosen = grids[0]
                return {
                    "cols": chosen["cols"],
                    "label": f"{cls_name}#{chosen['method']}",
                    "not_found": False,
                }

        # grid_class를 지정했으나 찾지 못함 (Rule 4: fallback 금지)
        return {"cols": set(), "label": "", "not_found": True, "class_name": grid_class, "search_dir": search_dir_str}

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
                if len(parts) >= 3:
                    m_call = re.search(r"\b([A-Z]\w+)(?::\d+|\.\w+)?\b", parts[2])
                    if m_call and m_call.group(1) not in ("ServiceRequest", "ServiceResult", "SqlSession"):
                        calling_class = m_call.group(1)
                        break
            elif sql_ref in line:
                m_call = re.search(r"\b([A-Z]\w+)(?::\d+|\.\w+)\b", line)
                if m_call and m_call.group(1) not in ("ServiceRequest", "ServiceResult", "SqlSession"):
                    calling_class = m_call.group(1)
                    break
        if calling_class:
            break

    screens_to_try = []
    if calling_class and matched_screen:
        screens_to_try.append((matched_screen, calling_class))
    if calling_class:
        for sf in all_screens:
            if sf.stem.lower() == calling_class.lower():
                screens_to_try.append((sf, None))
    if matched_screen and not screens_to_try:
        screens_to_try.append((matched_screen, None))

    for sf, target_sec in screens_to_try:
        try:
            t = sf.read_text(encoding="utf-8", errors="replace")
            grids = _extract_all_grids(t, sf.stem, roots, target_section=target_sec)
            if grids:
                chosen = (
                    max(grids, key=lambda g: len(g["cols"] & api_fields))
                    if api_fields and len(grids) > 1
                    else grids[0]
                )
                return {"cols": chosen["cols"], "label": f"{sf.stem}#{chosen['method']}", "not_found": False}
        except OSError:
            pass

    return {"cols": set(), "label": "", "not_found": False}


def find_screen_grid_cols(
    sql_ref: str,
    src_root: Path | None = None,
    grid_class: str | None = None,
) -> set[str]:
    info = find_screen_grid_info(sql_ref, src_root=src_root, grid_class=grid_class)
    return info.get("cols", set())


def _extract_all_grids(
    text: str,
    stem: str,
    roots: list[Path] | None = None,
    target_section: str | None = None,
) -> list[dict[str, Any]]:
    if roots is None:
        roots = []
    section_text = text
    if target_section:
        sec_m = re.search(rf"###\s+{re.escape(target_section)}\b.*?(?=\n###\s|\Z)", text, re.DOTALL)
        if sec_m:
            section_text = sec_m.group(0)

    grids: list[dict[str, Any]] = []

    # 1) UI 그리드 목록: - 그리드 `var` (build*Grid*(), ...):
    for m in re.finditer(
        r"^-\s+그리드\s+`?([a-zA-Z0-9_]+)`?\s*\((.+)\)\s*:\s*\n((?:\s+-\s+[^\n]+\n)+)",
        section_text,
        re.MULTILINE,
    ):
        var_name = m.group(1)
        parens = m.group(2)
        body = m.group(3)
        meth_m = re.search(GRID_METHOD_NAME_PATTERN, parens)
        meth_name = meth_m.group(0) if meth_m else var_name
        props = [
            re.search(r'^\s*-\s+([a-zA-Z0-9_]+)', line).group(1)
            for line in body.strip().splitlines()
            if re.search(r'^\s*-\s+([a-zA-Z0-9_]+)', line)
        ]
        if props:
            grids.append({
                "method": meth_name,
                "var": var_name,
                "props": props,
            })

    # 2) Grid Spec 코드 블록: const build*Grid* = () => [ ... ];
    for m_spec in re.finditer(
        rf'const\s+({GRID_METHOD_NAME_PATTERN})\s*=\s*\(\)\s*=>\s*\[(.*?)\];',
        section_text,
        re.DOTALL,
    ):
        meth_name = m_spec.group(1)
        code = m_spec.group(2)
        gb_props = re.findall(r'gb\.\w+\(["\'](\w+)["\']', code)
        db_props = re.findall(r'//\s*(?:⚠DB없음\s+)?L\d+\s+([a-zA-Z0-9_]+)', code)
        props = gb_props or db_props
        if props and not any(g["method"] == meth_name for g in grids):
            grids.append({
                "method": meth_name,
                "var": meth_name,
                "props": props,
            })

    # 3) 단일 buildGrid fallback
    if not grids:
        m_single = re.search(
            r"^-\s+그리드[^\n]*\((.+)\)\s*:\s*\n((?:\s+-\s+[^\n]+\n)+)",
            section_text,
            re.MULTILINE,
        )
        if m_single:
            parens = m_single.group(1)
            meth_m = re.search(GRID_METHOD_NAME_PATTERN, parens)
            meth_name = meth_m.group(0) if meth_m else "buildGrid"
            props = [
                re.search(r'^\s*-\s+([a-zA-Z0-9_]+)', line).group(1)
                for line in m_single.group(2).strip().splitlines()
                if re.search(r'^\s*-\s+([a-zA-Z0-9_]+)', line)
            ]
            if props:
                grids.append({"method": meth_name, "var": meth_name, "props": props})

    if not grids:
        return []

    mod_m = re.search(r"Grid<([A-Z]\w+Model)>|GridBuilder<([A-Z]\w+)>|\b([A-Z]\w*_\w*Model)\b", section_text)
    default_model_name = next((g for g in mod_m.groups() if g), "") if mod_m else ""
    if not default_model_name:
        cls_base = target_section or stem
        default_model_name = cls_base.replace("_Tab_", "_").replace("_TabPage_", "_").replace("_Page_", "_") + "Model"

    for g in grids:
        m_spec_model = re.search(rf"{g['method']}[^;\n]*?([A-Z]\w+Model)|([A-Z]\w+Model)[^;\n]*?{g['method']}", section_text)
        model_name = (
            (m_spec_model.group(1) or m_spec_model.group(2))
            if m_spec_model
            else default_model_name
        )
        prop_to_col, _ns, _tbl, _aliases = find_mapper_for_model(model_name, roots)
        tbl_pfx = (re.match(r"^([a-z]+\d*)_", _tbl).group(1) + "_") if (_tbl and re.match(r"^([a-z]+\d*)_", _tbl)) else ""
        NON_DATA_PROPS = {"rownumberer", "checkboxselection", "actioncell"}
        tobe_props = set()
        for p in g["props"]:
            if p.lower() in NON_DATA_PROPS or p.lower().endswith("actioncell"):
                continue
            col = prop_to_col.get(p, "")
            tobe_props.add(col_to_tobe_prop(col, tbl_pfx) if col else p)
        g["cols"] = tobe_props

    return grids



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
    as_user: str = "admin",
    sql_total_ref: str | None = None,
    from_log: bool = False,
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

    # 1. API 호출
    api_res = request_api(
        method=method,
        path=path,
        base_url=base_url,
        as_role=as_user,
        company_code=company,
        tenant=tenant,
        params=api_params if method.upper() == "GET" else None,
        json_body=api_params if method.upper() != "GET" else None,
    )
    if not api_res.ok and not api_res.data:
        return ToolResult(ok=False, error=f"API 호출 실패: {api_res.error}")

    user_info = (api_res.data or {}).get("user_info") or {}
    if user_info:
        if "empId" not in sql_params and user_info.get("user_id") is not None:
            sql_params["empId"] = str(user_info["user_id"])
        if "orgId" not in sql_params and user_info.get("org_id") is not None:
            sql_params["orgId"] = str(user_info["org_id"])
        if "companyId" not in sql_params and user_info.get("company_id") is not None:
            sql_params["companyId"] = str(user_info["company_id"])

    # --from-log 처리
    used_params_msg = ""
    if from_log:
        trace_id = (api_res.data or {}).get("trace_id")
        if trace_id:
            log_p = extract_trace_sql_params(trace_id, sql_ref, req_path=path)
            merged = dict(log_p)
            merged.update(sql_params)
            sql_params = merged
        if sql_params:
            p_items = [f"{k}={v}" for k, v in sorted(sql_params.items())]
            used_params_msg = f"\n사용한 파라미터: {', '.join(p_items)}"

    # 2. SQL 렌더링
    stmts = {}
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

    raw_data = raw_json.get("data") if isinstance(raw_json, dict) and "data" in raw_json else raw_json
    if raw_data is None and isinstance(raw_json, list):
        raw_data = raw_json

    compare_conf = config.TOML_CONFIG.get("compare", {})
    paging_keys = compare_conf.get("paging_keys") or ["rows", "total"]
    rows_key = paging_keys[0] if len(paging_keys) > 0 else "rows"
    total_key = paging_keys[1] if len(paging_keys) > 1 else "total"

    is_paging = False
    api_total = 0
    api_rows_list: list[Any] = []
    api_fields: set[str] = set()

    if isinstance(raw_data, dict) and rows_key in raw_data and total_key in raw_data and isinstance(raw_data[rows_key], list):
        is_paging = True
        api_rows_list = raw_data[rows_key]
        try:
            api_total = int(raw_data[total_key])
        except (ValueError, TypeError):
            api_total = len(api_rows_list)
        api_row_count = len(api_rows_list)
        if api_rows_list and isinstance(api_rows_list[0], dict):
            api_fields.update(api_rows_list[0].keys())
    else:
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
        for row in api_rows_list:
            if isinstance(row, dict):
                api_fields.update(row.keys())

    # 3. SQL 실행 (Read-Only)
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

    # 페이징인 경우 총건수 대조
    if is_paging:
        sql_total = None
        if sql_total_ref:
            try:
                ns_t, sid_t = sql_total_ref.split(".", 1) if "." in sql_total_ref else ("", sql_total_ref)
                if sql_total_ref in stmts or any(s.sid == sid_t for s in stmts.values()):
                    total_sql, _ = mr_render(sql_total_ref, params=sql_params, mode="params", statements=stmts)
                else:
                    xml_path_t = find_mapper_file(ns_t, src_root)
                    if xml_path_t:
                        xml_text_t = xml_path_t.read_text(encoding="utf-8", errors="replace")
                        total_sql, _ = render_mybatis_sql(xml_text_t, sid_t, sql_params)
                    else:
                        total_sql = None
                if total_sql:
                    with psycopg.connect(conn_str, autocommit=False) as conn:
                        conn.read_only = True
                        with conn.cursor() as cur:
                            cur.execute(total_sql)
                            t_row = cur.fetchone()
                            if t_row:
                                sql_total = int(t_row[0])
            except Exception:  # noqa: BLE001, S110
                pass
        elif "LIMIT" in sql.upper():
            inner_sql = re.sub(r'\s+LIMIT\s+[0-9]+(?:\s+OFFSET\s+[0-9]+)?', '', sql, flags=re.IGNORECASE)
            inner_sql = re.sub(r'\s+OFFSET\s+[0-9]+(?:\s+LIMIT\s+[0-9]+)?', '', inner_sql, flags=re.IGNORECASE)
            cnt_query = f"SELECT count(*) FROM ({inner_sql}) _cnt_sub"
            try:
                with psycopg.connect(conn_str, autocommit=False) as conn:
                    conn.read_only = True
                    with conn.cursor() as cur:
                        cur.execute(cnt_query)
                        t_row = cur.fetchone()
                        if t_row:
                            sql_total = int(t_row[0])
            except Exception:  # noqa: BLE001, S110
                pass

        if sql_total is None:
            sql_total = sql_row_count

        rows_match = (api_total == sql_total)
        rows_mark = "✅" if rows_match else "❌"
        if api_row_count == api_total:
            count_part = f"API total={api_total} (rows={api_row_count}), SQL total={sql_total} {rows_mark}"
        else:
            count_part = f"API total={api_total} (이번 페이지 rows={api_row_count}), SQL total={sql_total} {rows_mark}"
    else:
        rows_match = (api_row_count == sql_row_count)
        rows_mark = "✅" if rows_match else "❌"
        count_part = f"API rows={api_row_count}, SQL rows={sql_row_count} {rows_mark}"

    # 테이블 접두어 추출
    tbl_pfx_m = re.match(r"^([a-z]+\d*)_", ns)
    tbl_prefix = (tbl_pfx_m.group(1) + "_") if tbl_pfx_m else ""

    # Grid Spec 컬럼 우선 매핑, 없으면 SQL 컬럼 사용
    grid_info = find_screen_grid_info(sql_ref, src_root, grid_class=grid, api_fields=api_fields)
    if grid_info.get("not_found"):
        search_dir = grid_info.get("search_dir", "")
        search_suffix = f" (탐색 폴더: {search_dir})" if search_dir else ""
        summary_line = f"{count_part}  ⚠ 그리드 못 찾음: {grid_info['class_name']}{search_suffix}"
        if used_params_msg:
            summary_line += f"\n{used_params_msg.strip()}"
        return ToolResult(
            ok=True,
            data={
                "summary": summary_line,
                "api_rows": api_row_count,
                "sql_rows": sql_row_count,
                "rows_match": rows_match,
                "cols_covered": False,
                "api_fields": sorted(api_fields),
                "expected_fields": [],
                "missing_fields": [],
                "rendered_sql": sql,
                "trace_id": (api_res.data or {}).get("trace_id"),
                "user_info": user_info,
            },
        )

    grid_cols = grid_info.get("cols")
    grid_label = grid_info.get("label", "")
    if grid_cols:
        expected_fields = grid_cols
        cols_desc = f" ({grid_label}, {len(expected_fields)}컬럼)"
    else:
        expected_fields = {col_to_tobe_prop(c, tbl_prefix) for c in sql_cols}
        cols_desc = ""

    missing_fields = {f for f in expected_fields if not _field_covered(f, api_fields)}
    cols_covered = (len(missing_fields) == 0)
    cols_mark = "✅" if cols_covered else "⚠️"

    if api_row_count == 0:
        summary_line = f"{count_part}  필드 비교 못 함 (행 0건){cols_desc}"
    else:
        summary_parts = [
            count_part,
            f"fields ⊇ grid cols {cols_mark}{cols_desc}",
        ]
        if not cols_covered and api_fields:
            summary_parts.append(f"(missing: {', '.join(sorted(missing_fields))})")
        summary_line = "  ".join(summary_parts)

    if used_params_msg:
        summary_line += f"\n{used_params_msg.strip()}"

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
            "trace_id": (api_res.data or {}).get("trace_id"),
            "user_info": user_info,
        },
    )
