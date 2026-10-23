import os
from unittest.mock import patch

from typer.testing import CliRunner

from yunhee import config
from yunhee.cli import app

runner = CliRunner()


def test_get_config_item_lookup():
    # 주 환경변수명으로 조회
    item = config.get_config_item("YUNHEE_ASIS_SRC_DIR")
    assert item is not None
    assert item.key == "YUNHEE_ASIS_SRC_DIR"

    # 접두사 없는 형태
    item2 = config.get_config_item("ASIS_SRC_DIR")
    assert item2 is not None
    assert item2.key == "YUNHEE_ASIS_SRC_DIR"

    # 별칭 (하이픈, 언더스코어, 소문자)
    assert config.get_config_item("asis-src") == item
    assert config.get_config_item("asis_src") == item
    assert config.get_config_item("asis") == item

    # 다른 주요 키들
    assert config.get_config_item("work-dir") is not None
    assert config.get_config_item("WORK_DIR") is not None
    assert config.get_config_item("YUNHEE_DB") is not None
    assert config.get_config_item("yunhee-db") is not None
    assert config.get_config_item("LOCAL_DB") is not None
    assert config.get_config_item("local-db") is not None
    assert config.get_config_item("TEST_DB") is not None
    assert config.get_config_item("ollama-url") is not None
    assert config.get_config_item("YUNHEE_OLLAMA_URL") is not None


def test_get_config_value_raw_and_masked():
    # YUNHEE_ASIS_SRC_DIR
    val = config.get_config_value("YUNHEE_ASIS_SRC_DIR")
    assert val == str(config.ASIS_SRC_DIR)

    # WORK_DIR
    val_work = config.get_config_value("work-dir")
    assert val_work == str(config.WORK_DIR)

    # 비밀번호 마스킹 테스트
    # TEST_ADMIN_PASS
    raw_pass = config.get_config_value("TEST_ADMIN_PASS", raw=True)
    masked_pass = config.get_config_value("TEST_ADMIN_PASS", raw=False)
    assert raw_pass == config.TEST_ADMIN_PASS
    assert masked_pass == "***"


def test_get_config_value_env_fallback():
    # 정의되지 않은 임의의 환경변수
    with patch.dict(os.environ, {"MY_CUSTOM_TEST_VAR": "hello_yunhee"}):
        assert config.get_config_value("MY_CUSTOM_TEST_VAR") == "hello_yunhee"
        assert config.get_config_value("my_custom_test_var") == "hello_yunhee"


def test_cli_value_single_key():
    # 단일 키 조회 -> 해당 값만 텍스트로 출력
    result = runner.invoke(app, ["value", "YUNHEE_ASIS_SRC_DIR"])
    assert result.exit_code == 0
    assert result.stdout.strip() == str(config.ASIS_SRC_DIR)

    # 별칭으로 조회
    result_alias = runner.invoke(app, ["value", "asis-src"])
    assert result_alias.exit_code == 0
    assert result_alias.stdout.strip() == str(config.ASIS_SRC_DIR)


def test_cli_value_list_no_args():
    # 인자 없이 실행 시 설정 목록 테이블 출력
    result = runner.invoke(app, ["value"])
    assert result.exit_code == 0
    assert "yunhee 설정 키 목록" in result.stdout
    assert "YUNHEE_ASIS_SRC_DIR" in result.stdout
    assert "LOCAL_DB" in result.stdout
    assert "사용법:" in result.stdout


def test_cli_value_list_flag():
    # --list 플래그 실행 시 테이블 출력
    result = runner.invoke(app, ["value", "--list"])
    assert result.exit_code == 0
    assert "yunhee 설정 키 목록" in result.stdout


def test_cli_value_keys_flag():
    # --keys 플래그 실행 시 키 이름만 출력
    result = runner.invoke(app, ["value", "--keys"])
    assert result.exit_code == 0
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    assert "YUNHEE_ASIS_SRC_DIR" in lines
    assert "WORK_DIR" in lines
    assert "LOCAL_DB" in lines


def test_cli_value_invalid_key():
    # 존재하지 않는 키 조회 시 에러 메시지 및 exit_code 1
    result = runner.invoke(app, ["value", "completely_nonexistent_key_xyz"])
    assert result.exit_code == 1
    assert "알 수 없는 설정 키" in result.stderr or "알 수 없는 설정 키" in result.stdout
