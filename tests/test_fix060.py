from pathlib import Path
from unittest.mock import MagicMock

import pytest

from yunhee.tools import api_client


class TestApiLogin:
    """수정사항060 #1: api 로그인 강화 및 계정 보호 안전장치 테스트."""

    def test_resolve_credentials_by_company_code(self, monkeypatch):
        """사번 401이 회사 A(id=10), B(id=20)에 있을 때 company_code='B'면 B의 사원 ID 선택."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        def fake_execute(query, params=None):
            q = query.strip()
            if "FROM sys01_company" in q:
                if params and params[0] == "B":
                    mock_cur.fetchone.return_value = {"sys01_company_id": 20}
                elif params and params[0] == "A":
                    mock_cur.fetchone.return_value = {"sys01_company_id": 10}
                else:
                    mock_cur.fetchone.return_value = None
            elif "FROM emp01_person" in q:
                # company_id에 따라 분기
                if params and len(params) >= 3 and params[2] == 20:
                    mock_cur.fetchone.return_value = {
                        "emp01_person_id": 200401,
                        "emp01_emp_no": "401",
                        "pwd": "decrypted_pwd",
                        "emp01_company_id": 20,
                    }
                elif params and len(params) >= 3 and params[2] == 10:
                    mock_cur.fetchone.return_value = {
                        "emp01_person_id": 100401,
                        "emp01_emp_no": "401",
                        "pwd": "decrypted_pwd",
                        "emp01_company_id": 10,
                    }
                else:
                    mock_cur.fetchone.return_value = None
            elif "FROM emp00_trans_info" in q:
                mock_cur.fetchone.return_value = {"emp00_org_code_id": 101}

        mock_cur.execute.side_effect = fake_execute

        monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: mock_conn)
        monkeypatch.setattr("yunhee.tools.sql_runner.get_connection_string", lambda *args: "postgresql://fake")

        u, _p, info = api_client.resolve_user_credentials("401", company_code="B")
        assert u == "401"
        assert info["user_id"] == 200401
        assert info["company_id"] == 20
        assert info["pw_source"] == "emp01_password"

    def test_resolve_credentials_ambiguous_emp_no_raises(self, monkeypatch):
        """회사 코드가 없는데 같은 사번이 여러 회사에 있으면 예외 발생."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        def fake_execute(query, params=None):
            q = query.strip()
            if "FROM emp01_person" in q:
                mock_cur.fetchall.return_value = [
                    {"emp01_person_id": 100401, "emp01_emp_no": "401", "pwd": "p1", "emp01_company_id": 10},
                    {"emp01_person_id": 200401, "emp01_emp_no": "401", "pwd": "p2", "emp01_company_id": 20},
                ]

        mock_cur.execute.side_effect = fake_execute

        monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: mock_conn)
        monkeypatch.setattr("yunhee.tools.sql_runner.get_connection_string", lambda *args: "postgresql://fake")

        with pytest.raises(ValueError, match="사원 ID로"):
            api_client.resolve_user_credentials("401", company_code=None)

    def test_password_priority(self, monkeypatch):
        """비밀번호 우선순위: password 인자 > YUNHEE_TEST_ACCOUNTS > DB 비밀번호 > DEFAULT_PASS."""
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        def fake_execute(query, params=None):
            q = query.strip()
            if "FROM emp01_person" in q:
                mock_cur.fetchall.return_value = [
                    {"emp01_person_id": 100401, "emp01_emp_no": "401", "pwd": "db_pass", "emp01_company_id": 10}
                ]
            elif "FROM emp00_trans_info" in q:
                mock_cur.fetchone.return_value = {"emp00_org_code_id": 101}

        mock_cur.execute.side_effect = fake_execute
        monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: mock_conn)
        monkeypatch.setattr("yunhee.tools.sql_runner.get_connection_string", lambda *args: "postgresql://fake")

        # 1. password 인자가 최우선
        monkeypatch.setenv("YUNHEE_TEST_ACCOUNTS", "401:acc_pass")
        monkeypatch.setenv("YUNHEE_TEST_DEFAULT_PASS", "def_pass")
        _u, p, info = api_client.resolve_user_credentials("401", password="cli_pass")
        assert p == "cli_pass"
        assert info["pw_source"] == "--password"

        # 2. password 인자 없으면 YUNHEE_TEST_ACCOUNTS
        _u, p, info = api_client.resolve_user_credentials("401")
        assert p == "acc_pass"
        assert info["pw_source"] == "YUNHEE_TEST_ACCOUNTS"

        # 3. ACCOUNTS 없으면 DB pwd
        monkeypatch.delenv("YUNHEE_TEST_ACCOUNTS", raising=False)
        _u, p, info = api_client.resolve_user_credentials("401")
        assert p == "db_pass"
        assert info["pw_source"] == "emp01_password"

        # 4. DB pwd 없으면 DEFAULT_PASS
        def fake_execute_no_pwd(query, params=None):
            q = query.strip()
            if "FROM emp01_person" in q:
                mock_cur.fetchall.return_value = [
                    {"emp01_person_id": 100401, "emp01_emp_no": "401", "pwd": None, "emp01_company_id": 10}
                ]
            elif "FROM emp00_trans_info" in q:
                mock_cur.fetchone.return_value = None

        mock_cur.execute.side_effect = fake_execute_no_pwd
        _u, p, info = api_client.resolve_user_credentials("401")
        assert p == "def_pass"
        assert info["pw_source"] == "YUNHEE_TEST_DEFAULT_PASS"

    def test_login_failure_details_and_lock_guard(self, monkeypatch, tmp_path: Path):
        """로그인 실패 시 시도 상세정보 출력 및 3회 이상 실패 시 재로그인 차단 안전장치."""
        monkeypatch.setattr(api_client, "get_sessions_dir", lambda: tmp_path)

        class MockFailResponse:
            def __init__(self, count: int):
                self.status_code = 401
                self.text = f'{{"code":"LOGIN_FAILED","message":"비밀번호가 일치하지 않습니다. (실패 {count}/5회)"}}'
                self.cookies = {}

        # 1. 2회 실패
        monkeypatch.setattr("httpx.post", lambda *args, **kwargs: MockFailResponse(2))
        res = api_client.login(
            user="401",
            password="wrong",
            company_code="kalpa",
            user_info={"user_id": 202611109048654, "emp_no": "401", "pw_source": "YUNHEE_TEST_ACCOUNTS"},
        )
        assert not res.ok
        assert "시도: 사원 202611109048654(사번 401, 회사 kalpa)" in res.error
        assert "비밀번호 출처 YUNHEE_TEST_ACCOUNTS" in res.error
        assert "서버 실패 횟수 2/5회" in res.error

        # 2. 3회 실패 시도
        monkeypatch.setattr("httpx.post", lambda *args, **kwargs: MockFailResponse(3))
        res3 = api_client.login(
            user="401",
            password="wrong",
            company_code="kalpa",
            user_info={"user_id": 202611109048654, "emp_no": "401", "pw_source": "YUNHEE_TEST_ACCOUNTS"},
        )
        assert not res3.ok
        assert "서버 실패 횟수 3/5회" in res3.error

        # 3. 3회 실패 이후 재시도 차단 확인
        res_blocked = api_client.login(
            user="401",
            password="wrong",
            company_code="kalpa",
            user_info={"user_id": 202611109048654, "emp_no": "401", "pw_source": "YUNHEE_TEST_ACCOUNTS"},
            force_login=False,
        )
        assert not res_blocked.ok
        assert "잠금 직전" in res_blocked.error
        assert "--force-login" in res_blocked.error

        # 4. force_login=True 로는 통과
        res_forced = api_client.login(
            user="401",
            password="wrong",
            company_code="kalpa",
            user_info={"user_id": 202611109048654, "emp_no": "401", "pw_source": "YUNHEE_TEST_ACCOUNTS"},
            force_login=True,
        )
        # 실패 응답을 직접 받음 (가드에 의해 차단되지 않음)
        assert "서버 실패 횟수 3/5회" in res_forced.error


class TestBizEndpoints:
    """수정사항060 #2: biz-endpoints 파싱 및 표/JSON 출력 테스트."""

    def test_collect_endpoints_fixtures(self):
        from yunhee.tools.biz.endpoints import (
            collect_endpoints,
            format_endpoints_json,
            format_endpoints_md,
        )

        fixture_dir = Path(__file__).parent / "fixtures" / "biz060"
        ctrl_file = fixture_dir / "controller" / "FooController.java"

        endpoints = collect_endpoints(ctrl_file, root_dir=fixture_dir)
        assert len(endpoints) == 4

        # 1. GET /api/v1/foo/bars
        e_get = endpoints[0]
        assert e_get["method"] == "GET"
        assert e_get["path"] == "/api/v1/foo/bars"
        assert e_get["query_str"] == "personId?, baseDate"
        assert e_get["body_str"] == "—"
        assert e_get["service"] == "FooService.search"
        assert "회사" in e_get["guards"] and "본인" in e_get["guards"]

        # 2. PUT /api/v1/foo/bars/{id}/time
        e_put_time = endpoints[1]
        assert e_put_time["method"] == "PUT"
        assert e_put_time["path"] == "/api/v1/foo/bars/{id}/time"
        assert e_put_time["query_str"] == "—"
        assert e_put_time["body_str"] == "FooReq{ids(List<Long>), checkIn(LocalDate), checkInStr}"
        assert e_put_time["service"] == "FooService.updateTime"
        assert e_put_time["guards"] == ["회사"]

        # 3. DELETE /api/v1/foo/bars
        e_del = endpoints[2]
        assert e_del["method"] == "DELETE"
        assert e_del["path"] == "/api/v1/foo/bars"
        assert e_del["body_str"] == "List<Long>"
        assert e_del["service"] == "FooService.deleteList"
        assert e_del["guards"] == ["KFS관리자"]

        # 4. PUT /api/v1/foo/bars/{id}/appr
        e_put_appr = endpoints[3]
        assert e_put_appr["method"] == "PUT"
        assert e_put_appr["query_str"] == "apprId"
        assert e_put_appr["body_str"] == "—"
        assert e_put_appr["service"] == "FooService.updateAppr"
        assert e_put_appr["guards"] == ["⚠없음"]

        # Markdown 포맷 검증
        md = format_endpoints_md(endpoints)
        assert "| GET | /api/v1/foo/bars |" in md
        assert "FooReq{ids(List<Long>), checkIn(LocalDate), checkInStr}" in md
        assert "엔드포인트 4개 · 쓰기 3개 · ⚠없음 1개(쓰기 1·조회 0) · 쓰기 중 'KFS관리자' 1 · '본인' 0 · '회사'만 1 ← biz-authz 후보" in md

        # JSON 포맷 키 구조 검증
        j_data = format_endpoints_json(endpoints)
        assert len(j_data) == 4
        assert set(j_data[0].keys()) >= {"method", "path", "query", "body", "service", "guards", "file", "line"}


class TestBizAuthz:
    """수정사항060 #3: biz-authz 권한 훑기 및 판정 테스트."""

    def test_authz_probe_and_judge(self, monkeypatch):
        from yunhee.tools.base import ToolResult
        from yunhee.tools.biz.authz import run_authz

        # 1. request_api 모킹
        def mock_request_api(method, path, **kwargs):
            m = method.upper()
            if m == "GET" and path == "/api/v1/foo/admin":
                return ToolResult(
                    ok=True,
                    data={"summary": "HTTP 200 (0.01s)\nRows: 10\nFields: [id, name]"},
                )
            if m == "GET" and path == "/api/v1/foo/my":
                return ToolResult(
                    ok=True,
                    data={"summary": "HTTP 200 (0.01s)\nRows: 2\nFields: [id, name]"},
                )
            if m == "PUT" and path == "/api/v1/foo/bars/0/time":
                # 빈 본문으로 호출되었는지 검증
                assert kwargs.get("json_body") == {}
                return ToolResult(
                    ok=True,
                    data={"summary": "HTTP 200 (0.01s)\nData: 0"},
                )
            if m == "PUT" and path == "/api/v1/pay/work-times":
                return ToolResult(
                    ok=False,
                    error="HTTP 403 (0.01s)\nError: ACCESS_DENIED",
                    data={"summary": "HTTP 403 (0.01s)\nError: ACCESS_DENIED"},
                )
            return ToolResult(ok=False, error=f"Unhandled: {m} {path}")

        monkeypatch.setattr("yunhee.tools.api_client.request_api", mock_request_api)

        # 2. 가짜 엔드포인트 목록
        fake_endpoints = [
            {
                "method": "GET",
                "path": "/api/v1/foo/admin",
                "query": [],
                "query_str": "—",
                "body": {"type": None, "list": False, "fields": []},
                "body_str": "—",
                "service": "FooService.searchAdmin",
                "guards": ["회사"],
                "guard_str": "회사",
                "file": "FooController.java:10",
                "line": 10,
            },
            {
                "method": "GET",
                "path": "/api/v1/foo/my",
                "query": [],
                "query_str": "—",
                "body": {"type": None, "list": False, "fields": []},
                "body_str": "—",
                "service": "FooService.searchMy",
                "guards": ["회사", "본인"],
                "guard_str": "회사·본인",
                "file": "FooController.java:20",
                "line": 20,
            },
            {
                "method": "PUT",
                "path": "/api/v1/foo/bars/{id}/time",
                "query": [],
                "query_str": "—",
                "body": {"type": "FooReq", "list": False, "fields": []},
                "body_str": "FooReq{...}",
                "service": "FooService.updateTime",
                "guards": ["회사"],
                "guard_str": "회사",
                "file": "FooController.java:30",
                "line": 30,
            },
            {
                "method": "PUT",
                "path": "/api/v1/pay/work-times",
                "query": [],
                "query_str": "—",
                "body": {"type": "List<PayReq>", "list": True, "fields": []},
                "body_str": "List<PayReq>",
                "service": "PayService.save",
                "guards": ["KFS관리자"],
                "guard_str": "KFS관리자",
                "file": "PayController.java:40",
                "line": 40,
            },
            {
                "method": "DELETE",
                "path": "/api/v1/foo/bars",
                "query": [],
                "query_str": "—",
                "body": {"type": "List<Long>", "list": True, "fields": []},
                "body_str": "List<Long>",
                "service": "FooService.deleteList",
                "guards": ["회사"],
                "guard_str": "회사",
                "file": "FooController.java:50",
                "line": 50,
            },
        ]

        # 3. URL -> 메뉴 번호 매핑 및 사원 메뉴 모킹
        # /api/v1/foo/admin -> 메뉴 1002 (관리자 화면, 사원 권한 없음)
        # /api/v1/foo/my -> 메뉴 1001 (사원 화면, 사원 권한 있음)
        url_menus = {
            "/api/v1/foo/admin": {"1002"},
            "/api/v1/foo/my": {"1001"},
        }
        user_menus = {"1001"}

        results = run_authz(
            endpoints=fake_endpoints,
            as_user="401",
            company="kalpa",
            probe_write=True,
            probe_delete=False,
            url_menu_map=url_menus,
            user_menu_set=user_menus,
        )

        # 검증: DELETE는 probe_delete=False 이므로 제외되어 4개 결과
        assert len(results) == 4

        # 1) /api/v1/foo/admin -> 메뉴 1002(미보유)인데 200 반환 -> ⚠ 관리자 화면 자료를 사원이 받음
        r_admin = next(r for r in results if r["path"] == "/api/v1/foo/admin")
        assert "⚠" in r_admin["verdict"]

        # 2) /api/v1/foo/my -> 메뉴 1001(보유)이고 200 반환 -> 본인 자료(정상)
        r_my = next(r for r in results if r["path"] == "/api/v1/foo/my")
        assert "정상" in r_my["verdict"]

        # 3) /api/v1/foo/bars/{id}/time -> 빈 본문 200 -> ⚠ 검사 없이 서비스까지 들어감
        r_time = next(r for r in results if "{id}" in r["path"])
        assert "⚠" in r_time["verdict"]

        # 4) /api/v1/pay/work-times -> 403 ACCESS_DENIED -> 막힘(정상)
        r_pay = next(r for r in results if r["path"] == "/api/v1/pay/work-times")
        assert "막힘(정상)" in r_pay["verdict"]


class TestBizAppr:
    """수정사항060 #4: biz-appr 결재 상신·승인 자동화 테스트."""

    def test_biz_appr_flow_success(self, monkeypatch):
        from yunhee.tools.base import ToolResult
        from yunhee.tools.biz.appr import run_appr

        called_requests = []

        def mock_request_api(method, path, **kwargs):
            called_requests.append((method, path, kwargs))
            m = method.upper()
            if m == "GET" and path == "/api/v1/apr/apprs/new":
                return ToolResult(
                    ok=True,
                    data={"data": {"apprId": 99901, "steps": [{"apprStepId": 88801}]}},
                )
            if m == "GET" and path == "/api/v1/apr/apprs/link-seed":
                return ToolResult(
                    ok=True,
                    data={
                        "data": {
                            "title": "연장근무 신청서",
                            "content": "<p>내용</p>",
                            "effectDate": "2026-11-19T00:00:00",
                            "regDate": "2026-11-12T10:00:00",
                            "signCompany": "kalpa",
                        }
                    },
                )
            if m == "PUT" and path == "/api/v1/apr/apprs/99901":
                # 상신 페이로드 검증
                body = kwargs.get("json_body", {})
                assert body["title"] == "연장근무 신청서"
                assert len(body["steps"]) == 2
                assert body["steps"][0]["stepTypeCode"] == "00"
                assert body["steps"][1]["stepTypeCode"] == "10"
                return ToolResult(ok=True, data={"success": True})
            if m == "PUT" and "/api/v1/att/overtime-reqs/me/12345/appr" in path:
                # A74 쿼리 파라미터 스타일 검증
                params = kwargs.get("params", {})
                assert params.get("apprId") == "99901"
                return ToolResult(ok=True, data={"success": True})
            if m == "POST" and path == "/api/v1/apr/apprs/99901/confirm":
                # 승인 액션 검증
                body = kwargs.get("json_body", {})
                assert body.get("action") == "confirm"
                return ToolResult(ok=True, data={"success": True})
            return ToolResult(ok=True, data={})

        monkeypatch.setattr("yunhee.tools.api_client.request_api", mock_request_api)

        # resolve_user_credentials 모킹
        def mock_resolve(user_or_role, company_code=None, **kwargs):
            if user_or_role == "401":
                return "401", "1111", {"user_id": 40100, "company_id": 100}
            if user_or_role == "301":
                return "301", "1111", {"user_id": 30100, "company_id": 100}
            return user_or_role, "1111", {"user_id": 99999, "company_id": 100}

        monkeypatch.setattr("yunhee.tools.api_client.resolve_user_credentials", mock_resolve)

        # mock class id lookup
        monkeypatch.setattr("yunhee.tools.biz.appr.get_class_tree_id", lambda link_cd, comp_id, db=None: 202611109047109)

        result_lines = run_appr(
            link_code="A74",
            ref_id=12345,
            as_user="401",
            company="kalpa",
            approvers=["301"],
            confirm=True,
        )

        assert any("상신 apprId=99901" in line for line in result_lines)
        assert any("연결 PUT /api/v1/att/overtime-reqs/me/12345/appr" in line for line in result_lines)
        assert any("승인 301 → 30 완료" in line for line in result_lines)

    def test_biz_appr_missing_class_raises(self, monkeypatch):
        from yunhee.tools.biz.appr import run_appr

        monkeypatch.setattr(
            "yunhee.tools.api_client.resolve_user_credentials",
            lambda *args, **kwargs: ("401", "1111", {"user_id": 40100, "company_id": 100}),
        )
        monkeypatch.setattr("yunhee.tools.biz.appr.get_class_tree_id", lambda link_cd, comp_id, db=None: None)

        with pytest.raises(ValueError, match="문서분류지정"):
            run_appr(
                link_code="A74",
                ref_id=12345,
                as_user="401",
                company="kalpa",
                approvers=["301"],
            )

    def test_biz_appr_reject(self, monkeypatch):
        from yunhee.tools.base import ToolResult
        from yunhee.tools.biz.appr import run_appr

        sent_post_bodies = []

        def mock_request_api(method, path, **kwargs):
            m = method.upper()
            if m == "GET" and path == "/api/v1/apr/apprs/new":
                return ToolResult(ok=True, data={"data": {"apprId": 99902, "steps": [{"apprStepId": 88802}]}})
            if m == "GET" and path == "/api/v1/apr/apprs/link-seed":
                return ToolResult(ok=True, data={"data": {"title": "오후근무", "content": "내용"}})
            if m == "PUT" and path == "/api/v1/apr/apprs/99902":
                return ToolResult(ok=True, data={"success": True})
            if m == "PUT" and "/api/v1/att/pm-works/12345/appr" in path:
                return ToolResult(ok=True, data={"success": True})
            if m == "POST" and path == "/api/v1/apr/apprs/99902/confirm":
                sent_post_bodies.append(kwargs.get("json_body", {}))
                return ToolResult(ok=True, data={"success": True})
            return ToolResult(ok=True, data={})

        monkeypatch.setattr("yunhee.tools.api_client.request_api", mock_request_api)
        monkeypatch.setattr(
            "yunhee.tools.api_client.resolve_user_credentials",
            lambda *args, **kwargs: ("402", "1111", {"user_id": 40200, "company_id": 100}),
        )
        monkeypatch.setattr("yunhee.tools.biz.appr.get_class_tree_id", lambda link_cd, comp_id, db=None: 1001)

        result_lines = run_appr(
            link_code="A73",
            ref_id=12345,
            as_user="402",
            company="kalpa",
            approvers=["302"],
            reject="사유 부족",
        )

        assert any("반려 302 → 반려 완료" in line for line in result_lines)
        assert len(sent_post_bodies) == 1
        assert sent_post_bodies[0]["action"] == "reject"
        assert sent_post_bodies[0]["message"] == "사유 부족"


class TestBizPatch:
    """수정사항060 #5: biz-patch 조회 후 수정 저장 테스트."""

    def test_biz_patch_single_object(self, monkeypatch):
        from yunhee.tools.base import ToolResult
        from yunhee.tools.biz.patch import run_patch

        db_state = {"a": "false", "b": 1, "cNm": "x"}
        sent_put_payload = {}

        def mock_request_api(method, path, **kwargs):
            m = method.upper()
            if m == "GET":
                return ToolResult(ok=True, data={"data": dict(db_state)})
            if m == "PUT":
                sent_put_payload.update(kwargs.get("json_body", {}))
                db_state.update(kwargs.get("json_body", {}))
                return ToolResult(ok=True, data={"success": True})
            return ToolResult(ok=False, error="Unhandled")

        monkeypatch.setattr("yunhee.tools.api_client.request_api", mock_request_api)

        lines, warnings = run_patch(
            path="/api/v1/test/obj",
            sets=["a=true", "b=2"],
            drop_suffixes=["Nm"],
            as_user="admin",
            company="kalpa",
        )

        # 1. cNm 제거 확인
        assert "cNm" not in sent_put_payload
        # 2. 원래 타입 유지: 'false'(str) -> 'true'(str), 1(int) -> 2(int)
        assert sent_put_payload["a"] == "true"
        assert sent_put_payload["b"] == 2
        assert any("a: 'false' → 'true'" in line or "a: false → true" in line for line in lines)
        assert len(warnings) == 0

    def test_biz_patch_list_where(self, monkeypatch):
        from yunhee.tools.base import ToolResult
        from yunhee.tools.biz.patch import run_patch

        rows = [
            {"id": 1, "name": "A", "val": 10},
            {"id": 2, "name": "B", "val": 20},
        ]
        sent_body = []

        def mock_request_api(method, path, **kwargs):
            m = method.upper()
            if m == "GET":
                return ToolResult(ok=True, data={"data": list(rows)})
            if m == "PUT":
                sent_body.extend(kwargs.get("json_body", []))
                return ToolResult(ok=True, data={"success": True})
            return ToolResult(ok=False, error="Unhandled")

        monkeypatch.setattr("yunhee.tools.api_client.request_api", mock_request_api)

        # 1. id=2 행 선택 및 수정
        _lines, _ = run_patch(
            path="/api/v1/test/list",
            sets=["val=25"],
            where=["id=2"],
            is_list=True,
            as_user="admin",
            company="kalpa",
        )
        assert len(sent_body) == 1
        assert sent_body[0]["id"] == 2
        assert sent_body[0]["val"] == 25

        # 2. id=999 (0건) -> 오류
        with pytest.raises(ValueError, match="0개"):
            run_patch(
                path="/api/v1/test/list",
                sets=["val=30"],
                where=["id=999"],
                is_list=True,
                as_user="admin",
                company="kalpa",
            )

    def test_biz_patch_wiped_field_warning(self, monkeypatch):
        from yunhee.tools.base import ToolResult
        from yunhee.tools.biz.patch import run_patch

        first_get = True

        def mock_request_api(method, path, **kwargs):
            nonlocal first_get
            m = method.upper()
            if m == "GET":
                if first_get:
                    first_get = False
                    return ToolResult(ok=True, data={"data": {"id": 1, "important": "data", "status": "init"}})
                # 두 번째 GET에서는 important가 지워져서 None이 됨
                return ToolResult(ok=True, data={"data": {"id": 1, "important": None, "status": "updated"}})
            if m == "PUT":
                return ToolResult(ok=True, data={"success": True})
            return ToolResult(ok=False, error="Unhandled")

        monkeypatch.setattr("yunhee.tools.api_client.request_api", mock_request_api)

        _lines, warnings = run_patch(
            path="/api/v1/test/obj",
            sets=["status=updated"],
            as_user="admin",
            company="kalpa",
        )
        assert any("important" in w for w in warnings)


class TestBizCode:
    """수정사항060 #6: biz-code 공통코드 조회 및 유사 추천 테스트."""

    def test_biz_code_found(self, monkeypatch):
        from yunhee.tools.biz.code import format_code_table, get_code_rows

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        def fake_execute(query, params=None):
            q = query.strip()
            if "FROM sys08_code_kind" in q and "sys08_kind_cd = %s" in q:
                mock_cur.fetchone.return_value = {
                    "sys08_code_kind_id": 10,
                    "sys08_kind_cd": "WorkTypeCode",
                    "sys08_kind_nm": "근무형태구분",
                    "sys08_sys_yn": "true",
                }
            elif "FROM sys09_code" in q:
                mock_cur.fetchall.return_value = [
                    {
                        "sys09_company_id": 0,
                        "sys09_code": "10",
                        "sys09_name": "연장근무",
                        "sys09_seq": "001",
                        "sys09_close_yn": "false",
                        "sys09_apply_date": "2020-01-01",
                    },
                    {
                        "sys09_company_id": 0,
                        "sys09_code": "20",
                        "sys09_name": "야간근무",
                        "sys09_seq": "002",
                        "sys09_close_yn": "false",
                        "sys09_apply_date": "2020-01-01",
                    },
                ]

        mock_cur.execute.side_effect = fake_execute
        monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: mock_conn)
        monkeypatch.setattr("yunhee.tools.sql_runner.get_connection_string", lambda *args: "postgresql://fake")

        kind_info, rows, _similar = get_code_rows("WorkTypeCode")
        assert kind_info is not None
        assert len(rows) == 2
        assert rows[0]["sys09_name"] == "연장근무"

        table_str = format_code_table(kind_info, rows)
        assert "| 0(공통) | 10 | 연장근무 |" in table_str
        assert "| 0(공통) | 20 | 야간근무 |" in table_str

    def test_biz_code_not_found_suggests_similar(self, monkeypatch):
        from yunhee.tools.biz.code import get_code_rows

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        def fake_execute(query, params=None):
            q = query.strip()
            if "sys08_kind_cd = %s" in q:
                mock_cur.fetchone.return_value = None
            elif "ILIKE" in q:
                mock_cur.fetchall.return_value = [
                    {"sys08_kind_cd": "PaymentMethodCode", "sys08_kind_nm": "지급방법"},
                    {"sys08_kind_cd": "PayTypeCode", "sys08_kind_nm": "급여유형"},
                ]

        mock_cur.execute.side_effect = fake_execute
        monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: mock_conn)
        monkeypatch.setattr("yunhee.tools.sql_runner.get_connection_string", lambda *args: "postgresql://fake")

        kind_info, _rows, similar = get_code_rows("PaymentTypeCode")
        assert kind_info is None
        assert len(similar) == 2
        assert "PaymentMethodCode" in similar


class TestBizDbWrite:
    """수정사항060 #7: biz-db-write 로컬 DB 안전 쓰기 및 트랜잭션 롤백 테스트."""

    def test_safety_check_connection(self, monkeypatch):
        from yunhee.tools.biz.dbwrite import check_db_write_allowed

        monkeypatch.setenv("YUNHEE_DB_WRITE", "1")
        # localhost + asseterpdb -> 허용
        assert check_db_write_allowed("postgresql://user:pass@localhost:5432/asseterpdb") is True
        assert check_db_write_allowed("postgresql://user:pass@127.0.0.1:5432/asseterpdb") is True

        # 원격 호스트 -> 거절
        with pytest.raises(ValueError, match="원격"):
            check_db_write_allowed("postgresql://user:pass@10.0.0.5:5432/asseterpdb")

        # 다른 DB -> 거절
        with pytest.raises(ValueError, match="허용되지 않은 DB"):
            check_db_write_allowed("postgresql://user:pass@localhost:5432/otherdb")

        # YUNHEE_DB_WRITE 꺼짐 -> 거절
        monkeypatch.delenv("YUNHEE_DB_WRITE", raising=False)
        with pytest.raises(ValueError, match="YUNHEE_DB_WRITE"):
            check_db_write_allowed("postgresql://user:pass@localhost:5432/asseterpdb")

    def test_guard_write_statement(self):
        from yunhee.tools.biz.dbwrite import guard_write_statement

        # 정상 문장
        guard_write_statement("UPDATE table SET a=1 WHERE id=1;")
        guard_write_statement("DELETE FROM table WHERE id=1;")
        guard_write_statement("INSERT INTO table (id) VALUES (1);")

        # WHERE 없는 DELETE / UPDATE -> 거절
        with pytest.raises(ValueError, match="WHERE"):
            guard_write_statement("DELETE FROM table;")
        with pytest.raises(ValueError, match="WHERE"):
            guard_write_statement("UPDATE table SET a=1;")

        # DDL 문장 -> 거절
        with pytest.raises(ValueError, match="DDL"):
            guard_write_statement("DROP TABLE table;")
        with pytest.raises(ValueError, match="DDL"):
            guard_write_statement("TRUNCATE TABLE table;")

        # allow_ddl=True 면 통과
        guard_write_statement("DROP TABLE table;", allow_ddl=True)

    def test_backup_failure_aborts(self, monkeypatch):
        from unittest.mock import MagicMock

        from yunhee.tools.biz.dbwrite import execute_db_write

        monkeypatch.setenv("YUNHEE_DB_WRITE", "1")
        monkeypatch.setattr("yunhee.tools.sql_runner.get_connection_string", lambda *args: "postgresql://localhost/asseterpdb")

        mock_sub = MagicMock()
        mock_sub.return_value.returncode = 1
        mock_sub.return_value.stderr = "Backup failed"
        monkeypatch.setattr("subprocess.run", mock_sub)

        with pytest.raises(ValueError, match="백업"):
            execute_db_write(sql_text="UPDATE t SET a=1 WHERE id=1;", no_backup=False)

    def test_multi_statement_rollback_on_error(self, monkeypatch):
        from yunhee.tools.biz.dbwrite import execute_db_write

        monkeypatch.setenv("YUNHEE_DB_WRITE", "1")
        monkeypatch.setattr("yunhee.tools.sql_runner.get_connection_string", lambda *args: "postgresql://localhost/asseterpdb")

        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_conn.__enter__.return_value = mock_conn
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur

        def fake_execute(query, params=None):
            if "FAIL" in query:
                raise RuntimeError("DB Error on statement 2")

        mock_cur.execute.side_effect = fake_execute
        monkeypatch.setattr("psycopg.connect", lambda *args, **kwargs: mock_conn)

        sql_script = "UPDATE t SET a=1 WHERE id=1;\nUPDATE t SET a=FAIL WHERE id=2;"
        with pytest.raises(RuntimeError, match="DB Error"):
            execute_db_write(sql_text=sql_script, no_backup=True)

        # 롤백 호출 확인
        assert mock_conn.rollback.called
        assert not mock_conn.commit.called


class TestBizEventNew:
    """수정사항060 #8: biz-event-new 단위 테스트."""

    def test_generate_biz_event_doc_snapshot(self, monkeypatch, tmp_path):
        import shutil

        from yunhee.tools.biz.eventdoc import generate_biz_event_doc

        fixture_dir = Path(__file__).parent / "fixtures" / "biz060"
        # tmp_path로 fixture 복사
        root_dir = tmp_path / "project"
        shutil.copytree(fixture_dir, root_dir)

        # company menu 모킹 (1489는 없음)
        monkeypatch.setattr(
            "yunhee.tools.biz.eventdoc._check_company_menus",
            lambda comp, nos, db=None: set(),
        )

        out_path, content = generate_biz_event_doc(
            event_id="PAY-BZ-9999",
            screens=["1489"],
            title="시험",
            company="kalpa",
            force=False,
            root_dir=root_dir,
        )

        assert out_path.exists()
        assert out_path.name == "PAY-BZ-9999-시험.md"

        # 메뉴 줄 확인
        assert "#1489 기초자료 > 30. 자산&경영 > 근로시간기준관리 (kalpa 메뉴 없음)" in content

        # 따라 하기 확인
        assert "| 1 | TODO | #1489 | [조회] | TODO |" in content
        assert "| 2 | TODO | #1489 | [등록] | TODO |" in content
        assert "| 3 | TODO | #1489 | [저장] | TODO |" in content
        assert "| 4 | TODO | #1489 | [삭제] (확인창 [예]) | TODO |" in content

        # DB 테이블 확인
        assert "| `pay34_work_time_config` | TODO | TODO |" in content

        # yaml 확인
        assert "api: GET /api/v1/pay/work-times" in content
        assert "api: PUT /api/v1/pay/work-times" in content
        assert "api: DELETE /api/v1/pay/work-times" in content

        # 근거 절 확인
        assert "Pay34_Tab_WorkTimeConfig(E0~E5" in content
        assert "PayWorkTimeController" in content
        assert "Pay34_Tab_WorkTimeConfig.tsx" in content

    def test_generate_biz_event_file_exists_raises(self, monkeypatch, tmp_path):
        from yunhee.tools.biz.eventdoc import generate_biz_event_doc

        fixture_dir = Path(__file__).parent / "fixtures" / "biz060"
        target_file = tmp_path / "test.md"
        target_file.write_text("existing content", encoding="utf-8")

        monkeypatch.setattr(
            "yunhee.tools.biz.eventdoc._check_company_menus",
            lambda *args, **kwargs: set(),
        )

        with pytest.raises(FileExistsError, match="이미 존재"):
            generate_biz_event_doc(
                event_id="PAY-BZ-9999",
                screens=["1489"],
                out=str(target_file),
                force=False,
                root_dir=fixture_dir,
            )

        # force=True 덮어쓰기 성공
        out_p, content = generate_biz_event_doc(
            event_id="PAY-BZ-9999",
            screens=["1489"],
            out=str(target_file),
            force=True,
            root_dir=fixture_dir,
        )
        assert out_p == target_file
        assert "PAY-BZ-9999" in content







