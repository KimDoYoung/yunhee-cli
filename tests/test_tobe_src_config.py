from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from yunhee import config
from yunhee.cli import app
from yunhee.tools.analysis.tobe import resolve as resolve_tobe
from yunhee.tools.page_style import resolve_target_path
from yunhee.tools.trace.tobe import find_layout

runner = CliRunner()


def test_tobe_src_dir_configured(tmp_path: Path):
    tobe_dir = tmp_path / "mock_tobe"
    tobe_dir.mkdir()
    pages_dir = tobe_dir / "frontend" / "src" / "pages" / "sys"
    pages_dir.mkdir(parents=True)
    sample_file = pages_dir / "Sys99_Tab_Mock.tsx"
    sample_file.write_text("export default function Sys99_Tab_Mock() { return <div>mock</div>; }", encoding="utf-8")

    with patch.object(config, "TOBE_SRC_DIR", tobe_dir):
        # 1. find_layout() without args picks up TOBE_SRC_DIR
        layout = find_layout()
        assert layout.root == tobe_dir
        assert layout.pages_dir == tobe_dir / "frontend" / "src" / "pages"
        assert layout.usable is True

        # 2. resolve_target_path in page_style resolves from TOBE_SRC_DIR
        resolved = resolve_target_path("Sys99_Tab_Mock.tsx")
        assert resolved == sample_file.resolve()

        # 3. analysis tobe resolves relative path from TOBE_SRC_DIR
        summary = resolve_tobe("frontend/src/pages/sys/Sys99_Tab_Mock.tsx", {})
        assert len(summary["files"]) == 1
        assert summary["files"][0]["file"] == str(sample_file)

        # 4. cli value tobe-src
        res = runner.invoke(app, ["value", "tobe-src"])
        assert res.exit_code == 0
        assert str(tobe_dir) in res.stdout


def test_tobe_src_dir_default_work_dir():
    # When TOBE_SRC_DIR equals WORK_DIR, find_layout defaults to WORK_DIR
    with patch.object(config, "TOBE_SRC_DIR", config.WORK_DIR):
        layout = find_layout()
        assert layout.root == config.WORK_DIR
