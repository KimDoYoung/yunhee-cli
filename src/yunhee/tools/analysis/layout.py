"""AS-IS GXT 폼 화면의 레이아웃(줄·칸 폭·라벨·읽기 전용) 정적 파서."""

import re
from typing import Any

from yunhee.tools.as_is.src_indexer import paren_end, split_args


def _parse_margins(margin_expr: str) -> str:
    """Margins 표현식을 m20, m0,50,0,0 등의 문자열로 변환한다."""
    m_match = re.search(r"new\s+Margins\s*\(([^)]+)\)", margin_expr)
    raw = m_match.group(1) if m_match else margin_expr
    m_args = [a.strip() for a in split_args(raw)]
    if not m_args:
        return ""
    if len(m_args) == 1:
        return f"m{m_args[0]}"
    if len(m_args) == 4:
        if m_args[0] == m_args[1] == m_args[2] == m_args[3]:
            return f"m{m_args[0]}"
        return f"m{','.join(m_args)}"
    return f"m{','.join(m_args)}"


def _format_size(w: str, h: str, margin_str: str = "", is_cell: bool = False) -> str:
    """폭, 높이, 여백을 규칙에 따라 포맷팅한다."""
    w = w.strip()
    h = h.strip()
    parts = []

    if w == "-1" and h == "-1":
        parts.append("auto")
    elif h == "-1":
        if w == "1":
            parts.append("1×auto")
        else:
            parts.append(w)
    else:
        parts.append(f"{w}×{h}")

    if not is_cell and margin_str and margin_str != "m0":
        parts.append(margin_str)

    return " ".join(parts)


def _find_class_methods(lines: list[str]) -> list[tuple[str, int, int]]:
    """클래스 직속 메서드들의 (이름, start_line, end_line)을 찾는다."""
    methods = []
    depth = 0
    in_class = False
    for idx, line in enumerate(lines):
        line_num = idx + 1
        clean = line.split("//")[0].strip()
        if not in_class:
            if re.search(r"\bclass\s+\w+", clean):
                in_class = True
                depth += clean.count("{") - clean.count("}")
            continue

        if depth == 1:
            m_decl = re.search(
                r"(?:private|protected|public)\s+[\w<>,\[\]]+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+[\w,\s]+)?\s*\{",
                clean,
            )
            if m_decl:
                m_name = m_decl.group(1)
                m_start = line_num
                m_depth = clean.count("{") - clean.count("}")
                m_end = line_num
                for k in range(idx + 1, len(lines)):
                    c_k = lines[k].split("//")[0].strip()
                    m_depth += c_k.count("{") - c_k.count("}")
                    if m_depth <= 0:
                        m_end = k + 1
                        break
                methods.append((f"{m_name}()", m_start, m_end))

        depth += clean.count("{") - clean.count("}")
    return methods


def parse_layout(java_text: str) -> str:
    """AS-IS Java 파일 내용에서 폼 레이아웃 구조를 추출한다."""
    lines = java_text.splitlines()

    # 1. 레이아웃 컨테이너 검출 (Horizontal/Vertical/HBox/VBox/CssFloat)
    container_types: dict[str, str] = {}  # var -> 'Horizontal' | 'Vertical' | 'HBox' | 'VBox'
    for line in lines:
        for m in re.finditer(
            r"\b(HorizontalLayoutContainer|VerticalLayoutContainer|HBoxLayoutContainer|VBoxLayoutContainer|CssFloatLayoutContainer)\s+(\w+)\s*=\s*new\b",
            line,
        ):
            raw_t = m.group(1)
            if "HBox" in raw_t:
                c_type = "HBox"
            elif "VBox" in raw_t:
                c_type = "VBox"
            elif "Horizontal" in raw_t or "CssFloat" in raw_t:
                c_type = "Horizontal"
            else:
                c_type = "Vertical"
            container_types[m.group(2)] = c_type

    if not container_types:
        extra_only = _extract_toolbar_and_style_constants(lines)
        if extra_only:
            return "#### 레이아웃 (툴바·스타일 상수)\n" + "\n".join(extra_only)
        return "레이아웃 없음 (폼 컨테이너를 찾지 못함)"

    # 1-b. 위젯 타입, 필수 여부(setAllowBlank(false)), 읽기 전용/비활성 사전 수집
    field_types: dict[str, str] = {}
    for line in lines:
        for m_ft in re.finditer(
            r"\b(TextField|MyTextField|DateField|MyDateField|TextArea|MyTextArea|ComboBox|CodeComboBox|SimpleComboBox|ComboBoxField|CommonComboBoxField|CheckBox|Radio|LookupTriggerField|NumberField|DoubleField|IntegerField|LongField|PasswordField|FileUploadField)(?:<[^>]+>)?\s+(\w+)\s*=\s*new\b",
            line,
        ):
            field_types[m_ft.group(2)] = m_ft.group(1)

    required_vars: set[str] = set()
    read_only_map: dict[str, list[str]] = {}
    for line in lines:
        s = line.strip()
        m_req = re.search(r"(?:this\.)?(\w+)\.setAllowBlank\s*\(\s*false\s*\)", s)
        if m_req:
            required_vars.add(m_req.group(1))
        m_ro = re.search(r"(?:this\.)?(\w+)\.setReadOnly\s*\(\s*true\s*\)", s)
        if m_ro:
            var = m_ro.group(1)
            read_only_map.setdefault(var, [])
            if "readOnly" not in read_only_map[var]:
                read_only_map[var].append("readOnly")
        m_dis = re.search(r"(?:this\.)?(\w+)\.(?:disable\(\)|setEnabled\s*\(\s*false\s*\))", s)
        if m_dis:
            var = m_dis.group(1)
            read_only_map.setdefault(var, [])
            if "disable" not in read_only_map[var]:
                read_only_map[var].append("disable")

    # 2. LayoutData 변수 수집: (var) -> (w, h, margin_str)
    layout_data_vars: dict[str, tuple[str, str, str]] = {}
    for line in lines:
        for m in re.finditer(
            r"\b(?:HorizontalLayoutData|VerticalLayoutData|BoxLayoutData|CssFloatData)\s+(\w+)\s*=\s*new\s+(?:HorizontalLayoutData|VerticalLayoutData|BoxLayoutData|CssFloatData)\s*\(([^;]+)\);",
            line,
        ):
            var_name = m.group(1)
            args = split_args(m.group(2))
            if "BoxLayoutData" in line:
                w = "-1"
                h = "-1"
                m_str = _parse_margins(args[0]) if args else ""
            else:
                w = args[0].strip() if len(args) > 0 else "-1"
                h = args[1].strip() if len(args) > 1 else "-1"
                m_str = ""
                if len(args) > 2:
                    m_str = _parse_margins(args[2])
            layout_data_vars[var_name] = (w, h, m_str)

    # 3. .add() 호출 수집: container -> list of children
    container_adds: dict[str, list[dict[str, Any]]] = {c: [] for c in container_types}
    for idx, line in enumerate(lines):
        line_num = idx + 1
        s = line.strip()
        m_add = re.search(r"\b(\w+)\.add\s*\(", s)
        if not m_add:
            continue
        c_var = m_add.group(1)
        if c_var not in container_types:
            continue

        p_open = s.find("(", m_add.start())
        p_close = paren_end(s, p_open)
        arg_str = s[p_open + 1 : p_close] if p_close > p_open else s[p_open + 1 :]
        args = split_args(arg_str)
        if not args:
            continue

        first_arg = args[0].strip()
        second_arg = args[1].strip() if len(args) > 1 else ""

        w, h, m_str = "-1", "-1", ""
        if second_arg in layout_data_vars:
            w, h, m_str = layout_data_vars[second_arg]
        elif second_arg:
            m_inline = re.search(
                r"new\s+(HorizontalLayoutData|VerticalLayoutData|BoxLayoutData|CssFloatData)\s*\((.*)\)",
                second_arg,
            )
            if m_inline:
                ld_type = m_inline.group(1)
                in_args = split_args(m_inline.group(2))
                if ld_type == "BoxLayoutData":
                    m_str = _parse_margins(in_args[0]) if in_args else ""
                else:
                    w = in_args[0].strip() if len(in_args) > 0 else "-1"
                    h = in_args[1].strip() if len(in_args) > 1 else "-1"
                    if len(in_args) > 2:
                        m_str = _parse_margins(in_args[2])

        # 첫 인자 분석
        m_fl = re.search(r"new\s+FieldLabel\s*\(\s*(\w+)\s*,\s*(.*)\)", first_arg)
        if m_fl:
            field_name = m_fl.group(1)
            lbl_expr = m_fl.group(2)
            lbl_match = re.search(r'"([^"]+)"', lbl_expr)
            label = lbl_match.group(1) if lbl_match else ""
            req_mark = "*" if field_name in required_vars else ""
            wtype = f"({field_types[field_name]})" if field_name in field_types else ""
            ro_mark = f"[{'·'.join(read_only_map[field_name])}]" if field_name in read_only_map else ""
            cell_name = f"{label}{req_mark}{{{field_name}}}{wtype}{ro_mark}"
            child_type = "field"
            child_var = field_name
        elif first_arg in container_types:
            cell_name = f"{{{first_arg}}}"
            child_type = "container"
            child_var = first_arg
        else:
            m_ident = re.search(r"^\s*(\w+)", first_arg)
            var = m_ident.group(1) if m_ident else first_arg
            req_mark = "*" if var in required_vars else ""
            wtype = f"({field_types[var]})" if var in field_types else ""
            ro_mark = f"[{'·'.join(read_only_map[var])}]" if var in read_only_map else ""
            cell_name = f"{{{var}}}{req_mark}{wtype}{ro_mark}"
            child_type = "widget"
            child_var = var

        container_adds[c_var].append({
            "name": cell_name,
            "type": child_type,
            "var": child_var,
            "w": w,
            "h": h,
            "m": m_str,
            "line": line_num,
        })

    # 4. 루트 컨테이너 찾기
    added_to_others = set()
    for c_var, adds in container_adds.items():
        for ch in adds:
            if ch["type"] == "container":
                added_to_others.add(ch["var"])

    roots = [c for c in container_types if c not in added_to_others]
    if not roots:
        roots = list(container_types.keys())[:1]

    # 루트 컨테이너가 속한 메서드 범위 탐색
    root_var = roots[0]
    root_line = 1
    for idx, line in enumerate(lines):
        if re.search(rf"\b{re.escape(root_var)}\s*=", line):
            root_line = idx + 1
            break

    class_methods = _find_class_methods(lines)
    method_name = "getEditor()"
    m_start = 1
    m_end = len(lines)
    for m_nm, m_st, m_ed in class_methods:
        if m_st <= root_line <= m_ed:
            method_name = m_nm
            m_start = m_st
            m_end = m_ed
            break

    # 5. 라벨 폭
    label_width_line = ""
    for idx, line in enumerate(lines):
        m_lw = re.search(r"\.setLabelWidth\s*\(\s*(\d+)\s*\)", line)
        if m_lw:
            label_width_line = f"- 라벨 폭: {m_lw.group(1)} (L{idx + 1})"
            break

    # 6. 읽기 전용 / 비활성
    read_only_map: dict[str, list[str]] = {}
    for idx, line in enumerate(lines):
        s = line.strip()
        m_ro = re.search(r"(?:this\.)?(\w+)\.setReadOnly\s*\(\s*true\s*\)", s)
        if m_ro:
            var = m_ro.group(1)
            if var not in read_only_map:
                read_only_map[var] = []
            if "readOnly" not in read_only_map[var]:
                read_only_map[var].append("readOnly")
        m_dis = re.search(r"(?:this\.)?(\w+)\.(?:disable\(\)|setEnabled\s*\(\s*false\s*\))", s)
        if m_dis:
            var = m_dis.group(1)
            if var not in read_only_map:
                read_only_map[var] = []
            if "disable" not in read_only_map[var]:
                read_only_map[var].append("disable")

    ro_str = ", ".join(f"{v}({', '.join(attrs)})" for v, attrs in read_only_map.items())

    # 7. 출력 조립
    out_lines = [f"#### 레이아웃 `{method_name}` L{m_start}-{m_end}"]
    if label_width_line:
        out_lines.append(label_width_line)

    for r in roots:
        r_type = container_types[r]
        r_adds = container_adds[r]
        parts = []
        nested_containers = []
        for ch in r_adds:
            sz = _format_size(ch["w"], ch["h"], ch["m"], is_cell=False)
            token = f"{ch['name']} {sz}".strip()
            parts.append(token)
            if ch["type"] == "container":
                nested_containers.append(ch["var"])

        out_lines.append(f"- {r} ({r_type}): {' | '.join(parts)}")

        for n_var in nested_containers:
            n_type = container_types[n_var]
            n_adds = container_adds[n_var]
            all_same = False
            first_sz = ""
            if n_adds:
                first_sz = _format_size(n_adds[0]["w"], n_adds[0]["h"], n_adds[0]["m"], is_cell=False)
                all_same = all(
                    _format_size(a["w"], a["h"], a["m"], is_cell=False) == first_sz
                    for a in n_adds
                )

            if all_same and first_sz:
                out_lines.append(f"- {n_var} ({n_type}) {len(n_adds)}줄, 각 {first_sz}:")
            else:
                out_lines.append(f"- {n_var} ({n_type}) {len(n_adds)}줄:")

            for row_ch in n_adds:
                row_var = row_ch["var"]
                row_line = row_ch["line"]
                cell_tokens = []
                if container_adds.get(row_var):
                    row_cells = container_adds[row_var]
                    row_first_line = row_cells[0]["line"]
                    for cell in row_cells:
                        csz = _format_size(cell["w"], cell["h"], is_cell=True)
                        token = f"{cell['name']} {csz}".strip() if csz else cell["name"]
                        cell_tokens.append(token)
                    out_lines.append(f"  - {row_var} (L{row_first_line}): {' · '.join(cell_tokens)}")
                else:
                    out_lines.append(f"  - {row_var} (L{row_line}): {row_ch['name']}")

    if ro_str:
        out_lines.append(f"- 읽기 전용·비활성: {ro_str}")

    extra_lines = _extract_toolbar_and_style_constants(lines)
    if extra_lines:
        out_lines.extend(extra_lines)

    return "\n".join(out_lines)


def _extract_toolbar_and_style_constants(lines: list[str]) -> list[str]:
    """툴바(buttonBar.add) 요소 배치 순서·폭 및 HTML/CSS 문자열 상수를 추출한다 (#5)."""
    out: list[str] = []

    # 위젯별 setWidth 수집
    widget_widths: dict[str, str] = {}
    for line in lines:
        m_w = re.search(r"(?:this\.)?(\w+)\.setWidth\s*\(\s*(\d+)\s*\)", line)
        if m_w:
            widget_widths[m_w.group(1)] = m_w.group(2)

    # buttonBar / searchBar / toolBar .add(...) 순서 수집
    tb_items: list[str] = []
    spacer_cnt = 0
    for line in lines:
        s = line.strip()
        m_tb = re.search(r"\b(buttonBar|searchBar|toolBar|topBar)\.add\s*\((.*)\)\s*;", s)
        if not m_tb:
            continue
        arg = m_tb.group(2).strip()
        if re.search(r'new\s+LabelToolItem\s*\(\s*""\s*\)', arg):
            spacer_cnt += 1
            continue
        if spacer_cnt > 0:
            tb_items.append(f"빈칸×{spacer_cnt}" if spacer_cnt > 1 else "빈칸")
            spacer_cnt = 0
        m_fl = re.search(r'new\s+FieldLabel\s*\(\s*(\w+)\s*,\s*"([^"]+)"\s*\)', arg)
        if m_fl:
            v, lbl = m_fl.group(1), m_fl.group(2)
            w_s = f", w={widget_widths[v]}" if v in widget_widths else ""
            tb_items.append(f"{lbl}{{{v}{w_s}}}")
        else:
            m_var = re.match(r"^(?:this\.)?(\w+)$", arg)
            if m_var:
                v = m_var.group(1)
                w_s = f"(w={widget_widths[v]})" if v in widget_widths else ""
                tb_items.append(f"{{{v}}}{w_s}")
            else:
                tb_items.append(arg[:40])
    if spacer_cnt > 0:
        tb_items.append(f"빈칸×{spacer_cnt}" if spacer_cnt > 1 else "빈칸")

    if tb_items:
        out.append(f"- 툴바 순서: {' → '.join(tb_items)}")

    # HTML / style 문자열 상수 추출
    for idx, line in enumerate(lines):
        m_sc = re.search(
            r'(?:private|protected|public)?\s*(?:static\s+)?(?:final\s+)?String\s+(\w+)\s*=\s*"([^"]*(?:style=|div|span|font)[^"]*)"',
            line,
            re.IGNORECASE,
        )
        if m_sc:
            out.append(f'- 스타일 상수 `{m_sc.group(1)}` (L{idx + 1}): `"{m_sc.group(2)[:80]}"`')

    return out
