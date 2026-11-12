"""yunhee screen-capture 단위 테스트."""

from __future__ import annotations

import pytest

from yunhee.tools.screen_capture import (
    ScreenTarget,
    _build_flexlayout_storage_json,
    build_local_api_url,
    build_tenant_url,
    is_safe_popup_button,
    normalize_label_text,
    parse_login_spec,
    parse_range_spec,
    parse_set_specs,
    parse_viewport_spec,
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


def test_normalize_label_text():
    assert normalize_label_text("  ▼ 신청내역 ") == "신청내역"
    assert normalize_label_text("일자 :") == "일자"
    assert normalize_label_text("*승인기간：") == "승인기간"


def test_parse_range_spec():
    assert parse_range_spec("2025-01-01~2026-12-31") == ("2025-01-01", "2026-12-31")
    assert parse_range_spec("2025-01-01..2025-12-31") == ("2025-01-01", "2025-12-31")
    assert parse_range_spec(None) is None
    with pytest.raises(ValueError):
        parse_range_spec("2025-01-01")


def test_parse_set_specs():
    specs = parse_set_specs(
        [
            "승인기간=2025-01-01~2025-12-31",
            "구분#2=일반",
            "검색=삼성",
        ]
    )
    assert len(specs) == 3
    assert specs[0] == {
        "raw_key": "승인기간",
        "label": "승인기간",
        "occurrence": 1,
        "value": "2025-01-01~2025-12-31",
    }
    assert specs[1] == {
        "raw_key": "구분#2",
        "label": "구분",
        "occurrence": 2,
        "value": "일반",
    }
    assert specs[2]["label"] == "검색"


def test_parse_viewport_spec():
    assert parse_viewport_spec("720p") == (1280, 720)
    assert parse_viewport_spec("810p") == (1440, 810)
    assert parse_viewport_spec("1080p") == (1920, 1080)
    assert parse_viewport_spec("1440x810") == (1440, 810)
    with pytest.raises(ValueError):
        parse_viewport_spec("invalid")


def test_is_safe_popup_button_click_all():
    assert is_safe_popup_button("저장", click_all=False) is False
    assert is_safe_popup_button("저장", click_all=True) is True
    assert is_safe_popup_button("조회", click_all=True) is False
    assert is_safe_popup_button("거래처 관리 바로가기", click_all=True) is False


def test_cli_screen_capture_help_has_boxes():
    from typer.testing import CliRunner

    from yunhee.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["screen-capture", "--help"])
    assert result.exit_code == 0
    assert "--boxes" in result.output
    assert "boxes.json" in result.output


