"""
Tests for project initialization and mcp.json generation
"""

import json

from yunhee import project


def test_project_init_creates_project_and_mcp_json(tmp_path):
    data = project.init(root=tmp_path)
    assert data["name"] == tmp_path.name
    assert data["mcp_created"] is True

    # project.json 검증
    pfile = tmp_path / ".yunhee" / "project.json"
    assert pfile.is_file()
    pdata = json.loads(pfile.read_text(encoding="utf-8"))
    assert pdata["yunhee_version"] == project.current_version()

    # mcp.json 검증
    mfile = tmp_path / ".yunhee" / "mcp.json"
    assert mfile.is_file()
    mdata = json.loads(mfile.read_text(encoding="utf-8"))
    assert "mcpServers" in mdata
    assert "time" in mdata["mcpServers"]
    assert "fetch" in mdata["mcpServers"]
    assert mdata["mcpServers"]["time"]["command"] == "uvx"
    assert mdata["mcpServers"]["fetch"]["command"] == "uvx"


def test_project_init_preserves_existing_mcp_json(tmp_path):
    pdir = tmp_path / ".yunhee"
    pdir.mkdir(parents=True, exist_ok=True)
    mfile = pdir / "mcp.json"
    custom_content = '{"mcpServers": {"custom": {"command": "echo"}}}'
    mfile.write_text(custom_content, encoding="utf-8")

    data = project.init(root=tmp_path)
    assert data["mcp_created"] is False

    # 기존 mcp.json이 변경되지 않았는지 검증
    assert mfile.read_text(encoding="utf-8") == custom_content
