import sqlite3

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools import legacy_page, page_schema, schema_snapshot


def _col(name, type_="integer", note=None):
    return {"name": name, "type": type_, "not_null": False, "default": None,
            "identity": None, "generated": None, "note": note}


def _table(name, schema="public", cols=None, note=None):
    return {"schema": schema, "name": name, "note": note, "columns": cols or [_col("id")],
            "pk": ["id"], "uniques": [], "indexes": []}


def _snapshot():
    return {
        "tables": [
            _table("act01_account_code", note="계정코드"),
            _table("act02_journal", cols=[_col("id"), _col("acct_id"), _col("st", "status")]),
            _table("sys09_code"),
            _table("sys09_code", schema="hist"),
        ],
        "refs": [
            {"name": "j_acct_fk", "schema": "public", "table": "act02_journal", "columns": ["acct_id"],
             "ref_schema": "public", "ref_table": "act01_account_code", "ref_columns": ["id"],
             "on_delete": "a", "on_update": "a"},
            {"name": "code_fk", "schema": "public", "table": "sys09_code", "columns": ["id"],
             "ref_schema": "public", "ref_table": "act02_journal", "ref_columns": ["id"],
             "on_delete": "a", "on_update": "a"},
        ],
        "enums": [{"schema": "public", "name": "status", "values": ["A"]},
                  {"schema": "public", "name": "unused", "values": ["X"]}],
    }


def test_slice_by_name_glob_and_schema_qualified():
    r = schema_snapshot.slice_tables(_snapshot(), ["ACT01_ACCOUNT_CODE", "hist.sys09_code", "nope"])
    assert r.data["tables"] == ["act01_account_code", "sys09_code"]
    assert 'Table "hist"."sys09_code"' in r.data["dbml"]
    assert 'Table "public"."sys09_code"' not in r.data["dbml"]
    assert r.data["missing"] == ["nope"]

    r = schema_snapshot.slice_tables(_snapshot(), ["act0*"])
    assert r.data["tables"] == ["act01_account_code", "act02_journal"]


def test_slice_refs_and_enums_follow_included_tables():
    r = schema_snapshot.slice_tables(_snapshot(), ["act02_journal"])
    dbml = r.data["dbml"]
    # 포함된 테이블에서 나가는 FK만, 대상이 slice 밖이면 주석
    assert "// Ref j_acct_fk" in dbml
    assert "code_fk" not in dbml
    # 컬럼 타입으로 쓰인 enum만
    assert 'Enum "public"."status"' in dbml
    assert "unused" not in dbml

    r = schema_snapshot.slice_tables(_snapshot(), ["act02_journal", "act01_account_code"])
    assert 'Ref "j_acct_fk"' in r.data["dbml"]


def test_slice_budget_keeps_priority_order():
    one = len(schema_snapshot.slice_tables(_snapshot(), ["public.sys09_code"]).data["dbml"])
    r = schema_snapshot.slice_tables(_snapshot(), ["public.sys09_code", "act01_account_code"], char_limit=one + 10)
    assert r.data["tables"] == ["sys09_code"]
    assert r.data["omitted"] == ["act01_account_code"]
    assert r.truncated is True


def test_snapshot_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(schema_snapshot, "SNAPSHOT_DIR", tmp_path)
    assert not schema_snapshot.load_snapshot("X_DB").ok

    schema_snapshot.save_snapshot("X_DB", _snapshot())
    loaded = schema_snapshot.load_snapshot("X_DB")
    assert loaded.ok
    assert loaded.data["env_name"] == "X_DB"
    assert loaded.data["tables"][0]["note"] == "계정코드"


def test_page_tables_ranked_by_reference_count(tmp_path, monkeypatch):
    src = tmp_path / "src"
    mapper_dir = src / "server" / "ast" / "mapper"
    mapper_dir.mkdir(parents=True)
    (mapper_dir / "ast01_class_tree.xml").write_text("<mapper/>")
    (src / "Ast01_Tab_Info.java").write_text("class A {}")
    monkeypatch.setattr(legacy_page, "ASIS_SRC_DIR", src)

    db = tmp_path / "yunhee.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE mapper_index (mapper_name, sql_id, sql_type, tables, file_path)")
    rel = "server/ast/mapper/ast01_class_tree.xml"
    conn.executemany("INSERT INTO mapper_index VALUES (?, ?, ?, ?, ?)", [
        ("ast01_class_tree", "a", "select", "ast01_class_tree,sys09_code", rel),
        ("ast01_class_tree", "b", "select", "ast01_class_tree", rel),
        ("ast01_class_tree", "c", "select", "", rel),
        ("ast02_other", "d", "select", "zzz_other", "server/ast/mapper/ast02_other.xml"),
    ])
    conn.commit()
    conn.close()
    monkeypatch.setattr(page_schema, "DB_PATH", db)

    r = page_schema.page_tables("ast01")
    assert r.ok
    assert r.data == ["ast01_class_tree", "sys09_code"]


def test_table_cli_prints_only_dbml_on_stdout(tmp_path, monkeypatch):
    monkeypatch.setattr(schema_snapshot, "SNAPSHOT_DIR", tmp_path)
    schema_snapshot.save_snapshot("X_DB", _snapshot())
    runner = CliRunner()

    result = runner.invoke(cli.app, ["table", "act01_account_code", "nope", "--db", "X_DB"])
    assert result.exit_code == 0, result.output
    assert result.stdout.startswith('Table "public"."act01_account_code"')
    assert "nope" not in result.stdout
    assert "스냅샷에 없음: nope" in result.stderr

    assert runner.invoke(cli.app, ["table", "nope", "--db", "X_DB"]).exit_code == 1
    assert runner.invoke(cli.app, ["table", "x", "--db", "MISSING_DB"]).exit_code == 1
    assert runner.invoke(cli.app, ["table", "--db", "X_DB"]).exit_code == 1
