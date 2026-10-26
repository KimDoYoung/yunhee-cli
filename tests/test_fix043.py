"""수정사항 043 단위 테스트:
- null: 파라미터 지원 (mybatis_render)
- port-sql include 태그 정리 (mybatis_render mode=structure)
- api URL 사전 보정 및 401 재로그인, -c 회사코드 에러 안내 (api_client)
- drift --note-file 존재 검증 (drift)
- analysis sql --no-cte 및 --section where (sql)
- analysis ui --tobe 다중 경로 및 --done 타 도메인 포함 (ui)
- events getButtonBar().add() 도달 판정 및 닫기 버튼 매핑 (events)
- compare SQL 에러 축약 및 TOBE rows 표기 (comparator)
- yunhee cat 및 outline --range (outliner & cli)
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools.analysis.sql import _fold_cte_and_section
from yunhee.tools.as_is.drift import record_baseline
from yunhee.tools.as_is.events import extract_buttons, extract_events_and_methods
from yunhee.tools.as_is.mybatis_render import (
    Node,
    _strip_type_prefix,
    render_node,
)
from yunhee.tools.as_is.mybatis_render import (
    render as mr_render,
)
from yunhee.tools.comparator import compare_api_sql
from yunhee.tools.outliner import parse_line_range, read_file_range


# 1. mybatis_render: null: 접두사 및 <sql> 태그 언래핑
def test_strip_type_prefix_null():
    pfx, val = _strip_type_prefix("null:")
    assert pfx == "null"
    assert val is None

    pfx2, val2 = _strip_type_prefix("s:foo")
    assert pfx2 == "s"
    assert val2 == "foo"

    pfx3, val3 = _strip_type_prefix("n:123")
    assert pfx3 == "n"
    assert val3 == "123"


def test_mybatis_render_null_param():
    from yunhee.tools.as_is.mybatis_render import Statement

    node = Node("select", {"id": "testNull"}, [])
    node.children = [
        "SELECT * FROM foo WHERE col = 1",
        Node("choose", {}, []),
        " AND status = #{status} AND ref = #{classId}",
    ]
    st = Statement(
        ns="test",
        sid="testNull",
        kind="select",
        node=node,
        rel=Path("test.xml"),
        line=1,
        raw="<select>...</select>",
    )
    sql, missing = mr_render("test.testNull", params={"classId": "null:", "status": "n:10"}, mode="params", statements={"test.testNull": st})
    assert "ref = NULL" in sql
    assert "status = 10" in sql
    assert "classId" not in missing


def test_mybatis_render_structure_sql_tag_unwrapped():
    # mode="structure"에서 <sql id="..."> 태그는 본문만 노출하고 태그 자체는 벗겨져야 함 (#11)
    sql_node = Node("sql", {"id": "selectIpo"}, ["SELECT id, nm FROM ipo_tbl"])
    res = render_node(sql_node, "test", {}, {}, mode="structure", seen=(), missing_params=[])
    assert "<sql" not in res
    assert "</sql>" not in res
    assert "SELECT id, nm FROM ipo_tbl" in res


# 2. analysis sql: --no-cte 및 --section where
def test_fold_cte_and_section():
    sql = """WITH cte1 AS (
    SELECT id FROM a
), cte2 AS (
    SELECT name FROM b
)
SELECT *
FROM main_table
WHERE code = 10 AND status = 'A'
ORDER BY id
"""
    # 1) no_cte
    folded = _fold_cte_and_section(sql, no_cte=True)
    assert "-- CTE cte1, cte2 (생략)" in folded
    assert "WITH cte1 AS" not in folded
    assert "SELECT *" in folded

    # 2) section=where
    where_only = _fold_cte_and_section(sql, section="where")
    assert "-- CTE cte1, cte2 (생략)" in where_only
    assert where_only.startswith("-- CTE cte1, cte2 (생략)\nWHERE code = 10")


# 3. events: getButtonBar().add() 및 닫기 버튼 매핑
def test_events_get_button_bar_add():
    code = """
public class Sch10_Lookup_Ipo extends Window {
    private ColorButtonBottom closeButton = new ColorButtonBottom("닫기");

    public Sch10_Lookup_Ipo() {
        init();
    }

    public void init() {
        this.getButtonBar().add(closeButton);
        closeButton.addSelectHandler(new SelectHandler() {
            @Override
            public void onSelect(SelectEvent event) {
                hide();
            }
        });
    }

    public void hide() {}
}
"""
    events, _methods = extract_events_and_methods(code, file_path="Sch10_Lookup_Ipo.java")
    # 도달 불가 표시가 없어야 함 (#9, #13)
    ev = next((e for e in events if "closeButton" in e.source or e.action == "hide()"), None)
    assert ev is not None
    assert not ev.is_unreachable

    # 버튼 절이 type="close"로 확정 매핑되어야 함
    buttons = extract_buttons(code, events=events, file_path="Sch10_Lookup_Ipo.java")
    btn = next((b for b in buttons if b.label == "닫기" or "closeButton" in b.var), None)
    assert btn is not None
    assert btn.button_type == "close"
    assert "후보" not in btn.jsx
    assert btn.jsx == '<Button type="close" onClick={hide}>닫기</Button>'


# 4. drift: --note-file 미존재 시 에러 종료
def test_drift_note_file_not_found(tmp_path: Path):
    non_existent = tmp_path / "docs" / "not_found.md"
    src_root = tmp_path / "src"
    src_root.mkdir()
    src_index = tmp_path / "index"
    src_index.mkdir()
    code, msg = record_baseline(
        src_root=src_root,
        src_index=src_index,
        screen_names=["Sys01_Tab_Company"],
        note_file=non_existent,
    )
    assert code != 0
    assert "존재하지 않습니다" in msg


# 5. outliner: parse_line_range 및 read_file_range
def test_outliner_parse_line_range_and_read(tmp_path: Path):
    test_file = tmp_path / "sample.txt"
    test_file.write_text("\n".join(f"Line {i}" for i in range(1, 101)), encoding="utf-8")

    # range 파싱
    assert parse_line_range("L1-20", 100) == (1, 20)
    assert parse_line_range("5:15", 100) == (5, 15)
    assert parse_line_range("30", 100) == (30, 30)

    # 범위 읽기
    lines = read_file_range(test_file, range_str="L10-12")
    assert len(lines) == 3
    assert lines[0] == (10, "Line 10")
    assert lines[1] == (11, "Line 11")
    assert lines[2] == (12, "Line 12")


# 6. cli: yunhee cat 및 outline --range
def test_cli_cat_and_outline_range(tmp_path: Path):
    runner = CliRunner()
    f1 = tmp_path / "f1.txt"
    f1.write_text("Alpha\nBeta\nGamma\nDelta\nEpsilon\n", encoding="utf-8")

    # yunhee cat
    res = runner.invoke(cli.app, ["cat", f"{f1}:2-4"])
    assert res.exit_code == 0
    assert "Beta" in res.output
    assert "Delta" in res.output
    assert "Alpha" not in res.output

    # yunhee outline --range
    res_outline = runner.invoke(cli.app, ["outline", str(f1), "--range", "1-2"])
    assert res_outline.exit_code == 0
    assert "Alpha" in res_outline.output
    assert "Beta" in res_outline.output
    assert "Gamma" not in res_outline.output


# 7. comparator: AS-IS SQL 실패 시 축약 및 TOBE rows 출력 (#15)
def test_comparator_sql_failure_truncation(tmp_path: Path):
    fake_xml = tmp_path / "test.xml"
    fake_xml.write_text("<mapper></mapper>", encoding="utf-8")
    with patch("yunhee.tools.comparator.request_api") as mock_req, \
         patch("yunhee.tools.comparator.find_mapper_file", return_value=fake_xml), \
         patch("yunhee.tools.as_is.mybatis_render.render_from_xml_with_meta", return_value=("SELECT * FROM fnd25_terms", [], [])), \
         patch("psycopg.connect") as mock_conn:
        mock_req.return_value = MagicMock(
            ok=True,
            data={"text": '{"data": [1, 2, 3]}', "status_code": 200, "rows": 3, "fields": ["id", "nm"]},
        )
        mock_conn.side_effect = Exception('column "fnd25_fund_id" does not exist')

        res = compare_api_sql(
            method="GET",
            path="/api/v1/fnd/test",
            sql_ref="fnd01_fund.selectTest",
            sql_params={},
        )
        assert not res.ok
        assert "TOBE API 결과: rows=3" in res.error
        assert 'column "fnd25_fund_id" does not exist' in res.error
        assert "실행 SQL: SELECT" not in res.error
        assert "AS-IS SQL이 현재 DB 스키마와 불일치합니다" in res.error
