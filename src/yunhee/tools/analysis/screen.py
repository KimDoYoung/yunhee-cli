"""색인 화면 파일에서 필요한 부분만 추출하는 도구."""

import re
from typing import Any

from yunhee.tools.analysis.common import count_as_is_grids, resolve_as_is_paths

NAME = "screen"
DESCRIPTION = "색인 화면 파일에서 필요한 클래스 및 절(section) 추출 (연결 컴포넌트 포함)"
TARGET_HELP = "<화면클래스>"
FORMATS = ("md",)
EXAMPLES = [
    "yunhee analysis screen Emp00_Tab_TransInfo --list",
    "yunhee analysis screen Emp00_Tab_TransInfo --class Emp03_TabPage_Trans --section events",
    "yunhee analysis screen Emp00_Tab_TransInfo --section services --class Emp03_Edit_Person",
]


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """색인 화면 마크다운 파일을 찾아 구조화한다."""
    src_root, src_index = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    if not src_index or not src_index.is_dir():
        raise ValueError("색인 디렉터리를 찾을 수 없습니다. --src-index 옵션을 지정하세요.")

    target_name = target.strip().removesuffix(".md")

    matched_files = list(src_index.glob(f"**/screens/{target_name}.md"))
    if not matched_files:
        # 하위 클래스 이름으로도 검색
        matched_files = [f for f in src_index.glob("**/screens/*.md") if f.stem.lower() == target_name.lower()]
    if not matched_files:
        # components/ 디렉터리에서도 검색
        matched_files = list(src_index.glob(f"**/components/{target_name}.md"))
    if not matched_files:
        matched_files = [f for f in src_index.glob("**/components/*.md") if f.stem.lower() == target_name.lower()]
    if not matched_files:
        raise ValueError(f"색인 화면 파일을 찾을 수 없습니다: {target_name}.md")

    from yunhee.tools.as_is.drift import parse_frontmatter

    screen_file = matched_files[0]
    raw_text = screen_file.read_text(encoding="utf-8", errors="replace")
    frontmatter, text = parse_frontmatter(raw_text)

    # 1. 파일 내 클래스별 섹션 분리
    classes: list[dict[str, Any]] = []
    main_cls = screen_file.stem
    classes.append({"name": main_cls, "text": text})

    # 하위 클래스들 탐색 (### X.java 또는 ### X)
    cls_matches = list(re.finditer(r"^###\s+([A-Z]\w+)(?:\.java)?\b", text, re.MULTILINE))
    if cls_matches:
        classes = []
        for i, m in enumerate(cls_matches):
            c_name = m.group(1)
            start_p = m.start()
            end_p = cls_matches[i + 1].start() if i + 1 < len(cls_matches) else len(text)
            c_text = text[start_p:end_p]
            classes.append({"name": c_name, "text": c_text})

    # 통계 집계 (클래스별 줄수, 버튼수, 이벤트수, 그리드수)
    class_stats = []
    for c in classes:
        c_text = c["text"]
        lines_cnt = c_text.count("\n") + 1
        btn_cnt = len(re.findall(r"-\s*<Button\b|\d+\.\s+<Button\b", c_text))
        ev_cnt = len(re.findall(r"\[E\d+\]", c_text))
        grid_cnt, grid_warn = count_as_is_grids(c_text)
        class_stats.append({
            "name": c["name"],
            "raw_name": c["name"],
            "lines": lines_cnt,
            "buttons": btn_cnt,
            "events": ev_cnt,
            "grids": grid_cnt,
            "grid_warn": grid_warn,
            "text": c_text,
            "is_linked": False,
            "same_domain": True,
            "file": screen_file,
        })

    # 2. 연결 컴포넌트 탐색
    linked_candidates: list[tuple[str, str | None]] = []
    # (1) "- 연결 화면·컴포넌트 (각 파일 참고):" 줄에서 추출
    m_link_line = re.search(r"^-\s*연결\s*화면[·\s]*컴포넌트[^\n]*", text, re.MULTILINE)
    if m_link_line:
        line_str = m_link_line.group(0)
        for m in re.finditer(r"\[`?([A-Za-z0-9_]+)`?\]\(([^)]+)\)", line_str):
            linked_candidates.append((m.group(1), m.group(2)))

    # (2) 메서드 표/본문의 "조회창 X 열기" 추출
    for m in re.finditer(r"조회창\s+([A-Za-z0-9_]+)\s+열기", text):
        c_name = m.group(1)
        if not any(cand[0] == c_name for cand in linked_candidates):
            linked_candidates.append((c_name, None))

    # 도메인 식별 (화면 파일)
    try:
        screen_rel = screen_file.relative_to(src_index)
        screen_domain = screen_rel.parts[0]
    except (ValueError, IndexError):
        screen_domain = screen_file.parent.parent.name

    existing_names = {c["name"].lower() for c in classes}

    for comp_name, comp_rel in linked_candidates:
        if comp_name.lower() in existing_names:
            continue

        comp_file = None
        if comp_rel:
            cand = (screen_file.parent / comp_rel).resolve()
            if cand.is_file():
                comp_file = cand
        if not comp_file or not comp_file.is_file():
            cands = list(src_index.glob(f"**/components/{comp_name}.md"))
            if not cands:
                cands = [f for f in src_index.glob("**/components/*.md") if f.stem.lower() == comp_name.lower()]
            if cands:
                comp_file = cands[0]

        if not comp_file or not comp_file.is_file():
            continue

        try:
            comp_rel_path = comp_file.relative_to(src_index)
            comp_domain = comp_rel_path.parts[0]
        except (ValueError, IndexError):
            comp_domain = comp_file.parent.parent.name

        is_same_domain = (comp_domain == screen_domain)
        _, comp_text = parse_frontmatter(comp_file.read_text(encoding="utf-8", errors="replace"))
        lines_cnt = comp_text.count("\n") + 1
        btn_cnt = len(re.findall(r"-\s*<Button\b|\d+\.\s+<Button\b", comp_text))
        ev_cnt = len(re.findall(r"\[E\d+\]", comp_text))
        grid_cnt, grid_warn = count_as_is_grids(comp_text)

        disp_name = f"{comp_name} (연결)" if is_same_domain else f"{comp_name} (연결·다른 도메인)"
        class_stats.append({
            "name": disp_name,
            "raw_name": comp_name,
            "lines": lines_cnt,
            "buttons": btn_cnt,
            "events": ev_cnt,
            "grids": grid_cnt,
            "grid_warn": grid_warn,
            "text": comp_text,
            "is_linked": True,
            "same_domain": is_same_domain,
            "file": comp_file,
        })
        existing_names.add(comp_name.lower())

    return {
        "file": screen_file,
        "screen": main_cls,
        "full_text": text,
        "frontmatter": frontmatter,
        "class_stats": class_stats,
        "src_root": src_root,
    }


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    from yunhee.tools.as_is.drift import format_screen_source_section, parse_frontmatter

    if opts is None:
        opts = {}

    list_opt = opts.get("list", False) or opts.get("list_classes", False)
    screen_name = obj["screen"]
    stats = obj["class_stats"]
    _, full_text = parse_frontmatter(obj["full_text"])
    no_linked = opts.get("no_linked", False)

    # 1. --list / --list-classes
    if list_opt:
        display_stats = [s for s in stats if not (no_linked and s.get("is_linked"))]
        lines = [f"### 화면 `{screen_name}` 클래스 목록 ({len(display_stats)}개)"]
        lines.append("\n| 클래스 | 줄 수 | 버튼 | 이벤트 | 그리드 |")
        lines.append("|:---|---:|---:|---:|---:|")

        def include_in_total(s: dict[str, Any]) -> bool:
            if not s.get("is_linked"):
                return True
            return s.get("same_domain", False) and not no_linked

        tot_lines = sum(s["lines"] for s in display_stats if include_in_total(s))
        tot_btns = sum(s["buttons"] for s in display_stats if include_in_total(s))
        tot_evs = sum(s["events"] for s in display_stats if include_in_total(s))
        tot_grids = sum(s["grids"] for s in display_stats if include_in_total(s))
        for s in display_stats:
            g_disp = f"{s['grids']}⚠" if s.get("grid_warn") else f"{s['grids']}"
            lines.append(f"| {s['name']} | {s['lines']} | {s['buttons']} | {s['events']} | {g_disp} |")
        lines.append(f"| **합계** | **{tot_lines}** | **{tot_btns}** | **{tot_evs}** | **{tot_grids}** |")
        return "\n".join(lines)

    # 2. 필터링 (--class, --section)
    cls_filter = opts.get("target_class") or opts.get("class")
    sec_filter = opts.get("section")

    target_texts = []
    if cls_filter:
        c_names = [c.strip().lower() for c in cls_filter.split(",")]
        matched_stats = [
            s for s in stats
            if s["name"].lower() in c_names or s.get("raw_name", "").lower() in c_names
        ]
        if matched_stats:
            target_texts = [parse_frontmatter(s["text"])[1] for s in matched_stats]
    if not target_texts:
        target_texts = [full_text]

    combined = "\n\n".join(target_texts)
    target_cls = (cls_filter or screen_name).strip()

    if sec_filter:
        sec_filter = sec_filter.lower()

        if sec_filter in ("source", "sources"):
            fm = obj.get("frontmatter")
            if fm is None and "file" in obj and obj["file"]:
                try:
                    fm, _ = parse_frontmatter(obj["file"].read_text(encoding="utf-8", errors="replace"))
                except Exception:  # noqa: BLE001
                    fm = None
            return format_screen_source_section(screen_name, fm)

        if sec_filter in ("fields", "field"):
            _, java_text = _find_java_source(target_cls, obj, combined, full_text)
            if not java_text:
                return f"클래스 소스 파일을 찾을 수 없습니다: {target_cls}.java"
            return parse_fields(java_text)

        if sec_filter in ("layout", "layouts"):
            from yunhee.tools.analysis.layout import parse_layout

            _, java_text = _find_java_source(target_cls, obj, combined, full_text)
            if not java_text:
                return f"클래스 소스 파일을 찾을 수 없습니다: {target_cls}.java"
            return parse_layout(java_text)

        if sec_filter in ("services", "service"):
            m_srv = re.search(r"##\s*(?:호출\s*)?서비스\b.*?(?=\n##\s|\Z)", combined, re.DOTALL)
            if not m_srv:
                m_srv = re.search(r"##\s*(?:호출\s*)?서비스\b.*?(?=\n##\s|\Z)", full_text, re.DOTALL)
            if not m_srv:
                return "서비스 섹션을 찾을 수 없습니다."
            srv_text = m_srv.group(0).strip()
            _, java_text = _find_java_source(target_cls, obj, combined, full_text)
            if java_text:
                srv_text = _inject_dynamic_services(srv_text, java_text, target_cls)
            srv_text = _format_service_rows(srv_text)
            if cls_filter:
                c_names = [c.strip().lower() for c in cls_filter.split(",")]
                lines = srv_text.splitlines()
                out_lines = []
                header_done = False
                for l in lines:
                    if l.startswith("|") and ":---" in l:
                        out_lines.append(l)
                        header_done = True
                        continue
                    if not header_done:
                        out_lines.append(l)
                        continue
                    if l.startswith("|") and any(cn in l.lower() for cn in c_names):
                        out_lines.append(l)
                return "\n".join(out_lines)
            return srv_text

        if sec_filter in ("tables", "table"):
            m_tbl = re.search(r"##\s*(?:관련\s*)?테이블\b.*?(?=\n##\s|\Z)", combined, re.DOTALL)
            if not m_tbl:
                m_tbl = re.search(r"##\s*(?:관련\s*)?테이블\b.*?(?=\n##\s|\Z)", full_text, re.DOTALL)
            return m_tbl.group(0).strip() if m_tbl else "테이블 섹션을 찾을 수 없습니다."

        if sec_filter in ("events", "event"):
            m_ev = re.search(r"##\s*이벤트.*?(?=\n##\s*|\Z)|####\s*이벤트.*?(?=####\s*|###\s*|\Z)", combined, re.DOTALL)
            return m_ev.group(0).strip() if m_ev else "이벤트 섹션을 찾을 수 없습니다."

        if sec_filter in ("grid", "grids"):
            m_gd = re.search(r"##\s*Grid Spec.*?(?=\n##\s*|\Z)|####\s*그리드.*?(?=####\s*|###\s*|\Z)", combined, re.DOTALL)
            return m_gd.group(0).strip() if m_gd else "Grid Spec 섹션을 찾을 수 없습니다."

        if sec_filter in ("buttons", "button"):
            m_btn = re.search(r"##\s*사용된 버튼.*?(?=\n##\s*|\Z)|####\s*버튼.*?(?=####\s*|###\s*|\Z)", combined, re.DOTALL)
            return m_btn.group(0).strip() if m_btn else "버튼 섹션을 찾을 수 없습니다."

    # 기본 (전체/클래스 본문)
    _, java_text = _find_java_source(target_cls, obj, combined, full_text)
    if java_text:
        m_srv = re.search(r"(##\s*(?:호출\s*)?서비스\b.*?(?=\n##\s|\Z))", combined, re.DOTALL)
        if m_srv:
            new_srv = _inject_dynamic_services(m_srv.group(1).strip(), java_text, target_cls)
            combined = combined[:m_srv.start(1)] + new_srv + combined[m_srv.end(1):]

    combined = _format_service_rows(combined)

    # 미정의 SQL 경고 헤더 추가
    undef_calls = _extract_undefined_sqls(combined)
    if not undef_calls and full_text != combined:
        undef_calls = _extract_undefined_sqls(full_text)
    if undef_calls:
        warn_header = f"⚠ 미정의 SQL 호출 {len(undef_calls)}개: {', '.join(undef_calls)}\n\n"
        combined = warn_header + combined

    return combined


WIDGET_TYPES = {
    "TextField", "MyTextField", "DateField", "MyDateField", "MyTextArea",
    "TextArea", "ComboBox", "ComboBoxField", "CommonComboBoxField", "CheckBox",
    "FormPanel", "Grid", "GridBuilder", "ButtonBar", "ColorButtonBar",
    "ColorButtonBottom", "TextButton", "Button", "OmsButton", "HeaderButtonBar",
    "FieldLabel", "HtmlMessageBox", "SimpleMessage", "SafeHtml", "EditDriver",
    "SimpleBeanEditorDriver", "ContentPanel", "VerticalLayoutContainer",
    "HorizontalLayoutContainer", "BorderLayoutContainer", "BoxLayoutContainer",
    "Label", "Text", "Image", "Widget", "Component", "ResourceIcon",
    "LayoutContainer", "TreeGrid", "Tree",
}


def parse_fields(java_text: str) -> str:
    """Java 소스에서 위젯이 아닌 상태 필드와 초기값, 읽기/쓰기 줄 번호를 추출한다."""
    lines = java_text.splitlines()
    clean_lines = []
    in_block_comment = False
    for l in lines:
        if in_block_comment:
            if "*/" in l:
                in_block_comment = False
                clean_lines.append("")
            else:
                clean_lines.append("")
            continue
        if "/*" in l:
            if "*/" in l:
                clean_lines.append(re.sub(r"/\*.*?\*/", "", l))
            else:
                in_block_comment = True
                clean_lines.append(l[:l.find("/*")])
            continue
        if "//" in l:
            clean_lines.append(l[:l.find("//")])
        else:
            clean_lines.append(l)

    method_ranges = []
    m_re = re.compile(
        r"(?:public|protected|private|static|final)\s+(?:[\w<>\[\], ?]+\s+)?([A-Za-z0-9_]+)\s*\([^)]*\)\s*(?:throws\s+[\w.,\s]+)?\s*\{"
    )
    for idx, l in enumerate(clean_lines):
        m = m_re.search(l)
        if m:
            open_line = idx
            depth = 1
            close_line = idx
            for j in range(idx + 1, len(clean_lines)):
                depth += clean_lines[j].count("{") - clean_lines[j].count("}")
                if depth <= 0:
                    close_line = j
                    break
            method_ranges.append((m.group(1), open_line, close_line))

    in_method_lines = set()
    for _, s_l, e_l in method_ranges:
        for line_idx in range(s_l, e_l + 1):
            in_method_lines.add(line_idx)

    field_re = re.compile(
        r"^\s*(?:(?:private|protected|public|static|final)\s+)*"
        r"([A-Z]\w*(?:<[^>]+>)?|[a-z]+)\s+([a-zA-Z_]\w*)\s*(?:=\s*([^;]+))?;"
    )

    fields_found = []
    for idx, l in enumerate(clean_lines):
        if idx in in_method_lines:
            continue
        m = field_re.search(l)
        if not m:
            continue
        f_type = m.group(1).strip()
        f_name = m.group(2).strip()
        init_val = m.group(3).strip() if m.group(3) else "null"
        raw_type = f_type.split("<")[0]
        if (
            raw_type in WIDGET_TYPES
            or raw_type.endswith(("Field", "Button", "Driver", "Panel", "Container", "ComboBox", "Box", "Grid", "Bar"))
        ):
            continue
        fields_found.append((f_name, f_type, init_val, idx + 1))

    if not fields_found:
        return "상태 필드를 찾을 수 없습니다."

    out_lines = []
    for f_name, f_type, init_val, decl_line in fields_found:
        writes = []
        reads = []
        for m_name, s_l, e_l in method_ranges:
            m_body_lines = clean_lines[s_l:e_l + 1]
            for offset, m_l in enumerate(m_body_lines):
                line_no = s_l + offset + 1
                # Skip the method signature line (where parameters of the same name may appear)
                if offset == 0:
                    continue
                if re.search(r'(?:this\.)?\b' + re.escape(f_name) + r'\s*=(?!=)', m_l):
                    writes.append(f"{m_name} L{line_no} 설정")
                elif re.search(r'\b' + re.escape(f_name) + r'\b', m_l):
                    reads.append(f"{m_name} L{line_no} 읽음")

        usage_parts = []
        if writes:
            usage_parts.append(", ".join(writes[:2]))
        if reads:
            usage_parts.append(", ".join(reads[:2]))

        usage_str = f" ← {', '.join(usage_parts)}" if usage_parts else ""
        out_lines.append(f"{f_name} {f_type} = {init_val} (L{decl_line}){usage_str}")

    return "\n".join(out_lines)


def _find_java_source(target_cls: str, obj: dict[str, Any], combined: str, full_text: str) -> tuple[Any, str]:
    from pathlib import Path

    from yunhee.tools.as_is.src_indexer import find_app

    src_root = obj.get("src_root") or Path.cwd()
    app = find_app(src_root) or src_root

    rel_path = ""
    m_cls_sec = re.search(rf"^###\s+{re.escape(target_cls)}\b[^(]*\(`([^`]+)`", combined, re.MULTILINE)
    if not m_cls_sec:
        m_cls_sec = re.search(rf"^###\s+{re.escape(target_cls)}\b[^(]*\(`([^`]+)`", full_text, re.MULTILINE)
    if m_cls_sec:
        rel_path = m_cls_sec.group(1)
    else:
        m_list = re.search(rf"-\s+`?{re.escape(target_cls)}`?\s+`?([a-zA-Z0-9_/.]+\.java)`?", combined)
        if not m_list:
            m_list = re.search(rf"-\s+`?{re.escape(target_cls)}`?\s+`?([a-zA-Z0-9_/.]+\.java)`?", full_text)
        if m_list:
            rel_path = m_list.group(1)
        else:
            m_file = re.search(r"-\s*파일:\s*`([^`]+)`", combined)
            if not m_file:
                m_file = re.search(r"-\s*파일:\s*`([^`]+)`", full_text)
            if m_file:
                rel_path = m_file.group(1)

    java_file = None
    if rel_path:
        for cand in [app / rel_path, src_root / rel_path]:
            if cand.is_file():
                java_file = cand
                break

    if not java_file or not java_file.is_file():
        for cand in src_root.rglob(f"{target_cls}.java"):
            if "target" not in cand.parts:
                java_file = cand
                break

    if not java_file or not java_file.is_file():
        return None, ""

    java_text = java_file.read_text(encoding="utf-8", errors="replace")
    return java_file, java_text


def _inject_dynamic_services(srv_text: str, java_text: str, screen_cls: str) -> str:
    m_call = re.search(r'\b\w+\.retrieve\s*\(\s*["\']([^"\']+)["\']\s*\+\s*(\w+)', java_text)
    if not m_call:
        return srv_text
    prefix = m_call.group(1)
    var_name = m_call.group(2)
    call_line = java_text.count("\n", 0, m_call.start()) + 1

    lines = java_text.splitlines()
    assign_vals: list[tuple[str, str]] = []
    curr_cond = ""
    start_look = max(0, call_line - 30)
    for l in lines[start_look:call_line]:
        m_if = re.search(r'\bif\s*\(', l)
        if m_if:
            from yunhee.tools.as_is.src_indexer import paren_end

            p_open = l.find("(", m_if.start())
            p_close = paren_end(l, p_open)
            cond_expr = l[p_open + 1:p_close].strip() if p_close > p_open else l[p_open + 1:].rstrip("{").strip()
            curr_cond = f"if ({cond_expr})"
        elif re.search(r'\belse\b', l):
            curr_cond = "else"
        m_asgn = re.search(r'\b' + re.escape(var_name) + r'\s*=\s*["\'](\w+)["\']', l)
        if m_asgn:
            assign_vals.append((m_asgn.group(1), curr_cond))

    if not assign_vals:
        return srv_text

    parts = prefix.rstrip(".").split(".")
    domain = parts[0] if parts else "sys"
    srv_class = parts[1] if len(parts) > 1 else screen_cls

    def to_snake(s: str) -> str:
        s = re.sub(r'(?<!^)(?<!_)(?=[A-Z])', '_', s).lower()
        return re.sub(r'_+', '_', s)

    mapper_name = to_snake(srv_class)
    table_lines = srv_text.splitlines()
    new_rows = []
    seen_sqls = set()
    for val, cond in sorted(assign_vals, key=lambda x: x[0]):
        if val in seen_sqls:
            continue
        seen_sqls.add(val)
        full_s = f"{prefix.rstrip('.')}.{val}"
        sql_id = f"{mapper_name}.{val}"
        if sql_id in srv_text or f"`{full_s}`" in srv_text:
            continue
        cond_info = f" ({cond})" if cond else ""
        row = f"| `{full_s}` (동적 이름) | {screen_cls}:{call_line}{cond_info} | [`{srv_class}.java`](../../{domain}/services/{srv_class}.md) | [`{sql_id}`](../../{domain}/sql/{mapper_name}.md) |"
        new_rows.append(row)

    if new_rows:
        table_lines.extend(new_rows)
        return "\n".join(table_lines)
    return srv_text


def _format_service_rows(text: str) -> str:
    lines = []
    for l in text.splitlines():
        if "(없음)" in l and "⚠ 매퍼에 SQL 없음" not in l:
            l = re.sub(r'(\([a-zA-Z0-9_.]*없음\))', r'\1 ⚠ 매퍼에 SQL 없음 — 원본에서도 실패', l)
        lines.append(l)
    return "\n".join(lines)


def _extract_undefined_sqls(text: str) -> list[str]:
    undef_calls = []
    for line in text.splitlines():
        if "(없음)" in line and line.strip().startswith("|"):
            m_row = re.match(r"^\|\s*`?([^`|]+)`?\s*\|\s*([^|]+?)\s*\|", line.strip())
            if m_row:
                svc_part = m_row.group(1).strip()
                call_name = svc_part.split(".")[-1]
                loc = m_row.group(2).strip()
                first_loc = loc.split(",")[0].strip()
                undef_calls.append(f"{call_name} ({first_loc})")
    return undef_calls
