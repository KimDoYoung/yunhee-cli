from pathlib import Path

from yunhee.tools import legacy_page


def test_find_page_files_matches_prefix_case_insensitive(tmp_path, monkeypatch):
    monkeypatch.setattr(legacy_page, "ASIS_SRC_DIR", tmp_path)

    module_dir = tmp_path / "client" / "vi" / "ast"
    module_dir.mkdir(parents=True)
    (module_dir / "Ast01_Tab_InfoManagement.java").write_text("class Ast01Tab {}")

    mapper_dir = tmp_path / "server" / "ast" / "mapper"
    mapper_dir.mkdir(parents=True)
    (mapper_dir / "ast01_class_tree.xml").write_text("<mapper/>")

    other_dir = tmp_path / "client" / "vi" / "act"
    other_dir.mkdir(parents=True)
    (other_dir / "Act01_Something.java").write_text("class Act01 {}")

    result = legacy_page.find_page_files("ast01")

    assert result.ok
    paths = {f["path"] for f in result.data}
    assert paths == {
        str(Path("client/vi/ast/Ast01_Tab_InfoManagement.java")),
        str(Path("server/ast/mapper/ast01_class_tree.xml")),
    }
    assert result.truncated is False


def test_find_page_files_excludes_target_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(legacy_page, "ASIS_SRC_DIR", tmp_path)

    target_dir = tmp_path / "application" / "target" / "classes"
    target_dir.mkdir(parents=True)
    (target_dir / "Ast01_Tab_InfoManagement.java").write_text("class Ast01Tab {}")

    result = legacy_page.find_page_files("ast01")

    assert not result.ok
    assert "찾지 못했습니다" in result.error


def test_find_page_files_truncates_large_content(tmp_path, monkeypatch):
    monkeypatch.setattr(legacy_page, "ASIS_SRC_DIR", tmp_path)
    monkeypatch.setattr(legacy_page, "PER_FILE_CHAR_LIMIT", 100)
    monkeypatch.setattr(legacy_page, "TOTAL_CHAR_LIMIT", 100)

    (tmp_path / "Ast01_Big.java").write_text("x" * 5000)

    result = legacy_page.find_page_files("ast01")

    assert result.ok
    assert result.truncated is True
    assert len(result.data[0]["content"]) == 100


def test_find_page_files_missing_src_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(legacy_page, "ASIS_SRC_DIR", tmp_path / "does-not-exist")

    result = legacy_page.find_page_files("ast01")

    assert not result.ok
    assert "찾을 수 없습니다" in result.error
