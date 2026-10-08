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
