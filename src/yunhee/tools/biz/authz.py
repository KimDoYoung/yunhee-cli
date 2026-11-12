"""권한 훑기 도구 (`biz-authz`).

낮은 권한(사원) 계정으로 도메인 내의 엔드포인트들을 안전하게 프로빙하여,
관리자 화면의 API가 사원에게 열려 있는지(BOLA/IDOR 및 인가 누락) 판정한다.
"""

from __future__ import annotations

import datetime
import json
import re
from pathlib import Path
from typing import Any

from yunhee.tools import api_client
from yunhee.tools.base import ToolResult
from yunhee.tools.trace.tobe import find_layout, normalize_url, parse_api_ts


def resolve_user_menus(
    as_user: str,
    company: str,
    base_url: str | None = None,
    password: str | None = None,
    db_name: str | None = None,
) -> set[str]:
    """로그인 사원이 접근 가능한 메뉴 번호 집합을 조회한다."""
    menus: set[str] = set()

    # 1. /api/v1/sys/menus API 호출 시도
    kw: dict[str, Any] = {"as_role": as_user, "company_code": company}
    if base_url:
        kw["base_url"] = base_url
    if password:
        kw["password"] = password

    res = api_client.request_api("GET", "/api/v1/sys/menus", **kw)
    if res.ok and res.data:
        try:
            raw_text = res.data.get("text", "")
            data_obj = json.loads(raw_text)
            items = data_obj.get("data") if isinstance(data_obj, dict) else data_obj

            def _walk(node: Any) -> None:
                if isinstance(node, dict):
                    if node.get("menuNo"):
                        menus.add(str(node["menuNo"]).strip())
                    for v in node.values():
                        _walk(v)
                elif isinstance(node, list):
                    for elem in node:
                        _walk(elem)

            _walk(items)
            if menus:
                return menus
        except Exception:  # noqa: BLE001, S110
            pass

    # 2. DB fallback (sys05_user_role -> sys07_role_menu -> sys06_menu)
    try:
        import psycopg
        from psycopg.rows import dict_row

        from yunhee.tools.sql_runner import get_connection_string

        db_url = get_connection_string(db_name)
        if db_url:
            with psycopg.connect(db_url, autocommit=False) as conn:
                conn.read_only = True
                with conn.cursor(row_factory=dict_row) as cur:
                    cur.execute(
                        """
                        SELECT DISTINCT m.sys06_menu_no
                        FROM emp01_person p
                        JOIN sys05_user_role ur ON ur.sys05_user_id = p.emp01_person_id
                        JOIN sys07_role_menu rm ON rm.sys07_role_id = ur.sys05_role_id AND rm.sys07_use_yn = 'true'
                        JOIN sys06_menu m ON m.sys06_menu_id = rm.sys07_menu_id
                        WHERE p.emp01_emp_no = %s OR p.emp01_person_id::text = %s;
                        """,
                        (as_user, as_user),
                    )
                    for r in cur.fetchall():
                        if r.get("sys06_menu_no"):
                            menus.add(str(r["sys06_menu_no"]).strip())
    except Exception:  # noqa: BLE001, S110
        pass

    return menus


def build_url_menu_map(root_dir: Path) -> dict[str, set[str]]:
    """프론트엔드 API 함수 및 화면 TSX를 역추적하여 URL -> 허용 메뉴 번호 매핑을 구축한다."""
    url_to_menus: dict[str, set[str]] = {}

    layout = find_layout(root_dir)
    # 1. docs/as-is/src/menus.md 파싱 (| 메뉴 | # | 사용 | [`클래스`](…) |)
    menus_md = root_dir / "docs" / "as-is" / "src" / "menus.md"
    class_to_menu: dict[str, str] = {}
    if menus_md.is_file():
        text = menus_md.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            # | 메뉴 경로 | 1002 | true | [`Dcr01_Tab_DcrUser`](...) |
            m = re.search(r"\|\s*([^|]+?)\s*\|\s*(\d{3,5})\s*\|\s*(?:true|false)\s*\|\s*\[`(\w+)`\]", line)
            if m:
                menu_no = m.group(2).strip()
                cls_name = m.group(3).strip()
                class_to_menu[cls_name] = menu_no

    # 2. frontend/src/api/*.ts 파싱: fn_name -> normalized_url
    short_fn_to_urls: dict[str, list[str]] = {}
    if layout.api_dir.is_dir():
        for api_file in layout.api_dir.glob("*.ts"):
            txt = api_file.read_text(encoding="utf-8", errors="replace")
            fns = parse_api_ts(txt, str(api_file))
            for f in fns:
                if f.url:
                    short_fn_to_urls.setdefault(f.name, []).append(f.url)
                    if f.obj:
                        short_fn_to_urls.setdefault(f"{f.obj}.{f.name}", []).append(f.url)

    # 3. frontend/src/pages/**/*.tsx 파싱: 각 페이지가 호출하는 URL 매핑
    if layout.pages_dir.is_dir():
        for page_file in layout.pages_dir.rglob("*.tsx"):
            cls_stem = page_file.stem
            menu_no = class_to_menu.get(cls_stem)
            if not menu_no:
                continue

            page_txt = page_file.read_text(encoding="utf-8", errors="replace")
            page_words = set(re.findall(r"\b[A-Za-z_]\w*\b", page_txt))
            for short_fn in page_words.intersection(short_fn_to_urls.keys()):
                for u in short_fn_to_urls[short_fn]:
                    url_to_menus.setdefault(u, set()).add(menu_no)

    return url_to_menus


def _make_dummy_param(p_type: str) -> str:
    t = p_type.lower()
    if "date" in t:
        return datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    if "int" in t or "long" in t:
        return "1"
    return ""


def run_authz(
    endpoints: list[dict[str, Any]],
    as_user: str,
    company: str,
    password: str | None = None,
    probe_write: bool = False,
    probe_delete: bool = False,
    common_params: dict[str, str] | None = None,
    url_menu_map: dict[str, set[str]] | None = None,
    user_menu_set: set[str] | None = None,
    root_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """엔드포인트 목록에 대해 낮은 권한 계정으로 인가 상태를 확인한다."""
    if root_dir is None:
        root_dir = find_layout().root

    if url_menu_map is None:
        url_menu_map = build_url_menu_map(root_dir)

    if user_menu_set is None:
        user_menu_set = resolve_user_menus(as_user, company, password=password)

    results: list[dict[str, Any]] = []
    common_params = common_params or {}

    for ep in endpoints:
        verb = ep["method"].upper()
        raw_path = ep["path"]
        guards_str = ep.get("guard_str", "—")

        # 1. 쓰기 엔드포인트 필터링
        is_write = verb in ("POST", "PUT", "DELETE", "PATCH")
        if is_write and not probe_write:
            continue
        if verb == "DELETE" and not probe_delete:
            continue

        # 2. 경로 변수 처리
        has_path_var = "{" in raw_path
        if not is_write and has_path_var:
            # GET 경로 변수는 기본 스킵
            continue

        call_path = raw_path
        if is_write and has_path_var:
            # 쓰기는 경로 변수를 0(더미 ID)으로 치환
            call_path = re.sub(r"\{[^}/]*\}", "0", raw_path)

        # 3. 쿼리 / 본문 준비
        req_params: dict[str, str] = {}
        json_body: Any = None

        if not is_write:
            for q in ep.get("query", []):
                q_name = q["name"]
                if q_name in common_params:
                    req_params[q_name] = common_params[q_name]
                elif q["required"] or "date" in q["type"].lower() or "date" in q_name.lower():
                    req_params[q_name] = _make_dummy_param(q["type"])
        else:
            b_info = ep.get("body", {})
            if b_info.get("list"):
                json_body = []
            else:
                json_body = {}

        # 4. API 요청
        kw: dict[str, Any] = {
            "as_role": as_user,
            "company_code": company,
            "auto_login": True,
        }
        if password:
            kw["password"] = password
        if req_params:
            kw["params"] = req_params
        if json_body is not None:
            kw["json_body"] = json_body

        res: ToolResult = api_client.request_api(verb, call_path, **kw)

        # 5. 결과 요약 문자열 및 판정 추출
        summary = ""
        if res.data and isinstance(res.data, dict) and "summary" in res.data:
            summary = res.data["summary"]
        elif res.error:
            summary = res.error

        norm_url = normalize_url(raw_path)
        associated_menus = url_menu_map.get(norm_url, set())

        # 판정 로직
        res_display = ""
        verdict = ""

        if not is_write:
            # GET 판정
            rows_m = re.search(r"Rows:\s*(\d+)", summary)
            rows_str = f"rows={rows_m.group(1)}" if rows_m else ""
            if res.ok:
                res_display = f"200 {rows_str}".strip()
            else:
                err_line = next((line for line in summary.splitlines() if line.startswith("HTTP ") or line.startswith("Error: ")), summary.splitlines()[0])
                res_display = err_line

            if not res.ok:
                if "403" in summary or "ACCESS_DENIED" in summary:
                    verdict = "막힘(정상)"
                else:
                    verdict = "오류"
            else:
                # 200 성공인 경우
                if "본인" in ep.get("guards", []):
                    verdict = "본인 자료(정상)"
                elif associated_menus and not (associated_menus & user_menu_set):
                    # 화면 메뉴는 존재하는데 사원 메뉴 목록에 없는 경우 -> 관리자 화면 자료 노출!
                    verdict = "⚠ 관리자 화면 자료를 사원이 받음"
                elif associated_menus and (associated_menus & user_menu_set):
                    verdict = "본인 자료(정상)"
                else:
                    verdict = "⚠"
        else:
            # 쓰기 판정 (--probe-write)
            if "ACCESS_DENIED" in summary or "403" in summary or "권한이 없습니다" in summary:
                res_display = "빈 본문 → ACCESS_DENIED"
                verdict = "막힘(정상)"
            elif res.ok or "DATA_NOT_FOUND" in summary or "INVALID_INPUT" in summary or "400" in summary:
                # 검사 없이 서비스 내부까지 진입함!
                data_val = ""
                if "Data:" in summary:
                    m_data = re.search(r"Data:\s*([^\n]+)", summary)
                    if m_data:
                        data_val = f" Data:{m_data.group(1).strip()}"
                res_display = f"빈 본문 → 200{data_val}" if res.ok else "빈 본문 → 400"
                verdict = "⚠ 검사 없이 서비스까지 들어감"
            else:
                res_display = "빈 본문 → 500"
                verdict = "오류(본문 형식 확인)"

        results.append({
            "method": verb,
            "path": raw_path,
            "call_path": call_path,
            "guard_str": guards_str,
            "result_str": res_display,
            "verdict": verdict,
            "associated_menus": list(associated_menus),
        })

    return results


def format_authz_md(
    results: list[dict[str, Any]],
    as_user: str,
    emit_rows: bool = False,
) -> str:
    """판정 결과를 마크다운 테이블 및 요약으로 변환한다."""
    lines = [
        f"| 메서드 | 경로 | 검사(정적) | 사원 {as_user} 결과 | 판정 |",
        "|:---|:---|:---|:---|:---|",
    ]
    suspect_count = 0
    emit_lines: list[str] = []

    for r in results:
        is_suspect = "⚠" in r["verdict"]
        if is_suspect:
            suspect_count += 1
            emit_lines.append(f"| … | {as_user} {r['method']} {r['path']} → {r['result_str']} |")

        lines.append(
            f"| {r['method']} | {r['path']} | {r['guard_str']} | "
            f"{r['result_str']} | {r['verdict']} |"
        )

    summary = f"\n⚠ {suspect_count}건 — 보안_및_버그_의심.md에 적을 후보"
    out = "\n".join(lines) + "\n" + summary
    if emit_rows and emit_lines:
        out += "\n\n### 의심 후보 행:\n" + "\n".join(emit_lines)
    return out
