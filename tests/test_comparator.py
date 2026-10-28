"""comparator 도구 및 compare 커맨드 테스트."""

import json
from pathlib import Path

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
    assert "= 28000" in sql or "= '28000'" in sql
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


def test_027_compare_multi_grid_and_screen_matching(monkeypatch):
    """027-3: compare 다중 그리드 분리, --grid Screen#method 지정, 비존재 그리드 fallback 방지 검증."""
    # 1. find_screen_grid_info 검증 (Sys05_Tab_PersonRole은 buildUserGrid와 buildRoleGrid 두 개 보유)
    # (1) #method 직접 지정: buildRoleGrid
    info_role = comparator.find_screen_grid_info(
        "dummy.sql",
        grid_class="Sys05_Tab_PersonRole#buildRoleGrid",
    )
    assert not info_role["not_found"]
    assert info_role["label"] == "Sys05_Tab_PersonRole#buildRoleGrid"
    # buildRoleGrid 4컬럼: roleName, userRoleYn, seq, note (또는 매핑된 이름)
    assert len(info_role["cols"]) == 4
    assert any("role" in c.lower() for c in info_role["cols"])
    assert not any("emp" in c.lower() for c in info_role["cols"])

    # (2) #method 직접 지정: buildUserGrid
    info_user = comparator.find_screen_grid_info(
        "dummy.sql",
        grid_class="Sys05_Tab_PersonRole#buildUserGrid",
    )
    assert not info_user["not_found"]
    assert info_user["label"] == "Sys05_Tab_PersonRole#buildUserGrid"
    assert len(info_user["cols"]) >= 8
    assert any("emp" in c.lower() for c in info_user["cols"])

    # (3) 클래스만 지정 시 api_fields와 가장 많이 겹치는 그리드 자동 선택
    info_auto_role = comparator.find_screen_grid_info(
        "dummy.sql",
        grid_class="Sys05_Tab_PersonRole",
        api_fields={"roleName", "seq", "note"},
    )
    assert info_auto_role["label"] == "Sys05_Tab_PersonRole#buildRoleGrid"

    info_auto_user = comparator.find_screen_grid_info(
        "dummy.sql",
        grid_class="Sys05_Tab_PersonRole",
        api_fields={"empKorName", "orgKorName", "empNo"},
    )
    assert info_auto_user["label"] == "Sys05_Tab_PersonRole#buildUserGrid"

    # (4) 존재하지 않는 그리드 지정 시 fallback 방지 및 not_found 플래그
    info_none = comparator.find_screen_grid_info(
        "dummy.sql",
        grid_class="NonExistent_Tab_Screen",
    )
    assert info_none["not_found"]
    assert info_none["cols"] == set()

    # 2. compare_api_sql 실행 시 요약문 출력 검증
    dummy_api_res = {
        "text": json.dumps({
            "success": True,
            "data": [
                {"roleName": "Admin", "seq": "010", "note": "관리자", "userRoleYn": "Y"},
            ],
        })
    }
    from yunhee.tools.base import ToolResult
    monkeypatch.setattr(
        comparator,
        "request_api",
        lambda **kwargs: ToolResult(ok=True, data=dummy_api_res),
    )

    # (1) 비존재 그리드 지정 시: fallback하지 않고 ⚠ 그리드 못 찾음 경고 출력
    res_none = comparator.compare_api_sql(
        method="GET",
        path="/api/v1/sys/roles",
        sql_ref="sys04_role.selectByName",
        sql_params={"roleName": "%", "companyId": "0"},
        grid="NonExistent_Tab_Screen",
    )
    assert res_none.ok
    assert "⚠ 그리드 못 찾음: NonExistent_Tab_Screen" in res_none.data["summary"]

    # (2) 정상 지정 시: 요약문에 그리드명 및 컬럼수 표기 (Sys05_Tab_PersonRole#buildRoleGrid, 4컬럼)
    res_role = comparator.compare_api_sql(
        method="GET",
        path="/api/v1/sys/roles",
        sql_ref="sys04_role.selectByName",
        sql_params={"roleName": "%", "companyId": "0"},
        grid="Sys05_Tab_PersonRole#buildRoleGrid",
    )
    assert res_role.ok
    assert "(Sys05_Tab_PersonRole#buildRoleGrid, 4컬럼)" in res_role.data["summary"]


def test_028_compare_build_grid_xxx_and_addr_mapping():
    """028-1, 028-5: buildGridXxx 패턴 인식, 변수명 지정(#gridRole), Address ↔ Addr 매핑 검증."""
    # 1. Address ↔ Addr 매핑 검증
    assert comparator._field_covered("emailAddress", {"emailAddr"})
    assert comparator._field_covered("emailAddr", {"emailAddress"})
    assert comparator._field_covered("zipAddress", {"zipAddr"})
    assert comparator._field_covered("zipAddr", {"zipAddress"})
    assert not comparator._field_covered("homeAddress", {"workAddr"})

    # 2. Sys04_Tab_RoleAdmin의 buildGridRole / buildGridCompany 인식 검증
    # (1) #buildGridRole 직접 지정
    info_role = comparator.find_screen_grid_info(
        "dummy.sql",
        grid_class="Sys04_Tab_RoleAdmin#buildGridRole",
    )
    assert not info_role["not_found"]
    assert info_role["label"] == "Sys04_Tab_RoleAdmin#buildGridRole"
    assert "roleName" in info_role["cols"]
    assert "seq" in info_role["cols"]
    assert "defaultRole" in info_role["cols"]

    # (2) 필드/변수명(#gridRole)으로 지정해도 메서드명 라벨로 바인딩
    info_by_var = comparator.find_screen_grid_info(
        "dummy.sql",
        grid_class="Sys04_Tab_RoleAdmin#gridRole",
    )
    assert not info_by_var["not_found"]
    assert info_by_var["label"] == "Sys04_Tab_RoleAdmin#buildGridRole"

    # (3) 클래스만 지정 시 api_fields에 따라 최적 그리드 자동 선택
    info_auto_role = comparator.find_screen_grid_info(
        "dummy.sql",
        grid_class="Sys04_Tab_RoleAdmin",
        api_fields={"roleName", "seq", "note"},
    )
    assert info_auto_role["label"] == "Sys04_Tab_RoleAdmin#buildGridRole"

    info_auto_company = comparator.find_screen_grid_info(
        "dummy.sql",
        grid_class="Sys04_Tab_RoleAdmin",
        api_fields={"locationName"},
    )
    assert info_auto_company["label"] == "Sys04_Tab_RoleAdmin#buildGridCompany"

    # 3. buildGrid, buildXxxGrid, buildGridXxx 3개가 한 화면에 섞인 경우 3개 그리드/라벨 추출
    # (1) 불릿 형식
    sample_bullet = """
- 그리드 `gridBase` (buildGrid()):
  - col1 100 "C1" Text
- 그리드 `gridUser` (buildUserGrid()):
  - col2 100 "C2" Text
- 그리드 `gridRole` (buildGridRole(), 체크박스(다중)):
  - col3 100 "C3" Text
"""
    grids_bullet = comparator._extract_all_grids(sample_bullet, "MixedScreen")
    assert len(grids_bullet) == 3
    assert [g["method"] for g in grids_bullet] == [
        "buildGrid",
        "buildUserGrid",
        "buildGridRole",
    ]

    # (2) Grid Spec 형식
    sample_spec = """
## Grid Spec

```ts
const buildGrid = () => [
  gb.text('col1', 100, 'C1'),
];
const buildUserGrid = () => [
  gb.text('col2', 100, 'C2'),
];
const buildGridRole = () => [
  gb.text('col3', 100, 'C3'),
];
```
"""
    grids_spec = comparator._extract_all_grids(sample_spec, "MixedSpec")
    assert len(grids_spec) == 3
    assert [g["method"] for g in grids_spec] == [
        "buildGrid",
        "buildUserGrid",
        "buildGridRole",
    ]


def test_030_comparator_non_data_props_and_zero_rows():
    """030-4: actionCell/rowNumberer/checkBoxSelection 제외 및 0건 시 '필드 비교 못 함' 출력."""
    # 1. 비데이터 프로퍼티 제외 확인
    spec_text = """## Grid Spec
```ts
const buildGrid = () => [
  gb.text('rowNumberer', 40, 'No'),
  gb.text('checkBoxSelection', 40, '선택'),
  gb.text('companyNm', 150, '회사명'),
  gb.text('actionCell', 60, '관리'),
];
```"""
    grids = comparator._extract_all_grids(spec_text, "TestScreen")
    assert len(grids) == 1
    cols = grids[0]["cols"]
    assert "companyNm" in cols
    assert "rowNumberer" not in cols
    assert "checkBoxSelection" not in cols
    assert "actionCell" not in cols

    # 2. 0건 시 렌더링 메시지 확인 (compare_api_sql 목킹)
    from unittest import mock
    with mock.patch("yunhee.tools.comparator.request_api") as mock_api, \
         mock.patch("yunhee.tools.comparator.psycopg.connect") as mock_conn:
        mock_api.return_value = comparator.ToolResult(
            ok=True,
            data={"status": 200, "data": [], "body": '{"data": []}'},
        )
        mock_cursor = mock.MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.description = [("company_id",), ("company_nm",)]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        res = comparator.compare_api_sql(
            "GET",
            "/api/v1/test",
            "sys01_company.selectByName",
        )
        assert res.ok
        assert "필드 비교 못 함 (행 0건)" in res.data["summary"]
        assert "API rows=0, SQL rows=0 ✅" in res.data["summary"]


def test_042_compare_branch_params_and_string_type_binding(monkeypatch):
    """수정사항042 #2, #14: choose/when 분기 제외 변수 요구 방지, admin orgId=0 미주입, 문자열 코드 바인딩(s:, managerType)."""
    from unittest import mock

    from yunhee.tools.as_is.mybatis_render import render_from_xml_with_meta

    # 1. #14: managerType=21 자동 문자열 바인딩 및 s:/n: 접두사 검증
    xml_emp = """
    <mapper namespace="emp12_manager">
        <select id="selectByPosition">
            SELECT * FROM emp12_manager
            WHERE emp12_company_id = #{companyId}
            AND emp12_manager_type = #{managerType}
            AND emp12_seq = #{seq}
        </select>
    </mapper>
    """
    sql1, missing1, _ = render_from_xml_with_meta(
        xml_emp,
        "selectByPosition",
        {"companyId": "28000", "managerType": "21", "seq": "s:10"},
    )
    assert not missing1
    assert "emp12_company_id = 28000" in sql1
    assert "emp12_manager_type = '21'" in sql1
    assert "emp12_seq = '10'" in sql1

    sql2, _, _ = render_from_xml_with_meta(
        xml_emp,
        "selectByPosition",
        {"companyId": "28000", "managerType": "n:21", "seq": "10"},
    )
    assert "emp12_manager_type = 21" in sql2

    # 2. #2: admin 로그인 시 user_info(org_id=0)가 choose/when orgId 분기를 잘못 켜지 않는지 검증
    xml_tdm = """
    <mapper namespace="tdm99_mock">
        <select id="selectDashboardUndone">
            SELECT tdm51_chck_id FROM tdm51_chck
            WHERE tdm51_company_id = #{companyId}
            <choose>
                <when test="exctId != null">
                    AND tdm51_exct_id = #{exctId}
                </when>
                <when test="orgId != null">
                    AND tdm51_org_id = f_get_org(#{orgId}, #{retrieveType})
                </when>
            </choose>
        </select>
    </mapper>
    """
    from yunhee.tools.as_is import mybatis_render

    monkeypatch.setattr(mybatis_render, "get_all_statements", lambda *a, **kw: {})
    monkeypatch.setattr(comparator, "find_mapper_file", lambda ns, sr=None: comparator.Path("mock.xml"))
    monkeypatch.setattr(comparator.Path, "read_text", lambda self, **kw: xml_tdm)

    with mock.patch("yunhee.tools.comparator.request_api") as mock_api, \
         mock.patch("yunhee.tools.comparator.psycopg.connect") as mock_conn:
        mock_api.return_value = comparator.ToolResult(
            ok=True,
            data={
                "status": 200,
                "text": json.dumps({"success": True, "data": [{"chckId": 1}, {"chckId": 2}, {"chckId": 3}]}),
                "user_info": {"user_id": 0, "org_id": 0, "company_id": 28000},
            },
        )
        mock_cursor = mock.MagicMock()
        mock_cursor.fetchall.return_value = [(1,), (2,), (3,)]
        mock_cursor.description = [("tdm51_chck_id",)]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        res = comparator.compare_api_sql(
            "GET",
            "/api/v1/tdm/check-manuals/dashboard-undone",
            "tdm99_mock.selectDashboardUndone",
            sql_params={"companyId": "28000", "exctId": "1018"},
            as_user="admin",
        )
        assert res.ok
        assert "API rows=3, SQL rows=3 ✅" in res.data["summary"]
        assert "branch: exctId ON, orgId OFF" in res.data["summary"]
        assert "retrieveType" not in res.data["summary"]


def test_042_compare_naming_rule_diff_and_paging(monkeypatch):
    """수정사항042 #7, #20: 가짜 열(new) 제외, 범용 모델(string02) 이름 대조 생략, PageRes(rows/total) 및 --total-sql 검증."""
    from unittest import mock

    # 1. #7: new 가짜 열 제외 확인
    bullet_text = """
- 그리드 `grid` (buildGrid()):
  - new 100 "그룹헤더" HeaderGroupMap
  - string02 120 "성명" Text
  - long01 80 "합계" Number
"""
    grids = comparator._extract_all_grids(bullet_text, "Emp10_Tab_Print")
    assert len(grids) == 1
    assert "new" not in grids[0]["cols"]
    assert "string02" in grids[0]["cols"]
    assert "long01" in grids[0]["cols"]

    # 2. #7 & #20: PageRes 응답 + 범용 모델 컬럼(string02, long01) 비교 시 이름 대조 생략 및 total SQL 검증
    monkeypatch.setattr(
        comparator,
        "find_screen_grid_info",
        lambda *a, **kw: {"cols": {"string02", "long01"}, "label": "Emp10_Tab_Print#buildGrid", "not_found": False},
    )

    page_rows = [{"empKorNm": f"사원{i}", "totCnt": i, "deptNm": "운용"} for i in range(5)]
    with mock.patch("yunhee.tools.comparator.request_api") as mock_api, \
         mock.patch("yunhee.tools.comparator.psycopg.connect") as mock_conn:
        mock_api.return_value = comparator.ToolResult(
            ok=True,
            data={
                "status": 200,
                "text": json.dumps({"success": True, "data": {"total": 390, "rows": page_rows}}),
            },
        )
        mock_cursor = mock.MagicMock()
        # 첫 번째 호출: 페이지 SQL (5건), 두 번째 호출: total SQL (390)
        mock_cursor.fetchall.return_value = [(f"사원{i}", i, "운용") for i in range(5)]
        mock_cursor.fetchone.return_value = (390,)
        mock_cursor.description = [("string02",), ("long01",), ("string03",)]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        # (a) --total-sql 미지정 시
        res_page = comparator.compare_api_sql(
            "GET",
            "/api/v1/apr/download-histories",
            "sys04_role.selectByName",
            sql_params={"roleName": "%", "companyId": "0"},
        )
        assert res_page.ok
        assert "API rows=5 (total 390), SQL rows=5 ✅" in res_page.data["summary"]
        assert "ℹ 이름 규칙 차이로 이름 대조 생략 (그리드 열 2개, API 필드 3개)" in res_page.data["summary"]
        assert "⚠️" not in res_page.data["summary"]

        # (b) --total-sql 지정 시
        res_total = comparator.compare_api_sql(
            "GET",
            "/api/v1/apr/download-histories",
            "sys04_role.selectByName",
            sql_params={"roleName": "%", "companyId": "0"},
            sql_total_ref="sys04_role.selectByName",
        )
        assert res_total.ok
        assert "API rows=5 (total 390), SQL rows=5 ✅, total SQL 390 ✅" in res_total.data["summary"]


def test_044_compare_src_index_support(tmp_path: Path, monkeypatch):
    """044-1: compare --src-index 옵션 지원 및 하위 디렉터리 색인 인식 검증."""
    from unittest.mock import MagicMock, patch

    from typer.testing import CliRunner

    from yunhee.cli import app
    from yunhee.tools.base import ToolResult

    custom_idx = tmp_path / "custom_index"
    screen_dir = custom_idx / "tdm" / "screens"
    screen_dir.mkdir(parents=True)
    md_content = """# Tdm51_TabPage_CheckOrg

### Tdm51_TabPage_CheckOrg (`client/vi/tdm/Tdm51_TabPage_CheckOrg.java`, 100줄)

- 그리드 `checkManlGrid` (buildGrid()):
  - selectYn 40 "선택" Boolean
  - checkItem 120 "점검항목" Text
  - checkerName 100 "점검자" Text

## Grid Spec
```tsx
const buildGrid = () => [
  gb.boolean("selectYn", 40, "선택"), // L10 selectYn
  gb.text("checkItem", 120, "점검항목"), // L11 checkItem
  gb.text("checkerName", 100, "점검자"), // L12 checkerName
];
```
"""
    (screen_dir / "Tdm51_TabPage_CheckOrg.md").write_text(md_content, encoding="utf-8")

    # 1. find_screen_grid_info에 src_index 전달 시 색인 인식 검증
    # (a) src_index 미지정 시 (빈 폴더를 WORK_DIR로 모의하여 비존재)
    empty_dir = tmp_path / "empty_dir"
    empty_dir.mkdir()
    monkeypatch.setattr("yunhee.config.WORK_DIR", empty_dir)
    monkeypatch.setattr("yunhee.tools.as_is.WORK_DIR", empty_dir)

    info_fail = comparator.find_screen_grid_info(
        "tdm52_chck_manl.selectByChckOrgId",
        grid_class="Tdm51_TabPage_CheckOrg",
        src_index=empty_dir,
    )
    assert info_fail["not_found"]

    # (b) src_index 지정 시 정상 인식
    info_ok = comparator.find_screen_grid_info(
        "tdm52_chck_manl.selectByChckOrgId",
        grid_class="Tdm51_TabPage_CheckOrg",
        src_index=custom_idx,
    )
    assert not info_ok["not_found"]
    assert "Tdm51_TabPage_CheckOrg" in info_ok["label"]
    assert info_ok["cols"] == {"selectYn", "checkItem", "checkerName"}

    # 2. compare_api_sql에 src_index 전달 시 그리드 정상 매핑 검증
    dummy_api_res = {
        "text": json.dumps({
            "success": True,
            "data": [
                {"selectYn": "Y", "checkItem": "Item 1", "checkerName": "User 1"},
            ],
        }),
        "status_code": 200,
        "elapsed_ms": 10.0,
    }
    monkeypatch.setattr(
        "yunhee.tools.comparator.request_api",
        lambda **kwargs: ToolResult(ok=True, data=dummy_api_res),
    )

    with patch("psycopg.connect") as mock_conn:
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("Y", "Item 1", "User 1")]
        mock_cursor.rowcount = 1
        mock_cursor.description = [("select_yn",), ("check_item",), ("checker_name",)]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        res = comparator.compare_api_sql(
            method="GET",
            path="/api/v1/tdm/check-manls",
            sql_ref="tdm52_chck_manl.selectByChckOrgId",
            sql_params={"chckOrgId": "202607289814553"},
            grid="Tdm51_TabPage_CheckOrg",
            src_index=custom_idx,
        )
        assert res.ok
        assert "(Tdm51_TabPage_CheckOrg#buildGrid, 3컬럼)" in res.data["summary"]
        assert "⚠ 그리드 못 찾음" not in res.data["summary"]

    # 3. CLI compare 명령어의 --src-index 옵션 호출 검증
    runner = CliRunner()
    with patch("yunhee.tools.comparator.compare_api_sql") as mock_compare_api_sql:
        mock_compare_api_sql.return_value = ToolResult(
            ok=True,
            data={"summary": "API rows=1, SQL rows=1 ✅  fields ⊇ grid cols ✅ (Tdm51_TabPage_CheckOrg#buildGrid, 3컬럼)"},
        )
        result = runner.invoke(
            app,
            [
                "compare",
                "GET",
                "/api/v1/tdm/check-manls",
                "--sql",
                "tdm52_chck_manl.selectByChckOrgId",
                "--grid",
                "Tdm51_TabPage_CheckOrg",
                "--src-index",
                str(custom_idx),
            ],
        )
        assert result.exit_code == 0
        assert mock_compare_api_sql.call_args.kwargs["src_index"] == custom_idx



