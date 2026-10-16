from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools import sql_runner

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
    pkg = repo / "src" / "main" / "java" / "my" / "app"
    (pkg / "client" / "vi" / "sys" / "model").mkdir(parents=True, exist_ok=True)
    (pkg / "client" / "vi" / "emp").mkdir(parents=True, exist_ok=True)
    (pkg / "server" / "sys" / "mapper").mkdir(parents=True, exist_ok=True)

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

    menus_dir = repo / "docs" / "as-is"
    menus_dir.mkdir(parents=True, exist_ok=True)
    (menus_dir / "menus.tsv").write_text(
        "1\t시스템 > 로그인관리\tSys27_Tab_LoginManage\ttrue\n2\t시스템 > 회사관리\tSys01_Tab_Company\ttrue\n",
        encoding="utf-8",
    )

    (pkg / "client" / "vi" / "sys" / "model" / "Sys27_LoginManageModel.java").write_text(
        "package my.app.client.vi.sys.model;\npublic class Sys27_LoginManageModel { private Long loginId; }\n",
        encoding="utf-8",
    )
    (pkg / "client" / "vi" / "emp" / "Emp00_Lookup_SelectSingle.java").write_text(
        "package my.app.client.vi.emp;\npublic class Emp00_Lookup_SelectSingle { public void show() {} }\n",
        encoding="utf-8",
    )
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
    (pkg / "server" / "sys" / "mapper" / "sys27_login_manage.xml").write_text(
        """<?xml version="1.0" encoding="UTF-8"?>
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



def test_033_1_sql_output_formats_and_out_file(tmp_path: Path):
    """033-1: tsv/csv/json 포맷, NULL/이스케이프, --no-header, --out 원자적 저장·타임아웃 시 파일 없음, 행 수 기본값, | 이스케이프, --rollback -o json, 미지원 형식 Exit 2."""
    # ① tsv 이스케이프(탭·줄바꿈·백슬래시)와 NULL 및 --no-header
    res_tsv = runner.invoke(
        cli.app,
        ["sql", r"SELECT 'a|b' AS x, E'c\td\ne\\f' AS y, NULL AS z", "-o", "tsv"],
    )
    assert res_tsv.exit_code == 0, res_tsv.output
    tsv_lines = res_tsv.output.rstrip("\n").splitlines()
    assert tsv_lines[0] == "x\ty\tz"
    assert tsv_lines[1] == "a|b\tc\\td\\ne\\\\f\t"

    res_tsv_null = runner.invoke(
        cli.app,
        ["sql", "SELECT NULL AS a, 'ok' AS b", "-o", "tsv", "--null", "\\N", "--no-header"],
    )
    assert res_tsv_null.exit_code == 0, res_tsv_null.output
    assert res_tsv_null.output.strip() == "\\N\tok"

    # ② csv 따옴표·쉼표·줄바꿈 (RFC 4180)
    res_csv = runner.invoke(
        cli.app,
        ["sql", "SELECT 'a,b' AS c1, 'q\"w' AS c2, E'line1\\nline2' AS c3", "-o", "csv"],
    )
    assert res_csv.exit_code == 0, res_csv.output
    parsed_csv = list(csv.reader(io.StringIO(res_csv.output)))
    assert parsed_csv[0] == ["c1", "c2", "c3"]
    assert parsed_csv[1] == ["a,b", 'q"w', "line1\nline2"]

    # ③ json 타입(int·bool·null)
    res_json = runner.invoke(
        cli.app,
        ["sql", "SELECT 1 AS n, true AS b, NULL AS v, 3.5::numeric AS d", "-o", "json"],
    )
    assert res_json.exit_code == 0, res_json.output
    data_json = json.loads(res_json.output)
    assert data_json == [{"n": 1, "b": True, "v": None, "d": 3.5}]

    # ④ --out 성공 시 요약 한 줄, 타임아웃이면 파일 없음
    out_tsv = tmp_path / "sub" / "result.tsv"
    res_out = runner.invoke(
        cli.app,
        ["sql", "SELECT generate_series(1, 10) AS id, 'item' AS nm", "-o", "tsv", "--no-header", "--out", str(out_tsv)],
    )
    assert res_out.exit_code == 0, res_out.output
    assert f"rows=10 → {out_tsv}" in res_out.output.strip()
    assert out_tsv.is_file()
    assert len(out_tsv.read_text(encoding="utf-8").splitlines()) == 10

    timeout_out = tmp_path / "sub" / "timeout.tsv"
    res_to = runner.invoke(
        cli.app,
        ["sql", "SELECT pg_sleep(2)", "--timeout", "0.1", "-o", "tsv", "--out", str(timeout_out)],
    )
    assert res_to.exit_code != 0
    assert not timeout_out.exists()

    # ⑤ -n 없을 때 tsv는 전체, table은 5행; -n 지정 시 잘림 경고는 stderr로 분리
    res_tbl_default = runner.invoke(cli.app, ["sql", "SELECT generate_series(1, 12) AS n"])
    assert res_tbl_default.exit_code == 0
    assert "(총 12행 중 5행만 표시)" in res_tbl_default.output

    res_tsv_default = runner.invoke(cli.app, ["sql", "SELECT generate_series(1, 12) AS n", "-o", "tsv", "--no-header"])
    assert res_tsv_default.exit_code == 0
    assert len(res_tsv_default.output.strip().splitlines()) == 12

    res_tsv_limit = sql_runner.run_sql(
        query="SELECT generate_series(1, 12) AS n",
        output_fmt="tsv",
        no_header=True,
        limit=3,
    )
    assert res_tsv_limit.ok
    assert len(res_tsv_limit.data["summary"].splitlines()) == 3
    assert "12행 중 3행만 출력" not in res_tsv_limit.data["summary"]
    assert any("⚠ 12행 중 3행만 출력" in w for w in res_tsv_limit.data["warnings"])

    # ⑥ | 포함 값의 표 이스케이프
    res_pipe = runner.invoke(cli.app, ["sql", "SELECT 'a|b' AS x, 'c' AS y"])
    assert res_pipe.exit_code == 0
    assert r"| a\|b | c |" in res_pipe.output

    # ⑦ --rollback과 -o json 함께 쓰기 (순수 JSON 유지)
    res_rb_json = runner.invoke(
        cli.app,
        ["sql", "SELECT current_setting('transaction_read_only') AS ro, 42 AS v", "--rollback", "-o", "json"],
    )
    assert res_rb_json.exit_code == 0, res_rb_json.output
    rb_parsed = json.loads(res_rb_json.output)
    assert rb_parsed == [{"ro": "off", "v": 42}]

    # ⑧ 지원하지 않는 형식은 Exit 2
    res_bad_fmt = runner.invoke(cli.app, ["sql", "SELECT 1", "-o", "xml"])
    assert res_bad_fmt.exit_code == 2
    assert "지원 형식" in res_bad_fmt.output


def test_033_2_drift_record_from_and_record_all(tmp_path: Path, monkeypatch):
    """033-2: --record-from / --record-all 헤더 이름 탐색, 백틱·링크 제거, 상태 필터, 미존재 건너뜀, --dry-run, 변경 없음, 해시 충돌 시 --force 거부, AS-IS 기준 중복 없음."""
    work_dir = tmp_path / "work_033_2"
    work_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(cli, "WORK_DIR", work_dir)

    repo = _create_sample_asis_repo(tmp_path / "asis_033_2", with_git=True)
    target = work_dir / "docs" / "as-is" / "src"
    menus = repo / "docs" / "as-is" / "menus.tsv"

    runner.invoke(cli.app, ["index-src", str(repo), "-t", str(target), "--menus", str(menus), "--no-events"])

    # A표와 C표의 열 순서가 다르고, 백틱·링크·상태(완료, 확인, 대기, 보류)·없는 클래스 포함
    conv_md = work_dir / "docs" / "01-변환목록.md"
    conv_md.parent.mkdir(parents=True, exist_ok=True)
    conv_md.write_text(
        """# 01 변환 목록

## A. 시스템 화면 (열 순서: ID | 도메인 | 화면명 | 클래스 | 상태)

| ID | 도메인 | 화면명 | 클래스 | 상태 |
|:---|:---|:---|:---|:---|
| A01 | sys | 로그인관리 | [`Sys27_Tab_LoginManage`](docs/as-is/src/sys/screens/Sys27_Tab_LoginManage.md) | 완료 |
| A34 | sys | 대기화면 | `Sys98_Tab_Pending` | 대기 |

## C. 추가 화면 (열 순서: 상태 | 클래스 | 비고 | ID)

| 상태 | 클래스 | 비고 | ID |
|:---|:---|:---|:---|
| 확인 | `Sys01_Tab_Company` | 회사 | C01 |
| 보류 | Sys99_Tab_Hold | 보류건 | A36 |
""",
        encoding="utf-8",
    )

    # ⑤ --dry-run: 파일·baseline을 쓰지 않고 대상 및 상태 필터 건너뜀 표시
    res_dry = runner.invoke(
        cli.app,
        [
            "drift",
            "--record-from",
            str(conv_md),
            "--status",
            "완료,확인",
            "--dry-run",
            "--src",
            str(repo),
            "--src-index",
            str(target),
        ],
    )
    assert res_dry.exit_code == 0, res_dry.output
    assert "대상 2개 · 건너뜀 2개 (A34: 상태 대기, A36: 상태 보류 — 상태 필터)" in res_dry.output
    assert not (work_dir / ".yunhee" / "baseline.json").exists()
    assert not (work_dir / "docs" / "work" / "A01-작업기록.md").exists()

    # 기존 작업기록에 이미 AS-IS 기준 줄이 있는 경우 중복 방지 확인용 파일 생성
    note_a01 = work_dir / "docs" / "work" / "A01-작업기록.md"
    note_a01.parent.mkdir(parents=True, exist_ok=True)
    note_a01.write_text("# A01 작업기록\nAS-IS 기준: 이전값\n\n본문\n", encoding="utf-8")

    # ① ② ③ ⑧ 실제 일괄 기록 실행
    res_rec = runner.invoke(
        cli.app,
        [
            "drift",
            "--record-from",
            str(conv_md),
            "--status",
            "완료,확인",
            "--src",
            str(repo),
            "--src-index",
            str(target),
        ],
    )
    assert res_rec.exit_code == 0, res_rec.output
    assert "기록 2개 · 작업기록 2개 갱신 · 건너뜀 0개" in res_rec.output
    assert (work_dir / ".yunhee" / "baseline.json").is_file()
    assert note_a01.read_text(encoding="utf-8").count("AS-IS 기준:") == 1
    assert (work_dir / "docs" / "work" / "C01-작업기록.md").is_file()

    # ⑥ 다시 실행 시 이미 같은 기준이면 변경 없음
    res_again = runner.invoke(
        cli.app,
        [
            "drift",
            "--record-from",
            str(conv_md),
            "--status",
            "완료,확인",
            "--src",
            str(repo),
            "--src-index",
            str(target),
        ],
    )
    assert res_again.exit_code == 0, res_again.output
    assert res_again.output.strip() == "변경 없음 2개"
    assert note_a01.read_text(encoding="utf-8").count("AS-IS 기준:") == 1

    # ④ 클래스가 색인에 없는 완료 행이 있어도 건너뛰고 나머지는 계속 처리
    conv_md_missing = work_dir / "docs" / "01-변환목록-missing.md"
    conv_md_missing.write_text(
        """| ID | 클래스 | 상태 |
|:---|:---|:---|
| A01 | `Sys27_Tab_LoginManage` | 완료 |
| A99 | `NonExistent_Tab_Screen` | 완료 |
""",
        encoding="utf-8",
    )
    res_missing = runner.invoke(
        cli.app,
        [
            "drift",
            "--record-from",
            str(conv_md_missing),
            "--status",
            "완료",
            "--src",
            str(repo),
            "--src-index",
            str(target),
        ],
    )
    assert res_missing.exit_code == 0, res_missing.output
    assert "변경 없음 1개" in res_missing.output
    assert "건너뜀 1개 (A99(NonExistent_Tab_Screen): 색인에 없음)" in res_missing.output

    # ⑦ 원본이 바뀌어 해시가 달라졌을 때 --force 없이는 덮어쓰지 않고 거부
    sys27_java = next(repo.rglob("Sys27_Tab_LoginManage.java"))
    sys27_java.write_text(sys27_java.read_text(encoding="utf-8") + "\n// changed after baseline\n", encoding="utf-8")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "modify sys27")
    runner.invoke(cli.app, ["index-src", str(repo), "-t", str(target), "--menus", str(menus), "--no-events"])

    res_conflict = runner.invoke(
        cli.app,
        [
            "drift",
            "--record-from",
            str(conv_md),
            "--status",
            "완료,확인",
            "--src",
            str(repo),
            "--src-index",
            str(target),
        ],
    )
    assert res_conflict.exit_code == 2
    assert "기준 변경: 원본이 바뀜 — drift로 먼저 확인" in res_conflict.output

    # .yunhee.toml 설정 + --record-all + --force로 갱신 확인
    (work_dir / ".yunhee.toml").write_text(
        """[drift]
done_from = "docs/01-변환목록.md"
record_status = ["완료", "확인"]
note_dir = "docs/work"
note_suffix = "-작업기록.md"
""",
        encoding="utf-8",
    )
    res_force = runner.invoke(
        cli.app,
        [
            "drift",
            "--record-all",
            "--force",
            "--src",
            str(repo),
            "--src-index",
            str(target),
        ],
    )
    assert res_force.exit_code == 0, res_force.output
    assert "기록 2개 · 작업기록 2개 갱신 · 건너뜀 0개" in res_force.output
    assert note_a01.read_text(encoding="utf-8").count("AS-IS 기준:") == 1


def test_033_3_index_src_and_drift_screen_counts(tmp_path: Path):
    """033-3: index-src 요약, _source.json, drift 머리 줄의 화면 총계 및 (메뉴·프레임) 표기 일치, --menus 없을 때 안내 문구."""
    repo = _create_sample_asis_repo(tmp_path / "asis_033_3", with_git=True)
    target_with_menus = tmp_path / "idx_with_menus"
    menus = repo / "docs" / "as-is" / "menus.tsv"

    # 1. --menus 지정 색인
    res_idx = runner.invoke(
        cli.app,
        ["index-src", str(repo), "-t", str(target_with_menus), "--menus", str(menus), "--no-events"],
    )
    assert res_idx.exit_code == 0, res_idx.output
    assert "화면 3개(메뉴 2 + 프레임 1)" in res_idx.output
    assert "메뉴 화면: 2개, 프레임: 1개" in res_idx.output

    # ③ _source.json 필드 확인
    s_json = json.loads((target_with_menus / "_source.json").read_text(encoding="utf-8"))
    assert s_json["screens_count"] == 3
    assert s_json["screens_menu"] == 2
    assert s_json["screens_frame"] == 1
    assert s_json["has_menus"] is True

    # ① drift 머리 줄과 총계·구성 일치 확인
    res_drift = runner.invoke(
        cli.app,
        ["drift", "--all", "--src", str(repo), "--src-index", str(target_with_menus)],
    )
    assert res_drift.exit_code == 0, res_drift.output
    assert "화면 3개(메뉴 2 · 프레임 1)" in res_drift.output

    # ② --menus 없이 색인했을 때 '메뉴 화면: 연결 안 됨(--menus 없음)' 표시
    target_no_menus = tmp_path / "idx_no_menus" / "src"
    res_no_menus = runner.invoke(
        cli.app,
        ["index-src", str(repo), "-t", str(target_no_menus), "--no-events"],
    )
    assert res_no_menus.exit_code == 0, res_no_menus.output
    assert "화면 3개(메뉴 2 + 프레임 1)" in res_no_menus.output
    assert "메뉴 화면: 연결 안 됨(--menus 없음)" in res_no_menus.output


def test_033_4_builtin_menus_sql(tmp_path: Path):
    """033-4: yunhee sql --builtin menus 4열 TSV 생성, 읽기 전용 강제, 미존재 이름 Exit 2, README 안내 확인."""
    # ① --builtin menus 실행 시 4열 TSV 출력 및 파일 저장
    menus_out = tmp_path / "menus.tsv"
    res_menus = runner.invoke(
        cli.app,
        ["sql", "--builtin", "menus", "-o", "tsv", "--out", str(menus_out), "--no-header"],
    )
    assert res_menus.exit_code == 0, res_menus.output
    assert f"→ {menus_out}" in res_menus.output
    lines = menus_out.read_text(encoding="utf-8").splitlines()
    assert len(lines) > 0
    first_cols = lines[0].split("\t")
    assert len(first_cols) == 4

    # ② 읽기 전용 강제 확인 (쓰기 쿼리는 거부)
    res_ro = runner.invoke(cli.app, ["sql", "DELETE FROM sys06_menu WHERE 1=0", "-o", "tsv"])
    assert res_ro.exit_code != 0
    assert "읽기 전용 모드" in res_ro.output

    # ③ --builtin 이름이 없으면 목록 안내 및 Exit 2
    res_unknown = runner.invoke(cli.app, ["sql", "--builtin", "no_such_sql"])
    assert res_unknown.exit_code == 2
    assert "menus" in res_unknown.output

    # 버전 0.3.9 및 changelog 확인
    res_ver = runner.invoke(cli.app, ["--version"])
    assert "0.3.9" in res_ver.output
    res_cl = runner.invoke(cli.app, ["changelog"])
    assert "## [0.3.9]" in res_cl.output
