"""trace-table: 스냅샷 + mapper 해석 + 색인으로 만드는 테이블 팩트 시트."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.base import ToolResult
from yunhee.tools.trace import table as trace_table_mod
from yunhee.tools.trace.resolve import TargetNotFoundError, load_context
from yunhee.tools.trace.table import _usage_by_table, trace_table

runner = CliRunner()


def _col(name, type_="numeric", **kw):
    return {"name": name, "type": type_, "not_null": kw.get("nn", False), "default": kw.get("default"), "note": kw.get("note")}


SNAPSHOT = {
    "generated_at": "2026-10-11T10:25:41+09:00",
    "tables": [
        {
            "schema": "public", "name": "emp02_others", "note": "Others 개인정보",
            "columns": [_col("emp02_others_id", nn=True, note="ID"), _col("emp02_person_id", note="개인ID"), _col("emp02_note", "text")],
            "pk": ["emp02_others_id"], "uniques": [{"name": "emp02_uk", "columns": ["emp02_person_id"]}], "indexes": [],
        },
        {"schema": "public", "name": "emp01_person", "note": "개인정보", "columns": [_col("emp01_id"), _col("emp02_person_id")], "pk": ["emp01_id"], "uniques": [], "indexes": []},
        {"schema": "public", "name": "emp01_person_20211118", "note": "백업", "columns": [_col("emp02_person_id")], "pk": [], "uniques": [], "indexes": []},
    ],
    "views": [{"name": "v_emp", "definition": "select * from emp02_others"}],
    "triggers": [],
    "refs": [],
}

MAPPER = """<mapper namespace="emp02_others">
  <select id="selectByPersonId">SELECT * FROM emp02_others WHERE emp02_person_id = #{personId}</select>
  <update id="upsert">
    WITH upsert AS (UPDATE emp02_others SET emp02_note = #{note} WHERE emp02_person_id = #{personId} RETURNING 1)
    INSERT INTO emp02_others (emp02_person_id, emp02_note) SELECT #{personId}, #{note} WHERE NOT EXISTS (SELECT 1 FROM upsert)
  </update>
  <delete id="deleteByPersonId">DELETE FROM emp02_others WHERE emp02_person_id = #{personId}</delete>
</mapper>"""

MENUS = """| 메뉴 | # | 사용 | 화면 |
|:---|:---|:---|:---|
| 경영관리 > 사원정보 관리 | 1029 | true | [`Emp00_Tab_TransInfo`](emp/screens/Emp00_Tab_TransInfo.md) |
"""

INDEX = {
    "server_classes": {
        "emp.Emp02_Others": {"methods": [
            {"name": "updateOne", "sqls": ["emp02_others.upsert"], "udm_calls": []},
            {"name": "selectByPersonId", "sqls": ["emp02_others.selectByPersonId"], "udm_calls": []},
            {"name": "remove", "sqls": [], "udm_calls": [["deleteModel", "emp02_others"]]},
        ]}
    },
    "client_classes": {
        "Emp02_TabPage_Others": {"services": ["emp.Emp02_Others.updateOne", "emp.Emp02_Others.remove"], "refs": []},
        "Emp00_Tab_TransInfo": {"services": [], "refs": ["Emp02_TabPage_Others"]},
    },
    "statements": {"emp02_others.upsert": {"file": "server/emp/mapper/emp02_others.xml", "line": 66, "kind": "update"}},
}


@pytest.fixture
def env(tmp_path, monkeypatch):
    src = tmp_path / "src"
    (src / "server" / "emp" / "mapper").mkdir(parents=True)
    (src / "server" / "emp" / "mapper" / "emp02_others.xml").write_text(MAPPER, encoding="utf-8")
    idx = tmp_path / "idx"
    idx.mkdir()
    (idx / "menus.md").write_text(MENUS, encoding="utf-8")
    (idx / "_index.json").write_text(json.dumps(INDEX), encoding="utf-8")
    monkeypatch.setattr(trace_table_mod, "load_snapshot", lambda env_name: ToolResult(ok=True, data=SNAPSHOT))
    _usage_by_table.cache_clear()
    return src, idx


def _facts(res):
    return "\n".join(res.facts)


def test_usage_classifies_crud(env):
    src, _ = env
    usage, approx = _usage_by_table(str(src))
    ops = {u.key: u.ops for u in usage["emp02_others"]}
    assert ops["emp02_others.selectByPersonId"] == "R"
    assert ops["emp02_others.upsert"] == "CU"  # CTE 안의 UPDATE + 본 INSERT
    assert ops["emp02_others.deleteByPersonId"] == "D"
    assert "upsert" not in usage  # CTE 이름은 테이블이 아니다
    assert approx == 0


def test_trace_table_fact_sheet(env):
    src, idx = env
    ctx = load_context("asis", src=src, src_index=idx)
    res = trace_table("emp02_others", ctx)
    text = _facts(res)
    assert "테이블: public.emp02_others — Others 개인정보" in text
    assert "PK: emp02_others_id" in text and "UNIQUE emp02_uk: emp02_person_id" in text
    assert "emp02_others_id numeric PK NN — ID" in text
    # 같은 이름의 컬럼은 조인 후보다. 백업 테이블은 빼고 개수만 알린다
    assert "emp02_person_id: emp01_person" in text and "백업·임시 테이블 1개 제외" in text
    assert "emp01_person_20211118" not in text.split("백업·임시")[0]
    assert "이 테이블을 참조하는 뷰(1): v_emp" in text
    assert "C(1): emp02_others.upsert" in text and "D(1): emp02_others.deleteByPersonId" in text
    assert "U(1): emp02_others.upsert" in text and "R(1): emp02_others.selectByPersonId" in text
    # 서비스 → 클라이언트 클래스 → 소속 화면(메뉴 번호)
    assert "emp.Emp02_Others.updateOne[CU]" in text
    assert "emp.Emp02_Others.remove[D]" in text  # SQL이 아니라 UpdateDataModel 동적 삭제
    assert "Emp02_TabPage_Others → Emp00_Tab_TransInfo(#1029)" in text
    ev = "\n".join(res.evidence)
    assert "스키마 스냅샷" in ev and "SQL emp02_others.upsert → server/emp/mapper/emp02_others.xml:66" in ev
    assert "UpdateDataModel(emp02_others) 동적 삭제" in ev


def test_trace_table_without_index_keeps_sql_usage(env):
    src, _ = env
    ctx = load_context("asis", src=src, src_index=src / "no_index")
    res = trace_table("emp02_others", ctx)
    assert "SQL 사용 3개" in _facts(res)
    assert any("색인이 없어" in u for u in res.unresolved)


def test_trace_table_no_shared_columns_is_stated(env, monkeypatch):
    src, idx = env
    ctx = load_context("asis", src=src, src_index=idx)
    snapshot_only = dict(SNAPSHOT, tables=[SNAPSHOT["tables"][0]])
    monkeypatch.setattr(trace_table_mod, "load_snapshot", lambda env_name: ToolResult(ok=True, data=snapshot_only))
    assert "같은 이름의 컬럼을 가진 테이블: 없음" in _facts(trace_table("emp02_others", ctx))


def test_trace_table_unknown_table_suggests(env):
    src, idx = env
    ctx = load_context("asis", src=src, src_index=idx)
    with pytest.raises(TargetNotFoundError) as exc:
        trace_table("emp02_other", ctx)
    assert "emp02_others" in exc.value.suggestions


def test_trace_table_missing_snapshot_is_unresolved(env, monkeypatch):
    src, idx = env
    monkeypatch.setattr(trace_table_mod, "load_snapshot", lambda env_name: ToolResult(ok=False, error="스냅샷 없음"))
    res = trace_table("emp02_others", load_context("asis", src=src, src_index=idx))
    assert res.facts == [] and any("스냅샷" in u for u in res.unresolved)


def test_cli_trace_table(env):
    src, idx = env
    out = runner.invoke(app, ["trace-table", "emp02_others", "--side", "asis", "--src", str(src), "--src-index", str(idx), "-o", "json"])
    assert out.exit_code == 0
    data = json.loads(out.output[out.output.index("{"):])
    assert data["params"]["resolved"] == "emp02_others" and data["facts"]
    nf = runner.invoke(app, ["trace-table", "nope_table", "--side", "asis", "--src", str(src), "--src-index", str(idx)])
    assert nf.exit_code == 1


def test_tobe_usage_lists_statements_and_screens(env, fake_schema):
    src, idx = env
    from yunhee.tools.trace.resolve import load_context as lc

    tobe_root = src.parent / "tobe"
    (tobe_root / "frontend/src/pages/emp").mkdir(parents=True)
    (tobe_root / "frontend/src/api").mkdir(parents=True)
    (tobe_root / "backend/src/main/java/x").mkdir(parents=True)
    (tobe_root / "backend/src/main/resources/mapper").mkdir(parents=True)
    (tobe_root / "frontend/src/pages/emp/Emp00_Tab_TransInfo.tsx").write_text("/** AS-IS: myApp/client/vi/emp/Emp00_Tab_TransInfo.java */\nempApi.searchTransInfos();\n", encoding="utf-8")
    (tobe_root / "frontend/src/api/emp.ts").write_text(
        "export const empApi = {\n  searchTransInfos: async () => {\n    await apiClient.get<X>('v1/emp/trans-infos', {});\n  },\n};\n", encoding="utf-8")
    (tobe_root / "backend/src/main/java/x/EmpController.java").write_text(
        'package x;\n@RequestMapping("/api/v1/emp")\npublic class EmpController {\n  private final EmpService svc;\n  @GetMapping("/trans-infos")\n  public R get() { return svc.find(); }\n}\n', encoding="utf-8")
    (tobe_root / "backend/src/main/java/x/EmpService.java").write_text("package x;\npublic class EmpService {\n  private final EmpMapper mapper;\n  public R find() {\n    return mapper.findAll();\n  }\n}\n", encoding="utf-8")
    (tobe_root / "backend/src/main/resources/mapper/EmpMapper.xml").write_text(
        '<mapper namespace="x.EmpMapper"><select id="findAll">SELECT * FROM emp02_others</select>'
        '<update id="touch">UPDATE emp02_others SET emp02_note = #{n}</update></mapper>', encoding="utf-8")
    from yunhee.tools.trace.tobe import build_index

    build_index.cache_clear()
    ctx = lc("both", src=src, src_index=idx)
    text = _facts(trace_table("emp02_others", ctx, tobe=tobe_root))
    assert "TOBE SQL 사용 2개" in text and "R(1): EmpMapper.findAll" in text and "U(1): EmpMapper.touch" in text
    assert "TOBE 화면(이 테이블에 닿는 API를 부름)(1): Emp00_Tab_TransInfo[R]" in text  # touch에 닿는 API는 없으므로 R만


def test_tobe_usage_without_tobe_is_unresolved(env, fake_schema, tmp_path):
    src, idx = env
    from yunhee.tools.trace.resolve import load_context as lc

    res = trace_table("emp02_others", lc("both", src=src, src_index=idx), tobe=tmp_path / "nowhere")
    assert any("TOBE mapper를 찾지 못해" in u for u in res.unresolved)


def test_cli_trace_table_and_flow_accept_tobe(env, fake_schema):
    src, idx = env
    base = ["--tobe", str(src.parent / "tobe"), "--src", str(src), "--src-index", str(idx), "--side", "asis"]
    assert runner.invoke(app, ["trace-table", "emp02_others", *base]).exit_code == 0
    assert runner.invoke(app, ["trace-flow", "Nope_X", *base]).exit_code == 1  # 옵션은 받고 대상이 없어서 1 (사용법 오류 2가 아니다)
