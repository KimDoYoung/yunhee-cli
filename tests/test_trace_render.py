"""trace-* 공통 렌더러(render.py) 테스트."""

import json

from yunhee.tools.trace.render import (
    TraceResult,
    apply_max,
    limit,
    render,
    render_json,
    render_md,
)


def _result(**kw) -> TraceResult:
    base = {"command": "trace-x", "description": "d", "side": "asis"}
    base.update(kw)
    return TraceResult(**base)


def test_md_has_three_blocks_in_order():
    out = render_md(_result(facts=["a"], evidence=["f.java:1"], unresolved=["동적 호출"]))
    assert out.index("## facts") < out.index("## evidence") < out.index("## unresolved")
    assert "- a" in out and "- f.java:1" in out and "- 동적 호출" in out


def test_md_empty_sections_show_none():
    out = render_md(_result())
    assert out.count("(없음)") == 3


def test_md_multiline_item_keeps_continuation_lines():
    out = render_md(_result(facts=["arguments:\n  - k: v"]))
    assert "- arguments:\n  - k: v" in out


def test_json_keys_and_omitted_only_when_cut():
    data = json.loads(render_json(_result(facts=["a"])))
    assert set(data) == {"command", "description", "side", "options", "params", "facts", "evidence", "unresolved"}
    cut = json.loads(render_json(limit(_result(facts=["a", "b", "c"]), 2)))
    assert cut["facts"] == ["a", "b"]
    assert cut["omitted"] == {"facts": 1}


def test_apply_max():
    assert apply_max(["a", "b", "c"], 2) == (["a", "b"], 1)
    assert apply_max(["a"], 5) == (["a"], 0)
    assert apply_max(["a", "b"], None) == (["a", "b"], 0)
    assert apply_max(["a", "b"], 0) == (["a", "b"], 0)


def test_limit_marks_remaining_and_never_hides_unresolved():
    res = _result(facts=["1", "2", "3", "4"], evidence=["e1", "e2", "e3"], unresolved=["u1", "u2", "u3"])
    out = render_md(limit(res, 2))
    assert "… 나머지 2건" in out  # facts
    assert "… 나머지 1건" in out  # evidence
    assert "- u3" in out  # unresolved는 절단하지 않음


def test_limit_does_not_mutate_original():
    res = _result(facts=["1", "2", "3"])
    limit(res, 1)
    assert res.facts == ["1", "2", "3"] and res.omitted == {}


def test_render_dispatches_on_format():
    res = _result(facts=["a"])
    assert render(res, "json").lstrip().startswith("{")
    assert render(res, "md").startswith("## facts")
    assert render(res, "JSON").lstrip().startswith("{")
