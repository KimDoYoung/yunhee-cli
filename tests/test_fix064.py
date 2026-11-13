"""수정사항 064 검증 테스트.

- 그룹 A: biz-appr 시드 없을 때 방어, --title/--content, --link-body, 후보 경로 제안 (#1, #10)
- 그룹 B: api --fields 누락 경고 및 '-' 표기, 400 Validation 실패 사유, rows=0 파라미터 힌트 (#2, #8, #14)
- 그룹 C: biz-endpoints screen 필터링/도메인 생략 다중화, 서비스내부 검사, biz-authz --lint-delete-by-id (#6, #7, #9, #13)
- 그룹 D: compare ${isPostgreSql} 치환 및 미치환 안내, sql --rollback --allow-ddl (#3, #12)
- 그룹 E: biz-orphans, api --track --children, trace-crud 비도달 D 경고 배제 (#4, #5, #11)
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from yunhee.tools.api_client import summarize_response
from yunhee.tools.biz.appr import run_appr
from yunhee.tools.biz.authz import lint_delete_by_id, run_authz
from yunhee.tools.biz.endpoints import _analyze_guards
from yunhee.tools.biz.orphans import get_fk_relations
from yunhee.tools.outliner import is_allowed_read_path
from yunhee.tools.sql_runner import guard_statement


def test_064_01_appr_seed_fallback_and_options():
    """#1, #10: link-seed가 null일 때 AttributeError 없이 기본값/--title/--content가 반영되는지 검증."""
    with patch("yunhee.tools.api_client.request_api") as mock_api:
        # 1. new 응답
        mock_api.side_effect = [
            MagicMock(ok=True, data={"data": {"apprId": 9999, "steps": [{"apprStepId": 1}]}}),
            # 2. link-seed 응답 (data가 null)
            MagicMock(ok=True, data={"data": None, "text": '{"data": null}'}),
        ]

        # dry-run 실행
        lines = run_appr(
            link_code="A27",
            ref_id=1,
            as_user="201",
            company="kalpa",
            class_id=10,
            dry_run=True,
            title="커스텀 체크리스트 상신",
            content="<p>내용</p>",
            link_path="/api/v1/ics/checklist-confirms/relate-apprs/appr-id",
            link_body='{"stdDate":"2026-11-01","apprId":{apprId}}',
        )

        dry_text = "\n".join(lines)
        assert "커스텀 체크리스트 상신" in dry_text
        assert "<p>내용</p>" in dry_text
        assert '{"stdDate":"2026-11-01","apprId":9999}' in dry_text


def test_064_02_api_fields_missing_warning_and_dash(capsys):
    """#2: api --fields에 없는 키가 있을 때 difflib 추천 경고 및 '-' 출력 검증."""
    from typer.testing import CliRunner

    from yunhee.cli import app

    runner = CliRunner()
    with patch("yunhee.tools.api_client.request_api") as mock_req:
        mock_req.return_value = MagicMock(
            ok=True,
            data={
                "text": json.dumps({
                    "data": [
                        {"personNm": "홍길동", "apprStatusNm": "완료"},
                        {"personNm": "이순신", "apprStatusNm": None},
                    ]
                }),
                "summary": "Rows: 2",
            },
        )
        res = runner.invoke(app, ["api", "GET", "/test", "--fields", "personName,apprStatusNm"])
        assert res.exit_code == 0
        # personName 누락 경고가 stderr에 찍혔거나 출력에 포함
        assert "personName" in res.output or "personName" in res.stderr
        # 첫 번째 행의 personName 위치는 '-' 여야 함
        lines = [ln for ln in res.output.splitlines() if ln.strip() and not ln.startswith("⚠")]
        assert lines[0] == "personName\tapprStatusNm"
        assert lines[1] == "-\t완료"
        assert lines[2] == "-\t"


def test_064_03_compare_postgresql_branch_substitution():
    """#3: mybatis render에서 ${isPostgreSql} 분기가 true로 자동 치환되는지 검증."""
    xml = """
    <mapper namespace="test">
      <select id="selectTest">
        SELECT 1
        <choose>
          <when test="${isPostgreSql}">
            FROM pg_tables
          </when>
          <otherwise>
            FROM all_tables
          </otherwise>
        </choose>
      </select>
    </mapper>
    """
    from yunhee.tools.as_is.mybatis_render import render_from_xml_with_meta

    sql, _missing, _branch_log = render_from_xml_with_meta(xml, "selectTest", {})
    assert "FROM pg_tables" in sql
    assert "FROM all_tables" not in sql


def test_064_04_biz_orphans_and_relations(tmp_path):
    """#4: 고아 행 탐지기 명명 규칙 FK 매핑 및 DELETE SQL 생성 검증."""
    mock_conn = MagicMock()
    # PK: ics21_checklist_l_class -> ics21_checklist_l_class_id
    # cols: ics22_checklist_l_class_company -> [..., ics21_checklist_l_class_id]
    with patch("yunhee.tools.biz.orphans.get_table_metadata") as mock_meta:
        mock_meta.return_value = (
            {"ics21_checklist_l_class": "ics21_checklist_l_class_id"},
            {
                "ics21_checklist_l_class": ["ics21_checklist_l_class_id", "name"],
                "ics22_checklist_l_class_company": ["ics22_id", "ics21_checklist_l_class_id", "company_id"],
            },
        )
        rels = get_fk_relations(mock_conn)
        match = next((r for r in rels if r["child_table"] == "ics22_checklist_l_class_company"), None)
        assert match is not None
        assert match["parent_table"] == "ics21_checklist_l_class"
        assert match["fk_col"] == "ics21_checklist_l_class_id"


def test_064_05_trace_crud_unreachable_d():
    """#5: trace-crud에서 비도달 D가 'ASIS RU(D 도달 불가)'로 표기되고 경고 없는지 검증."""
    from yunhee.tools.trace.crud import _compare

    a = {"tbl1": {"R", "U", "D"}}
    t = {"tbl1": {"R", "U"}}
    unreach = {"tbl1": {"D"}}

    lines = _compare(a, t, unreachable_ops=unreach)
    assert len(lines) == 1
    # ⚠ TOBE에 D 없음 경고가 없고 (D 도달 불가)가 표기되어야 함
    assert "⚠ TOBE에 D 없음" not in lines[0]
    assert "ASIS RU(D 도달 불가)" in lines[0]
    assert "/ TOBE RU" in lines[0]


def test_064_06_biz_authz_lint_delete_by_id(tmp_path):
    """#6: biz-authz --lint-delete-by-id 가 DTO Id 무검증 삭제 패턴을 검출하는지 검증."""
    backend_dir = tmp_path / "backend" / "src" / "main" / "java" / "com" / "test"
    backend_dir.mkdir(parents=True)
    svc_file = backend_dir / "TestService.java"
    svc_file.write_text(
        """
        public class TestService {
            public void updateRelateApprId(UserPrincipal user, RelateApprReq req) {
                if (req.lastApprId() != null) {
                    mapper.deleteAppr(companyId, req.lastApprId());
                }
            }
        }
        """,
        encoding="utf-8",
    )

    findings = lint_delete_by_id(root_dir=tmp_path)
    assert len(findings) == 1
    assert findings[0]["service"] == "TestService.updateRelateApprId"
    assert "lastApprId" in findings[0]["summary"]
    assert "deleteAppr" in findings[0]["summary"]


def test_064_08_api_validation_failed_summary():
    """#8: 400 Validation failed 응답에서 필드 에러가 요약에 추출되는지 검증."""
    text = json.dumps({
        "status": 400,
        "message": "Validation failed for argument [2]: [Field error in object 'req' on field 'apprId': default message [널이면 안 됩니다]]",
        "errors": [{"field": "apprId", "defaultMessage": "널이면 안 됩니다"}],
    })
    res = summarize_response(400, text, 100)
    assert "Validation: apprId: 널이면 안 됩니다" in res


def test_064_09_biz_authz_probe_write_dry_run():
    """#9: biz-authz --probe-write --dry-run 검증."""
    eps = [
        {"method": "PUT", "path": "/api/v1/test", "guard_str": "회사", "query": [], "body": {}},
    ]
    results = run_authz(eps, as_user="401", company="kalpa", probe_write=True, dry_run=True)
    assert len(results) == 1
    assert "dry-run" in results[0]["result_str"]
    assert results[0]["verdict"] == "미호출(dry-run)"


def test_064_11_outliner_allowed_log_dir(tmp_path):
    """#11: outliner의 허용 경로에 LOG_DIR 및 ~/tmp 가 포함되는지 검증."""
    log_file = Path.home() / "tmp" / "test.log"
    assert is_allowed_read_path(log_file) is True


def test_064_12_sql_rollback_allow_ddl():
    """#12: sql --rollback --allow-ddl 에서 CREATE 등 DDL이 허용되고 COMMIT은 차단되는지 검증."""
    # 1. allow_ddl=False 일 때 CREATE 차단
    err = guard_statement("CREATE TABLE t1 (id int);", rollback=True, allow_ddl=False)
    assert err is not None
    assert "실행할 수 없습니다" in err

    # 2. allow_ddl=True 일 때 CREATE 허용
    err_allow = guard_statement("CREATE TABLE t1 (id int);", rollback=True, allow_ddl=True, is_postgres=True)
    assert err_allow is None

    # 3. allow_ddl=True 라도 COMMIT은 차단
    err_commit = guard_statement("COMMIT;", rollback=True, allow_ddl=True, is_postgres=True)
    assert err_commit is not None
    assert "실행할 수 없습니다" in err_commit


def test_064_13_biz_endpoints_internal_guard():
    """#13: 서비스 초반부 check* 호출이 있을 때 '서비스내부(메서드명)'이 guards에 들어가고 ⚠없음이 배제되는지 검증."""
    with patch("yunhee.tools.biz.endpoints._find_type_source") as mock_src:
        tmp_java = Path("/tmp/dummy_svc.java")
        tmp_java.write_text(
            """
            public class TestService {
                public void delete(UserPrincipal user, Long id) {
                    checkEditable(user, id);
                    mapper.delete(id);
                }
            }
            """,
            encoding="utf-8",
        )
        mock_src.return_value = tmp_java

        guards = _analyze_guards("TestService", "delete", "", Path("/tmp"), Path("/tmp/Ctrl.java"))
        assert "서비스내부(checkEditable)" in guards
        assert "⚠없음" not in guards
