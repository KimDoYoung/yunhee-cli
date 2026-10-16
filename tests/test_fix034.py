from __future__ import annotations

import json
import shutil
from pathlib import Path

from test_fix032 import _create_sample_asis_repo, _git
from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools.analysis import screen, sql, ui
from yunhee.tools.as_is.drift import collect_source_info

runner = CliRunner()


def _outer_repo_with_plain_copy(tmp_path: Path) -> tuple[Path, Path]:
    """git 저장소 안에 .git 없는 소스 복사본(git archive를 푼 상황)을 만든다."""
    src = _create_sample_asis_repo(tmp_path / "orig", with_git=False)
    outer = tmp_path / "outer"
    outer.mkdir()
    _git(outer, "init", "-b", "main")
    _git(outer, "config", "user.name", "T")
    _git(outer, "config", "user.email", "t@example.com")
    (outer / "README").write_text("x", encoding="utf-8")
    _git(outer, "add", ".")
    _git(outer, "commit", "-m", "outer")
    plain = outer / "bench" / "src"
    shutil.copytree(src, plain)
    return outer, plain


def test_034_1_outer_repo_ignored(tmp_path: Path):
    _outer, plain = _outer_repo_with_plain_copy(tmp_path)
    target = tmp_path / "idx"
    menus = plain / "docs" / "as-is" / "menus.tsv"
    res = runner.invoke(cli.app, ["index-src", str(plain), "-t", str(target), "--menus", str(menus), "--no-events"])
    assert res.exit_code == 0, res.output
    assert "git 저장소의 루트가 아니다" in res.output
    assert "소스 (비-git)" in res.output
    meta = json.loads((target / "_source.json").read_text(encoding="utf-8"))
    assert meta["vcs"] == "none"
    assert meta["commit"] is None


def test_034_1_repo_root_and_vcs_root_and_nested(tmp_path: Path):
    repo = _create_sample_asis_repo(tmp_path / "root_repo", with_git=True)
    assert collect_source_info(repo)["vcs"] == "git"

    outer, plain = _outer_repo_with_plain_copy(tmp_path)
    info = collect_source_info(plain, vcs_root=outer)
    assert info["vcs"] == "git"
    assert info["vcs_root"] == str(outer.resolve())

    # 중첩 저장소: 소스 루트에 자체 .git
    _git(plain, "init", "-b", "inner")
    _git(plain, "config", "user.name", "T")
    _git(plain, "config", "user.email", "t@example.com")
    _git(plain, "add", ".")
    _git(plain, "commit", "-m", "inner")
    nested = collect_source_info(plain)
    assert nested["vcs"] == "git"
    assert nested["branch"] == "inner"


def _screen_fixture(tmp_path: Path) -> Path:
    idx = tmp_path / "index"
    d = idx / "sys" / "screens"
    d.mkdir(parents=True)
    (d / "Scr.md").write_text(
        "# Scr\n\n### Scr_Main (`client/Scr_Main.java`)\n1. <Button>저장</Button>\n[E0] 초기화\n",
        encoding="utf-8",
    )
    return idx


def test_034_2_3_screen_list_columns_and_json(tmp_path: Path):
    idx = _screen_fixture(tmp_path)
    src = tmp_path / "src"
    (src / "client").mkdir(parents=True)
    (src / "client" / "Scr_Main.java").write_text("a\nb\nc\n", encoding="utf-8")
    opts = {"src_index": idx, "src": src}
    obj = screen.resolve("Scr", opts)

    md = screen.render(obj, opts={"list": True})
    assert "줄(원본)" in md and "줄(UI절)" in md

    out = screen.render(obj, fmt="json", opts={"list": True})
    d = json.loads(out)
    assert set(d) == {"screen", "classes", "total"}
    c = d["classes"][0]
    assert {"name", "lines", "lines_src", "buttons", "events", "grids", "linked"} <= set(c)
    assert c["linked"] is False
    assert c["lines_src"] == 3
    assert d["total"]["buttons"] == c["buttons"] == 1


def test_034_3_screen_missing_exit1(tmp_path: Path):
    idx = _screen_fixture(tmp_path)
    res = runner.invoke(
        cli.app, ["analysis", "screen", "Nope", "--list", "-o", "json", "--src-index", str(idx)]
    )
    assert res.exit_code == 1


def test_034_3_ui_json(tmp_path: Path):
    idx = _screen_fixture(tmp_path)
    obj = ui.resolve("Scr", {"src_index": idx})
    d = json.loads(ui.render(obj, fmt="json"))
    assert {"screen", "groups", "total", "classes"} <= set(d)
    assert d["total"]["buttons"] == 1


def test_034_3_sql_json_formats():
    assert "json" in sql.FORMATS
    assert "json" in screen.FORMATS and "json" in ui.FORMATS
