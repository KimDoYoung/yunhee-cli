"""trace-pair: 근거 있는 ASIS↔TOBE 짝."""

import json

from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.trace.pair import screen_tsx, trace_pair
from yunhee.tools.trace.screen import parse_screen_doc
from yunhee.tools.trace.tobe import build_index

runner = CliRunner()


def test_screen_pair_has_reasons(world):
    res = trace_pair("#1029", world.ctx, world.tobe)
    text = "\n".join(res.facts)
    assert "Emp00_Tab_TransInfo ↔ frontend/src/pages/emp/Emp00_Tab_TransInfo.tsx" in text
    assert "근거: 같은 클래스명; TSX 헤더 AS-IS 일치; 메뉴 번호 일치 #1029" in text


def test_service_api_pairs_use_as_is_comments(world):
    text = "\n".join(trace_pair("Emp00_Tab_TransInfo", world.ctx, world.tobe).facts)
    assert "emp.Emp00_TransInfo.selectByText ↔ GET /api/v1/emp/trans-infos (EmpTransInfoController.searchTransInfos)" in text
    assert "TOBE 호출: Emp00_Tab_TransInfo(empApi.searchTransInfos)" in text
    assert "[근거: 컨트롤러 주석의 AS-IS 서비스 키; api 함수 주석의 AS-IS 서비스 키]" in text or "[근거: 컨트롤러 주석의 AS-IS 서비스 키]" in text
    # ASIS에만 있음 / 근거 없는 TOBE 호출은 따로 낸다
    assert "ASIS에만 있음 — TOBE에 대응 API 없음(2)" in text and "emp.Emp09_Etc.legacy" in text and "emp.Emp00_TransInfo.update" in text


def test_tobe_only_is_not_invented_for_other_screens(world):
    # Emp77_Tab_Brand의 API는 ASIS Emp00 화면의 서비스와 무관하고, Emp00의 TSX가 부르지도 않으므로 TOBE만 항목에 나오지 않는다
    text = "\n".join(trace_pair("Emp00_Tab_TransInfo", world.ctx, world.tobe).facts)
    assert "brand" not in text


def test_sql_pair_by_comment_and_skips_common_sql(world):
    text = "\n".join(trace_pair("Emp00_Tab_TransInfo", world.ctx, world.tobe).facts)
    assert "emp00_trans_info.selectByText ↔ EmpTransInfoMapper.searchTransInfos [근거: 문장 주석의 AS-IS id]" in text
    assert "dbConfig.getSeq" not in text  # 채번 같은 공통 SQL은 짝짓기 대상이 아니다


def test_table_comparison(world):
    text = "\n".join(trace_pair("Emp00_Tab_TransInfo", world.ctx, world.tobe).facts)
    assert "테이블 비교: 같음 1 / ASIS만 2 / TOBE만 0" in text
    assert "ASIS에만: emp02_others, emp09_etc" in text


def test_pair_basis_weak_by_tables_only_when_unique_and_equal(world):
    from yunhee.tools.trace.pair import pair_sql, tobe_statements

    idx = build_index(str(world.tobe))
    t_stmts = tobe_statements(idx)
    for st in idx.statements.values():
        st.as_is_ids = []  # 주석 근거를 지운다
    reached = [idx.statements["x.EmpTransInfoMapper.searchTransInfos"]]
    # 테이블 조합이 같고 후보가 하나면 약한 근거로 짝짓는다
    found, basis = pair_sql("any.id", idx, reached, ["emp01_person"], t_stmts)
    assert [s.id for s in found] == ["searchTransInfos"] and "약한 근거" in basis
    # 테이블 조합이 다르면 억지로 짝짓지 않는다
    assert pair_sql("any.id", idx, reached, ["emp01_person", "emp02_others"], t_stmts) == ([], "")
    # 후보가 둘 이상이면 모호하므로 짝짓지 않는다
    both = [*reached, idx.statements["x.EmpTransInfoMapper.untracked"]]
    assert pair_sql("any.id", idx, both, ["emp01_person"], t_stmts) == ([], "")


def test_statement_outside_chain_is_flagged(world):
    from yunhee.tools.trace.pair import pair_sql, tobe_statements

    idx = build_index(str(world.tobe))
    other = idx.statements["x.EmpTransInfoMapper.untracked"]
    other.as_is_ids = ["emp02_others.insert"]
    found, basis = pair_sql("emp02_others.insert", idx, [idx.statements["x.EmpTransInfoMapper.searchTransInfos"]], None, tobe_statements(idx))
    assert [s.id for s in found] == ["untracked"] and "체인 밖" in basis


def test_renamed_tsx_is_found_by_header(world):
    idx = build_index(str(world.tobe))
    doc = parse_screen_doc("Emp09_Tab_Legacy", "---\nsource_commit: a\n---\n# Emp09_Tab_Legacy\n")
    idx.tsx["Emp88_New"] = type(idx.tsx["Emp77_Tab_Brand"])(**{**idx.tsx["Emp77_Tab_Brand"].__dict__, "name": "Emp88_New", "as_is_file": "myApp/client/vi/emp/Emp09_Tab_Legacy.java"})
    found, notes = screen_tsx(idx, "Emp09_Tab_Legacy", doc)
    assert [t.name for t in found] == ["Emp88_New"] and "TSX 헤더 AS-IS가 이 클래스를 가리킴" in notes[0]


def test_no_tobe_screen_is_reported(world):
    text = "\n".join(trace_pair("Emp09_Tab_Legacy", world.ctx, world.tobe).facts)
    assert "화면 짝: 없음" in text


def test_missing_tobe_tree_is_unresolved(world, tmp_path):
    res = trace_pair("#1029", world.ctx, tmp_path / "nowhere")
    assert res.facts == [] and any("TOBE 소스를 찾지 못함" in u for u in res.unresolved)


def test_cli_trace_pair(world):
    out = runner.invoke(app, ["trace-pair", "#1029", "--tobe", str(world.tobe), "--src", str(world.src), "--src-index", str(world.index), "-o", "json"])
    assert out.exit_code == 0
    data = json.loads(out.output[out.output.index("{"):])
    assert data["command"] == "trace-pair" and data["params"]["resolved"] == "Emp00_Tab_TransInfo" and data["facts"]
    assert runner.invoke(app, ["trace-pair", "Nope_X", "--tobe", str(world.tobe), "--src-index", str(world.index)]).exit_code == 1
