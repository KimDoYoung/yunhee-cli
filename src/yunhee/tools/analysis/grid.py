"""그리드 한 개의 정확한 모양 및 GridType 판정 도구."""

import json
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


def _parse_single_grid(
    cls_name: str,
    meth_name: str,
    field_name: str | None,
    grid_text: str,
    start_line_offset: int,
    full_text: str,
    app: Any,
    src_root: Any,
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

    # 3. 컬럼 빌더 호출 목록 수집
    raw_cols: list[dict[str, Any]] = []
    add_re = re.compile(rf"(?<![\w.])(?:{builder_alt})\.(add\w+)\s*\(")

    for i, line in enumerate(lines):
        line_num = start_line_offset + i
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

        prop_m = re.search(r"\.(\w+)\s*(?:\(\s*\))?", args[0])
        prop = prop_m.group(1) if prop_m else re.sub(r"[^\w]", "", args[0])

        w_m = re.search(r"\d+", args[1])
        width = int(w_m.group(0)) if w_m else 80

        label = args[2].strip(" \t\"'")

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

    for fc in final_cols:
        p = fc["prop"]
        col = prop_to_col.get(p, "")
        fc["col"] = col
        fc["tobe_prop"] = col_to_tobe_prop(col, tbl_pfx) if col else p

    return {
        "method": meth_name,
        "field": field_name,
        "model": model_name,
        "grid_type": grid_type,
        "checked_type": checked_type,
        "row_num_hidden": row_num_hidden,
        "columns": final_cols,
        "hidden_calls": hidden_calls,
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

    src_root, _ = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
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
        if re.search(r"GridBuilder\b", m_text)
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
        "grid_type": first_g.get("grid_type", "SingleGrid"),
        "checked_type": first_g.get("checked_type"),
        "row_num_hidden": first_g.get("row_num_hidden", False),
        "columns": first_g.get("columns", []),
        "hidden_calls": first_g.get("hidden_calls", []),
    }


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    cls_name = obj["cls"]
    grids = obj.get("grids", [])
    is_filtered = obj.get("is_filtered", False)

    if not grids:
        grids = [{
            "method": "buildGrid",
            "field": None,
            "model": obj.get("model", ""),
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
        lines = [f"### 그리드 `{cls_name}` (유형: `{grid_type}`)"]
        if g.get("checked_type"):
            lines.append(f"- **선택 모드**: `{g['checked_type']}`")
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

    # 둘 이상이거나 특정 메서드로 필터링된 경우
    tables = []
    for g in grids:
        title_name = f"{g['field']} = {g['method']}()" if g.get("field") else f"{g['method']}()"
        grid_type = g["grid_type"]
        cols = g["columns"]
        hidden_calls = g["hidden_calls"]
        lines = [f"### 그리드 `{title_name}` (유형: `{grid_type}`, 모델: `{g['model']}`)"]
        if g.get("checked_type"):
            lines.append(f"- **선택 모드**: `{g['checked_type']}`")
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
        tables.append("\n".join(lines))

    return "\n\n".join(tables)
