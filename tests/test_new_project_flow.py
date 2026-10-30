import os
import tempfile
from pathlib import Path

from typer.testing import CliRunner

from yunhee import config, project
from yunhee.cli import app

runner = CliRunner()


def test_init_in_empty_directory():
    with tempfile.TemporaryDirectory() as td:
        orig = os.getcwd()
        try:
            os.chdir(td)
            # Before init, status should be missing
            assert project.status(Path(td)) == "missing"

            res = runner.invoke(app, ["init"])
            assert res.exit_code == 0
            assert "등록 완료" in res.output

            pdir = Path(td) / ".yunhee"
            assert pdir.is_dir()
            assert (pdir / "project.json").is_file()
            assert (pdir / "mcp.json").is_file()
            assert (pdir / "memory.md").is_file()
            assert (pdir / "sessions").is_dir()
            assert (pdir / "runs").is_dir()
            assert (pdir / ".gitignore").is_file()

            # After init, status should be ok
            assert project.status(Path(td)) == "ok"
        finally:
            os.chdir(orig)


def test_cascading_env_file_loading(tmp_path: Path):
    global_dir = tmp_path / "global_yunhee"
    global_dir.mkdir()
    global_env = global_dir / ".env.yunhee"
    global_env.write_text("YUNHEE_TEST_VAR_A=global_a\nYUNHEE_TEST_VAR_B=global_b\n", encoding="utf-8")

    local_dir = tmp_path / "my_project"
    local_dir.mkdir()
    local_env = local_dir / ".env.yunhee"
    local_env.write_text("YUNHEE_TEST_VAR_B=local_b_override\n", encoding="utf-8")

    # Verify search helpers
    g_found = config._find_global_env_file(global_dir)
    assert g_found == global_env.resolve()

    l_found = config._find_local_env_file(local_dir, global_env=g_found)
    assert l_found == local_env.resolve()
