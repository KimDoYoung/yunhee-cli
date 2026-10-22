import pytest

from yunhee import config
from yunhee.agent.tools.core_fs import (
    edit_file,
    find_files,
    grep_search,
    list_files,
    read_file,
    write_file,
)


@pytest.fixture
def temp_workspace(tmp_path, monkeypatch):
    """테스트용 임시 작업 디렉토리 격리."""
    monkeypatch.setattr(config, "WORK_DIR", str(tmp_path))
    return tmp_path


def test_write_and_read_file(temp_workspace):
    res_write = write_file("sample.txt", "line1\nline2\nline3\n")
    assert "success" in res_write

    res_read = read_file("sample.txt", start_line=1, max_lines=2)
    assert "line1" in res_read
    assert "line2" in res_read
    assert "line3" not in res_read


def test_list_files(temp_workspace):
    write_file("file1.txt", "abc")
    write_file("subdir/file2.txt", "def")

    res_list = list_files(".")
    assert "file1.txt" in res_list
    assert "[DIR]" in res_list or "subdir" in res_list


def test_edit_file(temp_workspace):
    write_file("code.py", "def foo():\n    return 1\n")
    res_edit = edit_file("code.py", target="return 1", replacement="return 42")
    assert "success" in res_edit

    updated = read_file("code.py")
    assert "return 42" in updated
    assert "return 1" not in updated


def test_edit_file_target_not_found(temp_workspace):
    write_file("test.txt", "hello world")
    res_edit = edit_file("test.txt", target="goodbye", replacement="bye")
    assert "error" in res_edit


def test_path_traversal_blocked(temp_workspace):
    # 상위 경로 탈출 시도
    res = read_file("../../../etc/passwd")
    assert "error" in res
    assert "외부" in res or "PermissionError" in res or "작업 디렉터리" in res


def test_find_files(temp_workspace):
    write_file("src/main/UserMapper.xml", "<mapper></mapper>")
    write_file("src/main/OrderMapper.xml", "<mapper></mapper>")
    write_file("src/main/UserService.java", "class UserService {}")

    res = find_files("*.xml", directory="src")
    assert "UserMapper.xml" in res
    assert "OrderMapper.xml" in res
    assert "UserService.java" not in res


def test_grep_search(temp_workspace):
    write_file("src/A.java", "public class A {\n    public void selectUser() {}\n}")
    write_file("src/B.java", "public class B {\n    public void deleteUser() {}\n}")

    res = grep_search("selectUser", path="src")
    assert "A.java:2: public void selectUser() {}" in res
    assert "B.java" not in res


def test_grep_search_case_insensitive(temp_workspace):
    write_file("notes.txt", "Important: Database Migration Guide")

    res = grep_search("database", path="notes.txt")
    assert "notes.txt:1: Important: Database Migration Guide" in res


def test_grep_search_not_found(temp_workspace):
    write_file("notes.txt", "Hello World")
    res = grep_search("NonExistentKeyword", path="notes.txt")
    assert "일치하는 내용을 찾을 수 없습니다" in res

