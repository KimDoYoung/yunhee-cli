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


def _clear_session(user: str, base_url: str, tenant: str | None = None, company: str | None = None) -> None:
    session_file = _get_session_path(user, base_url, tenant, company)
    if session_file.exists():
        try:
            session_file.unlink()
        except Exception:  # noqa: BLE001, S110
            pass


def resolve_user_credentials(user_or_role: str, db_name: str | None = None) -> tuple[str, str, dict[str, Any]]:
    """admin 또는 사원 ID/로그인 ID를 받아 (username, password, user_info)를 조회한다."""
    role_lower = user_or_role.lower()
    if role_lower == "admin":
        user = os.getenv("YUNHEE_TEST_ADMIN_USER", config.TEST_ADMIN_USER)
        pw = os.getenv("YUNHEE_TEST_ADMIN_PASS", config.TEST_ADMIN_PASS)
        user_info = {"user_id": -28656, "org_id": 0, "company_id": 28000}
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
                    cur.execute(
                        """
                        SELECT emp01_person_id, emp01_emp_no, TO_DECRYPTS(emp01_password) AS pwd, emp01_company_id
                        FROM emp01_person
                        WHERE emp01_person_id::text = %s OR emp01_emp_no = %s
                        LIMIT 1;
                        """,
                        (user_or_role, user_or_role),
                    )
                    row = cur.fetchone()
                    if row:
                        login_u = str(row["emp01_emp_no"])
                        login_p = accounts.get(user_or_role) or accounts.get(login_u) or str(row["pwd"])
                        p_id = int(row["emp01_person_id"])
                        c_id = int(row["emp01_company_id"]) if row.get("emp01_company_id") else 28000
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
                        }
                        return login_u, login_p, user_info
    except Exception:  # noqa: BLE001, S110
        pass

    if user_or_role in accounts:
        return user_or_role, accounts[user_or_role], {"user_id": user_or_role, "org_id": 0, "company_id": 28000}

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
) -> ToolResult:
    """로그인 엔드포인트를 호출하여 쿠키 및 토큰을 세션 파일에 저장한다."""
    url = f"{base_url.rstrip('/')}/{login_path.lstrip('/')}"
    comp = company_code or config.TEST_COMPANY

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
        return ToolResult(
            ok=False,
            error=f"로그인 실패 (HTTP {resp.status_code}): {err_msg[:400]}",
        )

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
) -> str:
    """결과 머리 태그 — 예: [AssetERP_1 · tenant=admin · company=kfstest · trace=95694936e2a3b376]"""
    parts = []
    if base_url:
        parsed = urlparse(base_url)
        path_part = parsed.path.strip("/")
        parts.append(path_part.split("/")[-1] if path_part else (parsed.netloc or "default"))
    if tenant:
        parts.append(f"tenant={tenant}")
    if company_code:
        parts.append(f"company={company_code}")
    if trace_id:
        parts.append(f"trace={trace_id}")
    return f"[{' · '.join(parts)}]" if parts else ""


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
) -> str:
    """응답을 토큰 절약형 1~4줄 요약으로 가공한다."""
    def _finalize(s: str) -> str:
        if mask:
            from yunhee.tools.log_reader import mask_sensitive

            s, _ = mask_sensitive(s, enabled=True)
        return s

    duration_sec = f"{duration_ms / 1000:.2f}s"
    lines = []
    tag = header_tag(base_url, tenant, company_code, trace_id=trace_id)
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
) -> ToolResult:
    """인증 세션을 사용하여 API를 호출하고 결과를 요약 반환한다.
    
    안전 원칙:
    - 최초 로그인 시도 실패 시 즉시 중단 (더미 요청으로 401을 발생시키지 않음).
    - 저장된 기존 세션이 만료되어 401이 난 경우에만 세션을 삭제하고 1회 재로그인 시도.
    - 재로그인이 실패하면 즉시 실패로 중단하여 계정 잠금(5회 실패 락) 위험 원천 차단.
    """
    import time

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

    try:
        user, pw, user_info = resolve_user_credentials(as_role)
    except ValueError as exc:
        return ToolResult(ok=False, error=str(exc))

    comp = company_code or config.TEST_COMPANY
    session = _load_session(user, base_url, tenant, comp)
    had_existing_session = session is not None
    if session and session.get("user_info"):
        user_info = session.get("user_info")

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
        )
        if not login_res.ok:
            # 로그인 실패 시 실패 메시지를 숨기지 않고 즉시 반환하여 중단!
            return ToolResult(ok=False, error=login_res.error)
        session = login_res.data
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

    # 기존에 저장되어 있던 세션이 만료되어 401이 뜬 경우에만 1회 재로그인 시도
    if resp.status_code == 401 and auto_login and had_existing_session:
        _clear_session(user, base_url, tenant, comp)
        login_res = login(
            base_url=base_url,
            user=user,
            password=pw,
            login_path=login_path,
            company_code=comp,
            tenant=tenant,
            user_info=user_info,
        )
        if not login_res.ok:
            # 재로그인 실패 시 추가 요청을 하지 않고 즉시 실패 반환 (계정 잠금 방지)
            return ToolResult(ok=False, error=f"세션 만료 후 재로그인 실패: {login_res.error}")

        session = login_res.data
        if session and session.get("user_info"):
            user_info = session.get("user_info")
        new_headers = dict(session.get("headers", {}))
        new_headers.update(_tenant_headers(base_url, tenant))
        if form_fields:
            new_headers.pop("Content-Type", None)
            new_headers.pop("content-type", None)

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
    )
    return ToolResult(
        ok=resp.is_success,
        data={
            "status_code": resp.status_code,
            "duration_ms": duration_ms,
            "text": resp.text,
            "summary": summary,
            "trace_id": trace_id,
            "user_info": user_info,
        },
        error=None if resp.is_success else f"HTTP {resp.status_code}",
    )
