"""기존 SQL 해석 코드를 sql_parse 어댑터로 교체한 경로(parse_mapper, src_indexer, analysis sql, sql_checker) 회귀 테스트."""

import importlib.util
from pathlib import Path

from yunhee.tools.analysis import sql as analysis_sql
from yunhee.tools.as_is.mybatis_render import parse_xml_statements
from yunhee.tools.as_is.sql_checker import select_output_names
from yunhee.tools.as_is.src_indexer import parse_mappers

UPSERT = """<mapper namespace="emp02_others">
  <sql id="cols">emp_no, note</sql>
  <update id="upsert">
    WITH upsert AS (UPDATE emp02_others SET note = #{note} WHERE emp_no = #{empNo} RETURNING emp_no)
    INSERT INTO emp02_others (<include refid="cols"/>) SELECT #{empNo}, #{note}
    WHERE NOT EXISTS (SELECT 1 FROM upsert)
  </update>
  <select id="withComments" resultType="map">
    <!-- SELECT * FROM old_commented_table -->
    SELECT extract(year FROM p.birth_dt) y, p.sys01_company_id AS sys09_code FROM emp01_person p
  </select>
</mapper>"""


def _load_parse_mapper():
    path = Path(__file__).resolve().parent.parent / "tools" / "parse_mapper.py"
    spec = importlib.util.spec_from_file_location("parse_mapper_under_test", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _analysis_md(key: str) -> str:
    _, statements = parse_xml_statements(UPSERT)
    obj = {"key": key, "statement": statements[key], "params": {}, "src_root": None, "statements": statements}
    return analysis_sql.render(obj, "md")


def test_analysis_sql_separates_cte_and_lists_dml_targets():
    md = _analysis_md("emp02_others.upsert")
    assert "- **테이블**: emp02_others\n" in md  # CTE 이름(upsert)은 테이블이 아니다
    assert "- **CTE**: upsert" in md
    assert "- **변경 대상**: INSERT emp02_others, UPDATE emp02_others" in md


def test_analysis_sql_ignores_comments_extract_from_and_aliases():
    md = _analysis_md("emp02_others.withComments")
    assert "- **테이블**: emp01_person\n" in md
    assert "old_commented_table" not in md
    assert "sys09_code" not in md.split("테이블")[1].split("\n")[0]


def test_parse_mapper_tables_use_ast_and_fallback_for_sql_fragments():
    pm = _load_parse_mapper()
    _, statements = parse_xml_statements(UPSERT)
    assert pm._statement_tables("emp02_others", "upsert", "update", "", statements) == ["emp02_others"]
    assert pm._statement_tables("emp02_others", "withComments", "select", "", statements) == ["emp01_person"]
    # <sql> 조각은 단독 SQL이 아니므로 정규식 추정을 쓴다
    assert pm._statement_tables("n", "frag", "sql", "FROM act01_journal j", statements) == ["act01_journal"]
    # statements가 없으면(구 호출 방식) 정규식으로 되돌린다
    assert pm._statement_tables("n", "s", "select", "FROM act01_journal j", None) == ["act01_journal"]


def test_src_indexer_parse_mappers_uses_expanded_sql(tmp_path):
    mapper = tmp_path / "server" / "emp" / "mapper"
    mapper.mkdir(parents=True)
    (mapper / "emp02_others.xml").write_text(UPSERT, encoding="utf-8")
    (mapper / "frag.xml").write_text(
        """<mapper namespace="frag">
          <sql id="join">JOIN org00_org_info o ON o.id = a.org_id</sql>
          <select id="byOrg">SELECT a.id FROM emp01_person a <include refid="frag.join"/></select>
        </mapper>""",
        encoding="utf-8",
    )
    statements, _ = parse_mappers(tmp_path, {}, set())
    upsert = statements["emp02_others.upsert"]
    assert upsert.tables == {"emp02_others"} and upsert.ctes == {"upsert"} and upsert.resolved
    assert statements["emp02_others.withComments"].tables == {"emp01_person"}
    # <include> 조각의 테이블은 전개된 SQL에서 나온다
    assert statements["frag.byOrg"].tables == {"emp01_person", "org00_org_info"}


def test_select_output_names_keeps_quoted_alias_and_regex_fallback():
    assert select_output_names('SELECT a AS "fooBar", b FROM t') == ['"fooBar"', "b"]
    # #{}가 남은 SQL은 파싱할 수 없으므로 기존 정규식 추정으로 되돌린다
    assert select_output_names("SELECT a, count(*) cnt FROM t WHERE x = #{x}") == ["a", "cnt"]
