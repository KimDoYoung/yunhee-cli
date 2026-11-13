"""수정사항 061, 062, 063 통합 검증 테스트 suite."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from yunhee.tools import comparator
from yunhee.tools.base import ToolResult


def test_compare_url_query_params_preserved(monkeypatch):
    """061 #8: compare 호출 시 URL 경로에 있는 쿼리 파라미터가 보존되고 API 호출과 SQL에 연계되는지 검증."""
    called_request = {}

    def mock_request_api(**kwargs):
        called_request.update(kwargs)
        return ToolResult(
            ok=True,
            data={
                "status_code": 200,
                "text": json.dumps({"success": True, "data": [{"id": 1, "name": "test"}]}),
                "user_info": {"user_id": 401, "org_id": 501, "company_id": 10},
            },
        )

    monkeypatch.setattr(comparator, "request_api", mock_request_api)

    with patch("psycopg.connect") as mock_conn:
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [(1, "test")]
        mock_cur.rowcount = 1
        mock_cur.description = [("id",), ("name",)]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        res = comparator.compare_api_sql(
            method="GET",
            path="/api/v1/pay/insure-applies?gubun=1&startDate=2026-01-01&closeDate=2026-01-31",
            sql_ref="sys04_role.selectByName",
            api_params={"extra": "foo"},
            sql_params={"roleName": "test", "companyId": "0"},
            no_grid=True,
        )

        assert res.ok
        # URL 경로는 clean_path로 분리되고 params에 쿼리 파라미터가 포함되어 전달됨
        assert called_request["path"] == "/api/v1/pay/insure-applies"
        assert called_request["params"]["gubun"] == "1"
        assert called_request["params"]["startDate"] == "2026-01-01"
        assert called_request["params"]["closeDate"] == "2026-01-31"
        assert called_request["params"]["extra"] == "foo"
        assert "API params: closeDate=2026-01-31, extra=foo, gubun=1, startDate=2026-01-01" in res.data["summary"]


def test_compare_user_info_mismatch_warning(monkeypatch, capsys):
    """062 #2: 손으로 준 파라미터가 로그인 세션과 다를 때 경고 출력 검증."""
    def mock_request_api(**kwargs):
        return ToolResult(
            ok=True,
            data={
                "status_code": 200,
                "text": json.dumps({"success": True, "data": []}),
                "user_info": {"user_id": 202611109048638, "org_id": 202611109048610, "company_id": 202611109046432},
            },
        )

    monkeypatch.setattr(comparator, "request_api", mock_request_api)

    with patch("psycopg.connect") as mock_conn:
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_cur.rowcount = 0
        mock_cur.description = [("id",)]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        comparator.compare_api_sql(
            method="GET",
            path="/api/v1/test",
            sql_ref="sys04_role.selectByName",
            sql_params={"orgId": "999999999", "companyId": "888888888", "roleName": "test"},
            as_user="301",
            no_grid=True,
        )

        captured = capsys.readouterr()
        assert "⚠ orgId=999999999 (로그인 사원 301의 조직은 202611109048610)" in captured.err
        assert "⚠ companyId=888888888 (로그인 회사는 202611109046432)" in captured.err


def test_compare_zero_val_dynamic_sql_warning(monkeypatch, capsys, tmp_path):
    """062 #1 방안2: 0 전달 시 MyBatis dynamic SQL != null 조건 경고 출력 검증."""
    dummy_mapper = tmp_path / "sys04_role.xml"
    dummy_mapper.write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="sys04_role">
    <select id="selectWithCond">
        SELECT * FROM sys04_role
        <where>
            <if test="trCodeId != null">
                AND tr_code_id = #{trCodeId}
            </if>
        </where>
    </select>
</mapper>
""",
        encoding="utf-8",
    )

    def mock_request_api(**kwargs):
        return ToolResult(
            ok=True,
            data={
                "status_code": 200,
                "text": json.dumps({"success": True, "data": []}),
            },
        )

    monkeypatch.setattr(comparator, "request_api", mock_request_api)

    with patch("psycopg.connect") as mock_conn:
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_cur.rowcount = 0
        mock_cur.description = [("id",)]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cur

        comparator.compare_api_sql(
            method="GET",
            path="/api/v1/test",
            sql_ref="sys04_role.selectWithCond",
            sql_params={"trCodeId": "0"},
            src_root=tmp_path,
            no_grid=True,
        )

        captured = capsys.readouterr()
        assert "⚠ trCodeId=0 전달됨: AS-IS 원본 서버에서 0을 null로 변환하는지 확인하세요" in captured.err


def test_biz_appr_default_link_apis_and_unknown():
    """061 #3, #9: 기본 링크코드 표 확장 및 미등록 링크코드 시 에러 발생 검증."""
    from yunhee.tools.biz.appr import DEFAULT_LINK_APIS, run_appr

    assert "A02" in DEFAULT_LINK_APIS
    assert "A05" in DEFAULT_LINK_APIS
    assert "X01" in DEFAULT_LINK_APIS
    assert "A63" in DEFAULT_LINK_APIS
    assert "A64" in DEFAULT_LINK_APIS
    assert DEFAULT_LINK_APIS["A63"]["style"] == "ids-body"

    with pytest.raises(ValueError, match="링크코드 X99의 연결 API를 모릅니다"):
        run_appr(
            link_code="X99",
            ref_id=10,
            as_user="401",
            company="kalpa",
            approvers=[],
            class_id=1,
            dry_run=True,
        )


def test_biz_appr_multi_ref_and_ids_body(monkeypatch):
    """061 #9: 다중 --ref 및 ids-body 스타일 지원 검증."""
    from yunhee.tools.biz.appr import run_appr

    monkeypatch.setattr(
        "yunhee.tools.api_client.resolve_user_credentials",
        lambda *args, **kwargs: ("401", "1111", {"company_id": 1, "user_id": 401}),
    )

    def mock_request_api(method, path, **kwargs):
        if "/apr/apprs/new" in path:
            return ToolResult(ok=True, data={"data": {"apprId": 7777, "steps": [{"apprStepId": 1}]}})
        if "/apr/apprs/link-seed" in path:
            # seed 호출 시 ids가 파라미터로 전달되었는지 확인
            assert kwargs.get("params", {}).get("ids") == "101,102"
            return ToolResult(ok=True, data={"data": {"title": "지출결의서", "content": "내용"}})
        return ToolResult(ok=True, data={})

    monkeypatch.setattr("yunhee.tools.api_client.request_api", mock_request_api)

    lines = run_appr(
        link_code="A63",
        ref_id="101,102",
        as_user="401",
        company="kalpa",
        approvers=[],
        class_id=99,
        dry_run=True,
    )

    text = "\n".join(lines)
    assert "PUT /api/v1/pay/expenses/appr-id" in text
    assert '"ids": [\n    101,\n    102\n  ]' in text or '"ids": [101, 102]' in text


def test_biz_appr_pre_creation(monkeypatch):
    """061 #4: --pre 사전 생성 호출 및 ref 연계 검증."""
    from yunhee.tools.biz.appr import run_appr

    monkeypatch.setattr(
        "yunhee.tools.api_client.resolve_user_credentials",
        lambda *args, **kwargs: ("401", "1111", {"company_id": 1, "user_id": 401}),
    )

    pre_called = {}

    def mock_request_api(method, path, **kwargs):
        if "/pay/relate-apprs/month" in path:
            pre_called["method"] = method
            pre_called["body"] = kwargs.get("json_body")
            return ToolResult(ok=True, data={"data": 88888})
        if "/apr/apprs/new" in path:
            return ToolResult(ok=True, data={"data": {"apprId": 7777, "steps": [{"apprStepId": 1}]}})
        if "/apr/apprs/link-seed" in path:
            assert kwargs.get("params", {}).get("refId") in ("88888", "999999")
            return ToolResult(ok=True, data={"data": {"title": "급여대장", "content": "내용"}})
        return ToolResult(ok=True, data={})

    monkeypatch.setattr("yunhee.tools.api_client.request_api", mock_request_api)

    lines_dry = run_appr(
        link_code="A02",
        pre='POST /api/v1/pay/relate-apprs/month {"payCode":"01","payDate":"2026-12-24"}',
        as_user="401",
        company="kalpa",
        approvers=[],
        class_id=99,
        dry_run=True,
    )
    assert any("사전 호출(dry-run)" in l for l in lines_dry)

    # 실제 실행 모드
    lines_real = run_appr(
        link_code="A02",
        pre='POST /api/v1/pay/relate-apprs/month {"payCode":"01","payDate":"2026-12-24"}',
        as_user="401",
        company="kalpa",
        approvers=[],
        class_id=99,
        dry_run=False,
    )
    assert pre_called["method"] == "POST"
    assert any("사전 생성 성공: ref=88888" in l for l in lines_real)


def test_sql_runner_silent_write_function_warning(monkeypatch):
    """062 #3: read-only sql 실행 시 쓰기 함수가 NULL을 반환할 때 경고 발생 검증."""
    from yunhee.tools import sql_runner

    with patch("psycopg.connect") as mock_conn:
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = [{"seq": None}]
        mock_col = MagicMock()
        mock_col.name = "seq"
        mock_cur.description = [mock_col]
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cur

        res = sql_runner.run_sql(query="SELECT f_create_seq() as seq", rollback=False)
        assert res.ok
        assert any("⚠ 읽기 전용 실행: nextval/f_create_seq는 실패해 NULL일 수 있음" in w for w in res.data["warnings"])


def test_analysis_function_module(tmp_path):
    """062 #5: analysis function DB 함수 분석 모듈 검증."""
    from yunhee.tools.analysis import function

    funcs_dir = tmp_path / "docs" / "as-is" / "db" / "functions"
    funcs_dir.mkdir(parents=True)
    fn_md = funcs_dir / "f_create_depositbook_run.md"
    fn_md.write_text(
        """# f_create_depositBook_run
```sql
CREATE OR REPLACE FUNCTION f_create_depositBook_run(p_std_date text) RETURNS integer AS $$
BEGIN
    INSERT INTO ast09_book (std_date) VALUES (p_std_date);
    IF p_std_date IS NULL THEN
        RAISE EXCEPTION '일자 오류';
    END IF;
    RETURN 1;
EXCEPTION WHEN OTHERS THEN
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
```
""",
        encoding="utf-8",
    )

    # 1. md 분석
    res_md = function.resolve("f_create_depositBook_run", {"src": tmp_path})
    assert res_md["target"] == "f_create_depositBook_run"
    assert "ast09_book" in res_md["write_tables"]
    assert res_md["has_silent_exception"] is True

    md_output = function.render(res_md, fmt="md")
    assert "ast09_book" in md_output
    assert "EXCEPTION WHEN OTHERS THEN RETURN NULL" in md_output

    # 2. code 출력 및 lines 지원
    code_output = function.render(res_md, fmt="code", opts={"lines": "1-3"})
    assert "1 | CREATE OR REPLACE" in code_output
    assert "3 |     INSERT INTO" in code_output
    assert "RETURN 1" not in code_output


def test_cli_api_get_option(monkeypatch):
    """062 #4: yunhee api --get 옵션으로 단일 텍스트 값 추출 검증."""
    from typer.testing import CliRunner

    from yunhee.cli import app

    def mock_request_api(*args, **kwargs):
        return ToolResult(
            ok=True,
            data={
                "status_code": 200,
                "text": json.dumps({"success": True, "data": {"trId": 202611129141725, "items": [{"id": "item1"}]}}),
            },
        )

    monkeypatch.setattr("yunhee.tools.api_client.request_api", mock_request_api)

    runner = CliRunner()
    res1 = runner.invoke(app, ["api", "GET", "/api/v1/test", "--get", "data.trId"])
    assert res1.exit_code == 0
    assert res1.output.strip() == "202611129141725"

    res2 = runner.invoke(app, ["api", "GET", "/api/v1/test", "--get", "data.items[0].id"])
    assert res2.exit_code == 0
    assert res2.output.strip() == "item1"


def test_biz_endpoints_class_name_and_summary(tmp_path):
    """062 #6: 컨트롤러 클래스명 검색 및 요약의 ⚠없음 건수 표기 검증."""
    from yunhee.tools.biz.endpoints import collect_endpoints, format_endpoints_md

    ctrl_dir = tmp_path / "backend" / "src" / "main" / "java" / "biz" / "ast" / "controller"
    ctrl_dir.mkdir(parents=True)
    ctrl_file = ctrl_dir / "AstRelateApprController.java"
    ctrl_file.write_text(
        """package biz.ast.controller;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/v1/ast/relate-apprs")
public class AstRelateApprController {
    @PutMapping("/{id}/appr-id")
    public void linkAppr(@PathVariable Long id, @RequestBody Object req) {}

    @GetMapping
    public Object list() { return null; }
}
""",
        encoding="utf-8",
    )

    # 클래스명으로 찾기
    eps = collect_endpoints("AstRelateApprController", root_dir=tmp_path)
    assert len(eps) == 2

    # 복수 path 필터 테스트 (063 #5)
    eps_filt = collect_endpoints("AstRelateApprController", path_filter=["appr-id", "nonexistent"], root_dir=tmp_path)
    assert len(eps_filt) == 1
    assert eps_filt[0]["path"] == "/api/v1/ast/relate-apprs/{id}/appr-id"

    md_text = format_endpoints_md(eps)
    assert "⚠없음 2개(쓰기 1·조회 1)" in md_text


def test_biz_authz_reduced_false_positives_and_probe_appr(monkeypatch):
    """061 #5, #6: biz-authz 오판 축소(404 더미ID, 0행) 및 --probe-appr 결재 ID 바꿔치기 검증."""
    from yunhee.tools.biz.authz import format_authz_md, run_authz

    test_endpoints = [
        # 1. 404 DATA_NOT_FOUND (더미 ID) -> 오류가 아닌 자료없음
        {
            "method": "GET",
            "path": "/api/v1/pay/retire-tables/tax-calc",
            "guards": ["회사"],
            "query": [{"name": "monthId", "required": True, "type": "Long"}],
        },
        # 2. 200 rows=0 -> ⚠ 집계에서 제외
        {
            "method": "GET",
            "path": "/api/v1/pay/tax-withholdings",
            "guards": ["회사"],
            "query": [{"name": "stdYear", "required": False, "type": "String"}],
        },
        # 3. KFS 공통 기준표 -> 공통 기준표(참고)
        {
            "method": "GET",
            "path": "/api/v1/pay/tax-calcs",
            "guards": ["KFS관리자"],
            "query": [],
        },
        # 4. 결재 연결 PUT -> --probe-appr 대상
        {
            "method": "PUT",
            "path": "/api/v1/pay/tax-withholdings/{id}/appr-id",
            "guards": ["⚠없음"],
            "query": [],
        },
    ]

    put_called = []

    def mock_request_api(method, path, **kwargs):
        if "retire-tables" in path:
            return ToolResult(ok=False, data={"summary": "HTTP 404 DATA_NOT_FOUND 데이터를 찾을 수 없습니다"})
        if "tax-withholdings" in path and method == "GET":
            # stdYear 파라미터가 자동으로 현재 연도로 채워졌는지 확인 (061 #5)
            assert kwargs.get("params", {}).get("stdYear") is not None
            return ToolResult(ok=True, data={"summary": "200 OK Rows: 0", "data": [{"id": 10, "apprId": 999, "statusCode": 30}]})
        if "tax-calcs" in path:
            return ToolResult(ok=True, data={"summary": "200 OK Rows: 5"})
        if method == "PUT" and "appr-id" in path:
            put_called.append(kwargs.get("json_body"))
            return ToolResult(ok=True, data={"summary": "200 OK"})
        return ToolResult(ok=True, data={})

    monkeypatch.setattr("yunhee.tools.api_client.request_api", mock_request_api)

    results = run_authz(
        endpoints=test_endpoints,
        as_user="401",
        company="kalpa",
        probe_appr=True,
        url_menu_map={},
        user_menu_set={"1001"},
    )

    v_map = {r["path"]: r["verdict"] for r in results}
    assert v_map["/api/v1/pay/retire-tables/tax-calc"] == "자료없음(더미 ID) — 판정 못 함"
    assert v_map["/api/v1/pay/tax-withholdings"] == "⚠?(0행 — 자료 없음)"
    assert v_map["/api/v1/pay/tax-calcs"] == "공통 기준표(참고)"
    assert v_map["/api/v1/pay/tax-withholdings/{id}/appr-id"] == "⚠ 결재 ID 검사 없음"

    # probe_appr로 apprId=1 시도 후 원래 apprId(999)로 복원되었는지 확인 (061 #6)
    assert put_called == [{"apprId": 1}, {"apprId": 999}]

    # ⚠ 카운트에 0행 및 자료없음은 제외되고 1건(결재 ID 검사 없음)만 잡힘
    md = format_authz_md(results, as_user="401")
    assert "⚠ 1건 — 보안_및_버그_의심.md에 적을 후보" in md


def test_biz_event_new_cleaned_steps_and_linked_context(monkeypatch, tmp_path):
    """061 #7, 063 #4: biz-event-new 단계 잡음 제거, 팝업 표기, 관련 이벤트/의심번호 연동, 쓰기 API 표 연동 검증."""
    import shutil

    from yunhee.tools.biz.eventdoc import generate_biz_event_doc

    fixture_dir = Path(__file__).parent / "fixtures" / "biz060"
    root_dir = tmp_path / "project"
    shutil.copytree(fixture_dir, root_dir)

    monkeypatch.setattr(
        "yunhee.tools.biz.eventdoc._check_company_menus",
        lambda comp, nos, db=None: set(),
    )

    # 1. 화면 문서에 잡음 이벤트 및 확인창 추가
    scr_doc = root_dir / "docs" / "as-is" / "src" / "pay" / "screens" / "Pay34_Tab_WorkTimeConfig.md"
    scr_doc.write_text(
        """# Pay34_Tab_WorkTimeConfig
## 이벤트
- [E1] retrieveButton[조회].Select (L76) → retrieve()
- [E2] leaveYText (L80)
- [E3] saveButton[저장].Select (L90) → save()
- [E4] confirmDialog[YES] (L95)
## 서비스
| `pay.Pay34_WorkTimeConfig.delete` | L49 |
## 테이블
[`pay34_work_time_config`]
""",
        encoding="utf-8",
    )

    # 2. 앞선 이벤트 문서 및 의심 문서 추가
    ev_dir = root_dir / "docs" / "2-업무분석" / "biz-event" / "PAY"
    ev_dir.mkdir(parents=True)
    old_ev = ev_dir / "PAY-BZ-0004-급여대장.md"
    old_ev.write_text("# PAY-BZ-0004 급여대장\n메뉴: #1489 근로시간기준설정\n", encoding="utf-8")

    suspect_file = root_dir / "docs" / "2-업무분석" / "보안_및_버그_의심.md"
    suspect_file.write_text("# 보안 및 버그 의심 대장\n- #91 결재 ID 검사 누락\n", encoding="utf-8")

    # 실행
    out_file, content = generate_biz_event_doc(
        event_id="PAY-BZ-0010",
        screens=["1489"],
        title="근로시간기준설정",
        root_dir=root_dir,
        company="kalpa",
    )

    assert out_file.is_file()
    # 1. 비버튼 잡음(leaveYText) 제외, 확인창은 앞 저장 버튼에 결합됨
    assert "leaveYText" not in content
    assert "[저장] (확인창 [예])" in content
    assert "[조회]" in content

    # 2. 관련 이벤트 및 다음 의심 번호 연동
    assert "> 관련 이벤트: PAY-BZ-0004(#1489)" in content
    assert "<!-- 다음 의심 번호: #92 -->" in content

    # 3. 쓰기 API 표 및 biz-authz 연동
    assert "### 화면 쓰기 API 및 권한 검사 현황" in content
    assert "/api/v1/pay/work-times" in content
    assert "yunhee biz-authz pay --path work-times" in content





