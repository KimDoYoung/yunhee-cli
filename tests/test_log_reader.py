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
    assert "WARN" in tail_res
    assert "00:22:18 o.s.b.a.s.s.UserDetailsServiceAutoConfiguration - Using generated security password: ****" in tail_res


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


def test_023_archived_range_local():
    res = log_reader.get_req_summary(
        method="GET",
        path_pattern="companies",
        source="local",
        log_dir=str(FIXTURES_DIR),
        archived=True,
        from_time="2026-10-08 16:30",
        to_time="2026-10-08 16:45",
        log_tz="UTC",
    )
    assert "abd1f6520f3647c6" in res
    assert "10-08 07:39:15" in res


def test_023_archived_range_without_archived_notice():
    res = log_reader.get_req_summary(
        method="GET",
        path_pattern="companies",
        source="local",
        log_dir=str(FIXTURES_DIR),
        archived=False,
        from_time="2026-10-08 15:00",
        to_time="2026-10-08 15:20",
        log_tz="UTC",
    )
    assert "(일치하는 요청 없음)" in res
    assert "그 전은 --archived" in res
    assert "오늘 파일은 06:33부터" in res


def test_023_trace_archived_found():
    res = log_reader.get_trace_summary(
        trace_id="abd1f6520f3647c6",
        source="local",
        log_dir=str(FIXTURES_DIR),
        archived=True,
        log_tz="UTC",
    )
    assert "원문: yunhee log trace abd1f6520f3647c6 --raw --archived" in res
    assert "2026-10-08 07:39:15 UTC (10-08 16:39:15 KST)" in res


def test_023_trace_archived_not_found(capsys):
    with pytest.raises(typer.Exit) as exc_info:
        log_reader.get_trace_summary(
            trace_id="deadbeef00000000",
            source="local",
            log_dir=str(FIXTURES_DIR),
            archived=True,
            log_tz="UTC",
        )
    assert exc_info.value.exit_code == 1
    err = capsys.readouterr().err
    assert "archived gz" in err
    assert "지난 날은 --archived" not in err


def test_023_archived_without_range_notice():
    res = log_reader.get_req_summary(
        method="GET",
        path_pattern="companies",
        source="local",
        log_dir=str(FIXTURES_DIR),
        archived=True,
    )
    assert "(--archived: 범위가 오늘이라 지난 파일을 읽지 않음)" in res


def test_024_save_run_and_find_run_time_fallback(monkeypatch, tmp_path):
    import sqlite3
    from datetime import UTC, datetime

    from yunhee.store import run_tracker

    db_path = tmp_path / "test_runs.db"
    monkeypatch.setattr(run_tracker, "get_connection", lambda: sqlite3.connect(str(db_path)))
    run_tracker.init_db()

    # 1. save_run이 넘긴 created_at을 그대로 저장하는지 검증
    run_tracker.save_run(
        run_id="20261012_042207_994e94",
        project="test_proj",
        command="bash -c 'sleep 41'",
        exit_code=0,
        duration_ms=41000,
        log_path="/tmp/test.log",
        created_at="2026-10-12T04:22:48+00:00",  # 옛 기록: 끝 시각이 들어간 경우
    )

    saved = run_tracker.get_run("20261012_042207_994e94")
    assert saved is not None
    assert saved["created_at"] == "2026-10-12T04:22:48+00:00"

    # 2. find_run_time이 created_at이 끝 시각인 옛 기록에서 run ID 시각(04:22:07)을 시작 시각으로 쓰는지
    info = log_reader.find_run_time("20261012_042207_994e94")
    assert info.run_id == "20261012_042207_994e94"
    assert info.cmd == "bash -c 'sleep 41'"
    assert info.start_dt == datetime(2026, 10, 12, 4, 22, 7, tzinfo=UTC)
    assert info.end_dt == datetime(2026, 10, 12, 4, 22, 48, tzinfo=UTC)

    # 3. resolve_time_range 머리 줄 및 시간 범위 검증
    start_log, end_log, header_tag = log_reader.resolve_time_range(
        since_run="20261012_042207_994e94",
        log_tz="UTC",
    )
    assert "13:22:07~13:22:48 KST 이후" in header_tag
    assert "· run 20261012_042207_994e94" in header_tag
    assert start_log == datetime(2026, 10, 12, 4, 22, 7)  # noqa: DTZ001
    assert end_log is None  # --to가 없으므로 끝은 열려 있음

    # 4. 새로 저장된 기록 (created_at이 시작 시각)
    run_tracker.save_run(
        run_id="20261012_050000_aabbcc",
        project="test_proj",
        command="echo new",
        exit_code=0,
        duration_ms=3000,
        log_path="/tmp/new.log",
        created_at="2026-10-12T05:00:00+00:00",
    )
    info_new = log_reader.find_run_time("20261012_050000_aabbcc")
    assert info_new.start_dt == datetime(2026, 10, 12, 5, 0, 0, tzinfo=UTC)
    assert info_new.end_dt == datetime(2026, 10, 12, 5, 0, 3, tzinfo=UTC)


def test_026_sql_parameter_names(tmp_path, monkeypatch):
    """026-2: SQL 파라미터 이름 매퍼 연동 및 fallback 검증."""
    mapper_dir = tmp_path / "backend" / "src" / "main" / "resources" / "mapper"
    mapper_dir.mkdir(parents=True, exist_ok=True)

    # 1. SysCodeMapper.xml
    (mapper_dir / "SysCodeMapper.xml").write_text("""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="kr.co.kfs.asseterp.biz.sys.mapper.SysCodeMapper">
    <sql id="companyCols">
        sys01_company_id
    </sql>

    <!-- 1) 정상: 순서대로 이름 추출 (include 포함) -->
    <insert id="copyCodes">
        INSERT INTO sys09_code (company_id, source_company_id, code_kind_id)
        SELECT #{newCompanyId}, <include refid="companyCols"/>, #{sourceCompanyId}
        FROM sys09_code
        WHERE code_kind_id = #{codeKindId}
    </insert>

    <!-- 2) foreach 포함: 개수가 동적이므로 파라미터 이름 비활성화 -->
    <insert id="batchInsert">
        INSERT INTO sys09_code (code_id)
        VALUES
        <foreach collection="list" item="item" separator=",">
            (#{item.codeId})
        </foreach>
    </insert>

    <!-- 3) if 조건문 포함: 개수 불일치 시 fallback -->
    <select id="searchCodes" resultType="map">
        SELECT * FROM sys09_code
        WHERE sys01_company_id = #{companyId}
        <if test="codeName != null">
            AND code_name = #{codeName}
        </if>
        AND code_kind_id = #{codeKindId}
    </select>
</mapper>
""", encoding="utf-8")

    monkeypatch.setattr(config, "WORK_DIR", tmp_path)
    log_reader._MAPPER_CACHE = None
    log_reader._MAPPER_PARAM_CACHE = None

    log_file = tmp_path / "app-info.log"
    content = (
        # 1. copyCodes 정상 매칭 (3개)
        "2026-10-13 01:00:00.000 [1111111100000001] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.s.m.S.copyCodes - ==>  Preparing: INSERT INTO sys09_code ...\n"
        "2026-10-13 01:00:00.001 [1111111100000001] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.s.m.S.copyCodes - ==> Parameters: 28000(Long), 0(Long), 202407241733135(String)\n"
        "2026-10-13 01:00:00.002 [1111111100000001] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.s.m.S.copyCodes - <==    Updates: 0\n"
        # 2. batchInsert (<foreach> 포함 -> 파라미터 이름 없이 그대로 값만)
        "2026-10-13 01:00:00.010 [2222222200000002] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.s.m.S.batchInsert - ==>  Preparing: INSERT INTO sys09_code ...\n"
        "2026-10-13 01:00:00.011 [2222222200000002] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.s.m.S.batchInsert - ==> Parameters: 1(Long), 2(Long)\n"
        "2026-10-13 01:00:00.012 [2222222200000002] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.s.m.S.batchInsert - <==    Updates: 2\n"
        # 3. searchCodes (매퍼에는 3개 있지만 실행 시 if가 빠져서 2개만 바인딩된 경우 -> 개수 불일치 fallback)
        "2026-10-13 01:00:00.020 [3333333300000003] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.s.m.S.searchCodes - ==>  Preparing: SELECT * FROM sys09_code ...\n"
        "2026-10-13 01:00:00.021 [3333333300000003] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.s.m.S.searchCodes - ==> Parameters: 28000(Long), KIND01(String)\n"
        "2026-10-13 01:00:00.022 [3333333300000003] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.s.m.S.searchCodes - <==      Total: 5\n"
        # 4. UnknownMapper (매퍼 XML 없음 -> 그대로)
        "2026-10-13 01:00:00.030 [4444444400000004] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.x.m.UnknownMapper.doAction - ==>  Preparing: SELECT 1\n"
        "2026-10-13 01:00:00.031 [4444444400000004] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.x.m.UnknownMapper.doAction - ==> Parameters: 999(Long)\n"
        "2026-10-13 01:00:00.032 [4444444400000004] [-] [-] [-] [exec-1] DEBUG k.c.k.a.b.x.m.UnknownMapper.doAction - <==      Total: 1\n"
    )
    log_file.write_text(content, encoding="utf-8")

    # 1. t1: copyCodes 파라미터 이름 검증
    res_t1 = log_reader.get_trace_summary(trace_id="1111111100000001", file_path=str(log_file))
    assert "SysCodeMapper.copyCodes (newCompanyId=28000, sourceCompanyId=0, codeKindId=202407241733135) → Updates 0" in res_t1

    # 2. t2: foreach 포함 문장 -> 이름 없이 값만 그대로
    res_t2 = log_reader.get_trace_summary(trace_id="2222222200000002", file_path=str(log_file))
    assert "SysCodeMapper.batchInsert (1, 2) → Updates 2" in res_t2

    # 3. t3: 파라미터 개수 불일치 -> 이름 없이 값만 그대로
    res_t3 = log_reader.get_trace_summary(trace_id="3333333300000003", file_path=str(log_file))
    assert "SysCodeMapper.searchCodes (28000, KIND01) → Total 5" in res_t3

    # 4. t4: 매퍼 XML 없음 -> 이름 없이 값만 그대로
    res_t4 = log_reader.get_trace_summary(trace_id="4444444400000004", file_path=str(log_file))
    assert "UnknownMapper.doAction (999) → Total 1" in res_t4



