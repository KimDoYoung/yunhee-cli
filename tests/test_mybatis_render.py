"""MyBatis SQL 렌더러(mybatis_render) 단위 테스트."""

from pathlib import Path

from yunhee.tools.as_is.mybatis_render import (
    eval_bind,
    eval_test_condition,
    load_statements,
    render,
)


def test_eval_test_condition():
    # 1. null / empty check
    assert eval_test_condition("val != null", {"val": "123"}) is True
    assert eval_test_condition("val != null", {"val": ""}) is False
    assert eval_test_condition("val != null", {}) is False

    assert eval_test_condition("val != ''", {"val": "hello"}) is True
    assert eval_test_condition("val != ''", {"val": ""}) is False

    # 2. boolean literal (== true, == false)
    assert eval_test_condition("isTrue == true", {"isTrue": True}) is True
    assert eval_test_condition("isTrue == true", {"isTrue": "true"}) is True
    assert eval_test_condition("isTrue == true", {"isTrue": False}) is False
    assert eval_test_condition("isTrue == false", {"isTrue": False}) is True
    assert eval_test_condition("isTrue == false", {"isTrue": True}) is False

    # 3. size() check
    assert eval_test_condition("items.size() > 0", {"items": [1, 2, 3]}) is True
    assert eval_test_condition("items.size() > 0", {"items": []}) is False
    assert eval_test_condition("items.size() > 0", {}) is False

    # 4. and / or compound expressions
    assert eval_test_condition("a != null and b == 'foo'", {"a": 1, "b": "foo"}) is True
    assert eval_test_condition("a != null and b == 'foo'", {"a": 1, "b": "bar"}) is False
    assert eval_test_condition("a != null or b == 'foo'", {"a": None, "b": "foo"}) is True

    # 5. db vendor check
    assert eval_test_condition("_databaseId == 'postgresql'", {}) is True
    assert eval_test_condition("isPostgreSql", {}) is True
    assert eval_test_condition("isOracle", {}) is False

    # 6. unknown expression -> warns to stderr and returns False
    assert eval_test_condition("someComplexMethod(x) == 1", {"x": 1}) is False


def test_eval_bind():
    # 1. direct param copy
    params = {"orig": "hello"}
    eval_bind("target", "orig", params)
    assert params["target"] == "hello"

    # 2. string concatenation
    params = {"kw": "search"}
    eval_bind("pattern", "'%' + kw + '%'", params)
    assert params["pattern"] == "%search%"


def test_render_cross_namespace_and_include(tmp_path: Path):
    mapper_dir = tmp_path / "mapper"
    mapper_dir.mkdir()

    # 1. common.xml
    common_xml = mapper_dir / "common.xml"
    common_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="common">
    <sql id="companyFilter">
        AND company_id = #{companyId}
    </sql>
    <sql id="withPaging">
        WITH paging AS (SELECT 1 AS pno)
    </sql>
</mapper>
""", encoding="utf-8")

    # 2. user.xml
    user_xml = mapper_dir / "user.xml"
    user_xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="user">
    <select id="selectUsers">
        <include refid="common.withPaging"/>
        SELECT user_id, user_nm
        FROM sys01_user
        WHERE 1=1
        <include refid="common.companyFilter"/>
        <if test="userName != null and userName != ''">
            AND user_nm = #{userName}
        </if>
    </select>
</mapper>
""", encoding="utf-8")

    stmts = load_statements(tmp_path)
    assert "common.companyFilter" in stmts
    assert "user.selectUsers" in stmts

    # params 모드 렌더링
    sql_rendered, missing = render(
        "user.selectUsers",
        params={"companyId": 100, "userName": "Alice"},
        mode="params",
        statements=stmts,
    )
    assert missing == []
    assert "WITH paging AS" in sql_rendered
    assert "AND company_id = '100'" in sql_rendered
    assert "AND user_nm = 'Alice'" in sql_rendered

    # structure 모드 렌더링 (include는 펼치고 태그는 보존)
    sql_struct, _ = render(
        "user.selectUsers",
        mode="structure",
        statements=stmts,
    )
    assert "<if test=" in sql_struct
    assert "company_id = #{companyId}" in sql_struct


def test_greater_than_in_if_tag_and_eval_condition():
    """<if test="personId > 1">의 > 가 태그 끝으로 오인되지 않고 정상 파싱 및 평가되는지 검증."""
    from yunhee.tools.as_is.mybatis_render import (
        mask_sql_preserve,
        parse_xml,
        render_from_xml,
    )

    # 1. 숫자 대소비교 eval_test_condition 검증
    assert eval_test_condition("personId > 1", {"personId": "29035"}) is True
    assert eval_test_condition("personId > 1", {"personId": "0"}) is False
    assert eval_test_condition("personId > 1", {"personId": "1"}) is False
    assert eval_test_condition("personId >= 1", {"personId": "1"}) is True
    assert eval_test_condition("personId < 10", {"personId": "5"}) is True
    assert eval_test_condition("personId <= 10", {"personId": "10"}) is True
    assert eval_test_condition("personId == 10", {"personId": "10"}) is True
    assert eval_test_condition("personId != 10", {"personId": "5"}) is True
    assert eval_test_condition("personId &gt; 1", {"personId": "29035"}) is True
    assert eval_test_condition("personId &lt; 10", {"personId": "5"}) is True
    assert eval_test_condition("personId > 1", {}) is False

    # 2. parse_xml 파싱 시 > 가 태그 닫기로 오인되지 않는지 검증
    xml = """<mapper namespace="emp">
    <select id="selectByPersonId">
        SELECT emp_id, emp_nm FROM emp00
        WHERE 1=1
        <if test="personId > 1">
            AND person_id = #{personId}
        </if>
    </select>
</mapper>"""
    root = parse_xml(xml)
    mapper = root.children[0]
    sel = next(c for c in mapper.children if getattr(c, "tag", None) == "select")
    if_node = next(c for c in sel.children if getattr(c, "tag", None) == "if")

    assert if_node.attrs.get("test") == "personId > 1"
    # 자식 텍스트에 태그 잔여물(' 1">')이 없어야 함
    assert not any("1\">" in str(child) for child in if_node.children)

    # 3. explain 모드 렌더링: ' 1">' 없이 정상 렌더링
    sql_explain, _ = render_from_xml(xml, "emp.selectByPersonId", mode="explain")
    assert '1">' not in sql_explain
    assert "AND person_id = NULL" in sql_explain

    # 4. params 모드 렌더링: 조건 충족 시 포함, 미충족 시 제외
    sql_true, _ = render_from_xml(xml, "emp.selectByPersonId", params={"personId": "29035"}, mode="params")
    assert '1">' not in sql_true
    assert "AND person_id = '29035'" in sql_true

    sql_false, _ = render_from_xml(xml, "emp.selectByPersonId", params={"personId": "0"}, mode="params")
    assert '1">' not in sql_false
    assert "AND person_id" not in sql_false

    # 5. structure 모드: 원형 보존
    sql_struct, _ = render_from_xml(xml, "emp.selectByPersonId", mode="structure")
    assert '1">' not in sql_struct.replace('<if test="personId > 1">', "")
    assert '<if test="personId > 1">' in sql_struct

    # 6. mask_sql_preserve 검증
    masked = mask_sql_preserve(xml)
    assert '1">' not in masked
    assert "SELECT emp_id" in masked

