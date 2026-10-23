"""
Tests for MCP Adapter (mcp_adapter.py)
"""

from unittest.mock import AsyncMock, patch

from yunhee.agent.registry import ToolRegistry
from yunhee.agent.tools.mcp_adapter import MCPManager


def test_mcp_manager_load_config_empty(tmp_path):
    mgr = MCPManager(config_path=tmp_path / "non_existing.json")
    cfg = mgr.load_config()
    assert cfg == {}


def test_mcp_manager_load_config_valid(tmp_path):
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text('{"mcpServers": {"time": {"command": "uvx"}}}', encoding="utf-8")
    mgr = MCPManager(config_path=cfg_file)
    cfg = mgr.load_config()
    assert "mcpServers" in cfg
    assert "time" in cfg["mcpServers"]


def test_mcp_manager_connect_and_register(tmp_path):
    cfg_file = tmp_path / "mcp.json"
    cfg_file.write_text('{"mcpServers": {"test_srv": {"command": "uvx", "args": ["test"]}}}', encoding="utf-8")
    mgr = MCPManager(config_path=cfg_file)

    # _connect_server 모킹
    mock_tools_meta = [
        {
            "server": "test_srv",
            "name": "get_current_time",
            "description": "Get the current time in a timezone",
            "parameters": {"type": "object", "properties": {"timezone": {"type": "string"}}},
        }
    ]

    with patch.object(mgr, "_connect_server", new_callable=AsyncMock, return_value=mock_tools_meta):
        tools = mgr.connect_all()
        assert len(tools) == 1
        assert tools[0]["name"] == "get_current_time"

        # ToolRegistry에 등록
        reg = ToolRegistry()
        reg_count = mgr.register_tools_to_registry(reg)
        assert reg_count == 1
        assert reg.has_tool("get_current_time")

        # 도구 스키마 확인
        schemas = reg.get_schemas()
        assert len(schemas) == 1
        assert schemas[0]["function"]["name"] == "get_current_time"


def test_mcp_call_tool_mock(tmp_path):
    mgr = MCPManager(config_path=tmp_path / "mcp.json")
    mgr._tool_to_server["time_now"] = "srv1"

    def fake_run(coro, timeout=30):
        coro.close()
        return "2026-10-23T12:00:00Z"

    with patch.object(mgr, "_run_coro_sync", side_effect=fake_run):
        output = mgr.call_tool("time_now", {"timezone": "UTC"})
        assert output == "2026-10-23T12:00:00Z"

    mgr.close()
