"""수정사항 053 검증 테스트.

1. run 시험 요약 (클래스 합산 및 analysis run last --tests 상세)
2. trace-crud (INSERT...SELECT 대상 R 제외 및 --why 근거)
3. compare (API 파라미터 자동 상속 및 --no-grid / 자동 그리드 판별)
4. 메뉴 없는 클래스 (analysis ui 연결 클래스 탐색 및 drift 처리)
5. callers 및 grep -l (파일 목록 출력 및 --server 호출자 검색)
"""

from yunhee.context.run_analyzer import summarize_run
from yunhee.tools.analysis.callers import render as render_callers
from yunhee.tools.analysis.callers import resolve as resolve_callers
from yunhee.tools.analysis.run import _parse_tests
from yunhee.tools.analysis.run import render as r_render
from yunhee.tools.outliner import grep_files
from yunhee.tools.runner import extract_test_results
from yunhee.tools.sql_parse import parse_sql_text


def test_runner_multi_tests_and_classes(tmp_path):
    """1. run 복수 --tests 패턴 및 클래스 카운트 검증."""
    test_results_dir = tmp_path / "build" / "test-results" / "test"
    test_results_dir.mkdir(parents=True)

    xml1 = test_results_dir / "TEST-kr.co.kfs.NoticeSmsSenderDbTest.xml"
    xml1.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="kr.co.kfs.NoticeSmsSenderDbTest" tests="4" skipped="0" failures="0" errors="0" timestamp="2026-11-10T10:00:00">
</testsuite>
""", encoding="utf-8")

    xml2 = test_results_dir / "TEST-kr.co.kfs.EmpMyLeaveDbTest.xml"
    xml2.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="kr.co.kfs.EmpMyLeaveDbTest" tests="4" skipped="0" failures="0" errors="0" timestamp="2026-11-10T10:00:00">
</testsuite>
""", encoding="utf-8")

    xml3 = test_results_dir / "TEST-kr.co.kfs.EmpBenefitDbTest.xml"
    xml3.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="kr.co.kfs.EmpBenefitDbTest" tests="6" skipped="0" failures="0" errors="0" timestamp="2026-11-10T10:00:00">
</testsuite>
""", encoding="utf-8")

    cmd = "gradle test --tests '*NoticeSmsSenderDbTest' --tests '*EmpMyLeaveDbTest' --tests '*EmpBenefitDbTest'"
    info = extract_test_results(cmd, cwd=tmp_path, stdout="", stderr="", exit_code=0)
    assert info is not None
    assert info["total"] == 14
    assert info["failures"] == 0
    assert info["classes"] == 3

    summary = summarize_run(cmd, exit_code=0, duration_ms=1200, log_path="/tmp/test.log", stdout="", stderr="", cwd=tmp_path)
    assert "tests 14 (fail 0, skip 0) · 클래스 3" in summary


def test_analysis_run_last_tests_detail(tmp_path):
    """1-2. analysis run last --tests 실패 상세(메서드 + 실패 메시지 + 스택) 검증."""
    test_results_dir = tmp_path / "build" / "test-results" / "test"
    test_results_dir.mkdir(parents=True)

    xml = test_results_dir / "TEST-kr.co.kfs.EmpLeaveCancelDbTest.xml"
    xml.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="kr.co.kfs.EmpLeaveCancelDbTest" tests="2" skipped="0" failures="1" errors="0">
  <testcase name="상신하지_않은_휴가와_다른_회사_휴가는_취소할_수_없다" classname="kr.co.kfs.EmpLeaveCancelDbTest">
    <failure message="NullPointerException: Cannot invoke Object.equals because o is null" type="java.lang.NullPointerException">
java.lang.NullPointerException: Cannot invoke "Object.equals(Object)" because "o" is null
    at java.base/java.util.ImmutableCollections$Set12.contains(ImmutableCollections.java:689)
    at kr.co.kfs.EmpLeaveCancelDbTest.상신하지_않은_휴가와_다른_회사_휴가는_취소할_수_없다(EmpLeaveCancelDbTest.java:123)
    </failure>
  </testcase>
</testsuite>
""", encoding="utf-8")

    test_info = _parse_tests(tmp_path, "")
    assert test_info["failures"] == 1

    obj = {"run_record": {}, "log_text": "", "stdout": "", "stderr": ""}
    import yunhee.config as conf
    orig_work_dir = conf.WORK_DIR
    try:
        conf.WORK_DIR = tmp_path
        out = r_render(obj, fmt="md", opts={"tests": True})
        assert "❌ EmpLeaveCancelDbTest.상신하지_않은_휴가와_다른_회사_휴가는_취소할_수_없다" in out
        assert "NullPointerException" in out
        assert "at kr.co.kfs" in out
    finally:
        conf.WORK_DIR = orig_work_dir


def test_sql_parse_insert_select_target_w_only():
    """2. INSERT ... SELECT 에서 대상 테이블은 W만 부여되고 R은 붙지 않아야 함."""
    sql = """
INSERT
  INTO apr99_appr_del
SELECT
    f_create_seq()
    , apr01_appr_id
  FROM apr01_appr
 WHERE apr01_appr_id = 1
"""
    p = parse_sql_text(sql)
    assert p.tables.get("apr99_appr_del") == "W"
    assert p.tables.get("apr01_appr") == "R"


def test_grep_files_with_matches(tmp_path):
    """5-1. yunhee grep -l (files_with_matches) 검증."""
    f1 = tmp_path / "A.java"
    f1.write_text("class A { SendSMSAPI api; }", encoding="utf-8")
    f2 = tmp_path / "B.java"
    f2.write_text("class B { int x; }", encoding="utf-8")
    f3 = tmp_path / "C.java"
    f3.write_text("// SendSMSAPI used here", encoding="utf-8")

    res = grep_files("SendSMSAPI", [tmp_path], files_with_matches=True)
    assert res.ok
    files = res.data.splitlines()
    assert len(files) == 2
    assert any("A.java" in f for f in files)
    assert any("C.java" in f for f in files)
    assert not any("B.java" in f for f in files)


def test_callers_server_and_method(tmp_path):
    """5-2. analysis callers --server 및 메서드 호출자 검색 검증."""
    server_dir = tmp_path / "server" / "kr" / "co" / "kfs"
    server_dir.mkdir(parents=True)

    caller1 = server_dir / "EmpService.java"
    caller1.write_text("""package kr.co.kfs;
public class EmpService {
    public void sendNotice() {
        SendSMSAPI.send("010-1234-5678", "hello");
    }
}
""", encoding="utf-8")

    caller2 = server_dir / "SysService.java"
    caller2.write_text("""package kr.co.kfs;
public class SysService {
    public void resetPassword() {
        SendSMSAPI.send("010-0000-0000", "pw reset");
    }
}
""", encoding="utf-8")

    res = resolve_callers("SendSMSAPI", {"src": tmp_path, "server": True})
    assert len(res["rows"]) >= 2
    classes = [r["caller_class"] for r in res["rows"]]
    assert "EmpService" in classes
    assert "SysService" in classes

    rendered = render_callers(res)
    assert "EmpService.java" in rendered
    assert "SysService.java" in rendered


def test_analysis_ui_linked_class_fallback(tmp_path):
    """4. analysis ui 에서 독립 문서가 없는 경우 부모 화면에서 연결 클래스 역추적 검증."""
    from yunhee.tools.analysis.ui import resolve as resolve_ui

    screens_dir = tmp_path / "screens"
    screens_dir.mkdir(parents=True)

    parent_md = screens_dir / "Emp20_Tab_Leave.md"
    parent_md.write_text("""---
title: 휴가 관리
source_files:
  - myApp/client/vi/emp/Emp20_Tab_Leave.java
  - myApp/client/vi/emp/Emp20_Edit_Leave.java
---
# Emp20_Tab_Leave

### Emp20_Tab_Leave.java
#### 버튼
- <Button>조회</Button>

### Emp20_Edit_Leave.java
#### 버튼
- <Button>저장</Button>
- <Button>취소</Button>
""", encoding="utf-8")

    res = resolve_ui("Emp20_Edit_Leave", {"src_index": tmp_path})
    assert res is not None
    assert "as_is" in res
    class_names = list(res["as_is"].keys())
    assert "Emp20_Edit_Leave" in class_names
    # 부모 화면의 다른 클래스는 필터링되어 Emp20_Edit_Leave만 남아있어야 함
    assert "Emp20_Tab_Leave" not in class_names

