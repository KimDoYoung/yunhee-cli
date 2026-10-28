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
_FALLBACK_CTE_RE = re.compile(r"\b([a-z_][a-z0-9_]*)\s*(?:\([^()]*\)\s*)?as\s*\(", re.IGNORECASE)  # name AS ( 또는 name(cols) AS (
_SQL_NOISE = {"select", "set", "values", "where", "lateral", "only", "unnest", "generate_series"}


@dataclass
class Assignment:
    """UPDATE SET / INSERT 값 한 건: 어느 테이블의 어느 컬럼에 어떤 식을 쓰는가."""

    table: str
    column: str
    value: str
    action: str = "UPDATE"  # UPDATE / INSERT / CONFLICT(ON CONFLICT DO UPDATE)
    where: str = ""  # 그 UPDATE의 WHERE 식 (INSERT에는 없음)


@dataclass
class ParsedSql:
    kind: str = "other"  # select / insert / update / delete / other
    tables: dict[str, str] = field(default_factory=dict)  # 테이블명 → "R" / "W" / "RW" (SQL에 나온 순서)
    ctes: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)
    table_functions: list[str] = field(default_factory=list)  # FROM get_x(...) 처럼 테이블 자리에 쓰인 함수
    cases: list[str] = field(default_factory=list)  # CASE WHEN … END 식 (분기 지점)
    writes: list[tuple[str, str]] = field(default_factory=list)  # (INSERT|UPDATE|DELETE, 테이블) 나온 순서
    columns: dict[str, list[str]] = field(default_factory=dict)  # 테이블명 → 사용된 컬럼
    column_usage: dict[str, dict[str, list[str]]] = field(default_factory=dict)  # 테이블 → 컬럼 → 쓰인 절(SELECT/WHERE/JOIN/ORDER/GROUP/…)
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


# 필드 이름 → 그 안에서 읽는 컬럼이 속하는 절. SELECT 목록(targetList)은 문장 종류에 따라 달라 _target_clause가 정한다
_CLAUSES = {
    "whereClause": "WHERE", "havingClause": "HAVING", "sortClause": "ORDER", "groupClause": "GROUP",
    "quals": "JOIN", "valuesLists": "VALUES", "returningList": "RETURNING", "returningClause": "RETURNING",  # pglast 8: ReturningClause
}


def _target_clause(node: Any, inherited: str) -> str:
    if isinstance(node, ast.UpdateStmt):
        return "SET"  # SET col = <식>: 식 안의 컬럼은 읽기다
    if isinstance(node, ast.SelectStmt):
        return "SELECT"
    return inherited


class _Collector:
    """AST를 한 번 훑어 테이블·CTE·함수·컬럼 참조를 모은다."""

    def __init__(self) -> None:
        self.read: dict[str, int] = {}  # 테이블명 → 처음 나온 위치(location)
        self.written: set[str] = set()
        self.writes: list[tuple[str, str]] = []
        self.table_functions: list[str] = []
        self.cases: list[str] = []
        self.write_nodes: list[Any] = []  # CTE 안의 쓰기를 포함한 모든 INSERT/UPDATE 노드
        self.ctes: list[str] = []
        self.functions: list[str] = []
        self.alias: dict[str, str] = {}  # 별칭 → 테이블명
        self.column_refs: list[tuple[list[str], str]] = []  # (ColumnRef의 이름 조각(소문자), 쓰인 절)

    def walk(self, node: Any, clause: str = "") -> None:
        """AST를 훑는다. clause는 지금 읽고 있는 절 (컬럼이 SELECT 목록·WHERE·JOIN 중 어디서 쓰였는지 구분하는 데 쓴다)."""
        if isinstance(node, ast.Node):
            self._visit(node, clause)
            for name in node:
                self.walk(getattr(node, name), _CLAUSES.get(name, clause) if name != "targetList" else _target_clause(node, clause))
        elif isinstance(node, (list, tuple)):
            for item in node:
                self.walk(item, clause)

    def _visit(self, node: ast.Node, clause: str = "") -> None:
        if isinstance(node, ast.CommonTableExpr):
            self.ctes.append(node.ctename.lower())
        elif isinstance(node, ast.RangeVar):
            name = node.relname.lower()
            self.read.setdefault(name, node.location)
            if node.alias:
                self.alias[node.alias.aliasname.lower()] = name
        elif isinstance(node, (ast.InsertStmt, ast.UpdateStmt, ast.DeleteStmt)):
            rel = node.relation
            name = rel.relname.lower()
            self.written.add(name)
            if isinstance(node, (ast.InsertStmt, ast.UpdateStmt)):
                self.write_nodes.append(node)
            self.writes.append((type(node).__name__.removesuffix("Stmt").upper(), name))
            if rel.alias:
                self.alias[rel.alias.aliasname.lower()] = name
        elif isinstance(node, ast.CaseExpr):
            self.cases.append(re.sub(r"\s+", " ", _text(node)))
        elif isinstance(node, ast.RangeFunction):
            for pair in node.functions or ():
                call = pair[0] if isinstance(pair, (list, tuple)) else pair
                if isinstance(call, ast.FuncCall):
                    parts = _strings(call.funcname)
                    if parts:
                        self.table_functions.append(parts[-1])
        elif isinstance(node, ast.FuncCall):
            parts = _strings(node.funcname)
            if parts:
                self.functions.append(parts[-1])
        elif isinstance(node, ast.ColumnRef) and not any(isinstance(f, ast.A_Star) for f in node.fields):
            self.column_refs.append((_strings(node.fields), clause))  # `*`는 output_names에서 다룬다


def _top_select(stmt: Any) -> Any:
    """UNION이면 왼쪽 가지의 SELECT를 따라 내려간다 (출력 이름은 첫 SELECT 기준)."""
    while isinstance(stmt, ast.SelectStmt) and stmt.larg is not None:
        stmt = stmt.larg
    return stmt


_PLAIN_IDENT = re.compile(r"[a-z_][a-z0-9_]*")


def _display_name(name: str) -> str:
    """대소문자·특수문자가 있어 따옴표가 필요한 이름은 "..."로 감싼다 (기존 select_output_names와 같은 표기)."""
    return name if _PLAIN_IDENT.fullmatch(name) else f'"{name}"'


def _output_names(select: Any, resolve_star: Any) -> list[str | None] | None:
    names: list[str | None] = []
    for target in select.targetList or ():
        val = target.val
        if target.name:
            names.append(_display_name(target.name))
        elif isinstance(val, ast.ColumnRef):
            last = val.fields[-1]
            if isinstance(last, ast.A_Star):
                expanded = resolve_star(_strings(val.fields)[-1] if len(val.fields) > 1 else None)
                if expanded is None:
                    return None
                names.extend(expanded)
            else:
                names.append(_display_name(last.sval))
        elif isinstance(val, ast.FuncCall):
            names.append(_display_name(val.funcname[-1].sval))
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

    # 읽기/쓰기: 쓰기 대상은 RangeVar로도 잡히므로, 대상 외에 읽는 곳이 없으면 "W"만 남긴다. SQL에 나온 순서로 둔다.
    reads = _count_reads(root, col.written)
    names = (col.read.keys() | col.written) - cte_set
    for name in sorted(names, key=lambda n: (col.read.get(n, 0), n)):
        flag = ("R" if name in reads or name not in col.written else "") + ("W" if name in col.written else "")
        result.tables[name] = flag
    result.writes = list(dict.fromkeys(col.writes))
    result.table_functions = list(dict.fromkeys(col.table_functions))
    result.cases = list(dict.fromkeys(col.cases))

    _resolve_columns(result, col, cte_set, schema)

    if isinstance(root, ast.SelectStmt):
        select = _top_select(root)
        result.output_names = _output_names(select, lambda q: _expand_star(q, col, schema, cte_set))
        if result.output_names is None:
            result.unresolved.append("SELECT *를 풀 수 없어(스키마 스냅샷이 없거나 CTE·서브쿼리 별칭의 *) 출력 이름을 알 수 없음")
    if isinstance(root, (ast.UpdateStmt, ast.DeleteStmt)) and root.whereClause is not None:
        result.where.append(_text(root.whereClause))
    if isinstance(root, ast.SelectStmt) and root.whereClause is not None:
        result.where.append(_text(root.whereClause))
    for node in col.write_nodes:  # CTE 안의 UPDATE도 대입으로 본다 (upsert 패턴)
        if isinstance(node, ast.UpdateStmt):
            table = node.relation.relname.lower()
            where = re.sub(r"\s+", " ", _text(node.whereClause)) if node.whereClause is not None else ""
            result.assignments += [Assignment(table, t.name.lower(), _text(t.val), "UPDATE", where) for t in node.targetList or ()]
        else:
            _collect_insert_assignments(node, result)
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
    usage: dict[str, dict[str, set[str]]] = {}

    def note(table: str, name: str, clause: str) -> None:
        used.setdefault(table, set()).add(name)
        if clause:
            usage.setdefault(table, {}).setdefault(name, set()).add(clause)

    for parts, clause in col.column_refs:
        if not parts:
            continue
        name = parts[-1]
        if len(parts) >= 2:
            qualifier = parts[-2]
            table = col.alias.get(qualifier, qualifier)
            if table in cte_set or table not in result.tables:
                continue  # CTE·서브쿼리 별칭의 컬럼은 원본 테이블 컬럼이 아니다
            note(table, name, clause)
        elif schema:
            owners = [t for t in tables if name in schema.get(t, ())]
            if len(owners) == 1:
                note(owners[0], name, clause)
            elif len(owners) > 1:
                result.unresolved.append(f"컬럼 '{name}'이(가) 여러 테이블에 있어 귀속 불명: {', '.join(owners)}")
        elif len(tables) == 1:
            note(tables[0], name, clause)
    result.columns = {t: sorted(cols) for t, cols in sorted(used.items())}
    result.column_usage = {t: {c: sorted(cl) for c, cl in sorted(cols.items())} for t, cols in sorted(usage.items())}


def _collect_insert_assignments(root: ast.InsertStmt, result: ParsedSql) -> None:
    table = root.relation.relname.lower()
    cols = [c.name.lower() for c in root.cols or ()]
    select = root.selectStmt
    if isinstance(select, ast.SelectStmt) and select.valuesLists and cols:
        row = select.valuesLists[0]
        values = [_text(v) for v in (row.items if hasattr(row, "items") else row)]
        result.assignments += [Assignment(table, c, v, "INSERT") for c, v in zip(cols, values, strict=False)]
    elif isinstance(select, ast.SelectStmt) and select.targetList and cols:
        values = [_text(t.val) for t in select.targetList]
        result.assignments += [Assignment(table, c, v, "INSERT") for c, v in zip(cols, values, strict=False)]
    if root.onConflictClause is not None and root.onConflictClause.targetList:
        result.assignments += [Assignment(table, t.name.lower(), _text(t.val), "CONFLICT") for t in root.onConflictClause.targetList]


def _fallback(sql: str, error: str) -> ParsedSql:
    """AST 파싱이 실패했을 때의 정규식 추정. 호출한 쪽이 fallback 표시를 그대로 노출해야 한다."""
    ctes = [c.lower() for c in _FALLBACK_CTE_RE.findall(sql)]
    names = {m.lower() for m in _FALLBACK_TABLE_RE.findall(sql)} - set(ctes) - _SQL_NOISE
    result = ParsedSql(fallback=True, error=error)
    result.ctes = list(dict.fromkeys(ctes))
    result.tables = {n: "R" for n in sorted(names)}
    result.unresolved.append(f"파싱 실패, 정규식 추정: {error}")
    return result


MAX_BRANCH_VARIANTS = 8


def _merge(base: ParsedSql, other: ParsedSql) -> None:
    """다른 분기 변형에서만 나온 테이블·CTE·함수·컬럼·변경 작업을 base에 합친다."""
    for name, flag in other.tables.items():
        base.tables[name] = "".join(sorted(set(base.tables.get(name, "") + flag), key="RW".index))
    for attr in ("ctes", "functions", "table_functions", "writes", "cases"):
        have = getattr(base, attr)
        have += [x for x in getattr(other, attr) if x not in have]
    for table, cols in other.columns.items():
        base.columns[table] = sorted(set(base.columns.get(table, [])) | set(cols))
    for table, cols in other.column_usage.items():
        for name, clauses in cols.items():
            have = base.column_usage.setdefault(table, {}).setdefault(name, [])
            have[:] = sorted(set(have) | set(clauses))
    for name in base.ctes:  # 어느 변형에서든 CTE로 정의된 이름은 테이블이 아니다
        base.tables.pop(name, None)


def parse_statement(
    key: str,
    statements: dict[str, Any],
    schema: Schema | None = None,
    all_branches: bool = True,
    keep_params: bool = False,
) -> ToolResult:
    """MyBatis statement(`ns.sqlId`)를 `explain` 모드로 순수 SQL로 전개해 해석한다.

    `<if>`는 모두 켠 최대형 SQL이다. `<choose>`는 explain 렌더링이 한 분기만 고르므로, `all_branches`면
    다른 분기를 차례로 고른 변형도 해석해 테이블·CTE·함수·컬럼을 합친다 (kind·출력 이름·대입·WHERE는 기본 변형 기준).
    `${}`는 explain 렌더링이 `1`로 바꿔 버리므로 structure 렌더링에서 따로 찾아 unresolved에 남긴다.
    `keep_params`면 `#{status}`를 `NULL`이 아니라 `__p_status`로 남겨, 대입 값·WHERE에서 어떤 파라미터가 쓰였는지 알 수 있다.
    """
    from yunhee.tools.as_is.mybatis_render import render

    try:
        base = {"__keep_params__": True} if keep_params else None
        sql, _ = render(key, params=dict(base) if base else None, mode="explain", statements=statements)
        structure, _ = render(key, mode="structure", statements=statements)
    except Exception as exc:  # noqa: BLE001 - 호출한 쪽은 ok=False면 정규식 추정으로 되돌리므로 렌더 실패는 예외로 올리지 않는다
        return ToolResult(ok=False, error=str(exc))

    parsed = parse_sql_text(sql, schema)
    if all_branches and "<choose" in structure:
        seen = {sql}
        for variant in range(1, MAX_BRANCH_VARIANTS):
            alt, _ = render(key, params={"__pick__": variant, **(base or {})}, mode="explain", statements=statements)
            if alt in seen:
                break
            seen.add(alt)
            other = parse_sql_text(alt, schema)
            if other.fallback:
                # Tibero 계층 쿼리(START WITH) 등 PostgreSQL 문법이 아닌 분기: 정규식으로 추정한 테이블만 합치고 알린다
                _merge(parsed, other)
                note = "일부 분기가 PostgreSQL 문법이 아니라 정규식으로 추정한 테이블을 합침"
                if note not in parsed.unresolved:
                    parsed.unresolved.append(note)
            else:
                _merge(parsed, other)
    dollars = sorted(set(re.findall(r"\$\{[^}]*\}", structure)))
    if dollars:
        parsed.unresolved.append("${} 치환은 값을 알 수 없어 1로 대체함: " + ", ".join(dollars))
    return ToolResult(ok=True, data=parsed)
