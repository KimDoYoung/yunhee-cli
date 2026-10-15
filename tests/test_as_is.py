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


def test_027_sql_drift_detection(tmp_path: Path):
    """027-4: SQL Drift 감지 및 TOBE 매퍼 영향 분석 검증."""
    from yunhee.tools.as_is.sql_drift import check_sql_drift, normalize_sql_for_drift

    # 1. normalize_sql_for_drift 검증
    raw_sql = """
    <!-- XML 주석 -->
    SELECT
        a, b, /* 인라인 블록 주석 */
        -- 줄 주석
        c
    FROM my_table
    WHERE 1=1
    """
    norm = normalize_sql_for_drift(raw_sql)
    assert norm == "select a, b, c from my_table where 1=1"

    # 2. check_sql_drift 구/신 AS-IS 및 TOBE 매퍼 검증
    old_root = tmp_path / "old_asis"
    new_root = tmp_path / "new_asis"
    tobe_root = tmp_path / "tobe_mapper"

    for r in (old_root, new_root, tobe_root):
        r.mkdir(parents=True)

    # 구 AS-IS: selectOne, selectTwo
    (old_root / "test01.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="test01">
    <select id="selectOne">
        SELECT col_a, col_b FROM my_tbl
    </select>
    <select id="selectTwo">
        SELECT col_c FROM my_tbl
    </select>
    <select id="selectRemoved">
        SELECT col_del FROM my_tbl
    </select>
</mapper>
""", encoding="utf-8")

    # 신 AS-IS: selectOne(변경), selectTwo(동일), selectThree(추가), selectRemoved(삭제)
    (new_root / "test01.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="test01">
    <select id="selectOne">
        SELECT col_a, col_b, col_d FROM my_tbl
    </select>
    <select id="selectTwo">
        SELECT col_c FROM my_tbl
    </select>
    <select id="selectThree">
        SELECT col_e FROM my_tbl
    </select>
</mapper>
""", encoding="utf-8")

    # TOBE 매퍼: test01.xml
    (tobe_root / "test01.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!-- AS-IS server/test/mapper/test01.xml selectOne(L10) · selectTwo(L20) -->
<mapper namespace="com.example.mapper.Test01Mapper">
    <!-- AS-IS test01.selectOne -->
    <select id="selectOne">
        SELECT col_a, col_b, col_d FROM my_tbl
    </select>
    <!-- AS-IS test01.selectTwo -->
    <select id="selectTwo">
        SELECT col_c FROM my_tbl
    </select>
</mapper>
""", encoding="utf-8")

    res = check_sql_drift(
        old_root=old_root,
        new_root=new_root,
        tobe_dir=tobe_root,
    )

    assert res.ok is True
    summary = res.data["summary"]
    assert summary["same"] == 1
    assert summary["changed"] == 1
    assert summary["added"] == 1
    assert summary["removed"] == 1
    assert summary["tobe_affected"] == 1

    changed = res.data["changed"]
    assert len(changed) == 1
    assert changed[0]["key"] == "test01.selectOne"
    assert "col_d" in changed[0]["diff"]

    tobe_affected = res.data["tobe_affected"]
    # Test01Mapper.selectOne 은 바뀜 상태여야 함
    s1_aff = next(t for t in tobe_affected if "selectOne" in t["tobe_key"])
    assert s1_aff["is_changed"] is True
    assert any("test01.selectOne (바뀜)" in s for s in s1_aff["as_is_refs"])

    # 마크다운 렌더링 확인
    md = res.data["summary_text"]
    assert "### SQL Drift 검증 결과" in md
    assert "동일: 1개, 바뀜: 1개, 신규: 1개, 삭제: 1개" in md
    assert "Test01Mapper.selectOne" in md


def test_028_sql_drift_noise_and_reflection(tmp_path: Path):
    """028-2, 028-3, 028-4: 머리 주석 경로 무시, 반영 표시 주석, 대소문자 무시, diff 토큰화 검증."""
    from yunhee.tools.as_is.sql_drift import (
        check_sql_drift,
        get_diff_summary,
        normalize_sql_for_drift,
    )

    # 1. 028-4 정규화 대소문자 검증: 문자열 리터럴/파라미터 밖은 무시, 안은 보존
    sql_upper = "SELECT col_a FROM my_tbl WHERE flag = 'Y' AND id = #{myId}"
    sql_lower = "select COL_A from MY_TBL where flag = 'Y' and id = #{myId}"
    assert normalize_sql_for_drift(sql_upper) == normalize_sql_for_drift(sql_lower)

    # 리터럴 안이 다르면 다름
    sql_lit_diff = "select col_a from my_tbl where flag = 'y' and id = #{myId}"
    assert normalize_sql_for_drift(sql_upper) != normalize_sql_for_drift(sql_lit_diff)

    # 파라미터 안이 다르면 다름
    sql_param_diff = "select col_a from my_tbl where flag = 'Y' and id = #{myid}"
    assert normalize_sql_for_drift(sql_upper) != normalize_sql_for_drift(sql_param_diff)

    # 2. 028-4 diff 토큰화: 'false', #{companyId}, != 등이 분리되지 않음
    diff_s = get_diff_summary("where use_yn = 'false' and id = #{companyId} and a != b",
                              "where use_yn = 'true' and id = #{newCompanyId} and a == b")
    assert "- 'false' / + 'true'" in diff_s
    assert "' false '" not in diff_s
    assert "- #{companyId} / + #{newCompanyId}" in diff_s
    assert "# {" not in diff_s
    assert "- != / + ==" in diff_s

    # 3. 028-2, 028-3: 머리 주석 경로 첫 단어(server) 무시 및 (IDMS-IC) 반영 표시 검증
    old_root = tmp_path / "Asset-ERP"
    new_root = tmp_path / "IDMS-IC"
    tobe_root = tmp_path / "tobe"
    for r in (old_root, new_root, tobe_root):
        r.mkdir(parents=True)

    # 구 AS-IS
    (old_root / "emp00.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="emp00">
    <select id="selectByText">
        SELECT old_col FROM emp00
    </select>
    <select id="selectById">
        SELECT id FROM emp00
    </select>
</mapper>
""", encoding="utf-8")

    # 신 AS-IS (둘 다 변경됨)
    (new_root / "emp00.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="emp00">
    <select id="selectByText">
        SELECT new_col FROM emp00
    </select>
    <select id="selectById">
        SELECT new_id FROM emp00
    </select>
</mapper>
""", encoding="utf-8")

    # TOBE 매퍼:
    # - 머리 주석에 server/emp/mapper/... 경로 포함 (server가 statement로 오인되면 안 됨)
    # - searchTransInfos는 (IDMS-IC) 반영 표시됨
    # - selectById는 반영 표시 없음
    (tobe_root / "EmpMapper.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!--
AS-IS server/emp/mapper/emp00.xml selectByText(L10) · selectById(L20)
+ common.emp00(Common.xml L100).
-->
<mapper namespace="com.example.mapper.EmpMapper">
    <!-- AS-IS selectByText L10 (IDMS-IC) -->
    <select id="searchTransInfos">
        SELECT new_col FROM emp00
    </select>
    <!-- AS-IS selectById L20 -->
    <select id="selectById">
        SELECT new_id FROM emp00
    </select>
</mapper>
""", encoding="utf-8")

    res = check_sql_drift(
        old_root=old_root,
        new_root=new_root,
        tobe_dir=tobe_root,
        only_tobe=True,
    )

    assert res.ok is True
    # 028-2: server (미존재) 가 없어야 함
    assert "server (미존재)" not in res.data["summary_text"]
    assert "emp00.server" not in res.data["summary_text"]

    # 028-3: (IDMS-IC)가 달린 searchTransInfos는 바뀐 영향 목록에서 제외되고 반영 표시됨에 존재
    md = res.data["summary_text"]
    assert "EmpMapper.selectById" in md
    assert "EmpMapper.searchTransInfos" not in md.split("#### 새 원본 반영 표시됨")[0]
    assert "#### 새 원본 반영 표시됨 (1개)" in md
    assert "- `EmpMapper.searchTransInfos`" in md
    assert res.data["summary"]["tobe_affected"] == 1
    assert res.data["summary"]["tobe_reflected"] == 1


def test_029_sql_drift_improvements(tmp_path):
    """029-1, 029-2, 029-3: 주석 경계 분리, XML 태그 OGNL 대소문자 보존 및 diff 원문 대소문자, diff 요약 길이 제한 검증."""
    from yunhee.tools.as_is.sql_drift import (
        check_sql_drift,
        get_diff_details,
        get_diff_summary,
        normalize_sql_for_drift,
    )

    # 1. 029-2: 정규화 및 diff 원문 대소문자 검증
    # (1) SQL 키워드 대소문자만 다름 -> 같음
    sql1 = "SELECT colA FROM tblA WHERE flag = 'Y'"
    sql2 = "select colA from tblA where flag = 'Y'"
    assert normalize_sql_for_drift(sql1) == normalize_sql_for_drift(sql2)

    # (2) test="isA == true" vs test="isa == true" -> 바뀜
    sql_tag1 = '<choose><when test="isA == true">SELECT 1</when></choose>'
    sql_tag2 = '<choose><when test="isa == true">SELECT 1</when></choose>'
    assert normalize_sql_for_drift(sql_tag1) != normalize_sql_for_drift(sql_tag2)

    # (3) diff 출력 토큰이 원문 대소문자 유지
    old_code = '<choose><when test="extrAddTitleYn == true">SELECT id FROM emp</when></choose>'
    new_code = '<choose><when test="extrAddTitleYn == true">SELECT id FROM emp AND COALESCE(title, \'false\') = \'true\'</when></choose>'
    diff_s = get_diff_summary(old_code, new_code)
    assert "AND COALESCE" in diff_s
    assert "and coalesce" not in diff_s
    assert "'false'" in diff_s
    assert "'true'" in diff_s

    # 2. 029-3: diff 요약 줄 길이 및 청크 제한 검증
    # (1) 긴 변경 덩어리가 30토큰/200자에서 잘리고 (+N토큰) 표기
    long_exprs = " ".join(f"f_cdnm('Kind{i}', col{i}) as val{i}," for i in range(50))
    old_long = "SELECT id FROM tbl"
    new_long = f"SELECT id, {long_exprs} FROM tbl"
    diff_long, diff_full = get_diff_details(old_long, new_long)
    assert len(diff_long) <= 405
    assert "(+" in diff_long and "토큰)" in diff_long
    assert len(diff_full) >= 1

    # (2) 변경 덩어리가 3개 초과인 경우 '외 N곳' 표기
    old_chunks = "SELECT a, b, c, d, e, f FROM tbl"
    new_chunks = "SELECT a1, b1, c1, d1, e1, f FROM tbl"
    diff_multi = get_diff_summary(old_chunks, new_chunks)
    assert "외 2곳" in diff_multi

    # 3. 029-1: 주석 경계 분리 및 설명 주석 AS-IS 무시 검증
    old_root = tmp_path / "Asset-ERP"
    new_root = tmp_path / "IDMS-IC"
    tobe_root = tmp_path / "tobe"
    for r in (old_root, new_root, tobe_root):
        r.mkdir(parents=True)

    (old_root / "sys01_company.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="sys01_company">
    <select id="selectByName">
        SELECT old_name FROM sys01_company
    </select>
    <select id="selectById">
        SELECT old_id FROM sys01_company
    </select>
</mapper>
""", encoding="utf-8")

    (new_root / "sys01_company.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<mapper namespace="sys01_company">
    <select id="selectByName">
        SELECT new_name FROM sys01_company
    </select>
    <select id="selectById">
        SELECT new_id FROM sys01_company
    </select>
</mapper>
""", encoding="utf-8")

    # TOBE 매퍼:
    # 1) <sql id="companyColumns"> 앞의 설명 주석에 'AS-IS SELECT의 ...' 포함 -> searchCompanies에 붙으면 안 됨
    # 2) searchCompanies 앞에 <!-- AS-IS selectByName: 회사 조회 --> -> sys01_company.selectByName으로 매칭
    # 3) searchCompanies 본문 내부에 <!-- AS-IS innerSelect L20 (IDMS-IC) --> -> 다음 statement에 전파되면 안 됨
    # 4) selectById 앞에 <!-- AS-IS selectById L30 --> -> 반영 표시 없이 정상 매칭
    (tobe_root / "SysCompanyMapper.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!--
AS-IS server/sys/mapper/sys01_company.xml selectByName(L10) · selectById(L20)
-->
<mapper namespace="com.example.mapper.SysCompanyMapper">
    <!-- 그리드 컬럼만. 이름 컬럼은 AS-IS SELECT의 f_cdnm 식 그대로, … -->
    <sql id="companyColumns">
        col1, col2
    </sql>

    <!-- AS-IS selectByName: 회사 조회 -->
    <select id="searchCompanies">
        SELECT col1 FROM sys01_company
        <!-- AS-IS innerSelect L20 (IDMS-IC) -->
    </select>

    <!-- AS-IS selectById L30 -->
    <select id="selectById">
        SELECT col1 FROM sys01_company WHERE id = 1
    </select>
</mapper>
""", encoding="utf-8")

    res = check_sql_drift(
        old_root=old_root,
        new_root=new_root,
        tobe_dir=tobe_root,
        only_tobe=True,
    )

    assert res.ok is True
    summary_text = res.data["summary_text"]

    # 029-1: SELECT (미존재) 없음
    assert "미존재" not in summary_text
    assert "sys01_company.SELECT" not in summary_text

    # 029-1: searchCompanies는 selectByName (바뀜)으로 잡힘
    assert "SysCompanyMapper.searchCompanies" in summary_text
    assert "sys01_company.selectByName (바뀜)" in summary_text

    # 029-1: innerSelect의 (IDMS-IC)가 selectById나 searchCompanies에 전파되지 않음
    assert res.data["summary"]["tobe_affected"] == 2
    assert res.data["summary"]["tobe_reflected"] == 0
    assert "SysCompanyMapper.selectById" in summary_text


