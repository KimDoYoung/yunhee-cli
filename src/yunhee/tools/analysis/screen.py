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

    screen_file = matched_files[0]
    text = screen_file.read_text(encoding="utf-8", errors="replace")

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
        comp_text = comp_file.read_text(encoding="utf-8", errors="replace")
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
        "class_stats": class_stats,
        "src_root": src_root,
    }


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    if opts is None:
        opts = {}

    list_opt = opts.get("list", False) or opts.get("list_classes", False)
    screen_name = obj["screen"]
    stats = obj["class_stats"]
    full_text = obj["full_text"]
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
            target_texts = [s["text"] for s in matched_stats]
    if not target_texts:
        target_texts = [full_text]

    combined = "\n\n".join(target_texts)

    if not sec_filter:
        return combined

    sec_filter = sec_filter.lower()

    if sec_filter in ("services", "service"):
        m_srv = re.search(r"##\s*(?:호출\s*)?서비스\b.*?(?=\n##\s|\Z)", combined, re.DOTALL)
        if not m_srv:
            m_srv = re.search(r"##\s*(?:호출\s*)?서비스\b.*?(?=\n##\s|\Z)", full_text, re.DOTALL)
        if not m_srv:
            return "서비스 섹션을 찾을 수 없습니다."
        srv_text = m_srv.group(0).strip()
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

    if sec_filter in ("layout", "layouts"):
        from pathlib import Path

        from yunhee.tools.analysis.layout import parse_layout
        from yunhee.tools.as_is.src_indexer import find_app

        target_cls = (cls_filter or screen_name).strip()
        src_root = obj.get("src_root") or Path.cwd()
        app = find_app(src_root) or src_root

        # Java 파일 찾기: 색인 md 본문에서 상대 경로 탐색
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
            return f"클래스 소스 파일을 찾을 수 없습니다: {target_cls}.java"

        java_text = java_file.read_text(encoding="utf-8", errors="replace")
        return parse_layout(java_text)

    return combined
