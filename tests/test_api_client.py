import json
from pathlib import Path

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools import api_client


def test_summarize_response_list():
    raw_data = [{"id": 1, "name": "Admin", "code": "R01"}, {"id": 2, "name": "User", "code": "R02"}]
    summary = api_client.summarize_response(200, json.dumps(raw_data), 120)
    assert "HTTP 200 (0.12s)" in summary
    assert "Rows: 2" in summary
    assert "Fields (3): [id, name, code]" in summary
    assert "First row:" in summary


def test_summarize_response_api_response_pattern():
    raw_data = {
        "status": "OK",
        "data": [{"role_id": "SYS01", "role_nm": "시스템관리자"}],
        "message": "조회 성공",
    }
    summary = api_client.summarize_response(200, json.dumps(raw_data), 80)
    assert "HTTP 200 (0.08s)" in summary
    assert "Status: OK" in summary
    assert "Rows: 1" in summary
    assert "Fields (2): [role_id, role_nm]" in summary


def test_summarize_response_single_object():
    raw_data = {"id": 100, "username": "admin", "tenantId": "kfs"}
    summary = api_client.summarize_response(200, json.dumps(raw_data), 50)
    assert "HTTP 200 (0.05s)" in summary
    assert "Object keys (3): [id, username, tenantId]" in summary


def test_summarize_response_error():
    raw_text = '{"error": "Unauthorized", "message": "Invalid token"}'
    summary = api_client.summarize_response(401, raw_text, 40)
    assert "HTTP 401 (0.04s)" in summary
    assert "Object keys (2): [error, message]" in summary


def test_request_api_mock(monkeypatch, tmp_path: Path):
    # 세션 디렉터리 격리
    monkeypatch.setattr(api_client, "get_sessions_dir", lambda: tmp_path)

    # httpx.request 가짜 응답
    class MockResponse:
        def __init__(self):
            self.status_code = 200
            self.is_success = True
            self.text = json.dumps([{"role_id": "R1", "role_nm": "Admin"}])
            self.cookies = {}

    monkeypatch.setattr("httpx.request", lambda **kwargs: MockResponse())
    monkeypatch.setattr("httpx.post", lambda **kwargs: MockResponse())

    res = api_client.request_api("GET", "/api/v1/roles", auto_login=False)
    assert res.ok is True
    assert "HTTP 200" in res.data["summary"]
    assert "Rows: 1" in res.data["summary"]

    runner_cli = CliRunner()
    cli_res = runner_cli.invoke(cli.app, ["api", "GET", "/api/v1/roles"])
    assert cli_res.exit_code == 0
    assert "HTTP 200" in cli_res.output
