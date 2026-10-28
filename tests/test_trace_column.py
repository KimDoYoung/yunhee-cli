"""trace-column: 컬럼을 읽는/쓰는/조건에 쓰는 SQL, 화면 라벨, 값 분포."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.trace import column as column_mod
from yunhee.tools.trace import db
from yunhee.tools.trace.column import _short, trace_column
from yunhee.tools.trace.resolve import TargetNotFoundError

runner = CliRunner()


def _facts(res):
    return "\n".join(res.facts)


def test_short_keeps_asis_and_shortens_tobe_keys():
    assert _short("emp00_trans_info.selectByText") == "emp00_trans_info.selectByText"
    assert _short("kr.co.kfs.biz.emp.mapper.EmpTransInfoMapper.searchTransInfos") == "EmpTransInfoMapper.searchTransInfos"


def test_read_condition_and_write_are_separated(world, fake_schema):
    text = _facts(trace_column("emp02_others.emp02_note", world.ctx_for(), world.tobe))
    assert "컬럼: emp02_others.emp02_note varchar(10) — emp02_note 설명" in text
    assert "ASIS: 이 컬럼을 쓰는 SQL 2개" in text
    assert "읽기(SELECT·SET 식·RETURNING)(1): emp00_trans_info.selectByText" in text
    assert "쓰기(INSERT/UPDATE)(1): emp02_others.insert(INSERT)" in text
    cond = _facts(trace_column("emp01_person.emp01_company_id", world.ctx_for(), world.tobe))
    assert "조건(WHERE·JOIN·HAVING)(1): emp00_trans_info.selectByText" in cond.split("TOBE:")[0]
    assert "읽기(SELECT·SET 식·RETURNING)(0)" in cond.split("TOBE:")[0]  # 조건에만 쓰이고 SELECT 목록에는 없다


def test_tobe_side_uses_short_keys(world, fake_schema):
    text = _facts(trace_column("emp01_person.emp01_nm", world.ctx_for(), world.tobe))
    tobe = text.split("TOBE:")[1]
    assert "읽기(SELECT·SET 식·RETURNING)(1): EmpTransInfoMapper.searchTransInfos" in tobe


def test_labels_from_grid_specs_on_both_sides(world, fake_schema):
    screen = world.index / "emp/screens/Emp00_Tab_TransInfo.md"
    screen.write_text(screen.read_text(encoding="utf-8") + "\n#### Grid Spec\n```javascript\n  gb.date('hireDate', 100, '입사일'),\n```\n", encoding="utf-8")
    text = _facts(trace_column("emp01_person.emp01_hire_date", world.ctx_for(), world.tobe))
    assert "화면 표시 라벨(속성 이름 `hireDate`): ASIS 1건 / TOBE 1건" in text
    assert "ASIS: Emp00_Tab_TransInfo: '입사일'" in text and "TOBE: Emp00_Tab_TransInfo: '입사일'" in text


def test_value_distribution_only_for_code_like_columns(world, fake_schema, monkeypatch):
    calls = []

    def fake_fetch(sql, params=(), **kw):
        calls.append(sql)
        if "count(DISTINCT" in sql:
            return [(3, 1, 10)]
        return [("A", 6), ("B", 3), (None, 1)]

    monkeypatch.setattr(db, "fetch", fake_fetch)
    text = _facts(trace_column("emp01_person.kind", world.ctx_for(), world.tobe, stats=True))
    assert "값 분포(행 10, NULL 1, 고유 값 3종):\n  A: 6, B: 3, NULL: 1" in text
    monkeypatch.setattr(db, "fetch", lambda sql, params=(), **kw: [(500, 0, 800)] if "count(DISTINCT" in sql else pytest.fail("값을 조회하면 안 됨"))
    hidden = _facts(trace_column("emp01_person.emp01_nm", world.ctx_for(), world.tobe, stats=True))
    assert "고유 값 500종 — 코드성 컬럼(30종 이하)이 아니라 값은 내지 않음 (개인정보·식별자 노출 방지)" in hidden


def test_stats_db_failure_is_unresolved(world, fake_schema, monkeypatch):
    def boom(*a, **k):
        raise db.DbUnavailable("접속 실패")

    monkeypatch.setattr(db, "fetch", boom)
    res = trace_column("emp01_person.kind", world.ctx_for(), world.tobe, stats=True)
    assert any("--stats: 값 분포를 구하지 못함 (접속 실패)" in u for u in res.unresolved)


def test_unknown_column_suggests(world, fake_schema):
    with pytest.raises(TargetNotFoundError) as exc:
        trace_column("emp01_person.emp01_n", world.ctx_for(), world.tobe)
    assert "emp01_person.emp01_nm" in exc.value.suggestions
    with pytest.raises(TargetNotFoundError):
        trace_column("nope.col", world.ctx_for(), world.tobe)


def test_cli_trace_column(world, fake_schema):
    base = ["--tobe", str(world.tobe), "--src", str(world.src), "--src-index", str(world.index)]
    out = runner.invoke(app, ["trace-column", "emp02_others.emp02_note", "-o", "json", *base])
    assert out.exit_code == 0
    data = json.loads(out.stdout)
    assert data["params"]["col_ref"] == "emp02_others.emp02_note" and data["facts"]
    assert runner.invoke(app, ["trace-column", "badref", *base]).exit_code == 2
    assert runner.invoke(app, ["trace-column", "emp02_others.nope", *base]).exit_code == 1
    _ = column_mod
