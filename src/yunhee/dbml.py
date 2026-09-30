"""`tools.pg_schema.fetch_schema()` 결과를 DBML + SQL 섹션 마크다운으로 렌더링한다 (DB 접속 없음).

DBML은 테이블/컬럼/인덱스/Ref/Enum만 표현할 수 있으므로, view/function/procedure/sequence/trigger는
DBML 블록 뒤에 마크다운 섹션으로 SQL 정의문을 기록한다.
"""

from datetime import datetime

# pg_constraint.confdeltype/confupdtype → DBML Ref 액션 ('a' = no action은 기본값이라 생략)
_REF_ACTIONS = {"r": "restrict", "c": "cascade", "n": "set null", "d": "set default"}


def _q(name: str) -> str:
    return '"' + name.replace('"', '\\"') + '"'


def _qn(*parts: str) -> str:
    return ".".join(_q(p) for p in parts)


def _str(text: str) -> str:
    """DBML 문자열 리터럴. 여러 줄이면 ''' ''' 블록 문자열."""
    text = text.replace("\\", "\\\\")
    if "\n" in text:
        return "'''" + text.replace("'''", "\\'''") + "'''"
    return "'" + text.replace("'", "\\'") + "'"


def _column_line(col: dict, single_pk: str | None, unique_cols: set[str]) -> str:
    settings = []
    if col["name"] == single_pk:
        settings.append("pk")
    elif col["not_null"]:
        settings.append("not null")
    if col["name"] in unique_cols:
        settings.append("unique")

    default = col["default"]
    if col["identity"] or (default and default.startswith("nextval(")):
        settings.append("increment")

    note = col["note"]
    if col["generated"] == "s" and default:
        generated = f"GENERATED ALWAYS AS ({default}) STORED"
        note = f"{note}\n{generated}" if note else generated
    elif default and not default.startswith("nextval("):
        settings.append("default: `" + default.replace("`", "'") + "`")

    if note:
        settings.append("note: " + _str(note))

    line = f"  {_q(col['name'])} {_q(col['type'])}"
    if settings:
        line += " [" + ", ".join(settings) + "]"
    return line


def _index_line(idx: dict) -> str:
    cols = ["`" + c["expr"] + "`" if c["is_expression"] else c["expr"] for c in idx["columns"]]
    settings = []
    if idx["unique"]:
        settings.append("unique")
    if idx["method"] == "hash":
        settings.append("type: hash")
    settings.append("name: " + _str(idx["name"]))
    notes = []
    if idx["method"] not in ("btree", "hash"):
        notes.append(f"USING {idx['method']}")
    if idx["where"]:
        notes.append(f"WHERE {idx['where']}")
    if notes:
        settings.append("note: " + _str(" ".join(notes)))
    return f"    ({', '.join(cols)}) [{', '.join(settings)}]"


def _table_block(t: dict) -> str:
    single_pk = t["pk"][0] if len(t["pk"]) == 1 else None
    unique_cols = {u["columns"][0] for u in t["uniques"] if len(u["columns"]) == 1}

    lines = [f"Table {_qn(t['schema'], t['name'])} {{"]
    lines += [_column_line(c, single_pk, unique_cols) for c in t["columns"]]

    index_lines = []
    if len(t["pk"]) > 1:
        index_lines.append(f"    ({', '.join(_q(c) for c in t['pk'])}) [pk]")
    for u in t["uniques"]:
        if len(u["columns"]) > 1:
            index_lines.append(
                f"    ({', '.join(_q(c) for c in u['columns'])}) [unique, name: {_str(u['name'])}]"
            )
    index_lines += [_index_line(i) for i in t["indexes"]]
    if index_lines:
        lines += ["", "  indexes {", *index_lines, "  }"]

    if t["note"]:
        lines += ["", f"  Note: {_str(t['note'])}"]
    lines.append("}")
    return "\n".join(lines)


def _ref_line(r: dict, rendered: set[tuple[str, str]]) -> str:
    def endpoint(schema: str, table: str, cols: list[str]) -> str:
        if len(cols) == 1:
            return _qn(schema, table, cols[0])
        return f"{_qn(schema, table)}.({', '.join(_q(c) for c in cols)})"

    src = endpoint(r["schema"], r["table"], r["columns"])
    dst = endpoint(r["ref_schema"], r["ref_table"], r["ref_columns"])
    if (r["ref_schema"], r["ref_table"]) not in rendered:
        # 대상 테이블이 --schema 범위 밖이면 DBML 파싱 오류가 나므로 주석으로만 남긴다
        return f"// Ref {r['name']}: {src} > {dst} (대상 테이블이 출력 범위 밖)"

    settings = []
    for key, code in (("delete", r["on_delete"]), ("update", r["on_update"])):
        if code in _REF_ACTIONS:
            settings.append(f"{key}: {_REF_ACTIONS[code]}")
    line = f"Ref {_q(r['name'])}: {src} > {dst}"
    if settings:
        line += " [" + ", ".join(settings) + "]"
    return line


def render_dbml(schema: dict) -> str:
    """schema의 enums/tables/refs만 DBML 텍스트로 렌더링 (전체 스냅샷이든 일부 테이블 slice든 동일)."""
    blocks = []
    for e in schema["enums"]:
        values = "\n".join(f"  {_q(v)}" for v in e["values"])
        blocks.append(f"Enum {_qn(e['schema'], e['name'])} {{\n{values}\n}}")
    blocks += [_table_block(t) for t in schema["tables"]]

    rendered = {(t["schema"], t["name"]) for t in schema["tables"]}
    refs = [_ref_line(r, rendered) for r in schema["refs"]]
    if refs:
        blocks.append("\n".join(refs))
    return "\n\n".join(blocks)


def _sql_section(title: str, items: list[tuple[str, str | None, str]]) -> list[str]:
    """items: (제목, 코멘트, SQL). 비어 있으면 섹션 생략."""
    if not items:
        return []
    out = [f"## {title}", ""]
    for heading, note, sql in items:
        out += [f"### {heading}", ""]
        if note:
            out += [note, ""]
        out += ["```sql", sql.strip(), "```", ""]
    return out


def counts(schema: dict) -> dict[str, int]:
    views = [v for v in schema["views"] if not v["materialized"]]
    return {
        "tables": len(schema["tables"]),
        "enums": len(schema["enums"]),
        "refs": len(schema["refs"]),
        "views": len(views),
        "materialized views": len(schema["views"]) - len(views),
        "functions": sum(1 for r in schema["routines"] if r["kind"] == "function"),
        "procedures": sum(1 for r in schema["routines"] if r["kind"] == "procedure"),
        "sequences": len(schema["sequences"]),
        "triggers": len(schema["triggers"]),
    }


def render_markdown(schema: dict, *, source: str, source_url: str) -> str:
    """source: 환경변수 이름(LOCAL_DB 등), source_url: 비밀번호가 마스킹된 접속 URL."""
    summary = ", ".join(f"{k} {v}" for k, v in counts(schema).items())
    out = [
        f"# {source} DB 스키마",
        "",
        f"- 생성: {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %z')}",
        f"- 대상: `{source_url}` (database `{schema['database']}`, PostgreSQL {schema['server_version']})",
        f"- 스키마: {', '.join(schema['schemas'])}",
        f"- 객체: {summary}",
        "",
        "## DBML",
        "",
        "```dbml",
        render_dbml(schema),
        "```",
        "",
    ]

    def qualified(o: dict) -> str:
        return f"{o['schema']}.{o['name']}"

    out += _sql_section("Views", [
        (qualified(v), v["note"], f"CREATE OR REPLACE VIEW {qualified(v)} AS\n{v['definition']}")
        for v in schema["views"] if not v["materialized"]
    ])
    out += _sql_section("Materialized Views", [
        (qualified(v), v["note"], f"CREATE MATERIALIZED VIEW {qualified(v)} AS\n{v['definition']}")
        for v in schema["views"] if v["materialized"]
    ])
    for kind, title in (("function", "Functions"), ("procedure", "Procedures")):
        out += _sql_section(title, [
            (f"{qualified(r)}({r['arguments']})", r["note"], r["definition"])
            for r in schema["routines"] if r["kind"] == kind
        ])

    if schema["sequences"]:
        out += [
            "## Sequences",
            "",
            "| name | type | start | increment | min | max | cycle | owned by |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for s in schema["sequences"]:
            out.append(
                f"| {qualified(s)} | {s['type']} | {s['start']} | {s['increment']} | {s['min']} "
                f"| {s['max']} | {'yes' if s['cycle'] else 'no'} | {s['owned_by'] or ''} |"
            )
        out.append("")

    if schema["triggers"]:
        out += ["## Triggers", "", "```sql"]
        out += [f"{t['definition']};" for t in schema["triggers"]]
        out += ["```", ""]

    return "\n".join(out)
