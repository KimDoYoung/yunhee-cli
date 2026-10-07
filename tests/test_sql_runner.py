"""sql_runner 도구 및 sql 서브커맨드 테스트."""

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools import sql_runner


def test_split_statements_simple():
    sql = "SELECT 1; SELECT 2; SELECT 3;"
    stmts = sql_runner.split_statements(sql)
    assert len(stmts) == 3
    assert stmts[0] == "SELECT 1"
    assert stmts[1] == "SELECT 2"
    assert stmts[2] == "SELECT 3"


def test_split_statements_with_gset():
    sql = """
    SELECT f_create_seq() AS cid \\gset
    INSERT INTO test (id) VALUES (:cid);
    """
    stmts = sql_runner.split_statements(sql)
    assert len(stmts) == 2
    assert "\\gset" in stmts[0]
    assert "INSERT INTO test" in stmts[1]


def test_split_statements_with_comments_and_strings():
    sql = """
    -- 세미콜론이 있는 주석 ;
    SELECT 'hello; world' AS msg;
    /* 블록 주석 ; */
    SELECT 42;
    """
    stmts = sql_runner.split_statements(sql)
    assert len(stmts) == 2
    assert "hello; world" in stmts[0]
    assert "42" in stmts[1]


def test_rollback_guard_ddl_rejection():
    # CREATE/ALTER/DROP/COMMIT/END 등 DDL 및 COMMIT 차단
    res = sql_runner.run_sql(query="CREATE TABLE foo (id int);", rollback=True)
    assert not res.ok
    assert "CREATE" in res.error

    res_drop = sql_runner.run_sql(query="DROP TABLE foo;", rollback=True)
    assert not res_drop.ok
    assert "DROP" in res_drop.error

    res_commit = sql_runner.run_sql(query="COMMIT;", rollback=True)
    assert not res_commit.ok
    assert "COMMIT" in res_commit.error


def test_cli_sql_read_only():
    runner = CliRunner()
    result = runner.invoke(cli.app, ["sql", "SELECT 1 AS num"])
    assert result.exit_code == 0
    assert "rows=1" in result.output
    assert "num" in result.output


def test_guard_blocks_writes_in_read_only_mode():
    # DB 접속 전에 거부되므로 DB 없이도 검증된다.
    res = sql_runner.run_sql(query="update sys01_company set sys01_note=sys01_note where sys01_company_id=-1")
    assert not res.ok
    assert "읽기 전용 모드" in res.error and "--rollback" in res.error

    for q in ("select 1; commit", "select 1; end", "begin; select 1", "call p()", "set default_transaction_read_only = off"):
        assert not sql_runner.run_sql(query=q).ok, q

    res_cte = sql_runner.run_sql(query="with x as (delete from t returning *) select * from x")
    assert not res_cte.ok
    assert "DELETE" in res_cte.error


def test_guard_keyword_false_positives():
    # CASE … END, 문자열 안의 commit, 주석은 가드에 걸리지 않는다.
    assert sql_runner.guard_statement("select case when a then 'commit' end from t", rollback=False) is None
    assert sql_runner.guard_statement("-- update\nselect 1", rollback=False) is None
    assert sql_runner.guard_statement("select * from t for update", rollback=False) is None
    assert sql_runner.guard_statement("rollback", rollback=False) is None
    assert sql_runner.guard_statement("savepoint a", rollback=False) is None
    # --rollback 모드는 쓰기·CALL 허용, COMMIT/DDL은 거부
    assert sql_runner.guard_statement("update t set a = 1", rollback=True) is None
    assert sql_runner.guard_statement("call p(1)", rollback=True) is None
    assert sql_runner.guard_statement("commit", rollback=True) is not None


def test_proc_has_tx_control():
    class FakeCursor:
        def __init__(self, src: str) -> None:
            self.src, self.params = src, None

        def execute(self, query, params=None):
            self.params = params

        def fetchall(self):
            return [{"prosrc": self.src}]

    cur = FakeCursor("BEGIN INSERT INTO t VALUES (1); COMMIT; END")
    assert sql_runner.proc_has_tx_control(cur, "CALL public.my_proc(1)") == "my_proc"
    assert cur.params == ["my_proc", "public"]
    assert sql_runner.proc_has_tx_control(FakeCursor("BEGIN -- commit\n INSERT INTO t VALUES (1); END"), "call p(1)") is None


def _db_available() -> bool:
    res = sql_runner.run_sql(query="select 1 as one")
    return res.ok


def test_db_read_only_mode_is_on():
    import pytest

    if not _db_available():
        pytest.skip("DB 없음")
    res = sql_runner.run_sql(query="select current_setting('transaction_read_only') ro")
    assert res.ok
    assert "ro=on" in res.data["summary"]
    # ROLLBACK으로 트랜잭션을 끝내도 다음 트랜잭션도 읽기 전용
    res2 = sql_runner.run_sql(query="rollback; select current_setting('transaction_read_only') ro")
    assert res2.ok
    assert "| on |" in res2.data["summary"]


def test_db_rollback_mode_leaves_no_change():
    import pytest

    if not _db_available():
        pytest.skip("DB 없음")
    res = sql_runner.run_sql(query="create temp table if not exists _x (id int)", rollback=True)
    assert not res.ok  # DDL은 --rollback에서도 거부
    res = sql_runner.run_sql(
        query="select current_setting('transaction_read_only') ro; select 1 as one",
        rollback=True,
    )
    assert res.ok
    assert "남은 변경 없음" in res.data["summary"]
