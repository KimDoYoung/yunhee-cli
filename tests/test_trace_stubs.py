"""Tests for trace-* business exploration commands stubs."""

import json

from typer.testing import CliRunner

from yunhee.cli import app

runner = CliRunner()

ALL_TRACE_COMMANDS = [
    ("trace-map", ["--domain", "sys"]),
    ("trace-menu", ["시스템관리 > 권한관리"]),
    ("trace-screen", ["Fnd01_Tab_FundSearch"]),
    ("trace-table", ["sys01_company"]),
    ("trace-column", ["sys01_company.company_id"]),
    ("trace-code", ["LinkCode"]),
    ("trace-state", ["fnd01_fund.stat_cd"]),
    ("trace-crud", ["--domain", "sys", "--table", "sys01_company"]),
    ("trace-flow", ["Fnd01_Tab_FundSearch", "--event", "E1"]),
    ("trace-branch", ["Fnd01_Tab_FundSearch"]),
    ("trace-dblogic", ["fn_calc_amount"]),
    ("trace-pair", ["Fnd01_Tab_FundSearch"]),
    ("trace-diff", ["Fnd01_Tab_FundSearch", "--sql", "--branch"]),
    ("trace-gap", ["--domain", "sys"]),
    ("trace-rule", ["verify", "Fnd01_Tab_FundSearch", "--note", "규칙 검증"]),
    ("trace-term", ["펀드"]),
    ("trace-doc", ["sys"]),
    ("trace-guide", []),
]


# 구현이 끝난 명령은 전용 테스트(test_trace_screen.py, test_trace_table.py)가 검증한다
IMPLEMENTED = {"trace-screen", "trace-table"}
STUB_COMMANDS = [(name, args) for name, args in ALL_TRACE_COMMANDS if name not in IMPLEMENTED]


def test_all_trace_commands_help():
    """Verify that all 18 trace-* commands provide help."""
    for cmd_name, _ in ALL_TRACE_COMMANDS:
        result = runner.invoke(app, [cmd_name, "--help"])
        assert result.exit_code == 0, f"{cmd_name} --help failed: {result.output}"
        assert "Usage: " in result.output
        assert "--side" in result.output
        assert "--format" in result.output


def test_all_trace_commands_markdown():
    """Verify standard 3 markdown blocks (## facts, ## evidence, ## unresolved) for all stub commands."""
    for cmd_name, sample_args in STUB_COMMANDS:
        result = runner.invoke(app, [cmd_name] + sample_args + ["--side", "asis", "--format", "md"])
        assert result.exit_code == 0, f"{cmd_name} failed: {result.output}"
        assert "## facts" in result.output
        assert "## evidence" in result.output
        assert "## unresolved" in result.output
        assert f"- command: yunhee {cmd_name}" in result.output
        assert "- side: asis" in result.output


def test_all_trace_commands_json():
    """Verify JSON output structure for all stub commands."""
    for cmd_name, sample_args in STUB_COMMANDS:
        result = runner.invoke(app, [cmd_name] + sample_args + ["-o", "json", "--side", "tobe"])
        assert result.exit_code == 0, f"{cmd_name} JSON failed: {result.output}"
        data = json.loads(result.output)
        assert data["command"] == cmd_name
        assert data["side"] == "tobe"
        assert "description" in data
        assert "options" in data
        assert "params" in data
        assert isinstance(data["facts"], list)
        assert len(data["facts"]) > 0
        assert isinstance(data["evidence"], list)
        assert isinstance(data["unresolved"], list)


def test_max_option():
    """Verify --max option is recorded in output."""
    r_md = runner.invoke(app, ["trace-map", "--domain", "sys", "--max", "20"])
    assert r_md.exit_code == 0
    assert "max=20" in r_md.output

    r_json = runner.invoke(app, ["trace-map", "--domain", "sys", "--max", "20", "-o", "json"])
    assert r_json.exit_code == 0
    data = json.loads(r_json.output)
    assert data["options"]["max"] == 20


def test_log_request_alias():
    """Verify yunhee log request alias works."""
    r = runner.invoke(app, ["log", "request", "--help"])
    assert r.exit_code == 0
    assert "Usage: " in r.output
    assert "trace_id" in r.output
