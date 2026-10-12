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
    assert len(err_recs) == 4
    # 마지막 레코드에 continuation lines 붙어있는지 확인
    last = err_recs[-1]
    assert last.level == "ERROR"
    assert len(last.extra_lines) == 5
    assert any("Caused by: java.lang.NullPointerException" in line for line in last.extra_lines)


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
