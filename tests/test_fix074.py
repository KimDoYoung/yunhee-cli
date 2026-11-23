"""수정사항 074 검증 테스트 suite.

drift의 '판단 끝난 공유 변경' 제외 로직 보완:
1. 판단 시점(AS-IS 커밋 / 처리일 / __units__ blob·commit) 이후 새 커밋이 있으면 제외하지 않는다.
2. 파일 전체가 아니라 실제로 바뀐 단위(메서드·SQL ID) 기준으로 제외 판정한다.
3. 단위 키에 클래스를 붙이고 공용 컴포넌트(shared_links) 호출을 전파하며, 모르면 보고한다.
4. -o json에 excluded_done_shared를 싣고 --show-excluded 옵션을 제공한다.
5. --done-only 끝에 기준선 뒤 미연결 원본 변경 요약을 표시한다.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.as_is.drift import compute_git_blob_file, run_drift
from yunhee.tools.as_is.drift_ops import build_unit_screens_map, update_drift_done

runner = CliRunner()


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


def _setup_repo_and_project(tmp_path: Path) -> tuple[Path, Path, Path, str]:
    """공용 Apr01_Appr.java + 공용 컴포넌트 Apr01_Edit_ApprDoc + 3개 화면을 갖춘 임시 git repo와 프로젝트를 생성한다."""
    src_root = tmp_path / "src_repo"
    src_root.mkdir()
    _git(src_root, ["init", "-b", "main"])

    apr_rel = "application/src/main/java/myApp/server/apr/Apr01_Appr.java"
    apr_file = src_root / apr_rel
    apr_file.parent.mkdir(parents=True)
    apr_file.write_text(
        "package myApp.server.apr;\n"
        "public class Apr01_Appr {\n"
        "    public void update() {\n"
        "        int a = 1;\n"
        "    }\n"
        "    public void selectByRegEmpId() {\n"
        "        int b = 1;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    sc_rel_card = "application/src/main/java/myApp/client/vi/biz/Biz01_Tab_Card.java"
    (src_root / sc_rel_card).parent.mkdir(parents=True)
    (src_root / sc_rel_card).write_text("public class Biz01_Tab_Card {}\n", encoding="utf-8")

    sc_rel_other = "application/src/main/java/myApp/client/vi/sys/Sys01_Tab_Other.java"
    (src_root / sc_rel_other).parent.mkdir(parents=True)
    (src_root / sc_rel_other).write_text("public class Sys01_Tab_Other {}\n", encoding="utf-8")

    sc_rel_reg = "application/src/main/java/myApp/client/vi/apr/Apr13_Tab_Reg.java"
    (src_root / sc_rel_reg).parent.mkdir(parents=True)
    (src_root / sc_rel_reg).write_text("public class Apr13_Tab_Reg {}\n", encoding="utf-8")

    _git(src_root, ["add", "."])
    _git(src_root, ["commit", "-m", "initial"], date="2026-11-10T10:00:00+0900")
    base_commit = _git(src_root, ["rev-parse", "HEAD"])

    work_dir = tmp_path / "work"
    idx_root = work_dir / "docs" / "as-is" / "src"
    (idx_root / "apr" / "components").mkdir(parents=True)
    (idx_root / "biz" / "screens").mkdir(parents=True)
    (idx_root / "sys" / "screens").mkdir(parents=True)
    (idx_root / "apr" / "screens").mkdir(parents=True)

    # 공용 컴포넌트 Apr01_Edit_ApprDoc -> apr.Apr01_Appr.update 호출
    (idx_root / "apr" / "components" / "Apr01_Edit_ApprDoc.md").write_text(
        f"---\nsource_commit: {base_commit}\nsource_files:\n  {apr_rel}: {compute_git_blob_file(apr_file)}\n---\n"
        "# Apr01_Edit_ApprDoc\n"
        "| `apr.Apr01_Appr.update` | Apr01_Edit_ApprDoc:50 | [`Apr01_Appr.java:3`](../../apr/services/Apr01_Appr.md) | [`apr01_appr.update`](../../apr/sql/apr01_appr.md) |\n",
        encoding="utf-8",
    )

    # Biz01_Tab_Card (#1131): shared_links로 Apr01_Edit_ApprDoc 참조
    (idx_root / "biz" / "screens" / "Biz01_Tab_Card.md").write_text(
        f"---\nsource_commit: {base_commit}\nsource_files:\n"
        f"  {sc_rel_card}: {compute_git_blob_file(src_root / sc_rel_card)}\n"
        f"  {apr_rel}: {compute_git_blob_file(apr_file)}\n"
        "shared_links:\n  - Apr01_Edit_ApprDoc\n---\n"
        "# Biz01_Tab_Card (#1131)\n"
        "| `biz.Biz01_Card.selectList` | Biz01:10 | [`Biz01_Card.java:10`](x.md) | [`biz01_card.selectList`](y.md) |\n",
        encoding="utf-8",
    )

    # Sys01_Tab_Other (#1200): 다른 클래스의 update()만 호출하고 Apr01_Appr.update는 안 씀
    (idx_root / "sys" / "screens" / "Sys01_Tab_Other.md").write_text(
        f"---\nsource_commit: {base_commit}\nsource_files:\n"
        f"  {sc_rel_other}: {compute_git_blob_file(src_root / sc_rel_other)}\n"
        f"  {apr_rel}: {compute_git_blob_file(apr_file)}\n---\n"
        "# Sys01_Tab_Other (#1200)\n"
        "| `sys.Sys01_Other.update` | Sys01:10 | [`Sys01_Other.java:10`](x.md) | [`sys01_other.update`](y.md) |\n",
        encoding="utf-8",
    )

    # Apr13_Tab_Reg (#1300): Apr01_Appr.selectByRegEmpId 호출
    (idx_root / "apr" / "screens" / "Apr13_Tab_Reg.md").write_text(
        f"---\nsource_commit: {base_commit}\nsource_files:\n"
        f"  {sc_rel_reg}: {compute_git_blob_file(src_root / sc_rel_reg)}\n"
        f"  {apr_rel}: {compute_git_blob_file(apr_file)}\n---\n"
        "# Apr13_Tab_Reg (#1300)\n"
        "| `apr.Apr01_Appr.selectByRegEmpId` | Apr13:10 | [`Apr01_Appr.java:6`](x.md) | [`apr01_appr.selectByRegEmpId`](y.md) |\n",
        encoding="utf-8",
    )

    apr_blob = compute_git_blob_file(apr_file)
    (idx_root / "_source.json").write_text(
        json.dumps({"vcs": "git", "commit": base_commit, "commit_short": base_commit[:7], "src_root": str(src_root)}),
        encoding="utf-8",
    )
    (idx_root / "_files.json").write_text(
        json.dumps({
            apr_rel: ["Biz01_Tab_Card", "Sys01_Tab_Other", "Apr13_Tab_Reg"],
            sc_rel_card: ["Biz01_Tab_Card"],
            sc_rel_other: ["Sys01_Tab_Other"],
            sc_rel_reg: ["Apr13_Tab_Reg"],
        }),
        encoding="utf-8",
    )

    bl_path = work_dir / ".yunhee" / "baseline.json"
    bl_path.parent.mkdir(parents=True)
    bl_path.write_text(
        json.dumps({
            "Biz01_Tab_Card": {
                "commit": base_commit,
                "files": {sc_rel_card: compute_git_blob_file(src_root / sc_rel_card), apr_rel: apr_blob},
                "shared_links": ["Apr01_Edit_ApprDoc"],
            },
            "Sys01_Tab_Other": {
                "commit": base_commit,
                "files": {sc_rel_other: compute_git_blob_file(src_root / sc_rel_other), apr_rel: apr_blob},
            },
            "Apr13_Tab_Reg": {
                "commit": base_commit,
                "files": {sc_rel_reg: compute_git_blob_file(src_root / sc_rel_reg), apr_rel: apr_blob},
            },
        }),
        encoding="utf-8",
    )

    return src_root, work_dir, idx_root, base_commit


def _write_ledger(work_dir: Path, rows: list[str]) -> Path:
    ledger = work_dir / "docs" / "3-변경반영" / "변경반영-대장.md"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    header = [
        "# 변경반영 대장",
        "",
        "| 키 | 발견일 | AS-IS 커밋 | 종류 | 단위 | 변경 요약 | 영향 화면 | TOBE 대응 | 확인 | 상태 | 처리일 | 비고 |",
        "|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|:---|",
    ]
    ledger.write_text("\n".join(header + rows) + "\n", encoding="utf-8")
    return ledger


def test_074_new_commit_after_ledger_commit_is_not_excluded(tmp_path: Path):
    """#1: 대장 처리 커밋 이후 같은 파일에 새 커밋이 있으면 판단 끝난 단위로 제외하지 않는다."""
    src_root, work_dir, idx_root, _base = _setup_repo_and_project(tmp_path)
    apr_rel = "application/src/main/java/myApp/server/apr/Apr01_Appr.java"

    # 1차 변경 (11-11): selectByRegEmpId 수정 -> 대장에 넘김 기록
    (src_root / apr_rel).write_text(
        "package myApp.server.apr;\n"
        "public class Apr01_Appr {\n"
        "    public void update() {\n"
        "        int a = 1;\n"
        "    }\n"
        "    public void selectByRegEmpId() {\n"
        "        int b = 2;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", apr_rel])
    _git(src_root, ["commit", "-m", "first edit"], date="2026-11-11T10:00:00+0900")
    c_first = _git(src_root, ["rev-parse", "--short=9", "HEAD"])

    _write_ledger(work_dir, [
        f"| CH-0249 | 2026-11-12 | `{c_first}` 11-11 first | LOGIC | `server/apr/Apr01_Appr.java` · `selectByRegEmpId` | +1 -1 | #1300 | - | - | 넘김 | 2026-11-12 | - |",
    ])

    # 1차 시점에는 Sys01_Tab_Other는 selectByRegEmpId를 안 쓰므로 제외되어야 함
    code1, out1, _ = run_drift(
        screen_args=["Sys01_Tab_Other"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        work_dir=work_dir,
    )
    assert code1 == 0
    assert "기준 대비 변경 0개" in out1
    assert "판단 끝난 공유 변경 1건 제외" in out1

    # 2차 변경 (11-20): 같은 selectByRegEmpId를 다시 수정!
    (src_root / apr_rel).write_text(
        "package myApp.server.apr;\n"
        "public class Apr01_Appr {\n"
        "    public void update() {\n"
        "        int a = 1;\n"
        "    }\n"
        "    public void selectByRegEmpId() {\n"
        "        int b = 3;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", apr_rel])
    _git(src_root, ["commit", "-m", "second edit"], date="2026-11-20T10:00:00+0900")

    # 판단 커밋(c_first) 이후 새 커밋이 있으므로 이제 제외하면 안 됨!
    code2, out2, _ = run_drift(
        screen_args=["Sys01_Tab_Other"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        work_dir=work_dir,
    )
    assert code2 == 0
    assert "기준 대비 변경 1개" in out2
    assert "판단 끝난 공유 변경" not in out2


def test_074_same_day_commit_treated_as_new_when_no_hash(tmp_path: Path):
    """#1: 대장에 커밋 해시가 없고 처리일만 있으면 같은 날 커밋은 새 커밋으로 간주한다."""
    src_root, work_dir, idx_root, _base = _setup_repo_and_project(tmp_path)
    apr_rel = "application/src/main/java/myApp/server/apr/Apr01_Appr.java"

    (src_root / apr_rel).write_text(
        "package myApp.server.apr;\n"
        "public class Apr01_Appr {\n"
        "    public void update() {\n"
        "        int a = 1;\n"
        "    }\n"
        "    public void selectByRegEmpId() {\n"
        "        int b = 2;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", apr_rel])
    _git(src_root, ["commit", "-m", "same day edit"], date="2026-11-12T15:00:00+0900")

    # 해시 없이 처리일만 2026-11-12 (커밋과 같은 날) -> 새 커밋으로 보아 제외 금지
    _write_ledger(work_dir, [
        "| CH-0300 | 2026-11-12 | (미기재) | LOGIC | `server/apr/Apr01_Appr.java` · `selectByRegEmpId` | +1 -1 | #1300 | - | - | 해당없음 | 2026-11-12 | - |",
    ])
    code1, out1, _ = run_drift(
        screen_args=["Sys01_Tab_Other"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        work_dir=work_dir,
    )
    assert code1 == 0
    assert "기준 대비 변경 1개" in out1

    # 처리일이 커밋보다 나중(2026-11-13)이면 유효하게 제외
    _write_ledger(work_dir, [
        "| CH-0300 | 2026-11-12 | (미기재) | LOGIC | `server/apr/Apr01_Appr.java` · `selectByRegEmpId` | +1 -1 | #1300 | - | - | 해당없음 | 2026-11-13 | - |",
    ])
    code2, out2, _ = run_drift(
        screen_args=["Sys01_Tab_Other"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        work_dir=work_dir,
    )
    assert code2 == 0
    assert "기준 대비 변경 0개" in out2
    assert "판단 끝난 공유 변경 1건 제외" in out2


def test_074_other_method_changed_in_same_file_is_not_excluded(tmp_path: Path):
    """#2: 파일의 다른 메서드(update)가 바뀌었으면 selectByRegEmpId가 판단 끝났어도 파일을 제외하지 않는다."""
    src_root, work_dir, idx_root, _base = _setup_repo_and_project(tmp_path)
    apr_rel = "application/src/main/java/myApp/server/apr/Apr01_Appr.java"

    # update()를 수정 (selectByRegEmpId가 아님!)
    (src_root / apr_rel).write_text(
        "package myApp.server.apr;\n"
        "public class Apr01_Appr {\n"
        "    public void update() {\n"
        "        int a = 999;\n"
        "    }\n"
        "    public void selectByRegEmpId() {\n"
        "        int b = 1;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", apr_rel])
    _git(src_root, ["commit", "-m", "edit update"], date="2026-11-20T10:00:00+0900")
    c_head = _git(src_root, ["rev-parse", "--short=9", "HEAD"])

    # 대장에는 selectByRegEmpId만 최신 커밋으로 넘김 기록되어 있음
    _write_ledger(work_dir, [
        f"| CH-0282 | 2026-11-20 | `{c_head}` 11-20 | LOGIC | `server/apr/Apr01_Appr.java` · `selectByRegEmpId` | +1 -1 | #1300 | - | - | 넘김 | 2026-11-20 | - |",
    ])

    # 바뀐 단위는 update()이므로 Sys01_Tab_Other도, Biz01_Tab_Card도 제외하면 안 됨!
    code, out, _ = run_drift(
        screen_args=["Biz01_Tab_Card", "Sys01_Tab_Other"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        work_dir=work_dir,
    )
    assert code == 0
    assert "기준 대비 변경 2개" in out


def test_074_class_qualified_unit_and_shared_component_propagation(tmp_path: Path):
    """#3: 공용 컴포넌트(shared_links) 호출을 화면에 전파하고, 클래스 없는 맨 메서드명으로 오판하지 않는다."""
    src_root, work_dir, idx_root, _base = _setup_repo_and_project(tmp_path)
    apr_rel = "application/src/main/java/myApp/server/apr/Apr01_Appr.java"

    # build_unit_screens_map 검증: Apr01_Edit_ApprDoc -> Biz01_Tab_Card(#1131) 전파
    _sql_s, method_s, _file_s = build_unit_screens_map(idx_root)
    assert "#1131" in method_s.get("apr.Apr01_Appr.update", [])
    assert "#1131" in method_s.get("Apr01_Appr.update", [])
    assert "#1200" not in method_s.get("Apr01_Appr.update", [])  # Sys01_Other.update와 섞이지 않음

    # update() 수정 후 대장에 Apr01_Appr.java · update 판단 완료 기록
    (src_root / apr_rel).write_text(
        "package myApp.server.apr;\n"
        "public class Apr01_Appr {\n"
        "    public void update() {\n"
        "        int a = 42;\n"
        "    }\n"
        "    public void selectByRegEmpId() {\n"
        "        int b = 1;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    _git(src_root, ["add", apr_rel])
    _git(src_root, ["commit", "-m", "edit update"], date="2026-11-20T10:00:00+0900")
    c_head = _git(src_root, ["rev-parse", "--short=9", "HEAD"])

    _write_ledger(work_dir, [
        f"| CH-0475 | 2026-11-20 | `{c_head}` 11-20 | LOGIC | `server/apr/Apr01_Appr.java` · `update` | +1 -1 | #1131 | - | ok | 반영 | 2026-11-20 | - |",
    ])

    # Biz01_Tab_Card(#1131)는 공용 컴포넌트 Apr01_Edit_ApprDoc을 통해 Apr01_Appr.update를 쓰므로 보고되어야 함!
    # Sys01_Tab_Other(#1200)는 Sys01_Other.update만 쓰고 Apr01_Appr.update는 안 쓰므로 제외되어야 함!
    code, out_json, _ = run_drift(
        screen_args=["Biz01_Tab_Card", "Sys01_Tab_Other"],
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        output_fmt="json",
        work_dir=work_dir,
    )
    assert code == 0
    data = json.loads(out_json)
    by_sc = {d["screen"]: d for d in data}
    assert by_sc["Biz01_Tab_Card"]["status"] == "변경"
    assert by_sc["Biz01_Tab_Card"]["excluded_done_shared"] == []

    assert by_sc["Sys01_Tab_Other"]["status"] == "동일"
    assert len(by_sc["Sys01_Tab_Other"]["excluded_done_shared"]) == 1
    ex = by_sc["Sys01_Tab_Other"]["excluded_done_shared"][0]
    assert ex["path"] == apr_rel
    assert ex["unit"] == "update"
    assert ex["ledger_key"] == "CH-0475"
    assert ex["ledger_commit"] == c_head


def test_074_show_excluded_and_untracked_summary_and_units_blob(tmp_path: Path, monkeypatch):
    """#4, #5 및 drift-done __units__ blob 기록 검증."""
    src_root, work_dir, idx_root, _base = _setup_repo_and_project(tmp_path)
    apr_rel = "application/src/main/java/myApp/server/apr/Apr01_Appr.java"

    # 1) Apr01_Appr.selectByRegEmpId 수정 + 2) 색인에 없는 정적 파일(webapp/ckeditor/config.js) 추가
    (src_root / apr_rel).write_text(
        "package myApp.server.apr;\n"
        "public class Apr01_Appr {\n"
        "    public void update() {\n"
        "        int a = 1;\n"
        "    }\n"
        "    public void selectByRegEmpId() {\n"
        "        int b = 77;\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    static_file = src_root / "application" / "src" / "main" / "webapp" / "ckeditor" / "config.js"
    static_file.parent.mkdir(parents=True)
    static_file.write_text("CKEDITOR.editorConfig = function() {};\n", encoding="utf-8")

    _git(src_root, ["add", "."])
    _git(src_root, ["commit", "-m", "edit reg + static"], date="2026-11-20T10:00:00+0900")
    c_head = _git(src_root, ["rev-parse", "--short=9", "HEAD"])

    _write_ledger(work_dir, [
        f"| CH-0500 | 2026-11-20 | `{c_head}` 11-20 | LOGIC | `server/apr/Apr01_Appr.java` · `selectByRegEmpId` | +1 -1 | #1300 | - | - | 해당없음 | 2026-11-20 | - |",
    ])

    # --done-only --show-excluded 실행
    code, out, _ = run_drift(
        all_screens=True,
        done_only=True,
        src_root=src_root,
        src_index=idx_root,
        base="baseline",
        show_excluded=True,
        work_dir=work_dir,
    )
    assert code == 0
    assert "제외된 판단 끝난 공유 변경" in out
    assert "CH-0500" in out
    assert "기준선 뒤 미연결 원본 변경: 커밋 1건 · 파일 1개" in out
    assert "ckeditor/config.js" in out

    # drift-done 실행 시 __units__에 blob과 commit이 함께 기록되는지 검증
    monkeypatch.setattr("yunhee.config.ASIS_SRC_DIR", src_root)
    rc_done, _msg_done = update_drift_done(
        keys=["CH-0500"],
        status="해당없음",
        work_dir=work_dir,
    )
    assert rc_done == 0
    bl = json.loads((work_dir / ".yunhee" / "baseline.json").read_text(encoding="utf-8"))
    u_entry = bl["__units__"]["server/apr/Apr01_Appr.java · selectByRegEmpId"]
    assert u_entry.get("commit")
    assert u_entry.get("blob") == compute_git_blob_file(src_root / apr_rel)

    # CLI --show-excluded 옵션 연결 확인
    res = runner.invoke(
        app,
        [
            "drift",
            "--all",
            "--done-only",
            "--base",
            "baseline",
            "--src",
            str(src_root),
            "--src-index",
            str(idx_root),
            "--show-excluded",
        ],
    )
    assert res.exit_code == 0
