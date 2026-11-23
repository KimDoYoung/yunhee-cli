"""YUNHEE_DIR 탐색, .env.yunhee 로드, 하드코딩 제거 회귀 테스트."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from yunhee import config
from yunhee.agent.tools.ext_gotenberg import convert_markdown_to_pdf
from yunhee.store import db
from yunhee.tools import log_reader


def test_find_yunhee_dir_env_override(tmp_path: Path, monkeypatch):
    custom_home = tmp_path / "custom_yunhee"
    custom_home.mkdir()
    monkeypatch.setenv("YUNHEE_DIR", str(custom_home))

    assert config._find_yunhee_dir() == custom_home.resolve()


def test_find_yunhee_dir_site_packages_fallback_to_home(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("YUNHEE_DIR", raising=False)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    fake_site_pkg = tmp_path / "venv" / "lib" / "python3.13" / "site-packages" / "yunhee" / "config.py"
    fake_site_pkg.parent.mkdir(parents=True)
    fake_site_pkg.write_text("# stub", encoding="utf-8")

    monkeypatch.setattr(config, "__file__", str(fake_site_pkg))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    assert config._find_yunhee_dir() == fake_home / ".yunhee"


def test_find_yunhee_dir_dev_source_tree(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("YUNHEE_DIR", raising=False)
    repo_root = tmp_path / "repo"
    cfg_file = repo_root / "src" / "yunhee" / "config.py"
    cfg_file.parent.mkdir(parents=True)
    cfg_file.write_text("# stub", encoding="utf-8")
    (repo_root / "pyproject.toml").write_text("[project]\nname='yunhee'\n", encoding="utf-8")

    monkeypatch.setattr(config, "__file__", str(cfg_file))

    assert config._find_yunhee_dir() == repo_root.resolve()


def test_store_db_path_follows_yunhee_dir():
    expected = config.YUNHEE_DIR / "data" / "db" / "yunhee.db"
    assert db.DB_PATH == expected


def test_gotenberg_unset_returns_clear_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(config, "GOTENBERG_URL", "")
    ok, msg = convert_markdown_to_pdf("# Hello", tmp_path / "out.pdf")
    assert ok is False
    assert "YUNHEE_GOTENBERG_URL" in msg


def test_log_reader_no_hardcoded_docker_fallback(monkeypatch):
    monkeypatch.delenv("YUNHEE_LOG_DOCKER", raising=False)
    monkeypatch.delenv("YUNHEE_LOG_DIR", raising=False)
    monkeypatch.setattr(config, "LOG_DOCKER", "")
    monkeypatch.setattr(config, "LOG_DIR", "")

    docker, dir_str, _, tz_str = log_reader.resolve_log_source(source="docker")
    assert docker == ""
    assert dir_str == ""
    assert tz_str == "KST"


def test_new_config_items_registered():
    for key in ("YUNHEE_DB_NAME", "YUNHEE_LOG_ACCESS_LOGGER", "YUNHEE_JAVA_BASE_PACKAGE"):
        item = config.get_config_item(key)
        assert item is not None, f"ConfigItem 누락: {key}"
        assert config.get_config_value(key) != ""


def test_clean_env_subprocess_has_no_personal_hardcodings(tmp_path: Path):
    """환경변수·설정 파일이 전혀 없는 새 PC 환경에서 config 모듈 임포트 시 개인 경로가 노출되지 않는다."""
    fake_home = tmp_path / "empty_home"
    fake_home.mkdir()
    work_dir = tmp_path / "empty_work"
    work_dir.mkdir()

    # 전역 ~/.yunhee/.env.yunhee 와 로컬 .env.yunhee 우선순위까지 함께 검증
    dot_yunhee = fake_home / ".yunhee"
    dot_yunhee.mkdir()
    (dot_yunhee / ".env.yunhee").write_text(
        'YUNHEE_LOG_DOCKER="global-tomcat"\nYUNHEE_DB="postgresql://u:p@localhost:5432/customdb"\n',
        encoding="utf-8",
    )
    (work_dir / ".env.yunhee").write_text(
        'YUNHEE_LOG_DOCKER="local-tomcat"\n',
        encoding="utf-8",
    )

    pkg_root = str(Path(config.__file__).resolve().parents[1])
    env = {
        "HOME": str(fake_home),
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": pkg_root,
    }
    code = (
        "import json; from yunhee import config; "
        "print(json.dumps({"
        "'log_docker': config.LOG_DOCKER, "
        "'db_name': config.DEFAULT_DB_NAME, "
        "'gotenberg': config.GOTENBERG_URL, "
        "'asis': str(config.ASIS_SRC_DIR) if config.ASIS_SRC_DIR else '', "
        "'log_dir': config.LOG_DIR, "
        "'global_env': str(config.GLOBAL_ENV_FILE), "
        "'local_env': str(config.LOCAL_ENV_FILE)"
        "}))"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=work_dir,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    import json

    data = json.loads(proc.stdout.strip())
    assert data["log_docker"] == "local-tomcat"  # 로컬이 전역 오버라이드
    assert data["db_name"] == "customdb"  # YUNHEE_DB URL에서 추출
    assert data["gotenberg"] == ""
    assert data["asis"] == ""
    assert data["log_dir"] == ""
    assert data["global_env"] == str((dot_yunhee / ".env.yunhee").resolve())
    assert data["local_env"] == str((work_dir / ".env.yunhee").resolve())


def test_no_personal_hardcoded_tokens_in_src():
    """src/yunhee/**/*.py 에 특정 개발자 계정/개인 DDNS/하드코딩 컨테이너명이 남지 않았는지 검사."""
    src_root = Path(__file__).resolve().parents[1] / "src" / "yunhee"
    forbidden = ("kdy987", "jskn.iptime.org", "omen-tomcat", "oms-data")
    offenders: list[str] = []
    for py_file in sorted(src_root.rglob("*.py")):
        text = py_file.read_text(encoding="utf-8")
        for idx, line in enumerate(text.splitlines(), 1):
            for tok in forbidden:
                if tok in line:
                    offenders.append(f"{py_file.relative_to(src_root)}:{idx} ({tok})")
    assert offenders == [], f"개인/머신 하드코딩 잔존: {offenders}"


def test_local_env_does_not_fallback_to_env_local_in_same_global_dir(tmp_path: Path):
    """같은 디렉터리의 .env.yunhee가 전역 파일이면 같은 폴더의 .env.local을 로컬 오버라이드로 읽지 않는다."""
    env_yunhee = tmp_path / ".env.yunhee"
    env_local = tmp_path / ".env.local"
    env_yunhee.write_text('YUNHEE_DB="postgresql://u:p@localhost:5432/newdb"\n', encoding="utf-8")
    env_local.write_text('YUNHEE_DB="postgresql://u:p@localhost:5432/olddb"\n', encoding="utf-8")

    local_found = config._find_local_env_file(tmp_path, global_env=env_yunhee)
    assert local_found is None


def test_find_yunhee_dir_expands_dollar_home(tmp_path: Path, monkeypatch):
    """YUNHEE_DIR="$HOME/.yunhee" 형태도 환경변수 확장으로 정상 인식된다."""
    fake_home = tmp_path / "home"
    target = fake_home / ".yunhee"
    target.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("YUNHEE_DIR", "$HOME/.yunhee")

    assert config._find_yunhee_dir() == target.resolve()


def test_init_global_cli_and_missing_warning(tmp_path: Path, monkeypatch):
    """~/.yunhee/.env.yunhee 미존재 시 안내 출력, yunhee init --global로 생성 및 내용 표시 검증."""
    from typer.testing import CliRunner

    from yunhee import project
    from yunhee.cli import app

    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    runner = CliRunner()

    # 1. ~/.yunhee 없을 때 일반 커맨드 실행 -> stdout은 깨끗하고 stderr에 안내 표시
    assert config.needs_global_init() is True
    res_before = runner.invoke(app, ["value", "WORK_DIR"])
    assert res_before.exit_code == 0
    assert res_before.stdout.strip() == str(config.WORK_DIR)
    assert "yunhee init --global" in res_before.stderr

    # 2. yunhee init --global 실행 -> 파일 생성 + 설정 내용 출력 (경고 없음)
    res_init = runner.invoke(app, ["init", "--global"])
    assert res_init.exit_code == 0
    env_file = fake_home / ".yunhee" / ".env.yunhee"
    assert env_file.is_file()
    assert "YUNHEE_DB" in res_init.stdout
    assert "yunhee init --global" not in res_init.stderr
    assert config.needs_global_init() is False

    # 3. 기존 파일에 실제 비밀번호 저장 후 재실행 -> 덮어쓰지 않고 마스킹된 내용 표시
    env_file.write_text(
        'YUNHEE_DB="postgresql://alice:s3cr3t@localhost:5432/prod"\nYUNHEE_TEST_ADMIN_PASS="myrealpass"\n',
        encoding="utf-8",
    )
    res_again = runner.invoke(app, ["init", "--global"])
    assert res_again.exit_code == 0
    assert "이미 존재합니다" in res_again.stdout
    assert "s3cr3t" not in res_again.stdout
    assert "myrealpass" not in res_again.stdout
    assert "postgresql://alice:***@localhost:5432/prod" in res_again.stdout

    # 4. --force 실행 -> 샘플로 덮어쓰기
    res_force = runner.invoke(app, ["init", "--global", "--force"])
    assert res_force.exit_code == 0
    assert "덮어쓰기 완료" in res_force.stdout
    assert "alice" not in env_file.read_text(encoding="utf-8")
    assert project.redact_env_content('YUNHEE_TEST_PASS="abc"\n') == 'YUNHEE_TEST_PASS="***"\n'
