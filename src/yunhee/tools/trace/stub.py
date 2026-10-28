"""Stub formatting helpers for yunhee trace-* commands."""

from __future__ import annotations

from typing import Any

from yunhee.tools.trace.render import TraceResult, limit, render


def format_trace_stub(
    cmd_name: str,
    desc: str,
    params: dict[str, Any],
    side: str = "both",
    fmt: str = "md",
    max_n: int | None = None,
) -> str:
    """Format standard trace command stub output (facts / evidence / unresolved)."""
    fmt_lower = fmt.lower() if fmt else "md"
    side_lower = side.lower() if side else "both"

    opt_parts = [f"format={fmt_lower}"]
    if max_n is not None:
        opt_parts.append(f"max={max_n}")
    non_empty_params = {k: v for k, v in params.items() if v is not None}

    facts = [
        f"[STUB] {desc}",
        f"command: yunhee {cmd_name}",
        f"side: {side_lower}",
        f"options: {', '.join(opt_parts)}",
    ]
    if non_empty_params:
        facts.append("arguments:\n" + "\n".join(f"  - {k}: {v}" for k, v in non_empty_params.items()))

    result = TraceResult(
        command=cmd_name,
        description=desc,
        side=side_lower,
        options={"side": side_lower, "format": fmt_lower, "max": max_n},
        params=params,
        facts=facts,
        evidence=["[STUB] 근거 위치 (소스 코드 줄번호, mapper ID, DBML 스냅샷 시각 등이 여기에 표시됩니다)"],
        unresolved=["[STUB] 추적되지 않은 동적 호출이나 미해결 참조가 여기에 표시됩니다"],
    )
    return render(limit(result, max_n), fmt_lower)
