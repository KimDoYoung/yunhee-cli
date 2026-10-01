import json
import os
from pathlib import Path
from typing import Any

import httpx

from yunhee import config
from yunhee.tools.base import ToolResult

DEFAULT_API_BASE = os.getenv("YUNHEE_API_BASE_URL", "http://localhost:8082/OMS")
SESSION_DIR_NAME = ".yunhee/sessions"


def get_sessions_dir() -> Path:
    s_dir = config.WORK_DIR / SESSION_DIR_NAME
    s_dir.mkdir(parents=True, exist_ok=True)
    return s_dir


def _get_account_credentials(role: str) -> tuple[str, str]:
    """admin 또는 user 역할에 따른 기본 계정/비밀번호를 환경변수에서 찾는다."""
    if role.lower() == "admin":
        user = os.getenv("YUNHEE_TEST_ADMIN_USER", "admin")
        pw = os.getenv("YUNHEE_TEST_ADMIN_PASS", "admin1234!")
    else:
        user = os.getenv("YUNHEE_TEST_USER", "user")
        pw = os.getenv("YUNHEE_TEST_PASS", "user1234!")
    return user, pw


def _load_session(user: str) -> dict[str, Any] | None:
    session_file = get_sessions_dir() / f"{user}.json"
    if not session_file.exists():
        return None
    try:
        return json.loads(session_file.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None


def _save_session(user: str, cookies: dict, headers: dict) -> None:
    session_file = get_sessions_dir() / f"{user}.json"
    data = {"cookies": cookies, "headers": headers}
    session_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def login(
    base_url: str = DEFAULT_API_BASE,
    user: str = "admin",
    password: str = "admin1234!",
    login_path: str = "/api/v1/auth/login",
) -> ToolResult:
    """로그인 엔드포인트를 호출하여 쿠키 및 토큰을 세션 파일에 저장한다."""
    url = f"{base_url.rstrip('/')}/{login_path.lstrip('/')}"
    try:
        resp = httpx.post(
            url,
            json={"username": user, "password": password},
            timeout=10.0,
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"로그인 연결 실패 ({url}): {exc}")

    if resp.status_code != 200:
        return ToolResult(
            ok=False,
            error=f"로그인 실패 (HTTP {resp.status_code}): {resp.text[:300]}",
        )

    cookies = dict(resp.cookies)
    headers = {}
    # 토큰이 본문에 있으면 Authorization 헤더 보관
    try:
        data = resp.json()
        token = data.get("token") or data.get("accessToken") or (data.get("data") or {}).get("token")
        if token:
            headers["Authorization"] = f"Bearer {token}"
    except Exception:  # noqa: BLE001, S110
        pass

    _save_session(user, cookies, headers)
    return ToolResult(ok=True, data={"cookies": cookies, "headers": headers})


def summarize_response(status_code: int, text: str, duration_ms: int) -> str:
    """응답을 토큰 절약형 1~4줄 요약으로 가공한다."""
    duration_sec = f"{duration_ms / 1000:.2f}s"
    lines = [f"HTTP {status_code} ({duration_sec})"]

    try:
        data = json.loads(text)
    except Exception:  # noqa: BLE001
        # JSON이 아닌 경우
        preview = text.strip()[:200]
        if preview:
            lines.append(f"Content: {preview}")
        return "\n".join(lines)

    target_list = None
    if isinstance(data, list):
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
    base_url: str = DEFAULT_API_BASE,
    as_role: str = "admin",
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    auto_login: bool = True,
) -> ToolResult:
    """인증 세션을 사용하여 API를 호출하고 결과를 요약 반환한다."""
    user, pw = _get_account_credentials(as_role)
    session = _load_session(user)

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"

    # 세션이 없고 자동 로그인이 켜져 있으면 최초 로그인 시도
    if not session and auto_login:
        login_res = login(base_url, user, pw)
        if login_res.ok:
            session = login_res.data
        else:
            # 로그인 실패해도 그냥 호출해볼 수 있게 계속 진행
            session = {"cookies": {}, "headers": {}}

    cookies = (session or {}).get("cookies", {})
    headers = (session or {}).get("headers", {})

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

    # 만약 401이고 자동 로그인이 켜져 있다면 1회 재로그인 시도
    if resp.status_code == 401 and auto_login:
        login_res = login(base_url, user, pw)
        if login_res.ok:
            session = login_res.data
            try:
                resp = httpx.request(
                    method=method.upper(),
                    url=url,
                    params=params,
                    json=json_body,
                    cookies=session.get("cookies", {}),
                    headers=session.get("headers", {}),
                    timeout=15.0,
                )
                duration_ms = int((time.perf_counter() - start) * 1000)
            except Exception as exc:  # noqa: BLE001
                return ToolResult(ok=False, error=f"재시도 요청 실패: {exc}")

    summary = summarize_response(resp.status_code, resp.text, duration_ms)
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
