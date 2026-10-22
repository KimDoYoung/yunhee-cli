import json
from unittest.mock import MagicMock

from yunhee.agent.loop import AgentLoop
from yunhee.agent.registry import ToolRegistry


class DummyChoice:
    def __init__(self, message):
        self.message = message


class DummyResponse:
    def __init__(self, message):
        self.choices = [DummyChoice(message)]


class DummyFunction:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class DummyToolCall:
    def __init__(self, id, name, arguments):
        self.id = id
        self.function = DummyFunction(name, arguments)


class DummyMessage:
    def __init__(self, content=None, tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls or []
        self.role = "assistant"


def test_registry_dispatch():
    reg = ToolRegistry()
    reg.register(
        name="echo",
        func=lambda text: f"echo:{text}",
        description="echo text",
        parameters={"type": "object", "properties": {"text": {"type": "string"}}},
    )

    assert reg.has_tool("echo")
    res = reg.dispatch("echo", {"text": "hello"})
    assert res == "echo:hello"

    unknown = reg.dispatch("non_exist", {})
    assert "error" in unknown


def test_agent_loop_standard_tool_calls():
    reg = ToolRegistry()
    reg.register("add", lambda a, b: str(a + b), "add numbers", {})

    loop = AgentLoop(registry=reg)

    # 1번째 응답: add(2, 3) 도구 호출
    msg1 = DummyMessage(
        tool_calls=[DummyToolCall(id="call_1", name="add", arguments=json.dumps({"a": 2, "b": 3}))]
    )
    # 2번째 응답: 최종 텍스트 응답
    msg2 = DummyMessage(content="결과는 5입니다.")

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        DummyResponse(msg1),
        DummyResponse(msg2),
    ]
    loop._sync_client = mock_client

    called_tools = []
    final_text, history = loop.run(
        "2 더하기 3은?",
        on_tool_call=lambda name, args: called_tools.append((name, args)),
    )

    assert final_text == "결과는 5입니다."
    assert len(called_tools) == 1
    assert called_tools[0] == ("add", {"a": 2, "b": 3})
    # history에 system, user, assistant(tool_call), tool, assistant(final) 순서
    assert len(history) == 5


def test_agent_loop_fallback_tool_calls():
    reg = ToolRegistry()
    reg.register("greet", lambda name: f"Hello, {name}!", "greet", {})

    loop = AgentLoop(registry=reg)

    # 1번째 응답: 텍스트 본문(content) 안에 JSON 포함된 Fallback
    fallback_content = '도구를 실행합니다: {"name": "greet", "arguments": {"name": "World"}}'
    msg1 = DummyMessage(content=fallback_content, tool_calls=[])
    # 2번째 응답: 최종 완료 메시지
    msg2 = DummyMessage(content="인사가 완료되었습니다.", tool_calls=[])

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        DummyResponse(msg1),
        DummyResponse(msg2),
    ]
    loop._sync_client = mock_client

    called_tools = []
    final_text, _history = loop.run(
        "인사해줘",
        on_tool_call=lambda name, args: called_tools.append((name, args)),
    )

    assert final_text == "인사가 완료되었습니다."
    assert len(called_tools) == 1
    assert called_tools[0] == ("greet", {"name": "World"})


def test_agent_loop_infinite_loop_guard():
    reg = ToolRegistry()
    reg.register("ping", lambda: "pong", "ping", {})

    loop = AgentLoop(registry=reg)

    # 모델이 동일한 도구 호출을 계속 반복하는 상황 모의
    dup_call = DummyMessage(
        tool_calls=[DummyToolCall(id="c1", name="ping", arguments="{}")]
    )
    dup_call_again = DummyMessage(
        tool_calls=[DummyToolCall(id="c2", name="ping", arguments="{}")]
    )

    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = [
        DummyResponse(dup_call),
        DummyResponse(dup_call_again),
    ]
    loop._sync_client = mock_client

    final_text, _ = loop.run("루프 테스트")
    assert "반복 감지되어" in final_text
