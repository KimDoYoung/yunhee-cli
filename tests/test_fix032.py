from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from yunhee import cli

runner = CliRunner()


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    return proc.stdout.strip()


def _create_sample_asis_repo(repo: Path, with_git: bool = True) -> Path:
    """테스트용 소형 GXT AS-IS 프로젝트 구조를 생성한다."""
    pkg = repo / "src" / "main" / "java" / "my" / "app"
    (pkg / "client" / "vi").mkdir(parents=True, exist_ok=True)
    (pkg / "client" / "vi" / "sys").mkdir(parents=True, exist_ok=True)
    (pkg / "client" / "vi" / "sys" / "model").mkdir(parents=True, exist_ok=True)
    (pkg / "client" / "vi" / "emp").mkdir(parents=True, exist_ok=True)
    (pkg / "server" / "sys").mkdir(parents=True, exist_ok=True)
    (pkg / "server" / "sys" / "mapper").mkdir(parents=True, exist_ok=True)

    # MenuOpener.java
    (pkg / "client" / "vi" / "MenuOpener.java").write_text(
        """package my.app.client.vi;
public class MenuOpener {
    public Object openTab(String className) {
        if ("Sys27_Tab_LoginManage".equals(className)) { return new Sys27_Tab_LoginManage(); }
        if ("Sys01_Tab_Company".equals(className)) { return new Sys01_Tab_Company(); }
        return null;
    }
}
""",
        encoding="utf-8",
    )

    # menus.tsv
    menus_dir = repo / "docs" / "as-is"
    menus_dir.mkdir(parents=True, exist_ok=True)
    (menus_dir / "menus.tsv").write_text(
        "1\t시스템 > 로그인관리\tSys27_Tab_LoginManage\ttrue\n2\t시스템 > 회사관리\tSys01_Tab_Company\ttrue\n",
        encoding="utf-8",
    )

    # Client model
    (pkg / "client" / "vi" / "sys" / "model" / "Sys27_LoginManageModel.java").write_text(
        """package my.app.client.vi.sys.model;
public class Sys27_LoginManageModel {
    private Long loginId;
}
""",
        encoding="utf-8",
    )

    # Shared lookup component
    (pkg / "client" / "vi" / "emp" / "Emp00_Lookup_SelectSingle.java").write_text(
        """package my.app.client.vi.emp;
public class Emp00_Lookup_SelectSingle {
    public void show() {}
}
""",
        encoding="utf-8",
    )

    # Screen 1: Sys27_Tab_LoginManage
    (pkg / "client" / "vi" / "sys" / "Sys27_Tab_LoginManage.java").write_text(
        """package my.app.client.vi.sys;
import my.app.client.vi.sys.model.Sys27_LoginManageModel;
import my.app.client.vi.emp.Emp00_Lookup_SelectSingle;
public class Sys27_Tab_LoginManage {
    private Sys27_LoginManageModel model;
    public void retrieve() {
        Emp00_Lookup_SelectSingle popup = new Emp00_Lookup_SelectSingle();
        popup.show();
        ServiceRequest request = new ServiceRequest("sys.Sys27_LoginManage.selectByList");
        ServiceRequest commonReq = new ServiceRequest("sys.Sys00_Common.selectCode");
    }
}
""",
        encoding="utf-8",
    )

    # Screen 2: Sys01_Tab_Company
    (pkg / "client" / "vi" / "sys" / "Sys01_Tab_Company.java").write_text(
        """package my.app.client.vi.sys;
public class Sys01_Tab_Company {
    public void retrieve() {
        ServiceRequest commonReq = new ServiceRequest("sys.Sys00_Common.selectCode");
    }
}
""",
        encoding="utf-8",
    )

    # Server classes
    (pkg / "server" / "sys" / "Sys27_LoginManage.java").write_text(
        """package my.app.server.sys;
public class Sys27_LoginManage {
    String mapperName = "sys27_login_manage";
    public void selectByList(SqlSession sqlSession, ServiceRequest request, ServiceResult result) {
        sqlSession.selectList(mapperName + ".selectByList");
        sqlSession.selectList("sys00_common.selectCode");
    }
}
""",
        encoding="utf-8",
    )

    (pkg / "server" / "sys" / "Sys00_Common.java").write_text(
        """package my.app.server.sys;
public class Sys00_Common {
    public void selectCode(SqlSession sqlSession, ServiceRequest request, ServiceResult result) {
        sqlSession.selectList("sys00_common.selectCode");
    }
}
""",
        encoding="utf-8",
    )

    # Mapper XMLs
    (pkg / "server" / "sys" / "mapper" / "sys27_login_manage.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="sys27_login_manage">
    <select id="selectByList" resultType="my.app.client.vi.sys.model.Sys27_LoginManageModel">
        SELECT * FROM sys27_login_manage
    </select>
</mapper>
""",
        encoding="utf-8",
    )

    (pkg / "server" / "sys" / "mapper" / "sys00_common.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
<mapper namespace="sys00_common">
    <select id="selectCode" resultType="map">
        SELECT * FROM sys00_code
    </select>
</mapper>
""",
        encoding="utf-8",
    )

    if with_git:
        _git(repo, "init", "-b", "ioc")
        _git(repo, "config", "user.name", "Tester")
        _git(repo, "config", "user.email", "tester@example.com")
        _git(repo, "add", ".")
        _git(repo, "commit", "-m", "initial commit")

    return repo


def test_032_1_index_src_metadata_and_frontmatter(tmp_path: Path):
    """032-1: index-src 실행 시 _source.json, _files.json, README.md 헤더, 화면 frontmatter, analysis screen --section source 검증."""
    repo = _create_sample_asis_repo(tmp_path / "asis_repo", with_git=True)
    target = tmp_path / "docs" / "as-is" / "src"
    menus = repo / "docs" / "as-is" / "menus.tsv"

    res = runner.invoke(
        cli.app,
        ["index-src", str(repo), "-t", str(target), "--menus", str(menus), "--no-events"],
    )
    assert res.exit_code == 0, res.output
    assert "clean · 화면 2개" in res.output

    # 1. _source.json 확인
    source_json = json.loads((target / "_source.json").read_text(encoding="utf-8"))
    assert source_json["vcs"] == "git"
    assert source_json["branch"] == "ioc"
    assert source_json["dirty"] is False
    assert len(source_json["commit"]) == 40
    assert source_json["commit_short"] == source_json["commit"][:7]
    assert "+09:00" in source_json["commit_time"]
    assert "+09:00" in source_json["indexed_at"]

    # 2. README.md 확인
    readme_text = (target / "README.md").read_text(encoding="utf-8")
    assert f"소스 커밋: {source_json['commit']} (ioc," in readme_text
    assert "색인 생성:" in readme_text
    assert "yunhee 0.3.8" in readme_text

    # 3. 화면 .md frontmatter 확인
    sys27_md = target / "sys" / "screens" / "Sys27_Tab_LoginManage.md"
    assert sys27_md.is_file()
    md_text = sys27_md.read_text(encoding="utf-8")
    assert md_text.startswith("---\n")
    assert f"source_commit: {source_json['commit']}" in md_text
    assert "source_files:" in md_text
    assert "Sys27_Tab_LoginManage.java:" in md_text
    assert "Sys27_LoginManageModel.java:" in md_text
    assert "Sys27_LoginManage.java:" in md_text
    assert "Sys00_Common.java:" in md_text
    assert "sys27_login_manage.xml:" in md_text
    assert "sys00_common.xml:" in md_text
    assert "shared_links:" in md_text
    assert "- Emp00_Lookup_SelectSingle" in md_text

    # 4. _files.json 역색인 확인
    files_json = json.loads((target / "_files.json").read_text(encoding="utf-8"))
    common_entries = [v for k, v in files_json.items() if k.endswith("Sys00_Common.java")]
    assert common_entries and set(common_entries[0]) == {"Sys01_Tab_Company", "Sys27_Tab_LoginManage"}

    # 5. analysis screen 기본 출력에서 frontmatter 미노출 및 --section source 노출 확인
    res_default = runner.invoke(
        cli.app,
        ["analysis", "screen", "Sys27_Tab_LoginManage", "--src-index", str(target), "--src", str(repo)],
    )
    assert res_default.exit_code == 0, res_default.output
    assert "source_commit:" not in res_default.output

    res_source = runner.invoke(
        cli.app,
        [
            "analysis",
            "screen",
            "Sys27_Tab_LoginManage",
            "--section",
            "source",
            "--src-index",
            str(target),
            "--src",
            str(repo),
        ],
    )
    assert res_source.exit_code == 0, res_source.output
    assert f"source_commit {source_json['commit_short']}" in res_source.output
    assert "의존 파일 6개 (client 2 · server 1 · service 1 · mapper 2)" in res_source.output


def test_032_1_non_git_and_dirty_repo(tmp_path: Path):
    """032-1: 비-git 폴더(vcs: none) 및 dirty git 폴더 색인 검증."""
    # 1. 비-git 폴더
    non_git_repo = _create_sample_asis_repo(tmp_path / "non_git_asis", with_git=False)
    target_ng = tmp_path / "index_ng"
    menus_ng = non_git_repo / "docs" / "as-is" / "menus.tsv"

    res_ng = runner.invoke(
        cli.app,
        ["index-src", str(non_git_repo), "-t", str(target_ng), "--menus", str(menus_ng), "--no-events"],
    )
    assert res_ng.exit_code == 0, res_ng.output
    s_ng = json.loads((target_ng / "_source.json").read_text(encoding="utf-8"))
    assert s_ng["vcs"] == "none"
    md_ng = (target_ng / "sys" / "screens" / "Sys27_Tab_LoginManage.md").read_text(encoding="utf-8")
    assert "sha256:" in md_ng

    # 2. dirty git 폴더
    git_repo = _create_sample_asis_repo(tmp_path / "dirty_git_asis", with_git=True)
    java_file = next(git_repo.rglob("Sys27_Tab_LoginManage.java"))
    java_file.write_text(java_file.read_text(encoding="utf-8") + "\n// uncommitted change\n", encoding="utf-8")
    target_dirty = tmp_path / "index_dirty"
    menus_dirty = git_repo / "docs" / "as-is" / "menus.tsv"

    res_dirty = runner.invoke(
        cli.app,
        ["index-src", str(git_repo), "-t", str(target_dirty), "--menus", str(menus_dirty), "--no-events"],
    )
    assert res_dirty.exit_code == 0, res_dirty.output
    assert "미커밋 변경이 색인에 포함됨 — 기준 커밋만으로 재현 불가" in res_dirty.output
    readme_dirty = (target_dirty / "README.md").read_text(encoding="utf-8")
    assert "미커밋 변경이 색인에 포함됨 — 기준 커밋만으로 재현 불가" in readme_dirty
    md_dirty = (target_dirty / "sys" / "screens" / "Sys27_Tab_LoginManage.md").read_text(encoding="utf-8")
    assert "sha256:" in md_dirty


def test_032_2_drift_detection_all_states(tmp_path: Path):
    """032-2: drift 동일, 변경(table/diff/json/fail-on-drift), 삭제, 이동(rename), 공유 파일 전파, --new, 기준 없음 검증."""
    repo = _create_sample_asis_repo(tmp_path / "asis_drift", with_git=True)
    target = tmp_path / "index_drift"
    menus = repo / "docs" / "as-is" / "menus.tsv"

    runner.invoke(cli.app, ["index-src", str(repo), "-t", str(target), "--menus", str(menus), "--no-events"])

    # 1. 색인 직후 변경 0개 확인
    res_clean = runner.invoke(
        cli.app,
        ["drift", "--all", "--src", str(repo), "--src-index", str(target), "--fail-on-drift"],
    )
    assert res_clean.exit_code == 0, res_clean.output
    assert "기준 대비 변경 0개 / 화면 3개 (동일 3 · 기준 없음 0)" in res_clean.output

    # 2. 전용 파일 1줄 수정 후 drift 확인
    sys27_java = next(repo.rglob("Sys27_Tab_LoginManage.java"))
    orig_java = sys27_java.read_text(encoding="utf-8")
    sys27_java.write_text(orig_java.replace("popup.show();", "popup.show(); // modified"), encoding="utf-8")

    res_mod = runner.invoke(
        cli.app,
        ["drift", "Sys27_Tab_LoginManage", "--src", str(repo), "--src-index", str(target)],
    )
    assert res_mod.exit_code == 0, res_mod.output
    assert "변경 1파일 +1/-1" in res_mod.output

    res_fail = runner.invoke(
        cli.app,
        ["drift", "Sys27_Tab_LoginManage", "--src", str(repo), "--src-index", str(target), "--fail-on-drift"],
    )
    assert res_fail.exit_code == 1

    res_diff = runner.invoke(
        cli.app,
        ["drift", "Sys27_Tab_LoginManage", "--src", str(repo), "--src-index", str(target), "-o", "diff"],
    )
    assert res_diff.exit_code == 0
    assert "+        popup.show(); // modified" in res_diff.output

    res_json = runner.invoke(
        cli.app,
        ["drift", "Sys27_Tab_LoginManage", "--src", str(repo), "--src-index", str(target), "-o", "json"],
    )
    assert res_json.exit_code == 0
    payload = json.loads(res_json.output)
    assert payload[0]["screen"] == "Sys27_Tab_LoginManage"
    assert payload[0]["status"] == "변경"
    assert payload[0]["added"] == 1
    assert payload[0]["removed"] == 1

    # 원복
    sys27_java.write_text(orig_java, encoding="utf-8")

    # 3. 파일 이동(rename, 내용 동일) → 변경으로 세지 않고 이동으로만 표시
    moved_dir = sys27_java.parent / "sub"
    moved_dir.mkdir(exist_ok=True)
    moved_java = moved_dir / sys27_java.name
    shutil.move(str(sys27_java), str(moved_java))

    res_move = runner.invoke(
        cli.app,
        ["drift", "--all", "--src", str(repo), "--src-index", str(target), "--fail-on-drift"],
    )
    assert res_move.exit_code == 0, res_move.output
    assert "기준 대비 변경 0개" in res_move.output
    assert "이동 1" in res_move.output
    assert "이동: Sys27_Tab_LoginManage" in res_move.output

    # 다시 원래 위치로 복구 후 파일 삭제 테스트
    shutil.move(str(moved_java), str(sys27_java))
    moved_dir.rmdir()
    model_java = next(repo.rglob("Sys27_LoginManageModel.java"))
    orig_model = model_java.read_text(encoding="utf-8")
    model_java.unlink()

    res_del = runner.invoke(
        cli.app,
        ["drift", "Sys27_Tab_LoginManage", "--src", str(repo), "--src-index", str(target), "-o", "json"],
    )
    del_payload = json.loads(res_del.output)
    assert del_payload[0]["status"] == "삭제"
    model_java.write_text(orig_model, encoding="utf-8")

    # 4. 공통 파일(Sys00_Common.java) 수정 시 두 화면 모두 (공유 1)로 표시 및 하단 공유 변경 요약
    common_java = next(repo.rglob("Sys00_Common.java"))
    orig_common = common_java.read_text(encoding="utf-8")
    common_java.write_text(orig_common + "\n// shared change\n", encoding="utf-8")

    res_shared = runner.invoke(
        cli.app,
        ["drift", "--all", "--src", str(repo), "--src-index", str(target)],
    )
    assert res_shared.exit_code == 0, res_shared.output
    assert "(공유 1)" in res_shared.output
    assert "공유 변경(영향 화면 수): Sys00_Common.java (2)" in res_shared.output
    common_java.write_text(orig_common, encoding="utf-8")

    # 5. --new 옵션으로 신규 화면 탐지
    new_screen = sys27_java.parent / "Sys99_Tab_NewScreen.java"
    new_screen.write_text("package my.app.client.vi.sys;\npublic class Sys99_Tab_NewScreen {}\n", encoding="utf-8")
    res_new = runner.invoke(
        cli.app,
        ["drift", "--all", "--new", "--src", str(repo), "--src-index", str(target)],
    )
    assert res_new.exit_code == 0, res_new.output
    assert "신규: Sys99_Tab_NewScreen" in res_new.output
    new_screen.unlink()

    # 6. 머리말 없는 예전 색인 파일 → 기준 없음으로 표시되고 에러 나지 않음
    sys01_md = target / "sys" / "screens" / "Sys01_Tab_Company.md"
    raw_01 = sys01_md.read_text(encoding="utf-8")
    _, body_01 = raw_01.split("\n---\n", 1)
    sys01_md.write_text(body_01, encoding="utf-8")

    res_nobase = runner.invoke(
        cli.app,
        ["drift", "--all", "--src", str(repo), "--src-index", str(target)],
    )
    assert res_nobase.exit_code == 0, res_nobase.output
    assert "기준 없음 1" in res_nobase.output
    assert "기준 없음 (1개): Sys01_Tab_Company" in res_nobase.output


def test_032_3_baseline_record_and_note_file(tmp_path: Path, monkeypatch):
    """032-3: drift --record, history 누적, --note-file AS-IS 기준 줄 갱신, 오래된 색인 거부, --show-baseline 검증."""
    work_dir = tmp_path / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "WORK_DIR", work_dir)

    repo = _create_sample_asis_repo(tmp_path / "asis_base", with_git=True)
    target = work_dir / "docs" / "as-is" / "src"
    menus = repo / "docs" / "as-is" / "menus.tsv"

    runner.invoke(cli.app, ["index-src", str(repo), "-t", str(target), "--menus", str(menus), "--no-events"])

    note_file = work_dir / "notes" / "A21.md"
    note_file.parent.mkdir(parents=True, exist_ok=True)
    note_file.write_text("# A21 로그인관리 변환\n\n본문 내용\n", encoding="utf-8")

    # 1. --record 실행
    res_rec = runner.invoke(
        cli.app,
        [
            "drift",
            "--record",
            "Sys27_Tab_LoginManage",
            "--id",
            "A21",
            "--note-file",
            str(note_file),
            "--src",
            str(repo),
            "--src-index",
            str(target),
        ],
    )
    assert res_rec.exit_code == 0, res_rec.output
    assert "baseline 기록: Sys27_Tab_LoginManage @" in res_rec.output
    assert "작업기록 머리에 'AS-IS 기준:' 줄 추가" in res_rec.output

    baseline_path = work_dir / ".yunhee" / "baseline.json"
    assert baseline_path.is_file()
    bl_data = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert "Sys27_Tab_LoginManage" in bl_data
    assert bl_data["Sys27_Tab_LoginManage"]["history"] == []

    note_text_1 = note_file.read_text(encoding="utf-8")
    assert note_text_1.count("AS-IS 기준:") == 1

    # 2. 새 커밋 후 재색인 없이 --record 실행 시 거부(종료코드 2) 확인
    sys27_java = next(repo.rglob("Sys27_Tab_LoginManage.java"))
    sys27_java.write_text(sys27_java.read_text(encoding="utf-8") + "\n// commit 2\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "second commit")

    res_stale = runner.invoke(
        cli.app,
        ["drift", "--record", "Sys27_Tab_LoginManage", "--src", str(repo), "--src-index", str(target)],
    )
    assert res_stale.exit_code == 2
    assert "색인이 오래됨" in res_stale.output

    # 3. drift --all --base baseline --done-only 실행 시 완성 화면(Sys27) 1개만 검사하고 변경 감지
    res_done_drift = runner.invoke(
        cli.app,
        ["drift", "--all", "--base", "baseline", "--done-only", "--src", str(repo), "--src-index", str(target)],
    )
    assert res_done_drift.exit_code == 0, res_done_drift.output
    assert "기준 대비 변경 1개 / 완료 화면 1개" in res_done_drift.output

    # 4. 재색인 후 다시 --record 실행 시 history에 이전 기록 보관 및 note_file 중복 없이 갱신
    runner.invoke(cli.app, ["index-src", str(repo), "-t", str(target), "--menus", str(menus), "--no-events"])
    res_rec2 = runner.invoke(
        cli.app,
        [
            "drift",
            "--record",
            "Sys27_Tab_LoginManage",
            "--note-file",
            str(note_file),
            "--src",
            str(repo),
            "--src-index",
            str(target),
        ],
    )
    assert res_rec2.exit_code == 0, res_rec2.output
    bl_data2 = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert len(bl_data2["Sys27_Tab_LoginManage"]["history"]) == 1
    note_text_2 = note_file.read_text(encoding="utf-8")
    assert note_text_2.count("AS-IS 기준:") == 1

    # 5. --show-baseline 확인
    res_show = runner.invoke(cli.app, ["drift", "Sys27_Tab_LoginManage", "--show-baseline"])
    assert res_show.exit_code == 0, res_show.output
    assert "Sys27_Tab_LoginManage @" in res_show.output
    assert "history (1건):" in res_show.output


def test_032_4_prev_index_preservation(tmp_path: Path):
    """032-4: index-src 재실행 시 _prev 보존, 완료 요약 1줄 출력, drift --base prev-index 검증."""
    repo = _create_sample_asis_repo(tmp_path / "asis_prev", with_git=True)
    target = tmp_path / "index_prev"
    menus = repo / "docs" / "as-is" / "menus.tsv"

    # 1차 색인
    runner.invoke(cli.app, ["index-src", str(repo), "-t", str(target), "--menus", str(menus), "--no-events"])
    first_source = json.loads((target / "_source.json").read_text(encoding="utf-8"))

    # 소스 수정 후 커밋
    sys27_java = next(repo.rglob("Sys27_Tab_LoginManage.java"))
    sys27_java.write_text(sys27_java.read_text(encoding="utf-8") + "\n// change for prev-index\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "update sys27")

    # 2차 색인
    res2 = runner.invoke(cli.app, ["index-src", str(repo), "-t", str(target), "--menus", str(menus), "--no-events"])
    assert res2.exit_code == 0, res2.output
    assert "지난 색인 대비 변경 화면 1개, 신규 0개, 삭제 0개" in res2.output
    assert first_source["commit_short"] in res2.output
    assert (target / "_prev" / "_source.json").is_file()
    assert (target / "_prev" / "_screens.json").is_file()

    # drift --base prev-index
    res_prev_drift = runner.invoke(
        cli.app,
        ["drift", "--all", "--base", "prev-index", "--src", str(repo), "--src-index", str(target)],
    )
    assert res_prev_drift.exit_code == 0, res_prev_drift.output
    assert "기준 대비 변경 1개 / 화면 3개" in res_prev_drift.output
    assert "Sys27_Tab_LoginManage" in res_prev_drift.output


def test_032_5_multi_pc_commit_mismatch_warnings(tmp_path: Path, monkeypatch):
    """032-5: 소스 HEAD != 색인 commit 불일치 경고 및 baseline 커밋 이력 부재 시 경고+해시 비교 대체 검증."""
    work_dir = tmp_path / "work5"
    work_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "WORK_DIR", work_dir)

    repo = _create_sample_asis_repo(tmp_path / "asis_pc", with_git=True)
    target = work_dir / "docs" / "as-is" / "src"
    menus = repo / "docs" / "as-is" / "menus.tsv"

    # 커밋 1에서 색인
    runner.invoke(cli.app, ["index-src", str(repo), "-t", str(target), "--menus", str(menus), "--no-events"])

    # 커밋 2 생성 후 baseline 기록을 위해 재색인 + record
    sys27_java = next(repo.rglob("Sys27_Tab_LoginManage.java"))
    sys27_java.write_text(sys27_java.read_text(encoding="utf-8") + "\n// pc A commit\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "pc A commit")
    runner.invoke(cli.app, ["index-src", str(repo), "-t", str(target), "--menus", str(menus), "--no-events"])
    runner.invoke(
        cli.app,
        ["drift", "--record", "Sys27_Tab_LoginManage", "--src", str(repo), "--src-index", str(target)],
    )

    # PC B 시뮬레이션: 소스를 이전 커밋(HEAD~1)으로 되돌림 → 색인·baseline 커밋이 현재 HEAD 이력에 없음!
    _git(repo, "reset", "--hard", "HEAD~1")

    res_drift = runner.invoke(
        cli.app,
        ["drift", "Sys27_Tab_LoginManage", "--base", "baseline", "--src", str(repo), "--src-index", str(target)],
    )
    assert res_drift.exit_code == 0, res_drift.output
    assert "소스 HEAD(" in res_drift.output and "색인 기준(" in res_drift.output
    assert "기준 커밋을 소스에서 찾을 수 없음" in res_drift.output


def test_032_6_version_changelog_agent_guide():
    """032-6: 버전 0.3.8, changelog, agent-guide, drift --help 검증."""
    res_ver = runner.invoke(cli.app, ["--version"])
    assert res_ver.exit_code == 0
    assert "0.3.8" in res_ver.output

    res_cl = runner.invoke(cli.app, ["changelog"])
    assert res_cl.exit_code == 0
    assert "## [0.3.8]" in res_cl.output
    assert "yunhee drift" in res_cl.output
    assert "yunhee drift --record" in res_cl.output

    res_ag = runner.invoke(cli.app, ["agent-guide"])
    assert res_ag.exit_code == 0
    assert "drift --record" in res_ag.output
    assert "--section source" in res_ag.output

    res_help = runner.invoke(cli.app, ["drift", "--help"])
    assert res_help.exit_code == 0
    assert "--record" in res_help.output
    assert "--fail-on-drift" in res_help.output
