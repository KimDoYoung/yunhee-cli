"""UI 대조표 및 단계별 합계 분석 도구."""

import re
from pathlib import Path
from typing import Any

from yunhee.tools.analysis.common import resolve_as_is_paths

NAME = "ui"
DESCRIPTION = "UI 대조표 및 단계별 버튼/이벤트/그리드 현황 분석"
TARGET_HELP = "<화면클래스>"
FORMATS = ("md",)
EXAMPLES = [
    'yunhee analysis ui Emp00_Tab_TransInfo --done Emp00_Tab_TransInfo,Emp03_Edit_Person --later "2단계=Emp02_Lookup_HireDate,Emp03_Lookup_Grade"',
    "yunhee analysis ui Sys05_Tab_UserRole --tobe AssetERP_1/frontend/src/pages/sys",
]


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """화면 파일 및 TOBE 디렉터리에서 UI 통계를 추출한다."""
    _, src_index = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    if not src_index or not src_index.is_dir():
        raise ValueError("색인 디렉터리를 찾을 수 없습니다. --src-index 옵션을 지정하세요.")

    target_name = target.strip().removesuffix(".md")
    matched_files = list(src_index.glob(f"**/screens/{target_name}.md"))
    if not matched_files:
        matched_files = [f for f in src_index.glob("**/screens/*.md") if f.stem.lower() == target_name.lower()]
    if not matched_files:
        raise ValueError(f"색인 화면 파일을 찾을 수 없습니다: {target_name}.md")

    screen_file = matched_files[0]
    text = screen_file.read_text(encoding="utf-8", errors="replace")

    # 클래스별 섹션 분리
    cls_matches = list(re.finditer(r"^###\s+([A-Z]\w+)(?:\.java)?\b", text, re.MULTILINE))
    classes: list[dict[str, Any]] = []

    if cls_matches:
        main_header = text[: cls_matches[0].start()]
        if "#### 버튼" in main_header or "#### 이벤트" in main_header or "## Grid Spec" in main_header:
            classes.append({"name": screen_file.stem, "text": main_header})

        for i, m in enumerate(cls_matches):
            c_name = m.group(1)
            start_p = m.start()
            end_p = cls_matches[i + 1].start() if i + 1 < len(cls_matches) else len(text)
            classes.append({"name": c_name, "text": text[start_p:end_p]})
    else:
        classes.append({"name": screen_file.stem, "text": text})

    # 클래스별 AS-IS 통계
    as_is_stats: dict[str, dict[str, int]] = {}
    for c in classes:
        c_text = c["text"]
        btn_cnt = len(re.findall(r"-\s*<Button\b|\d+\.\s+<Button\b", c_text))
        ev_cnt = len(re.findall(r"\[E\d+\]", c_text))
        grid_cnt = 1 if re.search(r"const buildGrid\b|그리드[^\n]*\(buildGrid", c_text) else 0
        as_is_stats[c["name"]] = {
            "buttons": btn_cnt,
            "events": ev_cnt,
            "grids": grid_cnt,
        }

    # TOBE 통계 파싱 (지정된 경우)
    tobe_path_raw = opts.get("tobe")
    tobe_stats: dict[str, dict[str, int]] = {}
    if tobe_path_raw:
        tobe_dir = Path(tobe_path_raw)
        if tobe_dir.is_dir():
            for f in tobe_dir.rglob("*.tsx"):
                try:
                    f_text = f.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                f_name = f.stem
                t_btn = len(re.findall(r"<Button\b", f_text))
                t_ev = len(re.findall(r"\[E\d+\]", f_text))
                t_grid = 1 if re.search(r"<(?:SingleGrid|MultiGrid|CellEditGrid|ModalEditGrid)\b", f_text) else 0
                tobe_stats[f_name] = {"buttons": t_btn, "events": t_ev, "grids": t_grid}
        elif tobe_dir.is_file():
            try:
                f_text = tobe_dir.read_text(encoding="utf-8", errors="replace")
                t_btn = len(re.findall(r"<Button\b", f_text))
                t_ev = len(re.findall(r"\[E\d+\]", f_text))
                t_grid = 1 if re.search(r"<(?:SingleGrid|MultiGrid|CellEditGrid|ModalEditGrid)\b", f_text) else 0
                tobe_stats[tobe_dir.stem] = {"buttons": t_btn, "events": t_ev, "grids": t_grid}
            except OSError:
                pass

    return {
        "screen": screen_file.stem,
        "as_is": as_is_stats,
        "tobe": tobe_stats,
        "done": opts.get("done", ""),
        "later": opts.get("later", ""),
    }


def render(obj: dict[str, Any], fmt: str = "md", opts: dict[str, Any] | None = None) -> str:
    """결과를 포맷에 맞게 렌더링한다."""
    screen_name = obj["screen"]
    as_is = obj["as_is"]
    tobe = obj["tobe"]

    done_raw = obj["done"] or ""
    later_raw = obj["later"] or ""

    done_set = {c.strip() for c in done_raw.split(",") if c.strip()}

    later_label = "2단계"
    later_set = set()
    if later_raw:
        if "=" in later_raw:
            later_label, items = later_raw.split("=", 1)
            later_set = {c.strip() for c in items.split(",") if c.strip()}
        else:
            later_set = {c.strip() for c in later_raw.split(",") if c.strip()}

    all_cls_names = list(as_is.keys())

    # 그룹 분류
    group_done = [c for c in all_cls_names if c in done_set]
    group_later = [c for c in all_cls_names if c in later_set and c not in done_set]
    group_remain = [c for c in all_cls_names if c not in done_set and c not in later_set]

    has_tobe = bool(tobe)

    lines = [f"### `{screen_name}` UI 대조표"]

    if has_tobe:
        lines.append("\n| 클래스 | 버튼 (AS-IS/TOBE) | 이벤트 (AS-IS/TOBE) | 그리드 (AS-IS/TOBE) |")
        lines.append("|:---|:---:|:---:|:---:|")
        for c in all_cls_names:
            ai = as_is[c]
            tb = tobe.get(c, {"buttons": 0, "events": 0, "grids": 0})
            lines.append(
                f"| {c} | {ai['buttons']}/{tb['buttons']} | {ai['events']}/{tb['events']} | {ai['grids']}/{tb['grids']} |"
            )
        return "\n".join(lines)

    # 단계별 합계 표
    lines.append("\n| 그룹 | 클래스 수 | 버튼 | 이벤트 | 그리드 |")
    lines.append("|:---|---:|---:|---:|---:|")

    def calc_sum(names: list[str]) -> tuple[int, int, int]:
        b = sum(as_is[n]["buttons"] for n in names)
        e = sum(as_is[n]["events"] for n in names)
        g = sum(as_is[n]["grids"] for n in names)
        return b, e, g

    if group_done:
        b, e, g = calc_sum(group_done)
        lines.append(f"| 이번 단계 (done) | {len(group_done)} | {b} | {e} | {g} |")

    if group_later:
        b, e, g = calc_sum(group_later)
        lines.append(f"| {later_label} | {len(group_later)} | {b} | {e} | {g} |")

    if group_remain:
        b, e, g = calc_sum(group_remain)
        lines.append(f"| 미착수 (remain) | {len(group_remain)} | {b} | {e} | {g} |")

    tot_b, tot_e, tot_g = calc_sum(all_cls_names)
    lines.append(f"| **전체 합계** | **{len(all_cls_names)}** | **{tot_b}** | **{tot_e}** | **{tot_g}** |")

    return "\n".join(lines)
