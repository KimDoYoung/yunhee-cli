"""trace-* 명령 공통 출력 모델과 렌더러 (facts / evidence / unresolved 3블록)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

SECTIONS = ("facts", "evidence", "unresolved")
LIMITED_SECTIONS = ("facts", "evidence")  # unresolved는 숨기지 않는다


@dataclass
class TraceResult:
    """trace-* 한 번의 실행 결과. 사실(facts)·근거(evidence)·미해결(unresolved)을 분리해 담는다."""

    command: str
    description: str = ""
    side: str = "both"
    options: dict[str, Any] = field(default_factory=dict)
    params: dict[str, Any] = field(default_factory=dict)
    facts: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    omitted: dict[str, int] = field(default_factory=dict)  # --max로 잘린 섹션별 건수


def apply_max(items: list[str], max_n: int | None) -> tuple[list[str], int]:
    """상위 max_n개만 남기고 (남긴 목록, 잘린 건수)를 돌려준다. max_n이 None이거나 0 이하면 그대로."""
    if max_n is None or max_n <= 0 or len(items) <= max_n:
        return list(items), 0
    return list(items[:max_n]), len(items) - max_n


def limit(result: TraceResult, max_n: int | None) -> TraceResult:
    """facts·evidence에 --max를 적용한 새 결과를 만든다 (원본은 바꾸지 않는다)."""
    omitted = dict(result.omitted)
    kept: dict[str, list[str]] = {}
    for name in LIMITED_SECTIONS:
        items, cut = apply_max(getattr(result, name), max_n)
        kept[name] = items
        if cut:
            omitted[name] = omitted.get(name, 0) + cut
    return TraceResult(
        command=result.command,
        description=result.description,
        side=result.side,
        options=dict(result.options),
        params=dict(result.params),
        facts=kept["facts"],
        evidence=kept["evidence"],
        unresolved=list(result.unresolved),
        omitted=omitted,
    )


def _render_section(title: str, items: list[str], omitted: int) -> list[str]:
    lines = [f"## {title}"]
    if not items and not omitted:
        lines.append("(없음)")
    for item in items:
        first, *rest = item.split("\n")
        lines.append(f"- {first}")
        lines.extend(rest)  # 여러 줄 항목의 이어지는 줄은 호출 쪽 들여쓰기를 그대로 둔다
    if omitted:
        lines.append(f"… 나머지 {omitted}건")
    lines.append("")
    return lines


def render_md(result: TraceResult) -> str:
    """기본은 facts/evidence/unresolved 3블록. `options["document"]`면 facts의 각 항목이 문서의 한 절이라 그대로 이어 붙이고
    근거·미해결은 문서 뒤에 같은 3블록 형식으로 붙인다 (trace-doc)."""
    lines: list[str] = []
    if result.options.get("document"):
        lines += ["\n\n".join(result.facts), ""]
        if result.omitted.get("facts"):
            lines += [f"… 나머지 {result.omitted['facts']}절", ""]
        names = SECTIONS[1:]
    else:
        names = SECTIONS
    for name in names:
        lines += _render_section(name, getattr(result, name), result.omitted.get(name, 0))
    return "\n".join(lines)


def render_json(result: TraceResult) -> str:
    data: dict[str, Any] = {
        "command": result.command,
        "description": result.description,
        "side": result.side,
        "options": result.options,
        "params": result.params,
        "facts": result.facts,
        "evidence": result.evidence,
        "unresolved": result.unresolved,
    }
    if result.omitted:
        data["omitted"] = result.omitted
    return json.dumps(data, indent=2, ensure_ascii=False)


def render(result: TraceResult, fmt: str = "md") -> str:
    return render_json(result) if (fmt or "md").lower() == "json" else render_md(result)
