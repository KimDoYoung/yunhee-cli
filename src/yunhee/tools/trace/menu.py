"""trace-menu: 메뉴 트리 → ASIS 화면 클래스 → TOBE 화면/API.

메뉴는 ASIS 색인의 `menus.md`(sys06_menu 기준)에서 읽는다. 경로 검색어는 `>`로 나눈 조각이 메뉴 경로의 각 단계에
(부분 문자열로) 순서대로 들어 있는 메뉴를 고른다. 메뉴 번호(`#1029`)나 화면 클래스명으로도 찾는다.
"""

from __future__ import annotations

from pathlib import Path

from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import MenuEntry, TraceContext, load_menus
from yunhee.tools.trace.tobe import TobeIndex, build_index, find_layout

MAX_API = 4


def matches(entry: MenuEntry, query: str) -> bool:
    q = query.strip()
    if not q:
        return True
    if q.lstrip("#").isdigit():
        return entry.no == q.lstrip("#")
    if entry.screen and q.lower() in entry.screen.lower() and ">" not in q:
        return True
    pieces = [p.strip().lower() for p in q.split(">") if p.strip()]
    steps = [s.strip().lower() for s in entry.path.split(">")]
    i = 0
    for piece in pieces:  # 조각들이 경로 단계에 순서대로 들어 있어야 한다
        while i < len(steps) and piece not in steps[i]:
            i += 1
        if i >= len(steps):
            return False
        i += 1
    return True


def _tobe_status(entry: MenuEntry, idx: TobeIndex | None) -> str:
    if idx is None or not entry.screen:
        return ""
    tsx = idx.tsx.get(entry.screen) or next((t for t in idx.tsx.values() if Path(t.as_is_file).stem == entry.screen), None)
    if tsx is None:
        return " — TOBE 없음"
    urls = []
    for obj, fn in tsx.api_calls:
        api = idx.api_fns.get((obj, fn))
        if api:
            urls.append(f"{api.verb} {api.url}")
    urls = list(dict.fromkeys(urls))
    shown = ", ".join(urls[:MAX_API]) + (f" … 외 {len(urls) - MAX_API}개" if len(urls) > MAX_API else "")
    return f" — TOBE {idx.rel(tsx.file)}" + (f" / API {len(urls)}개: {shown}" if urls else " / API 호출 없음")


def trace_menu(ctx: TraceContext, tobe: Path | None = None, query: str | None = None) -> TraceResult:
    res = TraceResult(
        command="trace-menu",
        description="메뉴 트리 → ASIS 화면 클래스 → TOBE 화면/API",
        side=ctx.side,
        params={"menu_path": query},
    )
    res.unresolved += ctx.unresolved
    menus = load_menus(ctx)
    if not menus:
        if ctx.has_index:
            res.unresolved.append("색인에 menus.md가 없음 — `yunhee index-src --menus-from-db …`로 메뉴를 포함해 다시 색인")
        return res
    layout = find_layout(tobe)
    idx = build_index(str(layout.root)) if layout.usable else None
    if idx is None:
        res.unresolved.append(f"TOBE 소스를 찾지 못해 ASIS만 낸다 ({layout.root}) — --tobe로 지정")

    if not query:
        tops: dict[str, list[MenuEntry]] = {}
        for m in menus:
            tops.setdefault(m.path.split(" > ")[0], []).append(m)
        res.facts.append(f"최상위 메뉴 {len(tops)}개, 메뉴 {len(menus)}개 — 경로나 번호로 좁혀서 본다 (예: `trace-menu \"{next(iter(tops))}\"`)")
        for name, items in sorted(tops.items(), key=lambda kv: -len(kv[1])):
            with_screen = [m for m in items if m.screen]
            ported = sum(1 for m in with_screen if idx and (m.screen in idx.tsx or any(Path(t.as_is_file).stem == m.screen for t in idx.tsx.values())))
            res.facts.append(f"{name}: 메뉴 {len(items)}, 화면 있는 메뉴 {len(with_screen)}" + (f", TOBE 있음 {ported}" if idx else ""))
        return res

    found = [m for m in menus if matches(m, query)]
    if not found:
        res.unresolved.append(f"'{query}'에 맞는 메뉴가 없음")
        return res
    tree: dict[str, list[str]] = {}
    for m in found:
        steps = [s.strip() for s in m.path.split(">")]
        head = " > ".join(steps[:-1]) or steps[0]
        use = "" if m.use == "true" else " (사용 안 함)"
        screen = f" → {m.screen}" if m.screen else " → (화면 클래스 없음)"
        tree.setdefault(head, []).append(f"{steps[-1]} (#{m.no}){use}{screen}{_tobe_status(m, idx)}")
        res.evidence.append(f"menus.md #{m.no} {m.path}")
    res.facts.append(f"'{query}'에 맞는 메뉴 {len(found)}개")
    for head, lines in tree.items():
        res.facts.append(head + "\n" + "\n".join(f"  - {line}" for line in lines))
    no_screen = [m for m in found if not m.screen]
    if no_screen:
        res.unresolved.append("화면 클래스가 없는 메뉴(MenuOpener에 없음): " + ", ".join(f"#{m.no}" for m in no_screen[:10]))
    return res
