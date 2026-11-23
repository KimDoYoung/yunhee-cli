"""수정사항 075 검증 테스트 suite.

- A: 대장과 같은 폴더의 보관/*.md도 읽어 판단 끝난 공유 변경 단위를 수집한다.
- B: import·package·빈 줄·주석만 있는 hunk는 단위 판정에서 뺀다(단, hunk가 모두 neutral이면 안전하게 보고).
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from yunhee.tools.as_is.drift import _is_neutral_hunk, compute_git_blob_file, run_drift


def _git(repo: Path, args: list[str], date: str | None = None) -> str:
    env = os.environ.copy()
    env.setdefault("GIT_AUTHOR_NAME", "tester")
    env.setdefault("GIT_AUTHOR_EMAIL", "tester@example.com")
    env.setdefault("GIT_COMMITTER_NAME", "tester")
    env.setdefault("GIT_COMMITTER_EMAIL", "tester@example.com")
    if date:
        env["GIT_AUTHOR_DATE"] = date
        env["GIT_COMMITTER_DATE"] = date
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )
    return proc.stdout.strip()


def _setup_fixture(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    """공유 파일 X.java + 화면 S(foo 안 씀) + 화면 T(foo 씀)을 갖춘 임시 git repo 및 색인 생성."""
    src_root = tmp_path / "src_repo"
    src_root.mkdir()
    _git(src_root, ["init", "-b", "main"])

    x_rel = "application/src/main/java/myApp/server/foo/X.java"
    x_file = src_root / x_rel
    x_file.parent.mkdir(parents=True)
    x_file.write_text(
        "package myApp.server.foo;\n"
        "\n"
        "import java.util.List;\n"
        "\n"
        "public class X {\n"
        "    private int a = 1;\n"
        "\n"
        "    public void foo() {\n"
        "        int x = 1;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    s_rel = "application/src/main/java/myApp/client/vi/foo/ScreenS.java"
    (src_root / s_rel).parent.mkdir(parents=True)
    (src_root / s_rel).write_text("public class ScreenS {}\n", encoding="utf-8")

    t_rel = "application/src/main/java/myApp/client/vi/foo/ScreenT.java"
    (src_root / t_rel).write_text("public class ScreenT {}\n", encoding="utf-8")

    _git(src_root, ["add", "."])
    _git(src_root, ["commit", "-m", "initial"], date="2026-11-10T10:00:00+0900")
    base_commit = _git(src_root, ["rev-parse", "HEAD"])

    work_dir = tmp_path / "work"
    idx_root = work_dir / "docs" / "as-is" / "src"
    (idx_root / "foo" / "screens").mkdir(parents=True)

    x_blob = compute_git_blob_file(x_file)
    s_blob = compute_git_blob_file(src_root / s_rel)
    t_blob = compute_git_blob_file(src_root / t_rel)

    # ScreenS (#1001): X.java를 의존 파일로 갖지만 foo()는 안 씀
    (idx_root / "foo" / "screens" / "ScreenS.md").write_text(
        f"---\nsource_commit: {base_commit}\nsource_files:\n  {s_rel}: {s_blob}\n  {x_rel}: {x_blob}\n---\n"
        "# ScreenS (#1001)\n"
        "| `foo.Other.bar` | ScreenS:10 | [`Other.java:1`](x.md) | [`other.bar`](y.md) |\n",
        encoding="utf-8",
    )
    # ScreenT (#1002): foo.X.foo를 씀
    (idx_root / "foo" / "screens" / "ScreenT.md").write_text(
        f"---\nsource_commit: {base_commit}\nsource_files:\n  {t_rel}: {t_blob}\n  {x_rel}: {x_blob}\n---\n"
        "# ScreenT (#1002)\n"
        "| `foo.X.foo` | ScreenT:10 | [`X.java:8`](x.md) | [`x.foo`](y.md) |\n",
        encoding="utf-8",
    )

    (idx_root / "_source.json").write_text(
        json.dumps({"vcs": "git", "commit": base_commit, "commit_short": base_commit[:7], "src_root": str(src_root)}),
        encoding="utf-8",
    )
    (idx_root / "_files.json").write_text(
        json.dumps({
            x_rel: ["ScreenS", "ScreenT"],
            s_rel: ["ScreenS"],
            t_rel: ["ScreenT"],
        }),
        encoding="utf-8",
    )

    bl_path = work_dir / ".yunhee" / "baseline.json"
    bl_path.parent.mkdir(parents=True)
    bl_path.write_text(
        json.dumps({
            "ScreenS": {"commit": base_commit, "files": {s_rel: s_blob, x_rel: x_blob}},
            "ScreenT": {"commit": base_commit, "files": {t_rel: t_blob, x_rel: x_blob}},
        }),
        encoding="utf-8",
    )

    return src_root, work_dir, idx_root, x_rel


def _write_table(path: Path, rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# 변경반영 대장",
        "",
        "| 키 | 발견일 | AS-IS 커밋 | 종류 | 단위 | 변경 요약 | 영향 화면 | TOBE 대응 | 확인 | 상태 | 처리일 | 비고 |",
        "|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|",
    ]
    path.write_text("\n".join(header + rows) + "\n", encoding="utf-8")


def test_075_archive_ledger_is_read(tmp_path: Path):
    """보관/2026-11.md에만 있는 판단 줄도 읽어 제외 처리한다."""
    src_root, work_dir, idx_root, x_rel = _setup_fixture(tmp_path)

    (src_root / x_rel).write_text(
        "package myApp.server.foo;\n"
        "\n"
        "import java.util.List;\n"
        "\n"
        "public class X {\n"
        "    private int a = 1;\n"
        "\n"
        "    public void foo() {\n"
        "        int x = 2;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", x_rel])
    _git(src_root, ["commit", "-m", "edit foo"], date="2026-11-20T10:00:00+0900")
    c_hash = _git(src_root, ["rev-parse", "--short=9", "HEAD"])

    # 대장에는 머리줄만, 보관/2026-11.md에만 판단 줄 배치
    _write_table(work_dir / "docs" / "3-변경반영" / "변경반영-대장.md", [])
    _write_table(
        work_dir / "docs" / "3-변경반영" / "보관" / "2026-11.md",
        [
            f"| CH-0901 | 2026-11-20 | `{c_hash}` 11-20 edit foo | LOGIC | `X.java` · `foo` | +1 -1 | #1002 | - | - | 해당없음 | 2026-11-20 | - |",
        ],
    )

    code, out_json, _ = run_drift(
        screen_args=["ScreenS"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        output_fmt="json",
        work_dir=work_dir,
    )
    assert code == 0
    data = json.loads(out_json)
    assert len(data) == 1
    assert data[0]["files"] == []
    assert any(ex["unit"] == "foo" and ex["ledger_key"] == "CH-0901" for ex in data[0]["excluded_done_shared"])


def test_075_archive_missing_is_ok(tmp_path: Path):
    """보관/ 폴더가 없어도 오류 없이 정상 동작한다."""
    src_root, work_dir, idx_root, x_rel = _setup_fixture(tmp_path)

    (src_root / x_rel).write_text(
        "package myApp.server.foo;\n"
        "\n"
        "import java.util.List;\n"
        "\n"
        "public class X {\n"
        "    private int a = 1;\n"
        "\n"
        "    public void foo() {\n"
        "        int x = 2;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", x_rel])
    _git(src_root, ["commit", "-m", "edit foo"], date="2026-11-20T10:00:00+0900")
    c_hash = _git(src_root, ["rev-parse", "--short=9", "HEAD"])

    _write_table(
        work_dir / "docs" / "3-변경반영" / "변경반영-대장.md",
        [
            f"| CH-0902 | 2026-11-20 | `{c_hash}` 11-20 edit foo | LOGIC | `X.java` · `foo` | +1 -1 | #1002 | - | - | 해당없음 | 2026-11-20 | - |",
        ],
    )
    assert not (work_dir / "docs" / "3-변경반영" / "보관").exists()

    code, out_json, _ = run_drift(
        screen_args=["ScreenS"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        output_fmt="json",
        work_dir=work_dir,
    )
    assert code == 0
    data = json.loads(out_json)
    assert data[0]["files"] == []


def test_075_import_only_hunk_does_not_block(tmp_path: Path):
    """import 1줄 추가 + foo 본문 변경 시 import hunk가 제외를 막지 않는다."""
    src_root, work_dir, idx_root, x_rel = _setup_fixture(tmp_path)

    (src_root / x_rel).write_text(
        "package myApp.server.foo;\n"
        "\n"
        "import java.util.List;\n"
        "import java.util.Map;\n"
        "\n"
        "public class X {\n"
        "    private int a = 1;\n"
        "\n"
        "    public void foo() {\n"
        "        int x = 2;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", x_rel])
    _git(src_root, ["commit", "-m", "import + foo"], date="2026-11-20T10:00:00+0900")
    c_hash = _git(src_root, ["rev-parse", "--short=9", "HEAD"])

    _write_table(
        work_dir / "docs" / "3-변경반영" / "변경반영-대장.md",
        [
            f"| CH-0903 | 2026-11-20 | `{c_hash}` 11-20 | LOGIC | `X.java` · `foo` | +2 -1 | #1002 | - | - | 해당없음 | 2026-11-20 | - |",
        ],
    )

    code, out_json, _ = run_drift(
        screen_args=["ScreenS"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        output_fmt="json",
        work_dir=work_dir,
    )
    assert code == 0
    data = json.loads(out_json)
    assert data[0]["files"] == []
    assert any(ex["unit"] == "foo" for ex in data[0]["excluded_done_shared"])


def test_075_blank_and_comment_hunk_does_not_block(tmp_path: Path):
    """빈 줄과 // 주석 hunk가 메서드 밖이어도 제외를 막지 않는다."""
    src_root, work_dir, idx_root, x_rel = _setup_fixture(tmp_path)

    (src_root / x_rel).write_text(
        "package myApp.server.foo;\n"
        "\n"
        "// 설명 주석\n"
        "\n"
        "import java.util.List;\n"
        "\n"
        "public class X {\n"
        "    private int a = 1;\n"
        "\n"
        "    public void foo() {\n"
        "        int x = 2;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", x_rel])
    _git(src_root, ["commit", "-m", "comment + blank + foo"], date="2026-11-20T10:00:00+0900")
    c_hash = _git(src_root, ["rev-parse", "--short=9", "HEAD"])

    _write_table(
        work_dir / "docs" / "3-변경반영" / "변경반영-대장.md",
        [
            f"| CH-0904 | 2026-11-20 | `{c_hash}` 11-20 | LOGIC | `X.java` · `foo` | +3 -1 | #1002 | - | - | 해당없음 | 2026-11-20 | - |",
        ],
    )

    code, out_json, _ = run_drift(
        screen_args=["ScreenS"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        output_fmt="json",
        work_dir=work_dir,
    )
    assert code == 0
    data = json.loads(out_json)
    assert data[0]["files"] == []
    assert any(ex["unit"] == "foo" for ex in data[0]["excluded_done_shared"])


def test_075_field_change_still_blocks(tmp_path: Path):
    """메서드 밖 필드 변경이 포함되면 제외하지 않고 보고한다."""
    src_root, work_dir, idx_root, x_rel = _setup_fixture(tmp_path)

    (src_root / x_rel).write_text(
        "package myApp.server.foo;\n"
        "\n"
        "import java.util.List;\n"
        "\n"
        "public class X {\n"
        "    private int a = 99;\n"
        "\n"
        "    public void foo() {\n"
        "        int x = 2;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", x_rel])
    _git(src_root, ["commit", "-m", "field + foo"], date="2026-11-20T10:00:00+0900")
    c_hash = _git(src_root, ["rev-parse", "--short=9", "HEAD"])

    _write_table(
        work_dir / "docs" / "3-변경반영" / "변경반영-대장.md",
        [
            f"| CH-0905 | 2026-11-20 | `{c_hash}` 11-20 | LOGIC | `X.java` · `foo` | +2 -2 | #1002 | - | - | 해당없음 | 2026-11-20 | - |",
        ],
    )

    code, out_json, _ = run_drift(
        screen_args=["ScreenS"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        output_fmt="json",
        work_dir=work_dir,
    )
    assert code == 0
    data = json.loads(out_json)
    assert data[0]["status"] == "변경"
    assert len(data[0]["files"]) == 1


def test_075_import_only_file_still_reported(tmp_path: Path):
    """import 1줄만 바뀐 파일(메서드 변경 없음)은 안전하게 보고한다."""
    src_root, work_dir, idx_root, x_rel = _setup_fixture(tmp_path)

    (src_root / x_rel).write_text(
        "package myApp.server.foo;\n"
        "\n"
        "import java.util.List;\n"
        "import java.util.Set;\n"
        "\n"
        "public class X {\n"
        "    private int a = 1;\n"
        "\n"
        "    public void foo() {\n"
        "        int x = 1;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", x_rel])
    _git(src_root, ["commit", "-m", "import only"], date="2026-11-20T10:00:00+0900")
    c_hash = _git(src_root, ["rev-parse", "--short=9", "HEAD"])

    _write_table(
        work_dir / "docs" / "3-변경반영" / "변경반영-대장.md",
        [
            f"| CH-0906 | 2026-11-20 | `{c_hash}` 11-20 | LOGIC | `X.java` · `foo` | +1 -0 | #1002 | - | - | 해당없음 | 2026-11-20 | - |",
        ],
    )

    code, out_json, _ = run_drift(
        screen_args=["ScreenS"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        output_fmt="json",
        work_dir=work_dir,
    )
    assert code == 0
    data = json.loads(out_json)
    assert data[0]["status"] == "변경"
    assert len(data[0]["files"]) == 1


def test_075_is_neutral_hunk():
    """_is_neutral_hunk 단위 검증."""
    assert _is_neutral_hunk({"lines": ["+import a.B;"]}) is True
    assert _is_neutral_hunk({"lines": ["+", "-  "]}) is True
    assert _is_neutral_hunk({"lines": ["+// x"]}) is True
    assert _is_neutral_hunk({"lines": ["+ * x"]}) is True
    assert _is_neutral_hunk({"lines": ["+<!-- x -->"]}) is True
    assert _is_neutral_hunk({"lines": ["+int a;"]}) is False
    assert _is_neutral_hunk({"lines": ["+import a.B;", "+foo();"]}) is False
