"""그리드 한 개의 정확한 모양 및 GridType 판정 도구."""

import re
from typing import Any

from yunhee.tools.analysis.common import resolve_as_is_paths
from yunhee.tools.as_is.events import (
    KNOWN_GB_OPS,
    col_to_tobe_prop,
    find_mapper_for_model,
)
from yunhee.tools.as_is.src_indexer import find_app, paren_end, split_args

NAME = "grid"
DESCRIPTION = "그리드 한 개의 정확한 모양 및 ColumnModel 순서, GridType 판정"
TARGET_HELP = "<클래스>[.<그리드 필드>]"
FORMATS = ("md", "code")
EXAMPLES = [
    "yunhee analysis grid Org00_Lookup_SelectSingle",
    "yunhee analysis grid Emp00_Tab_TransInfo",
    "yunhee analysis grid Emp03_TabPage_Trans",
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


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """클래스 소스에서 그리드 빌더 및 설정 정보를 파싱한다."""
    target_clean = target.strip()
    _grid_var_filter = None
    if "." in target_clean:
        cls_name, _grid_var_filter = target_clean.split(".", 1)
    else:
        cls_name = target_clean

    src_root, _ = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    if not src_root or not src_root.is_dir():
        raise ValueError("AS-IS 소스 디렉터리를 찾을 수 없습니다. --src 옵션을 지정하세요.")

    app = find_app(src_root) or src_root

    # 클래스 파일 검색
    cls_file = next(app.rglob(f"{cls_name}.java"), None)
    if not cls_file:
        raise ValueError(f"클래스 소스 파일을 찾을 수 없습니다: {cls_name}.java")

    text = cls_file.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()

    # 1. 그리드 빌더 변수 및 모델 탐색
    m_builder = re.search(r"GridBuilder<([A-Z]\w+Model)>", text)
    model_name = m_builder.group(1) if m_builder else f"{cls_name}Model"

    builder_vars = set(re.findall(r"GridBuilder(?:<[^>]*>)?\s+(\w+)\s*=", text))
    if not builder_vars:
        builder_vars = {"gridBuilder", "builder", "gb"}
    builder_alt = "|".join(re.escape(v) for v in builder_vars)

    # 2. 그리드 옵션 탐색
    checked_type = None
    m_checked = re.search(
        rf"(?:{builder_alt})\.setChecked\(\s*(?:SelectionMode\.)?(\w+)\s*\)", text
    )
    if m_checked:
        checked_type = m_checked.group(1).upper()

    row_num_hidden = bool(
        re.search(rf"(?:{builder_alt})\.setRowNumHidden\(\s*true\s*\)", text)
    )
    has_cell_edit = bool(
        re.search(rf"(?:{builder_alt})\.set(?:DoubleClickEdit|Edit)\b", text)
    )
    has_editors = False

    # 3. 컬럼 빌더 호출 목록 수집
    raw_cols: list[dict[str, Any]] = []
    add_re = re.compile(rf"(?<![\w.])(?:{builder_alt})\.(add\w+)\s*\(")

    for i, line in enumerate(lines):
        line_num = i + 1
        stripped = line.strip()
        if stripped.startswith("//"):
            continue

        m_c = add_re.search(line)
        if not m_c:
            continue

        meth = m_c.group(1)
        close_idx = paren_end(line, m_c.end() - 1)
        if close_idx < 0:
            raw_args_str = line[m_c.end() :].rstrip(";").removesuffix(")")
        else:
            raw_args_str = line[m_c.end() : close_idx]

        args = split_args(raw_args_str)
        if len(args) < 3:
            continue

        # args[0]: properties.orgCode() 또는 orgCode
        prop_m = re.search(r"\.(\w+)\s*(?:\(\s*\))?", args[0])
        prop = prop_m.group(1) if prop_m else re.sub(r"[^\w]", "", args[0])

        # args[1]: width
        w_m = re.search(r"\d+", args[1])
        width = int(w_m.group(0)) if w_m else 80

        # args[2]: label
        label = args[2].strip(" \t\"'")

        # args[3] 이상: 편집기
        editor_kind = None
        if len(args) >= 4:
            ed_arg = args[3].strip()
            if ed_arg and ed_arg != "null":
                has_editors = True
                if "TextField" in ed_arg:
                    editor_kind = "text"
                elif "DateField" in ed_arg or "MyDateField" in ed_arg:
                    editor_kind = "date"
                elif "ComboBox" in ed_arg:
                    editor_kind = "select"
                elif "NumberField" in ed_arg or "LongField" in ed_arg:
                    editor_kind = "number"
                elif "Lookup" in ed_arg or "Search" in ed_arg:
                    editor_kind = "lookup"
                else:
                    editor_kind = ed_arg

        renderer_desc = SPECIAL_RENDERERS.get(meth, "")

        raw_cols.append({
            "line": line_num,
            "meth": meth,
            "prop": prop,
            "width": width,
            "label": label,
            "editor": editor_kind,
            "renderer": renderer_desc,
        })

    # 4. setHidden 호출 분석
    hidden_calls = []
    static_hidden_indices: set[int] = set()
    for i, line in enumerate(lines):
        line_num = i + 1
        if line.strip().startswith("//"):
            continue
        m_hid = re.search(
            r"(?:getColumnModel\(\)\.setHidden|setColumnHidden)\s*\(\s*(\d+)\s*,\s*([^)]+)\)",
            line,
        )
        if m_hid:
            col_idx = int(m_hid.group(1))
            cond_val = m_hid.group(2).strip()

            # 해당 호출이 속한 메서드 이름 역추적
            caller_meth = "unknown"
            for j in range(i, -1, -1):
                m_m = re.search(r"\bpublic\s+[\w<>]+\s+(\w+)\s*\(", lines[j])
                if m_m:
                    caller_meth = m_m.group(1)
                    break

            # 상위 if 조건문 역추적
            cond = cond_val
            has_if = False
            for j in range(i, max(-1, i - 15), -1):
                up_line = lines[j].strip()
                m_if = re.search(r"(?:else\s+)?if\s*\((.*)\)", up_line)
                if m_if:
                    cond = m_if.group(1).strip()
                    has_if = True
                    break

            # 정적 숨김: 조건문 없이 빌더/생성자/초기화 시점에 true로 숨기는 경우만
            if cond_val == "true" and not has_if and (caller_meth in ("buildGrid", "unknown") or "grid" in caller_meth.lower()):
                static_hidden_indices.add(col_idx)

            hidden_calls.append({
                "line": line_num,
                "index": col_idx,
                "caller": caller_meth,
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

    # 동적 숨김 호출에 열 이름 매핑
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

    for fc in final_cols:
        p = fc["prop"]
        col = prop_to_col.get(p, "")
        fc["col"] = col
        fc["tobe_prop"] = col_to_tobe_prop(col, tbl_pfx) if col else p

    return {
        "cls": cls_name,
        "model": model_name,
        "grid_type": grid_type,
        "checked_type": checked_type,
        "row_num_hidden": row_num_hidden,
        "columns": final_cols,
        "hidden_calls": hidden_calls,
    }


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    cls_name = obj["cls"]
    grid_type = obj["grid_type"]
    cols = obj["columns"]
    hidden_calls = obj["hidden_calls"]

    if fmt == "code":
        lines = [f"// GridType: {grid_type}", "const buildGrid = () => ["]
        for c in cols:
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
        return "\n".join(lines)

    # 기본 md 요약
    lines = [f"### 그리드 `{cls_name}` (유형: `{grid_type}`)"]
    if obj.get("checked_type"):
        lines.append(f"- **선택 모드**: `{obj['checked_type']}`")
    lines.append("\n| index | 속성 | 폭 | 제목 | GridBuilder 메서드 | 렌더링 | 편집기 | 숨김 |")
    lines.append("|:---|:---|:---|:---|:---|:---|:---|:---|")
    for c in cols:
        hid_str = "숨김" if c.get("hidden") else ""
        ed_str = c.get("editor") or ""
        ren_str = c.get("renderer") or ""
        lines.append(
            f"| {c['index']} | {c['prop']} | {c['width']} | {c['label']} | {c['meth']} | {ren_str} | {ed_str} | {hid_str} |"
        )

    if hidden_calls:
        lines.append("\n**동적 숨김 호출**:")
        for h in hidden_calls:
            col_info = f" ({h['col_name']})" if h.get("col_name") else ""
            lines.append(
                f"- index {h['index']}{col_info} ({h['caller']} L{h['line']}): 조건 `{h['cond']}`"
            )

    return "\n".join(lines)
