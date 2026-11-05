"""trace-gap: ASIS에만 있는 것, TOBE에만 있는 것, 추적하지 못한 지점 (도메인 단위 집계).

대응 판정은 trace-pair와 같은 근거를 쓴다: 화면은 같은 클래스명·TSX 헤더의 AS-IS, 서비스는 TOBE 주석의 AS-IS 서비스 키,
SQL은 TOBE 문장 주석의 AS-IS id. 근거가 없으면 "대응 없음"이 아니라 "추적하지 못함"으로 따로 센다.
"""

from __future__ import annotations

import re
from collections import deque
from pathlib import Path

from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import TraceContext, load_menus
from yunhee.tools.trace.tobe import TobeIndex, TobeLayout, build_index, find_layout

MAX_LISTED = 25
DEFAULT_STUB_PATTERN = r"다음 단계|아직 변환|연결됩니다|연결합니다|제공됩니다|아직 연결되지"


def _listing(label: str, items: list[str]) -> str:
    items = sorted(items)
    shown = "\n".join(f"  - {i}" for i in items[:MAX_LISTED])
    more = f"\n  … 외 {len(items) - MAX_LISTED}개" if len(items) > MAX_LISTED else ""
    return f"{label}({len(items)}):\n{shown}{more}" if items else f"{label}(0)"


def _tsx_domain(tsx_file: str, idx: TobeIndex) -> str:
    try:
        return Path(tsx_file).relative_to(idx.layout.pages_dir).parts[0]
    except (ValueError, IndexError):
        return ""


def _screen_gap(ctx: TraceContext, idx: TobeIndex, domain: str | None, res: TraceResult) -> None:
    index = ctx.index_data or {}
    src_index = ctx.src_index
    asis_screens: dict[str, str] = {}  # 화면 클래스 → 도메인
    if src_index:
        for p in src_index.glob("*/screens/*.md"):
            asis_screens[p.stem] = p.parent.parent.name
    asis_screens = {c: d for c, d in asis_screens.items() if not domain or d == domain}
    menu_no = {m.screen: m.no for m in load_menus(ctx) if m.screen}

    tobe_by_header = {Path(t.as_is_file).stem for t in idx.tsx.values() if t.as_is_file}
    a_only = [f"{c}" + (f" (#{menu_no[c]})" if c in menu_no else "") for c in asis_screens if c not in idx.tsx and c not in tobe_by_header]
    all_asis = set(index.get("client_classes", {})) | set(asis_screens)
    tobe_tsx = {n: t for n, t in idx.tsx.items() if not domain or _tsx_domain(t.file, idx) == domain}
    t_only = [n for n, t in tobe_tsx.items() if n not in all_asis and Path(t.as_is_file).stem not in all_asis]
    no_header = [n for n, t in tobe_tsx.items() if not t.as_is_file]
    covered = len(asis_screens) - len(a_only)
    res.facts.append(f"화면: ASIS {len(asis_screens)} / TOBE {len(tobe_tsx)} — TOBE에 대응 TSX가 있는 ASIS 화면 {covered}")
    res.facts.append(_listing("ASIS에만 있는 화면(TOBE에 같은 이름의 TSX도, 헤더 AS-IS도 없음)", a_only))
    res.facts.append(_listing("TOBE에만 있는 화면(ASIS 색인에 같은 이름의 클래스가 없음)", t_only))
    if no_header:
        res.unresolved.append(_listing("TSX 헤더에 AS-IS가 없어 ASIS 출처를 추적하지 못한 화면", no_header))


def _service_gap(ctx: TraceContext, idx: TobeIndex, domain: str | None, res: TraceResult) -> None:
    index = ctx.index_data or {}
    asis_keys: set[str] = set()
    for cls, info in index.get("server_classes", {}).items():
        for m in info.get("methods", []):
            if m.get("is_service"):
                asis_keys.add(f"{cls}.{m['name']}")
    asis_keys = {k for k in asis_keys if not domain or k.split(".")[0] == domain}
    tobe_keys = {k for ep in idx.endpoints for k in ep.keys} | {k for fn in idx.api_fns.values() for k in fn.keys}
    scoped_tobe = {k for k in tobe_keys if not domain or k.split(".")[0] == domain}
    res.facts.append(f"서비스(RPC): ASIS {len(asis_keys)} / TOBE 주석에 적힌 서비스 키 {len(scoped_tobe)} — 대응 {len(asis_keys & scoped_tobe)}")
    res.facts.append(_listing("ASIS에만 있는 서비스(TOBE 컨트롤러·api 주석에 이 서비스 키가 없음)", list(asis_keys - scoped_tobe)))
    res.facts.append(_listing("TOBE 주석에만 있는 서비스 키(ASIS 색인에 없음 — 오기·삭제된 서비스 가능)", list(scoped_tobe - asis_keys)))
    bare = [f"{ep.verb} {ep.path} ({ep.controller}.{ep.method})" for ep in idx.endpoints
            if not ep.keys and (not domain or ep.path.startswith(f"/api/v1/{domain}/"))]
    if bare:
        res.unresolved.append(_listing("AS-IS 서비스 키 주석이 없어 ASIS 출처를 추적하지 못한 TOBE 엔드포인트", bare))


def _sql_gap(ctx: TraceContext, idx: TobeIndex, domain: str | None, res: TraceResult) -> None:
    statements = (ctx.index_data or {}).get("statements", {})
    asis = {k for k, v in statements.items() if not domain or f"server/{domain}/" in v.get("file", "")}
    referenced = {i for st in idx.statements.values() for i in st.as_is_ids}
    scoped_ref = {i for i in referenced if i in statements}
    res.facts.append(f"SQL: ASIS {len(asis)} — TOBE 문장 주석이 가리키는 것 {len(asis & scoped_ref)}")
    res.facts.append(_listing("ASIS에만 있는 SQL(어느 TOBE 문장 주석도 가리키지 않음)", list(asis - scoped_ref)))
    dangling = [i for i in referenced if i not in statements and not i.startswith("common.")]
    if dangling:
        res.unresolved.append(_listing("TOBE 문장 주석이 가리키는데 ASIS 색인에 없는 SQL id", dangling))
    no_ref = [st.key.split(".")[-2] + "." + st.id for st in idx.statements.values()
              if not st.as_is_ids and (not domain or Path(st.file).name[: len(domain)].lower() == domain)]
    if no_ref:
        res.unresolved.append(_listing("AS-IS 주석이 없어 ASIS 출처를 추적하지 못한 TOBE mapper 문장", no_ref))


def _api_gap(idx: TobeIndex, domain: str | None, res: TraceResult) -> None:
    ep_keys = {(ep.verb, ep.path) for ep in idx.endpoints}
    dangling = []
    for t in idx.tsx.values():
        if domain and _tsx_domain(t.file, idx) != domain:
            continue
        for obj, fn in t.api_calls:
            api = idx.api_fns.get((obj, fn))
            if api is None:
                dangling.append(f"{t.name}: {obj}.{fn} (api/*.ts에서 찾지 못함)")
            elif (api.verb, api.url) not in ep_keys:
                dangling.append(f"{t.name}: {obj}.{fn} → {api.verb} {api.url} (컨트롤러에 없음)")
    if dangling:
        res.unresolved.append(_listing("TSX가 부르는 API가 컨트롤러까지 이어지지 않음", dangling))


def trace_gap(ctx: TraceContext, tobe: Path | None = None, domain: str | None = None) -> TraceResult:
    res = TraceResult(
        command="trace-gap",
        description="ASIS에만 있는 것, TOBE에만 있는 것, 추적하지 못한 지점 전체",
        side="both",
        params={"domain": domain},
    )
    res.unresolved += ctx.unresolved
    idx = build_index(str(find_layout(tobe).root))
    if not idx.layout.usable:
        res.unresolved.append(f"TOBE 소스를 찾지 못함 ({idx.layout.root}) — --tobe로 프로젝트 루트(또는 frontend/src)를 지정")
        return res
    if not ctx.has_index:
        return res
    if domain and not re.fullmatch(r"[a-z][a-z0-9]{1,5}", domain):
        raise ValueError(f"--domain은 소문자 도메인 코드여야 합니다 (예: emp, sys, fnd): {domain}")
    _screen_gap(ctx, idx, domain, res)
    _service_gap(ctx, idx, domain, res)
    _sql_gap(ctx, idx, domain, res)
    _api_gap(idx, domain, res)
    res.evidence.append(f"TOBE 색인: TSX {len(idx.tsx)}, api 함수 {len(idx.api_fns)}, 엔드포인트 {len(idx.endpoints)}, mapper 문장 {len(idx.statements)} ({idx.layout.root})")
    return res


# --- trace-gap --stubs -------------------------------------------------------

_MSG_CALL_RE = re.compile(r"message\.(?:info|warning)\s*\(\s*([`'\"])(.*?)\1")
_SKIP_COMMENT_RE = re.compile(r"//\s*(\[E\d+(?:\]\s*[~∼-]\s*\[E\d+)?\s*생략\].*)")
_EVENT_COMMENT_RE = re.compile(r"(?://|\{/\*)\s*(\[E\d+[^\]]*\][^*]*)")
_IMPORT_RE = re.compile(r"import\s+(?!type\b)([^;]*?)\s+from\s+['\"]([^'\"]+)['\"]")
_HEADER_STEP_RE = re.compile(r"(?:1단계|다음 단계)\s*:\s*(.+)")
_ACTIONABLE_SKIP_RE = re.compile(r"다음 단계|2단계|1단계|아직 변환")


def _load_menu_lookup(ctx: TraceContext, layout: TobeLayout) -> dict[str, list[tuple[str, str, bool]]]:
    """화면 클래스명 → [(메뉴번호, 말단메뉴명, 활성여부), ...] 매핑을 만든다."""
    by_screen: dict[str, list[tuple[str, str, bool]]] = {}

    def _add(no: str, full_path: str, screen: str | None, use_str: str) -> None:
        if not screen:
            return
        leaf = full_path.split(">")[-1].strip()
        active = use_str.lower() == "true" and not leaf.startswith("(X)") and not leaf.startswith("(구)")
        entry = (no.strip(), leaf, active)
        lst = by_screen.setdefault(screen.strip(), [])
        if entry not in lst:
            lst.append(entry)

    tsv = layout.root / "docs" / "as-is" / "menus.tsv"
    if tsv.is_file():
        for line in tsv.read_text(encoding="utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) >= 4:
                _add(parts[0], parts[1], parts[2], parts[3])

    menus_md = layout.root / "docs" / "as-is" / "src" / "menus.md"
    if menus_md.is_file():
        row_re = re.compile(r"^\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$")
        link_re = re.compile(r"\[`([^`]+)`\]")
        for line in menus_md.read_text(encoding="utf-8", errors="replace").splitlines():
            m = row_re.match(line)
            if m:
                lk = link_re.search(m.group(4))
                _add(m.group(2), m.group(1), lk.group(1) if lk else None, m.group(3))

    for m in load_menus(ctx):
        _add(m.no, m.path, m.screen, m.use)

    return by_screen


def _symbol_uses_child(target_text: str, sym: str, child: str) -> bool:
    if sym == child or sym == Path(child).stem:
        return True
    m = re.search(rf"export\s+(?:const|function)\s+{re.escape(sym)}\b", target_text)
    if not m:
        return True
    rest = target_text[m.start() :]
    nxt = re.search(r"\nexport\s+(?:const|function|type|interface)\s+", rest[10:])
    block = rest[: nxt.start() + 10] if nxt else rest
    return child in block


def _build_reverse_imports(front: Path) -> tuple[set[str], dict[str, str], dict[str, Path], dict[str, list[tuple[str, list[str]]]]]:
    screens_file = front / "pages" / "screens.ts"
    reg_tabs: set[str] = set()
    if screens_file.is_file():
        cleaned = re.sub(r"//.*", "", screens_file.read_text(encoding="utf-8", errors="replace"))
        reg_tabs = set(re.findall(r"\b([A-Za-z0-9]+_Tab_[A-Za-z0-9_]+)\b", cleaned))

    file_texts: dict[str, str] = {}
    file_paths: dict[str, Path] = {}
    for p in sorted(front.rglob("*.tsx")):
        if p.name == "screens.ts":
            continue
        file_texts[p.stem] = p.read_text(encoding="utf-8", errors="replace")
        file_paths.setdefault(p.stem, p)

    rev: dict[str, list[tuple[str, list[str]]]] = {}
    for stem, text in file_texts.items():
        for m in _IMPORT_RE.finditer(text):
            spec, src = m.group(1), m.group(2)
            target = Path(src).stem
            if target not in file_texts:
                continue
            syms = [s.strip().split(" as ")[0].strip() for s in re.sub(r"[{}]", "", spec).split(",") if s.strip()]
            rev.setdefault(target, []).append((stem, syms))

    return reg_tabs, file_texts, file_paths, rev


def _find_opening_tabs(
    stem: str,
    reg_tabs: set[str],
    file_texts: dict[str, str],
    rev: dict[str, list[tuple[str, list[str]]]],
) -> list[str]:
    if stem in reg_tabs:
        return [stem]
    visited: dict[str, int] = {stem: 0}
    q: deque[tuple[str, int, str | None]] = deque([(stem, 0, None)])
    tabs: dict[str, int] = {}
    fallback_tabs: dict[str, int] = {}
    while q:
        cur, dist, prev_child = q.popleft()
        cur_text = file_texts.get(cur, "")
        check_target = prev_child if prev_child is not None else cur
        for parent, syms in rev.get(cur, ()):
            if cur not in syms and not any(_symbol_uses_child(cur_text, s, check_target) for s in syms):
                continue
            if parent in visited:
                continue
            visited[parent] = dist + 1
            if parent in reg_tabs:
                tabs[parent] = dist + 1
            else:
                if "_Tab_" in parent:
                    fallback_tabs[parent] = dist + 1
                q.append((parent, dist + 1, cur))
    chosen = tabs or fallback_tabs
    if not chosen and "_Tab_" in stem:
        return [stem]
    return sorted(chosen, key=lambda k: (chosen[k], k))


def _nearest_event_comment(lines: list[str], line_no: int) -> str:
    """line_no(1-based) 위쪽에서 가장 가까운 [E…] 주석(없으면 바로 위 // 주석)을 찾는다."""
    for i in range(line_no - 1, max(-1, line_no - 18), -1):
        s = lines[i].strip()
        if i < line_no - 1 and (
            not s
            or (s.startswith("const ") and "=" in s)
            or s.startswith("export const ")
            or (s.startswith("<Button") and "onClick" in s)
        ):
            if s.startswith(("const ", "export const ")):
                m_same = _EVENT_COMMENT_RE.search(lines[i])
                if m_same:
                    return m_same.group(1).strip()
                for j in range(i - 1, max(-1, i - 4), -1):
                    if not lines[j].strip():
                        break
                    mj = _EVENT_COMMENT_RE.search(lines[j])
                    if mj:
                        return mj.group(1).strip()
            break
        m = _EVENT_COMMENT_RE.search(lines[i])
        if m:
            return m.group(1).strip()
    if line_no >= 2:
        prev = lines[line_no - 2].strip()
        if prev.startswith("//"):
            return prev.removeprefix("//").strip()
    return "-"


def _pick_menu(tab: str, menu_lookup: dict[str, list[tuple[str, str, bool]]], file_texts: dict[str, str]) -> tuple[str, str]:
    """tab 클래스에 대응하는 (메뉴번호, 말단메뉴명)을 돌려준다."""
    entries = menu_lookup.get(tab, [])
    head_text = file_texts.get(tab, "")[:2000]
    head_nos = re.findall(r"\[(\d{3,4})\]", head_text.split("*/")[0] if "*/" in head_text else head_text)
    if entries:
        for hno in head_nos:
            for no, leaf, active in entries:
                if no == hno and active:
                    return no, leaf
        for no, leaf, active in entries:
            if active:
                return no, leaf
        return entries[0][0], entries[0][1]
    if head_nos:
        return head_nos[0], ""
    return "", ""


def trace_stubs(
    ctx: TraceContext,
    tobe: Path | None = None,
    domain: str | None = None,
    pattern: str | None = None,
) -> TraceResult:
    """TOBE frontend/src에서 미연결 자리(다음 단계 안내·[E… 생략]·머리 주석)를 수집한다."""
    layout = find_layout(tobe)
    res = TraceResult(
        command="trace-gap --stubs",
        description="TOBE frontend/src의 미연결 자리(다음 단계 안내·[E… 생략]·화면 머리 주석) 수집",
        side="tobe",
        params={"domain": domain, "pattern": pattern or DEFAULT_STUB_PATTERN},
    )
    if not layout.frontend.is_dir():
        res.unresolved.append(f"TOBE frontend/src를 찾지 못함 ({layout.frontend}) — --tobe로 프로젝트 루트(또는 frontend/src)를 지정")
        return res
    if domain and not re.fullmatch(r"[a-z][a-z0-9]{1,5}", domain):
        raise ValueError(f"--domain은 소문자 도메인 코드여야 합니다 (예: emp, sys, fnd): {domain}")

    kw_re = re.compile(pattern or DEFAULT_STUB_PATTERN)
    menu_lookup = _load_menu_lookup(ctx, layout)
    reg_tabs, file_texts, file_paths, rev = _build_reverse_imports(layout.frontend)

    stub_rows: list[dict[str, str]] = []
    skip_rows: list[dict[str, str]] = []
    header_only_rows: list[str] = []

    for stem, p in sorted(file_paths.items(), key=lambda kv: str(kv[1])):
        rel_path = str(p.relative_to(layout.frontend))
        text = file_texts[stem]
        lines = text.splitlines()
        tabs = _find_opening_tabs(stem, reg_tabs, file_texts, rev)

        if domain:
            file_dom = rel_path.split("/")[1] if rel_path.startswith("pages/") and len(rel_path.split("/")) > 2 else ""
            tab_doms = {t[: len(domain)].lower() for t in tabs}
            if file_dom != domain and domain not in tab_doms:
                continue

        tab0 = tabs[0] if tabs else ""
        extra = len(tabs) - 1 if len(tabs) > 1 else 0
        no, leaf = _pick_menu(tab0, menu_lookup, file_texts) if tab0 else ("", "")
        tab_display = f"{tab0} 외 {extra}" if extra > 0 else (tab0 or "-")
        tab_code_display = f"`{tab0}` 외 {extra}" if extra > 0 else (f"`{tab0}`" if tab0 else f"`{stem}`")
        menu_col = f"#{no} ({tab_display})" if no else (f"({tab_display})" if tab0 else "-")
        menu_checklist = f"{leaf} #{no} ({tab_code_display})".strip() if no else f"({tab_code_display})"

        # 템플릿 헬퍼 함수 (예: const next = (name: string) => () => message.info(`${name} 창은 다음 단계에서 제공됩니다.`))
        helper_templates: dict[str, tuple[int, str]] = {}
        for idx, line in enumerate(lines, 1):
            hm = re.match(r"^\s*const\s+(\w+)\s*=\s*\([^)]*\)\s*=>.*message\.(?:info|warning)\s*\(\s*`([^`]+)`\s*\)", line)
            if hm and "${" in hm.group(2) and kw_re.search(hm.group(2)):
                helper_templates[hm.group(1)] = (idx, hm.group(2))

        file_has_body_stub = False
        for idx, line in enumerate(lines, 1):
            if idx in {ln for ln, _ in helper_templates.values()}:
                continue
            # 1) 템플릿 헬퍼 호출
            matched_helper = False
            for hname, (_hln, tmpl) in helper_templates.items():
                cm = re.search(rf"\b{re.escape(hname)}\s*\(\s*(['\"])(.*?)\1\s*\)", line)
                if cm:
                    msg_txt = re.sub(r"\$\{[^}]+\}", cm.group(2), tmpl)
                    ev = _nearest_event_comment(lines, idx)
                    stub_rows.append({
                        "loc": f"{rel_path}:{idx}",
                        "msg": msg_txt,
                        "event": ev,
                        "tab": tab_display,
                        "menu": menu_col,
                        "checklist": f"- [ ] `{rel_path}:{idx}` — {menu_checklist} — {msg_txt}",
                    })
                    file_has_body_stub = True
                    matched_helper = True
            if matched_helper:
                continue

            # 2) 직접 message.info / message.warning 호출
            for m in _MSG_CALL_RE.finditer(line):
                msg_txt = m.group(2)
                if kw_re.search(msg_txt):
                    ev = _nearest_event_comment(lines, idx)
                    stub_rows.append({
                        "loc": f"{rel_path}:{idx}",
                        "msg": msg_txt,
                        "event": ev,
                        "tab": tab_display,
                        "menu": menu_col,
                        "checklist": f"- [ ] `{rel_path}:{idx}` — {menu_checklist} — {msg_txt}",
                    })
                    file_has_body_stub = True

            # 3) // [E\d+ 생략] 주석
            sm = _SKIP_COMMENT_RE.search(line)
            if sm:
                comment_txt = sm.group(1).strip()
                row_data = {
                    "loc": f"{rel_path}:{idx}",
                    "msg": comment_txt,
                    "event": comment_txt.split("]")[0] + "]" if "]" in comment_txt else comment_txt,
                    "tab": tab_display,
                    "menu": menu_col,
                    "checklist": f"- [ ] `{rel_path}:{idx}` — {menu_checklist} — {comment_txt}",
                }
                if (
                    _ACTIONABLE_SKIP_RE.search(comment_txt)
                    and "원본" not in comment_txt
                    and "도달 불가" not in comment_txt
                    and "없다" not in comment_txt
                ):
                    stub_rows.append(row_data)
                    file_has_body_stub = True
                else:
                    skip_rows.append(row_data)

        # 4) 머리 주석의 1단계: / 다음 단계: 줄
        head_block = text.split("*/")[0] if "*/" in text[:4000] else ""
        for idx, line in enumerate(head_block.splitlines(), 1):
            hm = _HEADER_STEP_RE.search(line)
            if hm:
                step_txt = line.strip().lstrip("*").strip()
                if step_txt.startswith("다음 단계: 없음"):
                    continue
                tag = "본문 안내 없음(머리만 남음)" if not file_has_body_stub else "본문 안내 있음"
                header_only_rows.append(f"`{rel_path}:{idx}` ({menu_col}) [{tag}] — {step_txt}")

    # 결과 조립
    res.facts.append(
        f"미연결 안내(stub) {len(stub_rows)}건, [E… 생략] 주석(도달 불가·원본 미연결 등) {len(skip_rows)}건, 머리 주석(1단계/다음 단계) {len(header_only_rows)}건"
    )
    if stub_rows:
        tbl = [
            "미연결 자리 표 (`message.info/warning` 안내 및 단계 생략):",
            "  | 파일:줄 | 문구 | 가장 가까운 [E…] 주석 | 여는 화면 | 메뉴 번호 |",
            "  |:---|:---|:---|:---|:---|",
        ]
        for r in stub_rows:
            ev_short = r["event"] if len(r["event"]) <= 70 else r["event"][:67] + "..."
            tbl.append(f"  | `{r['loc']}` | {r['msg']} | {ev_short} | `{r['tab']}` | {r['menu']} |")
        res.facts.append("\n".join(tbl))

        chk = ["13-누락대장 교체용 목록 (`- [ ] 파일:줄 — 메뉴명 #번호 (Tab 클래스)`):"]
        for r in stub_rows:
            chk.append(f"  {r['checklist']}")
        res.facts.append("\n".join(chk))

    if skip_rows:
        sk_lines = [f"[E… 생략] 주석 ({len(skip_rows)}건):"]
        for r in skip_rows:
            sk_lines.append(f"  - `{r['loc']}` ({r['menu']}) — {r['msg']}")
        res.facts.append("\n".join(sk_lines))

    if header_only_rows:
        hd_lines = [f"화면 머리에 남은 `1단계:` / `다음 단계:` 주석 ({len(header_only_rows)}건):"]
        for h in header_only_rows:
            hd_lines.append(f"  - {h}")
        res.facts.append("\n".join(hd_lines))

    res.evidence.append(f"TOBE frontend/src 스캔: TSX {len(file_paths)}개, 등록된 _Tab_ 화면 {len(reg_tabs)}개 ({layout.frontend})")
    return res
