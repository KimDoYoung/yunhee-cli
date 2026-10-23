"""
Tests for Screen Scout & Spec Generator (screen_scout.py)
"""

from unittest.mock import MagicMock, patch

from yunhee.agent.tools.screen_scout import (
    build_screen_spec_markdown,
    export_spec_tool,
    find_screen_java_file,
)


def test_find_screen_java_file(tmp_path):
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True)
    java_file = src_dir / "Sys01_Company_Tab.java"
    java_file.write_text("public class Sys01_Company_Tab {}", encoding="utf-8")

    with patch("yunhee.config.ASIS_SRC_DIR", src_dir):
        found = find_screen_java_file("sys01")
        assert found is not None
        assert found.name == "Sys01_Company_Tab.java"


def test_build_screen_spec_markdown(tmp_path):
    with (
        patch("yunhee.config.WORK_DIR", tmp_path),
        patch("yunhee.agent.tools.screen_scout.find_screen_java_file", return_value=None),
        patch("yunhee.tools.page_schema.page_tables") as mock_pt,
    ):
        mock_pt.return_value = MagicMock(ok=True, data="Table sys01_company { comp_id varchar }")
        md_text, spec_path = build_screen_spec_markdown("sys01")

    assert "# 📋 마이그레이션 기술 명세서: sys01" in md_text
    assert "Table sys01_company" in md_text
    assert spec_path.is_file()
    assert spec_path.name == "sys01_spec.md"


def test_export_spec_tool_markdown(tmp_path):
    with (
        patch("yunhee.config.WORK_DIR", tmp_path),
        patch("yunhee.agent.tools.screen_scout.build_screen_spec_markdown") as mock_build,
    ):
        mock_build.return_value = ("# Markdown Spec", tmp_path / "sys01_spec.md")
        res = export_spec_tool("sys01", format="markdown")

    assert "마크다운 명세서 작성 완료" in res


def test_export_spec_tool_pdf(tmp_path):
    with (
        patch("yunhee.config.WORK_DIR", tmp_path),
        patch("yunhee.agent.tools.screen_scout.build_screen_spec_markdown") as mock_build,
        patch("yunhee.agent.tools.ext_gotenberg.convert_markdown_to_pdf", return_value=(True, "✔ PDF 발간 완료")),
    ):
        mock_build.return_value = ("# Markdown Spec", tmp_path / "sys01_spec.md")
        res = export_spec_tool("sys01", format="pdf")

    assert "✔ PDF 발간 완료" in res
