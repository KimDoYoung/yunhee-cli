"""Playwright 기반 TOBE 화면 및 팝업 자동 캡처 도구 (yunhee screen-capture).

LLM을 개입시키지 않고 결정적(Deterministic) DOM 요소 탐색을 통해:
1. login=company/user/pw 파싱 및 서브도메인 테넌트 URL 구성
2. 사전 API 탐색으로 겸직(Emp04_Lookup_AddTitleList) 목록 및 대상 화면(screen-id) 보유 겸직 자동 판별
3. 브라우저 로그인 및 겸직선택·출퇴근 팝업 자동 통과
4. TopBar 화면번호 입력(Enter) 또는 FlexLayout 모델 주입(Deeplink)으로 화면 오픈
5. 초기 화면 → [조회] 클릭 → 첫 행 선택 → 서브 탭 순회 → 팝업/Lookup 모달 오픈 순으로 캡처 저장
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse

import httpx

from yunhee import config
from yunhee.tools.api_client import _tenant_headers, resolve_user_credentials
from yunhee.tools.base import ToolResult

# 클릭 금지 버튼 키워드 (데이터 변경, 삭제, 파일 다운로드, 단순 행 조작 등)
DANGEROUS_BUTTON_KEYWORDS: tuple[str, ...] = (
    "저장",
    "삭제",
    "행추가",
    "행삭제",
    "취소",
    "확정",
    "승인",
    "반려",
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
)

SEARCH_BUTTON_KEYWORDS: tuple[str, ...] = ("조회", "검색")


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
            parts.append( _safe_filename(self.menu_no))
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
    elapsed_sec: float = 0.0


def _safe_filename(text: str, max_len: int = 40) -> str:
    cleaned = re.sub(r"[^\w가-힣\-]", "_", text.strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    return (cleaned or "unnamed")[:max_len]


def parse_login_spec(
    login_arg: str | None = None,
    extra_args: list[str] | None = None,
) -> LoginSpec:
    """'login=kfstest/104/1111' 또는 'kfstest/104/1111' 또는 key=value 인자들을 파싱한다."""
    raw = (login_arg or "").strip()

    # extra_args에서 login=... 또는 company-id=... / user-id=... / user-pw=... 추출 지원
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
            return LoginSpec(company=parts[0] or default_company, user=parts[1] or default_user, password=parts[2])
        if len(parts) == 2:
            comp, usr = parts[0] or default_company, parts[1] or default_user
            pw = _resolve_password_fallback(usr, default_pw)
            return LoginSpec(company=comp, user=usr, password=pw)
        if len(parts) == 1 and parts[0]:
            return LoginSpec(company=default_company, user=parts[0], password=_resolve_password_fallback(parts[0], default_pw))

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


def is_safe_popup_button(label: str) -> bool:
    """버튼 텍스트가 팝업/모달 탐색용으로 클릭해도 안전한지 판별한다."""
    text = re.sub(r"\s+", "", label or "")
    if not text:
        return False
    # 조회/검색은 Step 2에서 이미 실행하므로 제외
    if text in SEARCH_BUTTON_KEYWORDS:
        return False
    # 건수 표기 제거 후 비교 (예: 저장(0), 삭제(2))
    base_text = re.sub(r"\(\d+\)$", "", text)
    if not base_text:
        return False
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
                # export const SCREENS 블록 내 식별자 추출
                m = re.search(r"export\s+const\s+SCREENS\b[^{]*\{(.*)\}", content, flags=re.DOTALL)
                body = m.group(1) if m else content
                for ident in re.findall(r"\b([A-Za-z0-9]+_(?:Tab|Page|Edit|Lookup|Popup)_[A-Za-z0-9_]+)\b", body):
                    result[ident.lower()] = ident
                if result:
                    return result
            except OSError:
                continue
    return result


def _find_screen_in_menus(menus: list[dict[str, Any]], screen_id: str) -> dict[str, str] | None:
    """메뉴 트리(MenuLevel_1[])에서 menuNo, classNm, code, title 순으로 일치하는 메뉴 항목을 찾는다."""
    target = screen_id.strip().lower()
    if not target:
        return None

    all_items: list[dict[str, str]] = []
    for m1 in menus:
        for grp in m1.get("groups") or []:
            all_items.extend(grp.get("items") or [])

    # 1. menuNo 또는 classNm 또는 code 완전 일치
    for item in all_items:
        menu_no = str(item.get("menuNo") or "").strip()
        class_nm = str(item.get("classNm") or "").strip()
        code = str(item.get("code") or "").strip()
        if target in (menu_no.lower(), class_nm.lower(), code.lower()):
            return item

    # 2. title 완전 일치
    for item in all_items:
        title = str(item.get("title") or "").strip()
        if title.lower() == target:
            return item

    # 3. classNm 부분 일치 (예: FundSearch -> Fnd01_Tab_FundSearch)
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
        # 1. 로그인
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

        # 2. 겸직 목록 조회 (회사관리자 userId <= 0 이 아닌 경우)
        add_titles: list[dict[str, Any]] = []
        if isinstance(initial_user_id, int) and initial_user_id > 0:
            try:
                at_resp = client.get("/api/v1/emp/add-titles/login-list")
                if at_resp.status_code == 200:
                    add_titles = (at_resp.json().get("data")) or []
            except Exception:  # noqa: BLE001
                add_titles = []

        # 3. 현재(본업무) 메뉴 조회
        current_menus: list[dict[str, Any]] = []
        try:
            m_resp = client.get("/api/v1/sys/menus")
            if m_resp.status_code == 200:
                current_menus = m_resp.json().get("data") or []
        except Exception:  # noqa: BLE001
            current_menus = []

        # 본업무 메타 기록
        main_row = next(
            (r for r in add_titles if r.get("addPersonId") == initial_user_id or r.get("mainTitleYn")),
            None,
        )
        if main_row:
            target.selected_add_person_id = main_row.get("addPersonId")
            target.selected_org_name = main_row.get("orgFullName") or main_row.get("orgName")
            target.selected_title_name = main_row.get("titleName")

        # 사용자가 --title 로 특정 겸직(부서/직책/addPersonId)을 지정한 경우
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
                    sw_resp = client.post("/api/auth/switch-title", json={"addPersonId": add_pid})
                    if sw_resp.status_code == 200 and sw_resp.json().get("data"):
                        user_data = sw_resp.json()["data"]
                        m_resp = client.get("/api/v1/sys/menus")
                        if m_resp.status_code == 200:
                            current_menus = m_resp.json().get("data") or []
                target.selected_add_person_id = add_pid
                target.selected_org_name = matched_title.get("orgFullName") or matched_title.get("orgName")
                target.selected_title_name = matched_title.get("titleName")

        found_item = _find_screen_in_menus(current_menus, screen_id)

        # 4. 본업무 메뉴에 없고 겸직이 여러 개인 경우, 다른 겸직을 순회하며 해당 화면 권한이 있는 겸직 탐색
        if not found_item and not preferred_title and len(add_titles) > 1:
            best_row = main_row
            best_menu_count = _count_menus(current_menus)

            for row in add_titles:
                add_pid = row.get("addPersonId")
                if not add_pid or add_pid == initial_user_id:
                    continue
                sw_resp = client.post("/api/auth/switch-title", json={"addPersonId": add_pid})
                if sw_resp.status_code != 200:
                    continue
                sw_data = sw_resp.json().get("data") or {}
                m_resp = client.get("/api/v1/sys/menus")
                menus_for_row = (m_resp.json().get("data") or []) if m_resp.status_code == 200 else []
                cand = _find_screen_in_menus(menus_for_row, screen_id)
                if cand:
                    found_item = cand
                    user_data = sw_data
                    current_menus = menus_for_row
                    target.selected_add_person_id = add_pid
                    target.selected_org_name = row.get("orgFullName") or row.get("orgName")
                    target.selected_title_name = row.get("titleName")
                    break
                cnt = _count_menus(menus_for_row)
                if cnt > best_menu_count:
                    best_menu_count = cnt
                    best_row = row

            # 어느 겸직에서도 메뉴를 못 찾았으면 가장 메뉴가 많은 겸직(기본 본업무)으로 복귀
            if not found_item and best_row and best_row.get("addPersonId") != user_data.get("userId"):
                sw_resp = client.post("/api/auth/switch-title", json={"addPersonId": best_row["addPersonId"]})
                if sw_resp.status_code == 200 and sw_resp.json().get("data"):
                    user_data = sw_resp.json()["data"]
                target.selected_add_person_id = best_row.get("addPersonId")
                target.selected_org_name = best_row.get("orgFullName") or best_row.get("orgName")
                target.selected_title_name = best_row.get("titleName")

        if found_item:
            target.in_user_menu = True
            target.menu_no = found_item.get("menuNo") or None
            target.code = found_item.get("code") or None
            target.title = found_item.get("title") or None
            target.class_nm = found_item.get("classNm") or None
        else:
            # 사용자 메뉴에 없는 경우: DB sys06_menu 또는 screens.ts 에서 classNm 확인
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
                    # 부분 매칭 시도
                    for k_lower, orig_cls in registered_screens.items():
                        if screen_id.strip().lower() in k_lower:
                            target.class_nm = orig_cls
                            target.code = orig_cls
                            target.title = orig_cls
                            break

        cookies = dict(client.cookies)
        return target, cookies, user_data


def _build_flexlayout_storage_json(target: ScreenTarget | None = None) -> dict[str, Any]:
    """MainFrame이 읽는 asseterp_settings JSON 객체를 생성한다.

    target이 주어지면 해당 화면 탭을 열린/선택된 상태로 주입한다(Deeplink).
    """
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
    """현재 화면에 떠 있는 모달/다이얼로그를 닫기 버튼·X버튼·ESC 순으로 모두 닫는다."""
    for _ in range(max_attempts):
        try:
            modals = page.locator(".ant-modal-content:visible")
            if modals.count() == 0:
                return
            top_modal = modals.last

            # 1. confirm 다이얼로그의 확인/취소/아니오 버튼
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
    # 1. 로그인 폼이 보이는 경우
    login_input = page.locator("input#username:visible, input[placeholder*='로그인 ID']:visible")
    if login_input.count() > 0:
        login_input.first.fill(login_spec.user)
        pw_input = page.locator("input#password:visible, input[type='password']:visible")
        if pw_input.count() > 0:
            pw_input.first.fill(login_spec.password)
        submit_btn = page.locator("button[type='submit']:visible")
        if submit_btn.count() > 0:
            submit_btn.first.click()
        _wait_ui_settled(page, inflight_tracker, 4000)

        # 비밀번호 변경 권고 모달 ("N일 남았습니다. 지금 변경하시겠습니까?" -> [아니오])
        no_btn = page.locator(".ant-modal-confirm-btns button:has-text('아니오'):visible")
        if no_btn.count() > 0:
            no_btn.first.click()
            _wait_ui_settled(page, inflight_tracker, 2000)

    # 2. '로그인 선택' (겸직선택 Emp04_Lookup_AddTitleList) 모달이 보이는 경우
    add_title_modal = page.locator(".ant-modal-content:visible:has(.ant-modal-title:has-text('로그인 선택'))")
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

    # 3. MainFrame 진입 직후 출퇴근 기록 모달 등이 떠 있으면 닫기
    _dismiss_all_modals(page)


def capture_screen(
    screen_id: str,
    login_spec: LoginSpec,
    base_url: str = config.CAPTURE_BASE_URL,
    out_dir: str | Path = config.CAPTURE_OUT_DIR,
    preferred_title: str | None = None,
    include_popups: bool = True,
    headed: bool = False,
    viewport_width: int = 1920,
    viewport_height: int = 1080,
) -> ToolResult:
    """지정한 화면(screen_id)을 오픈하고 단계별 화면 및 팝업들을 캡처하여 저장한다."""
    start_ts = time.monotonic()

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

    # 기존 캡처 png 정리 (이전 실행 파일과 섞이지 않도록)
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

    def _save_shot(page: Any, step_code: str, filename: str, description: str) -> None:
        img_path = screen_out_dir / filename
        page.screenshot(path=str(img_path), full_page=False)
        report.captures.append(
            CaptureItem(
                step=step_code,
                filename=filename,
                path=str(img_path),
                description=description,
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

        # 쿠키 주입
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

        # sessionStorage(2차인증·겸직선택 통과) 및 초기 레이아웃(asseterp_settings) 주입
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

        # 콘솔 에러 및 HTTP 4xx/5xx 실패 수집 (프로필 사진 404 노이즈 제외)
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
            lambda resp: report.api_failures.append(f"HTTP {resp.status} {resp.request.method} {resp.url}")
            if resp.status >= 400 and "/api/" in resp.url and "/files/monitoring" not in resp.url
            else None,
        )

        try:
            page.goto(tenant_url, wait_until="domcontentloaded", timeout=20000)
            _wait_ui_settled(page, inflight_tracker, 5000)

            # 만약 로그인 화면이나 겸직선택 창이 뜨면 통과
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

                # 탭이 정상 오픈되었는지 확인 (My Page 외에 다른 탭 버튼 존재 여부)
                tab_buttons = page.locator(".flexlayout__tab_button:visible")
                if tab_buttons.count() > 1:
                    opened_via_topbar = True
                    report.open_method = f"topbar ({search_term})"

            if not opened_via_topbar:
                # Fallback: FlexLayout 모델에 직접 탭을 주입하여 리로드 (Deeplink)
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

            # 현재 활성화된 화면 탭 컨테이너(.flexlayout__tab:visible)
            active_tab = page.locator(".flexlayout__tab:visible").last

            # Step 1: 01_initial.png (화면 최초 오픈 상태)
            _save_shot(
                page,
                "01_initial",
                "01_initial.png",
                f"화면 최초 오픈 ({target.menu_no or ''} {target.title or target.class_nm or screen_id})".strip(),
            )

            # Step 2: 02_searched.png ([조회]/[검색] 버튼 클릭)
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
                            "el => new Set(Array.from(el.querySelectorAll('.ag-row[row-index]')).map(r => r.getAttribute('row-index'))).size"
                        )
                    )
                except Exception:  # noqa: BLE001
                    return active_tab.locator(".ag-row:visible").count()

            if clicked_search:
                _wait_ui_settled(page, inflight_tracker, 6000)
                # 조회 시 경고/안내 모달이 뜬 경우 닫기
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

            # Step 3: 03_row_selected.png (그리드 행 선택)
            visible_rows = active_tab.locator(".ag-row:visible")
            if visible_rows.count() > 0:
                try:
                    # 첫 행이 이미 자동 선택되어 있고 2행이 있으면 2행을 클릭해 행 전환 바인딩도 검증
                    row_idx_1 = active_tab.locator(".ag-row[row-index='1']:visible")
                    target_row = row_idx_1.first if row_idx_1.count() > 0 else visible_rows.first
                    cells = target_row.locator(".ag-cell:visible")
                    target_cell = cells.nth(1) if cells.count() > 1 else cells.first
                    target_cell.click(timeout=2500)
                    _wait_ui_settled(page, inflight_tracker, 3000)
                    _save_shot(
                        page,
                        "03_row_selected",
                        "03_row_selected.png",
                        "그리드 행 선택 상태",
                    )
                    # 만약 행 클릭만으로 모달이 열렸다면 닫아준다
                    _dismiss_all_modals(page)
                except Exception:  # noqa: BLE001, S110
                    pass

            # Step 4: 화면 내부 서브 탭(.ant-tabs-tab) 순회 캡처
            sub_tabs = active_tab.locator(".ant-tabs-nav .ant-tabs-tab:visible:not(.ant-tabs-tab-disabled)")
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
                # 첫 번째 서브 탭으로 복귀
                try:
                    sub_tabs.first.click(timeout=2000)
                    _wait_ui_settled(page, inflight_tracker, 2000)
                except Exception:  # noqa: BLE001, S110
                    pass

            # Step 5: 팝업/모달 오픈 버튼 & Lookup 돋보기 & 그리드 액션 아이콘 순회 캡처
            if include_popups:
                # 팝업 탐색 중 실제 CUD(DELETE/PUT/PATCH) 요청이 서버로 나가지 않도록 안전 가드 설정
                def _safety_route_guard(route: Any) -> None:
                    req = route.request
                    method = req.method.upper()
                    if method in ("DELETE", "PUT", "PATCH"):
                        route.abort()
                        return
                    if method == "POST" and "/api/" in req.url:
                        url_lower = req.url.lower()
                        if any(
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
                                "close",
                                "copy",
                            )
                        ):
                            route.abort()
                            return
                    route.continue_()

                page.route("**/api/**", _safety_route_guard)

                # 5-A. 일반 버튼 중 안전한 팝업 호출 후보 클릭
                all_btns = active_tab.locator("button.ant-btn:visible:not([disabled])")
                btn_total = all_btns.count()
                popup_idx = 0
                clicked_labels: set[str] = set()
                captured_modal_titles: set[str] = set()

                for b_i in range(min(btn_total, 25)):
                    try:
                        btn = all_btns.nth(b_i)
                        if not btn.is_visible() or not btn.is_enabled():
                            continue
                        raw_label = (btn.inner_text() or "").strip()
                        clean_label = re.sub(r"\s+", " ", raw_label)
                        if not clean_label or clean_label in clicked_labels:
                            continue
                        if not is_safe_popup_button(clean_label):
                            if clean_label not in SEARCH_BUTTON_KEYWORDS:
                                report.skipped_buttons.append(clean_label)
                            continue

                        clicked_labels.add(clean_label)
                        _dismiss_all_modals(page)

                        btn.click(timeout=2500)
                        _wait_ui_settled(page, inflight_tracker, 3000)

                        modals = page.locator(".ant-modal-content:visible")
                        if modals.count() > 0:
                            top_modal = modals.last
                            # 단순 경고/안내(confirm-warning/info/error) 창인지 확인
                            is_simple_alert = (
                                top_modal.locator(
                                    ".ant-modal-confirm-body:visible"
                                ).count()
                                > 0
                                and top_modal.locator(".ag-root-wrapper, form, input, table").count() == 0
                            )
                            if not is_simple_alert:
                                popup_idx += 1
                                modal_title_el = top_modal.locator(".ant-modal-title:visible")
                                modal_title = (
                                    modal_title_el.first.inner_text().strip()
                                    if modal_title_el.count() > 0
                                    else clean_label
                                )
                                captured_modal_titles.add(modal_title)
                                fname = f"05_popup_{popup_idx:02d}_{_safe_filename(clean_label)}.png"
                                _save_shot(
                                    page,
                                    "05_popup",
                                    fname,
                                    f"버튼 [{clean_label}] 클릭 → 모달 ({modal_title})",
                                )
                            _dismiss_all_modals(page)
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
                                )
                            _dismiss_all_modals(page)
                    except Exception:  # noqa: BLE001
                        _dismiss_all_modals(page)
                        continue

                # 5-C. 그리드 셀 내부 액션 아이콘 버튼 (iconCell: 상세보기/수정/이력 등, 삭제/다운로드 제외)
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
                                )
                            _dismiss_all_modals(page)
                    except Exception:  # noqa: BLE001
                        _dismiss_all_modals(page)
                        continue

        except Exception as exc:  # noqa: BLE001
            browser.close()
            return ToolResult(ok=False, error=f"화면 캡처 실행 중 오류 발생: {exc}")

        browser.close()

    report.elapsed_sec = round(time.monotonic() - start_ts, 2)

    # report.json 저장
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
        "grid_rows_after_search": report.grid_rows_after_search,
        "elapsed_sec": report.elapsed_sec,
        "captures": [
            {
                "step": c.step,
                "filename": c.filename,
                "path": c.path,
                "description": c.description,
            }
            for c in report.captures
        ],
        "skipped_buttons": report.skipped_buttons,
        "console_errors": report.console_errors,
        "api_failures": report.api_failures,
    }
    report_file = screen_out_dir / "report.json"
    report_file.write_text(json.dumps(report_dict, ensure_ascii=False, indent=2), encoding="utf-8")

    return ToolResult(ok=True, data=report_dict)
