"""묶음 C: trace-dblogic(DB 함수·트리거 본문과 호출처), trace-guide(에이전트 지침)."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.analysis.common import AmbiguousTargetError
from yunhee.tools.base import ToolResult
from yunhee.tools.trace import dblogic as dblogic_mod
from yunhee.tools.trace.dblogic import _body_view, trace_dblogic
from yunhee.tools.trace.guide import GROUPS, registered_commands, trace_guide
from yunhee.tools.trace.render import render
from yunhee.tools.trace.resolve import TargetNotFoundError

runner = CliRunner()

CDNM = (
    "CREATE OR REPLACE FUNCTION public.f_cdnm(av_kind character varying)\n RETURNS character varying\n LANGUAGE plpgsql\nAS $function$\nbegin\n"
    "  SELECT emp01_nm INTO x FROM emp01_person;\n  RETURN f_helper(av_kind);\nend;\n$function$\n"
)
SNAP = {
    "generated_at": "t",
    "tables": [{"name": "emp01_person"}, {"name": "emp02_others"}],
    "routines": [
        {"schema": "public", "name": "f_cdnm", "kind": "function", "arguments": "av_kind character varying", "definition": CDNM, "note": "None"},
        {"schema": "public", "name": "f_helper", "kind": "function", "arguments": "k text", "definition": "CREATE FUNCTION f_helper(k text)\n RETURNS text\n LANGUAGE sql\nAS $$ SELECT f_cdnm(k) $$", "note": "도우미"},
        {"schema": "public", "name": "p_close", "kind": "procedure", "arguments": "", "definition": "CREATE PROCEDURE p_close()\n LANGUAGE plpgsql\nAS $$ begin end $$", "note": "None"},
    ],
    "triggers": [{"schema": "public", "table": "emp01_person", "name": "trg_person", "definition": "CREATE TRIGGER trg_person AFTER UPDATE ON emp01_person FOR EACH ROW EXECUTE FUNCTION f_helper()"}],
}


@pytest.fixture
def dbw(world, monkeypatch):
    monkeypatch.setattr(dblogic_mod, "load_snapshot", lambda env: ToolResult(ok=True, data=SNAP))
    # ASIS mapper가 f_cdnm을 부르게 한다
    (world.src / "server/emp/mapper/emp03.xml").write_text(
        '<mapper namespace="emp03"><select id="named">SELECT f_cdnm(\'a\') AS n FROM emp01_person</select></mapper>', encoding="utf-8")
    from yunhee.tools.trace import sqlscan

    sqlscan.clear_caches()
    monkeypatch.setattr(sqlscan, "snapshot_schema", lambda env: None)
    return world


def _facts(res):
    return "\n".join(res.facts)


def test_body_view_caps_long_definitions():
    view = _body_view("\n".join(f"line{i}" for i in range(200)))
    assert view.count("\n") < 90 and "본문 200줄 중 80줄까지" in view and "line79" in view and "line80" not in view


def test_summary_without_name(dbw):
    text = _facts(trace_dblogic(None, dbw.ctx_for(), dbw.tobe))
    assert "DB 로직: 함수 2, 프로시저 1, 트리거 1" in text
    assert "ASIS SQL에서 가장 많이 호출되는 DB 함수(문장 수): f_cdnm(1)" in text
    assert "ASIS SQL이 호출하지 않는 함수·프로시저 2개" in text and "트리거가 많은 테이블: emp01_person(1)" in text


def test_function_body_tables_calls_and_callers(dbw):
    res = trace_dblogic("F_CDNM", dbw.ctx_for(), dbw.tobe)
    text = _facts(res)
    assert "function f_cdnm(av_kind character varying) RETURNS character varying [plpgsql]" in text
    assert "     5  begin" in text  # 본문에 줄 번호가 붙는다
    assert "본문이 참조하는 테이블(1): emp01_person" in text
    assert "본문이 부르는 다른 DB 함수(1): f_helper" in text
    assert "DB 안에서 이 함수를 부르는 다른 함수(1): f_helper" in text  # 상호 호출
    assert "ASIS SQL 호출처 1개: emp03.named" in text
    assert "TOBE SQL 호출처 0개 (mapper에서 이 함수를 부르는 곳이 없음)" in text
    assert any("JDBC" in u for u in res.unresolved)


def test_function_run_by_trigger_and_trigger_view(dbw):
    assert "이 함수를 실행하는 트리거(1): trg_person(emp01_person)" in _facts(trace_dblogic("f_helper", dbw.ctx_for(), dbw.tobe))
    trg = _facts(trace_dblogic("trg_person", dbw.ctx_for(), dbw.tobe))
    assert "트리거 trg_person — 테이블 emp01_person" in trg and "이 트리거가 실행하는 함수: f_helper" in trg


def test_ambiguous_partial_name_and_unknown(dbw):
    with pytest.raises(AmbiguousTargetError) as exc:
        trace_dblogic("f_", dbw.ctx_for(), dbw.tobe)
    assert exc.value.candidates == ["f_cdnm", "f_helper"]
    assert "procedure p_close()" in _facts(trace_dblogic("close", dbw.ctx_for(), dbw.tobe))  # 부분 이름이 하나뿐이면 그것
    with pytest.raises(TargetNotFoundError):
        trace_dblogic("nope", dbw.ctx_for(), dbw.tobe)


def test_snapshot_missing_is_unresolved(dbw, monkeypatch):
    monkeypatch.setattr(dblogic_mod, "load_snapshot", lambda env: ToolResult(ok=False, error="없음"))
    res = trace_dblogic("f_cdnm", dbw.ctx_for(), dbw.tobe)
    assert res.facts == [] and any("스키마 스냅샷을 읽지 못함" in u for u in res.unresolved)


def test_cli_trace_dblogic(dbw):
    base = ["--tobe", str(dbw.tobe), "--src", str(dbw.src), "--src-index", str(dbw.index)]
    out = runner.invoke(app, ["trace-dblogic", "f_cdnm", "-o", "json", *base])
    assert out.exit_code == 0 and json.loads(out.stdout)["params"]["resolved"] == "f_cdnm"
    assert runner.invoke(app, ["trace-dblogic", "f_", *base]).exit_code == 2
    assert runner.invoke(app, ["trace-dblogic", "nope", *base]).exit_code == 1


# --- trace-guide -----------------------------------------------------------

def test_guide_lists_every_registered_command_from_the_code():
    cmds = registered_commands()
    assert len(cmds) == 18
    text = "\n".join(trace_guide().facts)
    assert "## 4. 명령 (18개)" in text
    for name, desc in cmds.items():
        assert f"`yunhee {name}` — {desc}" in text
    grouped = [n for _, names in GROUPS for n in names]
    assert sorted(grouped) == sorted(cmds)  # 지침의 분류가 등록된 명령과 어긋나지 않는다


def test_guide_documents_contract_and_principles():
    text = "\n".join(trace_guide().facts)
    for needle in ("## facts", "## evidence", "## unresolved", "종료 코드", "trace-rule verify", "개인정보", "읽기 전용", "근거 없이 단정하지 않는다", "--accept"):
        assert needle in text
    assert text.count("\n## ") >= 6  # 출력 읽는 법·준비물·워크플로우·명령·원칙·한계


def test_guide_renders_as_document_and_json():
    md = render(trace_guide(), "md")
    assert md.startswith("# yunhee trace-* 업무파악 지침") and "\n- # " not in md
    assert json.loads(render(trace_guide(), "json"))["facts"][0].startswith("# yunhee")


def test_cli_trace_guide():
    out = runner.invoke(app, ["trace-guide"])
    assert out.exit_code == 0 and "## 3. 워크플로우" in out.output
    assert json.loads(runner.invoke(app, ["trace-guide", "-o", "json"]).stdout)["command"] == "trace-guide"
