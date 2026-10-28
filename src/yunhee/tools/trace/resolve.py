"""trace-* 공통 대상 해석: --side 검증, 색인 경로·데이터 로드, 화면 이름 해석."""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from yunhee.tools.analysis.common import (
    AmbiguousTargetError,
    load_index_data,
    resolve_as_is_paths,
)

SIDES = ("asis", "tobe", "both")
MAX_CANDIDATES = 10


class TargetNotFoundError(Exception):
    """대상을 색인에서 찾지 못했을 때. 비슷한 이름을 후보로 담는다."""

    def __init__(self, target: str, suggestions: list[str] | None = None) -> None:
        self.target = target
        self.suggestions = suggestions or []
        msg = f"'{target}'을(를) 색인에서 찾지 못했습니다."
        if self.suggestions:
            msg += " 후보: " + ", ".join(self.suggestions)
        super().__init__(msg)


def normalize_side(side: str | None) -> str:
    """--side 값을 검증한다. 비어 있으면 both."""
    value = (side or "both").lower()
    if value not in SIDES:
        raise ValueError(f"--side는 {', '.join(SIDES)} 중 하나여야 합니다: {side}")
    return value


def wants_asis(side: str) -> bool:
    return side in ("asis", "both")


def wants_tobe(side: str) -> bool:
    return side in ("tobe", "both")


@dataclass
class TraceContext:
    """한 번의 trace 실행에 필요한 경로와 색인 데이터. 없는 것은 unresolved에 사유를 남긴다."""

    side: str
    src_root: Path | None = None
    src_index: Path | None = None
    index_data: dict[str, Any] | None = None
    unresolved: list[str] = field(default_factory=list)

    @property
    def has_index(self) -> bool:
        return self.index_data is not None


def load_context(
    side: str = "both",
    src: Path | None = None,
    src_index: Path | None = None,
) -> TraceContext:
    """경로를 해석하고 ASIS 색인(_index.json)을 읽는다. 색인이 없어도 예외 대신 unresolved로 알린다."""
    side = normalize_side(side)
    ctx = TraceContext(side=side)
    ctx.src_root, ctx.src_index = resolve_as_is_paths(src=src, src_index=src_index)
    if not wants_asis(side):
        return ctx
    if not ctx.src_index or not ctx.src_index.is_dir():
        ctx.unresolved.append("ASIS 색인 디렉터리를 찾지 못했습니다 — `yunhee index-src`를 실행하거나 YUNHEE_SRC_INDEX_DIR을 지정하세요.")
        return ctx
    ctx.index_data = load_index_data(ctx.src_index, ctx.src_root)
    if ctx.index_data is None:
        ctx.unresolved.append(f"{ctx.src_index}/_index.json을 읽지 못했습니다 — `yunhee index-src`를 다시 실행하세요.")
    return ctx


def screen_names(ctx: TraceContext) -> list[str]:
    """색인에 있는 화면·하위 컴포넌트 클래스 이름 (중복 제거, 정렬)."""
    names: set[str] = set()
    if ctx.src_index and ctx.src_index.is_dir():
        names.update(p.stem for p in ctx.src_index.glob("**/screens/*.md"))
    if ctx.index_data:
        names.update(ctx.index_data.get("client_classes", {}))
    return sorted(names)


def resolve_screen(target: str, ctx: TraceContext) -> str:
    """화면ID 또는 클래스명을 색인의 클래스명 하나로 해석한다.

    우선순위: 정확히 일치(대소문자 무시) → 접두사 일치(`Fnd01` → `Fnd01_Tab_FundSearch`).
    후보가 여러 개면 AmbiguousTargetError, 없으면 TargetNotFoundError.
    """
    key = target.strip().removesuffix(".md")
    names = screen_names(ctx)
    lowered = key.lower()

    exact = [n for n in names if n.lower() == lowered]
    if len(exact) == 1:
        return exact[0]
    candidates = exact or [n for n in names if lowered and n.lower().startswith(lowered)]
    if len(candidates) == 1:
        return candidates[0]
    if candidates:
        raise AmbiguousTargetError(candidates[:MAX_CANDIDATES], target)
    raise TargetNotFoundError(target, difflib.get_close_matches(key, names, n=5, cutoff=0.5))
