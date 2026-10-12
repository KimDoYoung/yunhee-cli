from pathlib import Path

import pytest
import typer

from yunhee import config
from yunhee.tools import log_reader

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "log"
INFO_LOG = FIXTURES_DIR / "AssetERP-backend-info.log"
ERROR_LOG = FIXTURES_DIR / "AssetERP-backend-error.log"
MAPPER_DIR = FIXTURES_DIR / "mapper"


def test_parse_log_records():
    # 1. 줄 파서: 13줄 -> 레코드 13
    info_text = INFO_LOG.read_text(encoding="utf-8")
    recs = log_reader.parse_log_records(info_text)
    assert len(recs) == 13
    assert recs[0].trace == "95694936e2a3b376"

    # 여러 줄 스택
    err_text = ERROR_LOG.read_text(encoding="utf-8")
    err_recs = log_reader.parse_log_records(err_text)
    assert len(err_recs) == 5
    # 4번째 레코드 (NPE)
    npe_rec = err_recs[3]
    assert npe_rec.level == "ERROR"
    assert len(npe_rec.extra_lines) == 5
    assert any("Caused by: java.lang.NullPointerException" in line for line in npe_rec.extra_lines)
    # 5번째 레코드 (빈 메시지 WARN)
    last = err_recs[-1]
    assert last.level == "WARN"
    assert "Using generated security password" in last.extra_lines[0]


def test_trace_summary_and_masking(monkeypatch):
    monkeypatch.setattr(config, "WORK_DIR", FIXTURES_DIR)
    log_reader._MAPPER_CACHE = None

    # 마스킹 켜짐
    summary = log_reader.get_trace_summary(
        trace_id="95694936e2a3b376",
        file_path=str(INFO_LOG),
        mask=True,
    )
    assert "file:" in summary
    assert "PUT /api/v1/emp/others → 200 (117ms)" in summary
    assert "SQL 4:" in summary
    assert "Updates 0" in summary
    assert "******-*******" in summary
    assert "900101-1234567" not in summary
    assert "15:33:44 KST" in summary

    # 마스킹 꺼짐 (--no-mask)
    summary_raw = log_reader.get_trace_summary(
        trace_id="95694936e2a3b376",
        file_path=str(INFO_LOG),
        mask=False,
    )
    assert "900101-1234567" in summary_raw


def test_mapper_recovery(monkeypatch, tmp_path):
    # 가짜 매퍼 XML 경로 생성
    mapper_xml_dir = tmp_path / "src" / "main" / "resources" / "mapper"
    mapper_xml_dir.mkdir(parents=True)
    xml_content = (MAPPER_DIR / "EmpOthersMapper.xml").read_text(encoding="utf-8")
    (mapper_xml_dir / "EmpOthersMapper.xml").write_text(xml_content, encoding="utf-8")

    monkeypatch.setattr(config, "WORK_DIR", tmp_path)
    log_reader._MAPPER_CACHE = None

    recovered = log_reader.recover_mapper_name("k.c.k.a.b.e.m.E.selectOthers")
    assert recovered == "EmpOthersMapper.selectOthers"


def test_errors_grouping():
    summary = log_reader.get_errors_summary(
        file_path=str(ERROR_LOG),
        since="100000h",
    )
    # 같은 메시지 3줄 -> × 3
    assert "× 3" in summary
    assert "StompAuthChannelInterceptor" in summary
    assert "NullPointerException" in summary


def test_time_range_filter():
    # 2026-10-08 15:11 KST -> 06:11 UTC, 15:15 KST -> 06:15 UTC
    summary = log_reader.get_errors_summary(
        file_path=str(ERROR_LOG),
        log_tz="UTC",
        from_time="2026-10-08 15:11",
        to_time="2026-10-08 15:15",
    )
    assert "× 2" in summary
    assert "× 3" not in summary
    assert "NullPointerException" not in summary
    assert "범위" in summary


def test_mutual_exclusive_start_options():
    with pytest.raises(typer.Exit) as exc_info:
        log_reader.resolve_time_range(
            since="1h",
            from_time="15:00",
        )
    assert exc_info.value.exit_code == 2


def test_022_empty_first_line_and_password_masking(tmp_path):
    log_file = tmp_path / "app-error.log"
    log_file.write_text(
        "2026-10-12 00:22:18.509 [SYSTEM] [-] [-] [-] [main] WARN  o.s.b.a.s.s.UserDetailsServiceAutoConfiguration - \n"
        "Using generated security password: 70ea24fd-b57f-4f64-9be1-558e652a970d\n",
        encoding="utf-8",
    )

    # 1. get_errors_summary - no IndexError and password masked
    res = log_reader.get_errors_summary(
        file_path=str(log_file),
        log_tz="UTC",
        from_time="2026-10-12 09:00",
        mask=True,
    )
    assert "UserDetailsServiceAutoConfiguration - Using generated security password: ****" in res
    assert "70ea24fd" not in res

    # 2. get_tail_summary - no IndexError
    tail_res = log_reader.get_tail_summary(
        file_path=str(log_file),
        log_tz="UTC",
        from_time="2026-10-12 09:00",
        mask=True,
    )
    assert "WARN 00:22:18 o.s.b.a.s.s.UserDetailsServiceAutoConfiguration - Using generated security password: ****" in tail_res


def test_022_deduplication(tmp_path):
    log_file = tmp_path / "combined.log"
    # 동일한 레코드 2회 반복 (logback 이중 기록 모의)
    line = "2026-10-08 06:35:20.105 [c1e9fbe500000001] [admin] [kfstest:admin] [172.18.0.1] [http-nio-8080-exec-10] WARN  k.c.k.a.c.e.GlobalExceptionHandler - 요청 처리 실패: status=405\n"
    log_file.write_text(line + line, encoding="utf-8")

    res = log_reader.get_trace_summary(
        trace_id="c1e9fbe500000001",
        file_path=str(log_file),
    )
    assert "WARN/ERROR 1:" in res
    assert "WARN/ERROR 2:" not in res


def test_022_tail_level_grep_and_warning_indicator(tmp_path):
    log_file = tmp_path / "tail_test.log"
    content = (
        # 405 요청 (WARN 포함, SQL 1)
        "2026-10-08 06:35:20.100 [c1e9fbe500000001] [admin] [kfstest:admin] [172.18.0.1] [http-nio-8080-exec-10] DEBUG k.c.k.a.b.e.m.E.selectOthers - ==>  Preparing: SELECT 1\n"
        "2026-10-08 06:35:20.105 [c1e9fbe500000001] [admin] [kfstest:admin] [172.18.0.1] [http-nio-8080-exec-10] WARN  k.c.k.a.c.e.GlobalExceptionHandler - 요청 처리 실패: status=405\n"
        "2026-10-08 06:35:20.106 [c1e9fbe500000001] [admin] [kfstest:admin] [172.18.0.1] [http-nio-8080-exec-10] INFO  kr.co.kfs.asseterp.access - GET /AssetERP_1/api/v1/emp/educations 405 6ms\n"
        # 200 요청 (careers, SQL 2)
        "2026-10-08 06:34:27.100 [afc00e8900000001] [admin] [kfstest:admin] [172.18.0.1] [http-nio-8080-exec-11] DEBUG k.c.k.a.b.e.m.E.selectCareers - ==>  Preparing: SELECT * FROM emp07_career WHERE person_id = ?\n"
        "2026-10-08 06:34:27.103 [afc00e8900000001] [admin] [kfstest:admin] [172.18.0.1] [http-nio-8080-exec-11] DEBUG k.c.k.a.b.e.m.E.selectCareers - ==>  Preparing: SELECT * FROM emp07_career WHERE person_id = ?\n"
        "2026-10-08 06:34:27.111 [afc00e8900000001] [admin] [kfstest:admin] [172.18.0.1] [http-nio-8080-exec-11] INFO  kr.co.kfs.asseterp.access - GET /AssetERP_1/api/v1/emp/persons/1/careers 200 11ms\n"
    )
    log_file.write_text(content, encoding="utf-8")

    # 1. tail 경고 표시 (022-5): 요청 줄에 ⚠WARN과 status=405
    tail_all = log_reader.get_tail_summary(file_path=str(log_file))
    assert "⚠WARN" in tail_all
    assert "status=405" in tail_all

    # 2. level 필터 (022-3): --level WARN은 405만, --level ERROR는 없음
    tail_warn = log_reader.get_tail_summary(file_path=str(log_file), level="WARN")
    assert "/api/v1/emp/educations" in tail_warn
    assert "/api/v1/emp/persons/1/careers" not in tail_warn

    tail_err = log_reader.get_tail_summary(file_path=str(log_file), level="ERROR")
    assert "(기록 없음)" in tail_err

    # 3. grep 필터 (022-4): --grep careers는 trace 전체 보존하여 SQL 2 유지
    tail_grep = log_reader.get_tail_summary(file_path=str(log_file), grep_pattern="careers")
    assert "/api/v1/emp/persons/1/careers" in tail_grep
    assert "SQL 2" in tail_grep
    assert "요청 1, SQL 2" in tail_grep


def test_022_trace_id_validation():
    with pytest.raises(typer.Exit) as exc_info:
        log_reader.get_trace_summary(trace_id="xyz")
    assert exc_info.value.exit_code == 2

