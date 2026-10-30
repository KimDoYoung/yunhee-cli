"""수정사항 045 (1번 compare API 실패 처리 및 2번 분기 조건식 평가기 확장/가드) 검증 테스트."""

import json
from unittest import mock

from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.as_is.mybatis_render import (
    eval_test_condition,
    render,
    render_from_xml_with_meta,
)
from yunhee.tools.base import ToolResult
from yunhee.tools.comparator import compare_api_sql

# ==============================================================================
# 1. Item 1: compare API 서버 오류(HTTP 500, 4xx, success=false) 즉시 실패 검증
# ==============================================================================


def test_045_1_compare_http_500_fails_immediately():
    """Item 1: API HTTP 500 발생 시 rows=0 대조로 넘어가지 않고 즉시 실패 반환."""
    with mock.patch("yunhee.tools.comparator.request_api") as mock_api:
        mock_api.return_value = ToolResult(
            ok=False,
            data={
                "status_code": 500,
                "text": json.dumps({"success": False, "code": "INTERNAL_ERROR", "message": "Constructor auto-mapping failed"}),
                "trace_id": "9d51046c987",
            },
            error="HTTP 500",
        )

        res = compare_api_sql(
            method="GET",
            path="v1/car/bookings",
            sql_ref="car03_booking.selectByDate",
            api_params={"date": "2026-05-29", "type": "all"},
            sql_params={"companyId": "28000", "startDate": "2026-05-29", "type": "all", "personId": "-28656"},
        )

        assert not res.ok, "HTTP 500 응답 시 compare_api_sql은 반드시 ok=False여야 합니다"
        assert res.error is not None
        assert "❌ API 실패: HTTP 500 INTERNAL_ERROR Constructor auto-mapping failed" in res.error
        assert "(추적ID: 9d51046c987) — yunhee log trace 9d51046c987 --raw" in res.error
        # summary 등에 rows=0 ✅ 표기가 없어야 함
        if res.data and "summary" in res.data:
            assert "✅" not in res.data["summary"]


def test_045_1_compare_http_400_business_error():
    """Item 1: API HTTP 400 (업무/입력 예외) 발생 시 'API 업무 오류'로 구분 표기."""
    with mock.patch("yunhee.tools.comparator.request_api") as mock_api:
        mock_api.return_value = ToolResult(
            ok=False,
            data={
                "status_code": 400,
                "text": json.dumps({"success": False, "code": "INVALID_INPUT", "message": "날짜 형식이 올바르지 않습니다"}),
                "trace_id": "400trace123",
            },
            error="HTTP 400",
        )

        res = compare_api_sql(
            method="GET",
            path="v1/car/bookings",
            sql_ref="car03_booking.selectByDate",
            api_params={"date": "not-a-date"},
        )

        assert not res.ok
        assert "❌ API 업무 오류: HTTP 400 INVALID_INPUT 날짜 형식이 올바르지 않습니다" in res.error
        assert "추적ID: 400trace123" in res.error


def test_045_1_compare_http_200_success_false():
    """Item 1: HTTP 200이지만 공통 응답 봉투에서 success=false인 업무 예외 즉시 실패."""
    with mock.patch("yunhee.tools.comparator.request_api") as mock_api:
        mock_api.return_value = ToolResult(
            ok=True,
            data={
                "status_code": 200,
                "text": json.dumps({"success": False, "code": "ACCESS_DENIED", "message": "권한이 없습니다"}),
                "trace_id": "denied_trace",
            },
            error=None,
        )

        res = compare_api_sql(
            method="GET",
            path="v1/car/bookings",
            sql_ref="car03_booking.selectByDate",
        )

        assert not res.ok
        assert "❌ API 업무 오류: HTTP 200 ACCESS_DENIED 권한이 없습니다" in res.error


def test_045_1_compare_cli_exit_code_on_api_error():
    """Item 1: CLI compare 명령 실행 시 API 오류가 발생하면 비정상 종료 코드 1 반환."""
    runner = CliRunner()
    with mock.patch("yunhee.tools.comparator.request_api") as mock_api:
        mock_api.return_value = ToolResult(
            ok=False,
            data={
                "status_code": 500,
                "text": json.dumps({"success": False, "code": "INTERNAL_ERROR"}),
                "trace_id": "err_cli_trace",
            },
            error="HTTP 500",
        )

        result = runner.invoke(
            app,
            ["compare", "GET", "v1/car/bookings", "--sql", "car03_booking.selectByDate"],
        )
        assert result.exit_code == 1
        assert "❌ API 실패: HTTP 500 INTERNAL_ERROR" in result.output or "❌ API 실패: HTTP 500 INTERNAL_ERROR" in result.stderr


# ==============================================================================
# 2. Item 2: MyBatis 분기 조건식 평가기 확장 및 미평가 가드 검증
# ==============================================================================


def test_045_2_string_equals_evaluation():
    """Item 2: x.equals('lit'), 'lit'.equals(x), !x.equals('lit') 평가 검증."""
    params_my = {"type": "my"}
    params_all = {"type": "all"}

    # x.equals('lit')
    assert eval_test_condition("type.equals('my')", params_my)
    assert not eval_test_condition("type.equals('my')", params_all)

    # 'lit'.equals(x)
    assert eval_test_condition("'my'.equals(type)", params_my)
    assert not eval_test_condition("'my'.equals(type)", params_all)

    # !x.equals('lit')
    assert not eval_test_condition("!type.equals('my')", params_my)
    assert eval_test_condition("!type.equals('my')", params_all)

    # x.equalsIgnoreCase('lit')
    assert eval_test_condition("type.equalsIgnoreCase('MY')", params_my)


def test_045_2_car03_booking_select_by_date_branch():
    """Item 2: car03_booking.selectByDate에서 type=all 시 분기 OFF, type=my 시 분기 ON."""
    sql_all, _ = render(
        "car03_booking.selectByDate",
        {"companyId": "28000", "startDate": "2026-05-29", "type": "all", "personId": "-28656"},
    )
    assert "car03_person_id =" not in sql_all, "type=all인 경우 car03_person_id 조건이 없어야 합니다"

    sql_my, _ = render(
        "car03_booking.selectByDate",
        {"companyId": "28000", "startDate": "2026-05-29", "type": "my", "personId": "-28656"},
    )
    assert "car03_person_id = -28656" in sql_my or "car03_person_id =" in sql_my, "type=my인 경우 car03_person_id 조건이 포함되어야 합니다"


def test_045_2_size_without_parens_and_long_literals():
    """Item 2: .size 프로퍼티 접근 및 0l/0L Long 리터럴 비교."""
    # .size != 0 (fundIdList.size != 0)
    assert eval_test_condition("fundIdList.size != 0", {"fundIdList": ["1", "2"]})
    assert not eval_test_condition("fundIdList.size != 0", {"fundIdList": []})
    assert not eval_test_condition("fundIdList.size != 0", {})

    # Long 리터럴 접미사: personId != 0l, orgCodeId != 0L
    assert eval_test_condition("personId != 0l", {"personId": "123"})
    assert not eval_test_condition("personId != 0l", {"personId": "0"})
    assert eval_test_condition("orgCodeId != 0L", {"orgCodeId": "10"})
    assert not eval_test_condition("orgCodeId != 0L", {"orgCodeId": "0"})


def test_045_2_logical_operators_and_empty():
    """Item 2: &&, || 복합 논리 연산자 및 isEmpty() 평가."""
    assert eval_test_condition("dcr01TypeCd != null && dcr01TypeCd != ''", {"dcr01TypeCd": "A"})
    assert not eval_test_condition("dcr01TypeCd != null && dcr01TypeCd != ''", {"dcr01TypeCd": ""})
    assert eval_test_condition("type == 'A' || type == 'B'", {"type": "B"})

    # isEmpty()
    assert eval_test_condition("memo.isEmpty()", {"memo": ""})
    assert eval_test_condition("!memo.isEmpty()", {"memo": "hello"})


def test_045_2_unevaluated_condition_safe_guard(capsys):
    """Item 2: 평가할 수 없는 미지의 식은 임의로 켜지 않고 주석 처리(기본 OFF) 및 경고 출력."""
    xml = """<mapper namespace="test_ns">
    <select id="selectCustom">
        SELECT * FROM test_table WHERE 1=1
        <if test="unknownCustomMethod(arg1)">
            AND secret_filter = 1
        </if>
    </select>
    </mapper>"""

    sql, _missing, branch_log = render_from_xml_with_meta(xml, "selectCustom", {"arg1": "val"})

    captured = capsys.readouterr()
    assert "⚠ 분기 평가 불가: unknownCustomMethod(arg1)" in captured.err
    assert "기본 OFF" in sql
    assert "secret_filter = 1" in sql  # 주석 내부에 위치
    assert "/* ⚠ 분기 평가 불가(기본 OFF): unknownCustomMethod(arg1)" in sql
    assert any("평가 불가" in b for b in branch_log)


def test_045_2_branch_override():
    """Item 2: --branch 옵션을 통해 평가 불가 식 또는 일반 분기를 강제 ON/OFF."""
    xml = """<mapper namespace="test_ns">
    <select id="selectOverride">
        SELECT * FROM test_table WHERE 1=1
        <if test="unknownCustomMethod(arg1)">
            AND forced_col = 100
        </if>
    </select>
    </mapper>"""

    # 강제 ON
    sql_on, _, _ = render_from_xml_with_meta(
        xml,
        "selectOverride",
        {"arg1": "val"},
        branch_overrides={"unknownCustomMethod(arg1)": True},
    )
    assert "AND forced_col = 100" in sql_on
    assert "기본 OFF" not in sql_on

    # car03_booking.selectByDate에서 type=all이지만 강제 ON
    sql_forced, _ = render(
        "car03_booking.selectByDate",
        {"companyId": "28000", "startDate": "2026-05-29", "type": "all", "personId": "999"},
        branch_overrides={"type.equals('my')": True},
    )
    assert "car03_person_id = 999" in sql_forced


def test_045_2_compare_shows_uneval_branches_count():
    """Item 2: compare 실행 결과에 평가 불가 분기 수가 요약에 표시됨."""
    xml = """<mapper namespace="test_branch_count">
    <select id="selectBranchCount">
        SELECT 1 AS col
        <if test="someUnknownExpr()">
            WHERE 1=2
        </if>
    </select>
    </mapper>"""

    with mock.patch("yunhee.tools.comparator.request_api") as mock_api, \
         mock.patch("yunhee.tools.comparator.find_mapper_file") as mock_find, \
         mock.patch("yunhee.tools.comparator.psycopg.connect") as mock_conn:

        mock_api.return_value = ToolResult(
            ok=True,
            data={"status_code": 200, "text": json.dumps({"success": True, "data": [{"col": 1}]})},
        )
        mock_path = mock.MagicMock()
        mock_path.read_text.return_value = xml
        mock_find.return_value = mock_path

        mock_cursor = mock.MagicMock()
        mock_cursor.fetchall.return_value = [(1,)]
        mock_cursor.description = [("col",)]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        res = compare_api_sql(
            method="GET",
            path="v1/test",
            sql_ref="test_branch_count.selectBranchCount",
        )
        assert res.ok
        assert "(분기 1개 평가 불가)" in res.data["summary"]
