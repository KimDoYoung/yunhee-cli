"""UI 대조표 및 단계별 합계 분석 도구."""

import re
from pathlib import Path
from typing import Any

from yunhee.tools.analysis.common import (
    count_as_is_grids,
    count_tobe_buttons,
    count_tobe_grids,
    resolve_as_is_paths,
)

NAME = "ui"
DESCRIPTION = "UI 대조표 및 단계별 버튼/이벤트/그리드 현황 분석 (연결 컴포넌트 포함)"
TARGET_HELP = "<화면클래스>"
FORMATS = ("md", "json")
EXAMPLES = [
    'yunhee analysis ui Emp00_Tab_TransInfo --done Emp00_Tab_TransInfo,Emp03_Edit_Person --later "2단계=Emp02_Lookup_HireDate,Emp03_Lookup_Grade"',
    "yunhee analysis ui Sys05_Tab_UserRole --tobe AssetERP_1/frontend/src/pages/sys",
]


def _tobe_event_ids(text: str) -> tuple[set[int], set[int]]:
    """TOBE 파일 텍스트에서 구현된 이벤트 집합과 생략된 이벤트 집합을 추출한다.

    - 단일: [E0] -> {0} in impl
    - 범위: [E5]~[E9] -> {5,6,7,8,9} in impl
    - 생략 단일: [E1 생략] -> {1} in skipped
    - 생략 범위: [E1]~[E3 생략] -> {1,2,3} in skipped
    - 구현과 생략에 동시 포함되면 구현으로 취급 (skipped = skipped - impl)
    """
    impl: set[int] = set()
    skipped: set[int] = set()

    # 1. 생략 범위: [E1]~[E3 생략]
    def repl_skip_range(m: re.Match) -> str:
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b:
            for n in range(a, b + 1):
                skipped.add(n)
        return " " * len(m.group(0))

    t = re.sub(r"\[E(\d+)\]\s*[~∼-]\s*\[E(\d+)\s*생략\]", repl_skip_range, text)

    # 2. 일반 범위: [E5]~[E9]
    def repl_impl_range(m: re.Match) -> str:
        a, b = int(m.group(1)), int(m.group(2))
        if a <= b:
            for n in range(a, b + 1):
                impl.add(n)
        return " " * len(m.group(0))

    t = re.sub(r"\[E(\d+)\]\s*[~∼-]\s*\[E(\d+)\]", repl_impl_range, t)

    # 3. 생략 단일: [E1 생략]
    def repl_skip_single(m: re.Match) -> str:
        skipped.add(int(m.group(1)))
        return " " * len(m.group(0))

    t = re.sub(r"\[E(\d+)\s*생략\]", repl_skip_single, t)

    # 4. 구현 단일: [E0]
    for m in re.finditer(r"\[E(\d+)\]", t):
        impl.add(int(m.group(1)))

    skipped = skipped - impl
    return impl, skipped


def resolve(target: str, opts: dict[str, Any]) -> dict[str, Any]:
    """화면 파일 및 TOBE 디렉터리에서 UI 통계를 추출한다."""
    src_root, src_index = resolve_as_is_paths(src=opts.get("src"), src_index=opts.get("src_index"))
    if not src_index or not src_index.is_dir():
        raise ValueError("색인 디렉터리를 찾을 수 없습니다. --src-index 옵션을 지정하세요.")

    target_name = target.strip().removesuffix(".md")
    matched_files = list(src_index.glob(f"**/screens/{target_name}.md"))
    if not matched_files:
        matched_files = [f for f in src_index.glob("**/screens/*.md") if f.stem.lower() == target_name.lower()]
    if not matched_files:
        matched_files = list(src_index.glob(f"**/components/{target_name}.md"))
    if not matched_files:
        matched_files = [f for f in src_index.glob("**/components/*.md") if f.stem.lower() == target_name.lower()]
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

    unreachable_opt = str(opts.get("unreachable") or "count").lower()
    as_is_stats: dict[str, dict[str, Any]] = {}
    for c in classes:
        c_text = c["text"]
        btn_cnt = len(re.findall(r"-\s*<Button\b|\d+\.\s+<Button\b", c_text))
        ev_matches = re.findall(r"\[E(\d+)\]", c_text)
        unreach_matches = re.findall(r"\[E(\d+)\].*?(?:도달\s*불가|⚠\s*도달\s*불가)", c_text)

        if not ev_matches and src_root:
            c_files = list(src_root.rglob(f"{c['name']}.java"))
            if c_files:
                try:
                    java_text = c_files[0].read_text(encoding="utf-8", errors="replace")
                    from yunhee.tools.as_is.events import (
                        extract_buttons,
                        extract_events_and_methods,
                    )

                    ev_list, _ = extract_events_and_methods(java_text, c_files[0])
                    ev_matches = [e.id.replace("E", "") for e in ev_list]
                    unreach_matches = [e.id.replace("E", "") for e in ev_list if e.is_unreachable]
                    if btn_cnt == 0:
                        btn_list = extract_buttons(java_text, events=ev_list, file_path=c_files[0])
                        btn_cnt = len(btn_list)
                except Exception:  # noqa: BLE001, S110
                    pass

        ev_ids = {int(x) for x in ev_matches}
        unreach_ids = {int(x) for x in unreach_matches}
        if unreachable_opt == "ignore":
            ev_ids = ev_ids - unreach_ids

        grid_cnt, grid_warn = count_as_is_grids(c_text)
        as_is_stats[c["name"]] = {
            "buttons": btn_cnt,
            "events": len(ev_ids),
            "event_ids": ev_ids,
            "unreach_ids": unreach_ids,
            "grids": grid_cnt,
            "grid_warn": grid_warn,
        }

    # 연결 컴포넌트 탐색 (같은 도메인만 포함)
    linked_candidates: list[tuple[str, str | None]] = []
    m_link_line = re.search(r"^-\s*연결\s*화면[·\s]*컴포넌트[^\n]*", text, re.MULTILINE)
    if m_link_line:
        line_str = m_link_line.group(0)
        for m in re.finditer(r"\[`?([A-Za-z0-9_]+)`?\]\(([^)]+)\)", line_str):
            linked_candidates.append((m.group(1), m.group(2)))

    for m in re.finditer(r"조회창\s+([A-Za-z0-9_]+)\s+열기", text):
        c_name = m.group(1)
        if not any(cand[0] == c_name for cand in linked_candidates):
            linked_candidates.append((c_name, None))

    try:
        screen_rel = screen_file.relative_to(src_index)
        screen_domain = screen_rel.parts[0]
    except (ValueError, IndexError):
        screen_domain = screen_file.parent.parent.name

    for comp_name, comp_rel in linked_candidates:
        if comp_name in as_is_stats:
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

        # 같은 도메인 연결 컴포넌트만 대조표에 포함
        if comp_domain != screen_domain:
            continue

        comp_text = comp_file.read_text(encoding="utf-8", errors="replace")
        btn_cnt = len(re.findall(r"-\s*<Button\b|\d+\.\s+<Button\b", comp_text))
        ev_matches = re.findall(r"\[E(\d+)\]", comp_text)
        unreach_matches = re.findall(r"\[E(\d+)\].*?(?:도달\s*불가|⚠\s*도달\s*불가)", comp_text)

        if not ev_matches and src_root:
            c_files = list(src_root.rglob(f"{comp_name}.java"))
            if c_files:
                try:
                    java_text = c_files[0].read_text(encoding="utf-8", errors="replace")
                    from yunhee.tools.as_is.events import (
                        extract_buttons,
                        extract_events_and_methods,
                    )

                    ev_list, _ = extract_events_and_methods(java_text, c_files[0])
                    ev_matches = [e.id.replace("E", "") for e in ev_list]
                    unreach_matches = [e.id.replace("E", "") for e in ev_list if e.is_unreachable]
                    if btn_cnt == 0:
                        btn_list = extract_buttons(java_text, events=ev_list, file_path=c_files[0])
                        btn_cnt = len(btn_list)
                except Exception:  # noqa: BLE001, S110
                    pass

        ev_ids = {int(x) for x in ev_matches}
        unreach_ids = {int(x) for x in unreach_matches}
        if unreachable_opt == "ignore":
            ev_ids = ev_ids - unreach_ids

        grid_cnt, grid_warn = count_as_is_grids(comp_text)

        as_is_stats[comp_name] = {
            "buttons": btn_cnt,
            "events": len(ev_ids),
            "event_ids": ev_ids,
            "unreach_ids": unreach_ids,
            "grids": grid_cnt,
            "grid_warn": grid_warn,
            "is_linked": True,
            "same_domain": True,
        }

    # TOBE 통계 파싱 (지정된 경우)
    tobe_path_raw = opts.get("tobe")
    tobe_stats: dict[str, dict[str, Any]] = {}
    if tobe_path_raw:
        if isinstance(tobe_path_raw, (list, tuple)):
            raw_paths = [str(p).strip() for p in tobe_path_raw if str(p).strip()]
        else:
            raw_paths = [p.strip() for p in str(tobe_path_raw).split(",") if p.strip()]
        for p_str in raw_paths:
            tobe_target = Path(p_str)
            if tobe_target.is_dir():
                for f in tobe_target.rglob("*.tsx"):
                    try:
                        f_text = f.read_text(encoding="utf-8", errors="replace")
                    except OSError:
                        continue
                    f_name = f.stem
                    t_btn = count_tobe_buttons(f_text)
                    impl_ev, skip_ev = _tobe_event_ids(f_text)
                    t_grid = count_tobe_grids(f_text)
                    tobe_stats[f_name] = {
                        "buttons": t_btn,
                        "events": len(impl_ev),
                        "events_skipped": len(skip_ev),
                        "impl_event_ids": impl_ev,
                        "skipped_event_ids": skip_ev,
                        "grids": t_grid,
                    }
            elif tobe_target.is_file():
                try:
                    f_text = tobe_target.read_text(encoding="utf-8", errors="replace")
                    t_btn = count_tobe_buttons(f_text)
                    impl_ev, skip_ev = _tobe_event_ids(f_text)
                    t_grid = count_tobe_grids(f_text)
                    tobe_stats[tobe_target.stem] = {
                        "buttons": t_btn,
                        "events": len(impl_ev),
                        "events_skipped": len(skip_ev),
                        "impl_event_ids": impl_ev,
                        "skipped_event_ids": skip_ev,
                        "grids": t_grid,
                    }
                except OSError:
                    pass

    # --no-e0 옵션 적용
    no_e0 = bool(opts.get("no_e0", False))
    if no_e0:
        for st in as_is_stats.values():
            st["event_ids"].discard(0)
            st["events"] = len(st["event_ids"])
        for st in tobe_stats.values():
            st["impl_event_ids"].discard(0)
            st["skipped_event_ids"].discard(0)
            st["events"] = len(st["impl_event_ids"])
            st["events_skipped"] = len(st["skipped_event_ids"])

    return {
        "screen": screen_file.stem,
        "as_is": as_is_stats,
        "tobe": tobe_stats,
        "done": opts.get("done", ""),
        "later": opts.get("later", ""),
        "no_e0": no_e0,
        "unreachable": unreachable_opt,
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

    if fmt == "json":
        return _render_json(obj, opts, group_done, group_later, group_remain, later_label)

    lines = [f"### `{screen_name}` UI 대조표"]

    if has_tobe:
        lines.append("\n| 클래스 | 버튼 (AS-IS/TOBE) | 이벤트 (AS-IS/TOBE) | 그리드 (AS-IS/TOBE) |")
        lines.append("|:---|:---:|:---:|:---:|")
        has_missing_e0 = False
        for c in all_cls_names:
            ai = as_is[c]
            tb = tobe.get(
                c,
                {
                    "buttons": 0,
                    "events": 0,
                    "events_skipped": 0,
                    "grids": 0,
                    "impl_event_ids": set(),
                    "skipped_event_ids": set(),
                },
            )
            ai_ev_ids = set(ai.get("event_ids", set()))
            tb_impl_ids = set(tb.get("impl_event_ids", set()))
            tb_skip_ids = set(tb.get("skipped_event_ids", set()))

            unreach_ids = set(ai.get("unreach_ids", set()))
            unreachable_opt = str((opts and opts.get("unreachable")) or obj.get("unreachable", "count")).lower()
            if unreachable_opt == "ignore" and unreach_ids:
                ai_ev_ids = ai_ev_ids - unreach_ids
                tb_impl_ids = tb_impl_ids - unreach_ids
                tb_skip_ids = tb_skip_ids - unreach_ids

            ai_events = len(ai_ev_ids)
            tb_events = len(tb_impl_ids)

            no_e0 = bool((opts and opts.get("no_e0")) or obj.get("no_e0", False))
            if no_e0:
                if 0 in ai_ev_ids:
                    ai_ev_ids.discard(0)
                    ai_events = len(ai_ev_ids)
                if 0 in tb_impl_ids:
                    tb_impl_ids.discard(0)
                    tb_events = len(tb_impl_ids)
                if 0 in tb_skip_ids:
                    tb_skip_ids.discard(0)

            missing_ids = sorted(ai_ev_ids - tb_impl_ids)
            ev_str = f"{ai_events}/{tb_events}"
            if missing_ids:
                missing_parts = []
                for eid in missing_ids:
                    if eid in tb_skip_ids:
                        missing_parts.append(f"E{eid}(생략)")
                    else:
                        if eid == 0:
                            has_missing_e0 = True
                        missing_parts.append(f"E{eid}(미구현)")
                ev_str += f" · 없음: {', '.join(missing_parts)}"
            elif tb.get("events_skipped", 0) > 0:
                ev_str += f" (생략 {tb['events_skipped']})"

            ai_g_str = f"{ai['grids']}⚠" if ai.get("grid_warn") else f"{ai['grids']}"
            lines.append(
                f"| {c} | {ai['buttons']}/{tb['buttons']} | {ev_str} | {ai_g_str}/{tb['grids']} |"
            )
        if has_missing_e0:
            lines.append("\nE0은 생성자 이벤트 — 대응 코드 근처에 `// [E0] …` 주석을 달면 된다")
        return "\n".join(lines)

    # 단계별 합계 표
    lines.append("\n| 그룹 | 클래스 수 | 버튼 | 이벤트 | 그리드 |")
    lines.append("|:---|---:|---:|---:|---:|")

    def calc_sum(names: list[str]) -> tuple[int, int, int]:
        valid_names = [n for n in names if not (as_is[n].get("is_linked") and not as_is[n].get("same_domain", True))]
        b = sum(as_is[n]["buttons"] for n in valid_names)
        e = sum(as_is[n]["events"] for n in valid_names)
        g = sum(as_is[n]["grids"] for n in valid_names)
        return b, e, g

    if group_done:
        b, e, g = calc_sum(group_done)
        cnt = len([n for n in group_done if not (as_is[n].get("is_linked") and not as_is[n].get("same_domain", True))])
        lines.append(f"| 이번 단계 (done) | {cnt} | {b} | {e} | {g} |")

    if group_later:
        b, e, g = calc_sum(group_later)
        cnt = len([n for n in group_later if not (as_is[n].get("is_linked") and not as_is[n].get("same_domain", True))])
        lines.append(f"| {later_label} | {cnt} | {b} | {e} | {g} |")

    if group_remain:
        b, e, g = calc_sum(group_remain)
        cnt = len([n for n in group_remain if not (as_is[n].get("is_linked") and not as_is[n].get("same_domain", True))])
        lines.append(f"| 미착수 (remain) | {cnt} | {b} | {e} | {g} |")

    valid_total = [n for n in all_cls_names if not (as_is[n].get("is_linked") and not as_is[n].get("same_domain", True))]
    tot_b, tot_e, tot_g = calc_sum(all_cls_names)
    lines.append(f"| **전체 합계** | **{len(valid_total)}** | **{tot_b}** | **{tot_e}** | **{tot_g}** |")

    return "\n".join(lines)


def _render_json(
    obj: dict[str, Any],
    opts: dict[str, Any] | None,
    group_done: list[str],
    group_later: list[str],
    group_remain: list[str],
    later_label: str,
) -> str:
    """UI 대조 결과를 JSON으로 직렬화한다 (그룹별 합계 + 클래스별 값, --tobe면 TOBE 칸 포함)."""
    import json

    as_is = obj["as_is"]
    tobe = obj["tobe"]
    no_e0 = bool((opts and opts.get("no_e0")) or obj.get("no_e0", False))

    def excluded(n: str) -> bool:
        return bool(as_is[n].get("is_linked") and not as_is[n].get("same_domain", True))

    def cls_row(n: str) -> dict[str, Any]:
        ai = as_is[n]
        ai_ids = set(ai.get("event_ids", set()))
        if no_e0:
            ai_ids.discard(0)
        row: dict[str, Any] = {
            "name": n,
            "linked": bool(ai.get("is_linked")),
            "same_domain": bool(ai.get("same_domain", True)),
            "as_is": {"buttons": ai["buttons"], "events": ai["events"], "grids": ai["grids"]},
        }
        if tobe:
            tb = tobe.get(n, {})
            impl = set(tb.get("impl_event_ids", set()))
            skip = set(tb.get("skipped_event_ids", set()))
            if no_e0:
                impl.discard(0)
                skip.discard(0)
            row["tobe"] = {
                "buttons": tb.get("buttons", 0),
                "events": tb.get("events", len(impl)),
                "events_skipped": tb.get("events_skipped", len(skip)),
                "grids": tb.get("grids", 0),
            }
            row["missing_events"] = [
                {"id": f"E{e}", "reason": "생략" if e in skip else "미구현"} for e in sorted(ai_ids - impl)
            ]
        return row

    def group(label: str, names: list[str]) -> dict[str, Any]:
        valid = [n for n in names if not excluded(n)]
        return {
            "group": label,
            "classes": len(valid),
            "buttons": sum(as_is[n]["buttons"] for n in valid),
            "events": sum(as_is[n]["events"] for n in valid),
            "grids": sum(as_is[n]["grids"] for n in valid),
        }

    groups = []
    if group_done:
        groups.append(group("done", group_done))
    if group_later:
        groups.append(group(later_label, group_later))
    if group_remain:
        groups.append(group("remain", group_remain))
    return json.dumps(
        {
            "screen": obj["screen"],
            "groups": groups,
            "total": group("total", list(as_is.keys())),
            "classes": [cls_row(n) for n in as_is],
        },
        ensure_ascii=False,
        indent=2,
        default=str,
    )
