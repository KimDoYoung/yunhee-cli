import json
from pathlib import Path

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools import api_client, comparator
from yunhee.tools.as_is import mapper_runner, sql_checker


def test_fix039_auto_prefix():
    # 404 No static resource should auto-prefix
    summary = api_client.summarize_response(
        404,
        "No static resource dcr/doc-lists/apprs.",
        100,
        path="/api/v1/dcr/doc-lists/apprs",
        notice="ℹ 경로를 /api/v1/dcr/doc-lists/apprs 로 보정",
    )
    assert "HTTP 404" in summary
    assert "ℹ 경로를 /api/v1/dcr/doc-lists/apprs 로 보정" in summary


def test_fix039_user_info_header():
    summary = api_client.summarize_response(
        200,
        json.dumps({"success": True, "code": "OK", "data": []}),
        50,
        user_info={"user_id": 202204180108329, "org_id": 202604029585842, "company_id": 28000},
    )
    assert "user=202204180108329 org=202604029585842 company=28000" in summary
    assert "HTTP 200" in summary


def test_fix039_paging_keys(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(comparator.config, "WORK_DIR", tmp_path)
    # Test field and total extraction on paging response
    raw_data = {
        "rows": [{"personName": "홍길동", "regDateString": "2026-10-20", "title": "문서1"}],
        "total": 153,
    }
    # api_fields extraction
    assert raw_data["total"] == 153
    assert len(raw_data["rows"]) == 1
    assert set(raw_data["rows"][0].keys()) == {"personName", "regDateString", "title"}


def test_fix039_sql_check_tobe_filters(tmp_path: Path):
    mapper_dir = tmp_path / "mapper"
    mapper_dir.mkdir()
    xml1 = mapper_dir / "AprDownloadHistoryMapper.xml"
    xml1.write_text(
        """<mapper namespace="kr.co.kfs.asseterp.biz.apr.mapper.AprDownloadHistoryMapper">
    <select id="selectByTextPaging" resultType="int">SELECT 1</select>
</mapper>""",
        encoding="utf-8",
    )
    xml2 = mapper_dir / "AuditLogMapper.xml"
    xml2.write_text(
        """<mapper namespace="kr.co.kfs.asseterp.biz.sys.mapper.AuditLogMapper">
    <select id="selectAuditLogs" resultType="int">SELECT 1 FROM invalid_table_xyz</select>
</mapper>""",
        encoding="utf-8",
    )

    # When filtered with --only 'AprDownload*', xml2 should be ignored
    res = sql_checker.check_tobe_sql(mapper_dir, only=["AprDownload*"])
    assert res.ok is True
    assert "AprDownloadHistoryMapper" in res.data["summary"]
    assert "AuditLogMapper" not in res.data["summary"]

    # When --summary is passed
    res_summary = sql_checker.check_tobe_sql(mapper_dir, only=["AprDownload*"], summary=True)
    assert res_summary.ok is True
    assert "AprDownloadHistoryMapper: ✅ 1 / ❌ 0" in res_summary.data["summary"]


def test_fix039_mapper_runner_guards(tmp_path: Path):
    mapper_file = tmp_path / "TestMapper.xml"
    mapper_file.write_text(
        """<mapper namespace="kr.co.kfs.TestMapper">
    <insert id="insertRecord">
        INSERT INTO test_tbl (id) VALUES (#{id})
    </insert>
</mapper>""",
        encoding="utf-8",
    )

    # Without --rollback, write statement must be rejected
    res = mapper_runner.run_mapper_statement(f"{mapper_file}#insertRecord")
    assert res.ok is False
    assert "쓰기 statement(insert/update/delete)는 --rollback 옵션이 필요합니다" in res.error


def test_fix039_method_candidates_cli():
    runner = CliRunner()
    res = runner.invoke(cli.app, ["analysis", "method", "Fbx01_Grid_DocList.init"])
    assert res.exit_code == 2
    assert "후보:" in res.output or "후보" in res.output
