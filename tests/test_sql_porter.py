"""sql_porter 도구 및 port-sql, port-save 커맨드 테스트."""

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools.as_is import sql_porter


def test_determine_java_type():
    assert sql_porter.determine_java_type("role_id", "numeric") == "Long"
    assert sql_porter.determine_java_type("company_id", "numeric") == "Long"
    assert sql_porter.determine_java_type("role_nm", "character varying(100)") == "String"
    assert sql_porter.determine_java_type("seq", "character varying(10)") == "String"
    assert sql_porter.determine_java_type("leave_compulsion_rt", "numeric") == "BigDecimal"
    assert sql_porter.determine_java_type("start_date", "date") == "LocalDate"
    assert sql_porter.determine_java_type("reg_dt", "timestamp") == "LocalDateTime"
    assert sql_porter.determine_java_type("count", "", is_calculated=True, expr="COUNT(*)") == "Long"
    assert sql_porter.determine_java_type("company_nm", "", is_calculated=True, expr="f_get_company_nm(cid)") == "String"


def test_port_sql_sys04_role():
    res = sql_porter.port_sql("sys04_role.selectByName")
    assert res.ok
    output = res.data["output"]

    # roleColumns 확인
    assert '<sql id="roleColumns">' in output
    assert "sys04_role_id                        AS role_id" in output
    assert "sys04_company_id                     AS company_id" in output
    assert "sys04_role_nm                        AS role_nm" in output
    assert "sys04_seq                            AS seq" in output
    assert "sys04_note                           AS note" in output
    assert "sys04_default_role                   AS default_role" in output
    assert "sys04_admin_yn                       AS admin_yn" in output
    assert "f_get_company_nm(sys04_company_id)   AS company_nm" in output

    # RoleRes record 확인
    assert "public record RoleRes(" in output
    assert "Long roleId" in output
    assert "Long companyId" in output
    assert "String roleNm" in output
    assert "String seq" in output
    assert "String note" in output
    assert "String defaultRole" in output
    assert "String adminYn" in output
    assert "String companyNm" in output


def test_port_sql_cols_filter():
    res = sql_porter.port_sql(
        "sys01_company.selectByName",
        cols=["companyNm", "locNm", "useYn", "leaveMonthNm", "noticeDate"],
    )
    assert res.ok
    output = res.data["output"]
    assert "AS company_nm" in output
    assert "AS loc_nm" in output
    assert "AS use_yn" in output
    assert "AS leave_month_nm" in output
    assert "AS notice_date" in output
    # 필터 외 컬럼은 제외됨
    assert "AS emp_info" not in output


def test_port_save_sys04_role():
    res = sql_porter.port_save(
        table="sys04_role",
        cols=["role_nm", "seq", "note"],
        company_col="sys04_company_id",
    )
    assert res.ok
    output = res.data["output"]

    assert '<select id="selectNextId" resultType="long" flushCache="true">' in output
    assert "SELECT f_create_seq()" in output

    assert '<insert id="insertRole">' in output
    assert "INSERT INTO sys04_role (sys04_role_id, sys04_company_id, sys04_role_nm, sys04_seq, sys04_note)" in output
    assert "VALUES (#{roleId}, #{companyId}, #{roleNm}, #{seq}, #{note})" in output

    assert '<update id="updateRole">' in output
    assert "sys04_role_nm = #{roleNm}" in output
    assert "WHERE sys04_role_id    = #{roleId}" in output
    assert "AND sys04_company_id = #{companyId}" in output

    assert '<delete id="deleteRoles">' in output
    assert 'collection="roleIds"' in output


def test_cli_port_sql():
    runner = CliRunner()
    result = runner.invoke(cli.app, ["port-sql", "sys04_role.selectByName"])
    assert result.exit_code == 0
    assert "roleColumns" in result.output
    assert "RoleRes" in result.output


def test_cli_port_save():
    runner = CliRunner()
    result = runner.invoke(cli.app, ["port-save", "sys04_role", "--cols", "role_nm,seq,note", "--company-col", "sys04_company_id"])
    assert result.exit_code == 0
    assert "insertRole" in result.output
    assert "updateRole" in result.output
    assert "deleteRoles" in result.output


def test_to_plural():
    assert sql_porter.to_plural("Company") == "Companies"
    assert sql_porter.to_plural("Role") == "Roles"
    assert sql_porter.to_plural("Box") == "Boxes"
    assert sql_porter.to_plural("Branch") == "Branches"
    assert sql_porter.to_plural("Day") == "Days"


def test_statement_tag_from_body():
    # AS-IS가 <select>에 INSERT를 쓴 경우에도 본문으로 태그를 정한다.
    assert sql_porter.statement_tag("/* 주석 */\n<!-- x -->\n INSERT INTO t SELECT 1", "select") == "insert"
    assert sql_porter.statement_tag(" update t set a = 1", "select") == "update"
    assert sql_porter.statement_tag(" CALL p(#{companyId})", "select") == "update"
    assert sql_porter.statement_tag(" WITH x AS (SELECT 1) INSERT INTO t SELECT * FROM x", "select") == "insert"
    assert sql_porter.statement_tag(" SELECT 1", "select") == "select"


def test_inline_fixed_params():
    body = "VALUES (#{companyId}, #{useYn}, ${classTreeId}, #{itemTypeCodeName,jdbcType=VARCHAR}, #{note})"
    puts = [("companyId", None, 159), ("classTreeId", "0", 160), ("useYn", "'true'", 161), ("itemTypeCodeName", "'PayFormulaCode'", 172)]
    new_body, fixed = sql_porter.inline_fixed_params(body, puts)
    assert new_body == "VALUES (#{companyId}, 'true', 0, 'PayFormulaCode', NULL)"
    assert "useYn = 'true' (L161)" in fixed
    assert "note = NULL (map에 없음)" in fixed
    # puts가 없으면(map 사용이 확인 안 됨) 아무것도 바꾸지 않는다
    assert sql_porter.inline_fixed_params(body, []) == (body, [])


def test_java_params():
    assert sql_porter.java_params(" INSERT INTO t SELECT #{companyId}") == "Long companyId"
    assert sql_porter.java_params(" SELECT 1") == ""
    two = sql_porter.java_params(' WHERE a = #{companyId} AND b IN <foreach collection="roleIds" item="id">#{id}</foreach>')
    assert two == '@Param("roleIds") List<Long> roleIds, @Param("companyId") Long companyId'


def test_port_sql_cols_order_and_package():
    res = sql_porter.port_sql(
        "sys01_company.selectByName",
        cols=["useYn", "companyNm", "locNm"],
        dto_package="kr.co.kfs.asseterp.biz.sys.dto",
    )
    assert res.ok
    out = res.data["output"]
    # --cols 순서 유지
    assert out.index("AS use_yn") < out.index("AS company_nm") < out.index("AS loc_nm")
    # 영어 복수형, FQN resultType
    assert '<select id="searchCompanies" resultType="kr.co.kfs.asseterp.biz.sys.dto.CompanyRes">' in out


def test_port_sql_result_type_placeholder():
    res = sql_porter.port_sql("sys04_role.selectByName")
    assert res.ok
    assert 'resultType="{dto.package}.RoleRes"' in res.data["output"]
    assert '<select id="searchRoles"' in res.data["output"]


def test_port_save_side_effects_unique_ids():
    import re

    res = sql_porter.port_save(table="sys01_company", cols=["company_nm"])
    assert res.ok
    out = res.data["output"]
    ids = re.findall(r'<(?:select|insert|update|delete)\s+id="([^"]+)"', out)
    assert len(ids) == len(set(ids))
    if "insertFormIcs30" not in out:
        return  # AS-IS 소스(UpdateDataModel) 없음
    assert "ics30ComplianceInsertFormIcs30" in ids
    assert "ics33ComplianceAnswerInsertFormIcs30" in ids
    # <select>는 selectNextId 하나뿐 (INSERT를 <select>로 쓴 AS-IS도 <insert>로)
    assert re.findall(r'<select\s+id="([^"]+)"', out) == ["selectNextId"]
    assert "#{useYn}" not in out and "#{itemTypeCodeName}" not in out
    assert "    int ics30ComplianceInsertFormIcs30(Long companyId);" in res.data["mapper_methods"]
