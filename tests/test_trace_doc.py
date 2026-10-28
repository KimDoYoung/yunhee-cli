"""trace-doc: 문서 골격 (표는 사실, 서술은 표지)."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.store import trace_rules as store
from yunhee.tools.base import ToolResult
from yunhee.tools.trace import doc as doc_mod
from yunhee.tools.trace.doc import trace_doc
from yunhee.tools.trace.render import render
from yunhee.tools.trace.resolve import TargetNotFoundError

runner = CliRunner()
SNAPSHOT = {"generated_at": "t", "tables": [{"name": "emp01_person", "note": "개인정보"}, {"name": "emp02_others", "note": "기타"}]}


@pytest.fixture
def dw(world, rule_db, monkeypatch):
    monkeypatch.setattr(doc_mod, "load_snapshot", lambda env: ToolResult(ok=True, data=SNAPSHOT))
    return world


def _sections(res):
    return "\n\n".join(res.facts)


def test_skeleton_has_facts_tables_and_slots(dw):
    res = trace_doc("emp", dw.ctx, dw.tobe)
    text = _sections(res)
    assert text.startswith("# emp 업무 영역 — 신규 인원용 개요")
    assert "화면 2개, TOBE로 이식된 화면 1개" in text
    assert "| 사원관리 > 사원정보 관리 (#1029) | Emp00_Tab_TransInfo | 이식됨 | 3 | emp01_person, emp02_others, emp09_etc |" in text
    assert "| 사원관리 > 레거시 화면 (#1030) | Emp09_Tab_Legacy | 미이식 | 0 |" in text
    assert "| emp01_person | 개인정보 | 1 |" in text  # 테이블 설명은 스냅샷에서
    assert "| emp.Emp00_TransInfo.selectByText | Emp00_Tab_TransInfo |" in text
    assert text.count("<!-- 서술(에이전트):") == 6  # 개요·화면 흐름·테이블·서비스·규칙·이식 우선순위
    assert "- [ ] 화면 흐름" in text and "아직 TOBE에 없는 화면: Emp09_Tab_Legacy" in text


def test_rules_are_collected_by_domain(dw):
    store.add_rule("Emp00_Tab_TransInfo", "의도적 변경", "권한 조건 이동", [], "p1")
    store.add_rule("#1029", "누락", "버튼", [], "p1")
    store.add_rule("Fnd01_Tab_X", "일치", "다른 영역", [], "p1")
    text = _sections(trace_doc("emp", dw.ctx, dw.tobe))
    assert "이 영역과 관련된 규칙 2건" in text and "권한 조건 이동" in text and "다른 영역" not in text
    assert "저장된 규칙 없음" not in text and "| R-001 | Emp00_Tab_TransInfo | 의도적 변경 |" in text


def test_empty_rules_message(dw):
    assert "저장된 규칙 없음" in _sections(trace_doc("emp", dw.ctx, dw.tobe))


def test_document_render_is_raw_markdown_then_evidence(dw):
    out = render(trace_doc("emp", dw.ctx, dw.tobe), "md")
    assert out.startswith("# emp 업무 영역") and "\n- # emp" not in out  # facts를 불릿으로 감싸지 않는다
    assert "\n## evidence\n" in out and "\n## unresolved\n" in out
    as_json = json.loads(render(trace_doc("emp", dw.ctx, dw.tobe), "json"))
    assert isinstance(as_json["facts"], list) and as_json["facts"][0].startswith("# emp")


def test_pipes_in_cells_are_escaped(dw):
    assert doc_mod._cell("a|b\nc") == "a\\|b c"


def test_missing_tobe_and_snapshot_are_reported(dw, tmp_path, monkeypatch):
    monkeypatch.setattr(doc_mod, "load_snapshot", lambda env: ToolResult(ok=False, error="없음"))
    res = trace_doc("emp", dw.ctx, tmp_path / "nowhere")
    assert any("TOBE 소스를 찾지 못해" in u for u in res.unresolved) and any("스키마 스냅샷" in u for u in res.unresolved)
    assert "| — |" in _sections(res) or "—" in _sections(res)


def test_invalid_and_unknown_domain(dw):
    with pytest.raises(ValueError):
        trace_doc("EMP", dw.ctx, dw.tobe)
    with pytest.raises(TargetNotFoundError) as exc:
        trace_doc("zzz", dw.ctx, dw.tobe)
    assert "emp" in exc.value.suggestions


def test_cli_trace_doc(dw):
    base = ["--tobe", str(dw.tobe), "--src", str(dw.src), "--src-index", str(dw.index)]
    out = runner.invoke(app, ["trace-doc", "emp", *base])
    assert out.exit_code == 0 and out.output.startswith("# emp 업무 영역")
    assert runner.invoke(app, ["trace-doc", "zzz", *base]).exit_code == 1
    assert runner.invoke(app, ["trace-doc", "EMP", *base]).exit_code == 2
