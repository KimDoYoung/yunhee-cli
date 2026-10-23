"""Agent DB SQL 도구 및 레지스트리 디스패치 단위 테스트."""

from unittest.mock import patch

from yunhee.agent.registry import create_default_registry
from yunhee.agent.tools.db_sql import execute_sql
from yunhee.tools.base import ToolResult


def test_execute_sql_success():
    mock_res = ToolResult(
        ok=True,
        data={
            "summary": "rows=1  count=664",
            "table": {
                "total_rows": 1,
                "columns": ["count"],
                "rows": [{"count": 664}],
            },
        },
    )
    with patch("yunhee.agent.tools.db_sql._run_sql", return_value=mock_res):
        out = execute_sql("SELECT count(*) FROM information_schema.tables")

    assert "**쿼리 요약:** `rows=1  count=664`" in out
    assert "| count |" in out
    assert "| 664 |" in out


def test_execute_sql_empty_query():
    out = execute_sql("   ")
    assert "error: 쿼리가 비어 있습니다." in out


def test_execute_sql_failure():
    mock_res = ToolResult(ok=False, error="syntax error at or near 'FORM'")
    with patch("yunhee.agent.tools.db_sql._run_sql", return_value=mock_res):
        out = execute_sql("SELECT FORM sys01")

    assert "SQL 실행 실패: syntax error" in out


def test_registry_has_run_sql():
    reg = create_default_registry(load_mcp=False)
    assert reg.has_tool("run_sql")

    tool_def = reg.get("run_sql")
    assert tool_def is not None
    assert "asseterpdb" in tool_def.description
    assert "query" in tool_def.parameters["properties"]

    # 디스패치 테스트
    with patch("yunhee.agent.tools.db_sql._run_sql") as mock_run:
        mock_run.return_value = ToolResult(
            ok=True,
            data={"summary": "rows=1", "table": {"columns": ["val"], "rows": [{"val": 1}]}},
        )
        res = reg.dispatch("run_sql", {"query": "SELECT 1"})
        assert "| val |" in res


def test_get_table_schema_from_snapshot():
    from yunhee.agent.tools.db_sql import get_table_schema

    with (
        patch("yunhee.tools.schema_snapshot.load_snapshot") as mock_load,
        patch("yunhee.tools.schema_snapshot.slice_tables") as mock_slice,
    ):
        mock_load.return_value = ToolResult(ok=True, data={"tables": {}})
        mock_slice.return_value = ToolResult(ok=True, data={"dbml": 'Table "public"."sys06_menu" { id numeric }'})
        res = get_table_schema("sys06_menu")

    assert "```dbml" in res
    assert 'Table "public"."sys06_menu"' in res


def test_execute_sql_intercepts_backslash_d():
    with patch("yunhee.agent.tools.db_sql.get_table_schema") as mock_schema:
        mock_schema.return_value = '```dbml\nTable "public"."sys06_menu" {}\n```'
        res = execute_sql(r"\d sys06_menu")
        assert 'Table "public"."sys06_menu"' in res
        mock_schema.assert_called_once_with("sys06_menu")

    with patch("yunhee.agent.tools.db_sql.get_table_schema") as mock_schema:
        mock_schema.return_value = '```dbml\nTable "public"."sys06_menu" {}\n```'
        res = execute_sql("DESCRIBE sys06_menu;")
        assert 'Table "public"."sys06_menu"' in res
        mock_schema.assert_called_once_with("sys06_menu")


def test_registry_has_get_table_schema():
    reg = create_default_registry(load_mcp=False)
    assert reg.has_tool("get_table_schema")

    tool_def = reg.get("get_table_schema")
    assert tool_def is not None
    assert "DBML" in tool_def.description
    assert "table_name" in tool_def.parameters["properties"]

    res = reg.dispatch("get_table_schema", {"table_name": "sys06_menu"})
    assert 'Table "public"."sys06_menu"' in res


