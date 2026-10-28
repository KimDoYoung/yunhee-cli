"""trace-diff: 짝지어진 ASIS↔TOBE의 차이 — SQL 정규화 diff, 분기 대응표, UI 필드 대응표.

짝은 trace-pair와 같은 근거(AS-IS 주석)로 짓는다. 차이는 사실로만 낸다 (왜 달라졌는지, 의도적인지는 에이전트가 판정해 trace-rule에 남긴다).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from yunhee.tools.trace.branch import (
    Cond,
    _mapper_conditions,
    scan_java_conditions,
    scan_tsx_conditions,
)
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import TraceContext
from yunhee.tools.trace.screen import ClassUi
from yunhee.tools.trace.tobe import (
    MapperStatement,
    TobeIndex,
    TsxInfo,
    build_index,
    find_layout,
)

MAX_ITEMS = 12
_KEYWORDS = {"null", "true", "false", "and", "or", "not", "test", "in", "is", "size", "length", "empty", "equals", "eq", "ne"}


def _norm_name(name: str) -> str:
    """컬럼·별칭·변수 이름을 비교용으로: 소문자, 밑줄·따옴표 제거, 선행 `is` 제거(isSeparateAddTitle ↔ separateAddTitle)."""
    n = re.sub(r"[^0-9a-z]", "", name.lower())
    return n[2:] if n.startswith("is") and len(n) > 4 else n


def _tokens(cond: str) -> frozenset[str]:
    return frozenset(_norm_name(t) for t in re.findall(r"[A-Za-z_][A-Za-z0-9_]*", cond) if t.lower() not in _KEYWORDS)


def _shown(items: list[str], limit: int = MAX_ITEMS) -> str:
    items = sorted(items)
    return ", ".join(items[:limit]) + (f" … 외 {len(items) - limit}개" if len(items) > limit else "")


def _split_and(where: str) -> list[str]:
    """최상위 AND로 WHERE 식을 나눈다 (괄호·문자열 안은 건드리지 않는다)."""
    parts, depth, cur, i = [], 0, [], 0
    in_str = False
    while i < len(where):
        c = where[i]
        if c == "'":
            in_str = not in_str
        elif not in_str:
            depth += (c == "(") - (c == ")")
            if depth == 0 and where[i : i + 5].upper() == " AND ":
                parts.append("".join(cur).strip())
                cur, i = [], i + 5
                continue
        cur.append(c)
        i += 1
    parts.append("".join(cur).strip())
    return [re.sub(r"\s+", " ", p).lower() for p in parts if p]


# ---------------------------------------------------------------------------
# --sql
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _schema() -> dict[str, list[str]] | None:
    """스키마 스냅샷의 테이블 → 컬럼. 한정자 없는 컬럼의 귀속과 `SELECT *` 확장에 쓴다. 없으면 None."""
    from yunhee import config
    from yunhee.tools.schema_snapshot import load_snapshot
    from yunhee.tools.sql_parse import schema_from_snapshot

    snap = load_snapshot(config.SCHEMA_ENV)
    return schema_from_snapshot(snap.data) if snap.ok else None


def compare_sql(asis_key: str, a_stmts: dict[str, Any], tobe_key: str, t_stmts: dict[str, Any]) -> list[str]:
    """두 문장의 구조 차이. 같으면 `차이 없음`만, 다르면 항목별로 한 줄씩."""
    from yunhee.tools.as_is.mybatis_render import render
    from yunhee.tools.as_is.sql_drift import normalize_sql_for_drift
    from yunhee.tools.sql_parse import parse_statement

    schema = _schema()
    a, t = parse_statement(asis_key, a_stmts, schema), parse_statement(tobe_key, t_stmts, schema)
    if not a.ok or not t.ok:
        return [f"  (해석 실패: {a.error or t.error})"]
    pa, pt = a.data, t.data
    lines: list[str] = []

    def delta(label: str, sa: set[str], st: set[str]) -> None:
        if sa != st:
            lines.append(f"  {label}: ASIS만 [{_shown(list(sa - st))}] / TOBE만 [{_shown(list(st - sa))}]")

    delta("테이블", set(pa.tables), set(pt.tables))
    delta("쓰기 작업", {f"{a_}:{t_}" for a_, t_ in pa.writes}, {f"{a_}:{t_}" for a_, t_ in pt.writes})
    cols_a = {f"{tb}.{c}" for tb, cs in pa.columns.items() for c in cs}
    cols_t = {f"{tb}.{c}" for tb, cs in pt.columns.items() for c in cs}
    delta("사용 컬럼", cols_a, cols_t)
    if pa.output_names is not None and pt.output_names is not None:
        delta("출력 이름", {_norm_name(n) for n in pa.output_names if n}, {_norm_name(n) for n in pt.output_names if n})
    where_a = {w for x in pa.where for w in _split_and(x)} - {"1 = 1"}  # explain 렌더링이 붙인 WHERE 1=1은 조건이 아니다
    where_t = {w for x in pt.where for w in _split_and(x)} - {"1 = 1"}
    delta("WHERE 조건", where_a, where_t)
    delta("CTE", set(pa.ctes), set(pt.ctes))
    delta("함수", set(pa.functions), set(pt.functions))
    if len(pa.cases) != len(pt.cases):
        lines.append(f"  CASE WHEN 수: ASIS {len(pa.cases)} / TOBE {len(pt.cases)}")
    na, nt = (normalize_sql_for_drift(render(k, mode="explain", statements=s)[0]) for k, s in ((asis_key, a_stmts), (tobe_key, t_stmts)))
    lines.append("  정규화 SQL: " + ("동일" if na == nt else "다름 (공백·대소문자·주석을 무시한 비교)"))
    for u in dict.fromkeys(pa.unresolved + pt.unresolved):
        lines.append(f"  ⚠ {u}")
    if schema is None:
        lines.append("  ⚠ 스키마 스냅샷이 없어 한정자 없는 컬럼의 귀속과 SELECT * 확장을 하지 못함")
    return lines if len(lines) > 1 else ["  차이 없음"] + lines


# ---------------------------------------------------------------------------
# --branch
# ---------------------------------------------------------------------------


def _pair_conditions(a: list[Cond], t: list[Cond]) -> tuple[list[tuple[Cond, Cond]], list[Cond], list[Cond]]:
    """식별자 집합이 같은 조건끼리 짝짓는다. (같은 식별자 = 근거)"""
    by_tokens: dict[frozenset[str], list[Cond]] = {}
    for c in t:
        by_tokens.setdefault(_tokens(c.text), []).append(c)
    pairs, a_only, used = [], [], set()
    for c in a:
        key = _tokens(c.text)
        cand = next((x for x in by_tokens.get(key, []) if id(x) not in used), None) if key else None
        if cand is not None:
            used.add(id(cand))
            pairs.append((c, cand))
        else:
            a_only.append(c)
    return pairs, a_only, [c for c in t if id(c) not in used]


def _cond_line(c: Cond) -> str:
    return f"L{c.line} {c.kind} {c.text}"


def _branch_table(label: str, a: list[Cond], t: list[Cond]) -> str:
    pairs, a_only, t_only = _pair_conditions(a, t)
    body = [f"{label}: ASIS {len(a)} / TOBE {len(t)} — 대응 {len(pairs)}, ASIS만 {len(a_only)}, TOBE만 {len(t_only)}"]
    body += [f"  ≈ ASIS {_cond_line(x)}  ↔  TOBE {_cond_line(y)}  [근거: 같은 식별자 {', '.join(sorted(_tokens(x.text)))}]" for x, y in pairs[:MAX_ITEMS]]
    body += [f"  ASIS만: {_cond_line(x)}" for x in a_only[:MAX_ITEMS]]
    body += [f"  TOBE만: {_cond_line(y)}" for y in t_only[:MAX_ITEMS]]
    return "\n".join(body)


def _dynamic(st: Any, statements: dict[str, Any]) -> list[Cond]:
    out: list[Cond] = []
    _mapper_conditions(st, statements, set(), out)
    return [c for c in out if c.text and c.kind in ("if", "when") and "isTibero" not in c.text and "isPostgreSql" not in c.text]


# ---------------------------------------------------------------------------
# --ui
# ---------------------------------------------------------------------------

_GRID_COL = re.compile(r'^(\w+)\s+\d+\s+"(.*)"\s+\w+$')


def _ui_compare(cls: str, ui: ClassUi, tsx: TsxInfo) -> list[str]:
    lines: list[str] = []
    a_cols = [(m.group(1), m.group(2)) for g in ui.grids for c in g[1] if (m := _GRID_COL.match(c))]
    t_cols = tsx.grid_cols
    if a_cols or t_cols:
        t_by_label = {lab.strip(): f for f, lab in t_cols}
        a_labels = {lab.strip() for _, lab in a_cols}
        same = [(f, lab) for f, lab in a_cols if lab.strip() in t_by_label]
        renamed = [f"{lab}({f}→{t_by_label[lab.strip()]})" for f, lab in same if f != t_by_label[lab.strip()]]
        lines.append(f"  그리드 열: ASIS {len(a_cols)} / TOBE {len(t_cols)} — 같은 라벨 {len(same)} [근거: 라벨 일치]")
        if renamed:
            lines.append(f"    필드 이름이 바뀜({len(renamed)}): {_shown(renamed, 6)}")
        a_only = [f"{lab}({f})" for f, lab in a_cols if lab.strip() not in t_by_label]
        t_only = [f"{lab}({f})" for f, lab in t_cols if lab.strip() not in a_labels]
        if a_only:
            lines.append(f"    ASIS에만: {_shown(a_only)}")
        if t_only:
            lines.append(f"    TOBE에만: {_shown(t_only)}")
    a_btn = [b.split(" [")[0].strip() for b in ui.buttons]
    if a_btn or tsx.buttons:
        a_only_b = [b for b in a_btn if b not in tsx.buttons]
        t_only_b = [b for b in tsx.buttons if b not in a_btn]
        lines.append(f"  버튼: ASIS {len(a_btn)} / TOBE {len(tsx.buttons)} — 같은 라벨 {len(a_btn) - len(a_only_b)}"
                     + (f"; ASIS에만 [{_shown(a_only_b)}]" if a_only_b else "") + (f"; TOBE에만 [{_shown(t_only_b)}]" if t_only_b else ""))
    if ui.event_rows:
        ids = [e.id for e in ui.event_rows]
        dead = {e.id for e in ui.event_rows if e.unreachable}
        impl = [i for i in ids if i in tsx.impl_events]
        skipped = [i for i in ids if i in tsx.skipped_events]
        none = [i for i in ids if i not in tsx.impl_events and i not in tsx.skipped_events and i not in dead]
        lines.append(f"  이벤트: ASIS {len(ids)} — 구현 표시 {len(impl)}, 생략 표시 {len(skipped)}, 도달 불가 {len(dead)}, 표시 없음 {len(none)}"
                     + (f" [{_shown(none)}]" if none else ""))
    return lines or ["  (비교할 그리드·버튼·이벤트가 없음)"]


# ---------------------------------------------------------------------------


def _screen_parts(target: str, ctx: TraceContext, idx: TobeIndex, res: TraceResult):
    from yunhee.tools.trace.pair import load_asis_screen, pair_services, screen_tsx

    name, doc, _ = load_asis_screen(target, ctx)
    res.params["resolved"] = name
    if doc is None:
        res.unresolved.append(f"ASIS 색인 문서를 찾지 못함: {name}.md")
        return None
    tsx_list, _ = screen_tsx(idx, name, doc)
    pairs, _ = pair_services(doc, idx, tsx_list)
    return name, doc, tsx_list, [p for p in pairs if p.endpoints]


def trace_diff(target: str, ctx: TraceContext, tobe: Path | None = None, sql: bool = False, branch: bool = False, ui: bool = False) -> TraceResult:
    res = TraceResult(
        command="trace-diff",
        description="SQL 정규화 diff, 분기 대응표, UI 필드 대응표",
        side="both",
        params={"target": target, "sql": sql, "branch": branch, "ui": ui},
    )
    res.unresolved += ctx.unresolved
    if not (sql or branch or ui):
        sql = branch = ui = True
        res.params.update(sql=True, branch=True, ui=True)
    idx = build_index(str(find_layout(tobe).root))
    if not idx.layout.usable:
        res.unresolved.append(f"TOBE 소스를 찾지 못함 ({idx.layout.root}) — --tobe로 프로젝트 루트(또는 frontend/src)를 지정")
        return res

    from yunhee.tools.trace.pair import (
        asis_statements,
        compute_sql_pairs,
        reached_statements,
        tobe_statements,
    )

    a_stmts, t_stmts = asis_statements(ctx), tobe_statements(idx)
    is_mapper = bool(a_stmts and "." in target and target in a_stmts and a_stmts[target].kind != "sql")
    sql_pairs: list[tuple[str, list[MapperStatement], str]] = []
    parts = None
    if is_mapper:
        res.params["kind"] = "mapper"
        found = [s for s in idx.statements.values() if target in s.as_is_ids]
        sql_pairs = [(target, found, "문장 주석의 AS-IS id")] if found else []
        if not found:
            res.facts.append(f"짝 없음: TOBE 문장 주석에 AS-IS {target}를 적은 문장이 없음")
        if ui:
            res.unresolved.append("--ui는 화면 대상에서만 의미가 있음 (mapper id에는 건너뜀)")
    elif ctx.has_index:
        res.params["kind"] = "screen"
        parts = _screen_parts(target, ctx, idx, res)
        if parts is not None:
            _, _, _, done = parts
            sql_pairs, _ = compute_sql_pairs(done, idx, reached_statements(done, idx), a_stmts, t_stmts)
    else:
        return res

    if sql and sql_pairs and a_stmts:
        body: list[str] = []
        for sql_id, found, basis in sql_pairs:
            for st in found[:2]:
                body.append(f"- {sql_id} ↔ {st.key.split('.')[-2]}.{st.id} [근거: {basis}]")
                body += compare_sql(sql_id, a_stmts, st.key, t_stmts)
                res.evidence.append(f"TOBE {idx.rel(st.file)}:{st.line} {st.id}")
        res.facts.append(f"SQL 정규화 diff({len(sql_pairs)}쌍):\n" + "\n".join("  " + b if not b.startswith("  ") else b for b in body))
    elif sql and not sql_pairs and res.params.get("kind") == "screen":
        res.facts.append("SQL diff: 짝지어진 SQL이 없음 (trace-pair로 대응을 먼저 확인)")
    elif sql and a_stmts is None:
        res.unresolved.append("ASIS 소스를 찾지 못해 SQL diff를 건너뜀")

    if branch:
        if is_mapper and sql_pairs and a_stmts:
            for sql_id, found, _ in sql_pairs:
                for st in found[:2]:
                    res.facts.append(_branch_table(f"분기 대응 {sql_id} ↔ {st.id}", _dynamic(a_stmts[sql_id], a_stmts), _dynamic(t_stmts[st.key], t_stmts)))
        elif parts is not None:
            name, doc, tsx_list, _ = parts
            _branch_screen(name, doc, tsx_list, ctx, res, sql_pairs, a_stmts, t_stmts)

    if ui and parts is not None:
        name, doc, tsx_list, _ = parts
        body = []
        for tsx in tsx_list:
            u = doc.ui.get(tsx.name)
            if u is None:
                continue
            body.append(f"- {tsx.name}")
            body += _ui_compare(tsx.name, u, tsx)
            res.evidence.append(f"TOBE {idx.rel(tsx.file)}")
        res.unresolved.append("TOBE 버튼은 <Button>의 글자와 이벤트 주석의 [버튼[라벨]]만 센다 — 다른 컴포넌트가 만드는 버튼은 빠질 수 있음")
        res.facts.append(f"UI 대응표({len([b for b in body if b.startswith('- ')])}개 클래스):\n" + ("\n".join("  " + b if b.startswith("- ") else b for b in body) if body else "  (짝지어진 TSX 없음)"))
    return res


def _branch_screen(name: str, doc: Any, tsx_list: list[TsxInfo], ctx: TraceContext, res: TraceResult, sql_pairs, a_stmts, t_stmts) -> None:
    from yunhee.tools.trace.branch import _class_source

    a_conds: list[Cond] = []
    src = _class_source(ctx, name, doc)
    if src is not None:
        a_conds = scan_java_conditions(src.read_text(encoding="utf-8", errors="replace"))
    else:
        res.unresolved.append(f"{name}의 Java 소스를 찾지 못해 화면 분기를 건너뜀")
    main_tsx = next((t for t in tsx_list if t.name == name), None)
    t_conds = scan_tsx_conditions(Path(main_tsx.file).read_text(encoding="utf-8", errors="replace")) if main_tsx else []
    if main_tsx is None:
        res.unresolved.append(f"TOBE {name}.tsx가 없어 화면 분기를 건너뜀")
    else:
        res.facts.append(_branch_table(f"화면 분기 대응 {name}", a_conds, t_conds))
        res.unresolved.append("화면 분기는 식별자 집합이 같은 조건만 짝짓는다 — Java(GXT)와 React는 식이 달라 대응이 적게 나올 수 있고, 대응이 없다고 구현이 빠졌다는 뜻은 아니다")
    if sql_pairs and a_stmts:
        rows = []
        for sql_id, found, _ in sql_pairs:
            for st in found[:1]:
                a, t = _dynamic(a_stmts[sql_id], a_stmts), _dynamic(t_stmts[st.key], t_stmts)
                if a or t:
                    pairs, ao, to = _pair_conditions(a, t)
                    rows.append(f"  - {sql_id} ↔ {st.id}: ASIS {len(a)} / TOBE {len(t)} — 대응 {len(pairs)}, ASIS만 {len(ao)}, TOBE만 {len(to)}")
        if rows:
            res.facts.append("SQL 동적 분기 대응(상세는 `trace-diff <mapper id> --branch`):\n" + "\n".join(rows[:30]))
