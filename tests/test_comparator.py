"""comparator 도구 및 compare 커맨드 테스트."""

import json

from yunhee.tools import comparator


def test_eval_test_condition():
    params = {"useYn": "true", "roleName": "%", "emptyVal": ""}

    assert comparator._eval_test_condition("useYn != null", params)
    assert not comparator._eval_test_condition("nonExistent != null", params)
    assert comparator._eval_test_condition("nonExistent == null", params)
    assert comparator._eval_test_condition("useYn == 'true'", params)
    assert not comparator._eval_test_condition("useYn == 'false'", params)
    assert comparator._eval_test_condition("isPostgreSql != null", params)
    assert not comparator._eval_test_condition("isTibero != null", params)


def test_render_mybatis_sql():
    xml = """
    <mapper namespace="sys04_role">
        <select id="selectByName">
            SELECT * FROM sys04_role
            WHERE sys04_role_nm LIKE #{roleName}
            AND sys04_company_id = #{companyId}
            <if test="useYn != null">
                AND sys04_use_yn = #{useYn}
            </if>
        </select>
    </mapper>
    """
    sql, _ = comparator.render_mybatis_sql(
        xml,
        "selectByName",
        {"roleName": "%", "companyId": "28000", "useYn": "true"},
    )
    assert "LIKE '%'" in sql
    assert "= '28000'" in sql
    assert "sys04_use_yn = 'true'" in sql

    # useYn 없는 경우 <if> 제외
    sql_no_use, _ = comparator.render_mybatis_sql(
        xml,
        "selectByName",
        {"roleName": "%", "companyId": "28000"},
    )
    assert "sys04_use_yn" not in sql_no_use


def test_find_screen_grid_cols():
    cols = comparator.find_screen_grid_cols("sys01_company.selectByName")
    assert "companyNm" in cols
    assert "locNm" in cols
    assert "fullAddress" in cols
    assert "leaveMonthNm" in cols


def test_compare_api_sql_mock(monkeypatch):
    # api_client.request_api 목킹
    dummy_api_res = {
        "text": json.dumps({
            "success": True,
            "data": [
                {"roleId": 1, "companyId": 0, "roleNm": "Admin", "seq": "010", "note": "", "defaultRole": "true", "adminYn": "false", "companyNm": "KFS"},
                {"roleId": 2, "companyId": 0, "roleNm": "User", "seq": "020", "note": "", "defaultRole": "false", "adminYn": "false", "companyNm": "KFS"},
            ],
        })
    }

    from yunhee.tools.base import ToolResult
    monkeypatch.setattr(
        comparator,
        "request_api",
        lambda **kwargs: ToolResult(ok=True, data=dummy_api_res),
    )

    # get_connection_string 목킹 대신 실제 DB 또는 더미 연결
    # 실제 DB에서 sys04_role 조회
    res = comparator.compare_api_sql(
        method="GET",
        path="/api/v1/sys/roles",
        sql_ref="sys04_role.selectByName",
        sql_params={"roleName": "일반 사용자", "companyId": "0"},
    )
    assert res.ok
    assert "API rows=2" in res.data["summary"]
