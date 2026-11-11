"""수정사항 054 테스트: drift-* 명령군 및 인덱스 누락 보완 검증."""

import json
from pathlib import Path

from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.as_is.drift_ops import (
    append_to_ledger,
    classify_file_kind,
    compare_dbml_snapshots,
    parse_diff_hunks,
    parse_java_methods_positions,
    parse_xml_statements_positions,
    resolve_ledger_path,
    update_drift_done,
)
from yunhee.tools.as_is.src_indexer import parse_client, parse_server

runner = CliRunner()


def test_classify_file_kind():
    assert classify_file_kind("db/migrations/V1__init.sql") == "DB"
    assert classify_file_kind("server/sys/mapper/sys01_company.xml") == "SQL"
    assert classify_file_kind("server/sys/Sys01_Company.java") == "LOGIC"
    assert classify_file_kind("client/vi/sys/model/Sys01_CompanyModel.java") == "MODEL"
    assert classify_file_kind("client/vi/sys/Sys01_Tab_Company.java") == "UI"
    assert classify_file_kind("docs/README.md") == "ETC"


def test_parse_xml_statements_positions():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="sys01_company">
    <select id="selectById" resultType="map">
        SELECT * FROM sys01_company WHERE company_id = #{companyId}
    </select>

    <insert id="insert">
        INSERT INTO sys01_company (company_id) VALUES (#{companyId})
    </insert>
</mapper>
"""
    stmts = parse_xml_statements_positions(xml, "sys01_company")
    assert len(stmts) == 2
    assert stmts[0]["id"] == "selectById"
    assert stmts[0]["key"] == "sys01_company.selectById"
    assert stmts[0]["kind"] == "select"
    assert stmts[0]["start_line"] == 4
    assert stmts[1]["id"] == "insert"
    assert stmts[1]["key"] == "sys01_company.insert"


def test_parse_java_methods_positions():
    java = """package myApp.server.sys;

public class Sys01_Company {
    private String mapperName = "sys01_company";

    public void selectById(ServiceRequest req, ServiceResult res) {
        // body
    }

    public void update(
        ServiceRequest req,
        ServiceResult res
    ) {
        // multi-line args
    }
}
"""
    methods = parse_java_methods_positions(java, "Sys01_Company")
    assert len(methods) == 2
    assert methods[0]["name"] == "selectById"
    assert methods[0]["start_line"] == 6
    assert methods[1]["name"] == "update"


def test_parse_diff_hunks():
    diff_text = """diff --git a/sys01_company.xml b/sys01_company.xml
index abc..def 100644
--- a/sys01_company.xml
+++ b/sys01_company.xml
@@ -10,3 +10,4 @@
 line1
+line2
 line3
"""
    files = parse_diff_hunks(diff_text)
    assert len(files) == 1
    assert files[0]["new_path"] == "sys01_company.xml"
    assert len(files[0]["hunks"]) == 1
    assert files[0]["hunks"][0]["new_start"] == 10


def test_indexer_variable_service_and_mapper_call(tmp_path: Path):
    # §7 1: new ServiceRequest("ics.Ics32_RelateAppr.selectApprList")
    # §7 2: serviceName = "dcr.Dcr00_DocList.selectNoAuthByText"
    client_code = """package myApp.client.vi.test;
public class TestClient {
    public void test1() {
        ServiceRequest req = new ServiceRequest("ics.Ics32_RelateAppr.selectApprList");
    }
    public void test2() {
        String serviceName = "dcr.Dcr00_DocList.selectNoAuthByText";
        service.retrieve(serviceName, param);
    }
}
"""
    app_dir = tmp_path / "app"
    c_dir = app_dir / "client" / "vi" / "test"
    c_dir.mkdir(parents=True)
    c_file = c_dir / "TestClient.java"
    c_file.write_text(client_code, encoding="utf-8")

    # server/dcr 폴더 생성 (server_domains에 dcr, ics 포함되도록)
    (app_dir / "server" / "dcr").mkdir(parents=True)
    (app_dir / "server" / "ics").mkdir(parents=True)

    client_res_map = parse_client(app_dir)
    assert "TestClient" in client_res_map
    client_res = client_res_map["TestClient"][0]
    service_names = [s[0] for s in client_res.services]
    assert "ics.Ics32_RelateAppr.selectApprList" in service_names
    assert "dcr.Dcr00_DocList.selectNoAuthByText" in service_names

    # §7 3: sqlSession.selectList(mapperName + ".selectApprList", ...)
    server_code = """package myApp.server.test;
public class TestServer {
    private String mapperName = "test_mapper";
    public void doSomething() {
        sqlSession.selectList(mapperName + ".selectApprList", param);
    }
}
"""
    s_dir = app_dir / "server" / "test"
    s_dir.mkdir(parents=True)
    s_file = s_dir / "TestServer.java"
    s_file.write_text(server_code, encoding="utf-8")

    server_res_map = parse_server(app_dir)
    assert "test.TestServer" in server_res_map
    server_res = server_res_map["test.TestServer"]
    found_sqls = []
    for m in server_res.methods.values():
        found_sqls.extend(m.sql_ids)
    assert "test_mapper.selectApprList" in found_sqls


def test_drift_done_and_ledger(tmp_path: Path):
    wd = tmp_path / "project"
    wd.mkdir(parents=True)
    docs_dir = wd / "docs"
    docs_dir.mkdir(parents=True)
    chg_dir = docs_dir / "3-변경반영"
    chg_dir.mkdir(parents=True)

    # baseline.json
    baseline_path = docs_dir / "baseline.json"
    baseline_path.write_text(
        json.dumps({
            "Sys01_Tab_Company": {
                "commit": "abc1234",
                "files": {
                    "server/sys/Sys01_Company.java": "blob111",
                },
            }
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 변경반영-대장.md
    ledger_file = chg_dir / "변경반영-대장.md"
    ledger_content = """# 변경반영 대장

| 키 | 발견일 | AS-IS 커밋 | 종류 | 단위 | 변경 요약 | 영향 화면 | TOBE 대응 | 상태 | 처리일 | 비고 |
|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|
| CH-0001 | 2026-11-11 | `abc1234` 11-11 테스트 | LOGIC | `server/sys/Sys01_Company.java` · `selectById` | +5 −0줄 | #1001 |  | 대기 |  |  |
"""
    ledger_file.write_text(ledger_content, encoding="utf-8")

    # 1. resolve_ledger_path
    resolved = resolve_ledger_path(wd)
    assert resolved == ledger_file

    # 2. update_drift_done CH-0001
    code, msg = update_drift_done(
        keys=["CH-0001"],
        status="반영",
        note="TOBE 커밋 12345",
        work_dir=wd,
    )
    assert code == 0
    assert "CH-0001" in msg

    # 대장 확인
    new_ledger_text = ledger_file.read_text(encoding="utf-8")
    assert "| CH-0001 | 2026-11-11 | `abc1234` 11-11 테스트 | LOGIC | `server/sys/Sys01_Company.java` · `selectById` | +5 −0줄 | #1001 |  | 반영 |" in new_ledger_text
    assert "TOBE 커밋 12345" in new_ledger_text

    # baseline 확인
    b_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert "__units__" in b_data
    assert "server/sys/Sys01_Company.java · selectById" in b_data["__units__"]
    assert b_data["__units__"]["server/sys/Sys01_Company.java · selectById"]["status"] == "반영"

    # 3. append_to_ledger
    sample_units = [{
        "kind": "SQL",
        "unit": "`server/sys/mapper/sys01_company.xml` · `insert`",
        "raw_unit": "sys01_company.insert",
        "file": "server/sys/mapper/sys01_company.xml",
        "change": "+10 −0줄",
        "added": 10,
        "removed": 0,
        "status": "새로 생김",
        "screens": ["#1001", "#1002"],
        "tobe": "SysCompanyMapper#insert",
        "commit": "def5678",
        "lc": {"hash": "def5678", "date": "11-11", "subject": "신규추가"},
    }]
    code_app, msg_app = append_to_ledger(ledger_file, sample_units, dry_run=False)
    assert code_app == 0
    assert "신규 추가 1건" in msg_app

    ledger_after_app = ledger_file.read_text(encoding="utf-8")
    assert "CH-0002" in ledger_after_app
    assert "sys01_company.xml" in ledger_after_app


def test_compare_dbml_snapshots(tmp_path: Path):
    from_file = tmp_path / "prev-dbml.md"
    to_file = tmp_path / "curr-dbml.md"

    from_file.write_text("""# DBML
## DBML
```dbml
Table "public"."sys01_company" {
  "company_id" "int8" [not null]
  "company_name" "varchar(100)"
}
```
""", encoding="utf-8")

    to_file.write_text("""# DBML
## DBML
```dbml
Table "public"."sys01_company" {
  "company_id" "int8" [not null]
  "company_name" "varchar(200)"
  "use_yn" "varchar(1)" [default: 'Y']
}
Table "public"."sys02_dept" {
  "dept_id" "int8" [not null]
}
```
""", encoding="utf-8")

    code, out = compare_dbml_snapshots(from_file, to_file)
    assert code == 0
    assert "신규 테이블 1개" in out
    assert "+ sys02_dept" in out
    assert "sys01_company" in out
    assert "+ 컬럼 추가: use_yn" in out


def test_cli_drift_commands_registered():
    result = runner.invoke(app, ["drift-unit", "--help"])
    assert result.exit_code == 0
    assert "SQL ID·메서드" in result.output

    result_done = runner.invoke(app, ["drift-done", "--help"])
    assert result_done.exit_code == 0

    result_log = runner.invoke(app, ["drift-log", "--help"])
    assert result_log.exit_code == 0
