"""AS-IS GXT/DBML 색인 및 SQL 검증 도구 테스트."""

from pathlib import Path
from unittest.mock import patch

from yunhee.tools.as_is.dbml_indexer import index_dbml, mask_secrets, table_domain
from yunhee.tools.as_is.sql_checker import Node, Statement, check_sql, parse_xml, to_sql
from yunhee.tools.as_is.src_indexer import index_src


def test_dbml_indexer_table_domain():
    assert table_domain("emp01_person") == "emp"
    assert table_domain("sys04_role") == "sys"
    assert table_domain("sys04_role_bak") == "_backup"
    assert table_domain("sys04_role_backup") == "_backup"
    assert table_domain("unknown_table") == "_etc"


def test_dbml_indexer_mask_secrets():
    body = "SELECT encrypt('secret_pass', 'my_crypto_key', 'aes') FROM t;"
    masked = mask_secrets(body)
    assert "'my_crypto_key'" not in masked
    assert "'***'" in masked


def test_dbml_indexer_run(tmp_path: Path):
    dbml_content = """# AS-IS DB Schema
- Generated at: 2026-10-02

## DBML

Table "public"."sys04_role" {
  "role_id" bigint [pk]
  "role_cd" varchar(20)
  Note: '역할 코드'
}

Table "public"."emp01_person" {
  "person_id" bigint [pk]
  "person_nm" varchar(50)
  Note: '사원 정보'
}

## Views

### public.v_user_role
SELECT * FROM sys04_role;

## Functions

### public.f_get_user(p_id bigint)
RETURNS varchar AS $$
BEGIN
  RETURN 'test';
END;
$$ LANGUAGE plpgsql;

### public.t_emp_backup()
RETURNS trigger AS $$
BEGIN
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

## Sequences
- seq_sys04_role
- seq_emp01_person

## Triggers
CREATE TRIGGER tr_emp_backup AFTER INSERT ON emp01_person EXECUTE PROCEDURE t_emp_backup();
"""
    source_file = tmp_path / "schema-dbml.md"
    source_file.write_text(dbml_content, encoding="utf-8")
    target_dir = tmp_path / "out_db"

    res = index_dbml(source_file, target_dir)
    assert res.ok is True
    data = res.data
    assert data["tables_count"] == 2
    assert data["views_count"] == 1
    assert data["routines_count"] == 1
    assert data["trigger_fns_count"] == 1

    # 파일 생성 확인
    assert (target_dir / "README.md").is_file()
    assert (target_dir / "tables" / "sys.md").is_file()
    assert (target_dir / "tables" / "emp.md").is_file()
    assert (target_dir / "views.md").is_file()
    assert (target_dir / "triggers.md").is_file()
    assert (target_dir / "functions" / "f_get_user.md").is_file()
    assert not (target_dir / "functions" / "t_emp_backup.md").exists()


def test_src_indexer_run(tmp_path: Path):
    # AS-IS 디렉토리 구조 생성
    app_dir = tmp_path / "src" / "application" / "src" / "main" / "java" / "myApp"
    client_vi = app_dir / "client" / "vi" / "sys"
    client_vi.mkdir(parents=True, exist_ok=True)
    server_sys = app_dir / "server" / "sys"
    server_sys.mkdir(parents=True, exist_ok=True)
    mapper_dir = server_sys / "mapper"
    mapper_dir.mkdir(parents=True, exist_ok=True)

    # 1. MenuOpener.java
    (app_dir / "client" / "vi" / "MenuOpener.java").write_text("""
package myApp.client.vi;
import com.google.gwt.core.client.GWT;
import myApp.client.vi.sys.Sys04_Tab_Role;

public class MenuOpener {
    public static Object createTab(String className) {
        if ("Sys04_Tab_Role".equals(className)) {
            return GWT.create(Sys04_Tab_Role.class);
        }
        return null;
    }
}
""", encoding="utf-8")

    # 2. Sys04_Tab_Role.java
    (client_vi / "Sys04_Tab_Role.java").write_text("""
package myApp.client.vi.sys;

import myApp.client.service.ServiceRequest;

public class Sys04_Tab_Role {
    private TextButton btnSearch = new TextButton("조회");
    private GridBuilder grid = new GridBuilder();

    public Sys04_Tab_Role() {
        btnSearch.addSelectHandler(e -> retrieve());
        grid.addText(m.roleCd(), 100, "역할코드");
    }

    public void retrieve() {
        ServiceRequest req = new ServiceRequest("sys.Sys04_Role.selectList");
        req.addParam("companyId", "1000");
    }
}
""", encoding="utf-8")

    # 3. Sys04_Role.java (서버)
    (server_sys / "Sys04_Role.java").write_text("""
package myApp.server.sys;

import org.apache.ibatis.session.SqlSession;

public class Sys04_Role {
    public void selectList(SqlSession sqlSession, ServiceRequest req, ServiceResult res) {
        sqlSession.selectList("sys04_role.selectList");
    }
}
""", encoding="utf-8")

    # 4. sys04_role.xml (MyBatis)
    (mapper_dir / "sys04_role.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="sys04_role">
    <select id="selectList" resultType="map">
        SELECT role_id, role_cd
        FROM sys04_role
        WHERE company_id = #{companyId}
    </select>
</mapper>
""", encoding="utf-8")

    # 5. menus.tsv
    menus_file = tmp_path / "menus.tsv"
    menus_file.write_text("10\t시스템관리 > 역할관리\tSys04_Tab_Role\ttrue\n", encoding="utf-8")

    target_dir = tmp_path / "out_src"

    res = index_src(tmp_path / "src", target_dir, menus_path=menus_file)
    assert res.ok is True
    data = res.data
    assert data["app_package"] == "application/src/main/java/myApp"
    assert data["screens_count"] == 1
    assert data["service_methods_count"] == 1
    assert data["statements_count"] == 1

    # 산출물 확인
    assert (target_dir / "README.md").is_file()
    assert (target_dir / "menus.md").is_file()
    screen_md = (target_dir / "sys" / "screens" / "Sys04_Tab_Role.md").read_text(encoding="utf-8")
    assert "Sys04_Tab_Role" in screen_md
    assert "sys.Sys04_Role.selectList" in screen_md
    assert "sys04_role" in screen_md
    assert "역할코드" in screen_md
    # events 결과가 UI 절에 함께 들어간다
    assert data["events_classes_count"] >= 1
    assert data["events_errors"] == []
    assert "#### 이벤트" in screen_md
    assert "#### 메서드" in screen_md
    assert "#### 사용된 버튼들" in screen_md
    assert "원본:" not in screen_md
    assert "- 이벤트:" not in screen_md  # events 절과 겹치는 요약 줄은 생략
    assert "- 메서드:" not in screen_md

    res = index_src(tmp_path / "src", target_dir, menus_path=menus_file, with_events=False)
    assert res.ok is True
    screen_md = (target_dir / "sys" / "screens" / "Sys04_Tab_Role.md").read_text(encoding="utf-8")
    assert "#### 이벤트" not in screen_md
    assert "- 이벤트:" in screen_md
    assert "- 메서드:" in screen_md


def test_sql_checker_to_sql():
    xml_text = """
    <select id="selectUsers">
        SELECT * FROM users
        <where>
            <if test="name != null">
                AND name = #{name}
            </if>
        </where>
        <choose>
            <when test="isPostgreSql">
                LIMIT 10
            </when>
            <otherwise>
                ROWNUM &lt;= 10
            </otherwise>
        </choose>
    </select>
    """
    root = parse_xml(xml_text)
    node = next(c for c in root.children if isinstance(c, Node))
    st = Statement("user_mapper", "selectUsers", "select", node, Path("mapper.xml"), 1)
    statements = {st.key: st}

    sql = to_sql(st, statements)
    assert "WHERE 1=1" in sql
    assert "name = NULL" in sql
    assert "LIMIT 10" in sql
    assert "ROWNUM" not in sql


def test_sql_checker_run_mock(tmp_path: Path):
    app_dir = tmp_path / "src" / "myApp"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "client").mkdir()
    (app_dir / "server").mkdir()
    (app_dir / "server" / "test.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="test">
    <select id="selectTest">
        SELECT 1 FROM dual
    </select>
</mapper>
""", encoding="utf-8")

    target_file = tmp_path / "sql-check.md"

    # explain을 mock하여 psql 호출 없이 검증
    with patch("yunhee.tools.as_is.sql_checker.explain", return_value=None):
        res = check_sql(tmp_path / "src", target_file, db="testdb")
        assert res.ok is True
        assert res.data["passed_count"] == 1
        assert target_file.is_file()
        content = target_file.read_text(encoding="utf-8")
        assert "통과 1" in content


def test_sql_checker_connection_failure(tmp_path: Path):
    app_dir = tmp_path / "src" / "myApp"
    app_dir.mkdir(parents=True, exist_ok=True)
    (app_dir / "client").mkdir()
    (app_dir / "server").mkdir()
    (app_dir / "server" / "test.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="test">
    <select id="selectTest">SELECT 1</select>
</mapper>
""", encoding="utf-8")
    target_file = tmp_path / "sql-check.md"

    # psql 연결 실패를 모의(mock)
    with patch(
        "yunhee.tools.as_is.sql_checker.explain",
        return_value="psql: error: connection to server on socket failed: Connection refused",
    ):
        res = check_sql(tmp_path / "src", target_file, db="testdb")
        assert res.ok is False
        assert "접속 실패" in res.error


def test_sql_checker_parse_pg_url():
    from yunhee.tools.as_is.sql_checker import parse_pg_url

    url = "postgresql://myuser:mypass@127.0.0.1:5433/mydbname"
    env = parse_pg_url(url)
    assert env["PGHOST"] == "127.0.0.1"
    assert env["PGPORT"] == "5433"
    assert env["PGUSER"] == "myuser"
    assert env["PGPASSWORD"] == "mypass"
    assert env["PGDATABASE"] == "mydbname"


def test_clean_generated_safety_guard(tmp_path: Path):
    from yunhee.tools.as_is.dbml_indexer import clean_generated as dbml_clean
    from yunhee.tools.as_is.src_indexer import clean_generated as src_clean

    unsafe_dir = tmp_path / "important_docs"
    unsafe_dir.mkdir()
    (unsafe_dir / "important.md").write_text("# Do not delete", encoding="utf-8")

    # README가 없으므로 삭제 방지 발동
    ok1, err1 = src_clean(unsafe_dir)
    assert ok1 is False
    assert "안전 가드" in err1
    assert (unsafe_dir / "important.md").is_file()

    # README가 있지만 생성기 마커가 없으므로 삭제 방지 발동
    (unsafe_dir / "README.md").write_text("# Project Notes", encoding="utf-8")
    ok2, err2 = dbml_clean(unsafe_dir)
    assert ok2 is False
    assert "안전 가드" in err2
    assert (unsafe_dir / "important.md").is_file()


def test_find_as_is_dir(tmp_path: Path, monkeypatch):
    from yunhee.tools.as_is import find_as_is_dir

    repo_dir = tmp_path / "repo"
    docs_as_is = repo_dir / "docs" / "as-is"
    docs_as_is.mkdir(parents=True)
    sub_project = repo_dir / "OMS"
    sub_project.mkdir()

    # OMS/ 디렉터리에서 실행하는 상황 모의
    monkeypatch.setattr("yunhee.tools.as_is.WORK_DIR", sub_project)

    resolved_src = find_as_is_dir("src")
    assert resolved_src == docs_as_is / "src"



def test_select_output_names():
    from yunhee.tools.as_is.sql_checker import (
        extract_select_aliases_from_sql,
        select_output_names,
    )

    # AS 없는 컬럼, t.col, AS 없는 별칭, 함수명, 이름 없는 식
    sql = "SELECT audit_id, a.event_type, count(*) cnt, upper(x), 1 + 2, CASE WHEN a THEN 1 END AS flag FROM t a"
    assert select_output_names(sql) == ["audit_id", "event_type", "cnt", "upper", None, "flag"]
    # 서브쿼리 안의 별칭은 세지 않는다
    sql = "SELECT e.id, pw.pwd AS password FROM emp e LEFT JOIN (SELECT x AS pwd, y AS age_days FROM p) pw ON 1=1"
    assert extract_select_aliases_from_sql(sql) == {"id", "password"}
    # WITH RECURSIVE의 CTE 컬럼·별칭은 세지 않는다
    sql = (
        "WITH RECURSIVE m(id, depth, path) AS (SELECT id, 1 AS depth, ARRAY[id] AS path FROM menu "
        "UNION ALL SELECT c.id, m.depth + 1, m.path || c.id FROM menu c JOIN m ON 1=1) "
        "SELECT m.id AS menu_id, n.menu_nm FROM m JOIN menu n ON n.id = m.id ORDER BY path"
    )
    assert extract_select_aliases_from_sql(sql) == {"menuId", "menuNm"}
    # * 이 있으면 대조 불가
    assert extract_select_aliases_from_sql("SELECT t.*, 1 AS x FROM t") is None
    # 문자열 안의 콤마·FROM은 무시
    assert select_output_names("SELECT 'a, b FROM c' AS label, d FROM t") == ["label", "d"]


def test_find_record_fields_fqn(tmp_path: Path):
    from yunhee.tools.as_is.sql_checker import find_record_fields

    a = tmp_path / "kr" / "biz" / "company" / "dto"
    b = tmp_path / "kr" / "biz" / "sys" / "dto"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "CompanyRes.java").write_text("public record CompanyRes(Long companyId, String companyCode) {}")
    (b / "CompanyRes.java").write_text(
        "public record CompanyRes(@NotNull Long companyId, Map<String, Object> extra, String note) {}"
    )
    fields, warn = find_record_fields("kr.biz.company.dto.CompanyRes", [tmp_path])
    assert fields == {"companyId", "companyCode"} and warn is None
    fields, warn = find_record_fields("kr.biz.sys.dto.CompanyRes", [tmp_path])
    assert fields == {"companyId", "extra", "note"}
    # 짧은 이름이 여러 개면 경고하고 대조를 건너뛴다
    fields, warn = find_record_fields("CompanyRes", [tmp_path])
    assert fields is None and "2개" in warn


def test_parse_update_data_model_puts(tmp_path: Path):
    from yunhee.tools.as_is.src_indexer import java_literal, parse_update_data_model

    assert java_literal('"true"') == "'true'"
    assert java_literal("0l") == "0"
    assert java_literal("null") == "NULL"
    assert java_literal("companyId") is None
    assert java_literal("String.valueOf(companyId)") is None

    udm = tmp_path / "server" / "utils" / "db" / "UpdateDataModel.java"
    udm.parent.mkdir(parents=True)
    udm.write_text(
        """class UpdateDataModel {
    void run() {
        if ("sys01_company".equals(tableName)) {
            long seq = sqlSession.selectOne("getSeq", null);
            map.put("orgCd", "10000");
            sqlSession.insert("org01_code.insertOrg01Code", map);
            map.clear();
            map.put("companyId", companyId);
            map.put("useYn", "true");
            sqlSession.insert("ast02_detail.insertFromAst02", map);
        }
    }
}
"""
    )
    se = parse_update_data_model(tmp_path)["sys01_company"]
    first, second = se["items"]
    # namespace 없는 getSeq도 dbConfig.getSeq로 푼다
    assert first["seq"][2] == "dbConfig.getSeq"
    assert first["puts"] == [("orgCd", "'10000'", 5)]
    # map.clear() 이후 값만
    assert [(k, v) for k, v, _ in second["puts"]] == [("companyId", None), ("useYn", "'true'")]
