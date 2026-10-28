"""trace-diff: SQL 정규화 diff, 분기 대응표, UI 대응표."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.trace.branch import Cond
from yunhee.tools.trace.diff import (
    _norm_name,
    _pair_conditions,
    _split_and,
    _tokens,
    _ui_compare,
    compare_sql,
    trace_diff,
)
from yunhee.tools.trace.pair import asis_statements, tobe_statements
from yunhee.tools.trace.screen import parse_screen_doc
from yunhee.tools.trace.tobe import build_index

runner = CliRunner()
ASIS_KEY = "emp00_trans_info.selectByText"


def test_norm_name_and_tokens():
    assert _norm_name("isSeparateAddTitle") == _norm_name("separateAddTitle") == "separateaddtitle"
    assert _norm_name("emp_Kor_Nm") == "empkornm" and _norm_name("is") == "is"
    assert _tokens("isSeparateAddTitle == true") == _tokens("separateAddTitle == true")


def test_split_and_respects_parens_and_strings():
    assert _split_and("a = 1 AND (b = 2 AND c = 3) AND d = 'x AND y'") == ["a = 1", "(b = 2 and c = 3)", "d = 'x and y'"]


def test_pair_conditions_by_same_identifiers():
    a = [Cond(1, "if", "isSeparateAddTitle == true"), Cond(2, "if", "onlyAsis != null")]
    t = [Cond(5, "if", "separateAddTitle == true"), Cond(6, "if", "onlyTobe != null")]
    pairs, a_only, t_only = _pair_conditions(a, t)
    assert [(x.line, y.line) for x, y in pairs] == [(1, 5)]
    assert [c.line for c in a_only] == [2] and [c.line for c in t_only] == [6]


def test_compare_sql_reports_structural_differences(world):
    idx = build_index(str(world.tobe))
    lines = compare_sql(ASIS_KEY, asis_statements(world.ctx), "x.EmpTransInfoMapper.searchTransInfos", tobe_statements(idx))
    text = "\n".join(lines)
    assert "테이블: ASIS만 [emp02_others, emp09_etc] / TOBE만 []" in text
    assert "사용 컬럼:" in text and "emp02_others.emp02_note" in text  # ASIS만 쓰는 컬럼(TOBE는 SELECT 목록을 줄였다)
    assert "WHERE 조건: ASIS만" in text and "exists" in text  # 권한·존재 조건이 TOBE에 없다
    assert "정규화 SQL: 다름" in text


def test_compare_sql_identical_statements(world):
    a = asis_statements(world.ctx)
    lines = compare_sql("emp02_others.insert", a, "emp02_others.insert", a)
    assert lines[0] == "  차이 없음" and "정규화 SQL: 동일" in "\n".join(lines)


def test_diff_sql_for_mapper_id(world):
    res = trace_diff(ASIS_KEY, world.ctx, world.tobe, sql=True)
    text = "\n".join(res.facts)
    assert "SQL 정규화 diff(1쌍)" in text and "EmpTransInfoMapper.searchTransInfos [근거: 문장 주석의 AS-IS id]" in text
    assert res.params["kind"] == "mapper"


def test_diff_mapper_without_tobe_counterpart(world):
    res = trace_diff("emp09_etc.selectAll", world.ctx, world.tobe, sql=True)
    assert any("짝 없음" in f for f in res.facts)


def test_diff_branch_for_mapper(world):
    res = trace_diff(ASIS_KEY, world.ctx, world.tobe, branch=True)
    text = "\n".join(res.facts)
    assert "ASIS 2 / TOBE 1 — 대응 1, ASIS만 1, TOBE만 0" in text
    assert "isSeparateAddTitle == true" in text and "separateAddTitle == true" in text and "[근거: 같은 식별자" in text
    assert "ASIS만: L" in text and "searchText != null" in text


def test_ui_compare_matches_by_label(world):
    doc = parse_screen_doc("Emp00_Tab_TransInfo", (world.index / "emp/screens/Emp00_Tab_TransInfo.md").read_text())
    tsx = build_index(str(world.tobe)).tsx["Emp00_Tab_TransInfo"]
    text = "\n".join(_ui_compare("Emp00_Tab_TransInfo", doc.ui["Emp00_Tab_TransInfo"], tsx))
    assert "그리드 열: ASIS 3 / TOBE 3 — 같은 라벨 2 [근거: 라벨 일치]" in text
    assert "필드 이름이 바뀜(1): 성명(empKorName→korNm)" in text
    assert "ASIS에만: 구분(oldCol)" in text and "TOBE에만: 신규(newCol)" in text
    assert "버튼: ASIS 2 / TOBE 2 — 같은 라벨 2" in text
    assert "이벤트: ASIS 4 — 구현 표시 2, 생략 표시 0, 도달 불가 1, 표시 없음 1 [E2]" in text


def test_diff_screen_defaults_to_all_three(world):
    res = trace_diff("#1029", world.ctx, world.tobe)
    assert res.params["sql"] and res.params["branch"] and res.params["ui"]
    text = "\n".join(res.facts)
    assert "SQL 정규화 diff" in text and "화면 분기 대응 Emp00_Tab_TransInfo" in text and "UI 대응표(1개 클래스)" in text
    assert any("TOBE 버튼은" in u for u in res.unresolved)


def test_diff_ui_is_skipped_for_mapper_target(world):
    res = trace_diff(ASIS_KEY, world.ctx, world.tobe, ui=True)
    assert any("--ui는 화면 대상에서만" in u for u in res.unresolved)


def test_cli_trace_diff(world):
    args = ["--tobe", str(world.tobe), "--src", str(world.src), "--src-index", str(world.index)]
    out = runner.invoke(app, ["trace-diff", ASIS_KEY, "--sql", "-o", "json", *args])
    assert out.exit_code == 0
    data = json.loads(out.output[out.output.index("{"):])
    assert data["params"]["sql"] is True and data["params"]["branch"] is False and data["facts"]
    assert runner.invoke(app, ["trace-diff", "Nope_X", *args]).exit_code == 1


@pytest.mark.parametrize("flag", ["--sql", "--branch", "--ui"])
def test_cli_flags_are_accepted(world, flag):
    args = ["--tobe", str(world.tobe), "--src", str(world.src), "--src-index", str(world.index)]
    assert runner.invoke(app, ["trace-diff", "#1029", flag, *args]).exit_code == 0
