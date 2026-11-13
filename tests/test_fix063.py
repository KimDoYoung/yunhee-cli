"""수정사항 063 검증 테스트 suite.

- grep 옵션 (-c, -n, -r) 및 모르는 옵션 사용법 안내
- drift 줄바꿈(CRLF)만 바뀐 파일 판별 및 --record --force 없이 기준 이동
- drift --done-only 대장 해당없음 공유 변경 단위 제외
"""

import json

from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.as_is.drift import record_baseline, run_drift
from yunhee.tools.outliner import grep_files

runner = CliRunner()


class TestGrep:
    """063 #1: grep 옵션 개선 검증."""

    def test_grep_count_option(self, tmp_path):
        f1 = tmp_path / "sample1.txt"
        f1.write_text("apple\nbanana\napple juice\norange\n", encoding="utf-8")
        f2 = tmp_path / "sample2.txt"
        f2.write_text("grape\nmelon\n", encoding="utf-8")

        res = grep_files(pattern="apple", paths=[f1, f2], count=True)
        assert res.ok
        assert "sample1.txt:2" in res.data
        assert "sample2.txt" not in res.data

        # CLI -c
        result = runner.invoke(app, ["grep", "-c", "apple", str(tmp_path)])
        assert result.exit_code == 0
        assert "sample1.txt:2" in result.output

    def test_grep_noop_options(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello world\n", encoding="utf-8")

        # -n, -r no-op 호환
        result = runner.invoke(app, ["grep", "-n", "-r", "hello", str(f)])
        assert result.exit_code == 0
        assert "test.txt:1: hello world" in result.output

    def test_grep_unknown_option_help(self, tmp_path):
        import re

        result = runner.invoke(app, ["grep", "--unknown-opt", "pattern", str(tmp_path)])
        assert result.exit_code == 2
        clean_out = re.sub(r"\s+", " ", result.output.replace("│", " "))
        assert "사용 가능한 옵션: -l(파일 이름만) -m(파일당 최대 N줄) -C(앞뒤 문맥) -c(건수) · 패턴은 ERE(a|b)" in clean_out


class TestDriftCrlf:
    """063 #2: drift CRLF 판별 및 --record 검증."""

    def test_drift_crlf_treated_as_same_and_records_without_force(self, tmp_path, monkeypatch):
        # mock git repo & drift environment
        src_root = tmp_path / "src"
        src_root.mkdir()
        src_file = src_root / "Main.java"
        src_file.write_text("public class Main {\r\n}\r\n", encoding="utf-8")

        idx_root = tmp_path / "docs" / "as-is" / "src"
        idx_root.mkdir(parents=True)
        idx_file = idx_root / "_index.json"
        idx_file.write_text(
            json.dumps({
                "_meta": {"commit": "c111111", "branch": "main", "repo_name": "repo"},
                "Main": {
                    "kind": "screen",
                    "has_frontmatter": True,
                    "source_commit": "c111111",
                    "source_files": {"Main.java": "blob_crlf"},
                },
            }),
            encoding="utf-8",
        )

        baseline_file = tmp_path / ".yunhee" / "baseline.json"
        baseline_file.parent.mkdir(parents=True)
        baseline_file.write_text(
            json.dumps({
                "Main": {
                    "commit": "c111111",
                    "commit_short": "c111111",
                    "files": {"Main.java": "blob_orig_lf"},
                }
            }),
            encoding="utf-8",
        )

        monkeypatch.setattr("yunhee.tools.as_is.drift.is_git_repo", lambda *args, **kwargs: True)
        monkeypatch.setattr("yunhee.tools.as_is.drift._commit_object_exists", lambda *args, **kwargs: True)
        monkeypatch.setattr("yunhee.tools.as_is.drift.compute_git_blob_file", lambda p: "blob_curr_crlf")

        # CRLF만 바뀐 상황: _is_crlf_only_diff True 반환
        monkeypatch.setattr("yunhee.tools.as_is.drift._is_crlf_only_diff", lambda *args, **kwargs: True)
        monkeypatch.setattr(
            "yunhee.tools.as_is.drift._check_index_freshness",
            lambda s, i: (
                0,
                "",
                {"Main": {"has_frontmatter": True, "source_files": {"Main.java": "blob_crlf"}}},
                {"commit": "c111111", "commit_short": "c111111", "branch": "main"},
            ),
        )

        # 1. run_drift 실행 시 기본적으로 동일 판정 (변경에서 제외)
        code, out, _ = run_drift(
            screen_args=["Main"],
            src_root=src_root,
            src_index=idx_root,
            base="baseline",
            work_dir=tmp_path,
        )
        assert code == 0
        assert "기준 대비 변경 0개" in out

        # diff 출력 시 "변경된 파일이 없습니다." 확인
        code_diff, out_diff, _ = run_drift(
            screen_args=["Main"],
            src_root=src_root,
            src_index=idx_root,
            base="baseline",
            output_fmt="diff",
            work_dir=tmp_path,
        )
        assert code_diff == 0
        assert "변경된 파일이 없습니다." in out_diff

        # 2. record_baseline 실행 시 --force 없이 "줄바꿈만 바뀜 → 기준 이동" 기록 성공
        code_rec, msg_rec = record_baseline(
            screen_names=["Main"],
            src_root=src_root,
            src_index=idx_root,
            force=False,
            work_dir=tmp_path,
        )
        assert code_rec == 0
        assert "줄바꿈만 바뀜 → 기준 이동" in msg_rec


class TestDriftDoneShared:
    """063 #3: drift --done-only 대장 해당없음 공유 변경 단위 제외 검증."""

    def test_drift_done_only_excludes_settled_shared_unit(self, tmp_path, monkeypatch):
        src_root = tmp_path / "src"
        src_root.mkdir()
        (src_root / "Fnd00_Fund.java").write_text("class Fnd00_Fund {}", encoding="utf-8")
        (src_root / "OtherScreen.java").write_text("class OtherScreen {}", encoding="utf-8")

        idx_root = tmp_path / "docs" / "as-is" / "src"
        idx_root.mkdir(parents=True)
        idx_file = idx_root / "_index.json"
        idx_file.write_text(
            json.dumps({
                "_meta": {"commit": "c222222", "branch": "main", "repo_name": "repo"},
                "OtherScreen": {
                    "kind": "screen",
                    "has_frontmatter": True,
                    "source_commit": "c222222",
                    "source_files": {
                        "OtherScreen.java": "h_other",
                        "Fnd00_Fund.java": "h_shared_old",
                    },
                },
            }),
            encoding="utf-8",
        )
        (idx_root / "_files.json").write_text(
            json.dumps({
                "Fnd00_Fund.java": ["OtherScreen", "AnotherScreen"],
                "OtherScreen.java": ["OtherScreen"],
            }),
            encoding="utf-8",
        )

        # baseline에 OtherScreen 완료 등록
        baseline_file = tmp_path / ".yunhee" / "baseline.json"
        baseline_file.parent.mkdir(parents=True)
        baseline_file.write_text(
            json.dumps({
                "OtherScreen": {
                    "commit": "c222222",
                    "files": {
                        "OtherScreen.java": "h_other",
                        "Fnd00_Fund.java": "h_shared_old",
                    },
                },
                "__units__": {
                    "Fnd00_Fund.java · selectBySearchText": {
                        "status": "해당없음",
                    }
                },
            }),
            encoding="utf-8",
        )

        # OtherScreen md: selectBySearchText를 호출하지 않음
        sc_dir = idx_root / "fnd" / "screens"
        sc_dir.mkdir(parents=True)
        (sc_dir / "OtherScreen.md").write_text(
            "# OtherScreen (#1050)\n## 서비스\n| `fnd.OtherService.getList` | L10 | [`other.xml`] | [`selectList`] |\n",
            encoding="utf-8",
        )

        monkeypatch.setattr("yunhee.tools.as_is.drift.is_git_repo", lambda *args, **kwargs: True)
        monkeypatch.setattr("yunhee.tools.as_is.drift._commit_object_exists", lambda *args, **kwargs: True)
        monkeypatch.setattr("yunhee.tools.as_is.drift._is_crlf_only_diff", lambda *args, **kwargs: False)
        # Fnd00_Fund.java 해시는 달라졌음 (변경 감지)
        monkeypatch.setattr(
            "yunhee.tools.as_is.drift.compute_git_blob_file",
            lambda p: "h_shared_new" if p.name == "Fnd00_Fund.java" else "h_other",
        )

        code, out, _ = run_drift(
            all_screens=True,
            done_only=True,
            src_root=src_root,
            src_index=idx_root,
            base="baseline",
            work_dir=tmp_path,
        )

        assert code == 0
        assert "기준 대비 변경 0개" in out
        assert "판단 끝난 공유 변경 1건 제외" in out
