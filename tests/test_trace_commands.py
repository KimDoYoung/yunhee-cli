"""trace-* 18개 명령의 등록과 공통 계약 (각 명령의 동작은 test_trace_<명령>.py가 검증한다)."""

from typer.testing import CliRunner

from yunhee.cli import app

runner = CliRunner()

ALL_TRACE_COMMANDS = [
    "trace-map", "trace-menu", "trace-screen",
    "trace-table", "trace-column", "trace-code", "trace-state", "trace-crud",
    "trace-flow", "trace-branch", "trace-dblogic",
    "trace-pair", "trace-diff", "trace-gap",
    "trace-rule", "trace-term", "trace-doc", "trace-guide",
]


def test_all_18_commands_are_registered():
    registered = {c.name for c in app.registered_commands if c.name and c.name.startswith("trace-")}
    assert registered == set(ALL_TRACE_COMMANDS)


def test_every_command_has_help_and_common_options():
    for name in ALL_TRACE_COMMANDS:
        result = runner.invoke(app, [name, "--help"])
        assert result.exit_code == 0, f"{name} --help failed: {result.output}"
        assert "Usage: " in result.output and "--format" in result.output
        if name != "trace-guide":  # 지침은 대상 소스를 읽지 않는다
            assert "--side" in result.output


def test_every_command_has_a_one_line_description():
    from yunhee.tools.trace.guide import registered_commands

    cmds = registered_commands()
    assert set(cmds) == set(ALL_TRACE_COMMANDS)
    assert all(desc for desc in cmds.values())


def test_log_request_alias():
    """`log trace`와 trace-* 이름이 헷갈리지 않게 `log request` 별칭이 있다."""
    r = runner.invoke(app, ["log", "request", "--help"])
    assert r.exit_code == 0 and "Usage: " in r.output and "trace_id" in r.output
