"""trace-crud: CRUD 매트릭스 (화면 × 테이블 × C/R/U/D) — ASIS와 TOBE를 나란히.

ASIS: 화면 → 서비스(RPC) → SQL → 테이블 (mapper를 AST로 해석한 R/C/U/D, `UpdateDataModel` 동적 쓰기 포함)
TOBE: TSX → api 함수 → 컨트롤러 → 서비스 → mapper 문장 → 테이블
범위는 `--screen`(한 화면), `--domain`(영역), `--table`(테이블을 쓰는 모든 화면) 중 하나. 아무것도 안 주면 영역별 요약.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from yunhee.tools.sql_parse import ParsedSql
from yunhee.tools.trace.flow import _DYNAMIC
from yunhee.tools.trace.render import TraceResult
from yunhee.tools.trace.resolve import TraceContext, resolve_screen
from yunhee.tools.trace.screen import ScreenDoc, parse_screen_doc
from yunhee.tools.trace.sqlscan import scan_asis, scan_tobe
from yunhee.tools.trace.table import _ops
from yunhee.tools.trace.tobe import TobeIndex, build_index, find_layout

MAX_ROWS = 40
ORDER = "CRUD"


def _fmt(ops: set[str]) -> str:
    return "".join(o for o in ORDER if o in ops) + ("W" if "W" in ops else "")


def sql_table_ops(scan: dict[str, ParsedSql]) -> dict[str, dict[str, set[str]]]:
    """문장 키 → {테이블: {C,R,U,D}}."""
    out: dict[str, dict[str, set[str]]] = {}
    for key, parsed in scan.items():
        out[key] = {t: set(_ops(parsed, t) or "R") for t in parsed.tables}
    return out


def udm_by_service(index_data: dict | None) -> dict[str, dict[str, set[str]]]:
    """서비스 키(`emp.Emp04_AddTitle.update`) → {테이블: 동적 쓰기}. `UpdateDataModel`의 updateModel은 등록/수정, deleteModel은 삭제."""
    out: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
    for cls, info in (index_data or {}).get("server_classes", {}).items():
        for m in info.get("methods", []):
            for call, table in m.get("udm_calls", []):
                out[f"{cls}.{m['name']}"][table.lower()] |= {"D"} if call == "deleteModel" else {"C", "U"}
    return out


def asis_matrix(doc: ScreenDoc, ops_by_sql: dict[str, dict[str, set[str]]], udm: dict[str, dict[str, set[str]]] | None = None) -> dict[str, set[str]]:
    """한 ASIS 화면(하위 클래스의 서비스 포함)의 {테이블: 작업}. SQL로 닿는 작업에 동적 쓰기(UpdateDataModel)를 더한다."""
    m: dict[str, set[str]] = defaultdict(set)
    for svc in doc.services:
        for sql_id in svc.sql_ids:
            for table, ops in ops_by_sql.get(sql_id, {}).items():
                m[table] |= ops
        for table, ops in (udm or {}).get(svc.key, {}).items():
            m[table] |= ops
        if not svc.sql_ids and not (udm or {}).get(svc.key) and (dyn := _DYNAMIC.search(svc.note)):
            m[dyn.group(1)] |= {"D"} if "DELETE" in dyn.group(2) else {"C", "U"}  # 색인 없이 화면 문서의 설명만 있는 경우
    return dict(m)


def tobe_matrix(names: list[str], idx: TobeIndex, ops_by_stmt: dict[str, dict[str, set[str]]]) -> dict[str, set[str]]:
    """ASIS 화면과 같은 이름의 TOBE TSX들이 api → 엔드포인트 → 서비스 → mapper 문장으로 닿는 {테이블: 작업}."""
    m: dict[str, set[str]] = defaultdict(set)
    for name in names:
        tsx = idx.tsx.get(name)
        if tsx is None:
            continue
        for obj, fn_name in tsx.api_calls:
            fn = idx.api_fns.get((obj, fn_name))
            if fn is None:
                continue
            for ep in idx.endpoint_of(fn):
                for st in idx.statements_of(ep):
                    for table, ops in ops_by_stmt.get(st.key, {}).items():
                        m[table] |= ops
    return dict(m)


def _compare(a: dict[str, set[str]], t: dict[str, set[str]]) -> list[str]:
    lines = []
    for table in sorted(set(a) | set(t)):
        sa, st = a.get(table, set()), t.get(table, set())
        note = ""
        if table not in t:
            note = "  ⚠ TOBE에 없음"
        elif table not in a:
            note = "  (TOBE에만)"
        elif sa != st:
            lost = sa - st
            note = (f"  ⚠ TOBE에 {_fmt(lost)} 없음" if lost else "") + (f"  (TOBE에 {_fmt(st - sa)} 추가)" if st - sa else "")
        lines.append(f"  {table}: ASIS {_fmt(sa) or '-'} / TOBE {_fmt(st) or '-'}{note}")
    return lines


def _domain_docs(ctx: TraceContext, domain: str | None) -> list[tuple[str, str, ScreenDoc]]:
    out = []
    if not ctx.src_index:
        return out
    for p in sorted(ctx.src_index.glob("*/screens/*.md")):
        if domain and p.parent.parent.name != domain:
            continue
        out.append((p.parent.parent.name, p.stem, parse_screen_doc(p.stem, p.read_text(encoding="utf-8", errors="replace"))))
    return out


def trace_crud(
    ctx: TraceContext, tobe: Path | None = None, domain: str | None = None, screen: str | None = None, table: str | None = None
) -> TraceResult:
    res = TraceResult(
        command="trace-crud",
        description="CRUD 매트릭스 (화면 × 테이블 × C/R/U/D, ASIS와 TOBE)",
        side=ctx.side,
        params={"domain": domain, "screen": screen, "table": table},
    )
    res.unresolved += ctx.unresolved
    if sum(x is not None for x in (domain, screen, table)) > 1:
        raise ValueError("--domain, --screen, --table 중 하나만 지정하세요")
    if not ctx.has_index:
        return res
    if not ctx.src_root or not Path(ctx.src_root).is_dir():
        res.unresolved.append("ASIS 소스를 찾지 못해 SQL의 테이블 작업을 해석하지 못함 (YUNHEE_ASIS_SRC_DIR)")
        return res
    a_ops = sql_table_ops(scan_asis(str(ctx.src_root)))
    udm = udm_by_service(ctx.index_data)
    layout = find_layout(tobe)
    idx = build_index(str(layout.root)) if layout.usable else None
    t_ops = sql_table_ops(scan_tobe(str(layout.mapper_dir))) if idx else {}
    if idx is None:
        res.unresolved.append(f"TOBE 소스를 찾지 못해 ASIS만 낸다 ({layout.root}) — --tobe로 지정")

    def tobe_for(name: str, doc: ScreenDoc) -> dict[str, set[str]]:
        return tobe_matrix([name, *[c for c in doc.ui if c != name]], idx, t_ops) if idx else {}

    if screen:
        name = resolve_screen(screen, ctx)
        res.params["resolved"] = name
        doc = next((d for _, n, d in _domain_docs(ctx, None) if n == name), None)
        if doc is None:
            res.unresolved.append(f"ASIS 색인 문서를 찾지 못함: {name}.md")
            return res
        a, t = asis_matrix(doc, a_ops, udm), tobe_for(name, doc)
        res.facts.append(f"화면 {name}: 테이블 {len(set(a) | set(t))}개 (ASIS {len(a)} / TOBE {len(t)})\n" + "\n".join(_compare(a, t)))
    elif table:
        tbl = table.lower()
        rows = []
        for _, name, doc in _domain_docs(ctx, None):
            if f"`{tbl}`" not in " ".join(f"`{x}`" for x in doc.tables) and not any(tbl in (s.note or "") for s in doc.services):
                continue
            a, t = asis_matrix(doc, a_ops, udm), tobe_for(name, doc)
            if tbl in a or tbl in t:
                sa, st = a.get(tbl, set()), t.get(tbl, set())
                rows.append(f"  {name}: ASIS {_fmt(sa) or '-'} / TOBE {_fmt(st) or '-'}" + (f"  ⚠ TOBE에 {_fmt(sa - st)} 없음" if sa - st and idx else ""))
        res.facts.append(f"테이블 {tbl}을(를) 쓰는 화면 {len(rows)}개\n" + ("\n".join(rows) if rows else "  (없음 — 화면 서비스에서 이 테이블에 닿는 SQL이 없음)"))
    else:
        docs = _domain_docs(ctx, domain)
        if not docs:
            res.unresolved.append(f"영역 '{domain}'의 화면을 색인에서 찾지 못함")
            return res
        if domain:
            lines, per_table = [], defaultdict(lambda: defaultdict(set))
            for _, name, doc in docs:
                a, t = asis_matrix(doc, a_ops, udm), tobe_for(name, doc)
                counts = {op: sum(op in v for v in a.values()) for op in ORDER}
                lost = sorted(tb for tb in a if idx and name in idx.tsx and a[tb] - t.get(tb, set()) - {"R"})
                lines.append(
                    f"  {name}: ASIS 테이블 {len(a)}(" + " ".join(f"{op}{n}" for op, n in counts.items()) + f") / TOBE {len(t)}"
                    + ("" if idx and name in idx.tsx else " — TOBE에 화면 없음")
                    + (f"  ⚠ TOBE에 없는 쓰기: {', '.join(lost[:6])}{' …' if len(lost) > 6 else ''}" if lost else "")
                )
                for tb, ops in a.items():
                    for op in ops:
                        per_table[tb][op].add(name)
            res.facts.append(f"영역 {domain}: 화면 {len(docs)}개 — 화면별 ASIS 테이블 작업 수(C/R/U/D)와 TOBE\n" + "\n".join(lines[:MAX_ROWS]) + (f"\n  … 외 {len(lines) - MAX_ROWS}개" if len(lines) > MAX_ROWS else ""))
            trows = [f"  {tb}: " + " ".join(f"{op}({len(per_table[tb][op])})" for op in ORDER if per_table[tb][op]) for tb in sorted(per_table, key=lambda x: -sum(len(v) for v in per_table[x].values()))]
            res.facts.append(f"테이블별 쓰는 화면 수 — {len(trows)}개 테이블\n" + "\n".join(trows[:MAX_ROWS]) + (f"\n  … 외 {len(trows) - MAX_ROWS}개" if len(trows) > MAX_ROWS else ""))
        else:
            by_domain: dict[str, list[dict[str, set[str]]]] = defaultdict(list)
            for dom, _name, doc in docs:
                by_domain[dom].append(asis_matrix(doc, a_ops, udm))
            summary = []
            for dom, mats in sorted(by_domain.items()):
                tables = set().union(*[set(m) for m in mats])
                pairs = {op: sum(op in ops for m in mats for ops in m.values()) for op in ORDER}
                summary.append(f"  {dom}: 화면 {len(mats)}, 테이블 {len(tables)}, 화면×테이블 작업 " + " ".join(f"{op}{n}" for op, n in pairs.items()))
            res.facts.append(f"영역별 요약 {len(summary)}개 — `--domain <영역>`·`--screen <화면>`·`--table <테이블>`로 좁혀서 본다\n" + "\n".join(summary))
    res.unresolved.append("R은 SQL이 그 테이블을 읽는다는 뜻이다 (서브쿼리·JOIN 포함). 동적 쓰기(UpdateDataModel)는 ASIS에서 C/U 또는 D로만 센다")
    return res

