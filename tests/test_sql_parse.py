"""SQL 해석 어댑터(tools/sql_parse.py) 테스트."""

import pytest

from yunhee.tools.as_is.mybatis_render import parse_xml_statements
from yunhee.tools.schema_snapshot import load_snapshot
from yunhee.tools.sql_parse import parse_sql_text, parse_statement, schema_from_snapshot

SCHEMA = {
    "sys06_menu": ["sys06_menu_id", "sys06_menu_nm", "sys06_parent_id", "sys06_class_nm", "sys06_use_yn"],
    "emp01_person": ["emp01_id", "emp01_nm", "org_id"],
    "org00": ["org_id", "org_nm"],
}


def test_select_star_expands_with_schema():
    r = parse_sql_text("select * from sys06_menu", SCHEMA)
    assert r.kind == "select"
    assert r.tables == {"sys06_menu": "R"}
    assert r.output_names == SCHEMA["sys06_menu"]
    assert not r.fallback and not r.unresolved


def test_select_star_without_schema_is_unresolved():
    r = parse_sql_text("select * from sys06_menu")
    assert r.output_names is None
    assert any("SELECT *" in u for u in r.unresolved)


def test_qualified_star_and_alias():
    r = parse_sql_text("select m.*, o.org_nm from sys06_menu m join org00 o on o.org_id = m.sys06_parent_id", SCHEMA)
    assert r.output_names == [*SCHEMA["sys06_menu"], "org_nm"]
    assert r.tables == {"org00": "R", "sys06_menu": "R"}


def test_output_names_alias_function_and_expression():
    r = parse_sql_text(
        "select m.sys06_menu_nm nm, count(*) cnt, sys06_class_nm, upper(sys06_menu_nm), 1 + 2 from sys06_menu m", SCHEMA
    )
    assert r.output_names == ["nm", "cnt", "sys06_class_nm", "upper", None]
    assert r.functions == ["count", "upper"]


def test_extract_from_is_not_a_table():
    r = parse_sql_text("select extract(year from p.emp01_id) y from emp01_person p")
    assert r.tables == {"emp01_person": "R"}


def test_columns_resolved_by_alias_and_schema():
    r = parse_sql_text(
        "select p.emp01_nm, org_nm from emp01_person p left join org00 o on o.org_id = p.org_id", SCHEMA
    )
    assert r.columns == {"emp01_person": ["emp01_nm", "org_id"], "org00": ["org_id", "org_nm"]}


def test_ambiguous_unqualified_column_is_unresolved():
    r = parse_sql_text("select org_id from emp01_person p join org00 o on o.org_id = p.org_id", SCHEMA)
    assert any("org_id" in u and "귀속 불명" in u for u in r.unresolved)


def test_cte_is_excluded_and_dml_target_is_write():
    sql = (
        "WITH upsert AS (UPDATE emp02_others SET note = $1 WHERE emp_no = $2 RETURNING emp_no) "
        "INSERT INTO emp02_others (emp_no, note) SELECT $2, $1 WHERE NOT EXISTS (SELECT 1 FROM upsert)"
    )
    r = parse_sql_text(sql)
    assert r.kind == "insert"
    assert r.ctes == ["upsert"]
    assert r.tables == {"emp02_others": "W"}
    # CTE 안의 UPDATE(조건과 함께)와 본 INSERT가 모두 대입으로 잡힌다
    got = {(a.action, a.column, a.value, a.where) for a in r.assignments}
    assert got == {
        ("UPDATE", "note", "$1", "emp_no = $2"),
        ("INSERT", "emp_no", "$2", ""),
        ("INSERT", "note", "$1", ""),
    }


def test_update_assignments_and_where():
    r = parse_sql_text("update fnd01_fund set stat_cd = case when x = 1 then 'A' else 'B' end where stat_cd = 'N' and id = 3")
    assert r.kind == "update"
    assert r.tables == {"fnd01_fund": "W"}
    assert [(a.table, a.column) for a in r.assignments] == [("fnd01_fund", "stat_cd")]
    assert "CASE WHEN" in r.assignments[0].value and r.assignments[0].where == "stat_cd = 'N' AND id = 3"
    assert r.where == ["stat_cd = 'N' AND id = 3"]


def test_update_from_reads_other_table():
    r = parse_sql_text("update a_tbl t set v = s.v from b_tbl s where s.id = t.id")
    assert r.tables == {"a_tbl": "W", "b_tbl": "R"}


def test_delete_and_postgres_syntax():
    assert parse_sql_text("delete from a_b where id = $1::bigint").tables == {"a_b": "W"}
    r = parse_sql_text(
        "insert into a_b (id, v) values ($1::bigint, f_create_seq('x')) on conflict (id) do update set v = excluded.v returning id"
    )
    assert r.tables == {"a_b": "W"}
    assert ("a_b", "v", "excluded.v", "CONFLICT") in [(a.table, a.column, a.value, a.action) for a in r.assignments]
    assert "f_create_seq" in r.functions


def test_syntax_error_falls_back_and_says_so():
    r = parse_sql_text("SELECT FROM WHERE (( from foo_bar")
    assert r.fallback and r.error
    assert r.tables == {"foo_bar": "R"}
    assert any("정규식 추정" in u for u in r.unresolved)


MAPPER = """<mapper namespace="emp02_others">
  <sql id="cols">emp_no, note</sql>
  <select id="selectOne" resultType="map">
    WITH base AS (SELECT <include refid="cols"/> FROM emp02_others)
    SELECT b.*, p.emp01_nm FROM base b JOIN emp01_person p ON p.emp01_id = b.emp_no
    <where>
      <if test="note != null"> AND note = #{note}</if>
      <if test="orderBy != null"> AND ${orderBy} = 1</if>
    </where>
  </select>
  <update id="save">UPDATE emp02_others SET note = #{note} WHERE emp_no = #{empNo}</update>
</mapper>"""


def test_mybatis_statement_expands_includes_and_if():
    _, statements = parse_xml_statements(MAPPER)
    res = parse_statement("emp02_others.selectOne", statements, SCHEMA)
    assert res.ok
    parsed = res.data
    assert parsed.ctes == ["base"]
    assert parsed.tables == {"emp01_person": "R", "emp02_others": "R"}
    assert any("${orderBy}" in u for u in parsed.unresolved)  # ${}는 1로 대체되므로 반드시 알린다


def test_mybatis_update_statement():
    _, statements = parse_xml_statements(MAPPER)
    parsed = parse_statement("emp02_others.save", statements).data
    assert parsed.kind == "update"
    assert parsed.tables == {"emp02_others": "W"}
    assert [(a.column, a.value) for a in parsed.assignments] == [("note", "NULL")]


def test_mybatis_unknown_statement_is_error():
    _, statements = parse_xml_statements(MAPPER)
    res = parse_statement("emp02_others.nope", statements)
    assert not res.ok and "nope" in res.error


def test_real_snapshot_sys06_menu():
    snap = load_snapshot("LOCAL_DB")
    if not snap.ok:
        pytest.skip("LOCAL_DB 스냅샷 없음")
    schema = schema_from_snapshot(snap.data)
    if "sys06_menu" not in schema:
        pytest.skip("스냅샷에 sys06_menu 없음")
    r = parse_sql_text("select * from sys06_menu", schema)
    assert r.output_names == schema["sys06_menu"]
    assert len(r.output_names) >= 10


CHOOSE_MAPPER = """<mapper namespace="msc01">
  <select id="calendar" resultType="map">
    SELECT * FROM msc01_schedule m WHERE 1 = 1
    <choose>
      <when test="level == '0010'"> AND m.a = #{a} </when>
      <when test="level != '0030'">
        AND m.org_id IN (SELECT org_id FROM org00_org_info START WITH org_id = #{o} CONNECT BY parent_id = PRIOR org_id)
      </when>
      <otherwise> AND m.b IN (SELECT b FROM sys12_calendar) </otherwise>
    </choose>
  </select>
</mapper>"""


def test_choose_branches_are_all_covered():
    _, statements = parse_xml_statements(CHOOSE_MAPPER)
    single = parse_statement("msc01.calendar", statements, all_branches=False).data
    assert list(single.tables) == ["msc01_schedule"]
    merged = parse_statement("msc01.calendar", statements).data
    assert set(merged.tables) == {"msc01_schedule", "org00_org_info", "sys12_calendar"}
    # PostgreSQL 문법이 아닌 분기(START WITH)에서 온 테이블은 추정이라는 사실을 알린다
    assert any("정규식으로 추정" in u for u in merged.unresolved)


def test_commented_out_sql_is_not_counted():
    xml = """<mapper namespace="n"><select id="s">
      <!-- SELECT * FROM old_table -->
      SELECT f_create_no(#{a})
    </select></mapper>"""
    _, statements = parse_xml_statements(xml)
    assert parse_statement("n.s", statements).data.tables == {}


def test_alias_that_looks_like_table_is_not_counted():
    r = parse_sql_text("SELECT sys01_company_id AS sys09_code FROM sys01_company")
    assert list(r.tables) == ["sys01_company"]
