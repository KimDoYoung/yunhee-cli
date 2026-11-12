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
        assert "엔드포인트 4개 · 쓰기 3개 · 쓰기 중 'KFS관리자' 1 · '본인' 0 · '회사'만 1 ← biz-authz 후보" in md

        # JSON 포맷 키 구조 검증
        j_data = format_endpoints_json(endpoints)
        assert len(j_data) == 4
        assert set(j_data[0].keys()) >= {"method", "path", "query", "body", "service", "guards", "file", "line"}

