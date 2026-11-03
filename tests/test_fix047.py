"""수정사항 047 검증 테스트.

- <foreach> collection 파라미터 바인딩 (-p collection=a,b,c 또는 -p 'collection=[a,b]')
- 요소 타입 판별 (숫자 vs 문자열 리터럴, -p 기존 규칙 승계)
- <foreach> item 변수가 아닌 collection 변수 요구
- mapper-run 및 --rollback 통합 동작
"""

from pathlib import Path

import psycopg
import pytest
from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools.as_is import mapper_runner
from yunhee.tools.as_is.mybatis_render import (
    format_param_value,
    parse_collection_param,
    render_from_xml,
)
from yunhee.tools.sql_runner import get_connection_string

RUNNER = CliRunner()

ACT_MAPPER_PATH = Path("/home/kdy987/work/framework-sprt/AssetERP/backend/src/main/resources/mapper/ActAccountNumMapper.xml")


# ==============================================================================
# (e) 단위 테스트: collection 값 파싱 표 테스트
# ==============================================================================
@pytest.mark.parametrize(
    ("raw_input", "expected"),
    [
        # 단일 숫자
        ("1", ["1"]),
        (1, ["1"]),
        # 쉼표 구분 숫자
        ("1,2", ["1", "2"]),
        ("1, 2, 3", ["1", "2", "3"]),
        # 대괄호 배열 형태
        ("[1,2]", ["1", "2"]),
        ("[ 1 , 2 ]", ["1", "2"]),
        ("[1]", ["1"]),
        # 문자열
        ("a,b", ["a", "b"]),
        ("a, b", ["a", "b"]),
        ("['a', 'b']", ["a", "b"]),
        ('["foo", "bar"]', ["foo", "bar"]),
        # 빈 값
        ("", []),
        ("   ", []),
        (None, []),
        ("[]", []),
        ("[  ]", []),
        # 공백 및 혼합
        (" 1 , 2 ", ["1", "2"]),
        ("[1], [2]", ["1", "2"]),
        (", 1 , , 2 , ", ["1", "2"]),
        # Python 리스트/튜플
        ([1, 2], ["1", "2"]),
        (["a", "b"], ["a", "b"]),
        ([], []),
    ],
)
def test_parse_collection_param_table(raw_input, expected):
    assert parse_collection_param(raw_input) == expected


def test_format_param_value():
    # 1. 숫자형 추정 변수명 (Id, Seq 등)
    assert format_param_value("accountNumId", "123") == "123"
    assert format_param_value("seq", 456) == "456"

    # 2. 문자열형 추정 변수명 (Name, Code 등)
    assert format_param_value("roleName", "123") == "'123'"
    assert format_param_value("code", "01") == "'01'"

    # 3. 일반적인 item 변수명
    assert format_param_value("item", "123") == "123"
    assert format_param_value("item", "abc") == "'abc'"
    assert format_param_value("item", "01") == "'01'"  # 0으로 시작하는 다자리 숫자는 문자열 취급

    # 4. 명시적 타입 접두사
    assert format_param_value("item", "s:123") == "'123'"
    assert format_param_value("item", "n:123") == "123"
    assert format_param_value("item", "null:") == "NULL"
    assert format_param_value("item", "b:true") == "TRUE"


# ==============================================================================
# MyBatis render_from_xml <foreach> 렌더링 검증
# ==============================================================================
SAMPLE_MAPPER_XML = """<mapper namespace="kr.co.kfs.TestMapper">
    <delete id="deleteItems">
        DELETE FROM test_tbl
         WHERE company_id = #{companyId}
           AND id IN
        <foreach collection="ids" item="id" open="(" separator="," close=")">#{id}</foreach>
    </delete>

    <delete id="deleteCodes">
        DELETE FROM test_tbl
         WHERE code IN
        <foreach collection="codes" item="code" open="(" separator="," close=")">#{code}</foreach>
    </delete>

    <delete id="deleteGenericItem">
        DELETE FROM test_tbl
         WHERE num_id IN
        <foreach collection="numIds" item="item" open="(" separator="," close=")">#{item}</foreach>
    </delete>
</mapper>"""


def test_render_foreach_basic_and_variations():
    # 1. 기본 쉼표 목록
    sql, missing = render_from_xml(
        SAMPLE_MAPPER_XML,
        "deleteItems",
        params={"companyId": 100, "ids": "1,2"},
        mode="params",
    )
    assert missing == []
    assert "WHERE company_id = 100" in sql
    assert "( 1,2 )" in sql

    # 2. 대괄호 문법 [1,2]
    sql, missing = render_from_xml(
        SAMPLE_MAPPER_XML,
        "deleteItems",
        params={"companyId": 100, "ids": "[1,2]"},
        mode="params",
    )
    assert missing == []
    assert "( 1,2 )" in sql

    # 3. (c) 단일 요소 1개
    sql, missing = render_from_xml(
        SAMPLE_MAPPER_XML,
        "deleteItems",
        params={"companyId": 100, "ids": "1"},
        mode="params",
    )
    assert missing == []
    assert "( 1 )" in sql

    # 4. 문자열 요소
    sql, missing = render_from_xml(
        SAMPLE_MAPPER_XML,
        "deleteCodes",
        params={"codes": "A,B"},
        mode="params",
    )
    assert missing == []
    assert "( 'A','B' )" in sql

    # 5. generic item 변수명과 collection 접미사 반영
    sql, missing = render_from_xml(
        SAMPLE_MAPPER_XML,
        "deleteGenericItem",
        params={"numIds": "10,20"},
        mode="params",
    )
    assert missing == []
    assert "( 10,20 )" in sql

    # 6. 빈 컬렉션 -> ( NULL )
    sql, missing = render_from_xml(
        SAMPLE_MAPPER_XML,
        "deleteItems",
        params={"companyId": 100, "ids": ""},
        mode="params",
    )
    assert missing == []
    assert "( NULL )" in sql

    # 7. 필수 컬렉션 누락 시: item 변수(id)가 아닌 collection 변수(ids)를 요구
    sql, missing = render_from_xml(
        SAMPLE_MAPPER_XML,
        "deleteItems",
        params={"companyId": 100},
        mode="params",
    )
    assert "ids" in missing
    assert "id" not in missing


# ==============================================================================
# CLI 및 DB 실제 검증 ((a), (b), (c), (d))
# ==============================================================================
@pytest.mark.skipif(not ACT_MAPPER_PATH.exists(), reason="ActAccountNumMapper.xml 미존재")
def test_mapper_run_act_account_num_verification():
    conn_str = get_connection_string("asseterpdb")
    if not conn_str:
        pytest.skip("asseterpdb DB 접속 정보 없음")

    # (a) 없는 ID 목록 삭제 -> DELETE 0 (롤백됨)
    res_a = mapper_runner.run_mapper_statement(
        f"{ACT_MAPPER_PATH}#deleteAccountNums",
        params={"companyId": "28000", "accountNumIds": "1,2"},
        rollback=True,
    )
    assert res_a.ok is True
    assert "DELETE 0 (롤백됨)" in res_a.data["summary"]

    # (c) 요소가 하나(-p accountNumIds=1)
    res_c = mapper_runner.run_mapper_statement(
        f"{ACT_MAPPER_PATH}#deleteAccountNums",
        params={"companyId": "28000", "accountNumIds": "1"},
        rollback=True,
    )
    assert res_c.ok is True
    assert "DELETE 0 (롤백됨)" in res_c.data["summary"]

    # (b) 실제 존재하는 2개 행 삭제 -> DELETE 2 (롤백됨), DB count는 7 유지
    with psycopg.connect(conn_str) as conn, conn.cursor() as cur:
        cur.execute("SELECT act09_account_num_id FROM act09_account_num WHERE act09_company_id = 28000 LIMIT 2")
        ids = [str(r[0]) for r in cur.fetchall()]
        cur.execute("SELECT count(*) FROM act09_account_num")
        before_count = cur.fetchone()[0]

    assert len(ids) == 2, f"테스트 데이터 부족: {ids}"
    id_param = f"{ids[0]},{ids[1]}"

    res_b = mapper_runner.run_mapper_statement(
        f"{ACT_MAPPER_PATH}#deleteAccountNums",
        params={"companyId": "28000", "accountNumIds": id_param},
        rollback=True,
    )
    assert res_b.ok is True
    assert "DELETE 2 (롤백됨)" in res_b.data["summary"]

    # 롤백 후 카운트 확인
    with psycopg.connect(conn_str) as conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM act09_account_num")
        after_count = cur.fetchone()[0]
    assert after_count == before_count

    # (d) 회귀: foreach가 없는 문장의 동작과 --compare 유지
    res_select = mapper_runner.run_mapper_statement(
        f"{ACT_MAPPER_PATH}#selectByRetrieve",
        params={"companyId": "28000"},
        compare_sql="act09_account_num.selectByRetrieve",
    )
    assert res_select.ok is True
    assert "✅" in res_select.data["summary"]
    assert res_select.data["tobe_rows"] == res_select.data["asis_rows"]


def test_mapper_run_cli_repeated_params_and_help():
    # 1. --help 에 안내 확인
    res_help = RUNNER.invoke(cli.app, ["mapper-run", "--help"])
    assert res_help.exit_code == 0
    assert "<foreach>는 -p <collection>=a,b,c로 준다" in res_help.output

    # 2. CLI에서 반복 파라미터 (-p ids=1 -p ids=2) 전달
    if not ACT_MAPPER_PATH.exists():
        return
    res_cli = RUNNER.invoke(
        cli.app,
        [
            "mapper-run",
            f"{ACT_MAPPER_PATH}#deleteAccountNums",
            "-p",
            "companyId=28000",
            "-p",
            "accountNumIds=1",
            "-p",
            "accountNumIds=2",
            "--rollback",
        ],
    )
    assert res_cli.exit_code == 0
    assert "DELETE 0 (롤백됨)" in res_cli.output

    # 3. 파라미터 누락 시 결론 확인
    res_missing = RUNNER.invoke(
        cli.app,
        [
            "mapper-run",
            f"{ACT_MAPPER_PATH}#deleteAccountNums",
            "-p",
            "companyId=28000",
            "--rollback",
        ],
    )
    assert res_missing.exit_code == 1
    assert "❌ 파라미터 부족 (1건): accountNumIds" in res_missing.output
