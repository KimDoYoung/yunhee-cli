"""trace-* 공통 대상 해석(resolve.py) 테스트 — 가짜 색인 디렉터리 사용."""

import json

import pytest

from yunhee.tools.analysis.common import AmbiguousTargetError
from yunhee.tools.trace.resolve import (
    TargetNotFoundError,
    load_context,
    normalize_side,
    resolve_screen,
    screen_names,
    wants_asis,
    wants_tobe,
)


@pytest.fixture
def index_dir(tmp_path):
    idx = tmp_path / "idx"
    (idx / "fnd" / "screens").mkdir(parents=True)
    for name in ("Fnd01_Tab_FundSearch", "Fnd01_Tab_FundEdit", "Fnd09_Tab_Report"):
        (idx / "fnd" / "screens" / f"{name}.md").write_text(f"# {name}\n", encoding="utf-8")
    data = {"client_classes": {"Fnd01_Popup_Pick": {"file": "x", "domain": "fnd"}}, "server_classes": {}}
    (idx / "_index.json").write_text(json.dumps(data), encoding="utf-8")
    return idx


def test_normalize_side():
    assert normalize_side(None) == "both"
    assert normalize_side("ASIS") == "asis"
    with pytest.raises(ValueError):
        normalize_side("x")
    assert wants_asis("both") and wants_tobe("both")
    assert wants_asis("asis") and not wants_tobe("asis")
    assert wants_tobe("tobe") and not wants_asis("tobe")


def test_load_context_reads_index(index_dir, tmp_path):
    ctx = load_context("asis", src=tmp_path, src_index=index_dir)
    assert ctx.has_index and ctx.unresolved == []
    assert "Fnd01_Popup_Pick" in screen_names(ctx)  # 하위 컴포넌트도 포함
    assert "Fnd09_Tab_Report" in screen_names(ctx)


def test_load_context_without_index_reports_unresolved(tmp_path):
    ctx = load_context("asis", src=tmp_path, src_index=tmp_path / "none")
    assert not ctx.has_index
    assert any("색인" in u for u in ctx.unresolved)


def test_load_context_tobe_only_skips_asis_index(tmp_path):
    ctx = load_context("tobe", src=tmp_path, src_index=tmp_path / "none")
    assert ctx.unresolved == []


def test_resolve_screen_exact_case_insensitive(index_dir, tmp_path):
    ctx = load_context("asis", src=tmp_path, src_index=index_dir)
    assert resolve_screen("fnd09_tab_report", ctx) == "Fnd09_Tab_Report"
    assert resolve_screen("Fnd09_Tab_Report.md", ctx) == "Fnd09_Tab_Report"


def test_resolve_screen_unique_prefix(index_dir, tmp_path):
    ctx = load_context("asis", src=tmp_path, src_index=index_dir)
    assert resolve_screen("Fnd09", ctx) == "Fnd09_Tab_Report"


def test_resolve_screen_ambiguous_prefix(index_dir, tmp_path):
    ctx = load_context("asis", src=tmp_path, src_index=index_dir)
    with pytest.raises(AmbiguousTargetError) as exc:
        resolve_screen("Fnd01", ctx)
    assert "Fnd01_Tab_FundSearch" in exc.value.candidates


def test_resolve_screen_not_found_suggests(index_dir, tmp_path):
    ctx = load_context("asis", src=tmp_path, src_index=index_dir)
    with pytest.raises(TargetNotFoundError) as exc:
        resolve_screen("Fnd09_Tab_Reprot", ctx)
    assert "Fnd09_Tab_Report" in exc.value.suggestions
