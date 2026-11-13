import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from yunhee import config
from yunhee.tools.base import ToolResult

SESSION_DIR_NAME = ".yunhee/sessions"


def get_sessions_dir() -> Path:
    s_dir = config.WORK_DIR / SESSION_DIR_NAME
    s_dir.mkdir(parents=True, exist_ok=True)
    return s_dir


def _safe_name(text: str) -> str:
    """파일명으로 안전하게 사용할 수 있도록 특수문자를 _ 로 치환한다."""
    return re.sub(r"[^\w\-.]", "_", text)


def _get_session_path(user: str, base_url: str, tenant: str | None = None, company: str | None = None) -> Path:
    parsed = urlparse(base_url)
    host_part = _safe_name(parsed.netloc or parsed.path or "default")
    parts = [host_part]
    if tenant:
        parts.append(_safe_name(tenant))
    if company:
        parts.append(_safe_name(company))
    parts.append(_safe_name(user))
    filename = "_".join(parts) + ".json"
    return get_sessions_dir() / filename


def _tenant_headers(base_url: str, tenant: str | None) -> dict[str, str]:
    """테넌트가 지정된 경우 OMS TenantResolver가 판정할 수 있도록 Host 헤더를 구성한다."""
    if not tenant:
        return {}
    port = urlparse(base_url).port
    host = config.API_TENANT_HOST.format(tenant=tenant)
    return {"Host": f"{host}:{port}" if port else host}


def _load_session(user: str, base_url: str, tenant: str | None = None, company: str | None = None) -> dict[str, Any] | None:
    session_file = _get_session_path(user, base_url, tenant, company)
    if not session_file.exists():
        return None
    try:
        return json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _save_session(
    user: str,
    base_url: str,
    cookies: dict,
    headers: dict,
    tenant: str | None = None,
    company: str | None = None,
    user_info: dict[str, Any] | None = None,
) -> None:
    session_file = _get_session_path(user, base_url, tenant, company)
    data = {"cookies": cookies, "headers": headers, "user_info": user_info or {}}
    session_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _get_failed_path(user: str, base_url: str, tenant: str | None = None, company: str | None = None) -> Path:
    parsed = urlparse(base_url)
    host_part = _safe_name(parsed.netloc or parsed.path or "default")
    parts = [host_part]
    if tenant:
        parts.append(_safe_name(tenant))
    if company:
        parts.append(_safe_name(company))
    parts.append(_safe_name(user))
    filename = "_".join(parts) + ".failed"
    return get_sessions_dir() / filename


def _clear_session(user: str, base_url: str, tenant: str | None = None, company: str | None = None) -> None:
    session_file = _get_session_path(user, base_url, tenant, company)
    if session_file.exists():
        try:
            session_file.unlink()
        except Exception:  # noqa: BLE001, S110
            pass


def resolve_user_credentials(
    user_or_role: str,
    db_name: str | None = None,
    company_code: str | None = None,
    password: str | None = None,
) -> tuple[str, str, dict[str, Any]]:
    """admin 또는 사원 ID/로그인 ID를 받아 (username, password, user_info)를 조회한다."""
    role_lower = user_or_role.lower()
    if role_lower == "admin":
        if company_code == "admin":
            user = "admin"
        else:
            user = os.getenv("YUNHEE_TEST_ADMIN_USER", config.TEST_ADMIN_USER)
        pw = password or os.getenv("YUNHEE_TEST_ADMIN_PASS", config.TEST_ADMIN_PASS)
        pw_src = "--password" if password else "YUNHEE_TEST_ADMIN_PASS"
        user_info = {
            "user_id": -28656,
            "org_id": 0,
            "company_id": 28000,
            "pw_source": pw_src,
            "emp_no": user,
            "company_code": company_code or "admin",
        }
        return user, pw, user_info

    # 1. YUNHEE_TEST_ACCOUNTS 파싱 (format: id:pw,id2:pw2)
    test_accounts_str = os.getenv("YUNHEE_TEST_ACCOUNTS", "")
    accounts: dict[str, str] = {}
    if test_accounts_str:
        for entry in re.split(r"[,;\s\n]+", test_accounts_str.strip()):
            if ":" in entry:
                k, v = entry.split(":", 1)
                accounts[k.strip()] = v.strip()

    # 2. DB 조회 (emp01_person)
    try:
        import psycopg
        from psycopg.rows import dict_row

        from yunhee.tools.sql_runner import get_connection_string

        db_url = get_connection_string(db_name)
        if db_url:
            with psycopg.connect(db_url, autocommit=False) as conn:
                conn.read_only = True
                with conn.cursor(row_factory=dict_row) as cur:
                    target_company_id = None
                    if company_code:
                        cur.execute(
                            "SELECT sys01_company_id FROM sys01_company WHERE sys01_loc_nm = %s LIMIT 1;",
                            (company_code,),
                        )
                        comp_row = cur.fetchone()
                        if comp_row:
                            target_company_id = int(comp_row["sys01_company_id"])
                        else:
                            raise ValueError(f"존재하지 않는 회사 코드입니다: {company_code}")

                    if target_company_id is not None:
                        cur.execute(
                            """
                            SELECT emp01_person_id, emp01_emp_no, TO_DECRYPTS(emp01_password) AS pwd, emp01_company_id
                            FROM emp01_person
                            WHERE (emp01_person_id::text = %s OR emp01_emp_no = %s)
                              AND emp01_company_id = %s
                            LIMIT 1;
                            """,
                            (user_or_role, user_or_role, target_company_id),
                        )
                        single = cur.fetchone()
                        rows = [single] if single else []
                    else:
                        cur.execute(
                            """
                            SELECT emp01_person_id, emp01_emp_no, TO_DECRYPTS(emp01_password) AS pwd, emp01_company_id
                            FROM emp01_person
                            WHERE emp01_person_id::text = %s OR emp01_emp_no = %s
                            ORDER BY (emp01_company_id = 28000) DESC, emp01_person_id ASC
                            LIMIT 10;
                            """,
                            (user_or_role, user_or_role),
                        )
                        rows = cur.fetchall() or []

                    if len(rows) > 1:
                        distinct_persons = {r["emp01_person_id"] for r in rows if r}
                        if len(distinct_persons) > 1:
                            raise ValueError(
                                f"사번({user_or_role})이 여러 회사에 존재합니다. -c <회사코드> 또는 사원 ID로 -u를 주세요."
                            )

                    row = rows[0] if rows else None
                    if row:
                        login_u = str(row["emp01_emp_no"])
                        raw_pwd = row.get("pwd")
                        p_id = int(row["emp01_person_id"])
                        c_id = int(row["emp01_company_id"]) if row.get("emp01_company_id") else 28000

                        default_pass = os.getenv("YUNHEE_TEST_DEFAULT_PASS", config.TEST_DEFAULT_PASS)
                        admin_pass = os.getenv("YUNHEE_TEST_ADMIN_PASS", config.TEST_ADMIN_PASS)

                        if password:
                            login_p = password
                            pw_source = "--password"
                        elif user_or_role in accounts or login_u in accounts:
                            login_p = accounts.get(user_or_role) or accounts.get(login_u)
                            pw_source = "YUNHEE_TEST_ACCOUNTS"
                        elif raw_pwd is not None and str(raw_pwd).strip():
                            login_p = str(raw_pwd).strip()
                            pw_source = "emp01_password"
                        elif default_pass:
                            login_p = default_pass
                            pw_source = "YUNHEE_TEST_DEFAULT_PASS"
                        else:
                            login_p = admin_pass
                            pw_source = "YUNHEE_TEST_ADMIN_PASS"
                            import sys
                            print(
                                "경고: 직원에 YUNHEE_TEST_ADMIN_PASS를 사용합니다. YUNHEE_TEST_DEFAULT_PASS 또는 --password를 지정하세요.",
                                file=sys.stderr,
                            )

                        org_id = 0
                        try:
                            cur.execute(
                                """
                                SELECT emp00_org_code_id
                                FROM emp00_trans_info
                                WHERE emp00_person_id = %s
                                ORDER BY emp00_trans_date DESC
                                LIMIT 1;
                                """,
                                (p_id,),
                            )
                            row_org = cur.fetchone()
                            if row_org and row_org.get("emp00_org_code_id"):
                                org_id = int(row_org["emp00_org_code_id"])
                        except Exception:  # noqa: BLE001, S110
                            pass

                        user_info = {
                            "user_id": p_id,
                            "org_id": org_id,
                            "company_id": c_id,
                            "pw_source": pw_source,
                            "emp_no": login_u,
                            "company_code": company_code,
                        }
                        return login_u, login_p, user_info
                    elif company_code:
                        raise ValueError(f"사원을 찾을 수 없습니다: {user_or_role} (회사: {company_code})")
    except ValueError:
        raise
    except Exception:  # noqa: BLE001, S110
        pass

    default_pass = os.getenv("YUNHEE_TEST_DEFAULT_PASS", config.TEST_DEFAULT_PASS)
    if password:
        return user_or_role, password, {
            "user_id": user_or_role,
            "org_id": 0,
            "company_id": 28000,
            "pw_source": "--password",
            "emp_no": user_or_role,
            "company_code": company_code,
        }
    if user_or_role in accounts:
        return user_or_role, accounts[user_or_role], {
            "user_id": user_or_role,
            "org_id": 0,
            "company_id": 28000,
            "pw_source": "YUNHEE_TEST_ACCOUNTS",
            "emp_no": user_or_role,
            "company_code": company_code,
        }
    if default_pass:
        return user_or_role, default_pass, {
            "user_id": user_or_role,
            "org_id": 0,
            "company_id": 28000,
            "pw_source": "YUNHEE_TEST_DEFAULT_PASS",
            "emp_no": user_or_role,
            "company_code": company_code,
        }

    raise ValueError(f"로그인 실패: {user_or_role}")


def _get_account_credentials(role: str) -> tuple[str, str, dict[str, Any]]:
    return resolve_user_credentials(role)


def login(
    base_url: str = config.API_BASE_URL,
    user: str = "admin",
    password: str = "1111",
    login_path: str = config.API_LOGIN_PATH,
    company_code: str | None = None,
    tenant: str | None = None,
    user_info: dict[str, Any] | None = None,
    force_login: bool = False,
) -> ToolResult:
    """로그인 엔드포인트를 호출하여 쿠키 및 토큰을 세션 파일에 저장한다."""
    url = f"{base_url.rstrip('/')}/{login_path.lstrip('/')}"
    comp = company_code or config.TEST_COMPANY

    # 5. 안전장치: 직전 실패 횟수가 3 이상이면 계정 잠금 방지를 위해 차단
    fail_file = _get_failed_path(user, base_url, tenant, comp)
    if fail_file.exists() and not force_login:
        try:
            failed_data = json.loads(fail_file.read_text(encoding="utf-8"))
            fail_cnt = failed_data.get("fail_count", 0)
            if fail_cnt >= 3:
                return ToolResult(
                    ok=False,
                    error=(
                        f"로그인 중단: 직전 로그인 실패 횟수가 {fail_cnt}/5회로 계정 잠금 직전입니다.\n"
                        "비밀번호를 다시 확인한 후 --force-login 옵션을 붙여 실행하세요.\n"
                        f"(시도 대상: user={user}, company={comp})"
                    ),
                )
        except Exception:  # noqa: BLE001, S110
            pass

    payload: dict[str, Any] = {"username": user, "password": password}
    if comp:
        payload["companyCode"] = comp

    req_headers = _tenant_headers(base_url, tenant)

    try:
        resp = httpx.post(
            url,
            json=payload,
            headers=req_headers,
            timeout=10.0,
        )
    except httpx.TimeoutException:
        return ToolResult(ok=False, error=f"로그인 응답 시간 초과 (10s) — POST {url}")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"로그인 연결 실패 ({url}): {exc}")

    if resp.status_code != 200:
        err_msg = resp.text.strip()
        m = re.search(r"실패\s*(\d+)\s*/\s*(\d+)\s*회", err_msg)
        fail_count = int(m.group(1)) if m else None
        if fail_count is not None:
            try:
                fail_file.write_text(
                    json.dumps({"fail_count": fail_count, "user": user, "company": comp}),
                    encoding="utf-8",
                )
            except Exception:  # noqa: BLE001, S110
                pass

        extra_hint = ""
        if "COMPANY_NOT_FOUND" in err_msg or "company" in err_msg.lower():
            extra_hint = "\n힌트: -c는 회사코드입니다(예: admin, kfstest). 회사 ID가 아닙니다."
            if comp and comp.isdigit():
                extra_hint += f" ({comp}는 companyId로 오해했나요?)"
        elif comp and comp.isdigit():
            extra_hint = f"\n힌트: -c는 회사코드입니다(예: admin, kfstest). {comp}는 companyId로 오해했나요?"

        u_id = (user_info or {}).get("user_id", user)
        e_no = (user_info or {}).get("emp_no", user)
        c_code = comp or (user_info or {}).get("company_code") or "기본"
        pw_src = (user_info or {}).get("pw_source", "미상")
        fail_str = f"{fail_count}/5" if fail_count else "불명"
        attempt_info = (
            f"\n시도: 사원 {u_id}(사번 {e_no}, 회사 {c_code}) · "
            f"비밀번호 출처 {pw_src} · 서버 실패 횟수 {fail_str}회 — "
            "같은 계정으로 다시 부르기 전에 비밀번호를 확인하세요"
        )
        return ToolResult(
            ok=False,
            error=f"로그인 실패 (HTTP {resp.status_code}): {err_msg[:400]}{attempt_info}{extra_hint}",
        )

    if fail_file.exists():
        try:
            fail_file.unlink()
        except Exception:  # noqa: BLE001, S110
            pass

    cookies = dict(resp.cookies)
    headers = dict(req_headers)
    info = dict(user_info or {})
    # 토큰이 본문에 있으면 Authorization 헤더 보관
    try:
        data = resp.json()
        token = data.get("token") or data.get("accessToken") or (data.get("data") or {}).get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        body_data = data.get("data") if isinstance(data, dict) else None
        if isinstance(body_data, dict):
            if body_data.get("userId") is not None:
                info["user_id"] = body_data.get("userId")
            if body_data.get("companyId") is not None:
                info["company_id"] = body_data.get("companyId")
            if body_data.get("orgId") is not None:
                info["org_id"] = body_data.get("orgId")
            elif "org_id" not in info:
                info["org_id"] = 0
    except Exception:  # noqa: BLE001, S110
        pass

    _save_session(user, base_url, cookies, headers, tenant=tenant, company=comp, user_info=info)
    return ToolResult(ok=True, data={"cookies": cookies, "headers": headers, "user_info": info})


def header_tag(
    base_url: str = "",
    tenant: str | None = None,
    company_code: str | None = None,
    trace_id: str | None = None,
    login_status: str | None = None,
) -> str:
    """결과 머리 태그 — 예: [AssetERP_1 · kalpa.localhost:8082 · tenant=kalpa · company=kalpa · login=reused · trace=95694936e2a3b376]"""
    parts = []
    if base_url:
        parsed = urlparse(base_url)
        path_part = parsed.path.strip("/")
        app_name = path_part.split("/")[-1] if path_part else (parsed.netloc or "default")
        port = parsed.port
        if tenant:
            host_tmpl = config.API_TENANT_HOST.format(tenant=tenant)
            effective_host = f"{host_tmpl}:{port}" if port else host_tmpl
        elif parsed.netloc:
            effective_host = parsed.netloc
        else:
            effective_host = ""

        parts.append(app_name)
        if effective_host and effective_host != app_name:
            parts.append(effective_host)
    if tenant:
        parts.append(f"tenant={tenant}")
    if company_code:
        parts.append(f"company={company_code}")
    if login_status:
        parts.append(f"login={login_status}")
    if trace_id:
        parts.append(f"trace={trace_id}")
    return f"[{' · '.join(parts)}]" if parts else ""


def _find_optional_params(path: str) -> list[str]:
    """해당 GET API 엔드포인트의 선택 쿼리 파라미터(? 표시) 목록을 탐색한다."""
    try:
        from yunhee.tools.biz.endpoints import collect_endpoints

        clean_path = path.split("?")[0].rstrip("/")
        eps = collect_endpoints()
        for ep in eps:
            ep_path = ep.get("path", "").rstrip("/")
            if ep.get("method") == "GET" and (ep_path == clean_path or clean_path.endswith(ep_path)):
                params = ep.get("params", [])
                opt_params = [p for p in params if p.endswith("?")]
                if opt_params:
                    return opt_params
    except Exception:  # noqa: BLE001, S110
        pass
    return []


def summarize_response(
    status_code: int,
    text: str,
    duration_ms: int,
    tenant: str | None = None,
    base_url: str = "",
    company_code: str | None = None,
    trace_id: str | None = None,
    mask: bool = True,
    path: str = "",
    user_info: dict[str, Any] | None = None,
    notice: str | None = None,
    upload_info: list[str] | None = None,
    login_status: str | None = None,
) -> str:
    """응답을 토큰 절약형 1~4줄 요약으로 가공한다."""
    def _finalize(s: str) -> str:
        if mask:
            from yunhee.tools.log_reader import mask_sensitive

            s, _ = mask_sensitive(s, enabled=True)
        return s

    duration_sec = f"{duration_ms / 1000:.2f}s"
    lines = []
    tag = header_tag(base_url, tenant, company_code, trace_id=trace_id, login_status=login_status)
    if tag:
        lines.append(tag)

    if user_info and user_info.get("user_id") is not None:
        u_id = user_info.get("user_id")
        o_id = user_info.get("org_id", 0)
        c_id = user_info.get("company_id", "")
        lines.append(f"user={u_id} org={o_id} company={c_id}")

    lines.append(f"HTTP {status_code} ({duration_sec})")
    if upload_info:
        lines.append(f"Upload: {', '.join(upload_info)}")
    if status_code == 404 and "No static resource" in text and path and not path.startswith("/api"):
        lines.append("💡 '/api' 접두가 필요한가요?")
    if notice:
        lines.append(notice)

    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        # JSON이 아닌 경우
        preview = text.strip()[:200]
        if preview:
            lines.append(f"Content: {preview}")
        return _finalize("\n".join(lines))

    # 400 또는 Validation failed 감지 (#8)
    val_errors: list[str] = []
    if isinstance(data, dict):
        if isinstance(data.get("errors"), list):
            for err_item in data["errors"]:
                if isinstance(err_item, dict) and "field" in err_item:
                    fld = err_item.get("field")
                    dmsg = err_item.get("defaultMessage") or err_item.get("message") or "검증 실패"
                    val_errors.append(f"{fld}: {dmsg}")
        msg_str = str(data.get("message", ""))
        if "Validation failed" in msg_str or "MethodArgumentNotValidException" in msg_str:
            pat = re.compile(r"Field error in object '[^']*' on field '([^']+)':.*?default message \[([^\]]+)\]")
            for m in pat.finditer(msg_str):
                pair = f"{m.group(1)}: {m.group(2)}"
                if pair not in val_errors:
                    val_errors.append(pair)
            if not val_errors:
                pat2 = re.compile(r"on field '([^']+)'.*?\[([^\]]+)\]")
                for m in pat2.finditer(msg_str):
                    val_errors.append(f"{m.group(1)}: {m.group(2)}")
    elif "Validation failed" in text:
        pat = re.compile(r"on field '([^']+)':.*?default message \[([^\]]+)\]")
        for m in pat.finditer(text):
            val_errors.append(f"{m.group(1)}: {m.group(2)}")

    if val_errors:
        lines.append(f"Validation: {', '.join(val_errors)}")

    target_list = None

    # 1. 공통 응답 봉투(success, code, data) 언래핑
    if isinstance(data, dict) and {"success", "code", "data"} <= data.keys():
        if data.get("success") is False:
            lines.append(f"Error: {data.get('code')} {data.get('message') or ''}".rstrip())
            return _finalize("\n".join(lines))
        lines.append(f"Status: {data.get('code', 'OK')}")
        body = data["data"]
        if isinstance(body, list):
            target_list = body
        elif isinstance(body, dict):
            lines.append(f"Fields ({len(body)}): [{', '.join(list(body)[:15])}]")
            lines.append(f"Data: {json.dumps(body, ensure_ascii=False)[:250]}")
            return _finalize("\n".join(lines))
        else:  # 0, "abc", true, null
            lines.append(f"Data: {json.dumps(body, ensure_ascii=False)}")
            return _finalize("\n".join(lines))
    elif isinstance(data, list):
        target_list = data
    elif isinstance(data, dict):
        if "data" in data and isinstance(data["data"], list):
            target_list = data["data"]
            lines.append(f"Status: {data.get('status', 'OK')}")
        elif "items" in data and isinstance(data["items"], list):
            target_list = data["items"]
        else:
            # 단일 객체 dict
            keys = list(data.keys())
            lines.append(f"Object keys ({len(keys)}): [{', '.join(keys[:15])}]")
            preview = json.dumps(data, ensure_ascii=False)[:200]
            lines.append(f"Preview: {preview}...")
            return _finalize("\n".join(lines))

    if target_list is not None:
        lines.append(f"Rows: {len(target_list)}")
        if len(target_list) == 0 and path:
            hint_params = _find_optional_params(path)
            if hint_params:
                lines.append(f"💡 선택 파라미터: {', '.join(hint_params)} (안 준 값에 서버 기본값이 걸릴 수 있음)")
        if target_list and isinstance(target_list[0], dict):
            first_keys = list(target_list[0].keys())
            lines.append(f"Fields ({len(first_keys)}): [{', '.join(first_keys[:15])}]")
            first_row_preview = json.dumps(target_list[0], ensure_ascii=False)
            lines.append(f"First row: {first_row_preview[:250]}")
    return _finalize("\n".join(lines))


def _timeout_message(timeout: float, method: str, path: str) -> str:
    """시간 초과는 느린 SQL 신호로 쓰이므로 연결 실패와 다른 문구로 낸다."""
    return (
        f"응답 시간 초과 ({timeout:g}s) — {method.upper()} {path}\n"
        f"      서버 처리가 느립니다. 필요하면 --timeout 60 으로 늘리세요."
    )


_EXT_MIME_FALLBACK = {
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
    ".csv": "text/csv",
    ".pdf": "application/pdf",
    ".json": "application/json",
    ".txt": "text/plain",
    ".zip": "application/zip",
}


def _prepare_multipart(
    form_fields: list[str],
) -> tuple[dict[str, str], list[tuple[str, tuple[str, bytes, str]]], list[str], str | None]:
    """-F/--form 인자 목록을 파싱하여 (data_dict, files_list, upload_info, error)를 반환한다."""
    import mimetypes

    data_dict: dict[str, str] = {}
    files_list: list[tuple[str, tuple[str, bytes, str]]] = []
    upload_info: list[str] = []

    for item in form_fields:
        if "=" not in item:
            return {}, [], [], f"잘못된 -F/--form 형식 (name=value 또는 name=@파일경로 필요): {item}"
        name, val = item.split("=", 1)
        name = name.strip()
        if not name:
            return {}, [], [], f"빈 필드 이름: {item}"
        if val.startswith("@"):
            file_spec = val[1:]
            explicit_mime = None
            if ";type=" in file_spec:
                path_str, explicit_mime = file_spec.split(";type=", 1)
                explicit_mime = explicit_mime.strip()
            else:
                path_str = file_spec
            fpath = Path(path_str.strip()).expanduser()
            if not fpath.is_file():
                return {}, [], [], f"업로드할 파일을 찾을 수 없습니다: {path_str}"
            mime_type = (
                explicit_mime
                or mimetypes.guess_type(fpath.name)[0]
                or _EXT_MIME_FALLBACK.get(fpath.suffix.lower())
                or "application/octet-stream"
            )
            fbytes = fpath.read_bytes()
            files_list.append((name, (fpath.name, fbytes, mime_type)))
            upload_info.append(f"{fpath.name} ({len(fbytes)}B)")
        else:
            data_dict[name] = val

    return data_dict, files_list, upload_info, None


_PCT_HEX_RE = re.compile(r"%[0-9A-Fa-f]{2}")
_TABLE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?$")


def snapshot_tables(
    track_spec: str | list[str] | None,
    db_name: str | None = None,
    track_children: bool = False,
) -> dict[str, dict[str, Any]]:
    """--track에 지정된 테이블들의 호출 전 행 수와 PK 집합을 스냅샷으로 저장한다."""
    if not track_spec:
        return {}
    if isinstance(track_spec, str):
        tables = [t.strip() for t in track_spec.split(",") if t.strip()]
    else:
        tables = [t.strip() for item in track_spec for t in item.split(",") if t.strip()]
    if not tables:
        return {}

    if track_children:
        try:
            from yunhee.tools.biz.orphans import find_child_tables

            extra_children: list[str] = []
            for t in tables:
                extra_children.extend(find_child_tables(t, db_name=db_name))
            for ct in extra_children:
                if ct not in tables:
                    tables.append(ct)
        except Exception:  # noqa: BLE001, S110
            pass

    import psycopg

    from yunhee.tools.sql_runner import get_connection_string

    db_url = get_connection_string(db_name)
    if not db_url:
        return {"__error__": {"error": "DB 연결 정보를 찾을 수 없습니다 (YUNHEE_DB)"}}

    snaps: dict[str, dict[str, Any]] = {}
    try:
        with psycopg.connect(db_url, autocommit=True) as conn:
            conn.read_only = True
            with conn.cursor() as cur:
                for raw_tbl in tables:
                    if not _TABLE_IDENT_RE.match(raw_tbl):
                        snaps[raw_tbl] = {"error": f"유효하지 않은 테이블명: {raw_tbl}"}
                        continue
                    if "." in raw_tbl:
                        schema, tbl = raw_tbl.split(".", 1)
                    else:
                        schema, tbl = "public", raw_tbl
                    schema_l, tbl_l = schema.lower(), tbl.lower()
                    cur.execute(
                        """
                        SELECT kcu.column_name
                        FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage kcu
                          ON tc.constraint_name = kcu.constraint_name
                         AND tc.table_schema = kcu.table_schema
                        WHERE tc.constraint_type = 'PRIMARY KEY'
                          AND tc.table_schema = %s
                          AND tc.table_name = %s
                        ORDER BY kcu.ordinal_position
                        """,
                        (schema_l, tbl_l),
                    )
                    pk_cols = [r[0] for r in cur.fetchall()]
                    qualified = f'"{schema_l}"."{tbl_l}"'
                    try:
                        cur.execute(f"SELECT COUNT(*) FROM {qualified}")
                        cnt_row = cur.fetchone()
                        count = int(cnt_row[0]) if cnt_row else 0
                    except Exception as exc:  # noqa: BLE001
                        snaps[raw_tbl] = {"error": str(exc).splitlines()[0]}
                        continue

                    pks: set[tuple[Any, ...]] = set()
                    max_pks: tuple[Any, ...] | None = None
                    if pk_cols:
                        pk_select = ", ".join(f'"{c}"' for c in pk_cols)
                        if count <= 100000:
                            cur.execute(f"SELECT {pk_select} FROM {qualified}")
                            pks = {tuple(r) for r in cur.fetchall()}
                        else:
                            order_desc = ", ".join(f'"{c}" DESC' for c in pk_cols)
                            cur.execute(f"SELECT {pk_select} FROM {qualified} ORDER BY {order_desc} LIMIT 500")
                            rows = cur.fetchall()
                            pks = {tuple(r) for r in rows}
                            if rows:
                                max_pks = tuple(rows[0])
                    snaps[raw_tbl] = {
                        "schema": schema_l,
                        "table": tbl_l,
                        "pk_cols": pk_cols,
                        "count": count,
                        "pks": pks,
                        "max_pks": max_pks,
                    }
    except Exception as exc:  # noqa: BLE001
        return {"__error__": {"error": f"DB 연결 실패: {exc}"}}
    return snaps


def format_table_tracks(before_snaps: dict[str, dict[str, Any]], db_name: str | None = None) -> list[str]:
    """호출 전 스냅샷과 현재 DB 상태를 비교하여 테이블별 행 수 변화 및 신규 PK 문자열 목록을 반환한다."""
    if not before_snaps:
        return []
    if "__error__" in before_snaps:
        return [f"⚠ track 실패: {before_snaps['__error__']['error']}"]

    after_snaps = snapshot_tables(list(before_snaps.keys()), db_name=db_name)
    if "__error__" in after_snaps:
        return [f"⚠ track 실패: {after_snaps['__error__']['error']}"]

    lines: list[str] = []
    for tbl, b_info in before_snaps.items():
        if "error" in b_info:
            lines.append(f"{tbl}: ⚠ {b_info['error']}")
            continue
        a_info = after_snaps.get(tbl, {})
        if "error" in a_info:
            lines.append(f"{tbl}: ⚠ {a_info['error']}")
            continue
        b_cnt = b_info["count"]
        a_cnt = a_info["count"]
        delta = a_cnt - b_cnt
        pk_cols: list[str] = b_info.get("pk_cols") or []
        b_pks: set[tuple[Any, ...]] = b_info.get("pks") or set()
        a_pks: set[tuple[Any, ...]] = a_info.get("pks") or set()
        added = sorted(a_pks - b_pks)
        removed = sorted(b_pks - a_pks)

        if delta == 0 and not added and not removed:
            lines.append(f"{tbl}: {b_cnt} → {a_cnt} (변화 없음)")
        elif delta > 0 or added:
            sign_delta = f"+{delta}" if delta >= 0 else str(delta)
            if added and pk_cols:
                pk_items = []
                for tup in added[:5]:
                    if len(pk_cols) == 1:
                        pk_items.append(f"{pk_cols[0]}={tup[0]}")
                    else:
                        pk_items.append("(" + ", ".join(f"{c}={v}" for c, v in zip(pk_cols, tup, strict=False)) + ")")
                more = f" 외 {len(added) - 5}건" if len(added) > 5 else ""
                lines.append(f"{tbl}: {b_cnt} → {a_cnt} ({sign_delta}: {', '.join(pk_items)}{more})")
            else:
                lines.append(f"{tbl}: {b_cnt} → {a_cnt} ({sign_delta})")
        else:
            lines.append(f"{tbl}: {b_cnt} → {a_cnt} ({delta})")
    return lines


def normalize_query_param_value(val: Any, raw: bool = False) -> Any:
    """-p k=v 의 v에 이미 %XX(16진 두 자리) 패턴이 있으면 이중 인코딩을 막기 위해 1회 디코딩한다.

    - raw=True(--raw-param)이면 원문 그대로 유지한다.
    - '%' 단독이나 '%2', '%ZZ'처럼 16진 두 자리가 아닌 경우 그대로 두어 httpx가 인코딩하게 한다.
    """
    if raw or not isinstance(val, str):
        return val
    if _PCT_HEX_RE.search(val):
        from urllib.parse import unquote

        return unquote(val)
    return val


def encode_query_param_value(val: str, raw: bool = False) -> str:
    """쿼리 파라미터 값을 URL 인코딩한 문자열로 반환한다 (이중 인코딩 방지 포함)."""
    from urllib.parse import quote

    norm = normalize_query_param_value(val, raw=raw)
    return quote(str(norm), safe="")


def normalize_query_params(params: dict[str, Any] | None, raw: bool = False) -> dict[str, Any] | None:
    """쿼리 파라미터 딕셔너리의 값들에 이중 인코딩 방지 정규화를 적용한다."""
    if not params:
        return params
    out: dict[str, Any] = {}
    for k, v in params.items():
        if isinstance(v, list):
            out[k] = [normalize_query_param_value(item, raw=raw) for item in v]
        else:
            out[k] = normalize_query_param_value(v, raw=raw)
    return out


def request_api(
    method: str,
    path: str,
    base_url: str = config.API_BASE_URL,
    as_role: str = "admin",
    login_path: str = config.API_LOGIN_PATH,
    company_code: str | None = None,
    tenant: str | None = None,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    form_fields: list[str] | None = None,
    auto_login: bool = True,
    timeout: float | None = None,
    mask: bool = True,
    wait_deploy: float | None = None,
    raw_param: bool = False,
    track: str | list[str] | None = None,
    track_children: bool = False,
    fresh: bool = False,
    password: str | None = None,
    force_login: bool = False,
) -> ToolResult:
    """인증 세션을 사용하여 API를 호출하고 결과를 요약 반환한다.
    
    안전 원칙:
    - 최초 로그인 시도 실패 시 즉시 중단 (더미 요청으로 401을 발생시키지 않음).
    - 저장된 기존 세션이 만료되어 401이 난 경우에만 세션을 삭제하고 1회 재로그인 시도.
    - 재로그인이 실패하면 즉시 실패로 중단하여 계정 잠금(5회 실패 락) 위험 원천 차단.
    """
    import time

    params = normalize_query_params(params, raw=raw_param)

    if json_body is not None and form_fields:
        return ToolResult(ok=False, error="--body(-b)와 --form(-F) 옵션은 함께 사용할 수 없습니다.")

    form_data: dict[str, str] | None = None
    form_files: list[tuple[str, tuple[str, bytes, str]]] | None = None
    upload_info: list[str] = []
    if form_fields:
        d_dict, f_list, u_info, err_msg = _prepare_multipart(form_fields)
        if err_msg:
            return ToolResult(ok=False, error=err_msg)
        form_data = d_dict or None
        form_files = f_list or None
        upload_info = u_info

    if wait_deploy:
        from yunhee.tools.log_reader import check_app_starting_after_deploy

        wait_limit = float(wait_deploy)
        start_wait = time.perf_counter()
        while time.perf_counter() - start_wait < wait_limit:
            is_starting, _ = check_app_starting_after_deploy()
            if not is_starting:
                break
            time.sleep(1)

    comp = company_code or config.TEST_COMPANY
    try:
        try:
            user, pw, user_info = resolve_user_credentials(as_role, company_code=comp, password=password)
        except TypeError:
            user, pw, user_info = resolve_user_credentials(as_role)
    except ValueError as exc:
        return ToolResult(ok=False, error=str(exc))

    comp = company_code or config.TEST_COMPANY
    if fresh:
        _clear_session(user, base_url, tenant, comp)
        session = None
        had_existing_session = False
    else:
        session = _load_session(user, base_url, tenant, comp)
        had_existing_session = session is not None
    if session and session.get("user_info"):
        user_info = session.get("user_info")

    login_status = "reused" if had_existing_session else "new"

    conf_pfx = config.TOML_CONFIG.get("api", {}).get("auto_prefix")
    auto_prefix = "/api/v1/" if conf_pfx is None else (conf_pfx or "")
    if auto_prefix and not path.startswith(("/api/", "api/")):
        cleaned = path.lstrip("/")
        if cleaned.startswith("v1/"):
            path = "/api/" + cleaned
        else:
            pfx = auto_prefix if auto_prefix.endswith("/") else auto_prefix + "/"
            path = pfx + cleaned

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    # 세션이 없고 자동 로그인이 켜져 있으면 최초 로그인 시도
    if not session and auto_login:
        login_res = login(
            base_url=base_url,
            user=user,
            password=pw,
            login_path=login_path,
            company_code=comp,
            tenant=tenant,
            user_info=user_info,
            force_login=force_login,
        )
        if not login_res.ok:
            # 로그인 실패 시 실패 메시지를 숨기지 않고 즉시 반환하여 중단!
            return ToolResult(ok=False, error=login_res.error)
        session = login_res.data
        login_status = "new"
        if session and session.get("user_info"):
            user_info = session.get("user_info")

    cookies = (session or {}).get("cookies", {})
    headers = dict((session or {}).get("headers", {}))
    headers.update(_tenant_headers(base_url, tenant))
    if form_fields:
        headers.pop("Content-Type", None)
        headers.pop("content-type", None)

    if timeout is None:
        timeout = config.API_TIMEOUT

    req_kwargs: dict[str, Any] = {}
    if form_fields:
        if form_data:
            req_kwargs["data"] = form_data
        if form_files:
            req_kwargs["files"] = form_files
    elif json_body is not None:
        req_kwargs["json"] = json_body

    before_track_snaps = snapshot_tables(track, track_children=track_children) if track else {}

    start = time.perf_counter()
    try:
        resp = httpx.request(
            method=method.upper(),
            url=url,
            params=params,
            cookies=cookies,
            headers=headers,
            timeout=timeout,
            **req_kwargs,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
    except httpx.TimeoutException:
        return ToolResult(ok=False, error=_timeout_message(timeout, method, path))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"API 요청 실패 ({method} {url}): {exc}")

    # 기존에 저장되어 있던 세션이 만료되어 401 또는 TOKEN_EXPIRED가 뜬 경우에만 1회 재로그인 시도
    is_token_expired = resp.status_code == 401 or (
        "TOKEN_EXPIRED" in resp.text
        or "만료" in resp.text
        or "만료되었습니다" in resp.text
    )
    if is_token_expired and auto_login and had_existing_session:
        _clear_session(user, base_url, tenant, comp)
        login_res = login(
            base_url=base_url,
            user=user,
            password=pw,
            login_path=login_path,
            company_code=comp,
            tenant=tenant,
            user_info=user_info,
            force_login=force_login,
        )
        if not login_res.ok:
            # 재로그인 실패 시 추가 요청을 하지 않고 즉시 실패 반환 (계정 잠금 방지)
            return ToolResult(ok=False, error=f"세션 만료 후 재로그인 실패: {login_res.error}")

        session = login_res.data
        login_status = "new"
        if session and session.get("user_info"):
            user_info = session.get("user_info")
        new_headers = dict(session.get("headers", {}))
        new_headers.update(_tenant_headers(base_url, tenant))
        if form_fields:
            new_headers.pop("Content-Type", None)
            new_headers.pop("content-type", None)
        cookies = session.get("cookies", {})
        headers = new_headers

        try:
            resp = httpx.request(
                method=method.upper(),
                url=url,
                params=params,
                cookies=session.get("cookies", {}),
                headers=new_headers,
                timeout=timeout,
                **req_kwargs,
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
        except httpx.TimeoutException:
            return ToolResult(ok=False, error=_timeout_message(timeout, method, path))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"재시도 요청 실패: {exc}")

    notice = None
    if resp.status_code == 404:
        from yunhee.tools.log_reader import check_app_starting_after_deploy

        is_starting, hh_mm = check_app_starting_after_deploy()
        if is_starting and hh_mm:
            notice = f"ℹ 배포 후 앱이 아직 올라오는 중일 수 있음 (배포 {hh_mm}, 기동 기록 없음) — 잠시 뒤 다시"
        else:
            conf_pfx = config.TOML_CONFIG.get("api", {}).get("auto_prefix")
            auto_prefix = "/api/v1/" if conf_pfx is None else (conf_pfx or "")
            if auto_prefix and not path.startswith(("/api/", "api/")):
                cleaned = path.lstrip("/")
                if cleaned.startswith("v1/"):
                    corrected_path = "/api/" + cleaned
                else:
                    pfx = auto_prefix if auto_prefix.endswith("/") else auto_prefix + "/"
                    corrected_path = pfx + cleaned

                corrected_url = f"{base_url.rstrip('/')}/{corrected_path.lstrip('/')}"
                notice = f"ℹ 경로를 {corrected_path} 로 보정"
                start2 = time.perf_counter()
                try:
                    resp2 = httpx.request(
                        method=method.upper(),
                        url=corrected_url,
                        params=params,
                        cookies=cookies,
                        headers=headers,
                        timeout=timeout,
                        **req_kwargs,
                    )
                    duration_ms = int((time.perf_counter() - start2) * 1000)
                    resp = resp2
                    path = corrected_path
                except Exception:  # noqa: BLE001, S110
                    pass

    resp_headers = getattr(resp, "headers", {}) or {}
    trace_hdr = config.LOG_TRACE_HEADER or "X-Trace-Id"
    trace_id = resp_headers.get(trace_hdr) or resp_headers.get(trace_hdr.lower())

    summary = summarize_response(
        resp.status_code,
        resp.text,
        duration_ms,
        tenant=tenant,
        base_url=base_url,
        company_code=company_code,
        trace_id=trace_id,
        mask=mask,
        path=path,
        user_info=user_info,
        notice=notice,
        upload_info=upload_info or None,
        login_status=login_status,
    )
    track_lines = format_table_tracks(before_track_snaps) if before_track_snaps else []
    if track_lines:
        summary = summary + "\n" + "\n".join(track_lines)
    return ToolResult(
        ok=resp.is_success,
        data={
            "status_code": resp.status_code,
            "duration_ms": duration_ms,
            "text": resp.text,
            "summary": summary,
            "trace_id": trace_id,
            "user_info": user_info,
            "track": track_lines,
            "login_status": login_status,
        },
        error=None if resp.is_success else f"HTTP {resp.status_code}",
    )
