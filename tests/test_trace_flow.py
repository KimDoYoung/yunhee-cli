"""trace-flow: 이벤트 → 핸들러 → 서비스 → 서버 → SQL → 테이블 사슬 (줄 범위로 연결)."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.trace.flow import handler_closure, normalize_event, trace_flow
from yunhee.tools.trace.resolve import load_context
from yunhee.tools.trace.screen import parse_event_line, parse_screen_doc

runner = CliRunner()

SCREEN_MD = """---
source_commit: abc12345
indexed_at: 2026-10-28T18:43:16+09:00
---
# Emp00_Tab_TransInfo

- 종류: 화면
- 메뉴: 사원관리 > 사원정보 관리 (#1029)
- 파일: `client/vi/emp/Emp00_Tab_TransInfo.java`

## 서비스

| 서비스 | 호출 위치 | 서버 | SQL ID |
|:---|:---|:---|:---|
| `emp.Emp00_TransInfo.selectByText` | Emp00_Tab_TransInfo:65 | [`Emp00_TransInfo.java:33`](x.md) | [`emp00_trans_info.selectByText`](x.md) |
| `emp.Emp03_Trans.delete` | Emp00_Tab_TransInfo:52 | [`Emp03_Trans.java:200`](x.md) | `UpdateDataModel(emp03_trans)` 동적 DELETE |
| `emp.Emp09_Etc.run` | Emp00_Tab_TransInfo:68 | [`Emp09_Etc.java:10`](x.md) | (없음) |
| `emp.Emp02_Others.updateOne` | Emp02_TabPage_Others:20 | [`Emp02_Others.java:43`](x.md) | [`emp02_others.upsert`](x.md) |

## 해석 못 한 서비스 호출

- `Emp00_Tab_TransInfo:66` `serviceKey`

## UI

### Emp00_Tab_TransInfo (`client/vi/emp/Emp00_Tab_TransInfo.java`, 80줄)

#### 이벤트 (도달 불가: dead 미연결)
[E0] 화면 열림 (생성자 L10-20) → settings(), retrieve()
[E1] retrieveButton[조회].Select (L30) → retrieve()
[E2] searchText.KeyPress [Enter] (L40) → retrieve()
[E3] delButton[삭제].Select (L50) → 인라인 L50-55 (new SelectHandler() { @Override publi…)
[E4] insertButton[등록].Select (L45) → insert()
[E5] deadButton[템플릿].Select (L47) → 인라인 L47-49 (new SelectHandler(){…) ⚠ 도달 불가 (dead 미연결)

#### 메서드
| 메서드 | 줄 | 호출처 | 하는 일 | 구분 |
| --- | --- | --- | --- | --- |
| private settings() | L10-20 | 생성자 | 이벤트 연결 | UI구성 |
| public retrieve() | L60-70 | 생성자,E1,E2,insert | 서비스 emp.Emp00_TransInfo.selectByText | 업무 |
| public insert() | L72-76 | E4 | 팝업 Emp03_Edit_Person 열기 | 업무 |

### Emp02_TabPage_Others (`client/vi/emp/Emp02_TabPage_Others.java`, 30줄)

#### 이벤트
[E4] updateButton[저장].Select (L18) → update()

#### 메서드
| 메서드 | 줄 | 호출처 | 하는 일 | 구분 |
| --- | --- | --- | --- | --- |
| public update() | L19-25 | E4 | 서비스 emp.Emp02_Others.updateOne | 업무 |
"""

MAPPER = """<mapper namespace="emp00_trans_info">
  <select id="selectByText">SELECT * FROM emp01_person p JOIN emp03_trans t ON t.id = p.id</select>
</mapper>
<!-- -->"""

MAPPER2 = """<mapper namespace="emp02_others">
  <update id="upsert">UPDATE emp02_others SET note = #{note} WHERE id = #{id}</update>
</mapper>"""


@pytest.fixture
def ctx(tmp_path):
    idx = tmp_path / "idx"
    (idx / "emp" / "screens").mkdir(parents=True)
    (idx / "emp" / "screens" / "Emp00_Tab_TransInfo.md").write_text(SCREEN_MD, encoding="utf-8")
    (idx / "menus.md").write_text(
        "| 메뉴 | # | 사용 | 화면 |\n|:---|:---|:---|:---|\n| 사원관리 > 사원정보 관리 | 1029 | true | [`Emp00_Tab_TransInfo`](emp/screens/Emp00_Tab_TransInfo.md) |\n",
        encoding="utf-8",
    )
    (idx / "_index.json").write_text(json.dumps({"client_classes": {}, "statements": {}}), encoding="utf-8")
    src = tmp_path / "src" / "server" / "emp" / "mapper"
    src.mkdir(parents=True)
    (src / "emp00_trans_info.xml").write_text(MAPPER.replace("<!-- -->", ""), encoding="utf-8")
    (src / "emp02_others.xml").write_text(MAPPER2, encoding="utf-8")
    return load_context("asis", src=tmp_path / "src", src_index=idx)


def test_parse_event_line():
    row = parse_event_line("[E2] searchText.KeyPress [Enter] (L209) → retrieve()")
    assert (row.id, row.guard, row.handler_methods) == ("E2", "Enter", ["retrieve"])
    ctor = parse_event_line("[E0] 화면 열림 (생성자 L77-128) → settings(), retrieve()")
    assert ctor.ranges == [(77, 128)] and ctor.handler_methods == ["settings", "retrieve"]
    inline = parse_event_line("[E6] btn[템플릿].Select (L243) → 인라인 L243-248 (new SelectHandler(){ @Override public…) ⚠ 도달 불가 (x)")
    assert inline.ranges == [(243, 248)] and inline.handler_methods == [] and inline.unreachable
    label = parse_event_line("[E3] transName[재직].Collapse (L225) → retrieve()")
    assert label.guard == ""  # 대괄호가 라벨이면 조건이 아니다


def test_handler_closure_keeps_call_path():
    ui = parse_screen_doc("Emp00_Tab_TransInfo", SCREEN_MD).ui["Emp00_Tab_TransInfo"]
    ev = {e.id: e for e in ui.event_rows}
    direct = {m.name: p for m, p in handler_closure(ui, ev["E1"])}
    assert direct == {"retrieve": []}
    via = {m.name: p for m, p in handler_closure(ui, ev["E4"])}  # E4 → insert() → retrieve()
    assert via == {"insert": [], "retrieve": ["insert"]}
    ctor = {m.name for m, _ in handler_closure(ui, ev["E0"])}
    assert ctor == {"settings", "retrieve"}


def test_normalize_event():
    assert normalize_event("e3") == normalize_event("3") == normalize_event("E3") == "E3"


def test_flow_connects_event_to_tables_by_line_range(ctx):
    res = trace_flow("#1029", ctx, "e1")
    text = "\n".join(res.facts)
    assert "E1 → retrieve() (L65) → 서비스 emp.Emp00_TransInfo.selectByText → 서버 Emp00_TransInfo.java:33" in text
    assert "SQL emp00_trans_info.selectByText: emp01_person(R), emp03_trans(R)" in text
    assert "쓰는 테이블: R: emp01_person, emp03_trans" in text
    assert "Emp00_Tab_TransInfo:65 서비스 emp.Emp00_TransInfo.selectByText 호출" in "\n".join(res.evidence)
    assert any("serviceKey" in u for u in res.unresolved)  # 핸들러 범위(L60-70)의 해석 못 한 호출
    assert "E1 → retrieve() (L68) → 서비스 emp.Emp09_Etc.run" in text  # L68도 retrieve()(L60-70) 안이라 같은 사슬에 든다
    assert "emp.Emp03_Trans.delete" not in text  # L52는 retrieve() 밖(인라인 E3의 범위)이다


def test_flow_service_without_sql_is_unresolved(ctx):
    res = trace_flow("#1029", ctx, "E1")
    assert any("emp.Emp09_Etc.run" in u and "SQL ID가 없음" in u for u in res.unresolved)


def test_flow_inline_dynamic_write_and_popup(ctx):
    inline = trace_flow("#1029", ctx, "E3")  # 인라인 L50-55 안에 delete 호출(L52)
    text = "\n".join(inline.facts)
    assert "E3 → 인라인" in text and "UpdateDataModel(emp03_trans) 동적 DELETE" in text
    assert "D: emp03_trans" in text
    popup = trace_flow("#1029", ctx, "E4")
    assert "E4 → insert() → retrieve()" in "\n".join(popup.facts)
    assert "이 이벤트가 여는 하위 화면: Emp03_Edit_Person" in "\n".join(popup.facts)


def test_flow_subclass_and_unreachable(ctx):
    sub = trace_flow("#1029", ctx, "E4", "Emp02_TabPage_Others")
    text = "\n".join(sub.facts)
    assert "이벤트(Emp02_TabPage_Others): [E4] updateButton[저장].Select (L18)" in text
    assert "emp.Emp02_Others.updateOne" in text and "emp02_others(U)" in text
    dead = trace_flow("#1029", ctx, "E5")
    assert any("도달 불가" in u for u in dead.unresolved)


def test_flow_list_and_unknown_event(ctx):
    listing = trace_flow("#1029", ctx)
    assert "이벤트 목록(Emp00_Tab_TransInfo, 6)" in listing.facts[0] and "E2 searchText.KeyPress [Enter]" in listing.facts[0]
    missing = trace_flow("#1029", ctx, "E9")
    assert missing.facts == [] and any("E9가 없음" in u and "E0" in u for u in missing.unresolved)
    other = trace_flow("#1029", ctx, "E4", "Nope")
    assert any("--class Nope" in u for u in other.unresolved)


def test_flow_without_asis_source_still_chains(ctx, tmp_path):
    ctx2 = load_context("asis", src=tmp_path / "missing", src_index=ctx.src_index)
    res = trace_flow("#1029", ctx2, "E1")
    assert "emp.Emp00_TransInfo.selectByText" in "\n".join(res.facts)
    assert any("ASIS 소스" in u for u in res.unresolved)


def test_cli_trace_flow(ctx):
    base = ["--side", "asis", "--src", str(ctx.src_root), "--src-index", str(ctx.src_index)]
    ok = runner.invoke(app, ["trace-flow", "#1029", "-e", "E1", "-o", "json", *base])
    assert ok.exit_code == 0
    data = json.loads(ok.output[ok.output.index("{"):])
    assert data["params"]["event"] == "E1" and data["facts"]
    assert runner.invoke(app, ["trace-flow", "Nope_X", *base]).exit_code == 1
