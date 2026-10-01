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


def _get_session_path(user: str, base_url: str, tenant: str | None = None) -> Path:
    parsed = urlparse(base_url)
    host_part = _safe_name(parsed.netloc or parsed.path or "default")
    if tenant:
        filename = f"{host_part}_{_safe_name(tenant)}_{_safe_name(user)}.json"
    else:
        filename = f"{host_part}_{_safe_name(user)}.json"
    return get_sessions_dir() / filename


def _tenant_headers(base_url: str, tenant: str | None) -> dict[str, str]:
    """테넌트가 지정된 경우 OMS TenantResolver가 판정할 수 있도록 Host 헤더를 구성한다."""
    if not tenant:
        return {}
    port = urlparse(base_url).port
    host = config.API_TENANT_HOST.format(tenant=tenant)
    return {"Host": f"{host}:{port}" if port else host}


def _get_account_credentials(role: str) -> tuple[str, str]:
    """admin 또는 user 역할에 따른 기본 계정/비밀번호를 환경변수에서 찾는다."""
    if role.lower() == "admin":
        user = os.getenv("YUNHEE_TEST_ADMIN_USER", config.TEST_ADMIN_USER)
        pw = os.getenv("YUNHEE_TEST_ADMIN_PASS", config.TEST_ADMIN_PASS)
    else:
        user = os.getenv("YUNHEE_TEST_USER", "user")
        pw = os.getenv("YUNHEE_TEST_PASS", "user1234!")
    return user, pw


def _load_session(user: str, base_url: str, tenant: str | None = None) -> dict[str, Any] | None:
    session_file = _get_session_path(user, base_url, tenant)
    if not session_file.exists():
        return None
    try:
        return json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _save_session(user: str, base_url: str, cookies: dict, headers: dict, tenant: str | None = None) -> None:
    session_file = _get_session_path(user, base_url, tenant)
    data = {"cookies": cookies, "headers": headers}
    session_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _clear_session(user: str, base_url: str, tenant: str | None = None) -> None:
    session_file = _get_session_path(user, base_url, tenant)
    if session_file.exists():
        try:
            session_file.unlink()
        except Exception:  # noqa: BLE001, S110
            pass


def login(
    base_url: str = config.API_BASE_URL,
    user: str = "admin",
    password: str = "1111",
    login_path: str = config.API_LOGIN_PATH,
    company_code: str | None = None,
    tenant: str | None = None,
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
    # 토큰이 본문에 있으면 Authorization 헤더 보관
    try:
        data = resp.json()
        token = data.get("token") or data.get("accessToken") or (data.get("data") or {}).get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    except Exception:  # noqa: BLE001, S110
        pass

    _save_session(user, base_url, cookies, headers, tenant=tenant)
    return ToolResult(ok=True, data={"cookies": cookies, "headers": headers})


def summarize_response(status_code: int, text: str, duration_ms: int, tenant: str | None = None) -> str:
    """응답을 토큰 절약형 1~4줄 요약으로 가공한다."""
    duration_sec = f"{duration_ms / 1000:.2f}s"
    tenant_suffix = f" [tenant={tenant}]" if tenant else ""
    lines = [f"HTTP {status_code} ({duration_sec}){tenant_suffix}"]

    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        # JSON이 아닌 경우
        preview = text.strip()[:200]
        if preview:
            lines.append(f"Content: {preview}")
        return "\n".join(lines)

    target_list = None

    # 1. 공통 응답 봉투(success, code, data) 언래핑
    if isinstance(data, dict) and {"success", "code", "data"} <= data.keys():
        if data.get("success") is False:
            lines.append(f"Error: {data.get('code')} {data.get('message') or ''}".rstrip())
            return "\n".join(lines)
        lines.append(f"Status: {data.get('code', 'OK')}")
        body = data["data"]
        if isinstance(body, list):
            target_list = body
        elif isinstance(body, dict):
            lines.append(f"Fields ({len(body)}): [{', '.join(list(body)[:15])}]")
            lines.append(f"Data: {json.dumps(body, ensure_ascii=False)[:250]}")
            return "\n".join(lines)
        else:  # 0, "abc", true, null
            lines.append(f"Data: {json.dumps(body, ensure_ascii=False)}")
            return "\n".join(lines)
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
            return "\n".join(lines)

    if target_list is not None:
        lines.append(f"Rows: {len(target_list)}")
        if target_list and isinstance(target_list[0], dict):
            first_keys = list(target_list[0].keys())
            lines.append(f"Fields ({len(first_keys)}): [{', '.join(first_keys[:15])}]")
            first_row_preview = json.dumps(target_list[0], ensure_ascii=False)
            lines.append(f"First row: {first_row_preview[:250]}")
    return "\n".join(lines)


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
    auto_login: bool = True,
) -> ToolResult:
    """인증 세션을 사용하여 API를 호출하고 결과를 요약 반환한다.
    
    안전 원칙:
    - 최초 로그인 시도 실패 시 즉시 중단 (더미 요청으로 401을 발생시키지 않음).
    - 저장된 기존 세션이 만료되어 401이 난 경우에만 세션을 삭제하고 1회 재로그인 시도.
    - 재로그인이 실패하면 즉시 실패로 중단하여 계정 잠금(5회 실패 락) 위험 원천 차단.
    """
    user, pw = _get_account_credentials(as_role)
    session = _load_session(user, base_url, tenant)
    had_existing_session = session is not None

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    # 세션이 없고 자동 로그인이 켜져 있으면 최초 로그인 시도
    if not session and auto_login:
        login_res = login(
            base_url=base_url,
            user=user,
            password=pw,
            login_path=login_path,
            company_code=company_code,
            tenant=tenant,
        )
        if not login_res.ok:
            # 로그인 실패 시 실패 메시지를 숨기지 않고 즉시 반환하여 중단!
            return ToolResult(ok=False, error=login_res.error)
        session = login_res.data

    cookies = (session or {}).get("cookies", {})
    headers = dict((session or {}).get("headers", {}))
    headers.update(_tenant_headers(base_url, tenant))

    import time

    start = time.perf_counter()
    try:
        resp = httpx.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,
            cookies=cookies,
            headers=headers,
            timeout=15.0,
        )
        duration_ms = int((time.perf_counter() - start) * 1000)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"API 요청 실패 ({method} {url}): {exc}")

    # 기존에 저장되어 있던 세션이 만료되어 401이 뜬 경우에만 1회 재로그인 시도
    if resp.status_code == 401 and auto_login and had_existing_session:
        _clear_session(user, base_url, tenant)
        login_res = login(
            base_url=base_url,
            user=user,
            password=pw,
            login_path=login_path,
            company_code=company_code,
            tenant=tenant,
        )
        if not login_res.ok:
            # 재로그인 실패 시 추가 요청을 하지 않고 즉시 실패 반환 (계정 잠금 방지)
            return ToolResult(ok=False, error=f"세션 만료 후 재로그인 실패: {login_res.error}")

        session = login_res.data
        new_headers = dict(session.get("headers", {}))
        new_headers.update(_tenant_headers(base_url, tenant))

        try:
            resp = httpx.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_body,
                cookies=session.get("cookies", {}),
                headers=new_headers,
                timeout=15.0,
            )
            duration_ms = int((time.perf_counter() - start) * 1000)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(ok=False, error=f"재시도 요청 실패: {exc}")

    summary = summarize_response(resp.status_code, resp.text, duration_ms, tenant=tenant)
    return ToolResult(
        ok=resp.is_success,
        data={
            "status_code": resp.status_code,
            "duration_ms": duration_ms,
            "text": resp.text,
            "summary": summary,
        },
        error=None if resp.is_success else f"HTTP {resp.status_code}",
    )
