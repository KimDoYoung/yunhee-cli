"""trace-code: 공통 코드 그룹의 값(DB, 읽기 전용)과 사용처(소스)."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.analysis.common import AmbiguousTargetError
from yunhee.tools.trace import db
from yunhee.tools.trace.code import find_usages, trace_code
from yunhee.tools.trace.resolve import TargetNotFoundError

runner = CliRunner()
KINDS = {"AprStatusCode": (12, "AprStatusCode", "문서결재상태코드"), "AprStepStatusCode": (13, "AprStepStatusCode", "결재단계상태")}
CODES = {12: [("10", "상신", 1, False), ("20", "결재중", 3, False), ("99", "임시저장", 1, True)]}


@pytest.fixture
def code_db(monkeypatch):
    def fetch(sql, params=(), **kw):
        if "FROM sys08_code_kind" in sql:
            key = params[0]
            if "lower(sys08_kind_cd) = lower" in sql:
                return [KINDS[k] for k in KINDS if k.lower() == key.lower()]
            return [v for k, v in KINDS.items() if key.strip("%").lower() in k.lower()]
        if "FROM sys09_code" in sql:
            return CODES.get(params[0], [])
        raise AssertionError(sql)

    monkeypatch.setattr(db, "fetch", fetch)


@pytest.fixture
def code_world(world):
    (world.src / "client" / "vi").mkdir(parents=True, exist_ok=True)
    (world.src / "server").mkdir(exist_ok=True)
    (world.src / "client/vi/Apr01_List.java").write_text(
        'class A {\n  // old: new ComboBoxField("AprStatusCode")\n  ComboBoxField c = new ComboBoxField("AprStatusCode", "%", "전체");\n  boolean b = "AprStatusCode".equals(x);\n}\n', encoding="utf-8")
    (world.src / "server/emp/mapper/code.xml").write_text(
        "<mapper namespace=\"code\">\n<!-- SELECT f_cdnm('AprStatusCode', a) -->\n<select id=\"s\">SELECT f_cdnm('AprStatusCode', a) FROM t</select>\n</mapper>\n", encoding="utf-8")
    (world.tobe / "frontend/src/pages/emp/Code.tsx").write_text("const ok = codes('AprStatusCode').length;\n", encoding="utf-8")
    return world


def _facts(res):
    return "\n".join(res.facts)


def test_values_come_from_db(code_world, code_db):
    text = _facts(trace_code("aprstatuscode", code_world.ctx_for(), code_world.tobe))
    assert "코드 그룹: AprStatusCode — 문서결재상태코드 (코드 3개)" in text
    assert "  10 상신" in text and "  20 결재중  [회사 3곳]" in text and "  99 임시저장  (사용 중지)" in text


def test_usages_are_classified_and_comments_ignored(code_world, code_db):
    res = trace_code("AprStatusCode", code_world.ctx_for(), code_world.tobe)
    text = _facts(res)
    assert "ASIS 사용처 3곳" in text and "TOBE 사용처 1곳" in text  # 주석 속 두 건(java //, xml <!-- -->)은 세지 않는다
    assert "SQL 리터럴(mapper)(1):" in text and "server/emp/mapper/code.xml:3" in text
    assert "콤보·선택 목록(1):" in text and "client/vi/Apr01_List.java:3" in text
    assert "상수 비교(1):" in text and "그 밖의 참조(1):" in text  # TOBE의 codes('…')
    assert any("직접 비교하는 곳은" in u for u in res.unresolved)


def test_find_usages_skips_build_dirs(tmp_path):
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "A.java").write_text('x("G")\n', encoding="utf-8")
    (tmp_path / "A.java").write_text('x("G")\n', encoding="utf-8")
    hits = find_usages("G", {"S": tmp_path})["S"]
    assert sum(len(v) for v in hits.values()) == 1


def test_ambiguous_and_unknown_group(code_world, code_db):
    with pytest.raises(AmbiguousTargetError) as exc:
        trace_code("StatusCode", code_world.ctx_for(), code_world.tobe)
    assert len(exc.value.candidates) == 2
    with pytest.raises(TargetNotFoundError):
        trace_code("Nope", code_world.ctx_for(), code_world.tobe)
    with pytest.raises(ValueError, match="영문자"):
        trace_code("x; DROP", code_world.ctx_for(), code_world.tobe)


def test_db_unavailable_still_finds_usages(code_world, monkeypatch):
    def boom(*a, **k):
        raise db.DbUnavailable("접속 실패")

    monkeypatch.setattr(db, "fetch", boom)
    res = trace_code("AprStatusCode", code_world.ctx_for(), code_world.tobe)
    assert any("DB를 쓸 수 없어 코드값을 구하지 못함" in u for u in res.unresolved)
    assert "ASIS 사용처 3곳" in _facts(res) and "코드 그룹:" not in _facts(res)


def test_cli_trace_code(code_world, code_db):
    base = ["--tobe", str(code_world.tobe), "--src", str(code_world.src), "--src-index", str(code_world.index)]
    out = runner.invoke(app, ["trace-code", "AprStatusCode", "-o", "json", *base])
    assert out.exit_code == 0
    assert json.loads(out.stdout)["params"]["resolved"] == "AprStatusCode"
    assert runner.invoke(app, ["trace-code", "StatusCode", *base]).exit_code == 2
    assert runner.invoke(app, ["trace-code", "Nope", *base]).exit_code == 1
