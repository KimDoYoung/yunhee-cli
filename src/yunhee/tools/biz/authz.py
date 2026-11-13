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
from yunhee.tools.trace.tobe import _body, find_layout, normalize_url, parse_api_ts


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


def _make_dummy_param(p_type: str, p_name: str = "") -> str:
    name_l = p_name.lower()
    now_dt = datetime.datetime.now(tz=datetime.UTC)
    if "year" in name_l:
        return str(now_dt.year)
    if "month" in name_l:
        return now_dt.strftime("%Y.%m")
    if name_l in ("paycode", "pay_code"):
        return "01"
    t = p_type.lower()
    if "date" in t or "date" in name_l:
        return now_dt.date().isoformat()
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
    probe_appr: bool = False,
    dry_run: bool = False,
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
        is_appr_put = verb == "PUT" and raw_path.endswith(("/appr-id", "/appr"))
        if is_write and not probe_write and not (probe_appr and is_appr_put):
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

        # dry-run 처리 (064 #9)
        if dry_run and is_write:
            results.append({
                "method": verb,
                "path": raw_path,
                "call_path": call_path,
                "guard_str": guards_str,
                "result_str": "(미호출 — dry-run)",
                "verdict": "미호출(dry-run)",
                "associated_menus": [],
            })
            continue

        # 3. 쿼리 / 본문 준비
        req_params: dict[str, str] = {}
        json_body: Any = None

        if not is_write:
            for q in ep.get("query", []):
                q_name = q["name"]
                if q_name in common_params:
                    req_params[q_name] = common_params[q_name]
                else:
                    val = _make_dummy_param(q.get("type", "String"), q_name)
                    if val or q.get("required"):
                        req_params[q_name] = val or "1"
        else:
            b_info = ep.get("body", {})
            if b_info.get("list"):
                json_body = []
            else:
                json_body = {}

        # 4. 결재 ID 바꿔치기 프로빙 (--probe-appr, 061 #6)
        if probe_appr and verb == "PUT" and raw_path.endswith(("/appr-id", "/appr")):
            list_path = re.sub(r"/\{[^}/]*\}/appr(?:-id)?$", "", raw_path)
            curr_year = datetime.datetime.now(tz=datetime.timezone(datetime.timedelta(hours=9))).year
            res_list = api_client.request_api("GET", list_path, as_role=as_user, company_code=company, password=password, params={"stdYear": str(curr_year)})
            items = []
            if res_list.ok and isinstance(res_list.data, dict):
                d = res_list.data.get("data")
                if isinstance(d, list):
                    items = d
                elif isinstance(d, dict) and isinstance(d.get("rows"), list):
                    items = d["rows"]

            target_row = next((r for r in items if isinstance(r, dict) and (r.get("apprId") or r.get("statusCode") in (30, "30"))), None)
            if not target_row and items:
                target_row = items[0]

            if target_row and isinstance(target_row, dict):
                ref_id_val = target_row.get("id") or next((v for k, v in target_row.items() if k.endswith("Id")), 1)
                orig_appr_id = target_row.get("apprId", 1)
                call_put_path = raw_path.replace("{ref}", str(ref_id_val)).replace("{id}", str(ref_id_val))
                if re.search(r"\{[^}]+\}", call_put_path):
                    call_put_path = re.sub(r"\{[^}]+\}", str(ref_id_val), call_put_path)

                try:
                    res_tamper = api_client.request_api("PUT", call_put_path, as_role=as_user, company_code=company, password=password, json_body={"apprId": 1})
                    if res_tamper.ok:
                        res_display = "apprId=1 허용 (되돌림 완료)"
                        verdict = "⚠ 결재 ID 검사 없음"
                    else:
                        res_display = f"apprId=1 차단 ({res_tamper.error or '오류'})"
                        verdict = "막힘(정상)"
                finally:
                    if orig_appr_id is not None:
                        api_client.request_api("PUT", call_put_path, as_role=as_user, company_code=company, password=password, json_body={"apprId": orig_appr_id})
            else:
                res_display = "건너뜀(완료 행 없음)"
                verdict = "건너뜀"

            results.append({
                "method": verb,
                "path": raw_path,
                "call_path": call_path,
                "guard_str": guards_str,
                "result_str": res_display,
                "verdict": verdict,
                "associated_menus": [],
            })
            continue

        # 4. 일반 API 요청
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
            # GET 판정 (061 #5)
            rows_m = re.search(r"Rows:\s*(\d+)", summary)
            row_cnt = int(rows_m.group(1)) if rows_m else None
            rows_str = f"rows={row_cnt}" if row_cnt is not None else ""
            if res.ok:
                res_display = f"200 {rows_str}".strip()
            else:
                err_line = next((line for line in summary.splitlines() if line.startswith(("HTTP ", "Error: "))), summary.splitlines()[0])
                res_display = err_line

            if not res.ok:
                if "403" in summary or "ACCESS_DENIED" in summary or "권한이 없습니다" in summary:
                    verdict = "막힘(정상)"
                elif "404" in summary or "DATA_NOT_FOUND" in summary:
                    verdict = "자료없음(더미 ID) — 판정 못 함"
                else:
                    verdict = "오류"
            else:
                # 200 성공인 경우
                is_common_ref = any(k in raw_path for k in ("tax-calc", "tax-deduct", "common-code", "codes"))
                if "본인" in ep.get("guards", []):
                    verdict = "본인 자료(정상)"
                elif is_common_ref or "KFS관리자" in ep.get("guards", []):
                    verdict = "공통 기준표(참고)"
                elif row_cnt == 0:
                    verdict = "⚠?(0행 — 자료 없음)"
                elif associated_menus and not (associated_menus & user_menu_set):
                    verdict = "⚠ 관리자 화면 자료를 사원이 받음"
                elif associated_menus and (associated_menus & user_menu_set):
                    verdict = "본인 자료(정상)"
                else:
                    verdict = "⚠?(미분류)"
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

        # 5. 쓰기 200 시 생성 경고 처리 (064 #9)
        warn_created = None
        if is_write and res.ok:
            id_val = None
            id_key = None
            if isinstance(res.data, dict):
                d_obj = res.data.get("data")
                if isinstance(d_obj, dict):
                    for k, v in d_obj.items():
                        if k.endswith("Id") and v is not None:
                            id_key = k
                            id_val = v
                            break
                elif isinstance(d_obj, (int, str)):
                    id_key = "id"
                    id_val = d_obj
            del_method = "지울 API: 없음"
            del_ep = next((e for e in endpoints if e.get("method") == "DELETE" and (e.get("path") == raw_path or raw_path.startswith(e.get("path", "").split("{")[0]))), None)
            if del_ep:
                del_method = f"DELETE {del_ep['path']}"

            id_str = f"{id_key}={id_val}" if id_key else "ID 미확인"
            warn_created = f"⚠ 행이 만들어졌을 수 있음: {id_str} — {del_method}"

        results.append({
            "method": verb,
            "path": raw_path,
            "call_path": call_path,
            "guard_str": guards_str,
            "result_str": res_display,
            "verdict": verdict,
            "associated_menus": list(associated_menus),
            "warn_created": warn_created,
        })

    return results


def lint_delete_by_id(target: str | Path | None = None, root_dir: Path | None = None) -> list[dict[str, Any]]:
    """컨트롤러 요청 DTO의 ...Id 필드가 서비스에서 검증 없이 delete*/update* 매퍼로 전달되는 패턴을 정적 검출한다 (064 #6)."""
    if root_dir is None:
        root_dir = find_layout().root

    java_root = root_dir / "backend" / "src" / "main" / "java"
    svc_files: list[Path] = []
    if target:
        t_str = str(target).strip()
        if java_root.is_dir():
            svc_files = sorted(java_root.glob(f"**/biz/{t_str}/**/*Service.java"))
        if not svc_files:
            svc_files = sorted(root_dir.rglob(f"*{t_str}*Service.java"))
    else:
        if java_root.is_dir():
            svc_files = sorted(java_root.rglob("*Service.java"))
        else:
            svc_files = sorted(root_dir.rglob("*Service.java"))

    findings: list[dict[str, Any]] = []

    for sf in svc_files:
        text = sf.read_text(encoding="utf-8", errors="replace")

        method_pat = re.compile(
            r"^[ \t]*(?:public|protected)\s+(?!class)[\w<>\[\], ?.]+?\s+(\w+)\s*\(([^)]*)\)[^{;]*\{",
            re.MULTILINE,
        )
        for m in method_pat.finditer(text):
            m_name = m.group(1)
            params_str = m.group(2)
            open_brace = m.end() - 1
            body = _body(text, open_brace)

            dto_vars = []
            for p_chunk in params_str.split(","):
                p_tokens = p_chunk.strip().split()
                if len(p_tokens) >= 2:
                    p_type, p_var = p_tokens[-2], p_tokens[-1]
                    if p_type not in ("UserPrincipal", "Authentication", "HttpServletRequest", "HttpServletResponse"):
                        dto_vars.append(p_var)

            del_calls = re.findall(r"\bmapper\s*\.\s*(delete\w+|update\w+)\s*\(([^;]*?)\)", body)
            for mapper_meth, args_str in del_calls:
                for dvar in dto_vars:
                    id_m = re.search(r"\b" + re.escape(dvar) + r"\s*\.\s*(?:get)?(\w*Id)\s*\(", args_str)
                    if id_m:
                        field_name = id_m.group(1)
                        field_name = field_name[0].lower() + field_name[1:]
                        has_owner_check = bool(
                            re.search(r"getUserId\(\)\s*==\s*" + re.escape(field_name), body)
                            or re.search(r"\.equals\s*\(\s*user\.getUserId\(\)\s*\)", body)
                            or "checkOwner" in body
                            or "checkMine" in body
                        )
                        if not has_owner_check:
                            line_no = text[:m.start()].count("\n") + 1
                            svc_cls = sf.stem
                            findings.append({
                                "service": f"{svc_cls}.{m_name}",
                                "field": field_name,
                                "mapper_call": mapper_meth,
                                "file": f"{sf.name}:{line_no}",
                                "line": line_no,
                                "summary": f"{svc_cls}.{m_name} ({field_name} → {mapper_meth})",
                            })

    return findings


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
    created_warnings: list[str] = []

    for r in results:
        is_suspect = r["verdict"].startswith("⚠ ") and not r["verdict"].startswith("⚠?")
        if is_suspect:
            suspect_count += 1
            emit_lines.append(f"| … | {as_user} {r['method']} {r['path']} → {r['result_str']} |")

        if r.get("warn_created"):
            created_warnings.append(r["warn_created"])

        lines.append(
            f"| {r['method']} | {r['path']} | {r['guard_str']} | "
            f"{r['result_str']} | {r['verdict']} |"
        )

    summary = f"\n⚠ {suspect_count}건 — 보안_및_버그_의심.md에 적을 후보"
    out = "\n".join(lines) + "\n" + summary
    if created_warnings:
        out += "\n\n### 행 생성 경고:\n" + "\n".join(created_warnings)
    if emit_rows and emit_lines:
        out += "\n\n### 의심 후보 행:\n" + "\n".join(emit_lines)
    return out
