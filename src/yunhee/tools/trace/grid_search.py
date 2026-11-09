"""trace-grid: 그리드 컬럼 조건(타입, 제목 글자수/정규식) 및 모달/버튼 조건으로 화면 검색 (기본 TOBE)."""

from __future__ import annotations

import re
from pathlib import Path

from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import TraceContext
from yunhee.tools.trace.screen_catalog import ScreenRecord, iter_screens

_CHECK_ALIASES = {"check", "checkbox", "bool", "boolean", "booleanyn2", "체크", "체크박스"}


def _matches_col_type(col_type: str, target_type: str) -> bool:
    t = target_type.strip().lower()
    c = col_type.strip().lower()
    if t in _CHECK_ALIASES:
        return c in ("boolean", "booleanyn2")
    if t in ("num", "number", "숫자"):
        return c in ("long", "longcenter", "longcolor", "longsecond", "double", "doublecenter", "doublecolor")
    if t in ("date", "날짜"):
        return c.startswith("date")
    if t in ("text", "문자", "텍스트"):
        return c.startswith("text")
    return t in c


def trace_grid(
    ctx: TraceContext,
    tobe: Path | None = None,
    col_type: str | None = None,
    label: str | None = None,
    label_re: str | None = None,
    label_len: int | None = None,
    modal: str | None = None,
    button: str | None = None,
) -> TraceResult:
    side = ctx.side or "tobe"
    res = TraceResult(
        command="trace-grid",
        description="그리드 컬럼 조건(타입·라벨·글자수) 및 모달·버튼 조건으로 화면·메뉴·파일 탐색",
        side=side,
        params={
            "type": col_type,
            "label": label,
            "label_re": label_re,
            "label_len": label_len,
            "modal": modal,
            "button": button,
        },
    )
    res.unresolved += ctx.unresolved

    screens: list[ScreenRecord] = iter_screens(
        side=side,
        tobe=tobe,
        src_index=ctx.src_index,
    )
    if not screens:
        res.unresolved.append(f"{side.upper()} 화면 카탈로그가 비어 있습니다 (--tobe 또는 색인 경로 확인)")
        return res

    compiled_label_re = re.compile(label_re) if label_re else None
    compiled_modal_re = re.compile(modal, re.IGNORECASE) if modal else None
    compiled_btn_re = re.compile(button, re.IGNORECASE) if button else None

    hits: list[str] = []
    has_grid_filter = any(x is not None for x in (col_type, label, label_re, label_len))

    for s in screens:
        details: list[str] = []

        # 1. 그리드 컬럼 조건 검사
        if has_grid_filter:
            matched_cols = []
            for c in s.grid_cols:
                if col_type and not _matches_col_type(c.col_type, col_type):
                    continue
                if label and label.lower() not in c.label.lower():
                    continue
                if compiled_label_re and not compiled_label_re.search(c.label):
                    continue
                if label_len is not None and len(c.label.strip()) != label_len:
                    continue
                matched_cols.append(f'gb.{c.col_type}("{c.field}", {c.width}, "{c.label}")')
            if not matched_cols:
                continue
            details.extend(matched_cols)

        # 2. 모달 제목 조건 검사
        if compiled_modal_re:
            matched_modals = [
                f'{m.kind} title="{m.title}" (L{m.line})'
                for m in s.modals
                if compiled_modal_re.search(m.title)
            ]
            if not matched_modals:
                continue
            details.extend(matched_modals)

        # 3. 버튼 라벨 조건 검사
        if compiled_btn_re:
            matched_btns = [f"버튼[{b}]" for b in s.buttons if compiled_btn_re.search(b)]
            if not matched_btns:
                continue
            details.extend(matched_btns)

        if not has_grid_filter and not compiled_modal_re and not compiled_btn_re:
            if s.grid_cols or s.modals:
                details.append(f"컬럼 {len(s.grid_cols)}개, 모달 {len(s.modals)}개")
            else:
                continue

        hits.append(s.format_hit(", ".join(details)))

    res.facts.append(f"일치 화면/컴포넌트: {len(hits)}건 (대상: {side.upper()}, 전체 스캔: {len(screens)}개)")
    for h in hits:
        res.facts.append(h)

    return res
