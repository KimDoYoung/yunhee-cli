"""trace-crud: 화면 × 테이블 × C/R/U/D (ASIS와 TOBE)."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.trace.crud import _fmt, asis_matrix, trace_crud, udm_by_service
from yunhee.tools.trace.screen import parse_screen_doc

runner = CliRunner()


def _facts(res):
    return "\n".join(res.facts)


def test_fmt_orders_crud():
    assert _fmt({"D", "C", "R"}) == "CRD" and _fmt({"W"}) == "W"


def test_udm_by_service_reads_dynamic_writes():
    idx = {"server_classes": {"emp.Emp05_Academic": {"methods": [
        {"name": "update", "udm_calls": [["updateModel", "emp05_academic"]]},
        {"name": "delete", "udm_calls": [["deleteModel", "emp05_academic"]]},
    ]}}}
    udm = udm_by_service(idx)
    assert udm["emp.Emp05_Academic.update"]["emp05_academic"] == {"C", "U"}
    assert udm["emp.Emp05_Academic.delete"]["emp05_academic"] == {"D"}


def test_asis_matrix_adds_dynamic_writes_even_when_service_has_sql(world):
    doc = parse_screen_doc("Emp00_Tab_TransInfo", (world.index / "emp/screens/Emp00_Tab_TransInfo.md").read_text())
    ops = {"emp00_trans_info.selectByText": {"emp01_person": {"R"}}}
    udm = {"emp.Emp00_TransInfo.selectByText": {"emp01_person": {"C", "U"}}}
    assert asis_matrix(doc, ops, udm)["emp01_person"] == {"R", "C", "U"}


def test_screen_matrix_compares_asis_and_tobe(world, fake_schema):
    text = _facts(trace_crud(world.ctx, world.tobe, screen="#1029"))
    assert "화면 Emp00_Tab_TransInfo: 테이블 3개 (ASIS 3 / TOBE 1)" in text
    assert "emp01_person: ASIS R / TOBE R" in text
    assert "emp02_others: ASIS CR / TOBE -  ⚠ TOBE에 없음" in text  # insert(C)와 selectByText의 JOIN(R)
    assert "emp09_etc: ASIS R / TOBE -  ⚠ TOBE에 없음" in text


def test_table_scope_lists_screens_and_flags_lost_operations(world, fake_schema):
    text = _facts(trace_crud(world.ctx, world.tobe, table="emp02_others"))
    assert "테이블 emp02_others을(를) 쓰는 화면 1개" in text
    assert "Emp00_Tab_TransInfo: ASIS CR / TOBE -  ⚠ TOBE에 CR 없음" in text


def test_domain_scope_summarises_and_flags_missing_writes(world, fake_schema):
    text = _facts(trace_crud(world.ctx, world.tobe, domain="emp"))
    assert "영역 emp: 화면 2개" in text
    assert "Emp00_Tab_TransInfo: ASIS 테이블 3(C1 R3 U0 D0) / TOBE 1" in text and "⚠ TOBE에 없는 쓰기: emp02_others" in text
    assert "Emp09_Tab_Legacy: ASIS 테이블 0(C0 R0 U0 D0) / TOBE 0 — TOBE에 화면 없음" in text
    assert "테이블별 쓰는 화면 수 — 3개 테이블" in text


def test_overview_without_scope_and_scope_validation(world, fake_schema):
    assert "영역별 요약 1개" in _facts(trace_crud(world.ctx, world.tobe)) and "emp: 화면 2, 테이블 3" in _facts(trace_crud(world.ctx, world.tobe))
    with pytest.raises(ValueError, match="하나만"):
        trace_crud(world.ctx, world.tobe, domain="emp", table="x")


def test_missing_tobe_gives_asis_only(world, fake_schema, tmp_path):
    res = trace_crud(world.ctx, tmp_path / "nowhere", screen="#1029")
    assert "(ASIS 3 / TOBE 0)" in _facts(res) and any("TOBE 소스를 찾지 못해 ASIS만" in u for u in res.unresolved)


def test_cli_trace_crud(world, fake_schema):
    base = ["--tobe", str(world.tobe), "--src", str(world.src), "--src-index", str(world.index)]
    out = runner.invoke(app, ["trace-crud", "-s", "#1029", "-o", "json", *base])
    assert out.exit_code == 0
    assert json.loads(out.output[out.output.index("{"):])["params"]["resolved"] == "Emp00_Tab_TransInfo"
    assert runner.invoke(app, ["trace-crud", "-d", "emp", "-t", "x", *base]).exit_code == 2
