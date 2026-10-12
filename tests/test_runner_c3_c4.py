"""C-3(테스트 수 요약), C-4(상위 프로젝트 루트 탐색 및 cwd), C-5(outline 다중 경로) 단위 테스트."""

from pathlib import Path

from yunhee import project
from yunhee.context.run_analyzer import summarize_run
from yunhee.store import run_tracker
from yunhee.tools.outliner import outline_path
from yunhee.tools.runner import execute_command, extract_test_results


def test_c3_extract_test_results_xml(tmp_path: Path):
    # gradle test results XML 디렉토리 모의
    results_dir = tmp_path / "build" / "test-results" / "test"
    results_dir.mkdir(parents=True, exist_ok=True)

    xml_file = results_dir / "TEST-com.example.TransInfoDbTest.xml"
    xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.TransInfoDbTest" tests="3" failures="1" errors="0" skipped="0">
  <testcase name="testSuccess" classname="com.example.TransInfoDbTest"/>
  <testcase name="기본정보_저장_사원번호_중복" classname="com.example.TransInfoDbTest">
    <failure message="중복 에러" type="BusinessException"/>
  </testcase>
  <testcase name="testAnother" classname="com.example.TransInfoDbTest"/>
</testsuite>
""", encoding="utf-8")

    res = extract_test_results("./gradlew test", cwd=tmp_path)
    assert res is not None
    assert res["total"] == 3
    assert res["failures"] == 1
    assert res["skipped"] == 0
    assert any("TransInfoDbTest > 기본정보_저장_사원번호_중복 FAILED" in c for c in res["failed_cases"])

    # summarize_run 실패 케이스 최상단 표시 검증
    summary = summarize_run(
        command="./gradlew test",
        exit_code=1,
        duration_ms=1500,
        log_path="test.log",
        stdout="",
        stderr="Test failed",
        use_llm=False,
        cwd=tmp_path,
    )
    first_line = summary.splitlines()[0]
    assert "❌ TransInfoDbTest > 기본정보_저장_사원번호_중복 FAILED" in first_line


def test_c4_find_project_root_and_cwd(tmp_path: Path):
    # 루트에 .yunhee.toml 생성
    root_dir = tmp_path / "my_project"
    root_dir.mkdir()
    (root_dir / ".yunhee.toml").write_text("[as_is]\n", encoding="utf-8")

    frontend_dir = root_dir / "frontend" / "src"
    frontend_dir.mkdir(parents=True)

    # 하위 폴더에서 project_root 탐색
    found_root = project.find_project_root(frontend_dir)
    assert found_root == root_dir

    # execute_command 실행 시 상대 cwd 기록 확인
    res = execute_command("echo test", cwd=frontend_dir)
    assert res.ok is True
    data = res.data
    assert data["cwd"] == "frontend/src"
    assert data["project_root"] == str(root_dir)

    # run_tracker 저장 및 조회 검증
    import uuid
    test_run_id = f"run_c4_{uuid.uuid4().hex[:8]}"
    run_tracker.save_run(
        run_id=test_run_id,
        project="my_project",
        command="echo test",
        exit_code=0,
        duration_ms=10,
        log_path=data["log_path"],
        summary="성공",
        cwd=data["cwd"],
    )
    rec = run_tracker.get_run(test_run_id)
    assert rec is not None
    assert rec["cwd"] == "frontend/src"


def test_c5_outline_multiple_files(tmp_path: Path):
    f1 = tmp_path / "A.ts"
    f1.write_text("export const a = 1;\nexport function foo() {}\n", encoding="utf-8")
    f2 = tmp_path / "B.ts"
    f2.write_text("export const b = 2;\nexport function bar() {}\n", encoding="utf-8")

    res1 = outline_path(str(f1))
    res2 = outline_path(str(f2))
    assert res1.ok is True
    assert res2.ok is True
    assert "foo()" in res1.data
    assert "bar()" in res2.data


def test_c3_up_to_date_and_failed_details(tmp_path: Path):
    results_dir = tmp_path / "build" / "test-results" / "test"
    results_dir.mkdir(parents=True, exist_ok=True)
    xml_file = results_dir / "TEST-com.example.SampleTest.xml"
    xml_file.write_text("""<?xml version="1.0" encoding="UTF-8"?>
<testsuite name="com.example.SampleTest" tests="5" failures="1" errors="0" skipped="0">
  <testcase name="testFail" classname="com.example.SampleTest">
    <failure message="expected: 1 but was: 2" type="AssertionError">
org.opentest4j.AssertionFailedError: expected: 1 but was: 2
\tat com.example.SampleTest.testFail(SampleTest.java:42)
    </failure>
  </testcase>
  <testcase name="testPass" classname="com.example.SampleTest"/>
</testsuite>
""", encoding="utf-8")

    # XML이 start_time보다 과거인 상황 시뮬레이션
    old_time = xml_file.stat().st_mtime
    future_start = old_time + 10.0

    # 1. exit_code == 0 (UP-TO-DATE): 기존 XML 유지
    res_up_to_date = extract_test_results(
        "gradle test",
        cwd=tmp_path,
        start_time=future_start,
        exit_code=0,
    )
    assert res_up_to_date is not None
    assert res_up_to_date["total"] == 5

    # 2. exit_code == 1 (빌드 에러 등 새 XML 미생성): 과거 XML 폐기
    res_failed_no_new_xml = extract_test_results(
        "gradle test",
        cwd=tmp_path,
        start_time=future_start,
        exit_code=1,
    )
    assert res_failed_no_new_xml is None

    # 3. failed_details 추출 검증
    res_fail = extract_test_results("gradle test", cwd=tmp_path)
    assert res_fail is not None
    details = res_fail.get("failed_details", [])
    assert len(details) == 1
    assert details[0]["name"] == "SampleTest > testFail"
    assert "expected: 1 but was: 2" in details[0]["message"]
    assert details[0]["at"] == "SampleTest.java:42"

