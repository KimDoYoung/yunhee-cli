"""색인 화면 파일에서 필요한 부분만 추출하는 도구."""

import re
from typing import Any

from yunhee.tools.analysis.common import resolve_as_is_paths

NAME = "screen"
DESCRIPTION = "색인 화면 파일에서 필요한 클래스 및 절(section) 추출"
TARGET_HELP = "<화면클래스>"
FORMATS = ("md",)
EXAMPLES = [
    "yunhee analysis screen Emp00_Tab_TransInfo --list",
    "yunhee analysis screen Emp00_Tab_TransInfo --class Emp03_TabPage_Trans --section events",
    "yunhee analysis screen Emp00_Tab_TransInfo --section services --class Emp03_Edit_Person",
]


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """색인 화면 마크다운 파일을 찾아 구조화한다."""
    _, src_index = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    if not src_index or not src_index.is_dir():
        raise ValueError("색인 디렉터리를 찾을 수 없습니다. --src-index 옵션을 지정하세요.")

    target_name = target.strip().removesuffix(".md")

    matched_files = list(src_index.glob(f"**/screens/{target_name}.md"))
    if not matched_files:
        # 하위 클래스 이름으로도 검색
        matched_files = [f for f in src_index.glob("**/screens/*.md") if f.stem.lower() == target_name.lower()]
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
        btn_cnt = len(re.findall(r"-\s*<Button\b", c_text)) or len(re.findall(r"\d+\.\s+<Button\b", c_text))
        ev_cnt = len(re.findall(r"\[E\d+\]", c_text))
        grid_cnt = 1 if re.search(r"const buildGrid\b|그리드[^\n]*\(buildGrid", c_text) else 0
        class_stats.append({
            "name": c["name"],
            "lines": lines_cnt,
            "buttons": btn_cnt,
            "events": ev_cnt,
            "grids": grid_cnt,
            "text": c_text,
        })

    return {
        "file": screen_file,
        "screen": main_cls,
        "full_text": text,
        "class_stats": class_stats,
    }


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    if opts is None:
        opts = {}

    list_opt = opts.get("list", False) or opts.get("list_classes", False)
    screen_name = obj["screen"]
    stats = obj["class_stats"]
    full_text = obj["full_text"]

    # 1. --list / --list-classes
    if list_opt:
        lines = [f"### 화면 `{screen_name}` 클래스 목록 ({len(stats)}개)"]
        lines.append("\n| 클래스 | 줄 수 | 버튼 | 이벤트 | 그리드 |")
        lines.append("|:---|---:|---:|---:|---:|")
        tot_lines = sum(s["lines"] for s in stats)
        tot_btns = sum(s["buttons"] for s in stats)
        tot_evs = sum(s["events"] for s in stats)
        tot_grids = sum(s["grids"] for s in stats)
        for s in stats:
            lines.append(f"| {s['name']} | {s['lines']} | {s['buttons']} | {s['events']} | {s['grids']} |")
        lines.append(f"| **합계** | **{tot_lines}** | **{tot_btns}** | **{tot_evs}** | **{tot_grids}** |")
        return "\n".join(lines)

    # 2. 필터링 (--class, --section)
    cls_filter = opts.get("target_class") or opts.get("class")
    sec_filter = opts.get("section")

    target_texts = []
    if cls_filter:
        c_names = [c.strip().lower() for c in cls_filter.split(",")]
        matched_stats = [s for s in stats if s["name"].lower() in c_names]
        if matched_stats:
            target_texts = [s["text"] for s in matched_stats]
    if not target_texts:
        target_texts = [full_text]

    combined = "\n\n".join(target_texts)

    if not sec_filter:
        return combined

    sec_filter = sec_filter.lower()

    if sec_filter in ("services", "service"):
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

    return combined
