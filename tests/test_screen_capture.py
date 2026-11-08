"""yunhee screen-capture 단위 테스트."""

from __future__ import annotations

from yunhee.tools.screen_capture import (
    ScreenTarget,
    _build_flexlayout_storage_json,
    build_local_api_url,
    build_tenant_url,
    is_safe_popup_button,
    parse_login_spec,
)


def test_parse_login_spec_full():
    spec = parse_login_spec("login=kfstest/104/1111")
    assert spec.company == "kfstest"
    assert spec.user == "104"
    assert spec.password == "1111"


def test_parse_login_spec_without_prefix():
    spec = parse_login_spec("zzz/200/secret")
    assert spec.company == "zzz"
    assert spec.user == "200"
    assert spec.password == "secret"


def test_parse_login_spec_extra_args():
    spec = parse_login_spec(None, ["login=kfstest/104/1111"])
    assert spec.company == "kfstest"
    assert spec.user == "104"
    assert spec.password == "1111"


def test_parse_login_spec_kv_fallback():
    spec = parse_login_spec(None, ["company-id=abc", "user-id=105", "user-pw=9999"])
    assert spec.company == "abc"
    assert spec.user == "105"
    assert spec.password == "9999"


def test_build_tenant_url():
    url = build_tenant_url("localhost:8082/AssetERP", "kfstest")
    assert url == "http://kfstest.localhost:8082/AssetERP"

    url2 = build_tenant_url("http://127.0.0.1:8082/AssetERP", "admin")
    assert url2 == "http://admin.localhost:8082/AssetERP"


def test_build_local_api_url():
    url = build_local_api_url("http://kfstest.localhost:8082/AssetERP/")
    assert url == "http://localhost:8082/AssetERP"


def test_screen_target_folder_name():
    t1 = ScreenTarget(requested_id="1049", menu_no="1049", class_nm="Fnd01_Tab_FundSearch")
    assert t1.folder_name == "1049_Fnd01_Tab_FundSearch"

    t2 = ScreenTarget(requested_id="Sys01_Tab_Company", class_nm="Sys01_Tab_Company")
    assert t2.folder_name == "Sys01_Tab_Company"


def test_is_safe_popup_button():
    assert is_safe_popup_button("신규등록") is True
    assert is_safe_popup_button("불러오기") is True
    assert is_safe_popup_button("상세보기") is True
    assert is_safe_popup_button("권한설정") is True

    # 위험/제외 버튼
    assert is_safe_popup_button("조회") is False
    assert is_safe_popup_button("검색") is False
    assert is_safe_popup_button("저장") is False
    assert is_safe_popup_button("저장(3)") is False
    assert is_safe_popup_button("삭제") is False
    assert is_safe_popup_button("엑셀다운로드") is False
    assert is_safe_popup_button("행추가") is False


def test_build_flexlayout_storage_json():
    t = ScreenTarget(
        requested_id="1049",
        menu_no="1049",
        code="1049",
        title="펀드 조회",
        class_nm="Fnd01_Tab_FundSearch",
    )
    settings = _build_flexlayout_storage_json(t)
    tabset = settings["flexlayout_model"]["layout"]["children"][0]
    assert tabset["selected"] == 1
    assert len(tabset["children"]) == 2
    assert tabset["children"][1]["config"]["classNm"] == "Fnd01_Tab_FundSearch"
