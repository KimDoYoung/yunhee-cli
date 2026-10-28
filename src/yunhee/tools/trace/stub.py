"""Stub formatting helpers for yunhee trace-* commands."""

from __future__ import annotations

import json
from typing import Any


def format_trace_stub(
    cmd_name: str,
    desc: str,
    params: dict[str, Any],
    side: str = "both",
    fmt: str = "md",
    max_n: int | None = None,
    refs_only: bool = False,
) -> str:
    """Format standard trace command stub output.

    Output Structure:
    - facts: facts extracted (placeholder with params)
    - evidence: file:line, mapper id, snapshot timestamps
    - unresolved: unresolvable dynamic calls or missing references
    """
    fmt_lower = fmt.lower() if fmt else "md"
    side_lower = side.lower() if side else "both"

    if fmt_lower == "json":
        data = {
            "command": cmd_name,
            "description": desc,
            "side": side_lower,
            "options": {
                "side": side_lower,
                "format": fmt_lower,
                "max": max_n,
                "refs_only": refs_only,
            },
            "params": params,
            "facts": [] if refs_only else [f"[STUB] {desc}"],
            "evidence": [
                "[STUB] 근거 위치 (소스 코드 줄번호, mapper ID, DBML 스냅샷 시각 등이 여기에 표시됩니다)"
            ],
            "unresolved": [
                "[STUB] 추적되지 않은 동적 호출이나 미해결 참조가 여기에 표시됩니다"
            ],
        }
        return json.dumps(data, indent=2, ensure_ascii=False)

    # Markdown format
    lines: list[str] = []
    lines.append("## facts")
    if refs_only:
        lines.append("(사실 생략: --refs-only 지정됨)")
    else:
        lines.append(f"[STUB] {desc}")
        lines.append(f"- command: yunhee {cmd_name}")
        lines.append(f"- side: {side_lower}")
        opt_parts = [f"format={fmt_lower}"]
        if max_n is not None:
            opt_parts.append(f"max={max_n}")
        if refs_only:
            opt_parts.append(f"refs_only={refs_only}")
        lines.append(f"- options: {', '.join(opt_parts)}")
        non_empty_params = {k: v for k, v in params.items() if v is not None}
        if non_empty_params:
            lines.append("- arguments:")
            for k, v in non_empty_params.items():
                lines.append(f"  - {k}: {v}")
    lines.append("")
    lines.append("## evidence")
    lines.append("[STUB] (근거 위치: 소스 코드 줄번호, mapper ID, DBML 스냅샷 시각 등이 여기에 표시됩니다)")
    lines.append("")
    lines.append("## unresolved")
    lines.append("[STUB] (추적되지 않은 동적 호출이나 미해결 참조가 여기에 표시됩니다)")
    lines.append("")

    return "\n".join(lines)
