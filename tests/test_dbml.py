from typer.testing import CliRunner

from yunhee import cli
from yunhee.dbml import render_markdown
from yunhee.tools.base import ToolResult


def _col(name, type_="integer", **kw):
    col = {"name": name, "type": type_, "not_null": False, "default": None,
           "identity": None, "generated": None, "note": None}
    col.update(kw)
    return col


def _table(schema, name, columns, **kw):
    t = {"schema": schema, "name": name, "note": None, "columns": columns,
         "pk": [], "uniques": [], "indexes": []}
    t.update(kw)
    return t


def _schema(**kw):
    s = {"database": "testdb", "server_version": "15.0", "schemas": ["public"],
         "tables": [], "refs": [], "enums": [], "views": [], "routines": [],
         "sequences": [], "triggers": []}
    s.update(kw)
    return s


def _render(schema):
    return render_markdown(schema, source="LOCAL_DB", source_url="postgresql://u:***@h/db")


def test_columns_single_pk_types_defaults_notes():
    md = _render(_schema(tables=[_table("public", "acct", [
        _col("id", "bigint", not_null=True, identity="a"),
        _col("nm", "character varying(20)", not_null=True, note="계정's 이름"),
        _col("created", "timestamp with time zone", default="now()"),
        _col("seq", "integer", default="nextval('acct_seq'::regclass)"),
        _col("memo", "text", note="첫줄\n둘째줄"),
    ], pk=["id"], note="계정")]))

    assert 'Table "public"."acct" {' in md
    assert '"id" "bigint" [pk, increment]' in md
    assert '"nm" "character varying(20)" [not null, note: \'계정\\\'s 이름\']' in md
    assert '"created" "timestamp with time zone" [default: `now()`]' in md
    assert '"seq" "integer" [increment]' in md
    assert "note: '''첫줄\n둘째줄'''" in md
    assert "Note: '계정'" in md


def test_composite_pk_uniques_and_indexes():
    md = _render(_schema(tables=[_table("public", "t", [_col("a"), _col("b"), _col("c")],
        pk=["a", "b"],
        uniques=[{"name": "t_c_key", "columns": ["c"]}, {"name": "t_bc_key", "columns": ["b", "c"]}],
        indexes=[
            {"name": "t_lower_idx", "unique": False, "method": "btree",
             "columns": [{"expr": "lower(c::text)", "is_expression": True}], "where": "a > 0"},
            {"name": "t_gin", "unique": False, "method": "gin",
             "columns": [{"expr": "c", "is_expression": False}], "where": None},
        ],
    )]))

    assert '"c" "integer" [unique]' in md
    assert '("a", "b") [pk]' in md
    assert "(\"b\", \"c\") [unique, name: 't_bc_key']" in md
    assert "(`lower(c::text)`) [name: 't_lower_idx', note: 'WHERE a > 0']" in md
    assert "(c) [name: 't_gin', note: 'USING gin']" in md


def test_refs_enums_and_out_of_scope_ref():
    md = _render(_schema(
        enums=[{"schema": "public", "name": "status", "values": ["A", "B"]}],
        tables=[_table("public", "parent", [_col("id")], pk=["id"]),
                _table("public", "child", [_col("id"), _col("pid")], pk=["id"])],
        refs=[
            {"name": "child_pid_fk", "schema": "public", "table": "child", "columns": ["pid"],
             "ref_schema": "public", "ref_table": "parent", "ref_columns": ["id"],
             "on_delete": "c", "on_update": "a"},
            {"name": "child_ext_fk", "schema": "public", "table": "child", "columns": ["id", "pid"],
             "ref_schema": "other", "ref_table": "ext", "ref_columns": ["x", "y"],
             "on_delete": "a", "on_update": "a"},
        ],
    ))

    assert 'Enum "public"."status" {\n  "A"\n  "B"\n}' in md
    assert 'Ref "child_pid_fk": "public"."child"."pid" > "public"."parent"."id" [delete: cascade]' in md
    assert '// Ref child_ext_fk: "public"."child".("id", "pid") > "other"."ext".("x", "y")' in md


def test_sql_sections_present_and_empty_sections_omitted():
    md = _render(_schema(
        views=[{"schema": "public", "name": "v1", "materialized": False,
                "definition": " SELECT 1;", "note": "뷰"}],
        routines=[{"schema": "public", "name": "fn", "kind": "function", "arguments": "a integer",
                   "definition": "CREATE OR REPLACE FUNCTION public.fn(a integer) ...", "note": None}],
        sequences=[{"schema": "public", "name": "s1", "type": "bigint", "start": 1, "increment": 1,
                    "min": 1, "max": 9, "cycle": False, "owned_by": "public.t.id"}],
    ))

    assert "## Views\n\n### public.v1\n\n뷰\n\n```sql\nCREATE OR REPLACE VIEW public.v1 AS\n SELECT 1;\n```" in md
    assert "### public.fn(a integer)" in md
    assert "| public.s1 | bigint | 1 | 1 | 1 | 9 | no | public.t.id |" in md
    for absent in ("## Materialized Views", "## Procedures", "## Triggers"):
        assert absent not in md


runner = CliRunner()


def test_cli_rejects_missing_or_invalid_env(monkeypatch):
    monkeypatch.delenv("NOPE_DB", raising=False)
    assert runner.invoke(cli.app, ["make-dbml", "NOPE_DB"]).exit_code == 1
    assert runner.invoke(cli.app, ["dbml", "../x"]).exit_code == 1

    monkeypatch.setenv("NOT_PG", "mysql://u:secret@h/db")
    result = runner.invoke(cli.app, ["dbml", "NOT_PG"])
    assert result.exit_code == 1
    assert "secret" not in result.output


def test_cli_default_and_custom_output(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_DB", "postgresql://u:secret@h/db")
    monkeypatch.setattr(cli, "WORK_DIR", tmp_path)
    captured = {}

    def fake_fetch(dsn, schemas=None):
        captured["schemas"] = schemas
        return ToolResult(ok=True, data=_schema(tables=[_table("public", "t", [_col("id")])]))

    monkeypatch.setattr("yunhee.tools.pg_schema.fetch_schema", fake_fetch)

    result = runner.invoke(cli.app, ["make-dbml", "MY_DB"])
    assert result.exit_code == 0, result.output
    out = (tmp_path / "MY_DB-dbml.md").read_text()
    assert 'Table "public"."t"' in out
    assert "secret" not in out
    assert captured["schemas"] is None

    custom = tmp_path / "a.md"
    result = runner.invoke(cli.app, ["dbml", "MY_DB", "--output", str(custom), "--schema", "public"])
    assert result.exit_code == 0, result.output
    assert custom.exists()
    assert captured["schemas"] == ["public"]
