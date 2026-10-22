from yunhee.agent.parser import extract_tool_calls_from_text, sanitize_json_text


def test_sanitize_json_text():
    # 유니코드 큰따옴표 및 작은따옴표 치환
    raw = '“hello” ‘world’ \u00A0'
    cleaned = sanitize_json_text(raw)
    assert cleaned == '"hello" \'world\'  '


def test_parser_pure_json():
    text = '{"name": "read_file", "arguments": {"filename": "test.txt"}}'
    calls = extract_tool_calls_from_text(text)
    assert len(calls) == 1
    assert calls[0] == ("read_file", {"filename": "test.txt"})


def test_parser_markdown_codeblock():
    text = """
여기 도구를 실행합니다:
```json
{
  "name": "list_files",
  "arguments": {"directory": "src"}
}
```
확인해주세요.
"""
    calls = extract_tool_calls_from_text(text)
    assert len(calls) == 1
    assert calls[0] == ("list_files", {"directory": "src"})


def test_parser_json_array():
    text = """
[
  {"name": "list_files", "arguments": {}},
  {"name": "read_file", "arguments": {"filename": "app.py"}}
]
"""
    calls = extract_tool_calls_from_text(text)
    assert len(calls) == 2
    assert calls[0] == ("list_files", {})
    assert calls[1] == ("read_file", {"filename": "app.py"})


def test_parser_depth_bracket_in_text():
    # 텍스트 사이에 JSON이 끼어있는 경우
    text = '파일을 읽어볼게요: {"name": "read_file", "arguments": {"filename": "config.py"}} 잠시만 기다려주세요.'
    calls = extract_tool_calls_from_text(text)
    assert len(calls) == 1
    assert calls[0] == ("read_file", {"filename": "config.py"})


def test_parser_nested_openai_function_format():
    text = '{"type": "function", "function": {"name": "run_command", "arguments": "{\\"command\\": \\"ls\\"}"}}'
    calls = extract_tool_calls_from_text(text)
    assert len(calls) == 1
    assert calls[0] == ("run_command", {"command": "ls"})


def test_parser_alt_keys():
    text = '{"tool": "write_file", "parameters": {"filename": "a.txt", "content": "abc"}}'
    calls = extract_tool_calls_from_text(text)
    assert len(calls) == 1
    assert calls[0] == ("write_file", {"filename": "a.txt", "content": "abc"})


def test_parser_plain_text():
    text = "안녕하세요! 무엇을 도와드릴까요? 오늘은 좋은 날씨입니다."
    calls = extract_tool_calls_from_text(text)
    assert calls == []


def test_parser_alias_grep_with_list_args():
    # 사용자가 겪은 실제 케이스: grep 이름과 리스트 형태 인자
    text = """```json
{
  "name": "grep",
  "arguments": [
    "-rnw",
    ".",
    "-e",
    "class AgentLoop"
  ]
}
```"""
    calls = extract_tool_calls_from_text(text)
    assert len(calls) == 1
    assert calls[0] == ("grep_search", {"query": "class AgentLoop"})

