"""trace-branch: mapper·Java·TSX의 조건 지점."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.as_is.mybatis_render import parse_xml_statements
from yunhee.tools.trace.branch import (
    scan_java_conditions,
    scan_tsx_conditions,
    scan_ui_state,
    trace_branch,
)
from yunhee.tools.trace.resolve import TargetNotFoundError, load_context

runner = CliRunner()

JAVA = '''
public class Emp00_Tab_TransInfo {
    // if (commented.out()) { }
    /* if (blockComment) {
       throw new IllegalStateException("x");
    } */
    public Emp00_Tab_TransInfo() {
        if (LoginUser.getIsManager()) { button.setVisible(true); }
    }
    public void retrieve() {
        if ("겸직".equals(transName.getText())) {
            a();
        } else if (grid.getStore().size() > 0
                && flag != null) {
            b();
        }
        switch (type) { case 1: break; }
        String s = "if (inString) { }";
        throw new IllegalArgumentException("필수값(회사) 없음");
    }
    private void state() {
        saveButton.setEnabled(grid.getSelectionModel().getSelectedItem() != null);
        this.helper.setReadOnly(false);
    }
}
'''


def test_scan_java_conditions():
    conds = scan_java_conditions(JAVA)
    got = [(c.kind, c.text) for c in conds]
    assert ("if", "LoginUser.getIsManager()") in got
    assert ("if", '"겸직".equals(transName.getText())') in got
    assert ("else if", "grid.getStore().size() > 0 && flag != null") in got  # 여러 줄 조건
    assert ("switch", "type") in got
    assert ("throw", 'IllegalArgumentException("필수값(회사) 없음")') in got
    texts = " ".join(c.text for c in conds)
    assert "commented.out" not in texts and "blockComment" not in texts and "inString" not in texts
    assert next(c.line for c in conds if c.text == "LoginUser.getIsManager()") == 8


def test_scan_ui_state_marks_fixed_values():
    states = {c.text: c.kind for c in scan_ui_state(JAVA)}
    assert states["saveButton ← grid.getSelectionModel().getSelectedItem() != null"] == "setEnabled"
    assert any("button ← true" in t and "고정값" in t for t in states)


def test_scan_tsx_conditions():
    tsx = """import { Button } from 'x';
const A = () => (
  <div>
    <Button disabled={!selected}>저장</Button>
    {rows.length > 0 && <Grid />}
    {isAdmin ? <AdminBar /> : null}
  </div>
);
function f() {
  if (a > b) { return 1; }
}
"""
    kinds = {(c.kind, c.text) for c in scan_tsx_conditions(tsx)}
    assert ("disabled", "!selected") in kinds
    assert ("조건부 렌더링 &&", "rows.length > 0") in kinds
    assert ("조건부 렌더링 ?:", "isAdmin") in kinds
    assert ("if", "a > b") in kinds


MAPPER = """<mapper namespace="emp00">
  <sql id="orgFilter">
    <if test="orgId != null"> AND org_id = #{orgId}</if>
  </sql>
  <select id="search">
    SELECT CASE WHEN p.stat_cd = 'Y' THEN '사용' ELSE '미사용' END AS stat, p.name
    FROM emp01_person p
    <where>
      <if test="name != null"> AND p.name LIKE #{name}</if>
      <choose>
        <when test="${isTibero}"> AND p.a = 1</when>
        <when test="level == '10'"> AND p.b = 2</when>
        <otherwise> AND p.c = 3</otherwise>
      </choose>
      <include refid="orgFilter"/>
    </where>
  </select>
  <select id="plain">SELECT 1 FROM emp01_person</select>
</mapper>"""


@pytest.fixture
def ctx(tmp_path):
    src = tmp_path / "src" / "server" / "emp" / "mapper"
    src.mkdir(parents=True)
    (src / "emp00.xml").write_text(MAPPER, encoding="utf-8")
    idx = tmp_path / "idx"
    idx.mkdir()
    (idx / "_index.json").write_text(json.dumps({"client_classes": {}, "statements": {}}), encoding="utf-8")
    return load_context("asis", src=tmp_path / "src", src_index=idx)


def test_trace_branch_mapper(ctx):
    res = trace_branch("emp00.search", ctx)
    text = "\n".join(res.facts)
    assert "동적 SQL 분기(4)" in text  # if, when, otherwise, include 조각의 if (Tibero 분기는 방언 항목으로 분리)
    assert "<if test> name != null" in text and "<when test> level == '10'" in text and "<otherwise>" in text
    assert "<if test> orgId != null  (include emp00.orgFilter" in text  # include 조각 안의 분기와 출처
    assert "DB 방언 분기(1)" in text and "isTibero" in text
    assert "CASE WHEN(1)" in text and "CASE WHEN p.stat_cd = 'Y'" in text
    assert any(e.startswith("emp00.xml:") or "emp00.xml:" in e for e in res.evidence)
    assert any("${isTibero}" in u for u in res.unresolved)  # ${}는 값을 모르므로 알린다


def test_trace_branch_mapper_without_dynamic_sql(ctx):
    res = trace_branch("emp00.plain", ctx)
    assert "동적 SQL 분기: 없음" in "\n".join(res.facts)


def test_trace_branch_unknown_mapper_is_not_found(ctx):
    with pytest.raises(TargetNotFoundError):
        trace_branch("emp00.nope", ctx)
    base = ["--side", "asis", "--src", str(ctx.src_root), "--src-index", str(ctx.src_index)]
    assert runner.invoke(app, ["trace-branch", "emp00.nope", *base]).exit_code == 1


def test_mapper_branch_tags_come_from_the_statement_itself():
    _, statements = parse_xml_statements(MAPPER)
    assert "emp00.search" in statements


def test_cli_trace_branch(ctx):
    base = ["--side", "asis", "--src", str(ctx.src_root), "--src-index", str(ctx.src_index)]
    ok = runner.invoke(app, ["trace-branch", "emp00.search", "-o", "json", *base])
    assert ok.exit_code == 0
    data = json.loads(ok.output[ok.output.index("{"):])
    assert data["params"]["kind"] == "mapper" and data["facts"]
