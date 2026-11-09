"""screen-desc: 화면번호(복수 지정 가능, 쉼표·공백 혼합 지원)로 알 수 있는 모든 정보(메뉴·파일·팝업·하위컴포넌트·그리드·버튼·API·백엔드·SQL·테이블·ASIS)를 반환한다."""

from __future__ import annotations

import json
import re
from collections import deque
from pathlib import Path
from typing import Any

from yunhee.tools.trace.resolve import (
    TraceContext,
    find_class_doc,
    load_context,
    resolve_screen,
)
from yunhee.tools.trace.screen import ScreenDoc, parse_screen_doc
from yunhee.tools.trace.screen_catalog import (
    _IMPORT_RE,
    ScreenRecord,
    _is_valid_propagated_title,
    _load_full_menu_map,
    iter_screens,
)
from yunhee.tools.trace.tobe import TobeLayout, find_layout
from yunhee.tools.trace.tobe_rag import _load_menus_from_snapshot

_POPUP_ROLES = {"Lookup", "Edit", "Popup", "Move"}


def parse_screen_targets(raw_args: list[str] | str) -> list[str]:
    """쉼표(,)와 공백이 섞인 화면번호/화면명 인자들을 개별 토큰 리스트로 분리한다.

    예:
        ["1111,2222,3333,", "4444"] -> ["1111", "2222", "3333", "4444"]
        "1002, 1029  #1085" -> ["1002", "1029", "1085"]
    """
    if isinstance(raw_args, str):
        raw_list = [raw_args]
    else:
        raw_list = list(raw_args or [])

    tokens: list[str] = []
    seen: set[str] = set()
    for chunk in raw_list:
        for part in re.split(r"[\s,]+", chunk.strip()):
            clean = part.strip()
            if not clean:
                continue
            if clean.startswith("#") and clean[1:].isdigit():
                clean = clean[1:]
            if clean not in seen:
                seen.add(clean)
                tokens.append(clean)
    return tokens


def _extract_jsdoc_lines(text: str) -> list[str]:
    """파일 상단 /** ... */ 주석 줄들을 깔끔하게 추출한다."""
    m = re.match(r"\s*/\*\*+([\s\S]*?)\*/", text)
    if not m:
        return []
    lines: list[str] = []
    for raw in m.group(1).splitlines():
        clean = raw.strip().lstrip("*").strip()
        if clean:
            lines.append(clean)
    return lines


def _direct_import_names(rec: ScreenRecord, by_name: dict[str, ScreenRecord]) -> list[str]:
    """해당 컴포넌트 소스에서 직접 import한 하위 컴포넌트 이름만 추출한다."""
    txt = rec.text
    if not txt:
        return list(rec.child_components)
    out: list[str] = []
    for m in _IMPORT_RE.finditer(txt):
        stem = Path(m.group(2)).stem
        if stem in by_name and stem != rec.name and stem not in out:
            out.append(stem)
    return out


def _collect_related_records(
    main_rec: ScreenRecord | None,
    direct_menu_recs: list[ScreenRecord],
    by_name: dict[str, ScreenRecord],
) -> tuple[list[ScreenRecord], list[ScreenRecord]]:
    """메인 화면에서 연결된 팝업(Lookup/Edit/Popup/Move)과 하위 컴포넌트(TabPage/Grid/Component)를 수집한다."""
    visited: set[str] = set()
    ordered_children: list[ScreenRecord] = []

    if main_rec:
        visited.add(main_rec.name)

    q: deque[tuple[ScreenRecord, int]] = deque()
    if main_rec:
        q.append((main_rec, 0))
    for r in direct_menu_recs:
        if r.name not in visited:
            visited.add(r.name)
            ordered_children.append(r)
            if r.role not in _POPUP_ROLES:
                q.append((r, 1))

    while q:
        cur, depth = q.popleft()
        if depth >= 3:
            continue
        for child_name in _direct_import_names(cur, by_name):
            child_rec = by_name.get(child_name)
            if not child_rec or child_rec.name in visited:
                continue
            # 다른 독립 _Tab_ 화면으로 역참조하는 경우 제외 (단, 메인 화면이 직접 import한 위임 _Tab_은 depth==0에서 허용)
            if child_rec.role == "Tab" and depth > 0:
                continue
            visited.add(child_rec.name)
            ordered_children.append(child_rec)
            # Tab, TabPage, Grid, Component는 내부에 속한 팝업을 찾기 위해 탐색하되, 팝업 자체의 하위 팝업은 확장하지 않음
            if child_rec.role not in _POPUP_ROLES:
                q.append((child_rec, depth + 1))

    popups: list[ScreenRecord] = []
    sub_components: list[ScreenRecord] = []
    for rec in ordered_children:
        is_popup = rec.role in _POPUP_ROLES or any(
            m.kind in ("LookupModal", "EditModal", "Modal") for m in rec.modals
        )
        if is_popup and rec.role not in ("TabPage", "Tab"):
            popups.append(rec)
        else:
            sub_components.append(rec)

    return popups, sub_components


def _clean_modals(modals: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in modals:
        if m.title.startswith("{") or not _is_valid_propagated_title(m.title):
            continue
        out.append({"kind": m.kind, "title": m.title, "line": m.line})
    return out


def _clean_buttons(buttons: list[str]) -> list[str]:
    out: list[str] = []
    for b in buttons:
        clean = re.sub(r"^[\s\S]*\}>\s*", "", b).strip()
        if clean and clean not in out:
            out.append(clean)
    return out


def _format_component_brief(rec: ScreenRecord) -> dict[str, Any]:
    modal_list = _clean_modals(rec.modals)
    grid_list = [
        {"field": c.field, "label": c.label, "col_type": c.col_type, "width": c.width}
        for c in rec.grid_cols
    ]
    return {
        "name": rec.name,
        "role": rec.role,
        "file": rec.file,
        "page_style": rec.page_style,
        "modals": modal_list,
        "search_fields": rec.search_fields,
        "buttons": _clean_buttons(rec.buttons),
        "grid_cols": grid_list,
        "apis": rec.apis,
        "backend_files": rec.backend_files,
        "sql_ids": rec.sql_ids,
        "tables": rec.tables,
    }


def _build_asis_info(
    screen_name: str,
    ctx: TraceContext,
) -> dict[str, Any] | None:
    if not screen_name or not ctx.has_index:
        return None
    resolved = resolve_screen(screen_name, ctx)
    doc_path = find_class_doc(ctx, resolved)
    if doc_path is None and resolved != screen_name:
        doc_path = find_class_doc(ctx, screen_name)
    if doc_path is None:
        return None

    doc: ScreenDoc = parse_screen_doc(
        resolved,
        doc_path.read_text(encoding="utf-8", errors="replace"),
    )
    popups = [
        c
        for c in doc.classes
        if any(tok in c for tok in ("_Lookup_", "_Edit_", "_Popup_", "_Move_"))
    ]
    main_ui = doc.ui.get(doc.name)
    events = main_ui.events if main_ui else []
    buttons = main_ui.buttons if main_ui else []
    grids = [
        {"name": gname, "columns": cols}
        for gname, cols in (main_ui.grids if main_ui else [])
    ]

    return {
        "screen": doc.name,
        "kind": doc.kind,
        "file": doc.file,
        "index_doc": str(doc_path),
        "menus": doc.menus,
        "classes": doc.classes,
        "popups": popups,
        "layout": main_ui.layout if main_ui else "",
        "toolbar": main_ui.toolbar if main_ui else [],
        "buttons": buttons,
        "events": events,
        "grids": grids,
        "services": [
            {
                "service": s.key,
                "callers": s.callers,
                "server": s.server,
                "sql_ids": s.sql_ids,
                "note": s.note,
            }
            for s in doc.services
        ],
        "tables": doc.tables,
        "functions": doc.functions,
        "servlets": doc.servlets,
    }


def describe_single_screen(
    target: str,
    layout: TobeLayout,
    tobe_screens: list[ScreenRecord],
    menus_summary: list[dict[str, Any]],
    full_menu_map: dict[str, list[tuple[str, str, str, bool]]],
    ctx: TraceContext,
) -> dict[str, Any]:
    """단일 화면번호(또는 화면 클래스명)에 대한 모든 정보를 조립한다."""
    clean = target.strip().lstrip("#")
    by_name = {s.name: s for s in tobe_screens}
    by_name_lower = {s.name.lower(): s for s in tobe_screens}

    # 1. 메뉴 엔트리 탐색
    menu_entry: dict[str, Any] | None = None
    for m in menus_summary:
        if str(m.get("no")) == clean:
            menu_entry = m
            break

    # 만약 화면 클래스명으로 들어온 경우 (예: Emp00_Tab_TransInfo)
    if menu_entry is None:
        for m in menus_summary:
            if (
                str(m.get("tobe_screen", "")).lower() == clean.lower()
                or str(m.get("asis_screen", "")).lower() == clean.lower()
            ):
                menu_entry = m
                break

    # 2. TOBE 메인 화면 및 동일 메뉴번호 소속 컴포넌트 탐색
    main_rec: ScreenRecord | None = None
    direct_menu_recs: list[ScreenRecord] = []

    if clean.isdigit():
        matched = [s for s in tobe_screens if s.menu_no == clean]
        matched.sort(key=lambda s: (0 if s.role == "Tab" else 1, s.name))
        if matched:
            if matched[0].role == "Tab":
                main_rec = matched[0]
                direct_menu_recs = matched[1:]
            else:
                direct_menu_recs = matched
        if main_rec is None and menu_entry and menu_entry.get("tobe_screen"):
            main_rec = by_name.get(menu_entry["tobe_screen"])
    else:
        main_rec = by_name.get(clean) or by_name_lower.get(clean.lower())
        if main_rec and main_rec.menu_no:
            direct_menu_recs = [
                s
                for s in tobe_screens
                if s.menu_no == main_rec.menu_no and s.name != main_rec.name
            ]

    screen_no = (
        (menu_entry["no"] if menu_entry else "")
        or (main_rec.menu_no if main_rec else "")
        or (clean if clean.isdigit() else "")
    )
    asis_screen_name = (
        (menu_entry.get("asis_screen", "") if menu_entry else "")
        or (main_rec.name if main_rec else "")
        or (clean if not clean.isdigit() else "")
    )
    tobe_screen_name = (
        (main_rec.name if main_rec else "")
        or (menu_entry.get("tobe_screen", "") if menu_entry else "")
    )

    # 동일 화면 클래스에 연결된 모든 메뉴 경로
    related_menus: list[dict[str, Any]] = []
    lookup_key = tobe_screen_name or asis_screen_name
    if lookup_key and lookup_key in full_menu_map:
        for no, full_path, leaf, active in full_menu_map[lookup_key]:
            related_menus.append(
                {
                    "no": no,
                    "path": full_path,
                    "name": leaf,
                    "active": active,
                }
            )

    menu_info = {
        "no": screen_no,
        "name": (menu_entry.get("name", "") if menu_entry else "")
        or (main_rec.menu_name if main_rec else ""),
        "path": (menu_entry.get("path", "") if menu_entry else "")
        or (main_rec.menu_path if main_rec else ""),
        "active": bool(menu_entry.get("active", True)) if menu_entry else bool(main_rec),
        "migrated": main_rec is not None or bool(menu_entry and menu_entry.get("migrated")),
        "asis_screen": asis_screen_name,
        "tobe_screen": tobe_screen_name,
        "related_menus": related_menus,
    }

    # 3. TOBE 상세 정보 조립
    tobe_info: dict[str, Any] | None = None
    if main_rec or direct_menu_recs:
        popups, sub_components = _collect_related_records(main_rec, direct_menu_recs, by_name)
        all_recs = ([main_rec] if main_rec else []) + popups + sub_components

        all_fe_files = list(dict.fromkeys(r.file for r in all_recs if r.file))
        all_apis = list(dict.fromkeys(a for r in all_recs for a in r.apis))
        all_be_files = list(dict.fromkeys(b for r in all_recs for b in r.backend_files))
        all_sql_ids = list(dict.fromkeys(sid for r in all_recs for sid in r.sql_ids))
        all_tables = list(dict.fromkeys(t for r in all_recs for t in r.tables))

        all_modals: list[dict[str, Any]] = []
        seen_modal_keys: set[tuple[str, str, str]] = set()
        for r in all_recs:
            for cm in _clean_modals(r.modals):
                key = (r.name, cm["kind"], cm["title"])
                if key not in seen_modal_keys:
                    seen_modal_keys.add(key)
                    all_modals.append(
                        {
                            "component": r.name,
                            "file": r.file,
                            "kind": cm["kind"],
                            "title": cm["title"],
                            "line": cm["line"],
                        }
                    )

        header_lines = _extract_jsdoc_lines(main_rec.text) if main_rec else []

        tobe_info = {
            "main_screen": main_rec.name if main_rec else "",
            "main_file": main_rec.file if main_rec else "",
            "role": main_rec.role if main_rec else "",
            "page_style": main_rec.page_style if main_rec else "",
            "header_comments": header_lines,
            "opening_tabs": main_rec.opening_tabs if main_rec else [],
            "search_fields": main_rec.search_fields if main_rec else [],
            "buttons": _clean_buttons(main_rec.buttons) if main_rec else [],
            "modals": _clean_modals(main_rec.modals) if main_rec else [],
            "grid_cols": [
                {"field": c.field, "label": c.label, "col_type": c.col_type, "width": c.width}
                for c in (main_rec.grid_cols if main_rec else [])
            ],
            "popups": [_format_component_brief(p) for p in popups],
            "sub_components": [_format_component_brief(sc) for sc in sub_components],
            "all_frontend_files": all_fe_files,
            "all_modals": all_modals,
            "apis": all_apis,
            "backend_files": all_be_files,
            "sql_ids": all_sql_ids,
            "tables": all_tables,
        }

    # 4. AS-IS 상세 정보 조립
    asis_info = _build_asis_info(asis_screen_name, ctx)

    found = bool(menu_entry or main_rec or direct_menu_recs or asis_info)
    return {
        "query": target,
        "screen_no": screen_no or clean,
        "found": found,
        "menu": menu_info,
        "tobe": tobe_info,
        "asis": asis_info,
    }


def describe_screens(
    raw_targets: list[str] | str,
    tobe: Path | str | None = None,
) -> dict[str, Any]:
    """복수의 화면번호(쉼표/공백 구분)를 받아 전체 상세 설명 결과를 반환한다."""
    targets = parse_screen_targets(raw_targets)
    layout = find_layout(Path(tobe) if tobe else None)
    tobe_screens = iter_screens(side="tobe", tobe=layout.root)
    menus_summary = _load_menus_from_snapshot(layout)
    ctx = load_context("both")
    full_menu_map = _load_full_menu_map(ctx, layout)

    items = [
        describe_single_screen(
            t,
            layout=layout,
            tobe_screens=tobe_screens,
            menus_summary=menus_summary,
            full_menu_map=full_menu_map,
            ctx=ctx,
        )
        for t in targets
    ]
    return {
        "count": len(items),
        "found_count": sum(1 for item in items if item["found"]),
        "tobe_root": str(layout.root),
        "screens": items,
    }


def render_screen_desc_json(data: dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def render_screen_desc_md(data: dict[str, Any]) -> str:
    screens = data.get("screens") or []
    if not screens:
        return "조회할 화면번호가 지정되지 않았습니다."

    out: list[str] = []
    if len(screens) > 1:
        out.append(f"# 화면 상세 정보 요약 ({data.get('found_count', 0)}/{len(screens)}건)")
        out.append("")
        out.append("| 화면번호 | 메뉴 경로 | 상태 | TOBE 화면명 | 프론트엔드 파일 | 스타일 | 팝업 수 | 하위컴포넌트 수 | 테이블 수 |")
        out.append("| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: |")
        for item in screens:
            sno = f"#{item['screen_no']}" if str(item["screen_no"]).isdigit() else item["screen_no"]
            if not item["found"]:
                out.append(f"| {sno} | (미발견) | ❌ 없음 | - | - | - | 0 | 0 | 0 |")
                continue
            m = item["menu"]
            tb = item.get("tobe")
            status = "✔ TOBE" if m.get("migrated") else "⏳ AS-IS(미변환)"
            scr_name = f"`{m['tobe_screen']}`" if m.get("tobe_screen") else (f"`{m['asis_screen']}`" if m.get("asis_screen") else "-")
            fe_file = f"`{tb['main_file']}`" if tb and tb.get("main_file") else "-"
            style = tb.get("page_style") or "-" if tb else "-"
            pop_cnt = len(tb.get("popups", [])) if tb else 0
            sub_cnt = len(tb.get("sub_components", [])) if tb else 0
            tbl_cnt = len(tb.get("tables", [])) if tb else (len(item["asis"].get("tables", [])) if item.get("asis") else 0)
            out.append(
                f"| {sno} | {m.get('path') or '-'} | {status} | {scr_name} | {fe_file} | {style} | {pop_cnt} | {sub_cnt} | {tbl_cnt} |"
            )
        out.append("")
        out.append("---")
        out.append("")

    for idx, item in enumerate(screens):
        if idx > 0:
            out.append("")
            out.append("---")
            out.append("")

        sno = f"#{item['screen_no']}" if str(item["screen_no"]).isdigit() else item["screen_no"]
        if not item["found"]:
            out.append(f"## [{sno}] 화면 정보를 찾을 수 없음")
            out.append(f"- 입력 인자 `{item['query']}`에 해당하는 메뉴 번호나 화면 클래스를 찾지 못했습니다.")
            continue

        m = item["menu"]
        tb = item.get("tobe")
        asis = item.get("asis")
        title_name = m.get("name") or m.get("tobe_screen") or m.get("asis_screen") or sno
        status_badge = "✔ TOBE 변환완료" if m.get("migrated") else "⏳ TOBE 미변환 (AS-IS 전용)"

        out.append(f"## [{sno}] {title_name} ({status_badge})")
        out.append("")
        out.append("### 1. 기본 및 메뉴 정보")
        out.append(f"- **화면번호**: `{sno}`")
        out.append(f"- **메뉴명**: {m.get('name') or '-'}")
        out.append(f"- **메뉴 경로**: {m.get('path') or '-'}")
        out.append(f"- **메뉴 활성 여부**: {'사용(Active)' if m.get('active') else '미사용(Inactive)'}")
        out.append(f"- **TOBE 화면 클래스**: `{m.get('tobe_screen') or '-'}`")
        out.append(f"- **AS-IS 화면 클래스**: `{m.get('asis_screen') or '-'}`")
        if len(m.get("related_menus") or []) > 1:
            rel_strs = [
                f"`#{rm['no']}` {rm['path']} ({'사용' if rm['active'] else '미사용'})"
                for rm in m["related_menus"]
            ]
            out.append(f"- **동일 화면 연결 메뉴({len(rel_strs)})**: {', '.join(rel_strs)}")

        if tb:
            out.append("")
            out.append("### 2. TOBE 프론트엔드 화면 구성")
            out.append(f"- **메인 파일**: `{tb.get('main_file') or '-'}`")
            out.append(f"- **역할 / 페이지 스타일(SID)**: `{tb.get('role') or '-'}` / `{tb.get('page_style') or '-'}`")
            if tb.get("header_comments"):
                out.append("- **화면 머리 주석 요약**:")
                for hc in tb["header_comments"]:
                    out.append(f"  - {hc}")
            if tb.get("search_fields"):
                out.append(f"- **조회 조건 (`SearchBar` 라벨 {len(tb['search_fields'])}개)**: {', '.join(tb['search_fields'])}")
            else:
                out.append("- **조회 조건 (`SearchBar`)**: 없음")
            if tb.get("buttons"):
                out.append(f"- **메인 화면 버튼 ({len(tb['buttons'])}개)**: {', '.join(tb['buttons'])}")
            else:
                out.append("- **메인 화면 버튼**: 없음")

            main_cols = tb.get("grid_cols") or []
            if main_cols:
                col_strs = [f"`{c['label']}`(`{c['field']}`:{c['col_type']})" for c in main_cols]
                out.append(f"- **메인 그리드 컬럼 ({len(main_cols)}개)**: {', '.join(col_strs)}")

            # 사용되는 팝업/모달 상세
            popups = tb.get("popups") or []
            all_modals = tb.get("all_modals") or []
            out.append("")
            out.append(f"### 3. 사용되는 팝업·모달 창 ({len(popups)}개 컴포넌트 / 모달 타이틀 {len(all_modals)}건)")
            if not popups and not all_modals:
                out.append("- 사용되는 팝업/모달 창 없음")
            else:
                if all_modals:
                    out.append("- **모달 타이틀 요약**:")
                    for md in all_modals:
                        out.append(
                            f"  - `{md['kind']}` **\"{md['title']}\"** — `{md['component']}` (`{md['file']}`:L{md['line']})"
                        )
                if popups:
                    out.append("")
                    out.append("| 팝업 컴포넌트명 | 구분 | 모달 타이틀 | 파일 경로 | 내부 버튼 | 그리드 컬럼 수 | 호출 API |")
                    out.append("| :--- | :--- | :--- | :--- | :--- | ---: | :--- |")
                    for p in popups:
                        m_titles = ", ".join(f"{m['kind']}({m['title']})" for m in p.get("modals", [])) or "-"
                        p_btns = ", ".join(p.get("buttons", [])[:8]) or "-"
                        p_cols = len(p.get("grid_cols", []))
                        p_apis = ", ".join(p.get("apis", [])[:4]) or "-"
                        out.append(
                            f"| `{p['name']}` | {p['role']} | {m_titles} | `{p['file']}` | {p_btns} | {p_cols} | {p_apis} |"
                        )

            # 하위 탭페이지 / 그리드 / 부품 컴포넌트
            sub_comps = tb.get("sub_components") or []
            if sub_comps:
                out.append("")
                out.append(f"### 4. 하위 탭페이지·그리드·연결 컴포넌트 ({len(sub_comps)}개)")
                out.append("| 컴포넌트명 | 구분 | 파일 경로 | 버튼 | 그리드 컬럼 수 | 모달 타이틀 |")
                out.append("| :--- | :--- | :--- | :--- | ---: | :--- |")
                for sc in sub_comps:
                    sc_btns = ", ".join(sc.get("buttons", [])[:8]) or "-"
                    sc_cols = len(sc.get("grid_cols", []))
                    sc_modals = ", ".join(f"{m['kind']}({m['title']})" for m in sc.get("modals", [])) or "-"
                    out.append(
                        f"| `{sc['name']}` | {sc['role']} | `{sc['file']}` | {sc_btns} | {sc_cols} | {sc_modals} |"
                    )

            # 백엔드 API / 파일 / SQL / DB 테이블
            out.append("")
            out.append("### 5. TOBE 백엔드 API · 매퍼 SQL · DB 테이블")
            apis = tb.get("apis") or []
            be_files = tb.get("backend_files") or []
            sql_ids = tb.get("sql_ids") or []
            tables = tb.get("tables") or []
            out.append(f"- **호출 API ({len(apis)}개)**: {', '.join(f'`{a}`' for a in apis) if apis else '없음'}")
            if be_files:
                out.append(f"- **백엔드 파일 ({len(be_files)}개)**:")
                for bf in be_files:
                    out.append(f"  - `{bf}`")
            else:
                out.append("- **백엔드 파일**: 없음")
            out.append(
                f"- **MyBatis SQL ID ({len(sql_ids)}개)**: {', '.join(f'`{s}`' for s in sql_ids) if sql_ids else '없음'}"
            )
            out.append(
                f"- **참조 DB 테이블 ({len(tables)}개)**: {', '.join(f'`{t}`' for t in tables) if tables else '없음'}"
            )

        if asis:
            out.append("")
            sec_no = "6" if tb else "2"
            out.append(f"### {sec_no}. AS-IS 레거시 화면 정보 (`{asis['screen']}`)")
            out.append(f"- **AS-IS 소스 파일**: `{asis.get('file') or '-'}`")
            if asis.get("layout"):
                out.append(f"- **AS-IS 레이아웃**: {asis['layout']}")
            if asis.get("classes"):
                out.append(
                    f"- **AS-IS 연결 클래스 ({len(asis['classes'])}개)**: {', '.join(f'`{c}`' for c in asis['classes'])}"
                )
            if asis.get("popups"):
                out.append(
                    f"- **AS-IS 팝업 클래스 ({len(asis['popups'])}개)**: {', '.join(f'`{p}`' for p in asis['popups'])}"
                )
            if asis.get("services"):
                out.append(f"- **AS-IS 호출 서비스 RPC ({len(asis['services'])}개)**:")
                for sv in asis["services"][:20]:
                    sql_part = ", ".join(f"`{sid}`" for sid in sv["sql_ids"]) if sv["sql_ids"] else (sv["note"] or "-")
                    out.append(f"  - `{sv['service']}` → {sql_part} (호출: {', '.join(sv['callers'])})")
            if asis.get("tables"):
                out.append(
                    f"- **AS-IS 참조 테이블 ({len(asis['tables'])}개)**: {', '.join(f'`{t}`' for t in asis['tables'])}"
                )
            if asis.get("functions"):
                out.append(
                    f"- **AS-IS DB 함수 ({len(asis['functions'])}개)**: {', '.join(f'`{f}`' for f in asis['functions'])}"
                )
            if asis.get("events"):
                out.append(f"- **AS-IS 주요 이벤트 ({len(asis['events'])}개)**:")
                for ev in asis["events"][:15]:
                    out.append(f"  - {ev}")

    return "\n".join(out) + "\n"
