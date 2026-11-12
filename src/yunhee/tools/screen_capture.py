"""Playwright 기반 TOBE 화면 및 팝업 자동 캡처 도구 (yunhee screen-capture).

LLM을 개입시키지 않고 결정적(Deterministic) DOM 요소 탐색을 통해:
1. login=company/user/pw 파싱 및 서브도메인 테넌트 URL 구성
2. 사전 API 탐색으로 겸직(Emp04_Lookup_AddTitleList) 목록 및 대상 화면(screen-id) 보유 겸직 자동 판별
3. 브라우저 로그인 및 겸직선택·출퇴근 팝업 자동 통과
4. TopBar 화면번호 입력(Enter) 또는 FlexLayout 모델 주입(Deeplink)으로 화면 오픈
5. 조회 줄(SearchBar) 조건 지정(--range / --set) 적용 후 [조회] 클릭
6. 초기 화면 → [조회] 클릭 → 첫 행 선택 → 서브 탭 순회 → 팝업/Lookup 모달 오픈 순으로 캡처 저장
7. 텍스트 품질 신호(그리드 행수/헤더 줄바꿈/빈 그리드, 버튼 비활성, 가로스크롤, 팝업 미오픈 사유, 에러) 수집
"""

from __future__ import annotations

import json
import re
import struct
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from yunhee import config
from yunhee.tools.api_client import _tenant_headers, resolve_user_credentials
from yunhee.tools.base import ToolResult

# 클릭 금지 버튼 키워드 (데이터 변경, 삭제, 파일 다운로드, 단순 행 조작, 타 화면 이동 등)
DANGEROUS_BUTTON_KEYWORDS: tuple[str, ...] = (
    "저장",
    "삭제",
    "행추가",
    "행삭제",
    "취소",
    "확정",
    "승인",
    "반려",
    "상신",
    "결재",
    "마감",
    "엑셀",
    "다운로드",
    "양식",
    "템플릿",
    "업로드",
    "파일선택",
    "인쇄",
    "출력",
    "초기화",
    "발송",
    "전송",
    "생성",
    "복사",
    "일괄",
    "집계",
    "배치",
    "가져오기",
    "내보내기",
    "잠금",
    "해제",
    "전체선택",
    "전체해제",
    "펼치기",
    "접기",
    "적용",
    "실행",
    "처리",
    "반영",
    "바로가기",
)

# --click-all 시에도 조회/초기화/탭이동 버튼은 팝업 순회에서 제외
ALWAYS_SKIP_POPUP_KEYWORDS: tuple[str, ...] = (
    "조회",
    "검색",
    "초기화",
    "바로가기",
)

SEARCH_BUTTON_KEYWORDS: tuple[str, ...] = ("조회", "검색", "조회하기", "새로고침")

VIEWPORT_PRESETS: dict[str, tuple[int, int]] = {
    "720p": (1280, 720),
    "hd": (1280, 720),
    "810p": (1440, 810),
    "1080p": (1920, 1080),
    "fhd": (1920, 1080),
}


@dataclass
class LoginSpec:
    company: str
    user: str
    password: str


@dataclass
class ScreenTarget:
    requested_id: str
    menu_no: str | None = None
    code: str | None = None
    title: str | None = None
    class_nm: str | None = None
    in_user_menu: bool = False
    selected_add_person_id: int | None = None
    selected_org_name: str | None = None
    selected_title_name: str | None = None

    @property
    def folder_name(self) -> str:
        """--out 하위에 생성할 화면별 폴더명."""
        parts: list[str] = []
        if self.menu_no:
            parts.append(_safe_filename(self.menu_no))
        if self.class_nm and self.class_nm != self.menu_no:
            parts.append(_safe_filename(self.class_nm))
        if not parts:
            parts.append(_safe_filename(self.requested_id))
        return "_".join(parts)


@dataclass
class CaptureItem:
    step: str
    filename: str
    path: str
    description: str
    boxes: str | None = None


@dataclass
class CaptureReport:
    screen_id: str
    folder_name: str
    output_dir: str
    url: str
    company: str
    user: str
    selected_title: str | None = None
    open_method: str = "topbar"
    grid_rows_after_search: int = 0
    captures: list[CaptureItem] = field(default_factory=list)
    skipped_buttons: list[str] = field(default_factory=list)
    console_errors: list[str] = field(default_factory=list)
    api_failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    search_conditions: dict[str, Any] = field(default_factory=dict)
    grids: list[dict[str, Any]] = field(default_factory=list)
    buttons: list[dict[str, Any]] = field(default_factory=list)
    horizontal_scroll: dict[str, bool] = field(
        default_factory=lambda: {"page": False, "grids": False, "any": False}
    )
    popup_traversal: dict[str, Any] = field(default_factory=dict)
    anomalies: list[str] = field(default_factory=list)
    elapsed_sec: float = 0.0


def _safe_filename(text: str, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^\w가-힣\-]", "_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return (cleaned or "unnamed")[:max_len]


def normalize_label_text(text: str) -> str:
    """조회 줄 라벨 텍스트 정규화 (앞 기호 ▼/▶/* 제거, 뒤 콜론 : 제거, 공백 정리)."""
    s = (text or "").strip()
    s = re.sub(r"^[▼▶■●*·\s]+", "", s)
    s = re.sub(r"[:：]\s*$", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_range_spec(range_str: str | None) -> tuple[str, str] | None:
    """'--range 2025-01-01~2026-12-31' 형식을 (start_date, end_date)로 파싱한다."""
    if not range_str or not range_str.strip():
        return None
    raw = range_str.strip()
    if "~" in raw:
        parts = [p.strip() for p in raw.split("~", 1)]
    elif ".." in raw:
        parts = [p.strip() for p in raw.split("..", 1)]
    else:
        raise ValueError(
            f"잘못된 --range 형식입니다: '{range_str}' (예: 2025-01-01~2026-12-31)"
        )
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise ValueError(
            f"잘못된 --range 형식입니다: '{range_str}' (시작일~종료일 두 값을 모두 지정하세요)"
        )
    return parts[0], parts[1]


def parse_set_specs(set_args: list[str] | None) -> list[dict[str, Any]]:
    """'--set 승인기간=2025-01-01~2025-12-31 --set 구분#2=일반' 목록을 파싱한다."""
    result: list[dict[str, Any]] = []
    for item in set_args or []:
        raw = (item or "").strip()
        if not raw:
            continue
        if "=" not in raw:
            raise ValueError(
                f"잘못된 --set 형식입니다: '{raw}' (예: --set 라벨=값)"
            )
        raw_key, val = raw.split("=", 1)
        raw_key = raw_key.strip()
        val = val.strip()
        m = re.match(r"^(.*)#(\d+)$", raw_key)
        if m:
            base_label = normalize_label_text(m.group(1))
            occurrence = max(1, int(m.group(2)))
        else:
            base_label = normalize_label_text(raw_key)
            occurrence = 1
        if not base_label:
            raise ValueError(f"잘못된 --set 라벨입니다: '{raw}'")
        result.append(
            {
                "raw_key": raw_key,
                "label": base_label,
                "occurrence": occurrence,
                "value": val,
            }
        )
    return result


def parse_viewport_spec(viewport: str) -> tuple[int, int]:
    """뷰포트 문자열(1920x1080, 1440x810, 1280x720, 720p, 810p, 1080p 등)을 파싱한다."""
    raw = (viewport or "").strip().lower()
    if raw in VIEWPORT_PRESETS:
        return VIEWPORT_PRESETS[raw]
    vp_parts = raw.split("x")
    if len(vp_parts) != 2 or not vp_parts[0].isdigit() or not vp_parts[1].isdigit():
        raise ValueError(
            f"잘못된 --viewport 형식입니다: '{viewport}' (예: 1920x1080, 1440x810, 1280x720)"
        )
    return int(vp_parts[0]), int(vp_parts[1])


def parse_login_spec(
    login_arg: str | None = None,
    extra_args: list[str] | None = None,
) -> LoginSpec:
    """'login=kfstest/104/1111' 또는 'kfstest/104/1111' 또는 key=value 인자들을 파싱한다."""
    raw = (login_arg or "").strip()

    kv_company: str | None = None
    kv_user: str | None = None
    kv_pw: str | None = None

    for token in extra_args or []:
        t = token.strip()
        if t.startswith("login="):
            raw = t.split("=", 1)[1].strip()
        elif t.startswith(("company-id=", "company=")):
            kv_company = t.split("=", 1)[1].strip()
        elif t.startswith(("user-id=", "user=")):
            kv_user = t.split("=", 1)[1].strip()
        elif t.startswith(("user-pw=", "pw=", "password=")):
            kv_pw = t.split("=", 1)[1].strip()

    if raw.startswith("login="):
        raw = raw.split("=", 1)[1].strip()

    default_company = config.TEST_COMPANY or config.API_DEFAULT_TENANT or "kfstest"
    default_user = config.TEST_ADMIN_USER or "104"
    default_pw = config.TEST_ADMIN_PASS or "1111"

    if raw:
        parts = [p.strip() for p in raw.split("/")]
        if len(parts) >= 3:
            return LoginSpec(
                company=parts[0] or default_company,
                user=parts[1] or default_user,
                password=parts[2],
            )
        if len(parts) == 2:
            comp, usr = parts[0] or default_company, parts[1] or default_user
            pw = _resolve_password_fallback(usr, default_pw)
            return LoginSpec(company=comp, user=usr, password=pw)
        if len(parts) == 1 and parts[0]:
            return LoginSpec(
                company=default_company,
                user=parts[0],
                password=_resolve_password_fallback(parts[0], default_pw),
            )

    if kv_company or kv_user or kv_pw:
        usr = kv_user or default_user
        pw = kv_pw or _resolve_password_fallback(usr, default_pw)
        return LoginSpec(company=kv_company or default_company, user=usr, password=pw)

    return LoginSpec(company=default_company, user=default_user, password=default_pw)


def _resolve_password_fallback(user: str, default_pw: str) -> str:
    try:
        _, pw, _ = resolve_user_credentials(user)
        if pw and pw != "None":
            return pw
    except Exception:  # noqa: BLE001, S110
        pass
    return default_pw


def build_tenant_url(base_url: str, company: str) -> str:
    """base_url(예: localhost:8082/AssetERP)에 테넌트 서브도메인(예: kfstest.localhost)을 입힌다."""
    raw = base_url.strip()
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = parsed.hostname or "localhost"
    port = parsed.port

    if company and host in ("localhost", "127.0.0.1"):
        tenant_host = config.API_TENANT_HOST.format(tenant=company)
    else:
        tenant_host = host

    netloc = f"{tenant_host}:{port}" if port else tenant_host
    path = parsed.path or "/AssetERP"
    return urlunparse((parsed.scheme or "http", netloc, path, "", "", ""))


def build_local_api_url(base_url: str) -> str:
    """httpx 호출용 로컬 베이스 URL (호스트는 localhost로 유지하고 Host 헤더로 테넌트 전달)."""
    raw = base_url.strip()
    if "://" not in raw:
        raw = f"http://{raw}"
    parsed = urlparse(raw)
    host = parsed.hostname or "localhost"
    if host.endswith(".localhost"):
        host = "localhost"
    port = parsed.port
    netloc = f"{host}:{port}" if port else host
    path = (parsed.path or "/AssetERP").rstrip("/")
    return urlunparse((parsed.scheme or "http", netloc, path, "", "", ""))


def is_safe_popup_button(label: str, click_all: bool = False) -> bool:
    """버튼 텍스트가 팝업/모달 탐색용으로 클릭해도 안전한지 판별한다.

    click_all=False(기본): DANGEROUS_BUTTON_KEYWORDS가 포함된 버튼은 절대 클릭하지 않는다.
    click_all=True: 조회/초기화/바로가기를 제외한 모든 활성 버튼을 클릭한다(라우트 가드는 유지).
    """
    text = re.sub(r"\s+", "", label or "")
    if not text:
        return False
    if text in SEARCH_BUTTON_KEYWORDS:
        return False
    base_text = re.sub(r"\(\d+건?\)$", "", text)
    if not base_text:
        return False
    for kw in ALWAYS_SKIP_POPUP_KEYWORDS:
        if kw in base_text:
            return False
    if click_all:
        return True
    for kw in DANGEROUS_BUTTON_KEYWORDS:
        if kw in base_text:
            return False
    return True


def _load_registered_screens() -> dict[str, str]:
    """TOBE frontend/src/pages/screens.ts 에서 등록된 화면 클래스명 목록(소문자->원래이름)을 추출한다."""
    candidates = [
        config.TOBE_SRC_DIR / "frontend" / "src" / "pages" / "screens.ts",
        config.WORK_DIR / "frontend" / "src" / "pages" / "screens.ts",
        config.WORK_DIR / "AssetERP" / "frontend" / "src" / "pages" / "screens.ts",
    ]
    result: dict[str, str] = {}
    for p in candidates:
        if p.is_file():
            try:
                content = p.read_text(encoding="utf-8", errors="replace")
                m = re.search(
                    r"export\s+const\s+SCREENS\b[^{]*\{(.*)\}",
                    content,
                    flags=re.DOTALL,
                )
                body = m.group(1) if m else content
                for ident in re.findall(
                    r"\b([A-Za-z0-9]+_(?:Tab|Page|Edit|Lookup|Popup)_[A-Za-z0-9_]+)\b",
                    body,
                ):
                    result[ident.lower()] = ident
                if result:
                    return result
            except OSError:
                continue
    return result


def _find_screen_in_menus(
    menus: list[dict[str, Any]], screen_id: str
) -> dict[str, str] | None:
    """메뉴 트리(MenuLevel_1[])에서 menuNo, classNm, code, title 순으로 일치하는 메뉴 항목을 찾는다."""
    target = screen_id.strip().lower()
    if not target:
        return None

    all_items: list[dict[str, str]] = []
    for m1 in menus:
        for grp in m1.get("groups") or []:
            all_items.extend(grp.get("items") or [])

    for item in all_items:
        menu_no = str(item.get("menuNo") or "").strip()
        class_nm = str(item.get("classNm") or "").strip()
        code = str(item.get("code") or "").strip()
        if target in (menu_no.lower(), class_nm.lower(), code.lower()):
            return item

    for item in all_items:
        title = str(item.get("title") or "").strip()
        if title.lower() == target:
            return item

    for item in all_items:
        class_nm = str(item.get("classNm") or "").strip()
        menu_no = str(item.get("menuNo") or "").strip()
        if target in class_nm.lower() or (menu_no and target == menu_no.lower()):
            return item

    return None


def _count_menus(menus: list[dict[str, Any]]) -> int:
    total = 0
    for m1 in menus:
        for grp in m1.get("groups") or []:
            total += len(grp.get("items") or [])
    return total


def _lookup_menu_from_db(screen_id: str) -> dict[str, str] | None:
    """권한 메뉴에서 못 찾은 경우 DB sys06_menu에서 menu_no / class_nm 정보를 보조 조회한다."""
    try:
        import psycopg
        from psycopg.rows import dict_row

        from yunhee.tools.sql_runner import get_connection_string

        db_url = get_connection_string(None)
        if not db_url:
            return None
        with psycopg.connect(db_url, autocommit=True) as conn:
            conn.read_only = True
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT sys06_menu_id::text AS code,
                           sys06_menu_nm AS title,
                           sys06_menu_no AS menu_no,
                           sys06_class_nm AS class_nm
                    FROM sys06_menu
                    WHERE LOWER(sys06_menu_no) = LOWER(%s)
                       OR LOWER(sys06_class_nm) = LOWER(%s)
                    ORDER BY sys06_menu_no NULLS LAST
                    LIMIT 1;
                    """,
                    (screen_id.strip(), screen_id.strip()),
                )
                row = cur.fetchone()
                if row:
                    return {
                        "code": str(row.get("code") or screen_id),
                        "title": str(row.get("title") or screen_id),
                        "menuNo": str(row.get("menu_no") or ""),
                        "classNm": str(row.get("class_nm") or ""),
                    }
    except Exception:  # noqa: BLE001, S110
        pass
    return None


def preflight_session_and_screen(
    base_url: str,
    login_spec: LoginSpec,
    screen_id: str,
    preferred_title: str | None = None,
) -> tuple[ScreenTarget, dict[str, str], dict[str, Any]]:
    """백엔드 API를 통해 로그인 + 겸직 목록 확인 + 대상 화면 보유 겸직으로 전환 후 쿠키/유저정보를 반환한다."""
    local_base = build_local_api_url(base_url)
    headers = _tenant_headers(local_base, login_spec.company)
    target = ScreenTarget(requested_id=screen_id)
    registered_screens = _load_registered_screens()

    with httpx.Client(base_url=local_base, headers=headers, timeout=10.0) as client:
        login_resp = client.post(
            "/api/auth/login",
            json={
                "username": login_spec.user,
                "password": login_spec.password,
                "companyCode": login_spec.company,
            },
        )
        if login_resp.status_code != 200:
            try:
                err_body = login_resp.json()
                err_msg = err_body.get("message") or login_resp.text[:300]
            except Exception:  # noqa: BLE001
                err_msg = login_resp.text[:300]
            raise RuntimeError(f"로그인 실패 (HTTP {login_resp.status_code}): {err_msg}")

        login_json = login_resp.json()
        if not login_json.get("success", True):
            raise RuntimeError(f"로그인 실패: {login_json.get('message')}")

        user_data: dict[str, Any] = login_json.get("data") or {}
        initial_user_id = user_data.get("userId")

        add_titles: list[dict[str, Any]] = []
        if isinstance(initial_user_id, int) and initial_user_id > 0:
            try:
                at_resp = client.get("/api/v1/emp/add-titles/login-list")
                if at_resp.status_code == 200:
                    add_titles = (at_resp.json().get("data")) or []
            except Exception:  # noqa: BLE001
                add_titles = []

        current_menus: list[dict[str, Any]] = []
        try:
            m_resp = client.get("/api/v1/sys/menus")
            if m_resp.status_code == 200:
                current_menus = m_resp.json().get("data") or []
        except Exception:  # noqa: BLE001
            current_menus = []

        main_row = next(
            (
                r
                for r in add_titles
                if r.get("addPersonId") == initial_user_id or r.get("mainTitleYn")
            ),
            None,
        )
        if main_row:
            target.selected_add_person_id = main_row.get("addPersonId")
            target.selected_org_name = main_row.get("orgFullName") or main_row.get(
                "orgName"
            )
            target.selected_title_name = main_row.get("titleName")

        if preferred_title and len(add_titles) > 1:
            pref_lower = preferred_title.strip().lower()
            matched_title = next(
                (
                    r
                    for r in add_titles
                    if pref_lower in str(r.get("addPersonId", "")).lower()
                    or pref_lower in str(r.get("orgFullName", "")).lower()
                    or pref_lower in str(r.get("orgName", "")).lower()
                    or pref_lower in str(r.get("titleName", "")).lower()
                ),
                None,
            )
            if matched_title:
                add_pid = matched_title["addPersonId"]
                if add_pid != user_data.get("userId"):
                    sw_resp = client.post(
                        "/api/auth/switch-title", json={"addPersonId": add_pid}
                    )
                    if sw_resp.status_code == 200 and sw_resp.json().get("data"):
                        user_data = sw_resp.json()["data"]
                        m_resp = client.get("/api/v1/sys/menus")
                        if m_resp.status_code == 200:
                            current_menus = m_resp.json().get("data") or []
                target.selected_add_person_id = add_pid
                target.selected_org_name = matched_title.get(
                    "orgFullName"
                ) or matched_title.get("orgName")
                target.selected_title_name = matched_title.get("titleName")

        found_item = _find_screen_in_menus(current_menus, screen_id)

        if not found_item and not preferred_title and len(add_titles) > 1:
            best_row = main_row
            best_menu_count = _count_menus(current_menus)

            for row in add_titles:
                add_pid = row.get("addPersonId")
                if not add_pid or add_pid == initial_user_id:
                    continue
                sw_resp = client.post(
                    "/api/auth/switch-title", json={"addPersonId": add_pid}
                )
                if sw_resp.status_code != 200:
                    continue
                sw_data = sw_resp.json().get("data") or {}
                m_resp = client.get("/api/v1/sys/menus")
                menus_for_row = (
                    (m_resp.json().get("data") or [])
                    if m_resp.status_code == 200
                    else []
                )
                cand = _find_screen_in_menus(menus_for_row, screen_id)
                if cand:
                    found_item = cand
                    user_data = sw_data
                    current_menus = menus_for_row
                    target.selected_add_person_id = add_pid
                    target.selected_org_name = row.get("orgFullName") or row.get(
                        "orgName"
                    )
                    target.selected_title_name = row.get("titleName")
                    break
                cnt = _count_menus(menus_for_row)
                if cnt > best_menu_count:
                    best_menu_count = cnt
                    best_row = row

            if (
                not found_item
                and best_row
                and best_row.get("addPersonId") != user_data.get("userId")
            ):
                sw_resp = client.post(
                    "/api/auth/switch-title",
                    json={"addPersonId": best_row["addPersonId"]},
                )
                if sw_resp.status_code == 200 and sw_resp.json().get("data"):
                    user_data = sw_resp.json()["data"]
                target.selected_add_person_id = best_row.get("addPersonId")
                target.selected_org_name = best_row.get("orgFullName") or best_row.get(
                    "orgName"
                )
                target.selected_title_name = best_row.get("titleName")

        if found_item:
            target.in_user_menu = True
            target.menu_no = found_item.get("menuNo") or None
            target.code = found_item.get("code") or None
            target.title = found_item.get("title") or None
            target.class_nm = found_item.get("classNm") or None
        else:
            db_item = _lookup_menu_from_db(screen_id)
            if db_item:
                target.menu_no = db_item.get("menuNo") or None
                target.code = db_item.get("code") or screen_id
                target.title = db_item.get("title") or screen_id
                target.class_nm = db_item.get("classNm") or None
            if not target.class_nm:
                exact_cls = registered_screens.get(screen_id.strip().lower())
                if exact_cls:
                    target.class_nm = exact_cls
                    target.code = exact_cls
                    target.title = exact_cls
                else:
                    for k_lower, orig_cls in registered_screens.items():
                        if screen_id.strip().lower() in k_lower:
                            target.class_nm = orig_cls
                            target.code = orig_cls
                            target.title = orig_cls
                            break

        cookies = dict(client.cookies)
        return target, cookies, user_data


def _build_flexlayout_storage_json(target: ScreenTarget | None = None) -> dict[str, Any]:
    """MainFrame이 읽는 asseterp_settings JSON 객체를 생성한다."""
    children: list[dict[str, Any]] = [
        {
            "type": "tab",
            "name": "My Page",
            "component": "mypage",
            "enableClose": False,
            "enableScrollbars": False,
            "id": "tab-mypage",
        }
    ]
    selected_idx = 0
    if target and (target.class_nm or target.menu_no):
        code = target.code or target.class_nm or target.requested_id
        title = target.title or target.class_nm or target.requested_id
        menu_no = target.menu_no or code
        class_nm = target.class_nm or target.requested_id
        children.append(
            {
                "type": "tab",
                "name": f"{menu_no} {title}".strip(),
                "component": "screen",
                "id": f"tab-{code}",
                "config": {
                    "code": code,
                    "title": title,
                    "menuNo": menu_no,
                    "classNm": class_nm,
                },
                "enableClose": True,
                "enableScrollbars": False,
            }
        )
        selected_idx = 1

    return {
        "menu23_font_size": 0,
        "font_family": "pretendard",
        "saved_layouts": [],
        "mypage_employee_collapsed": False,
        "flexlayout_model": {
            "global": {
                "tabEnableClose": True,
                "tabSetEnableMaximize": False,
                "tabSetEnableClose": True,
                "tabSetEnableCloseButton": False,
                "tabSetEnableDeleteWhenEmpty": True,
                "tabEnableRename": False,
                "tabEnableScrollbars": False,
            },
            "borders": [],
            "layout": {
                "type": "row",
                "weight": 100,
                "children": [
                    {
                        "type": "tabset",
                        "weight": 100,
                        "id": "main-tabset",
                        "selected": selected_idx,
                        "children": children,
                    }
                ],
            },
        },
    }


def _wait_ui_settled(
    page: Any,
    inflight_tracker: dict[str, int] | None = None,
    timeout_ms: int = 5000,
) -> None:
    """진행 중인 /api/ 요청과 로딩 스피너(.ant-spin-spinning, .ant-btn-loading, .ag-overlay-loading-center)가 끝날 때까지 대기한다."""
    page.wait_for_timeout(150)
    deadline = time.monotonic() + (timeout_ms / 1000.0)
    quiet_since: float | None = None

    while time.monotonic() < deadline:
        inflight = (inflight_tracker or {}).get("count", 0)
        try:
            loading_els = page.locator(
                ".ant-spin-spinning:visible, button.ant-btn-loading:visible, .ag-overlay-loading-center:visible"
            ).count()
        except Exception:  # noqa: BLE001
            loading_els = 0

        if inflight <= 0 and loading_els == 0:
            if quiet_since is None:
                quiet_since = time.monotonic()
            elif (time.monotonic() - quiet_since) >= 0.25:
                break
        else:
            quiet_since = None

        page.wait_for_timeout(100)

    page.wait_for_timeout(150)


def _dismiss_all_modals(page: Any, max_attempts: int = 5) -> None:
    """현재 화면에 떠 있는 모달/다이얼로그를 취소/아니오·닫기·X버튼·ESC 순으로 모두 닫는다."""
    for _ in range(max_attempts):
        try:
            modals = page.locator(".ant-modal-content:visible")
            if modals.count() == 0:
                return
            top_modal = modals.last

            # 1. confirm 다이얼로그는 부수효과 방지를 위해 취소/아니오 우선 클릭, 없으면 확인 클릭
            cancel_confirm = top_modal.locator(
                ".ant-modal-confirm-btns button:has-text('아니오'):visible, "
                ".ant-modal-confirm-btns button:has-text('취소'):visible"
            )
            if cancel_confirm.count() > 0:
                cancel_confirm.first.click(timeout=1500)
                page.wait_for_timeout(250)
                continue

            confirm_btns = top_modal.locator(".ant-modal-confirm-btns button:visible")
            if confirm_btns.count() > 0:
                confirm_btns.first.click(timeout=1500)
                page.wait_for_timeout(250)
                continue

            # 2. 푸터의 닫기 / 취소 버튼
            close_btn = top_modal.locator(
                "button:has-text('닫기'):visible, button:has-text('취소'):visible"
            )
            if close_btn.count() > 0:
                close_btn.first.click(timeout=1500)
                page.wait_for_timeout(250)
                continue

            # 3. 우측 상단 X (.ant-modal-close)
            x_btn = top_modal.locator(".ant-modal-close:visible")
            if x_btn.count() > 0:
                x_btn.first.click(timeout=1500)
                page.wait_for_timeout(250)
                continue

            # 4. Escape 키
            page.keyboard.press("Escape")
            page.wait_for_timeout(250)
        except Exception:  # noqa: BLE001
            break


def _pass_login_and_gates_if_visible(
    page: Any,
    login_spec: LoginSpec,
    target: ScreenTarget,
    inflight_tracker: dict[str, int] | None = None,
) -> None:
    """쿠키 주입이 안 먹혔거나 로그인/겸직선택/출퇴근 창이 뜬 경우 DOM 요소를 찾아 통과한다."""
    login_input = page.locator(
        "input#username:visible, input[placeholder*='로그인 ID']:visible"
    )
    if login_input.count() > 0:
        login_input.first.fill(login_spec.user)
        pw_input = page.locator(
            "input#password:visible, input[type='password']:visible"
        )
        if pw_input.count() > 0:
            pw_input.first.fill(login_spec.password)
        submit_btn = page.locator("button[type='submit']:visible")
        if submit_btn.count() > 0:
            submit_btn.first.click()
        _wait_ui_settled(page, inflight_tracker, 4000)

        no_btn = page.locator(
            ".ant-modal-confirm-btns button:has-text('아니오'):visible"
        )
        if no_btn.count() > 0:
            no_btn.first.click()
            _wait_ui_settled(page, inflight_tracker, 2000)

    add_title_modal = page.locator(
        ".ant-modal-content:visible:has(.ant-modal-title:has-text('로그인 선택'))"
    )
    if add_title_modal.count() > 0:
        _wait_ui_settled(page, inflight_tracker, 2500)
        rows = add_title_modal.locator(".ag-row:visible")
        if rows.count() > 0:
            clicked_row = False
            if target.selected_add_person_id is not None:
                row_by_id = add_title_modal.locator(
                    f".ag-row[row-id='{target.selected_add_person_id}']:visible"
                )
                if row_by_id.count() > 0:
                    row_by_id.first.click()
                    clicked_row = True
            if not clicked_row and target.selected_org_name:
                row_by_org = rows.filter(has_text=target.selected_org_name)
                if row_by_org.count() > 0:
                    row_by_org.first.click()
                    clicked_row = True
            if not clicked_row:
                rows.first.click()

            confirm_btn = add_title_modal.locator("button:has-text('확인'):visible")
            if confirm_btn.count() > 0:
                confirm_btn.first.click()
                _wait_ui_settled(page, inflight_tracker, 3000)

    _dismiss_all_modals(page)


# ---------------------------------------------------------------------------
# 조회 줄(SearchBar / SearchPanel / Form) 탐색 및 --range / --set 조작
# ---------------------------------------------------------------------------

_INSPECT_SEARCH_BAR_JS = """
(tabEl) => {
    // 이전 태그 정리
    tabEl.querySelectorAll('[data-yunhee-sb-wid]').forEach(el => el.removeAttribute('data-yunhee-sb-wid'));

    const isVisible = (el) => {
        if (!el || el.nodeType !== 1) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0) return false;
        const rects = el.getClientRects();
        return rects && rects.length > 0;
    };

    const normalizeLabel = (raw) => {
        let s = (raw || '').trim();
        s = s.replace(/^[▼▶■●*·\\s]+/, '');
        s = s.replace(/[:：]\\s*$/, '');
        s = s.replace(/\\s+/g, ' ').trim();
        return s;
    };

    // 1. [조회]/[검색] 버튼을 기준으로 조회 줄(SearchBar) 컨테이너들을 찾는다.
    //    편집 폼이나 모달, 그리드 내부는 제외한다.
    const searchKeywords = new Set(['조회', '검색', '조회하기', '새로고침']);
    const allBtns = Array.from(tabEl.querySelectorAll('button')).filter(b => {
        if (!isVisible(b)) return false;
        if (b.closest('.ant-modal, .ag-root-wrapper')) return false;
        const t = (b.innerText || '').replace(/\\s+/g, '');
        return searchKeywords.has(t);
    });

    const searchRoots = [];
    for (const btn of allBtns) {
        let curr = btn.parentElement;
        while (curr && curr !== tabEl) {
            const parent = curr.parentElement;
            if (!parent || parent === tabEl) break;
            const parentHasGridOrTree = parent.querySelector('.ag-root-wrapper, .ant-tree, .ant-table, .ant-splitter') !== null;
            const currHasGridOrTree = curr.querySelector('.ag-root-wrapper, .ant-tree, .ant-table, .ant-splitter') !== null;
            if (parentHasGridOrTree && !currHasGridOrTree) {
                break;
            }
            const pRect = parent.getBoundingClientRect();
            if (pRect.height > 200) {
                break;
            }
            curr = parent;
        }
        if (curr && !searchRoots.some(r => r.contains(curr) || curr.contains(r))) {
            searchRoots.push(curr);
        }
    }

    // 만약 [조회] 버튼이 없는 화면이라면, 첫 그리드 바로 위의 상단 툴바 영역(높이 <= 150)을 보조로 확인
    if (searchRoots.length === 0) {
        const firstGrid = tabEl.querySelector('.ag-root-wrapper, .ant-tree, .ant-table');
        if (firstGrid && firstGrid.parentElement) {
            const gp = firstGrid.parentElement.parentElement || firstGrid.parentElement;
            for (const child of Array.from(gp.children)) {
                if (child.contains(firstGrid)) break;
                const r = child.getBoundingClientRect();
                if (isVisible(child) && r.height > 0 && r.height <= 150) {
                    searchRoots.push(child);
                }
            }
        }
    }

    let widCounter = 0;
    const nextWid = (el) => {
        const id = 'w_' + (widCounter++);
        el.setAttribute('data-yunhee-sb-wid', id);
        return id;
    };

    const containsWidgetOrButton = (el) => {
        return el.querySelector('.ant-picker, .ant-select, .ant-checkbox-wrapper, .ant-radio-group, input, textarea, button, .ant-btn') !== null;
    };

    const tokens = [];

    const walk = (node) => {
        if (!node) return;
        if (node.nodeType === 3) { // TEXT_NODE
            const raw = (node.textContent || '').trim();
            if (!raw || raw === '◀' || raw === '▶') return;
            if (raw === '~' || raw === '-') {
                tokens.push({ type: 'sep', text: '~' });
                return;
            }
            const lbl = normalizeLabel(raw);
            if (lbl === '~' || lbl === '-') {
                tokens.push({ type: 'sep', text: '~' });
            } else if (lbl) {
                tokens.push({ type: 'label', text: lbl });
            }
            return;
        }
        if (node.nodeType !== 1) return;
        const el = node;
        if (!isVisible(el)) return;
        const tag = el.tagName.toUpperCase();
        if (tag === 'BUTTON' || tag === 'SVG' || tag === 'STYLE' || tag === 'SCRIPT' || el.classList.contains('ant-btn')) {
            return;
        }
        if (el.closest('.ag-root-wrapper, .ant-modal')) {
            return;
        }

        // Atomic Widgets
        if (el.classList.contains('ant-picker-range')) {
            tokens.push({ type: 'widget', widgetType: 'date_range', wid: nextWid(el) });
            return;
        }
        if (el.classList.contains('ant-picker')) {
            tokens.push({ type: 'widget', widgetType: 'date', wid: nextWid(el) });
            return;
        }
        if (el.classList.contains('ant-select')) {
            tokens.push({ type: 'widget', widgetType: 'select', wid: nextWid(el) });
            return;
        }
        if (el.classList.contains('ant-checkbox-wrapper')) {
            const ownLabel = normalizeLabel(el.innerText || '');
            tokens.push({ type: 'widget', widgetType: 'checkbox', wid: nextWid(el), ownLabel });
            return;
        }
        if (el.classList.contains('ant-radio-group')) {
            tokens.push({ type: 'widget', widgetType: 'radio', wid: nextWid(el) });
            return;
        }
        if (
            el.classList.contains('ant-input-affix-wrapper') ||
            el.classList.contains('ant-input-group-wrapper') ||
            el.classList.contains('ant-input-search')
        ) {
            const inp = el.querySelector('input');
            if (inp) {
                const hasSearchIcon = el.querySelector('.anticon-search, .ant-input-search-button') !== null;
                const isReadonlyLookup = inp.readOnly && (hasSearchIcon || inp.style.cursor === 'pointer' || el.style.cursor === 'pointer');
                if (isReadonlyLookup) {
                    tokens.push({ type: 'widget', widgetType: 'lookup', wid: nextWid(el) });
                } else {
                    tokens.push({ type: 'widget', widgetType: 'text', wid: nextWid(inp) });
                }
                return;
            }
        }
        if (tag === 'INPUT') {
            const typeAttr = (el.getAttribute('type') || 'text').toLowerCase();
            if (typeAttr === 'hidden') return;
            if (typeAttr === 'checkbox') {
                tokens.push({ type: 'widget', widgetType: 'checkbox', wid: nextWid(el), ownLabel: '' });
                return;
            }
            if (typeAttr === 'radio') return;
            if (el.readOnly && el.style.cursor === 'pointer') {
                tokens.push({ type: 'widget', widgetType: 'lookup', wid: nextWid(el) });
                return;
            }
            tokens.push({ type: 'widget', widgetType: 'text', wid: nextWid(el) });
            return;
        }

        // 만약 하위 요소에 위젯이나 버튼이 전혀 없다면 이 요소 전체 텍스트를 하나의 라벨 토큰으로 처리
        if (!containsWidgetOrButton(el)) {
            const raw = (el.innerText || '').trim();
            if (!raw || raw === '◀' || raw === '▶') return;
            if (raw === '~' || raw === '-') {
                tokens.push({ type: 'sep', text: '~' });
                return;
            }
            const lbl = normalizeLabel(raw);
            if (lbl === '~' || lbl === '-') {
                tokens.push({ type: 'sep', text: '~' });
            } else if (lbl) {
                tokens.push({ type: 'label', text: lbl });
            }
            return;
        }

        for (const child of Array.from(el.childNodes)) {
            walk(child);
        }
    };

    for (const root of searchRoots) {
        walk(root);
    }

    // 토큰 스트림을 필드 목록으로 결합
    const fields = [];
    let pendingLabel = null;
    let currentField = null;

    for (let i = 0; i < tokens.length; i++) {
        const tok = tokens[i];
        if (tok.type === 'label') {
            pendingLabel = tok.text;
            currentField = null;
        } else if (tok.type === 'sep') {
            // '~' 구분자는 currentField 유지
        } else if (tok.type === 'widget') {
            if (tok.widgetType === 'checkbox' && tok.ownLabel) {
                const lbl = tok.ownLabel;
                fields.push({
                    label: lbl,
                    widget_type: 'checkbox',
                    wids: [tok.wid],
                });
                if (pendingLabel === lbl) pendingLabel = null;
                currentField = null;
                continue;
            }

            // 직전 필드가 단일 date 이고 현재 위젯도 date 이면 date_range 로 병합
            if (currentField && currentField.widget_type === 'date' && currentField.wids.length === 1 && tok.widgetType === 'date') {
                currentField.widget_type = 'date_range';
                currentField.wids.push(tok.wid);
                continue;
            }

            const assignedLabel = pendingLabel || '';
            pendingLabel = null;
            currentField = {
                label: assignedLabel,
                widget_type: tok.widgetType,
                wids: [tok.wid],
            };
            fields.push(currentField);
        }
    }

    // 중복 라벨 번호 부여 (#1, #2, ...) 및 date_range_pairs 추출
    const labelCounts = {};
    const availableLabels = [];
    const dateRangePairs = [];

    for (const f of fields) {
        if (f.label) {
            const c = (labelCounts[f.label] || 0) + 1;
            labelCounts[f.label] = c;
            f.occurrence = c;
            f.display_label = c === 1 ? f.label : `${f.label}#${c}`;
            availableLabels.push(f.display_label);
        } else {
            f.occurrence = 1;
            f.display_label = '';
        }

        if (f.widget_type === 'date_range') {
            dateRangePairs.push(f.wids);
        }
    }

    return {
        search_root_count: searchRoots.length,
        fields,
        available_labels: availableLabels,
        date_range_pairs: dateRangePairs,
    };
}
"""


def _format_date_for_input(current_val: str, target_date: str) -> str:
    """현재 DatePicker input의 포맷(YYYY-MM-DD, YYYY.MM.DD, YYYY/MM/DD, YYYY-MM 등)에 맞춰 변환한다."""
    cur = (current_val or "").strip()
    tgt = target_date.strip()
    if re.match(r"^\d{4}\.\d{2}\.\d{2}$", cur) and re.match(r"^\d{4}-\d{2}-\d{2}$", tgt):
        return tgt.replace("-", ".")
    if re.match(r"^\d{4}/\d{2}/\d{2}$", cur) and re.match(r"^\d{4}-\d{2}-\d{2}$", tgt):
        return tgt.replace("-", "/")
    if re.match(r"^\d{4}-\d{2}$", cur) and len(tgt) >= 7:
        return tgt[:7]
    if re.match(r"^\d{4}\.\d{2}$", cur) and len(tgt) >= 7:
        return tgt[:7].replace("-", ".")
    return tgt


def _set_datepicker_input(page: Any, inp_locator: Any, date_str: str) -> bool:
    """단일 DatePicker <input> 요소에 날짜를 타이핑 후 Enter로 확정하고 남은 달력 팝업을 Esc로 닫는다."""
    try:
        if inp_locator.count() == 0 or not inp_locator.first.is_enabled():
            return False
        inp = inp_locator.first
        cur_val = inp.input_value() or inp.get_attribute("placeholder") or ""
        formatted = _format_date_for_input(cur_val, date_str)

        inp.click(timeout=2000)
        page.wait_for_timeout(80)
        page.keyboard.press("Control+A")
        page.keyboard.press("Backspace")
        page.keyboard.type(formatted, delay=15)
        page.keyboard.press("Enter")
        page.wait_for_timeout(120)

        # 달력 팝업이 남아 있으면 Esc로 닫기
        if page.locator(".ant-picker-dropdown:visible").count() > 0:
            page.keyboard.press("Escape")
            page.wait_for_timeout(100)
        return True
    except Exception:  # noqa: BLE001
        return False


def _set_date_range_pair(
    page: Any, active_tab: Any, wids: list[str], start_date: str, end_date: str
) -> bool:
    """date_range 위젯(두 개의 .ant-picker 또는 단일 .ant-picker-range)에 시작일~종료일을 입력한다."""
    if len(wids) == 1:
        el = active_tab.locator(f"[data-yunhee-sb-wid='{wids[0]}']")
        inputs = el.locator("input")
        if inputs.count() >= 2:
            ok1 = _set_datepicker_input(page, inputs.nth(0), start_date)
            ok2 = _set_datepicker_input(page, inputs.nth(1), end_date)
            return ok1 and ok2
        return False
    if len(wids) >= 2:
        el1 = active_tab.locator(f"[data-yunhee-sb-wid='{wids[0]}'] input")
        el2 = active_tab.locator(f"[data-yunhee-sb-wid='{wids[1]}'] input")
        ok1 = _set_datepicker_input(page, el1, start_date)
        ok2 = _set_datepicker_input(page, el2, end_date)
        return ok1 and ok2
    return False


def _set_select_widget(page: Any, select_el: Any, target_text: str) -> tuple[bool, str]:
    """AntD Select 드롭다운을 열고 텍스트가 일치하는 옵션을 클릭한다."""
    try:
        if select_el.count() == 0:
            return False, "요소 없음"
        sel = select_el.first
        cls = sel.get_attribute("class") or ""
        if "ant-select-disabled" in cls:
            return False, "비활성(disabled)"

        selector = sel.locator(".ant-select-selector")
        if selector.count() > 0:
            selector.first.click(timeout=2000)
        else:
            sel.click(timeout=2000)
        page.wait_for_timeout(200)

        dropdowns = page.locator(".ant-select-dropdown:visible")
        if dropdowns.count() == 0:
            return False, "드롭다운 열리지 않음"
        dd = dropdowns.last
        options = dd.locator(".ant-select-item-option")
        opt_count = options.count()

        want = target_text.strip()
        # 1. 정확 일치
        for i in range(opt_count):
            opt = options.nth(i)
            txt = (opt.inner_text() or "").strip()
            if txt == want:
                opt.click(timeout=2000)
                page.wait_for_timeout(120)
                return True, f"적용 완료 ({txt})"

        # 2. 부분 일치
        for i in range(opt_count):
            opt = options.nth(i)
            txt = (opt.inner_text() or "").strip()
            if want in txt:
                opt.click(timeout=2000)
                page.wait_for_timeout(120)
                return True, f"적용 완료 ({txt})"

        # 후보 목록 수집 후 닫기
        avail: list[str] = []
        for i in range(min(opt_count, 10)):
            avail.append((options.nth(i).inner_text() or "").strip())
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        return False, f"옵션 '{want}' 없음 (후보: {', '.join(avail)})"
    except Exception as exc:  # noqa: BLE001
        try:
            page.keyboard.press("Escape")
        except Exception:  # noqa: BLE001, S110
            pass
        return False, f"오류: {exc}"


def _set_checkbox_widget(cb_el: Any, val_str: str) -> tuple[bool, str]:
    """AntD Checkbox 상태를 true/false로 맞춘다."""
    try:
        if cb_el.count() == 0:
            return False, "요소 없음"
        el = cb_el.first
        want = val_str.strip().lower() in ("true", "1", "y", "yes", "on", "예", "체크")
        inp = el.locator("input[type='checkbox']")
        if inp.count() > 0:
            cur = inp.first.is_checked()
        else:
            cur = el.locator(".ant-checkbox-checked").count() > 0
        if cur != want:
            el.click(timeout=2000)
        return True, f"적용 완료 ({want})"
    except Exception as exc:  # noqa: BLE001
        return False, f"오류: {exc}"


def _set_radio_widget(radio_group_el: Any, val_str: str) -> tuple[bool, str]:
    """AntD Radio.Group 내 라벨 일치 항목을 클릭한다."""
    try:
        if radio_group_el.count() == 0:
            return False, "요소 없음"
        labels = radio_group_el.first.locator("label.ant-radio-wrapper, label.ant-radio-button-wrapper")
        want = val_str.strip()
        for i in range(labels.count()):
            lbl = labels.nth(i)
            txt = (lbl.inner_text() or "").strip()
            if txt == want or want in txt:
                lbl.click(timeout=2000)
                return True, f"적용 완료 ({txt})"
        return False, f"라디오 옵션 '{want}' 없음"
    except Exception as exc:  # noqa: BLE001
        return False, f"오류: {exc}"


def _apply_search_conditions(
    page: Any,
    active_tab: Any,
    range_spec: tuple[str, str] | None,
    set_specs: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[str]]:
    """조회 줄(SearchBar)에 --range 와 --set 조건을 순서대로 적용한다 (--set 이 --range 보다 우선)."""
    warnings: list[str] = []
    info: dict[str, Any] = {
        "available_labels": [],
        "range": None,
        "set": [],
    }

    try:
        sb_meta = active_tab.evaluate(_INSPECT_SEARCH_BAR_JS)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"조회 줄 탐색 실패: {exc}")
        return info, warnings

    available_labels: list[str] = sb_meta.get("available_labels") or []
    fields: list[dict[str, Any]] = sb_meta.get("fields") or []
    date_range_pairs: list[list[str]] = sb_meta.get("date_range_pairs") or []
    info["available_labels"] = available_labels

    # 1. --range 적용 (조회 줄의 모든 날짜 범위 쌍 채우기)
    if range_spec is not None:
        start_d, end_d = range_spec
        req_str = f"{start_d}~{end_d}"
        if not date_range_pairs:
            info["range"] = {
                "requested": req_str,
                "applied_pairs": 0,
                "status": "날짜 범위 없음",
            }
        else:
            applied = 0
            for pair in date_range_pairs:
                if _set_date_range_pair(page, active_tab, pair, start_d, end_d):
                    applied += 1
            status_str = (
                f"적용 완료 ({applied}쌍: {req_str})"
                if applied > 0
                else "날짜 범위 입력 실패(비활성 등)"
            )
            info["range"] = {
                "requested": req_str,
                "applied_pairs": applied,
                "status": status_str,
            }

    # 2. --set 적용 (--range 뒤에 실행하므로 같은 날짜 칸이라도 --set 이 우선 덮어씀)
    for spec in set_specs:
        raw_key = spec["raw_key"]
        target_label = spec["label"]
        target_occ = spec["occurrence"]
        val_str = spec["value"]

        matched_field = next(
            (
                f
                for f in fields
                if f.get("label") == target_label
                and f.get("occurrence", 1) == target_occ
            ),
            None,
        )

        if not matched_field:
            cand_str = ", ".join(available_labels) if available_labels else "없음"
            msg = f"라벨 '{raw_key}' 못 찾음. 조회 줄 후보: {cand_str}"
            warnings.append(msg)
            info["set"].append(
                {
                    "label": raw_key,
                    "value": val_str,
                    "widget": None,
                    "status": "라벨 못 찾음",
                    "message": msg,
                }
            )
            continue

        wtype = matched_field.get("widget_type")
        wids: list[str] = matched_field.get("wids") or []

        if wtype == "lookup":
            msg = f"라벨 '{raw_key}'은(는) 조회창 필드로 미지원"
            warnings.append(msg)
            info["set"].append(
                {
                    "label": raw_key,
                    "value": val_str,
                    "widget": "lookup",
                    "status": "미지원",
                }
            )
            continue

        if wtype == "date_range":
            try:
                parsed_r = parse_range_spec(val_str)
            except ValueError:
                parsed_r = None
            if not parsed_r:
                msg = f"라벨 '{raw_key}'은(는) 날짜 범위(YYYY-MM-DD~YYYY-MM-DD) 형식이 필요합니다: '{val_str}'"
                warnings.append(msg)
                info["set"].append(
                    {
                        "label": raw_key,
                        "value": val_str,
                        "widget": "date_range",
                        "status": "형식 오류",
                    }
                )
                continue
            ok = _set_date_range_pair(page, active_tab, wids, parsed_r[0], parsed_r[1])
            info["set"].append(
                {
                    "label": raw_key,
                    "value": val_str,
                    "widget": "date_range",
                    "status": "적용 완료" if ok else "입력 실패",
                }
            )
            continue

        if wtype == "date":
            s_val = val_str.split("~", 1)[0].strip() if "~" in val_str else val_str
            el_inp = active_tab.locator(f"[data-yunhee-sb-wid='{wids[0]}'] input")
            ok = _set_datepicker_input(page, el_inp, s_val)
            info["set"].append(
                {
                    "label": raw_key,
                    "value": val_str,
                    "widget": "date",
                    "status": "적용 완료" if ok else "입력 실패",
                }
            )
            continue

        if wtype == "select":
            el_sel = active_tab.locator(f"[data-yunhee-sb-wid='{wids[0]}']")
            ok, st_msg = _set_select_widget(page, el_sel, val_str)
            if not ok:
                warnings.append(f"라벨 '{raw_key}' Select 설정 실패: {st_msg}")
            info["set"].append(
                {
                    "label": raw_key,
                    "value": val_str,
                    "widget": "select",
                    "status": st_msg,
                }
            )
            continue

        if wtype == "checkbox":
            el_cb = active_tab.locator(f"[data-yunhee-sb-wid='{wids[0]}']")
            ok, st_msg = _set_checkbox_widget(el_cb, val_str)
            info["set"].append(
                {
                    "label": raw_key,
                    "value": val_str,
                    "widget": "checkbox",
                    "status": st_msg if ok else f"실패 ({st_msg})",
                }
            )
            continue

        if wtype == "radio":
            el_rg = active_tab.locator(f"[data-yunhee-sb-wid='{wids[0]}']")
            ok, st_msg = _set_radio_widget(el_rg, val_str)
            if not ok:
                warnings.append(f"라벨 '{raw_key}' Radio 설정 실패: {st_msg}")
            info["set"].append(
                {
                    "label": raw_key,
                    "value": val_str,
                    "widget": "radio",
                    "status": st_msg,
                }
            )
            continue

        # 기본: text input
        try:
            el_txt = active_tab.locator(f"[data-yunhee-sb-wid='{wids[0]}']")
            if el_txt.count() > 0 and el_txt.first.is_enabled():
                el_txt.first.click(timeout=2000)
                el_txt.first.fill(val_str)
                page.wait_for_timeout(60)
                info["set"].append(
                    {
                        "label": raw_key,
                        "value": val_str,
                        "widget": "text",
                        "status": "적용 완료",
                    }
                )
            else:
                info["set"].append(
                    {
                        "label": raw_key,
                        "value": val_str,
                        "widget": "text",
                        "status": "비활성(disabled)",
                    }
                )
        except Exception as exc:  # noqa: BLE001
            info["set"].append(
                {
                    "label": raw_key,
                    "value": val_str,
                    "widget": "text",
                    "status": f"오류 ({exc})",
                }
            )

    return info, warnings


# ---------------------------------------------------------------------------
# 화면 품질 텍스트 신호 수집 (그리드 행수/헤더 줄바꿈/빈 그리드, 버튼, 가로 스크롤)
# ---------------------------------------------------------------------------

_COLLECT_SIGNALS_JS = """
(tabEl) => {
    const isVisible = (el) => {
        if (!el || el.nodeType !== 1) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity || '1') === 0) return false;
        const rects = el.getClientRects();
        return rects && rects.length > 0;
    };

    const isEffectivelyDisabled = (el) => {
        if (el.disabled || el.hasAttribute('disabled') || el.classList.contains('ant-btn-disabled')) return true;
        let curr = el;
        while (curr && curr !== tabEl) {
            const st = window.getComputedStyle(curr);
            if (st.pointerEvents === 'none') return true;
            curr = curr.parentElement;
        }
        return false;
    };

    // 단일 줄 텍스트 폭 측정용 캔버스
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const measureTextWidth = (text, font) => {
        if (!ctx) return 0;
        ctx.font = font || '12px sans-serif';
        return ctx.measureText(text).width;
    };

    // 1. 그리드별 신호 수집
    const gridEls = Array.from(tabEl.querySelectorAll('.ag-root-wrapper')).filter(g => isVisible(g) && !g.closest('.ant-modal'));
    const grids = gridEls.map((gEl, idx) => {
        // 행 수 계산 (가상 스크롤 대응: DOM row-index 집합과 aria-rowcount 비교)
        const rowIndices = new Set(
            Array.from(gEl.querySelectorAll('.ag-center-cols-container .ag-row[row-index], .ag-row[row-index]'))
                .filter(r => !r.closest('.ag-floating-top, .ag-floating-bottom'))
                .map(r => r.getAttribute('row-index'))
                .filter(Boolean)
        );
        let rowCount = rowIndices.size;
        const gridRoot = gEl.querySelector('.ag-root[role="grid"], .ag-root[role="treegrid"]');
        if (gridRoot && rowCount > 0) {
            const ariaCount = parseInt(gridRoot.getAttribute('aria-rowcount') || '0', 10);
            const headerRowCount = gEl.querySelectorAll('.ag-header-row').length || 1;
            if (ariaCount - headerRowCount > rowCount) {
                rowCount = ariaCount - headerRowCount;
            }
        }

        // 헤더 줄바꿈 / 잘림 감지
        const wrappedHeaders = [];
        const headerCells = Array.from(gEl.querySelectorAll('.ag-header-cell')).filter(isVisible);
        for (const hCell of headerCells) {
            const textEl = hCell.querySelector('.ag-header-cell-text') || hCell.querySelector('.ag-header-cell-label');
            if (!textEl) continue;
            const rawText = (textEl.innerText || '').trim();
            if (!rawText) continue;
            const cleanText = rawText.replace(/\\s+/g, ' ').trim();

            const st = window.getComputedStyle(textEl);
            const fontSize = parseFloat(st.fontSize || '13') || 13;
            const lineHeight = parseFloat(st.lineHeight) || (fontSize * 1.4);

            // (a) 텍스트 노드가 실제로 2줄 이상으로 나뉘었는지 Range rect 검사
            let multiLineRects = false;
            try {
                const range = document.createRange();
                range.selectNodeContents(textEl);
                const rects = Array.from(range.getClientRects()).filter(r => r.width > 1 && r.height > 1);
                if (rects.length > 1) {
                    const firstTop = rects[0].top;
                    if (rects.some(r => Math.abs(r.top - firstTop) > fontSize * 0.6)) {
                        multiLineRects = true;
                    }
                }
            } catch (e) {}

            // (b) 요소 높이가 1줄 높이를 초과했거나 scrollHeight 초과
            const heightWrapped = textEl.offsetHeight > lineHeight * 1.65 || textEl.scrollHeight > lineHeight * 1.65;

            // (c) 가로 잘림(ellipsis) 또는 셀 가용 폭보다 텍스트 단일 줄 폭이 더 큰 경우
            const horizClipped = textEl.scrollWidth > textEl.clientWidth + 2;
            const singleWidth = measureTextWidth(cleanText, st.font || `${st.fontWeight} ${st.fontSize} ${st.fontFamily}`);
            const labelBox = hCell.querySelector('.ag-header-cell-label') || textEl;
            const availWidth = labelBox.clientWidth || hCell.clientWidth - 16;
            const widthOverflow = availWidth > 0 && singleWidth > availWidth + 3;

            if (rawText.includes('\\n') || multiLineRects || heightWrapped || horizClipped || widthOverflow) {
                if (!wrappedHeaders.includes(cleanText)) {
                    wrappedHeaders.push(cleanText);
                }
            }
        }

        // 그리드 가로 스크롤 발생 여부
        const hScrollVp = gEl.querySelector('.ag-body-horizontal-scroll-viewport, .ag-center-cols-viewport');
        const gridHScroll = hScrollVp ? (hScrollVp.scrollWidth > hScrollVp.clientWidth + 4) : false;

        return {
            index: idx + 1,
            row_count: rowCount,
            empty: rowCount === 0,
            wrapped_headers: wrappedHeaders,
            has_wrapped_headers: wrappedHeaders.length > 0,
            horizontal_scroll: gridHScroll,
        };
    });

    // 2. 화면 버튼 목록 및 비활성 여부 수집
    const btnEls = Array.from(tabEl.querySelectorAll('button.ant-btn, button')).filter(b => {
        if (!isVisible(b)) return false;
        if (b.closest('.ant-modal, .ag-header, .ag-cell, .ant-picker, .ant-select, .ant-input-suffix')) return false;
        return true;
    });
    const buttons = [];
    const seenBtnKeys = new Set();
    for (const b of btnEls) {
        const lbl = (b.innerText || '').replace(/\\s+/g, ' ').trim();
        if (!lbl) continue;
        const dis = isEffectivelyDisabled(b);
        const key = `${lbl}::${dis}`;
        if (!seenBtnKeys.has(key)) {
            seenBtnKeys.add(key);
            buttons.push({ label: lbl, disabled: dis });
        }
    }

    // 3. 화면(레이아웃) 가로 스크롤 발생 여부 (그리드 내부 뷰포트 제외)
    let pageHScroll = tabEl.scrollWidth > tabEl.clientWidth + 4;
    if (!pageHScroll) {
        const containers = Array.from(tabEl.querySelectorAll('.ant-splitter-panel, div')).filter(d => {
            if (!isVisible(d)) return false;
            if (d.closest('.ag-root-wrapper, .ant-modal')) return false;
            return true;
        });
        for (const c of containers) {
            const st = window.getComputedStyle(c);
            if ((st.overflowX === 'auto' || st.overflowX === 'scroll') && c.scrollWidth > c.clientWidth + 4) {
                pageHScroll = true;
                break;
            }
        }
    }
    const gridAnyHScroll = grids.some(g => g.horizontal_scroll);

    return {
        grids,
        buttons,
        horizontal_scroll: {
            page: pageHScroll,
            grids: gridAnyHScroll,
            any: pageHScroll || gridAnyHScroll,
        },
    };
}
"""


def get_png_dimensions(path: Path) -> tuple[int, int]:
    """PNG 파일의 너비와 높이를 바이트 헤더(IHDR)에서 직접 읽어 반환한다."""
    try:
        with path.open("rb") as f:
            header = f.read(24)
            if len(header) >= 24 and header[:8] == b"\x89PNG\r\n\x1a\n":
                w, h = struct.unpack(">II", header[16:24])
                return (int(w), int(h))
    except Exception:  # noqa: BLE001, S110
        pass
    try:
        from PIL import Image

        with Image.open(path) as img:
            return (int(img.width), int(img.height))
    except Exception:  # noqa: BLE001, S110
        pass
    return (0, 0)


COLLECT_BOXES_JS = r"""
(clipElem) => {
    const scale = window.devicePixelRatio || 1;
    const vpW = window.innerWidth;
    const vpH = window.innerHeight;

    let originX = 0;
    let originY = 0;
    let boundW = vpW;
    let boundH = vpH;

    if (clipElem && typeof clipElem.getBoundingClientRect === 'function') {
        const cr = clipElem.getBoundingClientRect();
        originX = cr.left;
        originY = cr.top;
        boundW = cr.width;
        boundH = cr.height;
    }

    function isVisible(el) {
        if (!el || !(el instanceof Element)) return false;
        const rect = el.getBoundingClientRect();
        if (rect.width <= 0 || rect.height <= 0) return false;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden' || parseFloat(style.opacity) === 0) {
            return false;
        }
        if (el.closest('.ant-tabs-tabpane-hidden')) return false;
        return true;
    }

    function computeBox(rect) {
        if (!rect || rect.width <= 0 || rect.height <= 0) return null;
        const relX = rect.left - originX;
        const relY = rect.top - originY;
        const relW = rect.width;
        const relH = rect.height;

        const left = Math.max(0, relX);
        const top = Math.max(0, relY);
        const right = Math.min(boundW, relX + relW);
        const bottom = Math.min(boundH, relY + relH);

        if (right <= left || bottom <= top) return null;

        return [
            Math.round(left * scale),
            Math.round(top * scale),
            Math.round((right - left) * scale),
            Math.round((bottom - top) * scale),
        ];
    }

    function cleanText(txt) {
        if (!txt) return "";
        return txt.replace(/[\r\n\t]+/g, ' ').replace(/\s{2,}/g, ' ').trim();
    }

    // 1. Identify active visible modals
    const modalContentEls = Array.from(document.querySelectorAll('.ant-modal-content')).filter(isVisible);
    const modalMap = new Map();
    const modalNamesCount = new Map();

    for (const mEl of modalContentEls) {
        const titleEl = mEl.querySelector('.ant-modal-title, .ant-modal-header');
        let t = cleanText(titleEl ? titleEl.innerText : "");
        if (!t) t = "모달";

        let c = (modalNamesCount.get(t) || 0) + 1;
        modalNamesCount.set(t, c);
        const modalName = c > 1 ? `${t}#${c}` : t;

        const isLookup = Boolean(
            mEl.closest('.lookup-modal') ||
            mEl.closest('[class*="Lookup"]') ||
            /lookup|검색/i.test(t)
        );
        modalMap.set(mEl, {
            name: modalName,
            isLookup: isLookup,
            titleEl: titleEl,
            titleText: t,
        });
    }

    function getElementModalInfo(el) {
        const mEl = el.closest('.ant-modal-content');
        if (mEl && modalMap.has(mEl)) {
            return modalMap.get(mEl);
        }
        return null;
    }

    function findLabelForInput(el) {
        const formItem = el.closest('.ant-form-item');
        if (formItem) {
            const lbl = formItem.querySelector('.ant-form-item-label label');
            if (lbl) {
                const t = cleanText(lbl.innerText).replace(/^[*\s]+|[*\s:]+$/g, '');
                if (t) return t;
            }
        }
        const aria = el.getAttribute('aria-label') || el.getAttribute('title') || el.getAttribute('placeholder');
        if (aria) return cleanText(aria);

        let parent = el.parentElement;
        while (parent && parent !== document.body) {
            const prev = parent.previousElementSibling;
            if (prev && prev.innerText && prev.innerText.trim().length < 20) {
                const t = cleanText(prev.innerText).replace(/^[*\s]+|[*\s:]+$/g, '');
                if (t) return t;
            }
            if (parent.classList.contains('ant-space') || parent.classList.contains('ant-row') || parent.classList.contains('ant-form-item')) break;
            parent = parent.parentElement;
        }
        return "";
    }

    const rawElements = [];

    // --- A. Modals & Modal Titles ---
    for (const [mEl, mInfo] of modalMap.entries()) {
        const mBox = computeBox(mEl.getBoundingClientRect());
        if (mBox) {
            rawElements.push({
                name: mInfo.name,
                kind: "modal",
                text: mInfo.titleText,
                box: mBox,
                area: mInfo.isLookup ? "lookup" : "modal",
            });
        }
        if (mInfo.titleEl && isVisible(mInfo.titleEl)) {
            const tBox = computeBox(mInfo.titleEl.getBoundingClientRect());
            if (tBox) {
                rawElements.push({
                    name: `${mInfo.name}:제목`,
                    kind: "modal-title",
                    text: mInfo.titleText,
                    box: tBox,
                    area: mInfo.isLookup ? "lookup" : "modal",
                    parent: mInfo.name,
                });
            }
        }
    }

    // --- B. Tabs ---
    const tabEls = Array.from(document.querySelectorAll('.ant-tabs-tab')).filter(isVisible);
    for (const tEl of tabEls) {
        const tBox = computeBox(tEl.getBoundingClientRect());
        if (!tBox) continue;
        const text = cleanText(tEl.innerText);
        const mInfo = getElementModalInfo(tEl);
        rawElements.push({
            name: text || "tab",
            kind: "tab",
            text: text,
            box: tBox,
            area: mInfo ? (mInfo.isLookup ? "lookup" : "modal") : "main",
            parent: mInfo ? mInfo.name : undefined,
            disabled: tEl.classList.contains('ant-tabs-tab-disabled'),
        });
    }

    // --- C. Buttons & Icon-Buttons ---
    const btnEls = Array.from(document.querySelectorAll('button, .ant-btn, [role="button"]')).filter(isVisible);
    for (const btn of btnEls) {
        if (btn.closest('.ag-cell')) continue;
        if (btn.closest('.ant-tabs-tab')) continue;
        if (btn.closest('.ant-picker-header')) continue;

        const box = computeBox(btn.getBoundingClientRect());
        if (!box) continue;

        const mInfo = getElementModalInfo(btn);
        const area = mInfo ? (mInfo.isLookup ? "lookup" : "modal") : "main";
        const parent = mInfo ? mInfo.name : undefined;
        const disabled = btn.disabled || btn.classList.contains('ant-btn-disabled') || btn.getAttribute('aria-disabled') === 'true';

        const isClose = btn.classList.contains('ant-modal-close') || btn.closest('.ant-modal-close');
        if (isClose) {
            rawElements.push({
                name: "닫기",
                kind: "button",
                text: "닫기",
                box: box,
                area: area,
                parent: parent,
                disabled: disabled,
            });
            continue;
        }

        const text = cleanText(btn.innerText);
        if (text) {
            rawElements.push({
                name: text,
                kind: "button",
                text: text,
                box: box,
                area: area,
                parent: parent,
                disabled: disabled,
            });
        } else {
            let iconName = "";
            const aria = btn.getAttribute('aria-label') || btn.getAttribute('title');
            if (aria) {
                iconName = cleanText(aria);
            } else {
                const iconSvg = btn.querySelector('.anticon, svg');
                if (iconSvg) {
                    const cls = (typeof iconSvg.className === 'string') ? iconSvg.className : (iconSvg.getAttribute('class') || "");
                    const m = cls.match(/anticon-([a-z0-9-]+)/);
                    if (m) {
                        const it = m[1];
                        if (it.includes('search')) iconName = "search";
                        else if (it.includes('edit')) iconName = "edit";
                        else if (it.includes('delete')) iconName = "delete";
                        else if (it.includes('close')) iconName = "닫기";
                        else if (it.includes('plus')) iconName = "추가";
                        else if (it.includes('calendar')) iconName = "calendar";
                        else iconName = it;
                    }
                }
            }
            if (!iconName) iconName = "icon";
            rawElements.push({
                name: iconName,
                kind: "icon-button",
                box: box,
                area: area,
                parent: parent,
                disabled: disabled,
            });
        }
    }

    // --- D. Form Labels ---
    const labelEls = Array.from(document.querySelectorAll('.ant-form-item-label label')).filter(isVisible);
    for (const lbl of labelEls) {
        const box = computeBox(lbl.getBoundingClientRect());
        if (!box) continue;
        const text = cleanText(lbl.innerText).replace(/^[*\s]+|[*\s:]+$/g, '');
        if (!text) continue;
        const mInfo = getElementModalInfo(lbl);
        rawElements.push({
            name: text,
            kind: "label",
            text: text,
            box: box,
            area: mInfo ? (mInfo.isLookup ? "lookup" : "modal") : "main",
            parent: mInfo ? mInfo.name : undefined,
        });
    }

    // --- E. Inputs ---
    const inpEls = Array.from(document.querySelectorAll('input.ant-input, textarea.ant-input, input.ant-input-number-input')).filter(isVisible);
    for (const inp of inpEls) {
        if (inp.closest('.ant-picker-input') || inp.closest('.ant-select') || inp.closest('.ag-cell')) continue;
        const box = computeBox(inp.getBoundingClientRect());
        if (!box) continue;
        const mInfo = getElementModalInfo(inp);
        const name = findLabelForInput(inp) || "input";
        rawElements.push({
            name: name,
            kind: "input",
            box: box,
            area: mInfo ? (mInfo.isLookup ? "lookup" : "modal") : "main",
            parent: mInfo ? mInfo.name : undefined,
            disabled: inp.disabled || inp.readOnly,
        });
    }

    // --- F. Selects ---
    const selEls = Array.from(document.querySelectorAll('.ant-select')).filter(isVisible);
    for (const sel of selEls) {
        if (sel.closest('.ag-cell')) continue;
        const box = computeBox(sel.getBoundingClientRect());
        if (!box) continue;
        const mInfo = getElementModalInfo(sel);
        const name = findLabelForInput(sel) || "select";
        rawElements.push({
            name: name,
            kind: "select",
            box: box,
            area: mInfo ? (mInfo.isLookup ? "lookup" : "modal") : "main",
            parent: mInfo ? mInfo.name : undefined,
            disabled: sel.classList.contains('ant-select-disabled'),
        });
    }

    // --- G. Date Pickers ---
    const pickerEls = Array.from(document.querySelectorAll('.ant-picker')).filter(isVisible);
    for (const p of pickerEls) {
        if (p.closest('.ag-cell')) continue;
        const box = computeBox(p.getBoundingClientRect());
        if (!box) continue;
        const mInfo = getElementModalInfo(p);
        const name = findLabelForInput(p) || "date";
        rawElements.push({
            name: name,
            kind: "date",
            box: box,
            area: mInfo ? (mInfo.isLookup ? "lookup" : "modal") : "main",
            parent: mInfo ? mInfo.name : undefined,
            disabled: p.classList.contains('ant-picker-disabled'),
        });
    }

    // --- H. Checkboxes & Radios ---
    const chkEls = Array.from(document.querySelectorAll('.ant-checkbox-wrapper')).filter(isVisible);
    for (const chk of chkEls) {
        if (chk.closest('.ag-cell')) continue;
        const box = computeBox(chk.getBoundingClientRect());
        if (!box) continue;
        const text = cleanText(chk.innerText);
        const mInfo = getElementModalInfo(chk);
        rawElements.push({
            name: text || "checkbox",
            kind: "checkbox",
            text: text,
            box: box,
            area: mInfo ? (mInfo.isLookup ? "lookup" : "modal") : "main",
            parent: mInfo ? mInfo.name : undefined,
            disabled: chk.classList.contains('ant-checkbox-wrapper-disabled'),
        });
    }

    const radEls = Array.from(document.querySelectorAll('.ant-radio-wrapper')).filter(isVisible);
    for (const rad of radEls) {
        if (rad.closest('.ag-cell')) continue;
        const box = computeBox(rad.getBoundingClientRect());
        if (!box) continue;
        const text = cleanText(rad.innerText);
        const mInfo = getElementModalInfo(rad);
        rawElements.push({
            name: text || "radio",
            kind: "radio",
            text: text,
            box: box,
            area: mInfo ? (mInfo.isLookup ? "lookup" : "modal") : "main",
            parent: mInfo ? mInfo.name : undefined,
            disabled: rad.classList.contains('ant-radio-wrapper-disabled'),
        });
    }

    // --- I. AG Grids ---
    const allGridRoots = Array.from(document.querySelectorAll('.ag-root-wrapper, .ag-root')).filter(isVisible);
    const uniqueGrids = [];
    for (const g of allGridRoots) {
        if (g.classList.contains('ag-root')) {
            uniqueGrids.push(g);
        } else if (!g.querySelector('.ag-root')) {
            uniqueGrids.push(g);
        }
    }

    let gridIdx = 1;
    for (const grid of uniqueGrids) {
        const gridName = uniqueGrids.length > 1 ? `grid${gridIdx}` : `grid1`;
        gridIdx++;
        const gBox = computeBox(grid.getBoundingClientRect());
        const mInfo = getElementModalInfo(grid);
        const area = mInfo ? (mInfo.isLookup ? "lookup" : "modal") : "main";
        const parent = mInfo ? mInfo.name : undefined;

        if (gBox) {
            rawElements.push({
                name: gridName,
                kind: "grid",
                box: gBox,
                area: area,
                parent: parent,
            });
        }

        // Header cells
        const headerCells = Array.from(grid.querySelectorAll('.ag-header-cell')).filter(isVisible);
        const colHeaderMap = new Map();
        for (const hc of headerCells) {
            const hBox = computeBox(hc.getBoundingClientRect());
            const colId = hc.getAttribute('col-id') || "";
            const textEl = hc.querySelector('.ag-header-cell-text');
            let colName = cleanText(textEl ? textEl.innerText : hc.innerText);
            if (!colName) {
                colName = hc.getAttribute('title') || colId || "col";
            }
            if (colId) colHeaderMap.set(colId, colName);

            if (hBox) {
                rawElements.push({
                    name: `헤더:${colName}`,
                    kind: "grid-header",
                    text: colName,
                    col: colName,
                    box: hBox,
                    area: area,
                    parent: parent,
                });
            }
        }

        // Rows
        const rowEls = Array.from(grid.querySelectorAll('.ag-row:not(.ag-row-hidden)')).filter(isVisible);
        rowEls.sort((a, b) => a.getBoundingClientRect().top - b.getBoundingClientRect().top);
        const limitedRows = rowEls.slice(0, 20);

        let rowNum = 1;
        for (const rEl of limitedRows) {
            const currentRow = rowNum++;
            const rBox = computeBox(rEl.getBoundingClientRect());
            if (rBox) {
                rawElements.push({
                    name: `${gridName}.행${currentRow}`,
                    kind: "grid-row",
                    row: currentRow,
                    box: rBox,
                    area: area,
                    parent: parent,
                });
            }

            const cells = Array.from(rEl.querySelectorAll('.ag-cell')).filter(isVisible);
            for (const cell of cells) {
                const colId = cell.getAttribute('col-id') || "";
                const colName = colHeaderMap.get(colId) || colId || "col";
                const cBox = computeBox(cell.getBoundingClientRect());
                if (!cBox) continue;

                // Checkbox inside cell
                const chk = cell.querySelector('.ag-selection-checkbox, .ant-checkbox, input[type="checkbox"]');
                if (chk && isVisible(chk)) {
                    const chkBox = computeBox(chk.getBoundingClientRect());
                    if (chkBox) {
                        rawElements.push({
                            name: `${gridName}.행${currentRow}.체크`,
                            kind: "grid-check",
                            row: currentRow,
                            box: chkBox,
                            area: area,
                            parent: parent,
                        });
                    }
                }

                // Icon button inside cell
                const iconBtn = cell.querySelector('button, .ant-btn, .anticon, .ag-icon');
                if (iconBtn && isVisible(iconBtn)) {
                    const iBox = computeBox(iconBtn.getBoundingClientRect());
                    if (iBox) {
                        let iconName = cleanText(iconBtn.innerText) || iconBtn.getAttribute('title') || iconBtn.getAttribute('aria-label');
                        if (!iconName) {
                            const cls = (typeof iconBtn.className === 'string') ? iconBtn.className : "";
                            if (cls.includes('edit')) iconName = "수정";
                            else if (cls.includes('delete')) iconName = "삭제";
                            else iconName = colName;
                        }
                        rawElements.push({
                            name: `${gridName}.행${currentRow}.${iconName}`,
                            kind: "grid-icon",
                            row: currentRow,
                            col: colName,
                            box: iBox,
                            area: area,
                            parent: parent,
                        });
                    }
                }

                // Regular cell (first 5 rows only)
                if (currentRow <= 5) {
                    const cellText = cleanText(cell.innerText);
                    rawElements.push({
                        name: `${gridName}.행${currentRow}.${colName}`,
                        kind: "grid-cell",
                        row: currentRow,
                        col: colName,
                        text: cellText,
                        box: cBox,
                        area: area,
                        parent: parent,
                    });
                }
            }
        }
    }

    // --- J. Deduplicate names & Build final elements ---
    const nameCounts = new Map();
    const finalElements = [];

    for (const item of rawElements) {
        const baseName = item.name;
        const count = (nameCounts.get(baseName) || 0) + 1;
        nameCounts.set(baseName, count);

        const finalName = count > 1 ? `${baseName}#${count}` : baseName;

        const outItem = {
            name: finalName,
            kind: item.kind,
            box: item.box,
        };
        if (item.text !== undefined && item.text !== "") outItem.text = item.text;
        if (item.area) outItem.area = item.area;
        if (item.parent) outItem.parent = item.parent;
        if (item.row !== undefined) outItem.row = item.row;
        if (item.col !== undefined && item.col !== "") outItem.col = item.col;
        if (item.disabled) outItem.disabled = true;

        finalElements.push(outItem);
    }

    return {
        viewport: [vpW, vpH],
        scale: scale,
        origin: [Math.round(originX), Math.round(originY)],
        elements: finalElements,
    };
}
"""


def capture_screen(
    screen_id: str,
    login_spec: LoginSpec,
    base_url: str = config.CAPTURE_BASE_URL,
    out_dir: str | Path = config.CAPTURE_OUT_DIR,
    preferred_title: str | None = None,
    include_popups: bool = True,
    modal_only: bool = False,
    click_all: bool = False,
    boxes: bool = False,
    range_opt: str | None = None,
    set_opts: list[str] | None = None,
    headed: bool = False,
    viewport_width: int = 1920,
    viewport_height: int = 1080,
) -> ToolResult:
    """지정한 화면(screen_id)을 오픈하고 단계별 화면 및 팝업들을 캡처하여 저장한다."""
    start_ts = time.monotonic()

    try:
        parsed_range = parse_range_spec(range_opt)
        parsed_sets = parse_set_specs(set_opts)
    except ValueError as exc:
        return ToolResult(ok=False, error=str(exc))

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return ToolResult(
            ok=False,
            error="playwright가 설치되어 있지 않습니다. `uv add playwright && uv run playwright install chromium`을 실행하세요.",
        )

    # 1. 사전 API 로그인 & 겸직/메뉴 탐색
    try:
        target, cookies, user_data = preflight_session_and_screen(
            base_url=base_url,
            login_spec=login_spec,
            screen_id=screen_id,
            preferred_title=preferred_title,
        )
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))

    tenant_url = build_tenant_url(base_url, login_spec.company)
    parsed_tenant = urlparse(tenant_url)
    cookie_domain = parsed_tenant.hostname or "localhost"

    # 출력 디렉터리 준비 (--out / <화면폴더>)
    out_root = Path(out_dir)
    if not out_root.is_absolute():
        out_root = config.WORK_DIR / out_root
    screen_out_dir = out_root / target.folder_name
    screen_out_dir.mkdir(parents=True, exist_ok=True)

    # 기존 캡처 png 정리
    for old_png in screen_out_dir.glob("*.png"):
        try:
            old_png.unlink()
        except OSError:
            pass

    selected_title_desc = (
        f"{target.selected_org_name} / {target.selected_title_name} (personId={target.selected_add_person_id})"
        if target.selected_org_name
        else None
    )

    report = CaptureReport(
        screen_id=screen_id,
        folder_name=target.folder_name,
        output_dir=str(screen_out_dir),
        url=tenant_url,
        company=login_spec.company,
        user=login_spec.user,
        selected_title=selected_title_desc,
    )

    def _save_shot(
        page: Any,
        step_code: str,
        filename: str,
        description: str,
        clip_locator: Any | None = None,
    ) -> None:
        img_path = screen_out_dir / filename
        saved = False
        if clip_locator is not None:
            try:
                if clip_locator.count() > 0 and clip_locator.first.is_visible():
                    clip_locator.first.screenshot(path=str(img_path))
                    saved = True
            except Exception:  # noqa: BLE001
                saved = False
        if not saved:
            page.screenshot(path=str(img_path), full_page=False)

        boxes_filename: str | None = None
        if boxes:
            try:
                boxes_filename = filename.rsplit(".", 1)[0] + ".boxes.json"
                boxes_path = screen_out_dir / boxes_filename
                clip_handle = None
                if clip_locator is not None and saved:
                    try:
                        clip_handle = clip_locator.first.element_handle()
                    except Exception:  # noqa: BLE001
                        clip_handle = None

                boxes_data = page.evaluate(COLLECT_BOXES_JS, clip_handle)
                img_w, img_h = get_png_dimensions(img_path)
                if img_w <= 0 or img_h <= 0:
                    img_w, img_h = boxes_data.get("viewport", [viewport_width, viewport_height])

                boxes_payload = {
                    "version": 1,
                    "image": filename,
                    "image-size": [img_w, img_h],
                    "viewport": boxes_data.get("viewport", [viewport_width, viewport_height]),
                    "scale": float(boxes_data.get("scale", 1.0)),
                    "origin": boxes_data.get("origin", [0, 0]),
                    "screen": str(screen_id),
                    "elements": boxes_data.get("elements", []),
                }
                boxes_path.write_text(
                    json.dumps(boxes_payload, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
            except Exception:  # noqa: BLE001
                boxes_filename = None

        report.captures.append(
            CaptureItem(
                step=step_code,
                filename=filename,
                path=str(img_path),
                description=description,
                boxes=boxes_filename,
            )
        )

    jti = str(user_data.get("jti") or "")
    initial_settings = _build_flexlayout_storage_json(
        target if not target.in_user_menu else None
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=not headed,
            args=["--host-resolver-rules=MAP *.localhost 127.0.0.1"],
        )
        context = browser.new_context(
            viewport={"width": viewport_width, "height": viewport_height},
            locale="ko-KR",
        )

        if cookies:
            pw_cookies = [
                {
                    "name": k,
                    "value": v,
                    "domain": cookie_domain,
                    "path": "/",
                }
                for k, v in cookies.items()
            ]
            context.add_cookies(pw_cookies)

        init_settings_str = json.dumps(initial_settings, ensure_ascii=False)
        context.add_init_script(
            f"""
            (() => {{
                try {{
                    const jti = {json.dumps(jti)};
                    if (jti) {{
                        sessionStorage.setItem('secondaryAuthOk:' + jti, '1');
                        sessionStorage.setItem('addTitleOk:' + jti, '1');
                    }}
                    if (!sessionStorage.getItem('__yunhee_layout_initialized')) {{
                        localStorage.setItem('asseterp_settings', {json.dumps(init_settings_str)});
                        sessionStorage.setItem('__yunhee_layout_initialized', '1');
                    }}
                }} catch (e) {{}}
            }})();
            """
        )

        page = context.new_page()
        inflight_tracker = {"count": 0}

        def _on_req(req: Any) -> None:
            if "/api/" in req.url and "/files/monitoring" not in req.url:
                inflight_tracker["count"] += 1

        def _on_req_done(req: Any) -> None:
            if "/api/" in req.url and "/files/monitoring" not in req.url:
                inflight_tracker["count"] = max(0, inflight_tracker["count"] - 1)

        page.on("request", _on_req)
        page.on("requestfinished", _on_req_done)
        page.on("requestfailed", _on_req_done)

        def _on_console(msg: Any) -> None:
            if msg.type != "error":
                return
            txt = msg.text.strip()
            if "Failed to load resource: the server responded with a status of 404" in txt:
                return
            report.console_errors.append(txt[:300])

        page.on("console", _on_console)
        page.on(
            "pageerror",
            lambda err: report.console_errors.append(str(err)[:300]),
        )
        page.on(
            "response",
            lambda resp: report.api_failures.append(
                f"HTTP {resp.status} {resp.request.method} {resp.url}"
            )
            if resp.status >= 400
            and "/api/" in resp.url
            and "/files/monitoring" not in resp.url
            else None,
        )

        try:
            page.goto(tenant_url, wait_until="domcontentloaded", timeout=20000)
            _wait_ui_settled(page, inflight_tracker, 5000)

            _pass_login_and_gates_if_visible(page, login_spec, target, inflight_tracker)
            _wait_ui_settled(page, inflight_tracker, 3000)
            _dismiss_all_modals(page)

            # 2. 화면 오픈 (TopBar 검색창 입력 + Enter 우선, 미등록 화면은 Deeplink 주입)
            opened_via_topbar = False
            search_term = target.menu_no or target.title or screen_id
            topbar_input = page.locator("input[placeholder*='화면번호/메뉴명']:visible")

            if target.in_user_menu and topbar_input.count() > 0:
                topbar_input.first.click()
                topbar_input.first.fill(str(search_term))
                page.wait_for_timeout(200)
                topbar_input.first.press("Enter")
                _wait_ui_settled(page, inflight_tracker, 5000)
                _dismiss_all_modals(page)

                tab_buttons = page.locator(".flexlayout__tab_button:visible")
                if tab_buttons.count() > 1:
                    opened_via_topbar = True
                    report.open_method = f"topbar ({search_term})"

            if not opened_via_topbar:
                if not target.class_nm:
                    target.class_nm = screen_id
                deeplink_settings = _build_flexlayout_storage_json(target)
                page.evaluate(
                    "(settingsStr) => { localStorage.setItem('asseterp_settings', settingsStr); }",
                    json.dumps(deeplink_settings, ensure_ascii=False),
                )
                page.reload(wait_until="domcontentloaded", timeout=20000)
                _wait_ui_settled(page, inflight_tracker, 5000)
                _dismiss_all_modals(page)
                report.open_method = f"deeplink ({target.class_nm})"

            active_tab = page.locator(".flexlayout__tab:visible").last

            # Step 1: 01_initial.png (화면 최초 오픈 상태)
            _save_shot(
                page,
                "01_initial",
                "01_initial.png",
                f"화면 최초 오픈 ({target.menu_no or ''} {target.title or target.class_nm or screen_id})".strip(),
            )

            # Step 2: 조회 조건(--range / --set) 적용 후 [조회] 클릭 → 02_searched.png
            cond_info, cond_warnings = _apply_search_conditions(
                page, active_tab, parsed_range, parsed_sets
            )
            report.search_conditions = cond_info
            report.warnings.extend(cond_warnings)

            search_btns = active_tab.locator("button.ant-btn:visible:not([disabled])")
            clicked_search = False
            for i in range(search_btns.count()):
                btn = search_btns.nth(i)
                try:
                    txt = re.sub(r"\s+", "", btn.inner_text() or "")
                    if txt in SEARCH_BUTTON_KEYWORDS:
                        btn.click(timeout=3000)
                        clicked_search = True
                        break
                except Exception:  # noqa: BLE001, S112
                    continue

            def _count_grid_rows() -> int:
                try:
                    return int(
                        active_tab.evaluate(
                            "el => new Set(Array.from(el.querySelectorAll('.ag-center-cols-container .ag-row[row-index], .ag-row[row-index]')).filter(r => !r.closest('.ag-floating-top, .ag-floating-bottom')).map(r => r.getAttribute('row-index')).filter(Boolean)).size"
                        )
                    )
                except Exception:  # noqa: BLE001
                    return active_tab.locator(".ag-row:visible").count()

            if clicked_search or parsed_range is not None or bool(parsed_sets):
                _wait_ui_settled(page, inflight_tracker, 6000)
                _dismiss_all_modals(page)
                grid_rows = _count_grid_rows()
                report.grid_rows_after_search = grid_rows
                _save_shot(
                    page,
                    "02_searched",
                    "02_searched.png",
                    f"[조회] 클릭 후 (그리드 표시 행: {grid_rows}건)",
                )
            else:
                grid_rows = _count_grid_rows()
                report.grid_rows_after_search = grid_rows

            # Step 3: 03_row_selected.png (그리드 행 선택 — SingleGrid 셀 클릭 및 MultiGrid 체크박스 대응)
            first_grid = active_tab.locator(".ag-root-wrapper:visible").first
            visible_rows = first_grid.locator(
                ".ag-center-cols-container .ag-row:visible, .ag-row:visible"
            )
            if visible_rows.count() > 0:
                try:
                    row_0 = first_grid.locator(".ag-row[row-index='0']:visible")
                    row_1 = first_grid.locator(".ag-row[row-index='1']:visible")
                    cb_0_inp = row_0.locator("input[type='checkbox']")

                    if cb_0_inp.count() > 0:
                        # 체크박스 다중 선택 그리드(MultiGrid): 0번 행 체크박스가 안 켜져 있을 때만 클릭
                        if not cb_0_inp.first.is_checked():
                            cb_0_inp.first.click(timeout=2000)
                        else:
                            # 이미 0번 행이 체크된 상태면 체크가 풀리지 않도록 일반 텍스트 셀만 클릭
                            non_cb_cells = row_0.first.locator(
                                ".ag-cell:visible:not(:has(input[type='checkbox'])):not(:has(.ag-selection-checkbox))"
                            )
                            if non_cb_cells.count() > 0:
                                non_cb_cells.last.click(timeout=2000)
                    else:
                        # 단일 선택 그리드(SingleGrid): 이미 0행이 선택되어 있고 1행이 있으면 1행 클릭
                        already_selected = (
                            first_grid.locator(".ag-row-selected:visible").count() > 0
                        )
                        target_row = (
                            row_1.first
                            if (already_selected and row_1.count() > 0)
                            else (row_0.first if row_0.count() > 0 else visible_rows.first)
                        )
                        non_cb_cells = target_row.locator(
                            ".ag-cell:visible:not(:has(input[type='checkbox'])):not(:has(.ag-selection-checkbox))"
                        )
                        if non_cb_cells.count() > 0:
                            non_cb_cells.first.click(timeout=2500)

                    _wait_ui_settled(page, inflight_tracker, 3000)
                    _save_shot(
                        page,
                        "03_row_selected",
                        "03_row_selected.png",
                        "그리드 행 선택 상태",
                    )
                    _dismiss_all_modals(page)
                except Exception:  # noqa: BLE001, S110
                    pass

            # 조회 및 행 선택 완료 시점의 화면 텍스트 신호(그리드, 버튼, 가로스크롤) 수집
            try:
                sig = active_tab.evaluate(_COLLECT_SIGNALS_JS)
                report.grids = sig.get("grids") or []
                report.buttons = sig.get("buttons") or []
                report.horizontal_scroll = sig.get("horizontal_scroll") or {
                    "page": False,
                    "grids": False,
                    "any": False,
                }
                if report.grids:
                    report.grid_rows_after_search = sum(
                        int(g.get("row_count", 0)) for g in report.grids
                    )
            except Exception:  # noqa: BLE001, S110
                pass

            # Step 4: 화면 내부 서브 탭(.ant-tabs-tab) 순회 캡처
            sub_tabs = active_tab.locator(
                ".ant-tabs-nav .ant-tabs-tab:visible:not(.ant-tabs-tab-disabled)"
            )
            tab_count = sub_tabs.count()
            if tab_count > 1:
                for t_idx in range(1, min(tab_count, 16)):
                    try:
                        tab_el = sub_tabs.nth(t_idx)
                        tab_name = (tab_el.inner_text() or f"tab{t_idx + 1}").strip()
                        tab_el.click(timeout=2500)
                        _wait_ui_settled(page, inflight_tracker, 3000)
                        _dismiss_all_modals(page)
                        fname = f"04_tab_{t_idx:02d}_{_safe_filename(tab_name)}.png"
                        _save_shot(page, "04_tab", fname, f"내부 탭 전환: [{tab_name}]")
                    except Exception:  # noqa: BLE001, S112
                        continue
                try:
                    sub_tabs.first.click(timeout=2000)
                    _wait_ui_settled(page, inflight_tracker, 2000)
                except Exception:  # noqa: BLE001, S110
                    pass

            # Step 5: 팝업/모달 오픈 버튼 & Lookup 돋보기 & 그리드 액션 아이콘 순회 캡처
            popup_clicked: list[dict[str, Any]] = []
            popup_opened_modals: list[dict[str, str]] = []
            popup_not_opened: list[dict[str, str]] = []
            skipped_disabled = [
                b["label"] for b in report.buttons if b.get("disabled")
            ]

            if include_popups:
                def _safety_route_guard(route: Any) -> None:
                    req = route.request
                    method = req.method.upper()
                    if method in ("DELETE", "PUT", "PATCH"):
                        route.abort()
                        return
                    if method == "POST" and "/api/" in req.url:
                        url_lower = req.url.lower()
                        # 조회/체크성 POST(close-check, check, search, list, query)는 허용
                        if not any(
                            safe_w in url_lower
                            for safe_w in ("check", "search", "list", "query", "find", "select", "count")
                        ) and any(
                            w in url_lower
                            for w in (
                                "save",
                                "delete",
                                "remove",
                                "update",
                                "insert",
                                "create",
                                "confirm",
                                "approve",
                                "reject",
                                "cancel",
                                "send",
                                "upload",
                                "copy",
                            )
                        ):
                            route.abort()
                            return
                    route.continue_()

                page.route("**/api/**", _safety_route_guard)

                all_btns = active_tab.locator("button.ant-btn:visible:not([disabled])")
                btn_total = all_btns.count()
                popup_idx = 0
                label_click_counts: dict[str, int] = {}
                captured_modal_titles: set[str] = set()

                for b_i in range(min(btn_total, 25)):
                    try:
                        btn = all_btns.nth(b_i)
                        if not btn.is_visible() or not btn.is_enabled():
                            continue
                        # 부모 컨테이너가 pointer-events: none 인 경우(비활성 폼 내부 버튼) 제외
                        pe = btn.evaluate("el => window.getComputedStyle(el).pointerEvents")
                        if pe == "none":
                            continue

                        raw_label = (btn.inner_text() or "").strip()
                        clean_label = re.sub(r"\s+", " ", raw_label)
                        if not clean_label:
                            continue
                        if not is_safe_popup_button(clean_label, click_all=click_all):
                            if clean_label not in SEARCH_BUTTON_KEYWORDS and clean_label not in report.skipped_buttons:
                                report.skipped_buttons.append(clean_label)
                            continue

                        occ = label_click_counts.get(clean_label, 0) + 1
                        label_click_counts[clean_label] = occ
                        display_btn_label = clean_label if occ == 1 else f"{clean_label}#{occ}"
                        _dismiss_all_modals(page)

                        # 클릭 전 기존 토스트 메시지 스냅샷
                        prev_toasts = set(
                            page.locator(".ant-message-notice-content:visible").all_inner_texts()
                        )

                        btn.click(timeout=2500)
                        _wait_ui_settled(page, inflight_tracker, 3000)

                        modals = page.locator(".ant-modal-content:visible")
                        if modals.count() > 0:
                            top_modal = modals.last
                            is_simple_alert = (
                                top_modal.locator(".ant-modal-confirm-body:visible").count() > 0
                                and top_modal.locator(".ag-root-wrapper, form, input, table").count() == 0
                            )
                            if not is_simple_alert:
                                modal_title_el = top_modal.locator(".ant-modal-title:visible")
                                modal_title = (
                                    modal_title_el.first.inner_text().strip()
                                    if modal_title_el.count() > 0
                                    else display_btn_label
                                )
                                if modal_title not in captured_modal_titles:
                                    captured_modal_titles.add(modal_title)
                                    popup_idx += 1
                                    fname = f"05_popup_{popup_idx:02d}_{_safe_filename(display_btn_label)}.png"
                                    _save_shot(
                                        page,
                                        "05_popup",
                                        fname,
                                        f"버튼 [{display_btn_label}] 클릭 → 모달 ({modal_title})",
                                        clip_locator=top_modal if modal_only else None,
                                    )
                                    popup_clicked.append(
                                        {
                                            "label": display_btn_label,
                                            "kind": "button",
                                            "opened": True,
                                            "modal_title": modal_title,
                                            "file": fname,
                                        }
                                    )
                                    popup_opened_modals.append(
                                        {
                                            "trigger": display_btn_label,
                                            "modal_title": modal_title,
                                            "file": fname,
                                        }
                                    )
                            else:
                                confirm_txt = (
                                    top_modal.locator(".ant-modal-confirm-body:visible")
                                    .first.inner_text()
                                    .strip()
                                    .replace("\n", " ")[:120]
                                )
                                reason = f"안내/확인창: {confirm_txt}"
                                popup_clicked.append(
                                    {
                                        "label": display_btn_label,
                                        "kind": "button",
                                        "opened": False,
                                        "reason": reason,
                                    }
                                )
                                popup_not_opened.append(
                                    {"label": display_btn_label, "reason": reason}
                                )
                            _dismiss_all_modals(page)
                        else:
                            # 모달이 안 열린 경우: 토스트 메시지 또는 추정 사유 기록
                            cur_toasts = [
                                t.strip()
                                for t in page.locator(
                                    ".ant-message-notice-content:visible"
                                ).all_inner_texts()
                                if t.strip()
                            ]
                            new_toasts = [t for t in cur_toasts if t not in prev_toasts]
                            toast_msg = new_toasts[-1] if new_toasts else (cur_toasts[-1] if cur_toasts else "")
                            if toast_msg:
                                reason = f"알림: {toast_msg}"
                            elif report.grid_rows_after_search == 0 and report.grids:
                                reason = "그리드 0건 (행 선택 필요 추정)"
                            else:
                                reason = "모달 없음 (조건 미충족 또는 비모달 동작)"
                            popup_clicked.append(
                                {
                                    "label": display_btn_label,
                                    "kind": "button",
                                    "opened": False,
                                    "reason": reason,
                                }
                            )
                            popup_not_opened.append(
                                {"label": display_btn_label, "reason": reason}
                            )
                    except Exception:  # noqa: BLE001
                        _dismiss_all_modals(page)
                        continue

                # 5-B. LookupInput 돋보기 아이콘 (.anticon-search) 클릭
                lookup_icons = active_tab.locator(
                    ".ant-input-affix-wrapper:visible:not(.ant-input-affix-wrapper-disabled) .anticon-search:visible"
                )
                lookup_total = lookup_icons.count()
                lookup_idx = 0

                for l_i in range(min(lookup_total, 12)):
                    try:
                        icon = lookup_icons.nth(l_i)
                        if not icon.is_visible():
                            continue
                        pe = icon.evaluate("el => window.getComputedStyle(el).pointerEvents")
                        if pe == "none":
                            continue
                        _dismiss_all_modals(page)
                        icon.click(timeout=2500)
                        _wait_ui_settled(page, inflight_tracker, 3000)

                        modals = page.locator(".ant-modal-content:visible")
                        if modals.count() > 0:
                            top_modal = modals.last
                            modal_title_el = top_modal.locator(".ant-modal-title:visible")
                            modal_title = (
                                modal_title_el.first.inner_text().strip()
                                if modal_title_el.count() > 0
                                else f"lookup_{l_i + 1}"
                            )
                            if modal_title not in captured_modal_titles:
                                captured_modal_titles.add(modal_title)
                                lookup_idx += 1
                                fname = f"06_lookup_{lookup_idx:02d}_{_safe_filename(modal_title)}.png"
                                _save_shot(
                                    page,
                                    "06_lookup",
                                    fname,
                                    f"돋보기 Lookup 클릭 → 모달 ({modal_title})",
                                    clip_locator=top_modal if modal_only else None,
                                )
                                popup_clicked.append(
                                    {
                                        "label": f"Lookup#{lookup_idx}",
                                        "kind": "lookup",
                                        "opened": True,
                                        "modal_title": modal_title,
                                        "file": fname,
                                    }
                                )
                                popup_opened_modals.append(
                                    {
                                        "trigger": f"Lookup#{lookup_idx}",
                                        "modal_title": modal_title,
                                        "file": fname,
                                    }
                                )
                            _dismiss_all_modals(page)
                    except Exception:  # noqa: BLE001
                        _dismiss_all_modals(page)
                        continue

                # 5-C. 그리드 셀 내부 액션 아이콘 버튼 (iconCell: 상세보기/수정/이력 등)
                grid_icon_btns = active_tab.locator(
                    ".ag-cell button.ant-btn-icon-only:visible:not([disabled]):has(.anticon-edit, .anticon-search, .anticon-history, .anticon-eye, .anticon-swap)"
                )
                for g_i in range(min(grid_icon_btns.count(), 8)):
                    try:
                        g_btn = grid_icon_btns.nth(g_i)
                        if not g_btn.is_visible():
                            continue
                        _dismiss_all_modals(page)
                        g_btn.click(timeout=2500)
                        _wait_ui_settled(page, inflight_tracker, 3000)

                        modals = page.locator(".ant-modal-content:visible")
                        if modals.count() > 0:
                            top_modal = modals.last
                            is_simple_alert = (
                                top_modal.locator(".ant-modal-confirm-body:visible").count() > 0
                                and top_modal.locator(".ag-root-wrapper, form, input, table").count() == 0
                            )
                            modal_title_el = top_modal.locator(".ant-modal-title:visible")
                            modal_title = (
                                modal_title_el.first.inner_text().strip()
                                if modal_title_el.count() > 0
                                else f"grid_popup_{g_i + 1}"
                            )
                            if not is_simple_alert and modal_title not in captured_modal_titles:
                                captured_modal_titles.add(modal_title)
                                popup_idx += 1
                                fname = f"05_popup_{popup_idx:02d}_{_safe_filename(modal_title)}.png"
                                _save_shot(
                                    page,
                                    "05_popup",
                                    fname,
                                    f"그리드 아이콘 클릭 → 모달 ({modal_title})",
                                    clip_locator=top_modal if modal_only else None,
                                )
                                popup_clicked.append(
                                    {
                                        "label": f"GridIcon#{g_i + 1}",
                                        "kind": "grid_icon",
                                        "opened": True,
                                        "modal_title": modal_title,
                                        "file": fname,
                                    }
                                )
                                popup_opened_modals.append(
                                    {
                                        "trigger": f"GridIcon#{g_i + 1}",
                                        "modal_title": modal_title,
                                        "file": fname,
                                    }
                                )
                            _dismiss_all_modals(page)
                    except Exception:  # noqa: BLE001
                        _dismiss_all_modals(page)
                        continue

            report.popup_traversal = {
                "clicked": popup_clicked,
                "opened_modals": popup_opened_modals,
                "not_opened_buttons": popup_not_opened,
                "skipped_dangerous": report.skipped_buttons,
                "skipped_disabled": skipped_disabled,
            }

        except Exception as exc:  # noqa: BLE001
            browser.close()
            return ToolResult(ok=False, error=f"화면 캡처 실행 중 오류 발생: {exc}")

        browser.close()

    report.elapsed_sec = round(time.monotonic() - start_ts, 2)

    # 이상 신호(anomalies) 요약 생성 (이미지 열람 여부 판단용)
    anomalies: list[str] = []
    if report.console_errors:
        anomalies.append(f"콘솔 에러 {len(report.console_errors)}건")
    if report.api_failures:
        anomalies.append(f"네트워크 실패(4xx/5xx) {len(report.api_failures)}건")
    if report.grids and all(g.get("empty", False) for g in report.grids):
        anomalies.append("모든 그리드 데이터 0건(빈 그리드)")
    elif report.grids and report.grids[0].get("empty", False):
        anomalies.append("메인 그리드(Grid #1) 0건")
    wrapped_all: list[str] = []
    for g in report.grids:
        for wh in g.get("wrapped_headers") or []:
            wrapped_all.append(f"Grid#{g['index']}:{wh}")
    if wrapped_all:
        anomalies.append(f"그리드 헤더 줄바꿈/잘림({', '.join(wrapped_all)})")
    if report.horizontal_scroll.get("page"):
        anomalies.append("화면 레이아웃 가로 스크롤 발생")
    if report.warnings:
        anomalies.extend(report.warnings)
    report.anomalies = anomalies

    report_dict = {
        "screen_id": report.screen_id,
        "menu_no": target.menu_no,
        "class_nm": target.class_nm,
        "title": target.title,
        "folder_name": report.folder_name,
        "output_dir": report.output_dir,
        "url": report.url,
        "company": report.company,
        "user": report.user,
        "selected_title": report.selected_title,
        "open_method": report.open_method,
        "elapsed_sec": report.elapsed_sec,
        "search_conditions": report.search_conditions,
        "warnings": report.warnings,
        "grid_rows_after_search": report.grid_rows_after_search,
        "grids": report.grids,
        "buttons": report.buttons,
        "horizontal_scroll": report.horizontal_scroll,
        "popup_traversal": report.popup_traversal,
        "skipped_buttons": report.skipped_buttons,
        "console_errors": report.console_errors,
        "console_error_count": len(report.console_errors),
        "api_failures": report.api_failures,
        "api_failure_count": len(report.api_failures),
        "anomalies": report.anomalies,
        "has_anomalies": len(report.anomalies) > 0,
        "captures": [
            {
                "step": c.step,
                "filename": c.filename,
                "path": c.path,
                "description": c.description,
                **({"boxes": c.boxes} if c.boxes else {}),
            }
            for c in report.captures
        ],
    }
    report_file = screen_out_dir / "report.json"
    report_file.write_text(
        json.dumps(report_dict, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return ToolResult(ok=True, data=report_dict)
