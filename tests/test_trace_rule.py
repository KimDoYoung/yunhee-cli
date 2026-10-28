"""trace-rule: 규칙 저장소와 근거 검증 (OK / MOVED / STALE / MISSING)."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.store import trace_rules as store
from yunhee.tools.trace.rule import build_evidence, check_evidence, make_roots, run_rule

runner = CliRunner()
JAVA = "line1\nif (a) {\n    doIt();\n}\nline5\n"


@pytest.fixture
def roots_world(world, rule_db):
    java = world.tobe / "backend" / "src" / "main" / "java" / "x" / "Sample.java"
    java.write_text(JAVA, encoding="utf-8")
    return world, java


def _roots(world):
    return make_roots(world.ctx, world.tobe)


def test_verdict_normalization():
    assert store.normalize_verdict("의도적 변경") == "의도적 변경"
    assert store.normalize_verdict("changed") == "변경"
    assert store.normalize_verdict("의도적") == "의도적 변경"
    with pytest.raises(ValueError):
        store.normalize_verdict("애매함")


def test_store_crud_and_project_separation(rule_db):
    a = store.add_rule("Emp00", "일치", "ok", [], "p1")
    b = store.add_rule("Emp00", "누락", "gap", [], "p1")
    other = store.add_rule("Emp00", "변경", "x", [], "p2")
    assert (a.rule_id, b.rule_id, other.rule_id) == ("R-001", "R-002", "R-001")  # 번호는 프로젝트별
    assert [r.rule_id for r in store.list_rules("emp", "p1")] == ["R-001", "R-002"]  # 대소문자 무시·접두사
    assert [r.rule_id for r in store.list_rules(None, "p1", "누락")] == ["R-002"]
    upd = store.update_rule("r-001", verdict="변경", note="바뀜", proj="p1")
    assert (upd.verdict, upd.note) == ("변경", "바뀜") and upd.updated_at >= upd.created_at
    assert store.update_rule("R-999", note="x", proj="p1") is None
    assert store.get_rule("R-001", "p2").verdict == "변경" and store.get_rule("R-001", "p1").note == "바뀜"


def test_build_evidence_file_range_and_whole_file(roots_world):
    world, java = roots_world
    e = build_evidence(f"{java.name}:2-4", _roots(world), world.ctx)
    assert (e.kind, e.side, e.line, e.line_end) == ("file", "tobe", 2, 4) and e.excerpt == "if (a) { doIt(); }"
    assert e.path == "backend/src/main/java/x/Sample.java" and e.hash.startswith("sha256:")
    whole = build_evidence("Sample.java", _roots(world), world.ctx)
    assert whole.line is None and "line1" in whole.excerpt


def test_build_evidence_rejects_nonexistent_evidence(roots_world):
    world, java = roots_world
    r = _roots(world)
    with pytest.raises(ValueError, match="5줄인데 L99"):
        build_evidence(f"{java.name}:99", r, world.ctx)
    with pytest.raises(ValueError, match="파일을 찾지 못함"):
        build_evidence("NoSuchFile.java:3", r, world.ctx)
    with pytest.raises(ValueError, match="mapper 문장을 찾지 못함"):
        build_evidence("emp00_trans_info.nope", r, world.ctx)


def test_build_evidence_mapper_both_sides_and_ambiguity(roots_world):
    world, _ = roots_world
    asis = build_evidence("emp00_trans_info.selectByText", _roots(world), world.ctx)
    assert (asis.kind, asis.side, asis.anchor) == ("mapper", "asis", "emp00_trans_info.selectByText")
    tobe = build_evidence("EmpTransInfoMapper.searchTransInfos", _roots(world), world.ctx)
    assert tobe.side == "tobe" and tobe.anchor == "x.EmpTransInfoMapper.searchTransInfos" and tobe.line == 7
    # 같은 이름이 둘 이상인 파일은 경로를 요구한다
    (world.tobe / "frontend/src/pages/emp/Sample.java").write_text("a\n", encoding="utf-8")
    (world.tobe / "backend/src/main/java/x/Sample.java").write_text("a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="모호"):
        build_evidence("Sample.java:1", _roots(world), world.ctx)
    assert build_evidence("backend/src/main/java/x/Sample.java:1", _roots(world), world.ctx).side == "tobe"


def test_check_statuses_ok_moved_stale_missing(roots_world):
    world, java = roots_world
    r = _roots(world)
    e = build_evidence(f"{java.name}:2-4", r, world.ctx)
    assert check_evidence(e, r, world.ctx).status == "OK"
    java.write_text("// 새로 추가된 줄\n" + JAVA, encoding="utf-8")  # 내용은 같고 한 줄 아래로 밀림
    moved = check_evidence(e, r, world.ctx)
    assert (moved.status, moved.new_line) == ("MOVED", 3) and "L2-4 → L3-5" in moved.detail
    java.write_text(JAVA.replace("doIt();", "doOther();"), encoding="utf-8")
    assert check_evidence(e, r, world.ctx).status == "STALE"
    java.write_text("x\n", encoding="utf-8")
    assert check_evidence(e, r, world.ctx).status == "MISSING"  # 줄이 없어짐
    java.unlink()
    assert check_evidence(e, r, world.ctx).status == "MISSING"  # 파일이 없어짐


def test_formatting_and_blank_lines_are_not_content_changes(roots_world):
    world, java = roots_world
    r = _roots(world)
    e = build_evidence(f"{java.name}:2-4", r, world.ctx)
    java.write_text("line1\nif (a)   {\n        doIt();\n}\nline5\n", encoding="utf-8")  # 들여쓰기·공백만 바뀜
    assert check_evidence(e, r, world.ctx).status == "OK"
    java.write_text("line1\nif (a)   {\n\n        doIt();\n}\nline5\n", encoding="utf-8")  # 블록 안에 빈 줄이 끼어 한 줄 길어짐
    c = check_evidence(e, r, world.ctx)
    assert (c.status, c.new_line, c.new_end) == ("MOVED", 2, 5) and "L2-4 → L2-5" in c.detail
    java.write_text("line1\nif (a) {\n    doIt();\n    plus();\n}\nline5\n", encoding="utf-8")  # 내용이 실제로 늘어남
    assert check_evidence(e, r, world.ctx).status == "STALE"


def test_mapper_evidence_ignores_formatting_but_catches_sql_change(roots_world):
    world, _ = roots_world
    r = _roots(world)
    e = build_evidence("emp00_trans_info.selectByText", r, world.ctx)
    xml = world.src / "server/emp/mapper/emp00_trans_info.xml"
    original = xml.read_text(encoding="utf-8")
    xml.write_text(original.replace("SELECT p.emp01_nm", "select   p.emp01_nm"), encoding="utf-8")
    assert check_evidence(e, r, world.ctx).status == "OK"  # 대소문자·공백은 무시 (normalize_sql_for_drift)
    xml.write_text(original.replace("p.kind = 'A'", "p.kind = 'B'"), encoding="utf-8")
    assert check_evidence(e, r, world.ctx).status == "STALE"
    xml.write_text(original.replace('id="selectByText"', 'id="renamed"'), encoding="utf-8")
    assert check_evidence(e, r, world.ctx).status == "MISSING"


def test_run_rule_add_list_show_update(roots_world):
    world, java = roots_world
    res, code = run_rule("add", "Emp00_Tab_TransInfo", world.ctx, world.tobe, "조건 이동", "changed", [f"{java.name}:2-4", "emp00_trans_info.selectByText"])
    assert code == 0 and "규칙 저장: R-001 [변경] Emp00_Tab_TransInfo" in res.facts[0] and len(res.evidence) == 2
    lst, _ = run_rule("list", "emp00", world.ctx, world.tobe)
    assert lst.facts[0] == "규칙 1건 (대상 'emp00')" and "R-001" in lst.facts[1]
    show, _ = run_rule("show", "r-001", world.ctx, world.tobe)
    assert "사유: 조건 이동" in "\n".join(show.facts) and "Sample.java:2-4" in "\n".join(show.facts)
    upd, _ = run_rule("update", "R-001", world.ctx, world.tobe, "다시 씀", "의도적 변경")
    assert "[의도적 변경]" in upd.facts[0] and "다시 씀" in upd.facts[0] and "근거를 교체" not in upd.facts[0]
    swapped, _ = run_rule("update", "R-001", world.ctx, world.tobe, evidence=["emp00_trans_info.selectByText"])
    assert "근거를 교체함" in swapped.facts[0] and "(근거 1건)" in swapped.facts[0]


def test_run_rule_validation(roots_world):
    world, _ = roots_world
    with pytest.raises(ValueError, match="--verdict"):
        run_rule("add", "X", world.ctx, world.tobe, "n", None, [])
    with pytest.raises(ValueError, match="대상"):
        run_rule("add", None, world.ctx, world.tobe, "n", "일치", [])
    with pytest.raises(ValueError, match="규칙 ID"):
        run_rule("show", "화면", world.ctx, world.tobe)
    with pytest.raises(ValueError, match="찾지 못함"):
        run_rule("show", "R-009", world.ctx, world.tobe)
    with pytest.raises(ValueError, match="동작"):
        run_rule("remove", "R-001", world.ctx, world.tobe)
    res, _ = run_rule("add", "X", world.ctx, world.tobe, "근거 없음", "일치", [])
    assert any("근거(--evidence)가 없어" in u for u in res.unresolved)


def test_verify_all_and_exit_code(roots_world):
    world, java = roots_world
    run_rule("add", "A", world.ctx, world.tobe, "n", "일치", [f"{java.name}:2-4"])
    run_rule("add", "B", world.ctx, world.tobe, "n", "변경", ["emp00_trans_info.selectByText"])
    ok, code = run_rule("verify", None, world.ctx, world.tobe)
    assert code == 0 and "OK 2, MOVED 0, STALE 0, MISSING 0 (규칙 2건)" in ok.facts[0]
    java.write_text("// 위에 추가\n" + JAVA, encoding="utf-8")
    moved, code = run_rule("verify", None, world.ctx, world.tobe)
    assert code == 0 and "MOVED 1" in moved.facts[0]  # 줄만 이동한 것은 실패가 아니다
    java.write_text(JAVA.replace("doIt", "other"), encoding="utf-8")
    stale, code = run_rule("verify", "R-001", world.ctx, world.tobe)
    assert code == 1 and "STALE 1" in stale.facts[0] and any("STALE" in e for e in stale.evidence)
    java.unlink()
    missing, code = run_rule("verify", "R-001", world.ctx, world.tobe)
    assert code == 1 and "MISSING 1" in missing.facts[0] and "파일이 없음" in "\n".join(missing.facts)


def test_verify_accept_refreshes_evidence(roots_world):
    world, java = roots_world
    run_rule("add", "A", world.ctx, world.tobe, "n", "일치", [f"{java.name}:2-4"])
    java.write_text("// 위에 추가\n" + JAVA, encoding="utf-8")
    res, code = run_rule("verify", "R-001", world.ctx, world.tobe, accept=True)
    assert code == 0 and "근거를 현재 내용으로 갱신함" in "\n".join(res.facts)
    again, _ = run_rule("verify", "R-001", world.ctx, world.tobe)
    assert "OK 1, MOVED 0" in again.facts[0]
    moved = store.get_rule("R-001", "p1").evidence[0]
    assert (moved.line, moved.line_end, moved.ref) == (3, 5, "Sample.java:3-5")  # 근거가 새 위치를 가리키도록 갱신됨
    assert "if (a) { doIt(); }" in moved.excerpt


def test_verify_rule_without_evidence_is_missing(roots_world):
    world, _ = roots_world
    run_rule("add", "A", world.ctx, world.tobe, "n", "일치", [])
    res, code = run_rule("verify", None, world.ctx, world.tobe)
    assert code == 1 and "근거가 없어 확인할 수 없음" in "\n".join(res.facts)


def test_cli_trace_rule_flow_and_exit_codes(roots_world):
    world, java = roots_world
    base = ["--tobe", str(world.tobe), "--src", str(world.src), "--src-index", str(world.index)]
    add = runner.invoke(app, ["trace-rule", "add", "A", "-v", "일치", "--note", "메모", "-E", f"{java.name}:2-4", "-E", "emp00_trans_info.selectByText", "-o", "json", *base])
    assert add.exit_code == 0
    data = json.loads(add.output[add.output.index("{"):])
    assert data["params"]["project"] == "p1" and len(data["evidence"]) == 2
    assert runner.invoke(app, ["trace-rule", "verify", *base]).exit_code == 0
    java.write_text("changed\n", encoding="utf-8")
    assert runner.invoke(app, ["trace-rule", "verify", *base]).exit_code == 1
    assert runner.invoke(app, ["trace-rule", "add", "A", "-v", "일치", "-E", "Sample.java:99", *base]).exit_code == 2  # 없는 근거는 저장 전에 거부
    assert runner.invoke(app, ["trace-rule", "add", "A", *base]).exit_code == 2  # --verdict 없음
