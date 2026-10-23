"""
Tests for L1 Declarative Rules Memory (memory.py)
"""

from unittest.mock import patch

from yunhee.agent.memory import (
    MAX_RULE_LINES,
    get_rules_prompt_section,
    list_rules_text,
    load_rules,
    save_rule,
)


def test_load_rules_empty(tmp_path):
    mem_file = tmp_path / "memory.md"
    with patch("yunhee.agent.memory.get_memory_file_path", return_value=mem_file):
        rules = load_rules()
    assert rules == []


def test_save_and_load_rules(tmp_path):
    mem_file = tmp_path / "memory.md"
    with patch("yunhee.agent.memory.get_memory_file_path", return_value=mem_file):
        res1 = save_rule("DTO는 Java Record로 작성한다.")
        assert "성공적으로 저장" in res1

        res2 = save_rule("PostgreSQL DB를 기준으로 한다.")
        assert "성공적으로 저장" in res2

        rules = load_rules()
        assert len(rules) == 2
        assert "DTO는 Java Record로 작성한다." in rules
        assert "PostgreSQL DB를 기준으로 한다." in rules

        # 중복 방지 검증
        res_dup = save_rule("dto는 java record로 작성한다.")
        assert "이미 등록되어 있는 규칙" in res_dup
        assert len(load_rules()) == 2


def test_save_rule_limit_guard(tmp_path):
    mem_file = tmp_path / "memory.md"
    with patch("yunhee.agent.memory.get_memory_file_path", return_value=mem_file):
        # 40개 규칙 채우기
        for i in range(MAX_RULE_LINES):
            save_rule(f"규칙 {i}")

        assert len(load_rules()) == MAX_RULE_LINES

        # 41번째 규칙 시도 -> 가드 발동
        res_overflow = save_rule("41번째 초과 규칙")
        assert "최대 한도" in res_overflow
        assert len(load_rules()) == MAX_RULE_LINES


def test_get_rules_prompt_section(tmp_path):
    mem_file = tmp_path / "memory.md"
    with patch("yunhee.agent.memory.get_memory_file_path", return_value=mem_file):
        # 비어있을 때
        assert get_rules_prompt_section() == ""

        # 규칙 있을 때
        save_rule("컨벤션 A")
        section = get_rules_prompt_section()
        assert "[프로젝트 핵심 규칙 및 컨벤션" in section
        assert "- 컨벤션 A" in section


def test_list_rules_text(tmp_path):
    mem_file = tmp_path / "memory.md"
    with patch("yunhee.agent.memory.get_memory_file_path", return_value=mem_file):
        empty_text = list_rules_text()
        assert "등록된 핵심 규칙이 없습니다" in empty_text

        save_rule("규칙 1번")
        text = list_rules_text()
        assert "프로젝트 핵심 규칙" in text
        assert "1. 규칙 1번" in text
