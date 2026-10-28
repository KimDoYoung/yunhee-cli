"""trace-state: 컬럼에 값을 쓰는 SQL의 대입 값과 WHERE 조건."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.base import ToolResult
from yunhee.tools.trace import state as state_mod
from yunhee.tools.trace.resolve import TargetNotFoundError, load_context
from yunhee.tools.trace.state import _compare_key, show_params, split_ref, trace_state

runner = CliRunner()

SNAPSHOT = {
    "generated_at": "2026-10-11T10:25:41+09:00",
    "tables": [{"schema": "public", "name": "emp03_trans", "note": "발령", "pk": ["id"], "uniques": [], "indexes": [],
                "columns": [{"name": "id", "type": "numeric", "note": ""}, {"name": "emp03_stat_cd", "type": "varchar(3)", "note": "상태"}]}],
}

ASIS_STATE_MAPPER = """<mapper namespace="emp03_trans">
  <update id="approve">UPDATE emp03_trans SET emp03_stat_cd = '800' WHERE id = #{id} AND emp03_stat_cd = '100'</update>
  <update id="setStat">UPDATE emp03_trans SET emp03_stat_cd = #{statCd} WHERE id = #{id}</update>
  <insert id="insert">INSERT INTO emp03_trans (id, emp03_stat_cd) VALUES (#{id}, '100')</insert>
  <update id="upsert">
    WITH u AS (UPDATE emp03_trans SET emp03_stat_cd = '900' WHERE id = #{id} RETURNING id)
    INSERT INTO emp03_trans (id, emp03_stat_cd) SELECT #{id}, '100' WHERE NOT EXISTS (SELECT 1 FROM u)
  </update>
  <select id="read">SELECT emp03_stat_cd FROM emp03_trans</select>
</mapper>"""

TOBE_STATE_MAPPER = """<mapper namespace="x.EmpTransMapper">
  <update id="approve">UPDATE emp03_trans SET emp03_stat_cd = '800' WHERE id = #{id} AND emp03_stat_cd = '100'</update>
  <update id="setStat">UPDATE emp03_trans SET emp03_stat_cd = #{stat_cd} WHERE id = #{id}</update>
  <update id="cancel">UPDATE emp03_trans SET emp03_stat_cd = '999' WHERE id = #{id}</update>
</mapper>"""


@pytest.fixture
def swd(world, monkeypatch):
    (world.src / "server/emp/mapper/emp03_trans.xml").write_text(ASIS_STATE_MAPPER, encoding="utf-8")
    (world.tobe / "backend/src/main/resources/mapper/EmpTransMapper.xml").write_text(TOBE_STATE_MAPPER, encoding="utf-8")
    monkeypatch.setattr(state_mod, "load_snapshot", lambda env: ToolResult(ok=True, data=SNAPSHOT))
    state_mod._asis_writes.cache_clear()
    state_mod._tobe_writes.cache_clear()
    return world, load_context("both", src=world.src, src_index=world.index)


def test_helpers():
    assert split_ref("public.emp03_trans.EMP03_STAT_CD") == ("emp03_trans", "emp03_stat_cd")
    with pytest.raises(ValueError):
        split_ref("emp03_stat_cd")
    assert show_params('"__p_statCd" + __p_id') == "#{statCd} + #{id}"
    assert _compare_key('"__p_statCd"') == _compare_key('"__p_stat_cd"') == "#{statcd}"  # 파라미터 표기 차이는 같은 값으로 본다
    assert _compare_key("'800'") != _compare_key("'900'")


def test_asis_values_conditions_and_origin(swd):
    world, ctx = swd
    text = "\n".join(trace_state("emp03_trans.emp03_stat_cd", ctx, world.tobe).facts)
    assert "컬럼: emp03_trans.emp03_stat_cd varchar(3) — 상태" in text
    assert "ASIS: 쓰는 SQL 5개, 대입 값 4종" in text
    assert "'100' ← emp03_trans.insert(INSERT), emp03_trans.upsert(INSERT)" in text
    assert "'900' ← emp03_trans.upsert(UPDATE)" in text  # CTE 안의 UPDATE도 잡힌다
    assert "#{statCd} ← emp03_trans.setStat(UPDATE)" in text  # 파라미터는 이름을 남긴다
    assert "emp03_trans.approve [UPDATE]" in text and "조건: id = #{id} AND emp03_stat_cd = '100'" in text
    assert "(WHERE 없음" not in text.split("emp03_trans.insert [INSERT]")[1].split("-")[0]  # INSERT에는 WHERE가 없다
    assert "emp03_trans.read" not in text  # 읽기 전용 SQL은 제외


def test_asis_vs_tobe_value_comparison(swd):
    world, ctx = swd
    text = "\n".join(trace_state("emp03_trans.emp03_stat_cd", ctx, world.tobe).facts)
    assert "TOBE: 쓰는 SQL 3개, 대입 값 3종" in text
    assert "대입 값 비교: 같음 2 / ASIS에만 2 / TOBE에만 1" in text  # '800'·#{statCd}는 같음 (statCd ≡ stat_cd)
    assert "ASIS에만: '100', '900'" in text and "TOBE에만: '999'" in text


def test_dynamic_writes_are_listed_not_guessed(swd):
    world, ctx = swd
    ctx.index_data["server_classes"]["emp.Emp03_Trans"] = {"methods": [{"name": "update", "sqls": [], "is_service": True, "udm_calls": [["updateModel", "emp03_trans"]]}]}
    text = "\n".join(trace_state("emp03_trans.emp03_stat_cd", ctx, world.tobe).facts)
    assert "동적 쓰기(UpdateDataModel, 1)" in text and "emp.Emp03_Trans.update (등록/수정)" in text


def test_side_selection_and_missing_sources(swd, tmp_path):
    world, ctx = swd
    asis_only = trace_state("emp03_trans.emp03_stat_cd", load_context("asis", src=world.src, src_index=world.index), world.tobe)
    assert not any(f.startswith("TOBE") for f in asis_only.facts)
    no_tobe = trace_state("emp03_trans.emp03_stat_cd", ctx, tmp_path / "nowhere")
    assert any("TOBE mapper를 찾지 못함" in u for u in no_tobe.unresolved)


def test_column_without_writers_is_stated(swd):
    world, ctx = swd
    state_mod.load_snapshot = lambda env: ToolResult(ok=True, data={"tables": [{**SNAPSHOT["tables"][0], "columns": [{"name": "id", "type": "n"}, {"name": "other", "type": "n"}]}]})
    text = "\n".join(trace_state("emp03_trans.other", ctx, world.tobe).facts)
    assert "ASIS: 이 컬럼에 값을 쓰는 SQL을 찾지 못함" in text


def test_unknown_table_or_column_is_rejected(swd):
    world, ctx = swd
    with pytest.raises(TargetNotFoundError):
        trace_state("nope_tbl.x_cd", ctx, world.tobe)
    with pytest.raises(TargetNotFoundError) as exc:
        trace_state("emp03_trans.emp03_stat_c", ctx, world.tobe)
    assert "emp03_trans.emp03_stat_cd" in exc.value.suggestions


def test_cli_trace_state(swd):
    world, _ = swd
    base = ["--tobe", str(world.tobe), "--src", str(world.src), "--src-index", str(world.index)]
    out = runner.invoke(app, ["trace-state", "emp03_trans.emp03_stat_cd", "-o", "json", *base])
    assert out.exit_code == 0
    data = json.loads(out.output[out.output.index("{"):])
    assert data["params"]["col_ref"] == "emp03_trans.emp03_stat_cd" and data["facts"]
    assert runner.invoke(app, ["trace-state", "badref", *base]).exit_code == 2
    assert runner.invoke(app, ["trace-state", "nope_tbl.x_cd", *base]).exit_code == 1
