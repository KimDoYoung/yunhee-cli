"""이벤트 분석 문서 자동 생성 도구 (`biz-event-new`).

화면 번호와 AS-IS/TOBE 정적 분석 색인을 기반으로
이벤트 분석 마크다운 문서 뼈대(메뉴 줄, 따라 하기 이벤트 단계, DB 테이블, 권한 주의사항, yaml 시나리오, 근거 절)를 생성한다.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yunhee.tools.biz.authz import parse_api_ts
from yunhee.tools.biz.endpoints import collect_endpoints
from yunhee.tools.trace.tobe import find_layout


@dataclass
class ScreenMeta:
    menu_no: str
    menu_path: str
    class_name: str
    rel_doc_path: str
    events: list[dict[str, str]] = field(default_factory=list)  # [{"code": "E1", "label": "[조회]", "text": "..."}]
    max_event: str = "E0"
    methods_line_range: str = ""
    services: list[str] = field(default_factory=list)
    tables: list[str] = field(default_factory=list)
    tsx_file: str | None = None
    api_fns: list[str] = field(default_factory=list)


def _parse_menus_md(root_dir: Path) -> dict[str, dict[str, str]]:
    """docs/as-is/src/menus.md 파싱 -> {menu_no: {menu_path, class_name, rel_doc_path}}."""
    menus_file = root_dir / "docs" / "as-is" / "src" / "menus.md"
    if not menus_file.is_file():
        return {}

    res: dict[str, dict[str, str]] = {}
    pattern = re.compile(
        r"\|\s*([^|]+?)\s*\|\s*(\d{3,5})\s*\|\s*(?:true|false)\s*\|\s*\[`?(\w+)`?\]\(([^)]+)\)"
    )
    for line in menus_file.read_text(encoding="utf-8", errors="replace").splitlines():
        m = pattern.search(line)
        if m:
            path, no, cls, rel = m.group(1).strip(), m.group(2).strip(), m.group(3).strip(), m.group(4).strip()
            res[no] = {
                "menu_path": path,
                "class_name": cls,
                "rel_doc_path": rel,
            }
    return res


def _check_company_menus(
    company_code: str,
    menu_nos: list[str],
    db_name: str | None = None,
) -> set[str]:
    """회사 메뉴 여부를 DB(sys03_company_menu)에서 판정하여 포함된 menu_no set을 반환한다."""
    if not company_code or not menu_nos:
        return set()

    try:
        import psycopg
        from psycopg.rows import dict_row

        from yunhee.tools.sql_runner import get_connection_string

        db_url = get_connection_string(db_name)
        if not db_url:
            return set()

        with psycopg.connect(db_url, autocommit=False) as conn:
            conn.read_only = True
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT sys01_company_id FROM sys01_company WHERE sys01_loc_nm = %s LIMIT 1;",
                    (company_code,),
                )
                comp = cur.fetchone()
                if not comp:
                    return set()
                cid = comp["sys01_company_id"]

                cur.execute(
                    """
                    SELECT m.sys06_menu_no
                    FROM sys06_menu m
                    JOIN sys03_company_menu c ON c.sys03_menu_id = m.sys06_menu_id
                    WHERE c.sys03_company_id = %s AND m.sys06_menu_no = ANY(%s);
                    """,
                    (cid, menu_nos),
                )
                return {str(r["sys06_menu_no"]).strip() for r in cur.fetchall() if r.get("sys06_menu_no")}
    except Exception:  # noqa: BLE001
        return set()


def _parse_screen_doc(doc_path: Path, meta: ScreenMeta) -> None:
    """AS-IS 화면 마크다운 문서(docs/as-is/src/.../<클래스>.md)를 파싱하여 메타데이터를 채운다."""
    if not doc_path.is_file():
        return

    content = doc_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()

    section = ""
    event_max = 0
    all_lines: list[int] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            continue
        if stripped.startswith("### "):
            section = stripped[4:].strip()
            continue
        if stripped.startswith("#### "):
            section = stripped[5:].strip()
            continue

        if section == "이벤트":
            # [E1] retrieveButton[조회].Select (L76) → retrieve()
            m = re.search(r"\[E(\d+)\]\s*(.*)", stripped)
            if m:
                e_num = int(m.group(1))
                rest = m.group(2)
                event_max = max(event_max, e_num)

                if e_num > 0:
                    # 버튼 레이블 추출 ([조회], [등록] 등)
                    btn_m = re.findall(r"\[([^E\d][^\]]*)\]", rest)
                    label = f"[{btn_m[0]}]" if btn_m else rest.split(".")[0].strip()
                    meta.events.append({
                        "code": f"E{e_num}",
                        "label": label,
                        "text": rest,
                    })

        elif section == "메서드":
            # | public retrieve() | L130-141 | 생성자,E1 | 서비스 ... | 업무 |
            if "|" in stripped and not stripped.startswith("| ---"):
                parts = [p.strip() for p in stripped.split("|")]
                if len(parts) >= 3:
                    range_m = re.findall(r"L(\d+)(?:-(\d+))?", parts[2])
                    for start, end in range_m:
                        if start:
                            all_lines.append(int(start))
                        if end:
                            all_lines.append(int(end))

        elif section == "서비스":
            # | `pay.Pay34_WorkTimeConfig.delete` | ... | [`Pay34_WorkTimeConfig.java:49`](...) | ... |
            if "|" in stripped and not stripped.startswith("|:---") and not stripped.startswith("| 서비스"):
                parts = [p.strip() for p in stripped.split("|")]
                if len(parts) >= 4:
                    srv = re.sub(r"[`']", "", parts[1])
                    server_part = parts[3]
                    line_m = re.search(r":(\d+)", server_part)
                    line_suffix = f" L{line_m.group(1)}" if line_m else ""
                    if srv:
                        # 짧은 이름: srv에서 마지막 메서드명 또는 클래스.메서드
                        meta.services.append(f"{srv}{line_suffix}")

        elif section == "테이블":
            # [`pay34_work_time_config`](...)
            for tbl in re.findall(r"\[`?([a-zA-Z0-9_]+)`?\]", stripped):
                if tbl not in meta.tables:
                    meta.tables.append(tbl)

    meta.max_event = f"E{event_max}"
    if all_lines:
        meta.methods_line_range = f"L{min(all_lines)}-{max(all_lines)}"


def _find_tobe_page(root_dir: Path, class_name: str) -> Path | None:
    """frontend/src/pages/**/<클래스>.tsx 파일을 검색한다."""
    layout = find_layout(root_dir)
    if not layout.pages_dir.is_dir():
        # 루트 기준 fallback
        cands = list(root_dir.rglob(f"{class_name}.tsx"))
        return cands[0] if cands else None

    cands = list(layout.pages_dir.rglob(f"{class_name}.tsx"))
    return cands[0] if cands else None


def _extract_tobe_api_calls(tsx_path: Path, root_dir: Path) -> list[tuple[str, str]]:
    """TSX 파일에서 호출하는 api 함수를 파싱하여 (METHOD, URL) 목록을 추출한다."""
    if not tsx_path.is_file():
        return []

    layout = find_layout(root_dir)
    api_dir = layout.api_dir
    api_fn_map: dict[str, tuple[str, str]] = {}  # fn_name -> (method, url)
    if api_dir.is_dir():
        for api_file in api_dir.glob("*.ts"):
            txt = api_file.read_text(encoding="utf-8", errors="replace")
            for f in parse_api_ts(txt, str(api_file)):
                if f.url and f.verb:
                    verb_upper = f.verb.upper()
                    api_fn_map[f.name] = (verb_upper, f.url)
                    if f.obj:
                        api_fn_map[f"{f.obj}.{f.name}"] = (verb_upper, f.url)

    tsx_txt = tsx_path.read_text(encoding="utf-8", errors="replace")
    calls: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for fn_name, (method, url) in api_fn_map.items():
        if re.search(r"\b" + re.escape(fn_name) + r"\b", tsx_txt):
            item = (method, url)
            if item not in seen:
                seen.add(item)
                calls.append(item)

    return calls


def generate_biz_event_doc(
    event_id: str,
    screens: list[str],
    title: str = "",
    company: str | None = None,
    force: bool = False,
    out: str | None = None,
    root_dir: Path | None = None,
    db_name: str | None = None,
) -> tuple[Path, str]:
    """이벤트 분석 문서를 생성하고 대상 파일 경로와 내용을 반환한다."""
    if root_dir is None:
        root_dir = Path.cwd()

    event_id = event_id.strip()
    dom = event_id.split("-")[0].upper()

    title_slug = re.sub(r"\s+", "", title)[:10] if title else event_id
    if out:
        out_path = Path(out).resolve() if Path(out).is_absolute() else (root_dir / out).resolve()
    else:
        out_path = root_dir / "docs" / "2-업무분석" / "biz-event" / dom / f"{event_id}-{title_slug}.md"

    if out_path.exists() and not force:
        raise FileExistsError(f"파일이 이미 존재합니다: {out_path} (--force 로 덮어쓰기 가능)")

    # 1. 메뉴 및 화면 메타 파싱
    menus_dict = _parse_menus_md(root_dir)
    company_menus: set[str] = set()
    if company:
        company_menus = _check_company_menus(company, screens, db_name)

    screens_meta: list[ScreenMeta] = []
    for s_no in screens:
        s_no = s_no.strip()
        menu_info = menus_dict.get(s_no, {})
        menu_path = menu_info.get("menu_path", f"메뉴 #{s_no}")
        class_name = menu_info.get("class_name", f"Screen{s_no}")
        rel_path = menu_info.get("rel_doc_path", "")

        meta = ScreenMeta(
            menu_no=s_no,
            menu_path=menu_path,
            class_name=class_name,
            rel_doc_path=rel_path,
        )

        if rel_path:
            doc_file = root_dir / "docs" / "as-is" / "src" / rel_path
            _parse_screen_doc(doc_file, meta)

        tsx_path = _find_tobe_page(root_dir, class_name)
        if tsx_path:
            meta.tsx_file = tsx_path.name

        screens_meta.append(meta)

    # 2. 메뉴 줄 구성
    menu_items: list[str] = []
    for sm in screens_meta:
        m_item = f"#{sm.menu_no} {sm.menu_path}"
        if company:
            has_menu = sm.menu_no in company_menus
            m_item += f" ({company} 메뉴 있음)" if has_menu else f" ({company} 메뉴 없음)"
        menu_items.append(m_item)
    menu_line = ", ".join(menu_items)

    # 3. 따라 하기 (이벤트 E1..En)
    steps_lines: list[str] = []
    step_no = 1
    for sm in screens_meta:
        for ev in sm.events:
            steps_lines.append(f"| {step_no} | TODO | #{sm.menu_no} | {ev['label']} | TODO |")
            step_no += 1
    if not steps_lines:
        for sm in screens_meta:
            steps_lines.append(f"| {step_no} | TODO | #{sm.menu_no} | TODO | TODO |")
            step_no += 1

    # 4. DB에 남는 것
    db_tables: list[str] = []
    for sm in screens_meta:
        for tbl in sm.tables:
            if tbl not in db_tables:
                db_tables.append(tbl)
    db_lines: list[str] = []
    if db_tables:
        for tbl in db_tables:
            db_lines.append(f"| `{tbl}` | TODO | TODO |")
    else:
        db_lines.append("| TODO | TODO | TODO |")

    # 5. TOBE 엔드포인트 분석
    tobe_calls: list[tuple[str, str]] = []
    for sm in screens_meta:
        tsx_path = _find_tobe_page(root_dir, sm.class_name)
        if tsx_path:
            tobe_calls.extend(_extract_tobe_api_calls(tsx_path, root_dir))

    # 도메인 기준 collect_endpoints 수집
    dom_lower = dom.lower()
    endpoints_all: list[dict[str, Any]] = []
    try:
        endpoints_all = collect_endpoints(target=dom_lower, root_dir=root_dir)
    except Exception:  # noqa: BLE001, S110
        pass

    # URL 정규화 매칭용 헬퍼
    def _match_endpoint(call_method: str, call_url: str, ep: dict[str, Any]) -> bool:
        if ep["method"] != call_method:
            return False
        ep_p = re.sub(r"\{[^}]+\}", "[^/]+", ep["path"])
        call_p = re.sub(r":\w+", "[^/]+", call_url.split("?")[0])
        return bool(re.fullmatch(ep_p, call_p) or ep["path"] == call_url.split("?")[0])

    matched_endpoints: list[dict[str, Any]] = []
    seen_eps: set[str] = set()
    for method, url in tobe_calls:
        for ep in endpoints_all:
            if _match_endpoint(method, url, ep):
                key = f"{ep['method']} {ep['path']}"
                if key not in seen_eps:
                    seen_eps.add(key)
                    matched_endpoints.append(ep)

    # 6. 업무 규칙 · 주의 (권한 검사 확인)
    warn_lines: list[str] = []
    for ep in matched_endpoints:
        if ep["method"] in ("POST", "PUT", "DELETE", "PATCH"):
            guards = ep.get("guards", [])
            # ⚠없음 이거나 회사 단독인 경우
            if guards == ["⚠없음"] or guards == ["회사"]:
                warn_lines.append(f"- 권한 검사 확인: {ep['method']} {ep['path']} (서비스 {ep['service']})")

    rule_lines = ["- TODO"]
    rule_lines.extend(warn_lines)

    # 7. 시나리오 데이터 (YAML steps)
    yaml_steps: list[str] = []
    y_step_no = 1
    for ep in matched_endpoints:
        yaml_steps.append(f"  - no: {y_step_no}")
        yaml_steps.append(f"    api: {ep['method']} {ep['path']}")
        body = ep.get("body", {})
        b_type = body.get("type")
        fields = [f["name"] for f in body.get("fields", []) if isinstance(f, dict) and "name" in f]

        if fields:
            fields_str = ", ".join(fields)
            if body.get("list"):
                yaml_steps.append(f"    body: [{{{fields_str}}}]")
            else:
                yaml_steps.append(f"    body: {{{fields_str}}}")
        elif b_type and ("List" in str(b_type) or "[]" in str(b_type)):
            yaml_steps.append("    body: [<id>]")

        y_step_no += 1

    if not yaml_steps:
        yaml_steps = [
            "  - no: 1",
            "    api: TODO",
        ]

    # 8. 근거 (AS-IS · TOBE)
    as_is_parts: list[str] = []
    for sm in screens_meta:
        part = sm.class_name
        detail = []
        if sm.max_event:
            detail.append(f"E0~{sm.max_event}")
        if sm.methods_line_range:
            detail.append(f"메서드 {sm.methods_line_range}")
        if detail:
            part += f"({', '.join(detail)})"

        if sm.services:
            srv_str = "·".join(sm.services)
            part += f", 서버 {srv_str}"
        as_is_parts.append(part)
    as_is_evidence = ", ".join(as_is_parts) if as_is_parts else "TODO"

    # TOBE 컨트롤러, 서비스, tsx
    ctrl_map: dict[str, list[str]] = {}
    services_set: list[str] = []
    for ep in matched_endpoints:
        ctrl_file = ep.get("file", "").split(":")[0]
        ctrl_name = ctrl_file.replace(".java", "")
        if ctrl_name:
            ctrl_map.setdefault(ctrl_name, []).append(f"{ep['path']} {ep['method']}")
        srv_name = ep.get("service", "").split(".")[0]
        if srv_name and srv_name not in services_set:
            services_set.append(srv_name)

    ctrl_parts: list[str] = []
    for c_name, paths in ctrl_map.items():
        # path별 method 묶기
        p_to_m: dict[str, list[str]] = {}
        for item in paths:
            p, m = item.rsplit(" ", 1)
            p_to_m.setdefault(p, []).append(m)
        pm_strs = [f"{p} {'·'.join(m_list)}" for p, m_list in p_to_m.items()]
        ctrl_parts.append(f"{c_name}({', '.join(pm_strs)})")

    tsx_parts = [sm.tsx_file for sm in screens_meta if sm.tsx_file]

    tobe_components = []
    if ctrl_parts:
        tobe_components.append(", ".join(ctrl_parts))
    if services_set:
        tobe_components.append(", ".join(services_set))
    if tsx_parts:
        tobe_components.append(", ".join(tsx_parts))

    tobe_evidence = ", ".join(tobe_components) if tobe_components else "TODO"

    # 9. 최종 마크다운 조립
    doc_lines = [
        f"# {event_id} {title}".strip(),
        "",
        "> **한 줄 요약** — TODO",
        "",
        "| 항목 | 내용 |",
        "|:---|:---|",
        "| 누가 | TODO |",
        "| 언제 | TODO |",
        "| 먼저 있어야 하는 것 | TODO |",
        "| 다음 이벤트 | TODO |",
        "| 실제 실행 | TODO |",
        f"| 메뉴 | {menu_line} |",
        "",
        "## 따라 하기",
        "| 단계 | 누가 | 화면 | 누르는 것 · 입력하는 것 | 화면에 보이는 결과 |",
        "|:---:|:---|:---|:---|:---|",
        *steps_lines,
        "",
        "## DB에 남는 것",
        "| 테이블 | 무엇 | 실행 |",
        "|:---|:---|:---|",
        *db_lines,
        "",
        "## 업무 규칙 · 주의",
        *rule_lines,
        "",
        "<details><summary>시나리오 데이터 (자동 시험용)</summary>",
        "",
        "```yaml",
        f"id: {event_id}",
        "steps:",
        *yaml_steps,
        "```",
        "</details>",
        "",
        "<details><summary>근거 (AS-IS · TOBE)</summary>",
        "",
        f"- AS-IS: {as_is_evidence}",
        f"- TOBE: {tobe_evidence}",
        "</details>",
        "",
    ]

    content = "\n".join(doc_lines)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")
    return out_path, content
