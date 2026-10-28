"""trace-screen: 화면 색인 문서 파싱과 팩트 시트 — 가짜 색인 디렉터리 사용."""

import json

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.trace.resolve import TargetNotFoundError, load_context, resolve_screen
from yunhee.tools.trace.screen import parse_screen_doc, trace_screen

runner = CliRunner()

SCREEN_MD = """---
source_commit: 9aa7dd18b83a3b218bc74edbd97fa9e25b5f920e
indexed_at: 2026-10-28T18:43:16+09:00
source_files:
  application/src/main/java/myApp/client/vi/emp/Emp00_Tab_TransInfo.java: 0d817b45
---
# Emp00_Tab_TransInfo

- 종류: 화면
- 메뉴: 경영관리 > 사원관리 > 사원정보 관리 (#1029)
- 파일: `client/vi/emp/Emp00_Tab_TransInfo.java`
- 함께 쓰는 클래스 2개:
  - `Emp02_TabPage_Others` `client/vi/emp/Emp02_TabPage_Others.java`
  - `Emp03_Edit_Person` `client/vi/emp/Emp03_Edit_Person.java`

## 서비스

| 서비스 | 호출 위치 | 서버 | SQL ID |
|:---|:---|:---|:---|
| `emp.Emp00_TransInfo.selectByText` | Emp00_Tab_TransInfo:418 | [`Emp00_TransInfo.java:33`](../../emp/services/Emp00_TransInfo.md) | [`emp00_trans_info.selectByText`](../../emp/sql/emp00_trans_info.md) |
| `emp.Emp02_Others.updateOne` | Emp02_TabPage_Others:173 | [`Emp02_Others.java:43`](../../emp/services/Emp02_Others.md) | [`emp02_others.upsert`](../../emp/sql/emp02_others.md), [`dbConfig.getSeq`](../../utils/sql/dbConfig.md) |
| `emp.Emp03_Trans.delete` | Emp02_TabPage_Others:200 | [`Emp03_Trans.java:200`](../../emp/services/Emp03_Trans.md) | `UpdateDataModel(emp03_trans)` 동적 DELETE |

## 테이블

[`emp01_person`](../../../db/tables/emp.md), [`emp02_others`](../../../db/tables/emp.md)

## DB 함수

`f_create_seq`, `to_decrypts`

## 해석 못 한 서비스 호출

- `Emp00_Tab_TransInfo:387` `null`

## 서블릿 호출

- `Emp02_TabPage_Others:107` `FileUpload fileType=image parentId=…`

## UI

GXT 소스에서 정적으로 뽑은 화면 구성 (LLM 없음).

### Emp00_Tab_TransInfo (`client/vi/emp/Emp00_Tab_TransInfo.java`, 446줄)

- 레이아웃: center=vlc, south=cp
- 툴바 `buttonBar`: 조회일자: {transDate} {retrieveButton}
- 입력·하위 화면: `searchText` TextField, `transDate` MyDateField
- 그리드 `grid` (buildGrid()):
  - empKorName 100 "성명" Text
  - hireDate 100 "입사일" Date

#### 이벤트 (도달 불가: tempDownloadButton 미연결)
[E0] 화면 열림 (생성자 L77-128) → settings(), retrieve()
[E1] retrieveButton[조회].Select (L231) → retrieve()

#### 메서드
| 메서드 | 줄 |
| --- | --- |
| public retrieve() | L394-432 |

#### 사용된 버튼들
1. <Button type="search" onClick={retrieve}>조회</Button>
2. <Button type="unknown (미등록 문구)" onClick={() => /* 인라인 L269-276 (new SelectHandler() { @Override publi…) */}>인사기록카드</Button>

### Emp02_TabPage_Others (`client/vi/emp/Emp02_TabPage_Others.java`, 410줄)

- 입력·하위 화면: `engName` TextField

#### 이벤트
[E0] 화면 열림 (생성자 L103-161) → getEditor()
[E4] updateButton[저장].Select (L138) → update()

#### 사용된 버튼들
1. <Button type="save" onClick={() => /* update() */}>저장</Button>
"""

MENUS_MD = """# 메뉴 → 화면

| 메뉴 | # | 사용 | 화면 |
|:---|:---|:---|:---|
| 경영관리 > 사원관리 > 사원정보 관리 | 1029 | true | [`Emp00_Tab_TransInfo`](emp/screens/Emp00_Tab_TransInfo.md) |
| 기본정보 > 사원정보 등록 | 1452 | true | [`Emp00_Tab_TransInfo`](emp/screens/Emp00_Tab_TransInfo.md) |
| 기본정보 > 미구현 메뉴 | 1500 | true | (MenuOpener 없음) |
"""

INDEX = {
    "client_classes": {"Emp00_Tab_TransInfo": {"services": [], "refs": []}},
    "statements": {"emp00_trans_info.selectByText": {"file": "server/emp/mapper/emp00_trans_info.xml", "line": 339, "kind": "select"}},
}


@pytest.fixture
def index_dir(tmp_path):
    idx = tmp_path / "idx"
    (idx / "emp" / "screens").mkdir(parents=True)
    (idx / "emp" / "screens" / "Emp00_Tab_TransInfo.md").write_text(SCREEN_MD, encoding="utf-8")
    (idx / "menus.md").write_text(MENUS_MD, encoding="utf-8")
    (idx / "_index.json").write_text(json.dumps(INDEX), encoding="utf-8")
    return idx


def test_parse_screen_doc_sections():
    doc = parse_screen_doc("Emp00_Tab_TransInfo", SCREEN_MD)
    assert doc.kind == "화면" and doc.menus == ["경영관리 > 사원관리 > 사원정보 관리 (#1029)"]
    assert doc.file == "client/vi/emp/Emp00_Tab_TransInfo.java"
    assert doc.classes == ["Emp02_TabPage_Others", "Emp03_Edit_Person"]
    assert doc.tables == ["emp01_person", "emp02_others"] and doc.functions == ["f_create_seq", "to_decrypts"]
    assert doc.unresolved_calls == ["`Emp00_Tab_TransInfo:387` `null`"]
    assert doc.frontmatter["source_commit"].startswith("9aa7dd18")


def test_parse_screen_doc_services():
    svc = {s.key: s for s in parse_screen_doc("X", SCREEN_MD).services}
    one = svc["emp.Emp00_TransInfo.selectByText"]
    assert one.callers == ["Emp00_Tab_TransInfo:418"] and one.server == "Emp00_TransInfo.java:33"
    assert one.sql_ids == ["emp00_trans_info.selectByText"]
    assert svc["emp.Emp02_Others.updateOne"].sql_ids == ["emp02_others.upsert", "dbConfig.getSeq"]
    dyn = svc["emp.Emp03_Trans.delete"]  # SQL ID 칸이 링크가 아니면 설명을 그대로 둔다
    assert dyn.sql_ids == [] and "동적 DELETE" in dyn.note


def test_parse_screen_doc_ui():
    main = parse_screen_doc("X", SCREEN_MD).ui["Emp00_Tab_TransInfo"]
    assert main.layout == "center=vlc, south=cp"
    assert main.grids == [("grid", ['empKorName 100 "성명" Text', 'hireDate 100 "입사일" Date'])]
    assert [e.split(" ")[0] for e in main.events] == ["[E0]", "[E1]"]
    assert main.events_note == "도달 불가: tempDownloadButton 미연결"
    # 인라인 핸들러가 있는 버튼도 라벨·타입·줄 범위가 깨지지 않는다
    assert main.buttons == ["조회 [search] → retrieve", "인사기록카드 [unknown (미등록 문구)] → 인라인 L269-276"]


def test_resolve_screen_by_menu_number(index_dir, tmp_path):
    ctx = load_context("asis", src=tmp_path, src_index=index_dir)
    assert resolve_screen("#1029", ctx) == "Emp00_Tab_TransInfo"
    assert resolve_screen("1452", ctx) == "Emp00_Tab_TransInfo"
    with pytest.raises(TargetNotFoundError) as exc:
        resolve_screen("#1500", ctx)  # 화면 클래스가 없는 메뉴
    assert "MenuOpener 없음" in exc.value.suggestions[0]
    with pytest.raises(TargetNotFoundError):
        resolve_screen("#9999", ctx)


def test_trace_screen_fact_sheet(index_dir, tmp_path):
    ctx = load_context("asis", src=tmp_path, src_index=index_dir)
    res = trace_screen("#1029", ctx)
    text = "\n".join(res.facts)
    assert "메뉴: 경영관리 > 사원관리 > 사원정보 관리 (#1029)" in text
    assert "그리드 grid(Emp00_Tab_TransInfo, 2열)" in text and "empKorName 100" in text
    assert "emp.Emp02_Others.updateOne → emp02_others.upsert, dbConfig.getSeq" in text
    assert "테이블(2): emp01_person, emp02_others" in text
    assert "하위 클래스 UI 요약(1)" in text
    ev = "\n".join(res.evidence)
    assert "emp.Emp00_TransInfo.selectByText 호출: Emp00_Tab_TransInfo:418 / 서버 Emp00_TransInfo.java:33" in ev
    assert "SQL emp00_trans_info.selectByText → server/emp/mapper/emp00_trans_info.xml:339" in ev
    assert "source_commit 9aa7dd18" in ev
    assert any("해석 못 한 서비스 호출" in u for u in res.unresolved)
    assert any("도달 불가" in u for u in res.unresolved)


def test_trace_screen_class_detail_filters_services(index_dir, tmp_path):
    ctx = load_context("asis", src=tmp_path, src_index=index_dir)
    res = trace_screen("Emp00_Tab_TransInfo", ctx, detail_class="Emp02_TabPage_Others")
    text = "\n".join(res.facts)
    assert "이벤트(Emp02_TabPage_Others, 2)" in text
    assert "Emp02_TabPage_Others이(가) 호출하는 서비스(RPC) 2개" in text
    assert "selectByText" not in text  # 다른 클래스가 호출하는 서비스는 빠진다
    bad = trace_screen("Emp00_Tab_TransInfo", ctx, detail_class="Nope")
    assert any("--class Nope" in u for u in bad.unresolved)


def test_trace_screen_tobe_missing_is_unresolved(index_dir, tmp_path):
    ctx = load_context("tobe", src=tmp_path, src_index=index_dir)
    res = trace_screen("Emp00_Tab_TransInfo", ctx, tobe_dir=tmp_path / "none")
    assert res.facts == [] and any("TOBE 화면" in u for u in res.unresolved)


def test_cli_exit_codes_and_json(index_dir):
    base = ["--side", "asis", "--src-index", str(index_dir)]
    ok = runner.invoke(app, ["trace-screen", "#1029", "-o", "json", "--max", "3", *base])
    assert ok.exit_code == 0
    data = json.loads(ok.output[ok.output.index("{"):])
    assert data["command"] == "trace-screen" and data["params"]["resolved"] == "Emp00_Tab_TransInfo"
    assert len(data["facts"]) == 3 and data["omitted"]["facts"] > 0
    assert runner.invoke(app, ["trace-screen", "Nope_Tab_X", *base]).exit_code == 1
    assert runner.invoke(app, ["trace-screen", "X", "--side", "foo"]).exit_code == 2
