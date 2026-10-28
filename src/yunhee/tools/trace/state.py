"""trace-state: 컬럼에 값을 쓰는 모든 INSERT/UPDATE, 대입 값, 그 SQL의 WHERE 조건 — 상태 전이를 그릴 재료.

전이도를 그리는 것은 에이전트의 몫이다. 여기서는 "어느 SQL이 어떤 조건에서 어떤 값을 쓰는가"만 사실로 낸다.
파라미터는 `#{status}` 형태로 남겨, 값이 상수인지 호출자가 정하는 값인지 구분할 수 있게 한다.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from yunhee import config
from yunhee.tools.schema_snapshot import load_snapshot
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import (
    TargetNotFoundError,
    TraceContext,
    wants_asis,
    wants_tobe,
)
from yunhee.tools.trace.tobe import build_index, find_layout

MAX_PER_VALUE = 8
MAX_SQL_LINES = 40
_PARAM = re.compile(r'"?__p_(\w+)"?')


@dataclass
class StateWrite:
    sql: str  # 문장 키 (ASIS `ns.id`, TOBE `Mapper.id`)
    action: str  # INSERT / UPDATE / CONFLICT
    value: str
    where: str
    where_ref: str  # 파일:줄


def show_params(text: str) -> str:
    """`"__p_statCd"` → `#{statCd}`."""
    return _PARAM.sub(lambda m: "#{" + m.group(1) + "}", text)


def _compare_key(value: str) -> str:
    """대입 값 비교용: 파라미터 이름은 대소문자·밑줄을 무시하고(statCd ≡ stat_cd), 나머지는 공백만 정규화."""
    v = re.sub(r"\s+", " ", show_params(value)).strip()
    return re.sub(r"#\{(\w+)\}", lambda m: "#{" + re.sub(r"[^0-9a-z]", "", m.group(1).lower()) + "}", v)


def split_ref(col_ref: str) -> tuple[str, str]:
    m = re.fullmatch(r"(?:\w+\.)?([A-Za-z_]\w*)\.([A-Za-z_]\w*)", col_ref.strip())
    if not m:
        raise ValueError(f"테이블.컬럼 형식이어야 합니다 (예: fnd01_fund.stat_cd): {col_ref}")
    return m.group(1).lower(), m.group(2).lower()


def _scan(statements: dict[str, Any], where_of: Any) -> tuple[dict[tuple[str, str], list[StateWrite]], int]:
    """모든 문장을 해석해 (테이블, 컬럼) → 쓰는 SQL 목록. 두 번째 값은 AST로 해석하지 못한 문장 수."""
    from yunhee.tools.sql_parse import parse_statement

    out: dict[tuple[str, str], list[StateWrite]] = defaultdict(list)
    fallback = 0
    for key in sorted({s.key for s in statements.values() if s.kind != "sql"}):
        res = parse_statement(key, statements, keep_params=True)
        if not res.ok:
            continue
        parsed = res.data
        fallback += parsed.fallback
        for a in parsed.assignments:
            out[(a.table, a.column)].append(StateWrite(key, a.action, a.value, a.where, where_of(statements[key])))
    return dict(out), fallback


@lru_cache(maxsize=2)
def _asis_writes(src_root: str) -> tuple[dict[tuple[str, str], list[StateWrite]], int]:
    from yunhee.tools.as_is.mybatis_render import get_all_statements

    return _scan(get_all_statements(Path(src_root)), lambda st: f"{st.rel}:{st.line}")


@lru_cache(maxsize=2)
def _tobe_writes(root: str) -> tuple[dict[tuple[str, str], list[StateWrite]], int]:
    from yunhee.tools.as_is.mybatis_render import load_statements

    idx = build_index(root)
    stmts = load_statements(idx.layout.mapper_dir) if idx.layout.mapper_dir.is_dir() else {}
    return _scan(stmts, lambda st: f"{Path(str(st.rel)).name}:{st.line}")


def _by_value(writes: list[StateWrite]) -> dict[str, list[StateWrite]]:
    groups: dict[str, list[StateWrite]] = defaultdict(list)
    for w in writes:
        groups[show_params(re.sub(r"\s+", " ", w.value).strip())].append(w)
    return dict(sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0])))


def _value_lines(side: str, writes: list[StateWrite]) -> list[str]:
    lines = []
    for value, ws in _by_value(writes).items():
        who = ", ".join(f"{w.sql}({w.action})" for w in ws[:MAX_PER_VALUE])
        more = f" … 외 {len(ws) - MAX_PER_VALUE}개" if len(ws) > MAX_PER_VALUE else ""
        lines.append(f"  {value} ← {who}{more}")
    return lines


def _sql_lines(writes: list[StateWrite]) -> list[str]:
    lines = []
    for w in writes[:MAX_SQL_LINES]:
        cond = show_params(w.where) if w.where else ("(WHERE 없음 — 모든 행)" if w.action == "UPDATE" else "")
        lines.append(f"  - {w.sql} [{w.action}] {w.where_ref}\n      값: {show_params(w.value)}" + (f"\n      조건: {cond}" if cond else ""))
    if len(writes) > MAX_SQL_LINES:
        lines.append(f"  … 외 {len(writes) - MAX_SQL_LINES}개")
    return lines


def _dynamic_writers(ctx: TraceContext, table: str) -> list[str]:
    out = []
    for cls, info in (ctx.index_data or {}).get("server_classes", {}).items():
        for m in info.get("methods", []):
            for call, tbl in m.get("udm_calls", []):
                if tbl.lower() == table:
                    out.append(f"{cls}.{m['name']} ({'삭제' if call == 'deleteModel' else '등록/수정'})")
    return sorted(set(out))


def trace_state(col_ref: str, ctx: TraceContext, tobe: Path | None = None, schema_env: str | None = None) -> TraceResult:
    table, column = split_ref(col_ref)
    res = TraceResult(
        command="trace-state",
        description="이 컬럼에 값을 쓰는 모든 INSERT/UPDATE, 대입 값, 그 SQL의 WHERE 조건 (상태 전이 재료)",
        side=ctx.side,
        params={"col_ref": f"{table}.{column}"},
    )
    res.unresolved += ctx.unresolved
    snap = load_snapshot(schema_env or config.SCHEMA_ENV)
    if snap.ok:
        tbl = next((t for t in snap.data.get("tables", []) if t["name"].lower() == table), None)
        if tbl is None:
            raise TargetNotFoundError(col_ref)
        col = next((c for c in tbl.get("columns", []) if c["name"].lower() == column), None)
        if col is None:
            raise TargetNotFoundError(col_ref, [f"{table}.{c['name']}" for c in tbl["columns"] if column[:6] in c["name"].lower()][:5])
        res.facts.append(f"컬럼: {table}.{column} {col['type']}" + (f" — {col['note']}" if col.get("note") else ""))
    else:
        res.unresolved.append(f"스키마 스냅샷을 읽지 못해 {col_ref}가 실제 컬럼인지 확인하지 못함")

    keys = (table, column)
    asis_vals: dict[str, list[StateWrite]] = {}
    tobe_vals: dict[str, list[StateWrite]] = {}
    if wants_asis(ctx.side):
        if not ctx.src_root or not Path(ctx.src_root).is_dir():
            res.unresolved.append("ASIS 소스를 찾지 못해 ASIS의 쓰기를 구하지 못함 (YUNHEE_ASIS_SRC_DIR)")
        else:
            writes_map, fallback = _asis_writes(str(ctx.src_root))
            writes = writes_map.get(keys, [])
            asis_vals = _by_value(writes)
            _report(res, "ASIS", writes)
            if fallback:
                res.unresolved.append(f"ASIS mapper {fallback}개는 PostgreSQL 문법이 아니라 대입을 읽지 못함 — 이 컬럼을 쓰는 SQL이 더 있을 수 있음")
            dyn = _dynamic_writers(ctx, table)
            if dyn:
                res.facts.append(
                    f"동적 쓰기(UpdateDataModel, {len(dyn)}) — 어떤 컬럼에 무엇을 쓰는지는 클라이언트가 보내는 모델이 정하므로 SQL로는 알 수 없음:\n"
                    + "\n".join(f"  - {d}" for d in dyn[:12])
                )
    if wants_tobe(ctx.side):
        layout = find_layout(tobe)
        if not layout.usable or not layout.mapper_dir.is_dir():
            res.unresolved.append(f"TOBE mapper를 찾지 못함 ({layout.root}) — --tobe로 지정")
        else:
            writes_map, fallback = _tobe_writes(str(layout.root))
            writes = writes_map.get(keys, [])
            tobe_vals = _by_value(writes)
            _report(res, "TOBE", writes)
            if fallback:
                res.unresolved.append(f"TOBE mapper {fallback}개는 대입을 읽지 못함")
    if asis_vals and tobe_vals:
        a = {_compare_key(v): v for v in asis_vals}
        t = {_compare_key(v): v for v in tobe_vals}
        only_a, only_t = [a[k] for k in a.keys() - t.keys()], [t[k] for k in t.keys() - a.keys()]
        res.facts.append(
            f"대입 값 비교: 같음 {len(a.keys() & t.keys())} / ASIS에만 {len(only_a)} / TOBE에만 {len(only_t)}"
            + (f"\n  ASIS에만: {', '.join(sorted(only_a))}" if only_a else "")
            + (f"\n  TOBE에만: {', '.join(sorted(only_t))}" if only_t else "")
        )
    elif asis_vals and wants_tobe(ctx.side) and not tobe_vals:
        res.facts.append("대입 값 비교: TOBE에는 이 컬럼을 쓰는 SQL이 없음")
    return res


def _report(res: TraceResult, side: str, writes: list[StateWrite]) -> None:
    if not writes:
        res.facts.append(f"{side}: 이 컬럼에 값을 쓰는 SQL을 찾지 못함 (INSERT 컬럼 목록·UPDATE SET에 없음)")
        return
    groups = _by_value(writes)
    res.facts.append(f"{side}: 쓰는 SQL {len(writes)}개, 대입 값 {len(groups)}종\n" + "\n".join(_value_lines(side, writes)))
    res.facts.append(f"{side} SQL별 값과 조건:\n" + "\n".join(_sql_lines(writes)))
    res.evidence += [f"{side} {w.where_ref} {w.sql}" for w in writes[:MAX_SQL_LINES]]
