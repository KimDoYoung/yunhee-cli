"""
Tests for yunhee-cli Agentic REPL and UI components
"""

from unittest.mock import patch

from yunhee.ui.components import (
    EscCancelListener,
    format_tool_call_status,
    format_tool_result_preview,
    listen_esc_cancel,
    render_tools_table,
)
from yunhee.ui.repl import (
    ALL_AUTOCOMPLETE_COMMANDS,
    BUILTIN_COMMANDS,
    HYBRID_COMMANDS,
    _handle_hybrid_command,
    _help_text,
)


def test_format_tool_call_status():
    status = format_tool_call_status("read_file", {"filename": "test.txt"})
    assert "read_file" in status
    assert "test.txt" in status
    assert "ESC 2회" in status

    # 긴 인자 처리
    long_status = format_tool_call_status("write_file", {"filename": "a.txt", "content": "x" * 100})
    assert "..." in long_status


def test_format_tool_result_preview_short():
    res = format_tool_result_preview("list_files", "file1.txt\nfile2.txt")
    assert "✔ 도구 완료 (list_files)" in res
    assert "file1.txt" in res
    assert "file2.txt" in res
    assert "생략" not in res


def test_format_tool_result_preview_long():
    long_res = "\n".join(f"line {i}" for i in range(10))
    preview = format_tool_result_preview("grep_search", long_res, max_lines=3)
    assert "✔ 도구 완료 (grep_search)" in preview
    assert "line 0" in preview
    assert "line 2" in preview
    assert "외 7줄 생략" in preview


def test_render_tools_table():
    schemas = [
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "디렉터리 파일 목록을 조회합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {"directory": {"type": "string"}},
                },
            },
        }
    ]
    table = render_tools_table(schemas)
    assert table.title == "🤖 등록된 에이전트 도구 목록"
    assert len(table.rows) == 1


def test_listen_esc_cancel():
    called = False

    def on_cancel():
        nonlocal called
        called = True

    with listen_esc_cancel(on_cancel) as listener:
        assert isinstance(listener, EscCancelListener)
    assert not called


def test_help_text_contains_essential_commands():
    text = _help_text()
    assert "/help" in text
    assert "/tools" in text
    assert "/session" in text
    assert "/memory" in text
    assert "/knowledge" in text
    assert "/table" in text
    assert "/clear" in text
    assert "ESC 2회" in text


def test_command_lists():
    assert "/help" in BUILTIN_COMMANDS
    assert "/tools" in BUILTIN_COMMANDS
    assert "/memory" in BUILTIN_COMMANDS
    assert "/knowledge" in BUILTIN_COMMANDS
    assert "/table" in HYBRID_COMMANDS
    for cmd in BUILTIN_COMMANDS:
        assert cmd in ALL_AUTOCOMPLETE_COMMANDS
    for cmd in HYBRID_COMMANDS:
        assert cmd in ALL_AUTOCOMPLETE_COMMANDS


def test_handle_hybrid_command():
    history = [{"role": "system", "content": "init"}]
    with patch("yunhee.ui.repl.run_command", return_value="output of test command"):
        new_history = _handle_hybrid_command("/table sys01_company", history)

    assert len(new_history) == 2
    assert new_history[1]["role"] == "user"
    assert "output of test command" in new_history[1]["content"]
    assert "/table sys01_company" in new_history[1]["content"]
