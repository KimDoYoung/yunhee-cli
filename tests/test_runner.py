import sqlite3
from pathlib import Path

from typer.testing import CliRunner

from yunhee import cli
from yunhee.context.run_analyzer import summarize_run
from yunhee.store import run_tracker
from yunhee.tools import runner


def test_execute_command_success(tmp_path: Path):
    result = runner.execute_command("echo 'hello runner'", cwd=tmp_path)
    assert result.ok is True
    assert result.error is None
    data = result.data
    assert data["exit_code"] == 0
    assert "hello runner" in data["stdout"]
    assert Path(data["log_path"]).exists()

    log_content = Path(data["log_path"]).read_text()
    assert "=== Command: echo 'hello runner' ===" in log_content
    assert "hello runner" in log_content


def test_execute_command_failure(tmp_path: Path):
    cmd = "python3 -c 'import sys; sys.stderr.write(\"sample err\"); sys.exit(7)'"
    result = runner.execute_command(cmd, cwd=tmp_path)
    assert result.ok is False
    assert result.error == "Command failed with exit code 7"
    data = result.data
    assert data["exit_code"] == 7
    assert "sample err" in data["stderr"]
    assert Path(data["log_path"]).exists()


def test_execute_command_truncation(tmp_path: Path):
    cmd = "python3 -c 'print(\"A\" * 500)'"
    result = runner.execute_command(cmd, cwd=tmp_path, char_preview_limit=50)
    assert result.truncated is True
    assert "[TRUNCATED in preview]" in result.data["stdout_preview"]
    assert len(result.data["stdout"].strip()) == 500


def test_run_tracker_crud():
    conn = sqlite3.connect(":memory:")
    run_tracker.init_db(conn)

    run_tracker.save_run(
        run_id="run_1",
        project="test_proj",
        command="echo 1",
        exit_code=0,
        duration_ms=100,
        log_path="/tmp/run1.log",
        summary="Success summary",
        created_at="2026-10-01T10:00:00Z",
        conn=conn,
    )
    run_tracker.save_run(
        run_id="run_2",
        project="test_proj",
        command="echo 2",
        exit_code=1,
        duration_ms=250,
        log_path="/tmp/run2.log",
        summary="Fail summary",
        created_at="2026-10-01T10:05:00Z",
        conn=conn,
    )

    last = run_tracker.get_last_run("test_proj", conn=conn)
    assert last is not None
    assert last["id"] == "run_2"
    assert last["exit_code"] == 1

    runs = run_tracker.list_runs("test_proj", limit=10, conn=conn)
    assert len(runs) == 2
    assert runs[0]["id"] == "run_2"
    assert runs[1]["id"] == "run_1"

    item = run_tracker.get_run("run_1", conn=conn)
    assert item is not None
    assert item["command"] == "echo 1"


def test_summarize_run_success():
    summary = summarize_run(
        command="npm test",
        exit_code=0,
        duration_ms=1230,
        log_path="/path/to/log.log",
        stdout="Test Suites: 5 passed, 5 total",
        stderr="",
        use_llm=False,
    )
    assert summary == "✅ Execution Succeeded in 1.23s: `npm test` (log: /path/to/log.log)"


def test_summarize_run_failure_without_llm():
    summary = summarize_run(
        command="mvn compile",
        exit_code=1,
        duration_ms=4500,
        log_path="/path/to/mvn.log",
        stdout="",
        stderr="[ERROR] Failed to execute goal: compilation failure",
        use_llm=False,
    )
    assert "❌ Execution Failed (exit code: 1, 4.50s)" in summary
    assert "`mvn compile`" in summary
    assert "compilation failure" in summary


def test_cli_run_and_history(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    runner_cli = CliRunner()

    # 1. run command 성공
    res = runner_cli.invoke(cli.app, ["run", "echo 'cli test'", "--no-llm"])
    assert res.exit_code == 0
    assert "✅ Execution Succeeded" in res.output

    # 2. last-run 확인
    res_last = runner_cli.invoke(cli.app, ["last-run"])
    assert res_last.exit_code == 0
    assert "echo 'cli test'" in res_last.output

    # 3. runs 리스트 확인
    res_runs = runner_cli.invoke(cli.app, ["runs"])
    assert res_runs.exit_code == 0
    assert "echo" in res_runs.output
    assert "test" in res_runs.output


def test_cli_agent_guide():
    runner_cli = CliRunner()
    res = runner_cli.invoke(cli.app, ["agent-guide"])
    assert res.exit_code == 0
    assert "YUNHEE AI AGENT PROTOCOL" in res.output
    assert "yunhee outline" in res.output
    assert "yunhee table" in res.output
    assert "yunhee run" in res.output


def test_cli_config():
    runner_cli = CliRunner()
    res = runner_cli.invoke(cli.app, ["config"])
    assert res.exit_code == 0
    assert "Target (Work Dir)" in res.output
    assert "Source (ASIS)" in res.output
    assert "Local DB" in res.output


