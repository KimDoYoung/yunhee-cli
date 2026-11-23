import ast
from pathlib import Path
from unittest import mock

from yunhee.tools import sql_runner
from yunhee.tools.test.bz_event_skel import (
    check_bz_event_docs,
    generate_bz_event_code,
)
from yunhee.tools.test.coverage import (
    StatementCoverage,
    _match_preparing_line,
    run_test_coverage,
)


def test_068_11_sql_duplicate_columns_preserved():
    """068 #11: 별칭 없는 같은 이름 열(count, count)이 합쳐지지 않고 순서대로 출력되는지 검증."""
    with mock.patch("yunhee.tools.sql_runner.psycopg.connect") as mock_conn:
        mock_cur = mock.MagicMock()
        c1 = mock.MagicMock()
        c1.name = "count"
        c2 = mock.MagicMock()
        c2.name = "count"
        mock_cur.description = [c1, c2]
        mock_cur.fetchall.return_value = [(6, 0)]
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cur

        res = sql_runner.run_sql(
            query="select count(*), count(*) filter (where emp55_benefit_cd='TST9') from emp55_benefit_info where emp55_company_id=0",
            output_fmt="tsv",
            no_header=True,
            db_name="postgresql://fake",
        )
        assert res.ok
        assert res.data["formatted"] == "6\t0"
        assert any("같은 이름 열 'count'" in w for w in res.data["warnings"])


def test_068_bz_event_skel_emp_0018_and_0021_and_0023():
    """068 #1~#13: EMP-BZ-0018, 0021, 0022, 0023 이벤트 테스트 뼈대 품질 및 AST 검증."""
    real_root = Path("/home/kdy987/work/framework-sprt/AssetERP")
    if not real_root.is_dir():
        return

    # 1. EMP-BZ-0018: actor 이어받기(c401), 자리표시(emp["402"], errand_id), returns({"": 3}), sc.raw 에러 기대
    r18 = generate_bz_event_code("EMP-BZ-0018", src_root=real_root)
    assert r18.ok
    code18 = r18.data["code"]
    ast.parse(code18)
    assert 'EventTest("EMP-BZ-0018"' in code18
    assert "Client(COMPANY," in code18
    assert 'emp["402"]' in code18
    assert '{"publicYn": True}' in code18
    assert 'expect={"": 3}' in code18
    assert "sc.raw(" in code18
    assert "apr.save_body(" in code18

    # 2. EMP-BZ-0021: company: admin -> Client("admin", "admin", PW), 상대 경로 /copy, rows -> len(v or []) == 6
    r21 = generate_bz_event_code("EMP-BZ-0021", src_root=real_root)
    assert r21.ok
    code21 = r21.data["code"]
    ast.parse(code21)
    assert 'Client("admin", "admin", PW)' in code21
    assert "len(v or []) == 6" in code21
    assert '"/api/v1/emp/benefit-infos/copy"' in code21
    assert '"/api/v1/emp/benefit-infos?companyId=0"' in code21

    # 3. EMP-BZ-0022: 중복 api: 키 감지 및 보존
    r22 = generate_bz_event_code("EMP-BZ-0022", src_root=real_root)
    assert r22.ok
    assert len(r22.data["dup_warnings"]) >= 1
    ast.parse(r22.data["code"])

    # 4. EMP-BZ-0023: 멀티라인 주석 안전화 및 <3> 변수 바인딩
    r23 = generate_bz_event_code("EMP-BZ-0023", src_root=real_root)
    assert r23.ok
    code23 = r23.data["code"]
    ast.parse(code23)
    assert '"evalListStdId": sid' in code23
    assert '"/api/v1/emp/eval-list-stds/fix", body={"fixYn": False}' in code23


def test_068_14_check_bz_event_docs():
    """068 #14: --check 모드로 도메인 문서 일괄 점검."""
    real_root = Path("/home/kdy987/work/framework-sprt/AssetERP")
    if not real_root.is_dir():
        return
    res = check_bz_event_docs("EMP-BZ-0018", src_root=real_root)
    assert res.ok
    assert "✅ EMP-BZ-0018" in res.data["summary"]


def test_069_coverage_dedup_and_log_matching():
    """069 #1~#3: 문장 이중 집계 방지 및 Preparing 로그 매칭(확실 vs 모호) 검증."""
    st1 = StatementCoverage(
        domain="emp",
        mapper="EmpBenefitMapper",
        statement_id="insert",
        sql_tables={"emp17_benefit"},
    )
    st2 = StatementCoverage(
        domain="emp",
        mapper="EmpErrandMapper",
        statement_id="insert",
        sql_tables={"emp54_errand"},
    )
    st3 = StatementCoverage(
        domain="emp",
        mapper="EmpBenefitMapper",
        statement_id="selectNextId",
        sql_tables=set(),
    )
    st4 = StatementCoverage(
        domain="emp",
        mapper="EmpErrandMapper",
        statement_id="selectNextId",
        sql_tables=set(),
    )
    by_sid = {
        "insert": [st1, st2],
        "selectNextId": [st3, st4],
    }

    # 1. 테이블명으로 유일하게 특정되는 경우 -> 확실(exact)
    ex, am = _match_preparing_line(
        "k.c.k.a.b.e.m.E.insert",
        "INSERT INTO emp54_errand (emp54_errand_id) VALUES (?)",
        by_sid,
        "log",
    )
    assert ex == 1 and am == 0
    assert st2.is_tested and not st1.is_tested

    # 2. 테이블 없이 동일 도메인/이니셜에 여러 개 있는 경우 -> 모호(ambig)
    ex2, am2 = _match_preparing_line(
        "k.c.k.a.b.e.m.E.selectNextId",
        "SELECT f_create_seq()",
        by_sid,
        "log",
    )
    assert ex2 == 0 and am2 == 2
    assert st3.is_ambiguous and st4.is_ambiguous

    # 3. 실제 레포에서 중복 제거된 문장 수(2배로 부풀지 않음) 확인
    real_root = Path("/home/kdy987/work/framework-sprt/AssetERP")
    if real_root.is_dir():
        cov_res = run_test_coverage(domain_filter="emp", src_root=real_root)
        assert cov_res.ok
        assert 400 <= cov_res.data["total_statements"] < 800
