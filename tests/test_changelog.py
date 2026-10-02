import tomllib
from pathlib import Path

from typer.testing import CliRunner

from yunhee import changelog, cli

SAMPLE = """# 변경 이력

## [0.1.10] - 2026-10-05
- 열 번째

## [0.1.9] - 2026-10-04
- 아홉 번째

## [0.1.3] - 2026-10-01
- 세 번째
"""


def test_parse_orders_by_numeric_version():
    entries = changelog.parse(SAMPLE)
    assert [e.version for e in entries] == ["0.1.10", "0.1.9", "0.1.3"]
    assert entries[0].date == "2026-10-05"
    assert entries[0].body == "- 열 번째"


def test_select_modes():
    entries = changelog.parse(SAMPLE)
    assert [e.version for e in changelog.select(entries, version="0.1.9")] == ["0.1.9"]
    assert [e.version for e in changelog.select(entries, since="0.1.3")] == ["0.1.10", "0.1.9"]
    assert [e.version for e in changelog.select(entries, current="0.1.3")] == ["0.1.3"]
    assert len(changelog.select(entries, show_all=True)) == 3
    assert changelog.select(entries, version="9.9.9") == []


def test_current_pyproject_version_has_entry():
    # 버전을 올렸으면 src/yunhee/CHANGELOG.md에 항목도 추가해야 한다
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]
    versions = [e.version for e in changelog.parse(changelog.read_text())]
    assert version in versions, f"CHANGELOG.md에 [{version}] 항목이 없습니다"
    assert versions[0] == version, "CHANGELOG.md 맨 위 항목이 pyproject 버전이어야 합니다"


def test_changes_since(monkeypatch):
    monkeypatch.setattr(changelog, "read_text", lambda: SAMPLE)
    assert [e.version for e in changelog.changes_since("0.1.3", "0.1.9")] == ["0.1.9"]
    assert changelog.changes_since("0.1.10", "0.1.10") == []


def test_changelog_cli(monkeypatch):
    monkeypatch.setattr(changelog, "read_text", lambda: SAMPLE)
    monkeypatch.setattr(cli.project, "current_version", lambda: "0.1.10")
    runner = CliRunner()

    res = runner.invoke(cli.app, ["changelog"])
    assert res.exit_code == 0
    assert "## [0.1.10] - 2026-10-05" in res.output
    assert "0.1.9" not in res.output

    res = runner.invoke(cli.app, ["changelog", "--since", "0.1.3"])
    assert "0.1.10" in res.output and "0.1.9" in res.output and "0.1.3]" not in res.output

    res = runner.invoke(cli.app, ["changelog", "0.2.0"])
    assert res.exit_code == 1
