import json

from yunhee.agent.session import SessionLogger


def test_session_logger_creation(tmp_path):
    logger = SessionLogger(session_id="test_session_1", base_dir=tmp_path)
    assert logger.jsonl_path.exists() is False
    assert logger.md_path.exists() is True  # 헤더가 생성됨

    # 마크다운 헤더 확인
    md_text = logger.md_path.read_text(encoding="utf-8")
    assert "test_session_1" in md_text


def test_session_logger_logging_cycle(tmp_path):
    logger = SessionLogger(session_id="test_session_2", base_dir=tmp_path)

    # 1. 유저 메시지
    logger.log_user_message("Hello Yunhee")

    # 2. 도구 호출 및 결과
    logger.log_tool_call("grep_search", {"query": "test"})
    logger.log_tool_result("grep_search", "src/test.py:1: def test(): pass")

    # 3. 어시스턴트 답변
    logger.log_assistant_message("테스트를 찾았습니다.")

    # JSONL 검증
    assert logger.jsonl_path.exists() is True
    lines = logger.jsonl_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4

    record0 = json.loads(lines[0])
    assert record0["role"] == "user"
    assert record0["content"] == "Hello Yunhee"

    record1 = json.loads(lines[1])
    assert record1["role"] == "tool_call"
    assert record1["name"] == "grep_search"

    record2 = json.loads(lines[2])
    assert record2["role"] == "tool_result"
    assert "src/test.py:1" in record2["result"]

    record3 = json.loads(lines[3])
    assert record3["role"] == "assistant"
    assert record3["content"] == "테스트를 찾았습니다."

    # MD 검증
    md_content = logger.md_path.read_text(encoding="utf-8")
    assert "👤 User" in md_content
    assert "Hello Yunhee" in md_content
    assert "🛠 **도구 호출**" in md_content
    assert "grep_search" in md_content
    assert "🤖 Yunhee" in md_content
    assert "테스트를 찾았습니다." in md_content
