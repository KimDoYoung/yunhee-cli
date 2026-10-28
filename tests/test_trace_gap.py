"""trace-gap: ASIS에만 / TOBE에만 / 추적하지 못한 지점."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.trace.gap import trace_gap

runner = CliRunner()


def _facts(res):
    return "\n".join(res.facts)


def _unresolved(res):
    return "\n".join(res.unresolved)


def test_screen_gap(world):
    res = trace_gap(world.ctx, world.tobe, "emp")
    text = _facts(res)
    assert "화면: ASIS 2 / TOBE 2 — TOBE에 대응 TSX가 있는 ASIS 화면 1" in text
    assert "ASIS에만 있는 화면(TOBE에 같은 이름의 TSX도, 헤더 AS-IS도 없음)(1)" in text and "Emp09_Tab_Legacy (#1030)" in text
    assert "TOBE에만 있는 화면(ASIS 색인에 같은 이름의 클래스가 없음)(1)" in text and "Emp77_Tab_Brand" in text


def test_service_gap(world):
    res = trace_gap(world.ctx, world.tobe, "emp")
    text = _facts(res)
    assert "서비스(RPC): ASIS 3 / TOBE 주석에 적힌 서비스 키 1 — 대응 1" in text
    assert "ASIS에만 있는 서비스(TOBE 컨트롤러·api 주석에 이 서비스 키가 없음)(2)" in text
    assert "emp.Emp00_TransInfo.update" in text and "emp.Emp09_Etc.legacy" in text
    # 근거를 못 찾은 TOBE 엔드포인트는 "대응 없음"이 아니라 추적하지 못한 지점이다
    assert "AS-IS 서비스 키 주석이 없어 ASIS 출처를 추적하지 못한 TOBE 엔드포인트(1)" in _unresolved(res) and "POST /api/v1/emp/brand/{}" in _unresolved(res)


def test_sql_gap(world):
    res = trace_gap(world.ctx, world.tobe, "emp")
    text = _facts(res)
    assert "SQL: ASIS 3 — TOBE 문장 주석이 가리키는 것 1" in text
    assert "ASIS에만 있는 SQL(어느 TOBE 문장 주석도 가리키지 않음)(2)" in text
    assert "AS-IS 주석이 없어 ASIS 출처를 추적하지 못한 TOBE mapper 문장(1)" in _unresolved(res) and "untracked" in _unresolved(res)


def test_api_gap_reports_calls_that_do_not_reach_a_controller(world):
    res = trace_gap(world.ctx, world.tobe, "emp")
    # Emp77_Tab_Brand가 부르는 POST /api/v1/emp/brand/{}는 컨트롤러에 있으므로 끊김이 없다
    assert "TSX가 부르는 API가 컨트롤러까지 이어지지 않음" not in _unresolved(res)


def test_domain_filter_and_validation(world):
    other = trace_gap(world.ctx, world.tobe, "sys")
    assert "화면: ASIS 0 / TOBE 0" in _facts(other)
    with pytest.raises(ValueError):
        trace_gap(world.ctx, world.tobe, "EMP")


def test_without_domain_covers_everything(world):
    assert "ASIS 2 / TOBE 2" in _facts(trace_gap(world.ctx, world.tobe))


def test_missing_tobe_tree_is_unresolved(world, tmp_path):
    res = trace_gap(world.ctx, tmp_path / "nowhere")
    assert res.facts == [] and any("TOBE 소스를 찾지 못함" in u for u in res.unresolved)


def test_cli_trace_gap(world):
    args = ["--tobe", str(world.tobe), "--src", str(world.src), "--src-index", str(world.index)]
    out = runner.invoke(app, ["trace-gap", "-d", "emp", "-o", "json", *args])
    assert out.exit_code == 0
    data = json.loads(out.output[out.output.index("{"):])
    assert data["params"]["domain"] == "emp" and data["facts"]
    assert runner.invoke(app, ["trace-gap", "-d", "EMP", *args]).exit_code == 2
