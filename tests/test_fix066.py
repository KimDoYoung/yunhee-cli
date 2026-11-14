"""수정사항 066 검증 테스트.

- #1: biz-appr POST 등 다양한 HTTP 메서드 지원 및 A41, A76, A33, A34 후보 등록
- #2: biz-event-new 다음 의심 번호 정규식 엄격화 및 TSX 연관 API 정밀 매칭
- #3: biz-orphans 접두사 제거 기반 이름 규칙 FK 추정 (biz16_cont_corp_id ↔ biz10_cont_corp_id)
- #4: compare 화면 기본값(%) 필수 파라미터 힌트 추출
- #5: api 커스텀 요청 헤더(-H) 및 --no-login 옵션 지원 (환경변수 치환 포함)
- #6: biz-appr 기본 계정/회사 일관화 및 상신자 비밀번호 출처 안내 출력
- #7: biz-authz 날짜 범위 2000-01-01~2099-12-31 확장 및 0행 시 파라미터 힌트
- #8: mapper-run / compare 빈 값 파라미터 경고 및 0=0 (확인 못 함) 요약 표기
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from yunhee.tools.biz.appr import find_link_path_candidates, run_appr
from yunhee.tools.biz.authz import _make_dummy_param
from yunhee.tools.biz.eventdoc import _extract_tobe_api_calls, _find_next_suspect_number
from yunhee.tools.biz.orphans import _strip_table_prefix, get_fk_relations
from yunhee.tools.comparator import _find_screen_param_hints


def test_066_01_biz_appr_post_method_and_candidates():
    """#1: biz-appr에서 POST 메서드 지원 및 A41, A76, A33, A34 후보 경로 검증."""
    # 1. 후보 경로 등록 검증
    cands_a41 = find_link_path_candidates("A41")
    assert any("cards/appr-link" in c for c in cands_a41)
    cands_a33 = find_link_path_candidates("A33")
    assert any("users" in c for c in cands_a33)

    # 2. --link-path 에 POST가 포함된 경우 dry-run 출력 검증
    with (
        patch("yunhee.tools.api_client.resolve_user_credentials", return_value=("401", "1111", {"company_id": 28000, "user_id": 100, "emp_no": "401", "pw_source": "test"})),
        patch("yunhee.tools.api_client.request_api") as mock_api,
    ):
        mock_api.side_effect = [
            MagicMock(ok=True, data={"data": {"apprId": 8888, "steps": [{"apprStepId": 1}]}}),
            MagicMock(ok=True, data={"data": {"title": "법인카드 신청"}}),
        ]
        lines = run_appr(
            link_code="A41",
            ref_id=10,
            as_user="401",
            company="kalpa",
            class_id=5,
            dry_run=True,
            link_path="POST /api/v1/biz/promos/cards/appr-link",
            link_body='{"cardId":{ref},"apprId":{apprId}}',
        )
        dry_txt = "\n".join(lines)
        assert "연결 POST /api/v1/biz/promos/cards/appr-link" in dry_txt
        assert '{"cardId":10,"apprId":8888}' in dry_txt


def test_066_02_eventdoc_suspect_number_and_api_filter(tmp_path: Path):
    """#2: 의심 번호가 문서 내 메뉴번호(#1510)를 피하고 표 번호(#230 -> #231)로 계산되는지 검증."""
    doc_dir = tmp_path / "docs" / "2-업무분석"
    doc_dir.mkdir(parents=True)
    suspect_file = doc_dir / "보안_및_버그_의심.md"
    suspect_file.write_text(
        """
        # 보안 및 버그 의심 목록

        이 문서는 #1510 메뉴 및 #1402 화면에서 발생한 사항을 기록합니다.

        | 번호 | 등급 | 화면 | 내용 |
        |:---:|:---:|:---|:---|
        | 229 | 중 | #1001 | 일부 권한 누락 |
        | 230 | 상 | #1130 | 관리자 화면 데이터 접근 |

        ### 추가 확인 필요
        - #1406 번호는 메뉴 번호임.
        """,
        encoding="utf-8",
    )
    next_no = _find_next_suspect_number(tmp_path)
    assert next_no == 231  # #1510이나 #1406이 아닌 표의 230 + 1 = 231이어야 함


def test_066_02_eventdoc_popup_api_extraction(tmp_path: Path):
    """#2: 화면 TSX가 import하는 팝업 TSX의 API도 함께 추출되는지 검증."""
    src_dir = tmp_path / "frontend" / "src"
    pages_dir = src_dir / "pages" / "biz"
    components_dir = src_dir / "components" / "biz"
    api_dir = src_dir / "api"
    pages_dir.mkdir(parents=True)
    components_dir.mkdir(parents=True)
    api_dir.mkdir(parents=True)

    # API 정의
    (api_dir / "bizApi.ts").write_text(
        "export const bizApi = {\n"
        "    getLimits: () => apiClient.get('/api/v1/biz/limits'),\n"
        "    saveProvideSetup: (data: any) => apiClient.put('/api/v1/biz/provide-setups', data),\n"
        "    otherUnrelated: () => apiClient.put('/api/v1/biz/fund-price-modis'),\n"
        "};\n",
        encoding="utf-8",
    )

    # 팝업 TSX
    popup_tsx = components_dir / "Biz04_Lookup_EmpSetup.tsx"
    popup_tsx.write_text(
        """
        import { bizApi } from '@/api/bizApi';
        export const Biz04_Lookup_EmpSetup = () => {
            const onSave = () => bizApi.saveProvideSetup({});
            return <div>Popup</div>;
        };
        """,
        encoding="utf-8",
    )

    # 메인 화면 TSX
    main_tsx = pages_dir / "Biz90_Tab_Limit.tsx"
    main_tsx.write_text(
        """
        import { bizApi } from '@/api/bizApi';
        import { Biz04_Lookup_EmpSetup } from '@/components/biz/Biz04_Lookup_EmpSetup';
        export const Biz90_Tab_Limit = () => {
            const load = () => bizApi.getLimits();
            return <Biz04_Lookup_EmpSetup />;
        };
        """,
        encoding="utf-8",
    )

    calls = _extract_tobe_api_calls(main_tsx, root_dir=tmp_path)
    call_urls = [u for m, u in calls]
    assert "/api/v1/biz/limits" in call_urls
    assert "/api/v1/biz/provide-setups" in call_urls
    assert "/api/v1/biz/fund-price-modis" not in call_urls


def test_066_03_biz_orphans_prefix_stripped_fk():
    """#3: 접두사가 다른 컬럼간 어근 일치(biz16_cont_corp_id ↔ biz10_cont_corp_id) FK 추정 검증."""
    assert _strip_table_prefix("biz16_cont_corp_id") == "cont_corp_id"
    assert _strip_table_prefix("biz10_cont_corp_id") == "cont_corp_id"

    mock_conn = MagicMock()
    with patch("yunhee.tools.biz.orphans.get_table_metadata") as mock_meta:
        mock_meta.return_value = (
            # PK 맵
            {
                "biz10_cont_corp": "biz10_cont_corp_id",
                "biz16_each_contract": "biz16_each_contract_id",
            },
            # 컬럼 맵
            {
                "biz10_cont_corp": ["biz10_cont_corp_id", "name"],
                "biz16_each_contract": ["biz16_each_contract_id", "biz16_cont_corp_id", "amount"],
            },
        )
        rels = get_fk_relations(mock_conn, target_table="biz16_each_contract")
        match = next((r for r in rels if r["fk_col"] == "biz16_cont_corp_id"), None)
        assert match is not None
        assert match["parent_table"] == "biz10_cont_corp"
        assert match["parent_pk"] == "biz10_cont_corp_id"
        assert match["inferred"] is True


def test_066_04_compare_param_wildcard_hint(tmp_path: Path):
    """#4: 화면 소스에서 '%' 할당이 있는 경우 필수 파라미터 힌트에 '(화면 기본 "%")'가 붙는지 검증."""
    src_dir = tmp_path / "src" / "myApp" / "client" / "vi" / "biz"
    src_dir.mkdir(parents=True)
    screen_java = src_dir / "Biz01_Tab_Other.java"
    screen_java.write_text(
        """
        public class Biz01_Tab_Other {
            private void retrieve() {
                serviceRequest.add("provideRcvType", "%");
                serviceRequest.add("providePurCode", code + "%");
            }
        }
        """,
        encoding="utf-8",
    )

    hints = _find_screen_param_hints(["provideRcvType", "providePurCode", "otherParam"], "Biz01_Tab_Other", tmp_path)
    assert hints.get("provideRcvType") == '화면 기본 "%"'
    assert hints.get("providePurCode") == '화면: 코드 + "%"'
    assert "otherParam" not in hints


def test_066_05_api_custom_headers_and_no_login():
    """#5: api 호출 시 -H 및 --no-login 동작 검증."""
    from yunhee.tools.api_client import request_api

    with patch("httpx.request") as mock_req, patch.dict("os.environ", {"DEV_KEY": "secret-123"}):
        mock_resp = MagicMock(status_code=200, text='{"success":true,"data":"FUND 작업완료..commit"}', cookies={}, is_success=True)
        mock_req.return_value = mock_resp

        res = request_api(
            method="POST",
            path="/api/v1/batch/icamFund",
            headers={"X-Batch-Api-Key": "$env:DEV_KEY"},
            no_login=True,
        )
        assert res.ok is True
        # httpx 호출 인자 검증
        _args, kwargs = mock_req.call_args
        assert kwargs["headers"].get("X-Batch-Api-Key") == "secret-123"
        assert kwargs["cookies"] == {}


def test_066_06_biz_appr_default_credentials():
    """#6: biz-appr에서 -u, -c 생략 시 기본 계정 및 비밀번호 출처 안내 검증."""
    with (
        patch("yunhee.tools.api_client.resolve_user_credentials", return_value=("admin", "1111", {"company_id": 28000, "user_id": 1, "emp_no": "admin", "pw_source": "test_env"})),
        patch("yunhee.tools.api_client.request_api") as mock_api,
    ):
        mock_api.side_effect = [
            MagicMock(ok=True, data={"data": {"apprId": 7777, "steps": [{"apprStepId": 1}]}}),
            MagicMock(ok=True, data={"data": {"title": "테스트 신청서"}}),
        ]
        lines = run_appr(
            link_code="D01",
            ref_id=1,
            dry_run=True,
        )
        full_text = "\n".join(lines)
        # 상신자 비밀번호 출처 라인이 포함되어야 함
        assert "상신자:" in full_text
        assert "비밀번호 출처" in full_text


def test_066_07_authz_wide_date_range():
    """#7: biz-authz 파라미터 더미 생성 시 시작일과 종료일이 넓은 범위로 생성되는지 검증."""
    start_val = _make_dummy_param("String", "startDate")
    from_val = _make_dummy_param("String", "fromDate")
    close_val = _make_dummy_param("String", "closeDate")
    to_val = _make_dummy_param("String", "toDate")

    assert start_val == "2000-01-01"
    assert from_val == "2000-01-01"
    assert close_val == "2099-12-31"
    assert to_val == "2099-12-31"


def test_066_08_empty_param_warning_and_zero_summary(capsys):
    """#8: compare 및 mapper_runner에서 빈 값 파라미터 경고 및 0=0 요약 표기 검증."""
    from yunhee.tools.comparator import compare_api_sql

    with (
        patch("yunhee.tools.comparator.request_api") as mock_api,
        patch("yunhee.tools.as_is.mybatis_render.get_all_statements", return_value={"test.selectTest": MagicMock(sid="selectTest", key="test.selectTest")}),
        patch("yunhee.tools.as_is.mybatis_render.render_with_meta", return_value=("SELECT 1", [], [])),
        patch("yunhee.tools.comparator.psycopg.connect") as mock_db,
    ):
        # API 0행 응답
        mock_api.return_value = MagicMock(ok=True, data={"data": []})
        # DB SQL 0행 응답
        mock_conn = MagicMock()
        mock_cur = MagicMock()
        mock_cur.fetchall.return_value = []
        mock_cur.description = [("col1",)]
        mock_conn.cursor.return_value.__enter__.return_value = mock_cur
        mock_db.return_value.__enter__.return_value = mock_conn

        res = compare_api_sql(
            method="GET",
            path="/api/test",
            sql_ref="test.selectTest",
            sql_params={"fundType": "", "companyId": "100"},
            no_grid=True,
        )

        assert res.ok is True
        summary = res.data.get("summary", "")
        # 0=0 (확인 못 함 — 조건을 넓혀 보세요) 표기 검증
        assert "0=0 (확인 못 함 — 조건을 넓혀 보세요)" in summary

        # stderr에 빈 값 경고가 찍혔는지 검증
        captured = capsys.readouterr()
        assert "fundType=''" in captured.err
