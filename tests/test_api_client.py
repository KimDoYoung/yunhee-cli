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

        def json(self):
            return [{"role_id": "R1", "role_nm": "Admin"}]

    monkeypatch.setattr("httpx.request", lambda *args, **kwargs: MockResponse())
    monkeypatch.setattr("httpx.post", lambda *args, **kwargs: MockResponse())

    res = api_client.request_api("GET", "/api/v1/roles", auto_login=False)
    assert res.ok is True
    assert "HTTP 200" in res.data["summary"]
    assert "Rows: 1" in res.data["summary"]

    runner_cli = CliRunner()
    cli_res = runner_cli.invoke(cli.app, ["api", "GET", "/api/v1/roles"])
    assert cli_res.exit_code == 0
    assert "HTTP 200" in cli_res.output


def test_login_payload_with_company_code(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(api_client, "get_sessions_dir", lambda: tmp_path)

    captured_payload = {}

    class MockLoginResponse:
        def __init__(self):
            self.status_code = 200
            self.cookies = {"JSESSIONID": "mock-session-123"}
            self.text = '{"status": "OK"}'

        def json(self):
            return {"status": "OK"}

    def mock_post(url, json=None, headers=None, **kwargs):
        captured_payload.update(json or {})
        return MockLoginResponse()

    monkeypatch.setattr("httpx.post", mock_post)

    res = api_client.login(
        base_url="http://localhost:8082/OMS",
        user="admin",
        password="password",
        login_path="/api/auth/login",
        company_code="COMP_01",
        tenant="tenant_kfs",
    )
    assert res.ok is True
    assert captured_payload["username"] == "admin"
    assert captured_payload["companyCode"] == "COMP_01"


def test_login_failure_aborts_immediately_without_retry(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(api_client, "get_sessions_dir", lambda: tmp_path)

    login_call_count = 0

    class MockFailResponse:
        def __init__(self):
            self.status_code = 401
            self.text = '{"message": "아이디 또는 비밀번호가 올바르지 않습니다."}'

    def mock_post(url, **kwargs):
        nonlocal login_call_count
        login_call_count += 1
        return MockFailResponse()

    monkeypatch.setattr("httpx.post", mock_post)

    # auto_login=True 인 상태에서 로그인 실패 시 즉시 중단하고 에러 메시지를 명확히 반환해야 함
    res = api_client.request_api("GET", "/api/v1/sys/menus", auto_login=True)
    assert res.ok is False
    assert "로그인 실패 (HTTP 401)" in res.error
    assert "아이디 또는 비밀번호가 올바르지 않습니다" in res.error
    # 재시도하지 않아 호출 횟수는 정확히 1회여야 함 (5회 잠금 방지)
    assert login_call_count == 1


def test_tenant_session_isolation(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(api_client, "get_sessions_dir", lambda: tmp_path)

    class MockLoginResponse:
        def __init__(self, token):
            self.status_code = 200
            self.cookies = {"TOKEN": token}
            self.text = '{"status": "OK"}'

        def json(self):
            return {"status": "OK"}

    def mock_post(url, headers=None, **kwargs):
        tenant_id = (headers or {}).get("X-Tenant-Id", "default")
        return MockLoginResponse(f"token-for-{tenant_id}")

    monkeypatch.setattr("httpx.post", mock_post)

    # 테넌트 1로 로그인
    res1 = api_client.login(base_url="http://localhost:8082/OMS", user="admin", tenant="tenantA")
    assert res1.ok is True
    # 테넌트 2로 로그인
    res2 = api_client.login(base_url="http://localhost:8082/OMS", user="admin", tenant="tenantB")
    assert res2.ok is True

    # 세션 파일이 각각 별도로 존재하는지 확인
    files = list(tmp_path.glob("*.json"))
    assert len(files) == 2
    filenames = [f.name for f in files]
    assert any("tenantA" in name for name in filenames)
    assert any("tenantB" in name for name in filenames)


def test_summarize_response_envelope_unwrapping():
    # 1. 숫자 0
    resp_zero = json.dumps({"success": True, "code": "OK", "data": 0})
    s_zero = api_client.summarize_response(200, resp_zero, 30)
    assert "Status: OK" in s_zero
    assert "Data: 0" in s_zero
    assert "Object keys" not in s_zero

    # 2. 문자열
    resp_str = json.dumps({"success": True, "code": "OK", "data": "copy-success"})
    s_str = api_client.summarize_response(200, resp_str, 20)
    assert "Status: OK" in s_str
    assert 'Data: "copy-success"' in s_str
    assert "Object keys" not in s_str

    # 3. true (불리언)
    resp_bool = json.dumps({"success": True, "code": "OK", "data": True})
    s_bool = api_client.summarize_response(200, resp_bool, 20)
    assert "Status: OK" in s_bool
    assert "Data: true" in s_bool
    assert "Object keys" not in s_bool

    # 4. null
    resp_null = json.dumps({"success": True, "code": "OK", "data": None})
    s_null = api_client.summarize_response(200, resp_null, 25)
    assert "Status: OK" in s_null
    assert "Data: null" in s_null
    assert "Object keys" not in s_null

    # 5. 객체 (단일 dict)
    resp_obj = json.dumps({
        "success": True,
        "code": "OK",
        "data": {"id": 1, "username": "admin", "role": "SYSADMIN"},
    })
    s_obj = api_client.summarize_response(200, resp_obj, 40)
    assert "Status: OK" in s_obj
    assert "Fields (3): [id, username, role]" in s_obj
    assert "Data: {" in s_obj
    assert "Object keys" not in s_obj

    # 6. success: false (에러 봉투)
    resp_err = json.dumps({
        "success": False,
        "code": "INVALID_INPUT",
        "message": "권한명을 입력하세요.",
        "data": None,
    })
    s_err = api_client.summarize_response(400, resp_err, 15)
    assert "Error: INVALID_INPUT 권한명을 입력하세요." in s_err
    assert "Object keys" not in s_err

    # 7. 리스트 (회귀 테스트)
    resp_list = json.dumps({
        "success": True,
        "code": "OK",
        "data": [{"menuId": 1, "name": "시스템"}, {"menuId": 2, "name": "운용"}],
    })
    s_list = api_client.summarize_response(200, resp_list, 50)
    assert "Status: OK" in s_list
    assert "Rows: 2" in s_list
    assert "Fields (2): [menuId, name]" in s_list
    assert "First row:" in s_list
    assert "Object keys" not in s_list


def test_tenant_host_header_behavior(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(api_client, "get_sessions_dir", lambda: tmp_path)

    captured_req_headers = {}
    captured_login_headers = {}

    class MockResp:
        def __init__(self):
            self.status_code = 200
            self.is_success = True
            self.text = '{"success": true, "code": "OK", "data": "ok"}'
            self.cookies = {"TOKEN": "mock-token"}

        def json(self):
            return {"success": True, "code": "OK", "data": "ok"}

    def mock_post(url, headers=None, **kwargs):
        captured_login_headers.update(headers or {})
        return MockResp()

    def mock_request(method, url, headers=None, **kwargs):
        captured_req_headers.update(headers or {})
        return MockResp()

    monkeypatch.setattr("httpx.post", mock_post)
    monkeypatch.setattr("httpx.request", mock_request)

    # 1. 테넌트가 있을 때 (tenant="kfstest")
    res = api_client.request_api(
        "GET",
        "/api/public/tenant",
        base_url="http://localhost:8082/OMS",
        tenant="kfstest",
        auto_login=True,
    )
    assert res.ok is True
    assert "[tenant=kfstest]" in res.data["summary"]
    # Host 헤더 확인: kfstest.localhost:8082
    assert captured_req_headers.get("Host") == "kfstest.localhost:8082"
    assert captured_login_headers.get("Host") == "kfstest.localhost:8082"
    # X-Tenant-Id는 보내지 않아야 함
    assert "X-Tenant-Id" not in captured_req_headers
    assert "X-Tenant-Id" not in captured_login_headers

    # 2. 테넌트가 없을 때
    captured_req_headers.clear()
    res_no_tenant = api_client.request_api(
        "GET",
        "/api/public/tenant",
        base_url="http://localhost:8082/OMS",
        tenant=None,
        auto_login=False,
    )
    assert res_no_tenant.ok is True
    assert "[tenant=" not in res_no_tenant.data["summary"]
    assert "Host" not in captured_req_headers




def test_request_api_timeout_message(monkeypatch, tmp_path: Path):
    import httpx

    monkeypatch.setattr(api_client, "get_sessions_dir", lambda: tmp_path)
    seen: dict = {}

    def mock_request(*args, **kwargs):
        seen["timeout"] = kwargs.get("timeout")
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr("httpx.request", mock_request)

    res = api_client.request_api("GET", "/api/v1/sys/login-histories", auto_login=False, timeout=0.5)
    assert res.ok is False
    assert seen["timeout"] == 0.5
    assert "응답 시간 초과 (0.5s) — GET /api/v1/sys/login-histories" in res.error
    assert "--timeout 60" in res.error
    assert "API 요청 실패" not in res.error

    # 미지정 시 config.API_TIMEOUT 기본값 사용
    monkeypatch.setattr(api_client.config, "API_TIMEOUT", 7.0)
    api_client.request_api("GET", "/x", auto_login=False)
    assert seen["timeout"] == 7.0

    # CLI --timeout 전달
    cli_res = CliRunner().invoke(cli.app, ["api", "GET", "/x", "--timeout", "0.001"])
    assert cli_res.exit_code == 1
    assert seen["timeout"] == 0.001
    assert "응답 시간 초과 (0.001s)" in cli_res.output
