"""묶음 B: trace-map(영역 요약), trace-menu(메뉴 트리), trace-term(용어 교차 참조)."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.trace import db
from yunhee.tools.trace import term as term_mod
from yunhee.tools.trace.domainmap import compute, trace_map
from yunhee.tools.trace.menu import matches, trace_menu
from yunhee.tools.trace.resolve import MenuEntry, TargetNotFoundError
from yunhee.tools.trace.term import asis_labels, trace_term

runner = CliRunner()


def _facts(res):
    return "\n".join(res.facts)


# --- trace-map -------------------------------------------------------------

def test_map_counts_asis_and_tobe(world, fake_schema, monkeypatch):
    from yunhee.tools.trace import domainmap

    monkeypatch.setattr(domainmap, "load_snapshot", lambda env: type("R", (), {"ok": True, "data": {"tables": [{"name": "emp01_person"}, {"name": "emp02_others"}, {"name": "sys01_x"}]}})())
    text = _facts(trace_map(world.ctx_for(), world.tobe))
    assert "전체: ASIS 화면 2, TOBE 이식 1 (50%)" in text
    assert "emp (사원관리): ASIS 화면 2, 컴포넌트 0, 서비스 3, SQL 3, 테이블 2 | TOBE 이식 1/2 (50%), TSX 2, 엔드포인트 2, mapper 문장 2" in text


def test_map_domain_detail_and_unknown_domain(world, fake_schema):
    res = trace_map(world.ctx_for(), world.tobe, "emp")
    text = _facts(res)
    assert "아직 TOBE에 없는 화면(1): Emp09_Tab_Legacy" in text and "trace-gap --domain emp" in text
    with pytest.raises(TargetNotFoundError) as exc:
        trace_map(world.ctx_for(), world.tobe, "zzz")
    assert "emp" in exc.value.suggestions


def test_map_filters_non_domain_names(world, fake_schema):
    stats = compute(world.ctx_for(), __import__("yunhee.tools.trace.tobe", fromlist=["build_index"]).build_index(str(world.tobe)))
    assert set(stats) == {"emp"}  # 서버 클래스 키 `emp.Emp00_TransInfo`만 영역, 점이 없는 이름은 영역이 아니다


def test_map_without_tobe_is_asis_only(world, fake_schema, tmp_path):
    res = trace_map(world.ctx_for(), tmp_path / "nowhere")
    assert "TOBE 이식" not in _facts(res) and any("TOBE 소스를 찾지 못해" in u for u in res.unresolved)


# --- trace-menu ------------------------------------------------------------

def _entry(path, no, screen="Emp00_Tab_TransInfo"):
    return MenuEntry(path, no, "true", screen)


def test_menu_matching_rules():
    e = _entry("경영관리 > 01. 조직 및 사원관리 > 사원정보 관리", "1029")
    assert matches(e, "사원정보") and matches(e, "조직 및 사원관리 > 사원정보") and matches(e, "#1029") and matches(e, "1029")
    assert matches(e, "Emp00_Tab") and matches(e, "경영관리 > 사원정보")
    assert not matches(e, "사원정보 > 경영관리")  # 순서가 뒤바뀌면 아니다
    assert not matches(e, "#1030") and not matches(e, "급여")


def test_menu_overview_and_search(world):
    top = _facts(trace_menu(world.ctx_for(), world.tobe))
    assert "최상위 메뉴 1개, 메뉴 2개" in top and "사원관리: 메뉴 2, 화면 있는 메뉴 2, TOBE 있음 1" in top
    res = trace_menu(world.ctx_for(), world.tobe, "#1029")
    text = _facts(res)
    assert "사원정보 관리 (#1029) → Emp00_Tab_TransInfo — TOBE frontend/src/pages/emp/Emp00_Tab_TransInfo.tsx / API 1개: GET /api/v1/emp/trans-infos" in text
    legacy = _facts(trace_menu(world.ctx_for(), world.tobe, "레거시"))
    assert "레거시 화면 (#1030) → Emp09_Tab_Legacy — TOBE 없음" in legacy
    assert any("맞는 메뉴가 없음" in u for u in trace_menu(world.ctx_for(), world.tobe, "급여").unresolved)


def test_menu_marks_disabled_and_missing_screen(world):
    menus = world.index / "menus.md"
    menus.write_text(menus.read_text(encoding="utf-8") + "| 사원관리 > 미사용 메뉴 | 1099 | false | [`Emp00_Tab_TransInfo`](x.md) |\n| 사원관리 > 빈 메뉴 | 1098 | true | (MenuOpener 없음) |\n", encoding="utf-8")
    res = trace_menu(world.ctx_for(), world.tobe, "사원관리")
    text = _facts(res)
    assert "미사용 메뉴 (#1099) (사용 안 함)" in text and "빈 메뉴 (#1098) → (화면 클래스 없음)" in text
    assert any("#1098" in u for u in res.unresolved)


# --- trace-term ------------------------------------------------------------

@pytest.fixture
def term_world(world, monkeypatch):
    snap = {"generated_at": "t", "tables": [
        {"name": "emp01_person", "note": "개인정보", "columns": [{"name": "emp01_kor_nm", "note": "한글성명"}, {"name": "emp01_family_nm", "note": "가족 성명"}]},
        {"name": "empbak01_person", "note": "백업", "columns": [{"name": "empbak01_kor_nm", "note": "한글성명"}]},
    ]}
    monkeypatch.setattr(term_mod, "load_snapshot", lambda env: type("R", (), {"ok": True, "data": snap})())
    screen = world.index / "emp/screens/Emp00_Tab_TransInfo.md"
    screen.write_text(screen.read_text(encoding="utf-8") + "\n```javascript\n  gb.text('korNm', 100, '성명'),\n  gb.text('empKorNm', 100, '직원 성명'),\n```\n", encoding="utf-8")
    monkeypatch.setattr(db, "fetch", lambda sql, params=(), **kw: [("AprStatusCode", "결재상태", 5)] if "count(c.sys09_code_id)" in sql else [("AprStatusCode", "10", "성명 확인")])
    return world


def test_term_collects_columns_labels_and_codes(term_world):
    text = _facts(trace_term("성명", term_world.ctx_for(), term_world.tobe))
    assert "용어 '성명': 컬럼 2, 테이블 0" in text  # 백업 테이블의 컬럼은 뺀다
    assert "emp01_person.emp01_kor_nm — 한글성명" in text and "empbak01" not in text
    assert "ASIS 화면 라벨 2종" in text and "'성명' ← Emp00_Tab_TransInfo" in text
    assert "korNm ↔ 컬럼 emp01_person.emp01_kor_nm  [근거: 속성 이름이 컬럼명에서 만든 이름과 같음]" in text
    assert "empKorNm: 대응하는 컬럼 이름 없음" in text  # 규칙에 안 맞는 속성은 이어 붙이지 않는다
    assert "공통 코드: 그룹 1개, 코드값 이름에 포함 1건" in text and "AprStatusCode — 결재상태 (코드 5개)" in text


def test_term_tobe_labels_and_asis_labels_helper(term_world):
    text = _facts(trace_term("입사일", term_world.ctx_for(), term_world.tobe))
    assert "TOBE 화면 라벨 1종" in text and "'입사일' ← Emp00_Tab_TransInfo" in text
    assert asis_labels(term_world.index, "성명")["성명"] == [("Emp00_Tab_TransInfo", "korNm")]


def test_term_without_argument_and_db_failure(term_world, monkeypatch):
    assert "용어를 지정하세요" in _facts(trace_term(None, term_world.ctx_for(), term_world.tobe))

    def boom(*a, **k):
        raise db.DbUnavailable("접속 실패")

    monkeypatch.setattr(db, "fetch", boom)
    res = trace_term("성명", term_world.ctx_for(), term_world.tobe)
    assert any("DB를 쓸 수 없어 공통 코드 이름은 건너뜀" in u for u in res.unresolved) and "컬럼" in _facts(res)


def test_cli_map_menu_term(term_world):
    base = ["--tobe", str(term_world.tobe), "--src", str(term_world.src), "--src-index", str(term_world.index)]
    assert runner.invoke(app, ["trace-map", "-d", "emp", *base]).exit_code == 0
    assert runner.invoke(app, ["trace-map", "-d", "zzz", *base]).exit_code == 1
    out = runner.invoke(app, ["trace-menu", "#1029", "-o", "json", *base])
    assert out.exit_code == 0 and json.loads(out.stdout)["params"]["menu_path"] == "#1029"
    out = runner.invoke(app, ["trace-term", "성명", "-o", "json", *base])
    assert out.exit_code == 0 and json.loads(out.stdout)["facts"]
