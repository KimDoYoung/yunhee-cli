"""
Tests for Domain Helper Tools (domain_helper.py)
"""

from unittest.mock import patch

from yunhee.agent.tools.domain_helper import (
    lookup_config,
    read_recent_errors,
)


def test_lookup_config_summary():
    res = lookup_config()
    assert "[yunhee 현재 환경 설정 요약]" in res
    assert "work-dir" in res or "work_dir" in res


def test_lookup_config_single_key():
    with patch("yunhee.config.get_config_value", return_value="test_val"):
        res = lookup_config("TEST_KEY")
    assert "TEST_KEY: test_val" in res


def test_lookup_config_unknown_key():
    with (
        patch("yunhee.config.get_config_value", return_value=None),
        patch("yunhee.config.get_config_item", return_value=None),
    ):
        res = lookup_config("NON_EXISTING_KEY_XYZ")
    assert "알 수 없는 설정 키입니다" in res


def test_read_recent_errors():
    with patch("yunhee.tools.log_reader.get_errors_summary", return_value="ERROR: NullPointerException"):
        res = read_recent_errors(limit=3)
    assert "ERROR: NullPointerException" in res


def test_read_recent_errors_none():
    with patch("yunhee.tools.log_reader.get_errors_summary", return_value=""):
        res = read_recent_errors(limit=3)
    assert "감지된 WARN/ERROR 에러가 없습니다" in res
