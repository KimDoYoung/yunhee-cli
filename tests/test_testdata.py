"""test-insert-data 및 test-rollback-data 단위 테스트."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.biz.testdata import (
    ColumnMeta,
    LoginContext,
    TableMeta,
    ensure_local_db_write_safe,
    filter_candidate_tables,
    insert_test_data,
    list_test_transactions,
    parse_login_spec,
    pseudonymize_identifier,
    pseudonymize_numeric,
    pseudonymize_text,
    rollback_test_data,
    synthesize_table_rows,
)

runner = CliRunner()


def test_parse_login_spec() -> None:
    assert parse_login_spec("kfstest-121-1111") == ("kfstest", "121", "1111")
    assert parse_login_spec("kfstest/121/1111") == ("kfstest", "121", "1111")
    assert parse_login_spec("login=kfstest-121-1111") == ("kfstest", "121", "1111")
    assert parse_login_spec("kalpa-401") == ("kalpa", "401", None)

    with pytest.raises(ValueError, match="로그인 인자 형식"):
        parse_login_spec("invalid_single_token")


def test_ensure_local_db_write_safe() -> None:
    ensure_local_db_write_safe("postgresql://postgres:pw@localhost:5432/asseterpdb")
    ensure_local_db_write_safe("postgresql://postgres:pw@127.0.0.1:5432/asseterpdb")

    with pytest.raises(ValueError, match="원격 DB"):
        ensure_local_db_write_safe("postgresql://postgres:pw@192.168.1.50:5432/asseterpdb")


def test_filter_candidate_tables() -> None:
    raw = [
        "sys01_company",
        "sys09_code",
        "emp01_person",
        "org01_org_code",
        "ast02_asset_dtl",
        "ast01_asset",
        "fnd01_fund",
    ]
    filtered = filter_candidate_tables(raw, screen_name="Ast01_Tab_AssetList")
    # sys01_company, sys09_code, emp01_person, org01_org_code는 제외되고 ast01_asset이 1순위로 정렬되어야 함
    assert filtered == ["ast01_asset", "ast02_asset_dtl", "fnd01_fund"]

    # 인사(emp) 화면인 경우에는 emp01_person이 제외되지 않아야 함
    emp_filtered = filter_candidate_tables(["sys01_company", "emp01_person"], screen_name="Emp01_Tab_Person")
    assert emp_filtered == ["emp01_person"]


def test_synthesize_table_rows_clone_and_mutate() -> None:
    meta = TableMeta(
        name="ast01_asset",
        columns=[
            ColumnMeta("ast01_asset_id", "bigint", "int8", None, False, None, is_pk=True),
            ColumnMeta("ast01_company_id", "bigint", "int8", None, False, None),
            ColumnMeta("ast01_emp_id", "bigint", "int8", None, True, None),
            ColumnMeta("ast01_org_id", "bigint", "int8", None, True, None),
            ColumnMeta("ast01_asset_nm", "character varying", "varchar", 50, False, None),
            ColumnMeta("ast01_std_dt", "character varying", "varchar", 8, True, None),
            ColumnMeta("ast01_del_yn", "character varying", "varchar", 1, True, None),
            ColumnMeta("ast01_amt", "numeric", "numeric", None, True, None),
        ],
        pk_cols=["ast01_asset_id"],
    )
    ctx = LoginContext(
        raw="kfstest-121-1111",
        company_cd="kfstest",
        user="121",
        password="1111",
        company_id=1004,
        emp_id=5021,
        emp_no="121",
        emp_nm="홍길동",
        org_id=3012,
        today=date(2026, 11, 17),
    )

    sample_rows = [
        {
            "ast01_asset_id": 100,
            "ast01_company_id": 28000,
            "ast01_emp_id": 999,
            "ast01_org_id": 888,
            "ast01_asset_nm": "기존자산명",
            "ast01_std_dt": "20240101",
            "ast01_del_yn": "Y",
            "ast01_amt": 500000,
        }
    ]

    mock_conn = MagicMock()
    with (
        patch("yunhee.tools.biz.testdata._fetch_sample_rows", return_value=sample_rows),
        patch("yunhee.tools.biz.testdata._allocate_next_numeric_pk", return_value=[900001, 900002]),
    ):
        rows = synthesize_table_rows(
            conn=mock_conn,
            meta=meta,
            ctx=ctx,
            screen_no="1234",
            count=2,
        )

    assert len(rows) == 2
    assert rows[0]["ast01_asset_id"] == 900001
    assert rows[1]["ast01_asset_id"] == 900002
    assert rows[0]["ast01_company_id"] == 1004
    assert rows[0]["ast01_emp_id"] == 5021
    assert rows[0]["ast01_org_id"] == 3012
    # 최근 1개월 이내로 행마다 다르게 분산 (오늘 2026-11-17 기준 -1일, -3일)
    assert rows[0]["ast01_std_dt"] == "20261116"
    assert rows[1]["ast01_std_dt"] == "20261114"
    assert rows[0]["ast01_del_yn"] == "N"
    # 상시 가명화 적용: [TEST-...] 대신 가상임이 명백한 가명으로 살짝 치환
    assert rows[0]["ast01_asset_nm"] == "샘플자산명"
    assert rows[1]["ast01_asset_nm"] == "예시자산명"
    # 금액은 자릿수(6자리)를 유지하면서 깔끔한 라운드 금액으로 변형
    assert rows[0]["ast01_amt"] == 100000
    assert rows[1]["ast01_amt"] == 200000


def test_pseudonymize_text_subtle_replacement() -> None:
    """펀드명·법인명·인명·영문·회사명 포함 텍스트가 구조는 유지하되 확실한 가명으로 치환되는지 검증."""
    # 금융/업무 키워드 앞 고유명사 살짝 바꾸기
    assert (
        pseudonymize_text("엘엔에스전문투자형사모투자신탁 제1호(부동산)_제2종", 0)
        == "샘플전문투자형사모투자신탁 제1호(부동산)_제2종"
    )
    assert (
        pseudonymize_text("엘엔에스전문투자형사모투자신탁 제1호(부동산)_제2종", 1)
        == "예시전문투자형사모투자신탁 제1호(부동산)_제2종"
    )

    # 법인 표기((주), 주식회사) 보존 + 고유명사 교체
    assert pseudonymize_text("(주)미래에셋부동산", 2) == "(주)데모부동산"
    assert pseudonymize_text("주식회사 에이비씨자산운용", 3) == "주식회사 가나다자산운용"

    # DB 실제 고객사명 사전 우선 치환 (중간 등장 포함)
    assert (
        pseudonymize_text("2026년 엘엔에스 정기 리포트", 0, company_names=["엘엔에스"])
        == "2026년 샘플 정기 리포트"
    )

    # 사람 이름 / 영문 명칭 / 일반 문장
    assert pseudonymize_text("김실명", 0, col_name="emp01_emp_nm") == "홍길동"
    assert pseudonymize_text("박실명", 1, col_name="ast01_mngr_nm") == "김샘플"
    assert pseudonymize_text("LNS Global Fund 1", 0, col_name="fnd01_eng_nm") == "Sample Global Fund 1"
    assert pseudonymize_text("강남빌딩 매입 검토", 1, col_name="ast01_title") == "예시빌딩 매입 검토"
    assert pseudonymize_text("신규 거래처 승인 요청", 1, col_name="ast01_title") == "예시 거래처 승인 요청"


def test_pseudonymize_identifier_and_numeric() -> None:
    """식별번호 포맷 유지 더미화 및 금액·수량·비율 변형 검증."""
    assert pseudonymize_identifier("crm01_biz_no", "211-86-12345", 0) == "123-45-00001"
    assert pseudonymize_identifier("crm01_biz_no", "2118612345", 0) == "1234500001"
    assert pseudonymize_identifier("crm01_tel_no", "02-3456-7890", 1) == "02-0000-0002"
    assert pseudonymize_identifier("emp01_hp_no", "010-1234-5678", 0) == "010-0000-0001"
    assert pseudonymize_identifier("emp01_email_addr", "real@company.co.kr", 0) == "sample1@example.com"
    assert pseudonymize_identifier("crm01_acct_no", "110-123-456789", 0) == "100-000-000001"
    assert pseudonymize_identifier("crm01_addr1", "서울시 강남구 테헤란로 999", 0) == "서울특별시 영등포구 샘플로 100"

    assert pseudonymize_numeric("fnd01_eval_amt", 12345670000, 0, "numeric") == 10000000000
    assert pseudonymize_numeric("fnd01_eval_amt", Decimal(0), 0, "numeric") == Decimal(0)
    assert pseudonymize_numeric("ast01_qty", 55, 1, "integer") == 20
    assert pseudonymize_numeric("fnd01_yield_rate", Decimal("7.42"), 0, "numeric") == Decimal("1.5")


def test_synthesize_fk_remap_and_warning() -> None:
    """타 회사 샘플 복제 시 부모 FK가 현재 회사 소속 ID로 재매핑되고, 없으면 경고가 기록되는지 검증."""
    meta = TableMeta(
        name="ast01_asset",
        columns=[
            ColumnMeta("ast01_asset_id", "bigint", "int8", None, False, None, is_pk=True),
            ColumnMeta("ast01_company_id", "bigint", "int8", None, False, None),
            ColumnMeta("ast01_fund_id", "bigint", "int8", None, True, None),
            ColumnMeta("ast01_cust_id", "bigint", "int8", None, True, None),
        ],
        pk_cols=["ast01_asset_id"],
        fk_map={
            "ast01_fund_id": ("fnd01_fund", "fnd01_fund_id"),
            "ast01_cust_id": ("crm01_cust", "crm01_cust_id"),
        },
    )
    ctx = LoginContext(
        raw="kfstest-121-1111",
        company_cd="kfstest",
        user="121",
        password="1111",
        company_id=1004,
        emp_id=5021,
        emp_no="121",
        org_id=3012,
        today=date(2026, 11, 17),
    )
    sample_rows = [
        {"ast01_asset_id": 1, "ast01_company_id": 28000, "ast01_fund_id": 777, "ast01_cust_id": 888}
    ]
    warnings: list[str] = []

    def _fake_lookup(_conn: Any, ptbl: str, _ppk: str, _cid: int, _cache: Any) -> tuple[bool, list[Any]]:
        if ptbl == "fnd01_fund":
            return (True, [555])
        return (True, [])

    with (
        patch("yunhee.tools.biz.testdata._fetch_sample_rows", return_value=sample_rows),
        patch("yunhee.tools.biz.testdata._allocate_next_numeric_pk", return_value=[900001]),
        patch("yunhee.tools.biz.testdata._lookup_company_parent_ids", side_effect=_fake_lookup),
    ):
        rows = synthesize_table_rows(
            conn=MagicMock(),
            meta=meta,
            ctx=ctx,
            screen_no="1234",
            count=1,
            company_names=[],
            warnings=warnings,
        )

    assert rows[0]["ast01_fund_id"] == 555
    assert rows[0]["ast01_cust_id"] == 888
    assert len(warnings) == 1
    assert "crm01_cust" in warnings[0]


def test_insert_and_rollback_cycle(tmp_path: Path) -> None:
    """insert_test_data로 매니페스트가 생성되고 rollback_test_data로 역순 삭제 및 상태 변경이 수행되는지 검증."""
    fake_db_url = "postgresql://postgres:pw@localhost:5432/asseterpdb"

    t_meta = TableMeta(
        name="ast01_asset",
        columns=[
            ColumnMeta("ast01_asset_id", "bigint", "int8", None, False, None, is_pk=True),
            ColumnMeta("ast01_company_id", "bigint", "int8", None, False, None),
            ColumnMeta("ast01_asset_nm", "character varying", "varchar", 50, False, None),
        ],
        pk_cols=["ast01_asset_id"],
    )
    fake_ctx = LoginContext(
        raw="kfstest-121-1111",
        company_cd="kfstest",
        user="121",
        password="1111",
        company_id=1004,
        emp_id=5021,
        emp_no="121",
        org_id=3012,
    )
    fake_screen_info: dict[str, Any] = {
        "screen_no": "1234",
        "screen_name": "Ast01_Tab_AssetList",
        "menu_title": "자산목록",
        "target_tables": ["ast01_asset"],
        "all_candidate_tables": ["ast01_asset"],
        "apis": [],
        "sql_ids": [],
    }

    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_conn.__enter__.return_value = mock_conn
    mock_cur.__enter__.return_value = mock_cur
    mock_conn.cursor.return_value = mock_cur
    mock_cur.fetchone.side_effect = [
        {"ast01_asset_id": Decimal(900001)},
        {"ast01_asset_id": Decimal(900002)},
    ]
    mock_cur.rowcount = 2

    with (
        patch("yunhee.tools.biz.testdata.get_connection_string", return_value=fake_db_url),
        patch("psycopg.connect", return_value=mock_conn),
        patch("yunhee.tools.biz.testdata.resolve_login_context", return_value=fake_ctx),
        patch("yunhee.tools.biz.testdata.analyze_screen_targets", return_value=fake_screen_info),
        patch("yunhee.tools.biz.testdata.inspect_table_meta", return_value=t_meta),
        patch(
            "yunhee.tools.biz.testdata.synthesize_table_rows",
            return_value=[
                {"ast01_asset_id": 900001, "ast01_company_id": 1004, "ast01_asset_nm": "[TEST-1234-1] 자산"},
                {"ast01_asset_id": 900002, "ast01_company_id": 1004, "ast01_asset_nm": "[TEST-1234-2] 자산"},
            ],
        ),
    ):
        ins_res = insert_test_data(
            raw_login="kfstest-121-1111",
            screen_no="1234",
            count=2,
            verify_api=False,
            work_dir=tmp_path,
        )

    assert ins_res.ok is True
    tx_code = ins_res.data["tx_code"]
    assert tx_code.startswith("tx-1234-")

    # 이력 목록 조회 확인
    tx_list = list_test_transactions(work_dir=tmp_path)
    assert len(tx_list) == 1
    assert tx_list[0]["tx_code"] == tx_code
    assert tx_list[0]["status"] == "ACTIVE"

    # 다른 계정으로 롤백 시도 시 차단 확인
    with patch("yunhee.tools.biz.testdata.get_connection_string", return_value=fake_db_url):
        wrong_res = rollback_test_data(
            raw_login="kalpa-999-1111",
            tx_code=tx_code,
            work_dir=tmp_path,
        )
    assert wrong_res.ok is False
    assert "일치하지 않습니다" in (wrong_res.error or "")

    # 정상 계정으로 롤백 실행
    with (
        patch("yunhee.tools.biz.testdata.get_connection_string", return_value=fake_db_url),
        patch("psycopg.connect", return_value=mock_conn),
        patch("yunhee.tools.biz.testdata._delete_cascade_children", return_value=[]),
    ):
        rb_res = rollback_test_data(
            raw_login="kfstest-121-1111",
            tx_code=tx_code,
            work_dir=tmp_path,
        )

    assert rb_res.ok is True
    tx_after = list_test_transactions(work_dir=tmp_path)
    assert tx_after[0]["status"] == "ROLLED_BACK"
    assert tx_after[0]["rolled_back_at"] is not None


def test_cli_commands(tmp_path: Path) -> None:
    """CLI에서 test-insert-data 및 test-rollback-data 호출 검증."""
    fake_manifest = {
        "tx_code": "tx-1234-20261117-abcd",
        "status": "ACTIVE",
        "screen_no": "1234",
        "screen_name": "Ast01_Tab_AssetList",
        "login": "kfstest-121-1111",
        "company_cd": "kfstest",
        "company_id": 1004,
        "emp_no": "121",
        "emp_id": 5021,
        "org_id": 3012,
        "operations": [
            {
                "seq": 1,
                "table": "ast01_asset",
                "pk_columns": ["ast01_asset_id"],
                "inserted_pks": [[900001], [900002]],
                "row_count": 2,
            }
        ],
    }

    from yunhee.tools.base import ToolResult

    with patch("yunhee.tools.biz.testdata.insert_test_data", return_value=ToolResult(ok=True, data=fake_manifest)):
        r1 = runner.invoke(app, ["test-insert-data", "kfstest-121-1111", "1234"])
        assert r1.exit_code == 0
        assert "tx-1234-20261117-abcd" in r1.stdout
        assert "ast01_asset: 2건 INSERT" in r1.stdout

    fake_rb = {
        "transactions": [
            {
                "tx_code": "tx-1234-20261117-abcd",
                "screen_no": "1234",
                "login": "kfstest-121-1111",
                "status": "ROLLED_BACK",
                "deleted_details": [
                    {"table": "ast01_asset", "deleted_count": 2},
                ],
            }
        ]
    }
    with patch("yunhee.tools.biz.testdata.rollback_test_data", return_value=ToolResult(ok=True, data=fake_rb)):
        r2 = runner.invoke(app, ["test-rollback-data", "kfstest-121-1111", "tx-1234-20261117-abcd"])
        assert r2.exit_code == 0
        assert "롤백 완료: tx-1234-20261117-abcd" in r2.stdout
