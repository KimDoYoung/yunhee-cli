"""그리드 한 개의 정확한 모양 및 GridType 판정 도구."""

import json
import re
from typing import Any

from yunhee.tools.analysis import model as model_analyzer
from yunhee.tools.analysis.common import resolve_as_is_paths
from yunhee.tools.as_is.events import (
    KNOWN_GB_OPS,
    class_sql_ids,
    col_to_tobe_prop,
    find_mapper_for_model,
)
from yunhee.tools.as_is.mybatis_render import get_all_statements
from yunhee.tools.as_is.src_indexer import find_app, paren_end, split_args

NAME = "grid"
DESCRIPTION = "그리드 한 개의 정확한 모양 및 ColumnModel 순서, GridType 판정"
TARGET_HELP = "<클래스>[.<그리드 필드>]"
FORMATS = ("md", "code", "json")
EXAMPLES = [
    "yunhee analysis grid Org00_Lookup_SelectSingle",
    "yunhee analysis grid Sys05_Tab_PersonRole",
    "yunhee analysis grid Sys05_Tab_PersonRole --method buildRoleGrid",
]

# 특수 렌더러 사전
SPECIAL_RENDERERS: dict[str, str] = {
    "addOfficer": 'true→"임원", 아니면 " "',
    "addOfficerYn": 'true→"등기", false→"비등기"',
    "addBoolean": "체크박스",
    "addBooleanHtml": "체크박스",
    "addBooleanYn2": "✓/빈칸",
    "addBooleanYn": "true→Y, false→N",
    "addDate": "날짜 (YYYY-MM-DD)",
    "addDateTime": "일시 (YYYY-MM-DD HH:mm)",
    "addMoney": "금액 (천단위 콤마)",
    "addCode": "공통코드명",
    "addText": "텍스트",
    "addTextCenter": "텍스트(가운데)",
    "addLong": "정수",
    "addDouble": "실수",
}


def _extract_methods_with_braces(text: str) -> list[tuple[str, str, int]]:
    """Java 소스에서 메서드명, 메서드 본문, 시작 줄 번호를 추출한다."""
    methods: list[tuple[str, str, int]] = []
    # 메서드 시그니처 매칭
    sig_re = re.compile(
        r"^[ \t]*(?:public|protected|private)?\s*(?:static\s+)?(?:final\s+)?(?:Grid<[^>]+>|[\w<>\[\],]+)\s+(\w+)\s*\([^)]*\)[^{;\n]*\{",
        re.MULTILINE,
    )

    for m in sig_re.finditer(text):
        name = m.group(1)
        if name in ("if", "for", "while", "switch", "catch", "synchronized"):
            continue
        start_pos = m.start()
        brace_pos = m.end() - 1

        # 중괄호 깊이 추적
        depth = 0
        end_pos = len(text)
        for i in range(brace_pos, len(text)):
            ch = text[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end_pos = i + 1
                    break

        meth_text = text[start_pos:end_pos]
        start_line = text.count("\n", 0, start_pos) + 1
        methods.append((name, meth_text, start_line))

    return methods


def _find_grid_sqls(full_text: str, ns: str, app: Any, src_root: Any) -> list[str]:
    """화면 소스에서 그리드 모델의 매퍼(ns)에 해당하는 조회 SQL ID(ns.sid) 목록을 찾는다."""
    if not ns:
        return []
    try:
        stmts = get_all_statements(src_root)
    except Exception:  # noqa: BLE001
        stmts = {}

    # 1. GridRetrieveData.retrieve("...") 또는 select* 서비스 메서드 호출을 우선 탐색
    retrieve_calls = re.findall(
        r'\.retrieve\s*\(\s*"([a-z]\w*\.[A-Z]\w*\.\w+)"', full_text
    )
    select_srv_calls = re.findall(
        r'"([a-z]\w*\.[A-Z]\w*\.(?:select|search|retrieve)\w*)"', full_text
    )
    priority_text = "\n".join(f'"{k}"' for k in (retrieve_calls + select_srv_calls))
    priority_sids = class_sql_ids(priority_text, [app, src_root]) if priority_text else []
    all_sids = priority_sids + [s for s in class_sql_ids(full_text, [app, src_root]) if s not in priority_sids]

    def _collect(sids_list: list[str]) -> list[str]:
        res: list[str] = []
        for sid in sids_list:
            full_key = f"{ns}.{sid}"
            if full_key in stmts:
                if stmts[full_key].kind == "select" and full_key not in res:
                    res.append(full_key)
            elif sid.lower().startswith("select") and not stmts and full_key not in res:
                res.append(full_key)
        return res

    prio_matched = _collect(priority_sids)
    if prio_matched:
        return prio_matched
    return _collect(all_sids)


def _parse_single_grid(
    cls_name: str,
    meth_name: str,
    field_name: str | None,
    grid_text: str,
    start_line_offset: int,
    full_text: str,
    app: Any,
    src_root: Any,
    src_index: Any = None,
    sql_opt: str | None = None,
    check_columns: bool = True,
) -> dict[str, Any]:
    lines = grid_text.splitlines()

    # 1. 그리드 빌더 변수 및 모델 탐색
    m_builder = re.search(r"GridBuilder<([A-Z]\w+Model)>", grid_text)
    if not m_builder:
        m_builder = re.search(r"GridBuilder<([A-Z]\w+Model)>", full_text)
    model_name = m_builder.group(1) if m_builder else f"{cls_name}Model"

    builder_vars = set(re.findall(r"GridBuilder(?:<[^>]*>)?\s+(\w+)\s*=", grid_text))
    if not builder_vars:
        builder_vars = set(re.findall(r"GridBuilder(?:<[^>]*>)?\s+(\w+)\s*=", full_text))
    if not builder_vars:
        builder_vars = {"gridBuilder", "builder", "gb"}
    builder_alt = "|".join(re.escape(v) for v in builder_vars)

    # 2. 그리드 옵션 탐색
    checked_type = None
    m_checked = re.search(
        rf"(?:{builder_alt})\.setChecked\(\s*(?:SelectionMode\.)?(\w+)\s*\)", grid_text
    )
    if m_checked:
        checked_type = m_checked.group(1).upper()

    row_num_hidden = bool(
        re.search(rf"(?:{builder_alt})\.setRowNumHidden\(\s*true\s*\)", grid_text)
    )
    has_cell_edit = bool(
        re.search(rf"(?:{builder_alt})\.set(?:DoubleClickEdit|Edit)\b", grid_text)
    )
    has_editors = False

    # 2-1. 다단 헤더 그룹 (HeaderGroupConfig / HeaderGroupMap) 추출 (#6)
    header_groups: list[dict[str, Any]] = []
    for m_hgm_full in re.finditer(
        r"HeaderGroupMap\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*new\s+HeaderGroupConfig\s*\(\s*\"([^\"]+)\"\s*(?:,\s*(\d+)\s*,\s*(\d+))?",
        grid_text,
    ):
        header_groups.append({
            "title": m_hgm_full.group(3),
            "row": int(m_hgm_full.group(1)),
            "col": int(m_hgm_full.group(2)),
            "row_span": int(m_hgm_full.group(4)) if m_hgm_full.group(4) else 1,
            "col_span": int(m_hgm_full.group(5)) if m_hgm_full.group(5) else 1,
        })
    for m_hg in re.finditer(
        r"addHeaderGroup\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(?:new\s+HeaderGroupConfig\s*\(\s*)?\"([^\"]+)\"\s*(?:,\s*(\d+)\s*,\s*(\d+))?",
        grid_text,
    ):
        title = m_hg.group(3)
        if not any(h["title"] == title and h["col"] == int(m_hg.group(2)) for h in header_groups):
            header_groups.append({
                "title": title,
                "row": int(m_hg.group(1)),
                "col": int(m_hg.group(2)),
                "row_span": int(m_hg.group(4)) if m_hg.group(4) else 1,
                "col_span": int(m_hg.group(5)) if m_hg.group(5) else 1,
            })
    for m_hgm in re.finditer(
        r"new\s+HeaderGroup(?:Map|Config)\s*\(\s*\"([^\"]+)\"\s*,\s*(\d+)\s*,\s*(\d+)\s*\)",
        grid_text,
    ):
        title = m_hgm.group(1)
        if not any(h["title"] == title for h in header_groups):
            header_groups.append({
                "title": title,
                "row": 0,
                "col": int(m_hgm.group(2)),
                "row_span": 1,
                "col_span": int(m_hgm.group(3)),
            })

    # 2-1b. 고정 열 (setFrozenNum / add*Frozen) 및 동적 헤더 (getColumn(...).setHeader(...)) 추출 (#6)
    frozen_cnt = 0
    m_frz = re.search(r"setFrozenNum\s*\(\s*(\d+)\s*\)", grid_text)
    if m_frz:
        frozen_cnt = int(m_frz.group(1))
    else:
        frozen_cnt = len(re.findall(r"\.add\w*Frozen\s*\(", grid_text))

    dynamic_headers: list[str] = []
    for m_dh_meth, m_dh_body, _ in _extract_methods_with_braces(full_text):
        cols_dh = re.findall(r"getColumn\s*\(\s*([^)]+)\s*\)\s*\.setHeader\s*\(", m_dh_body)
        if cols_dh:
            dynamic_headers.append(f"{m_dh_meth} (열 {', '.join(dict.fromkeys(c.strip() for c in cols_dh))})")

    # 2-2. 합계 행 (AggregationRowConfig / SummaryType) 추출 (#6)
    summary_info: dict[str, Any] = {}
    sum_cols: list[str] = []
    count_cols: list[str] = []
    summary_label = "합계"
    if re.search(r"AggregationRowConfig|SummaryType|addAggregationRow|setSummaryType", grid_text):
        m_sum_lbl = re.search(r'setHtml\s*\(\s*[^,]+,\s*"([^"]+)"\s*\)', grid_text)
        if m_sum_lbl:
            summary_label = m_sum_lbl.group(1)
        for m_st in re.finditer(
            r"setSummaryType\s*\(\s*[^.]+\.(\w+)\s*\(\s*\)\s*,\s*(?:new\s+)?SummaryType\.(\w+)",
            grid_text,
        ):
            col_p, st_kind = m_st.group(1), m_st.group(2).lower()
            if "count" in st_kind:
                count_cols.append(col_p)
            else:
                sum_cols.append(col_p)
        for m_agg in re.finditer(r"addAggregation\w*\s*\(\s*[^.]+\.(\w+)\s*\(\s*\)", grid_text):
            col_p = m_agg.group(1)
            if col_p not in sum_cols:
                sum_cols.append(col_p)
        summary_info = {
            "label": summary_label,
            "sumCols": sum_cols,
            "countCols": count_cols,
        }

    # 2-3. 클래스 내 콤보박스 선택지 사전 (#6)
    from yunhee.tools.analysis.method import _extract_combo_options

    combo_opts_map = _extract_combo_options(full_text)

    # 2-4. 커스텀 셀 렌더러 (setCell(new AbstractCell...)) 추출 (#6)
    custom_renderers: dict[str, str] = {}
    for m_cell in re.finditer(
        r"(\w+)\.setCell\s*\(\s*new\s+AbstractCell[^{]*\{(.*?)\}\s*\)",
        grid_text,
        re.DOTALL,
    ):
        col_var = m_cell.group(1)
        cell_body = m_cell.group(2)
        m_ap = re.search(r"append(?:HtmlConstant|Escaped)?\s*\(([^;]+)\)", cell_body)
        if m_ap:
            expr = re.sub(r"\s+", " ", m_ap.group(1)).strip()
            custom_renderers[col_var] = expr[:60]

    # 3. 컬럼 빌더 호출 목록 수집
    raw_cols: list[dict[str, Any]] = []
    add_re = re.compile(rf"(?:(\w+)\s*=\s*)?(?<![\w.])(?:{builder_alt})\.(add\w+)\s*\(")

    for i, line in enumerate(lines):
        line_num = start_line_offset + i
        stripped = line.strip()
        if stripped.startswith("//"):
            continue

        m_c = add_re.search(line)
        if not m_c:
            continue

        col_var_lhs = m_c.group(1) or ""
        meth = m_c.group(2)
        if meth in ("addHeaderGroupMap", "addHeaderGroup", "addAggregationRow"):
            continue
        close_idx = paren_end(line, m_c.end() - 1)
        if close_idx < 0:
            raw_args_str = line[m_c.end() :].rstrip(";").removesuffix(")")
        else:
            raw_args_str = line[m_c.end() : close_idx]

        args = split_args(raw_args_str)
        if len(args) < 3:
            continue

        prop_m = re.search(r"\.(\w+)\s*(?:\(\s*\))?", args[0])
        prop = prop_m.group(1) if prop_m else re.sub(r"[^\w]", "", args[0])
        if prop in ("new", "") or prop.startswith("newHeaderGroup"):
            continue

        # addComboBox(prop, comboVar, width, label) 인자 순서 호환
        if len(args) >= 4 and not re.search(r"^\d+$", args[1].strip()) and re.search(r"^\d+$", args[2].strip()):
            args = [args[0], args[2], args[3], args[1]] + args[4:]

        w_m = re.search(r"\d+", args[1])
        width = int(w_m.group(0)) if w_m else 80

        label = args[2].strip(" \t\"'")

        editor_kind = None
        editor_detail = None
        checkbox_editable: bool | None = None
        is_action_cell = (
            meth == "addCell"
            or prop == "actionCell"
            or (len(args) >= 4 and any(kw in args[3] for kw in ("ImageCell", "ActionCell", "actionCell")))
        )
        if meth in ("addBoolean", "addBooleanHtml"):
            # CheckBoxCell 편집 가능 여부 판정 (#6)
            if len(args) >= 4 and args[3].strip() == "false":
                checkbox_editable = False
            elif len(args) >= 4 and args[3].strip() != "null":
                checkbox_editable = True
                editor_kind = "checkbox"
                has_editors = True
            else:
                checkbox_editable = True
                if has_cell_edit:
                    editor_kind = "checkbox"

        if len(args) >= 4 and not is_action_cell:
            ed_arg = args[3].strip()
            if ed_arg and ed_arg != "null":
                if "TextField" in ed_arg:
                    editor_kind = "text"
                    has_editors = True
                elif "DateField" in ed_arg or "MyDateField" in ed_arg:
                    editor_kind = "date"
                    has_editors = True
                elif "ComboBox" in ed_arg or ed_arg in combo_opts_map:
                    editor_kind = "select"
                    has_editors = True
                    c_var_m = re.match(r"^(?:this\.)?(\w+)$", ed_arg)
                    c_var = c_var_m.group(1) if c_var_m else ""
                    if c_var and c_var in combo_opts_map:
                        editor_detail = f"select({c_var}: {', '.join(combo_opts_map[c_var][:5])})"
                    elif c_var:
                        editor_detail = f"select({c_var})"
                elif "NumberField" in ed_arg or "LongField" in ed_arg or "DoubleField" in ed_arg:
                    editor_kind = "number"
                    has_editors = True
                elif "CheckBox" in ed_arg:
                    editor_kind = "checkbox"
                    checkbox_editable = True
                    has_editors = True
                elif "Lookup" in ed_arg or "Search" in ed_arg or "TriggerField" in ed_arg:
                    editor_kind = "lookup"
                    has_editors = True
                    l_var = ed_arg.replace("this.", "").strip()
                    editor_detail = f"lookup({l_var})"

        renderer_desc = SPECIAL_RENDERERS.get(meth, "")
        if checkbox_editable is True:
            renderer_desc = "체크박스(편집)"
        elif checkbox_editable is False and meth in ("addBoolean", "addBooleanHtml"):
            renderer_desc = "체크박스(표시)"
        if col_var_lhs and col_var_lhs in custom_renderers:
            renderer_desc = f"커스텀({custom_renderers[col_var_lhs]})"
        if is_action_cell and not renderer_desc:
            renderer_desc = "아이콘"

        raw_cols.append({
            "line": line_num,
            "meth": meth,
            "prop": prop,
            "width": width,
            "label": label,
            "editor": editor_kind,
            "editor_detail": editor_detail,
            "checkbox_editable": checkbox_editable,
            "renderer": renderer_desc,
        })

    # 4. setHidden 호출 분석
    hidden_calls = []
    static_hidden_indices: set[int] = set()
    for i, line in enumerate(lines):
        line_num = start_line_offset + i
        if line.strip().startswith("//"):
            continue
        m_hid = re.search(
            r"(?:getColumnModel\(\)\.setHidden|setColumnHidden)\s*\(\s*(\d+)\s*,\s*([^)]+)\)",
            line,
        )
        if m_hid:
            col_idx = int(m_hid.group(1))
            cond_val = m_hid.group(2).strip()

            cond = cond_val
            has_if = False
            for j in range(i, max(-1, i - 15), -1):
                up_line = lines[j].strip()
                m_if = re.search(r"(?:else\s+)?if\s*\((.*)\)", up_line)
                if m_if:
                    cond = m_if.group(1).strip()
                    has_if = True
                    break

            if cond_val == "true" and not has_if:
                static_hidden_indices.add(col_idx)

            hidden_calls.append({
                "line": line_num,
                "index": col_idx,
                "caller": meth_name,
                "cond": cond,
            })

    # 5. ColumnModel 인덱스 조립
    final_cols: list[dict[str, Any]] = []
    cur_idx = 0
    if not row_num_hidden:
        final_cols.append({
            "index": cur_idx,
            "prop": "rowNumberer",
            "width": 30,
            "label": "No",
            "meth": "RowNumberer",
            "renderer": "행번호",
            "editor": None,
            "hidden": False,
        })
        cur_idx += 1

    if checked_type:
        final_cols.append({
            "index": cur_idx,
            "prop": "checkBoxSelection",
            "width": 30,
            "label": "선택",
            "meth": f"setChecked({checked_type})",
            "renderer": "체크박스",
            "editor": None,
            "hidden": False,
        })
        cur_idx += 1

    for c in raw_cols:
        is_hidden = cur_idx in static_hidden_indices
        c_copy = dict(c)
        c_copy["index"] = cur_idx
        c_copy["hidden"] = is_hidden
        final_cols.append(c_copy)
        cur_idx += 1

    col_name_by_idx = {fc["index"]: fc["prop"] for fc in final_cols}
    for h in hidden_calls:
        h["col_name"] = col_name_by_idx.get(h["index"], "")

    # 6. GridType 판정
    if has_cell_edit or has_editors:
        grid_type = "CellEditGrid"
    elif checked_type in ("MULTI", "SIMPLE"):
        grid_type = "MultiGrid"
    else:
        grid_type = "SingleGrid"

    # 모델 정보 연결
    prop_to_col, _ns, tbl, _ = find_mapper_for_model(model_name, [app, src_root])
    tbl_pfx = (
        (re.match(r"^([a-z]+\d*)_", tbl).group(1) + "_")
        if (tbl and re.match(r"^([a-z]+\d*)_", tbl))
        else ""
    )

    candidate_sqls = _find_grid_sqls(full_text, _ns, app, src_root)
    if sql_opt:
        effective_sql = f"{_ns}.{sql_opt}" if ("." not in sql_opt and _ns) else sql_opt
    else:
        effective_sql = candidate_sqls[0] if candidate_sqls else None

    model_rows_by_prop: dict[str, dict[str, Any]] = {}
    if check_columns and effective_sql and _ns:
        try:
            m_res = model_analyzer.resolve(
                model_name,
                {"src": src_root, "src_index": src_index, "sql": effective_sql},
            )
            model_rows_by_prop = {r["prop"]: r for r in m_res.get("rows", [])}
        except Exception:  # noqa: BLE001, S110
            pass

    for fc in final_cols:
        p = fc["prop"]
        col = prop_to_col.get(p, "")
        fc["col"] = col
        fc["tobe_prop"] = col_to_tobe_prop(col, tbl_pfx) if col else p

        col_status = ""
        if model_rows_by_prop and p not in ("rowNumberer", "checkBoxSelection") and fc["meth"] != "addCell" and p != "actionCell":
            m_row = model_rows_by_prop.get(p)
            if m_row:
                st = m_row.get("sql_status", "")
                if st == "계산":
                    col_status = "계산"
                elif st.startswith("✅"):
                    col_status = "✅"
                elif "테이블에" in st:
                    col_status = "⚠ 테이블에 없음"
                else:
                    col_status = "⚠ SQL에 없음"
            else:
                col_status = "⚠ SQL에 없음"
        fc["col_status"] = col_status

    return {
        "method": meth_name,
        "field": field_name,
        "model": model_name,
        "sql": effective_sql,
        "candidate_sqls": candidate_sqls,
        "grid_type": grid_type,
        "checked_type": checked_type,
        "row_num_hidden": row_num_hidden,
        "columns": final_cols,
        "hidden_calls": hidden_calls,
        "header_groups": header_groups,
        "summary_info": summary_info,
        "frozen_cnt": frozen_cnt,
        "dynamic_headers": dynamic_headers,
    }


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """클래스 소스에서 그리드 빌더 및 설정 정보를 파싱한다."""
    target_clean = target.strip()
    target_meth_filter = None
    if "#" in target_clean:
        cls_name, target_meth_filter = target_clean.split("#", 1)
    elif "." in target_clean:
        cls_name, target_meth_filter = target_clean.split(".", 1)
    else:
        cls_name = target_clean

    meth_opt = opts.get("method") or target_meth_filter
    sql_opt = opts.get("sql")
    check_columns = opts.get("check_columns", True)

    src_root, src_index = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    if not src_root or not src_root.is_dir():
        raise ValueError("AS-IS 소스 디렉터리를 찾을 수 없습니다. --src 옵션을 지정하세요.")

    app = find_app(src_root) or src_root

    # 클래스 파일 검색
    cls_file = next(app.rglob(f"{cls_name}.java"), None)
    if not cls_file:
        raise ValueError(f"클래스 소스 파일을 찾을 수 없습니다: {cls_name}.java")

    text = cls_file.read_text(encoding="utf-8", errors="replace")

    # 1. 필드 - 메서드 할당 추적 (예: userGrid = this.buildUserGrid();)
    field_by_method: dict[str, str] = {}
    for m in re.finditer(
        r"(?:private|protected|public)?\s*(?:Grid<[^>]+>|[\w<>]+)\s+(\w+)\s*=\s*(?:this\.)?(\w+)\s*\(\)",
        text,
    ):
        field_by_method[m.group(2)] = m.group(1)

    # 2. 메서드 목록 추출
    methods = _extract_methods_with_braces(text)
    grid_methods = [
        (m_name, field_by_method.get(m_name), m_text, m_line)
        for m_name, m_text, m_line in methods
        if re.search(r"(?:GridBuilder|GridGroupBuilder)\b", m_text)
    ]

    # 메서드 블록 밖에서 선언된 경우 fallback
    if not grid_methods:
        grid_methods = [("buildGrid", None, text, 1)]

    # 3. 각 메서드별 그리드 파싱
    parsed_grids = [
        _parse_single_grid(
            cls_name=cls_name,
            meth_name=m_name,
            field_name=f_name,
            grid_text=m_text,
            start_line_offset=m_line,
            full_text=text,
            app=app,
            src_root=src_root,
            src_index=src_index,
            sql_opt=sql_opt,
            check_columns=check_columns,
        )
        for m_name, f_name, m_text, m_line in grid_methods
    ]

    is_filtered = False
    if meth_opt:
        filtered = [
            g
            for g in parsed_grids
            if g["method"].lower() == meth_opt.lower()
            or (g.get("field") and g["field"].lower() == meth_opt.lower())
        ]
        if not filtered:
            raise ValueError(f"그리드 메서드 또는 필드를 찾을 수 없습니다: {meth_opt}")
        parsed_grids = filtered
        is_filtered = True

    first_g = parsed_grids[0] if parsed_grids else {}

    return {
        "cls": cls_name,
        "grids": parsed_grids,
        "is_filtered": is_filtered,
        # 단일 그리드 호환성 필드
        "model": first_g.get("model", ""),
        "sql": first_g.get("sql"),
        "grid_type": first_g.get("grid_type", "SingleGrid"),
        "checked_type": first_g.get("checked_type"),
        "row_num_hidden": first_g.get("row_num_hidden", False),
        "columns": first_g.get("columns", []),
        "hidden_calls": first_g.get("hidden_calls", []),
        "header_groups": first_g.get("header_groups", []),
        "summary_info": first_g.get("summary_info", []),
    }


def _render_grid_table(cols: list[dict[str, Any]], show_col_status: bool) -> list[str]:
    lines: list[str] = []
    if show_col_status:
        lines.append("\n| index | 속성 | 폭 | 제목 | GridBuilder 메서드 | 렌더링 | 편집기 | 숨김 | 컬럼 검증 |")
        lines.append("|:---|:---|:---|:---|:---|:---|:---|:---|:---|")
    else:
        lines.append("\n| index | 속성 | 폭 | 제목 | GridBuilder 메서드 | 렌더링 | 편집기 | 숨김 |")
        lines.append("|:---|:---|:---|:---|:---|:---|:---|:---|")
    for c in cols:
        hid_str = "숨김" if c.get("hidden") else ""
        ed_str = c.get("editor_detail") or c.get("editor") or ""
        if c.get("meth") == "addBoolean" and c.get("checkbox_editable") is not None and not ed_str:
            ed_str = "checkbox(편집가능)" if c["checkbox_editable"] else "checkbox(읽기전용)"
        ren_str = c.get("renderer") or ""
        if show_col_status:
            st_str = c.get("col_status") or ""
            lines.append(
                f"| {c['index']} | {c['prop']} | {c['width']} | {c['label']} | {c['meth']} | {ren_str} | {ed_str} | {hid_str} | {st_str} |"
            )
        else:
            lines.append(
                f"| {c['index']} | {c['prop']} | {c['width']} | {c['label']} | {c['meth']} | {ren_str} | {ed_str} | {hid_str} |"
            )
    return lines


def _render_grid_extra_meta(g: dict[str, Any]) -> list[str]:
    meta_lines: list[str] = []
    hgs = g.get("header_groups") or []
    if hgs:
        hg_strs = []
        for hg in hgs:
            cs = hg.get("col_span", hg.get("colspan", 1))
            rs = hg.get("row_span", hg.get("rowspan", 1))
            c_start = hg["col"]
            c_end = c_start + cs - 1
            hg_strs.append(
                f"`{hg['title']}` = 열 {c_start}~{c_end} (row={hg['row']}, col={c_start}, colspan={cs}, rowspan={rs})"
            )
        meta_lines.append(f"- **묶음 헤더 (2단 헤더 그룹)**: {' · '.join(hg_strs)}")
    if g.get("frozen_cnt"):
        meta_lines.append(f"- **고정 열**: 1~{g['frozen_cnt']}")
    if g.get("dynamic_headers"):
        meta_lines.append(f"- **동적 헤더**: {', '.join(g['dynamic_headers'])}")
    sums = g.get("summary_info")
    if sums:
        if isinstance(sums, dict):
            s_parts = [f"라벨=\"{sums.get('label', '합계')}\""]
            if sums.get("sumCols"):
                s_parts.append(f"합계={', '.join(sums['sumCols'])}")
            if sums.get("countCols"):
                s_parts.append(f"건수={', '.join(sums['countCols'])}")
            meta_lines.append(f"- **합계/집계 행**: {' · '.join(s_parts)}")
        elif isinstance(sums, list):
            meta_lines.append(f"- **합계/집계 행**: {', '.join(str(x) for x in sums)}")
    return meta_lines


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    cls_name = obj["cls"]
    grids = obj.get("grids", [])
    is_filtered = obj.get("is_filtered", False)
    check_columns = opts.get("check_columns", True) if opts else True

    if not grids:
        grids = [{
            "method": "buildGrid",
            "field": None,
            "model": obj.get("model", ""),
            "sql": obj.get("sql"),
            "grid_type": obj.get("grid_type", "SingleGrid"),
            "checked_type": obj.get("checked_type"),
            "columns": obj.get("columns", []),
            "hidden_calls": obj.get("hidden_calls", []),
        }]

    if fmt == "json":
        return json.dumps(grids, ensure_ascii=False, indent=2)

    if fmt == "code":
        out_blocks = []
        for g in grids:
            m_name = g.get("method") or "buildGrid"
            grid_type = g["grid_type"]
            lines = [f"// GridType: {grid_type}", f"const {m_name} = () => ["]
            for c in g["columns"]:
                if c["prop"] in ("rowNumberer", "checkBoxSelection"):
                    continue
                prop_key = c.get("tobe_prop", c["prop"])
                width = c["width"]
                label = c["label"]
                meth = c["meth"]
                gb_func = KNOWN_GB_OPS.get(meth, "gb.text")
                opt_parts = []
                if c.get("editor"):
                    opt_parts.append(f"editor: '{c['editor']}'")
                if c.get("hidden"):
                    opt_parts.append("hide: true")
                opt_str = f", {{ {', '.join(opt_parts)} }}" if opt_parts else ""
                lines.append(f"  {gb_func}('{prop_key}', {width}, '{label}'{opt_str}),")
            lines.append("];")
            out_blocks.append("\n".join(lines))
        return "\n\n".join(out_blocks)

    # 기본 md 요약
    if len(grids) == 1 and not is_filtered:
        g = grids[0]
        grid_type = g["grid_type"]
        cols = g["columns"]
        hidden_calls = g["hidden_calls"]
        show_col_status = check_columns and any(c.get("col_status") for c in cols)
        lines = [f"### 그리드 `{cls_name}` (유형: `{grid_type}`)"]
        if g.get("checked_type"):
            lines.append(f"- **선택 모드**: `{g['checked_type']}`")
        lines.extend(_render_grid_extra_meta(g))
        if show_col_status and g.get("sql"):
            cands = g.get("candidate_sqls") or []
            cand_note = f" (후보: {', '.join(cands)} — --sql로 지정 가능)" if len(cands) > 1 else ""
            lines.append(f"- **대조 SQL**: `{g['sql']}`{cand_note}")
        lines.extend(_render_grid_table(cols, show_col_status))
        if hidden_calls:
            lines.append("\n**동적 숨김 호출**:")
            for h in hidden_calls:
                col_info = f" ({h['col_name']})" if h.get("col_name") else ""
                lines.append(
                    f"- index {h['index']}{col_info} ({h['caller']} L{h['line']}): 조건 `{h['cond']}`"
                )
        return "\n".join(lines)

    # 둘 이상이거나 특정 메서드로 필터링된 경우
    tables = []
    for g in grids:
        title_name = f"{g['field']} = {g['method']}()" if g.get("field") else f"{g['method']}()"
        grid_type = g["grid_type"]
        cols = g["columns"]
        hidden_calls = g["hidden_calls"]
        show_col_status = check_columns and any(c.get("col_status") for c in cols)
        lines = [f"### 그리드 `{title_name}` (유형: `{grid_type}`, 모델: `{g['model']}`)"]
        if g.get("checked_type"):
            lines.append(f"- **선택 모드**: `{g['checked_type']}`")
        lines.extend(_render_grid_extra_meta(g))
        if show_col_status and g.get("sql"):
            cands = g.get("candidate_sqls") or []
            cand_note = f" (후보: {', '.join(cands)} — --sql로 지정 가능)" if len(cands) > 1 else ""
            lines.append(f"- **대조 SQL**: `{g['sql']}`{cand_note}")
        lines.extend(_render_grid_table(cols, show_col_status))
        if hidden_calls:
            lines.append("\n**동적 숨김 호출**:")
            for h in hidden_calls:
                col_info = f" ({h['col_name']})" if h.get("col_name") else ""
                lines.append(
                    f"- index {h['index']}{col_info} ({h['caller']} L{h['line']}): 조건 `{h['cond']}`"
                )
        tables.append("\n".join(lines))

    return "\n\n".join(tables)
