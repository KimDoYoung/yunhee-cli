"""PostgreSQL SQL 해석 어댑터 — pglast(libpg_query) AST로 테이블·CTE·함수·컬럼·출력 이름·대입을 구한다.

MyBatis mapper는 `mybatis_render`의 `explain` 모드로 순수 SQL로 전개한 뒤 파싱한다.
파싱이 실패하면 정규식으로 추정하고 결과에 `fallback=True`를 표시한다 (틀린 값을 사실처럼 내지 않기 위해).
파서 호출은 이 모듈에만 둔다 (파서 교체 지점).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from pglast import ast, parse_sql
from pglast.parser import ParseError
from pglast.stream import RawStream

from yunhee.tools.base import ToolResult

Schema = dict[str, list[str]]  # 테이블명(소문자) → 컬럼명 목록 (스냅샷에서 만든다)

_FALLBACK_TABLE_RE = re.compile(r"\b(?:from|join|into|update)\s+([a-z_][a-z0-9_]*)", re.IGNORECASE)
_FALLBACK_CTE_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s+as\s*\(", re.IGNORECASE)
_SQL_NOISE = {"select", "set", "values", "where", "lateral", "only", "unnest", "generate_series"}


@dataclass
class Assignment:
    """UPDATE SET / INSERT 값 한 건: 어느 테이블의 어느 컬럼에 어떤 식을 쓰는가."""

    table: str
    column: str
    value: str


@dataclass
class ParsedSql:
    kind: str = "other"  # select / insert / update / delete / other
    tables: dict[str, str] = field(default_factory=dict)  # 테이블명 → "R" / "W" / "RW"
    ctes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    columns: dict[str, list[str]] = field(default_factory=dict)  # 테이블명 → 사용된 컬럼
    output_names: list[str | None] | None = None  # 최상위 SELECT 출력 이름. `*`를 알 수 없으면 None
    assignments: list[Assignment] = field(default_factory=list)
    where: list[str] = field(default_factory=list)  # 최상위 문장의 WHERE 식
    unresolved: list[str] = field(default_factory=list)
    fallback: bool = False  # True면 AST가 아니라 정규식 추정 결과
    error: str | None = None


def schema_from_snapshot(snapshot: dict[str, Any]) -> Schema:
    """스키마 스냅샷(`tools/schema_snapshot.load_snapshot().data`)에서 테이블 → 컬럼 맵을 만든다."""
    return {t["name"].lower(): [c["name"].lower() for c in t.get("columns", [])] for t in snapshot.get("tables", [])}


def _text(node: Any) -> str:
    try:
        return RawStream()(node)
    except Exception:  # noqa: BLE001 - 출력은 보조 정보라 실패해도 파싱 결과는 살린다
        return "<?>"


def _strings(fields: tuple[Any, ...]) -> list[str]:
    return [f.sval.lower() for f in fields if isinstance(f, ast.String)]


class _Collector:
    """AST를 한 번 훑어 테이블·CTE·함수·컬럼 참조를 모은다."""

    def __init__(self) -> None:
        self.read: set[str] = set()
        self.written: set[str] = set()
        self.ctes: list[str] = []
        self.functions: list[str] = []
        self.alias: dict[str, str] = {}  # 별칭 → 테이블명
        self.column_refs: list[list[str]] = []  # ColumnRef의 이름 조각 (소문자)

    def walk(self, node: Any) -> None:
        if isinstance(node, ast.Node):
            self._visit(node)
            for name in node:
                self.walk(getattr(node, name))
        elif isinstance(node, (list, tuple)):
            for item in node:
                self.walk(item)

    def _visit(self, node: ast.Node) -> None:
        if isinstance(node, ast.CommonTableExpr):
            self.ctes.append(node.ctename.lower())
        elif isinstance(node, ast.RangeVar):
            name = node.relname.lower()
            self.read.add(name)
            if node.alias:
                self.alias[node.alias.aliasname.lower()] = name
        elif isinstance(node, (ast.InsertStmt, ast.UpdateStmt, ast.DeleteStmt)):
            rel = node.relation
            name = rel.relname.lower()
            self.written.add(name)
            if rel.alias:
                self.alias[rel.alias.aliasname.lower()] = name
        elif isinstance(node, ast.FuncCall):
            parts = _strings(node.funcname)
            if parts:
                self.functions.append(parts[-1])
        elif isinstance(node, ast.ColumnRef) and not any(isinstance(f, ast.A_Star) for f in node.fields):
            self.column_refs.append(_strings(node.fields))  # `*`는 output_names에서 다룬다


def _top_select(stmt: Any) -> Any:
    """UNION이면 왼쪽 가지의 SELECT를 따라 내려간다 (출력 이름은 첫 SELECT 기준)."""
    while isinstance(stmt, ast.SelectStmt) and stmt.larg is not None:
        stmt = stmt.larg
    return stmt


def _output_names(select: Any, resolve_star: Any) -> list[str | None] | None:
    names: list[str | None] = []
    for target in select.targetList or ():
        val = target.val
        if target.name:
            names.append(target.name)
        elif isinstance(val, ast.ColumnRef):
            last = val.fields[-1]
            if isinstance(last, ast.A_Star):
                expanded = resolve_star(_strings(val.fields)[-1] if len(val.fields) > 1 else None)
                if expanded is None:
                    return None
                names.extend(expanded)
            else:
                names.append(last.sval)
        elif isinstance(val, ast.FuncCall):
            names.append(val.funcname[-1].sval)
        else:
            names.append(None)  # 이름을 정할 수 없는 식
    return names


def parse_sql_text(sql: str, schema: Schema | None = None) -> ParsedSql:
    """순수 PostgreSQL SQL 한 문장을 해석한다. 문법 오류면 정규식 추정(fallback)으로 되돌린다."""
    try:
        stmts = parse_sql(sql)
    except ParseError as exc:
        return _fallback(sql, str(exc))
    if not stmts:
        return ParsedSql(unresolved=["빈 SQL"])
    result = ParsedSql()
    if len(stmts) > 1:
        result.unresolved.append(f"문장이 {len(stmts)}개 — 첫 문장만 해석함")
    root = stmts[0].stmt

    col = _Collector()
    col.walk(root)
    cte_set = set(col.ctes)

    kinds = {ast.SelectStmt: "select", ast.InsertStmt: "insert", ast.UpdateStmt: "update", ast.DeleteStmt: "delete"}
    result.kind = next((k for t, k in kinds.items() if isinstance(root, t)), "other")
    result.ctes = list(dict.fromkeys(col.ctes))
    result.functions = list(dict.fromkeys(col.functions))

    # 읽기/쓰기: 쓰기 대상은 RangeVar로도 잡히므로, 대상 외에 읽는 곳이 없으면 "W"만 남긴다.
    reads = _count_reads(root, col.written)
    for name in sorted((col.read | col.written) - cte_set):
        flag = ("R" if name in reads or name not in col.written else "") + ("W" if name in col.written else "")
        result.tables[name] = flag

    _resolve_columns(result, col, cte_set, schema)

    if isinstance(root, ast.SelectStmt):
        select = _top_select(root)
        result.output_names = _output_names(select, lambda q: _expand_star(q, col, schema, cte_set))
        if result.output_names is None:
            result.unresolved.append("SELECT * 를 풀 스키마(스냅샷)가 없어 출력 이름을 알 수 없음")
    if isinstance(root, (ast.UpdateStmt, ast.DeleteStmt)) and root.whereClause is not None:
        result.where.append(_text(root.whereClause))
    if isinstance(root, ast.SelectStmt) and root.whereClause is not None:
        result.where.append(_text(root.whereClause))
    if isinstance(root, ast.UpdateStmt):
        table = root.relation.relname.lower()
        result.assignments += [Assignment(table, t.name.lower(), _text(t.val)) for t in root.targetList or ()]
    if isinstance(root, ast.InsertStmt):
        _collect_insert_assignments(root, result)
    return result


def _count_reads(root: Any, written: set[str]) -> set[str]:
    """쓰기 대상 자신의 RangeVar를 빼고, 문장 안에서 실제로 읽히는 테이블 이름을 센다."""
    reads: set[str] = set()
    targets = {id(root.relation)} if isinstance(root, (ast.InsertStmt, ast.UpdateStmt, ast.DeleteStmt)) else set()

    def visit(node: Any) -> None:
        if isinstance(node, ast.Node):
            if isinstance(node, (ast.InsertStmt, ast.UpdateStmt, ast.DeleteStmt)):
                targets.add(id(node.relation))
            if isinstance(node, ast.RangeVar) and id(node) not in targets:
                reads.add(node.relname.lower())
            for name in node:
                visit(getattr(node, name))
        elif isinstance(node, (list, tuple)):
            for item in node:
                visit(item)

    visit(root)
    return reads


def _expand_star(qualifier: str | None, col: _Collector, schema: Schema | None, cte_set: set[str]) -> list[str] | None:
    """`*` 또는 `t.*`가 가리키는 컬럼 목록. 스키마에 없는 테이블이 하나라도 섞이면 None."""
    if not schema:
        return None
    if qualifier is not None:
        table = col.alias.get(qualifier, qualifier)
        return list(schema[table]) if table in schema else None
    tables = [t for t in col.read if t not in cte_set]
    if not tables or any(t not in schema for t in tables):
        return None
    return [c for t in sorted(tables) for c in schema[t]]


def _resolve_columns(result: ParsedSql, col: _Collector, cte_set: set[str], schema: Schema | None) -> None:
    tables = [t for t in result.tables if t not in cte_set]
    used: dict[str, set[str]] = {}
    for parts in col.column_refs:
        if not parts:
            continue
        name = parts[-1]
        if len(parts) >= 2:
            qualifier = parts[-2]
            table = col.alias.get(qualifier, qualifier)
            if table in cte_set or table not in result.tables:
                continue  # CTE·서브쿼리 별칭의 컬럼은 원본 테이블 컬럼이 아니다
            used.setdefault(table, set()).add(name)
        elif schema:
            owners = [t for t in tables if name in schema.get(t, ())]
            if len(owners) == 1:
                used.setdefault(owners[0], set()).add(name)
            elif len(owners) > 1:
                result.unresolved.append(f"컬럼 '{name}'이(가) 여러 테이블에 있어 귀속 불명: {', '.join(owners)}")
        elif len(tables) == 1:
            used.setdefault(tables[0], set()).add(name)
    result.columns = {t: sorted(cols) for t, cols in sorted(used.items())}


def _collect_insert_assignments(root: ast.InsertStmt, result: ParsedSql) -> None:
    table = root.relation.relname.lower()
    cols = [c.name.lower() for c in root.cols or ()]
    select = root.selectStmt
    if isinstance(select, ast.SelectStmt) and select.valuesLists and cols:
        row = select.valuesLists[0]
        values = [_text(v) for v in (row.items if hasattr(row, "items") else row)]
        result.assignments += [Assignment(table, c, v) for c, v in zip(cols, values, strict=False)]
    elif isinstance(select, ast.SelectStmt) and select.targetList and cols:
        values = [_text(t.val) for t in select.targetList]
        result.assignments += [Assignment(table, c, v) for c, v in zip(cols, values, strict=False)]
    if root.onConflictClause is not None and root.onConflictClause.targetList:
        result.assignments += [
            Assignment(table, t.name.lower(), _text(t.val)) for t in root.onConflictClause.targetList
        ]


def _fallback(sql: str, error: str) -> ParsedSql:
    """AST 파싱이 실패했을 때의 정규식 추정. 호출한 쪽이 fallback 표시를 그대로 노출해야 한다."""
    ctes = [c.lower() for c in _FALLBACK_CTE_RE.findall(sql)]
    names = {m.lower() for m in _FALLBACK_TABLE_RE.findall(sql)} - set(ctes) - _SQL_NOISE
    result = ParsedSql(fallback=True, error=error)
    result.ctes = list(dict.fromkeys(ctes))
    result.tables = {n: "R" for n in sorted(names)}
    result.unresolved.append(f"파싱 실패, 정규식 추정: {error}")
    return result


def parse_statement(
    key: str,
    statements: dict[str, Any],
    schema: Schema | None = None,
) -> ToolResult:
    """MyBatis statement(`ns.sqlId`)를 `explain` 모드로 순수 SQL로 전개해 해석한다.

    `<if>`는 모두 켠 최대형 SQL이다. `${}`는 explain 렌더링이 `1`로 바꿔 버리므로 structure 렌더링에서
    따로 찾아 unresolved에 남긴다.
    """
    from yunhee.tools.as_is.mybatis_render import render

    try:
        sql, _ = render(key, mode="explain", statements=statements)
        structure, _ = render(key, mode="structure", statements=statements)
    except ValueError as exc:
        return ToolResult(ok=False, error=str(exc))

    parsed = parse_sql_text(sql, schema)
    dollars = sorted(set(re.findall(r"\$\{[^}]*\}", structure)))
    if dollars:
        parsed.unresolved.append("${} 치환은 값을 알 수 없어 1로 대체함: " + ", ".join(dollars))
    return ToolResult(ok=True, data=parsed)
