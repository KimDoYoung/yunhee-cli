from datetime import UTC, datetime
from pathlib import Path

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools import log_reader
from yunhee.tools.as_is import sql_checker

runner = CliRunner()


def test_sql_check_tobe_xml_well_formed(tmp_path: Path, monkeypatch):
    # Mock DB explain so it passes for valid queries
    monkeypatch.setattr(sql_checker, "explain", lambda sql, db, extra_env=None: None)
    monkeypatch.setattr(sql_checker, "get_db_env", lambda db: ("test_db", {}))

    mapper_dir = tmp_path / "mapper"
    mapper_dir.mkdir()

    # 1. 정상 매퍼
    good_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="kr.co.kfs.asseterp.GoodMapper">
  <select id="selectGood">
    SELECT 1 FROM good_table
  </select>
</mapper>
"""
    (mapper_dir / "GoodMapper.xml").write_text(good_xml, encoding="utf-8")

    # 2. 파싱 오류 매퍼 (raw <=)
    bad_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="kr.co.kfs.asseterp.CmpMailRoleMapper">
  <select id="selectBad">
    SELECT * FROM mail WHERE dt <= f_sysdate()
  </select>
</mapper>
"""
    (mapper_dir / "CmpMailRoleMapper.xml").write_text(bad_xml, encoding="utf-8")

    # 전체 검증 (summary=True)
    res = sql_checker.check_tobe_sql(mapper_dir, summary=True)
    assert not res.ok
    summary_text = res.data["summary"]
    assert "GoodMapper: ✅ 1 / ❌ 0" in summary_text
    assert "CmpMailRoleMapper: XML ❌ 1 / ✅ 0 / ❌ 0" in summary_text
    assert "❌ XML 오류: CmpMailRoleMapper.xml:5:33" in summary_text
    assert "힌트: 본문의 <, <=, <>, & 는 &lt;, &lt;=, &lt;&gt;, &amp; 또는 <![CDATA[ … ]]> 로 이스케이프 필요" in summary_text

    # CDATA 로 감싸면 정상 통과
    fixed_xml = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="kr.co.kfs.asseterp.CmpMailRoleMapper">
  <select id="selectBad">
    SELECT * FROM mail WHERE <![CDATA[ dt <= f_sysdate() ]]>
  </select>
</mapper>
"""
    (mapper_dir / "CmpMailRoleMapper.xml").write_text(fixed_xml, encoding="utf-8")
    res_fixed = sql_checker.check_tobe_sql(mapper_dir, summary=True)
    assert res_fixed.ok
    assert "CmpMailRoleMapper: ✅ 1 / ❌ 0" in res_fixed.data["summary"]


def test_parse_startup_failure_cause():
    log_snippet = """
2026-10-20 05:31:01.235 [SYSTEM] [-] [-] [-] [Catalina-utility-2] ERROR o.s.boot.SpringApplication - Application run failed
Caused by: org.springframework.beans.factory.BeanCreationException: Error creating bean with name 'sqlSessionFactory': Failed to instantiate: Failed to parse mapping resource: 'file [/usr/local/tomcat/webapps/AssetERP/WEB-INF/classes/mapper/CmpMailRoleMapper.xml]'
Caused by: org.apache.ibatis.builder.BuilderException: Error creating document instance.  Cause: org.xml.sax.SAXParseException; lineNumber: 28; columnNumber: 64; The content of elements must consist of well-formed character data or markup.
Caused by: org.xml.sax.SAXParseException: The content of elements must consist of well-formed character data or markup.
    """
    cause = log_reader.parse_startup_failure_cause(log_snippet)
    assert "CmpMailRoleMapper.xml" in cause
    assert "SAXParseException: The content of elements must consist of well-formed character data or markup." in cause


def test_check_deploy_startup_staleness_with_failure(tmp_path: Path, monkeypatch):
    log_file = tmp_path / "AssetERP-backend-info.log"
    log_content = """2026-10-20 04:00:00.000 [SYSTEM] INFO  k.c.k.a.AssetErpApplication - Started AssetErpApplication in 5.0 seconds
2026-10-20 05:31:01.235 [SYSTEM] ERROR o.s.boot.SpringApplication - Application run failed
Caused by: java.io.IOException: Failed to parse mapping resource: 'file [/app/mapper/CmpMailRoleMapper.xml]'
Caused by: org.xml.sax.SAXParseException: The content of elements must consist of well-formed character data or markup.
"""
    log_file.write_text(log_content, encoding="utf-8")

    fake_runs = [
        {
            "id": "20261020_053000_123456",
            "command": "./deploy.sh",
            "created_at": "2026-10-20T05:30:00+00:00",
            "duration_ms": 10000,  # 05:30:10 UTC (14:30:10 KST)
        }
    ]

    import yunhee.store.run_tracker
    monkeypatch.setattr(yunhee.store.run_tracker, "list_runs", lambda **kwargs: fake_runs)
    monkeypatch.setattr(log_reader.config, "LOG_DOCKER", "")
    monkeypatch.setattr(log_reader.config, "LOG_DIR", str(tmp_path))
    monkeypatch.setattr(log_reader.config, "LOG_APP", "AssetERP-backend")

    # 기동 성공 시각은 04:00 (배포 05:30:10 이전) -> 배포 후 05:31에 실패 발생
    deploy_dt_log = datetime(2026, 10, 20, 4, 0, 0, tzinfo=UTC)
    warn = log_reader.check_deploy_startup_staleness(deploy_dt_log, log_tz_is_utc=True)

    assert warn is not None
    assert "🚨 마지막 배포(14:30) 뒤 앱 기동 실패" in warn
    assert "CmpMailRoleMapper.xml" in warn
    assert "SAXParseException" in warn


def test_wait_for_deploy_health_success(tmp_path: Path, monkeypatch):
    log_file = tmp_path / "app-info.log"
    # 시작 시각 이후의 성공 기록
    log_file.write_text("2026-10-20 05:35:00.000 [SYSTEM] INFO  app - Started App in 6.0 seconds\n", encoding="utf-8")

    monkeypatch.setattr(log_reader.config, "LOG_DOCKER", "")
    dep_start_utc = datetime(2026, 10, 20, 5, 34, 50, tzinfo=UTC)

    status, msg = log_reader.wait_for_deploy_health(
        deploy_start_dt_utc=dep_start_utc,
        timeout=5,
        interval=0.1,
        file_path=log_file,
        log_tz="UTC",
    )
    assert status == "success"
    assert "앱 기동 확인" in msg


def test_wait_for_deploy_health_failure(tmp_path: Path, monkeypatch):
    log_file = tmp_path / "app-info.log"
    log_content = """2026-10-20 05:30:00.000 [SYSTEM] INFO  app - Started App in 5.0 seconds
2026-10-20 05:35:00.000 [SYSTEM] ERROR o.s.boot.SpringApplication - Application run failed
Caused by: java.io.IOException: Failed to parse mapping resource: 'file [/app/CmpMailRoleMapper.xml]'
Caused by: org.xml.sax.SAXParseException: The content of elements must consist of well-formed character data or markup.
"""
    log_file.write_text(log_content, encoding="utf-8")

    monkeypatch.setattr(log_reader.config, "LOG_DOCKER", "")
    dep_start_utc = datetime(2026, 10, 20, 5, 34, 50, tzinfo=UTC)

    status, msg = log_reader.wait_for_deploy_health(
        deploy_start_dt_utc=dep_start_utc,
        timeout=5,
        interval=0.1,
        file_path=log_file,
        log_tz="UTC",
    )
    assert status == "failure"
    assert "CmpMailRoleMapper.xml" in msg
    assert "SAXParseException" in msg


def test_run_deploy_health_integration(monkeypatch, tmp_path: Path):
    import uuid

    from yunhee.tools import runner

    # Mock execute_command to succeed
    monkeypatch.setattr(
        runner,
        "execute_command",
        lambda cmd, cwd=None, timeout=120: runner.ToolResult(
            ok=True,
            data={
                "command": cmd,
                "exit_code": 0,
                "duration_ms": 1000,
                "log_path": str(tmp_path / "run.log"),
                "stdout": "Deploying war...",
                "stderr": "",
                "run_id": f"test_run_{uuid.uuid4().hex[:8]}",
                "start_time": datetime.now(UTC).timestamp(),
            },
        ),
    )

    # 1. 헬스체크 실패 시 종료 코드가 1로 변경되고 요약에 실패 내용이 들어가는지 검증
    monkeypatch.setattr(
        log_reader,
        "wait_for_deploy_health",
        lambda **kwargs: ("failure", "CmpMailRoleMapper.xml: SAXParseException: invalid token"),
    )

    runner_cli = CliRunner()
    res = runner_cli.invoke(cli.app, ["run", "./deploy.sh", "--no-llm"])
    assert res.exit_code == 1
    assert "❌ 앱 기동 실패: CmpMailRoleMapper.xml: SAXParseException: invalid token (원 exit: 0)" in res.stdout

    # 2. 헬스체크 성공 시
    monkeypatch.setattr(
        log_reader,
        "wait_for_deploy_health",
        lambda **kwargs: ("success", "앱 기동 확인 (6초)"),
    )
    res_ok = runner_cli.invoke(cli.app, ["run", "./deploy.sh", "--no-llm"])
    assert res_ok.exit_code == 0
    assert "✅ 앱 기동 확인 (6초)" in res_ok.stdout

    # 3. --no-health 지정 시 헬스체크 호출 안 함
    called = []
    monkeypatch.setattr(
        log_reader,
        "wait_for_deploy_health",
        lambda **kwargs: called.append(True) or ("success", "ok"),
    )
    res_no_health = runner_cli.invoke(cli.app, ["run", "./deploy.sh", "--no-health", "--no-llm"])
    assert res_no_health.exit_code == 0
    assert len(called) == 0
