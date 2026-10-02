"""AS-IS GXT 위젯/화면 이벤트 및 메서드 추출기(events) 단위 테스트."""

from pathlib import Path

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools.as_is.events import (
    BUTTON_TYPE_MAP,
    ButtonInfo,
    extract_buttons,
    extract_events,
    extract_events_and_methods,
    extract_grid_spec,
    render_events_markdown,
)


def test_extract_events_explicit_and_implicit():
    code = """
package test.pkg;

public class MyScreen {
    private TextButton btnSearch = new TextButton("조회");
    private GridBuilder grid = new GridBuilder();

    public MyScreen() {
        btnSearch.addSelectHandler(new SelectHandler() {
            @Override
            public void onSelect(SelectEvent event) {
                retrieve();
            }
        });

        grid.setDoubleClickEdit(true);

        SearchBarBuilder sb = new SearchBarBuilder(this);
        sb.addRetrieveButton();
        sb.addTextField(txtKeyword, "검색어", 100, 50, true);
        this.retrieve();
    }

    public void retrieve() {
    }
}
"""
    events, methods = extract_events_and_methods(code, "MyScreen.java")
    # E0(생성자) + E1(btnSearch.Select) + E2(Grid.DoubleClickEdit) + E3(SearchBar.Retrieve) + E4(txtKeyword.EnterKey) = 5개
    assert len(events) == 5

    e_types = [e.event_type for e in events]
    assert "Open" in e_types
    assert "Select" in e_types
    assert "DoubleClickEdit" in e_types
    assert "Retrieve" in e_types
    assert "EnterKey" in e_types

    # E0 화면 열림
    e0 = events[0]
    assert e0.id == "E0"
    assert "생성자" in e0.source
    assert "retrieve()" in e0.action

    # E1 확인
    e1 = next(e for e in events if e.event_type == "Select")
    assert e1.source == "btnSearch[조회]"
    assert e1.action == "retrieve()"
    assert e1.kind == "explicit"

    # 암묵적 이벤트 확인
    e_enter = next(e for e in events if e.event_type == "EnterKey")
    assert "txtKeyword" in e_enter.source
    assert e_enter.kind == "implicit"
    assert e_enter.condition == "[Enter]"
    assert e_enter.action == "retrieve()"

    # 메서드 분석 확인
    ret_m = next(m for m in methods if "retrieve()" in m.name)
    assert ret_m.name == "public retrieve()"
    assert "생성자" in ret_m.callers
    assert e1.id in ret_m.callers
    assert ret_m.category == "업무"


def test_extract_events_inline_logic():
    code = """
package test.pkg;

public class InlineScreen {
    private TextButton btnClear = new TextButton("초기화");

    public InlineScreen() {
        btnClear.addSelectHandler(e -> {
            nameField.setValue("");
            ageField.setValue(0);
        });
    }
}
"""
    events = extract_events(code, "InlineScreen.java")
    # E0 + E1
    assert len(events) == 2
    e = events[1]
    assert e.source == "btnClear[초기화]"
    assert e.event_type == "Select"
    assert "인라인" in e.action


def test_nested_dialog_events_and_methods():
    code = """
public class CompanyScreen {
    private TextButton btnDelete = new TextButton("삭제");

    public CompanyScreen() {
        btnDelete.addSelectHandler(e -> delete());
    }

    public void delete() {
        HtmlMessageBox mb = new HtmlMessageBox("삭제", "정말 삭제하시겠습니까?");
        mb.addDialogHideHandler(new DialogHideHandler() {
            @Override
            public void onDialogHide(DialogHideEvent event) {
                if ("YES".equals(event.getHideButton().name())) {
                    deleteCompany();
                }
            }
        });
    }

    private void deleteCompany() {
        GridDeleteData service = new GridDeleteData();
        service.delete(grid.getStore(), list, "sys.Company.delete");
    }
}
"""
    events, methods = extract_events_and_methods(code, "CompanyScreen.java")
    # E0, E1(btnDelete.Select), E2(mb.DialogHide)
    assert len(events) == 3

    e1 = next(e for e in events if e.id == "E1")
    e2 = next(e for e in events if e.id == "E2")

    # E2는 E1(delete)의 하위 이벤트
    assert e2.condition == "[YES]"
    assert e2.parent_id == "E1"
    assert e2 in e1.sub_events
    assert "deleteCompany()" in e2.action

    # 메서드 분석
    del_m = next(m for m in methods if "delete()" in m.name)
    assert del_m.name == "public delete()"
    assert del_m.callers == ["E1"]
    assert "ConfirmBox → E2" in del_m.work_desc

    del_comp_m = next(m for m in methods if "deleteCompany" in m.name)
    assert del_comp_m.name == "private deleteCompany()"
    assert del_comp_m.callers == ["E2"]
    assert "GridDeleteData sys.Company.delete" in del_comp_m.work_desc


def test_cli_events_command(tmp_path: Path):
    java_file = tmp_path / "TestScreen.java"
    java_file.write_text("""
public class TestScreen {
    private TextButton btnOk = new TextButton("확인");
    public TestScreen() {
        btnOk.addSelectHandler(e -> doOk());
    }
    public void doOk() {}
}
""", encoding="utf-8")

    runner = CliRunner()

    # 1. 기본 마크다운 출력
    res = runner.invoke(cli.app, ["events", str(java_file)])
    assert res.exit_code == 0
    assert "TestScreen.java" in res.output
    assert "## 이벤트" in res.output
    assert "btnOk[확인].Select" in res.output
    assert "doOk()" in res.output
    assert "## 메서드" in res.output
    assert "## Grid Spec" in res.output
    assert "Grid 사용하지 않음" in res.output

    # 2. --ids 옵션
    res_ids = runner.invoke(cli.app, ["events", str(java_file), "--ids"])
    assert res_ids.exit_code == 0
    assert "[E0] 화면 열림" in res_ids.output
    assert "[E1] btnOk[확인].Select (L5) → doOk()" in res_ids.output

    # 3. --json 옵션
    res_json = runner.invoke(cli.app, ["events", str(java_file), "--json"])
    assert res_json.exit_code == 0
    assert '"id": "E1"' in res_json.output
    assert '"methods":' in res_json.output
    assert '"grid_spec":' in res_json.output


def test_golden_sys01_tab_company():
    """Sys01_Tab_Company.java 골든 검증: E8 조건, 건수 표시 미포함, 초기값, 체크된 행 목록 등 정밀 대조."""
    asseterp_path = Path("/home/kdy987/oms-data/src/Asset-ERP/application/src/main/java/myApp/client/vi/sys/Sys01_Tab_Company.java")
    if not asseterp_path.is_file():
        return

    text = asseterp_path.read_text(encoding="utf-8", errors="replace")
    events, methods = extract_events_and_methods(text, file_path=asseterp_path)

    # 1. E8 조건: [arg0 != null] (L159)
    e8 = next(e for e in events if e.id == "E8")
    assert e8.condition == "[arg0 != null]"

    # 2. E7 조건: [선택>0]
    e7 = next(e for e in events if e.id == "E7")
    assert e7.condition == "[선택>0]"

    # 3. retrieve(): 건수 표시 없음
    ret_m = next(m for m in methods if m.name == "public retrieve()")
    assert "건수 표시" not in ret_m.work_desc
    assert "sys.Sys01_Company.selectByName" in ret_m.work_desc
    assert "생성자" in ret_m.callers

    # 4. settings(): 초기값 useYnBox=true
    settings_m = next(m for m in methods if m.name == "private settings()")
    assert "useYnBox=true" in settings_m.work_desc
    assert "생성자" in settings_m.callers

    # 5. deleteCompany(): 체크된 행 목록
    del_comp_m = next(m for m in methods if m.name == "private deleteCompany()")
    assert "(체크된 행 목록)" in del_comp_m.work_desc

    # 6. copyMenu(): 콜백 unmask
    copy_m = next(m for m in methods if m.name == "private copyMenu()")
    assert "콜백: unmask" in copy_m.work_desc

    # 7. retrieveTabpage(): 탭페이지 목록 연계
    tab_m = next(m for m in methods if m.name == "private retrieveTabpage()")
    assert "Sys01_TabPage_Info01" in tab_m.work_desc


def test_extract_grid_spec_golden_oms():
    """Asset-OMS Sys01_Tab_Company.java의 buildGrid() 추출 골든 검증."""
    oms_path = Path("/home/kdy987/workspace26/Asset-OMS/application/src/main/java/myOms/client/vi/sys/Sys01_Tab_Company.java")
    if not oms_path.is_file():
        return

    text = oms_path.read_text(encoding="utf-8", errors="replace")
    grid_spec = extract_grid_spec(text, file_path=oms_path)
    assert grid_spec is not None

    expected_lines = [
        "const buildGrid = () => [",
        "  gb.booleanYn2('loginSecureYn', 100, '보안로그인'),  // L184",
        "  gb.text('companyNm', 200, '고객명'),  // L185",
        "  gb.textCenter('locNm', 120, 'Sub-Domain'),  // L186",
        "  gb.textCenter('icamCompanyCd', 80, 'ICAM<br>운용사코드'),  // L190",
        "  gb.textCenter('icamAdvisCompanyCd', 80, 'ICAM<br>자문사코드'),  // L191",
        "  gb.booleanYn2('useYn', 80, '사용여부'),  // L192",
        "  gb.text('note', 250, '비고'),  // L193",
        "  gb.text('empInfo', 150, '담당자(이름/부서/직책)'),  // L195",
        "  gb.text('officeTelNo', 120, '대표전화'),  // L196",
        "  gb.text('emailAddr', 150, '이메일주소'),  // L197",
        "  gb.date('startDate', 100, '설립일'),  // L198",
        "  gb.date('closeDate', 100, '계약종료일'),  // L199",
        '  // ⚠DB없음 L200 icamCompanyType 80 "ICAM<br>회사유형" (sys01_icam_company_type 컬럼 없음)',
        "];",
    ]
    for exp in expected_lines:
        assert exp in grid_spec, f"Expected line missing from grid_spec:\n{exp}\nActual:\n{grid_spec}"


def test_extract_grid_spec_no_grid():
    """그리드가 없는 화면인 경우 None 반환 및 'Grid 사용하지 않음' 마크다운 렌더링 검증."""
    code = """
public class NoGridScreen {
    private TextButton btn = new TextButton("버튼");
    public NoGridScreen() {
        btn.addSelectHandler(e -> doSomething());
    }
    public void doSomething() {}
}
"""
    spec = extract_grid_spec(code)
    assert spec is None

    md = render_events_markdown("NoGridScreen.java", [], [], grid_spec=spec)
    assert "## Grid Spec" in md
    assert "Grid 사용하지 않음" in md


def test_extract_grid_spec_unit_mock():
    """단위 테스트: mock GridBuilder 호출로부터 올바른 gb.* 함수와 라인 번호 생성 검증."""
    code = """
public class MockGridScreen {
    private Grid<MockModel> buildGrid() {
        MockModelProperties properties = GWT.create(MockModelProperties.class);
        GridBuilder<MockModel> gridBuilder = new GridBuilder<MockModel>(properties.keyId());
        gridBuilder.addText(properties.title(), 150, "제목");
        gridBuilder.addLong(properties.amount(), 100, "금액");
        gridBuilder.addDate(properties.regDate(), 100, "등록일");
        gridBuilder.addBoolean(properties.activeYn(), 80, "활성");
        return gridBuilder.getGrid();
    }
}
"""
    spec = extract_grid_spec(code)
    assert spec is not None
    assert "const buildGrid = () => [" in spec
    assert "gb.text('title', 150, '제목')" in spec
    assert "gb.long('amount', 100, '금액')" in spec
    assert "gb.date('regDate', 100, '등록일')" in spec
    assert "gb.boolean('activeYn', 80, '활성')" in spec


def test_extract_buttons_mock():
    """모의 GXT 코드에서 버튼 추출 및 onClick, type, 번호 매김 리스트 검증."""
    code = """
public class ButtonScreen {
    private ColorButtonBar retrieveButton = new ColorButtonBar("조회");
    private ColorButtonBar insertButton   = new ColorButtonBar("등록");
    private ColorButtonBar deleteButton   = new ColorButtonBar("삭제");
    private ColorButtonBar customButton   = new ColorButtonBar("사용자정의버튼");

    public ButtonScreen() {
        ButtonBar bar = new ButtonBar();
        bar.add(retrieveButton);
        bar.add(insertButton);
        bar.add(deleteButton);
        bar.add(customButton);

        retrieveButton.addSelectHandler(new SelectHandler() {
            @Override public void onSelect(SelectEvent event) {
                retrieve();
            }
        });
        insertButton.addSelectHandler(new SelectHandler() {
            @Override public void onSelect(SelectEvent event) {
                insert();
            }
        });
        deleteButton.addSelectHandler(new SelectHandler() {
            @Override public void onSelect(SelectEvent event) {
                delete();
            }
        });
        customButton.addSelectHandler(new SelectHandler() {
            @Override public void onSelect(SelectEvent event) {
                doCustomAction();
            }
        });
    }

    public void retrieve() {}
    public void insert() {}
    public void delete() {}
    public void doCustomAction() {}
}
"""
    buttons = extract_buttons(code, file_path="ButtonScreen.java")
    assert len(buttons) == 4
    assert isinstance(buttons[0], ButtonInfo)
    assert BUTTON_TYPE_MAP["조회"] == "search"

    assert buttons[0].label == "조회"
    assert buttons[0].button_type == "search"
    assert buttons[0].handler == "retrieve"
    assert buttons[0].jsx == '<Button type="search" onClick={retrieve}>조회</Button>'

    assert buttons[1].label == "등록"
    assert buttons[1].button_type == "register"
    assert buttons[1].handler == "insert"
    assert buttons[1].jsx == '<Button type="register" onClick={insert}>등록</Button>'

    assert buttons[2].label == "삭제"
    assert buttons[2].button_type == "delete"
    assert buttons[2].handler == "delete"
    assert buttons[2].jsx == '<Button type="delete" onClick={delete}>삭제</Button>'

    assert buttons[3].label == "사용자정의버튼"
    assert buttons[3].button_type == "unknown"
    assert buttons[3].handler == "doCustomAction"
    assert buttons[3].jsx == '<Button type="unknown" onClick={doCustomAction}>사용자정의버튼</Button>'

    md = render_events_markdown("ButtonScreen.java", [], [], buttons=buttons)
    assert "## 사용된 버튼들" in md
    assert '1. <Button type="search" onClick={retrieve}>조회</Button>' in md
    assert '2. <Button type="register" onClick={insert}>등록</Button>' in md
    assert '3. <Button type="delete" onClick={delete}>삭제</Button>' in md
    assert '4. <Button type="unknown" onClick={doCustomAction}>사용자정의버튼</Button>' in md


def test_extract_buttons_searchbar():
    """SearchBarBuilder 암묵적 버튼(조회/저장/등록/삭제) 추출 검증."""
    code = """
public class SearchBarScreen {
    public SearchBarScreen() {
        SearchBarBuilder sb = new SearchBarBuilder(this);
        sb.addRetrieveButton();
        sb.addUpdateButton();
        sb.addInsertButton();
        sb.addDeleteButton();
    }
    public void retrieve() {}
    public void update() {}
    public void insertRow() {}
    public void deleteRow() {}
}
"""
    buttons = extract_buttons(code, file_path="SearchBarScreen.java")
    assert len(buttons) == 4
    assert buttons[0].jsx == '<Button type="search" onClick={retrieve}>조회</Button>'
    assert buttons[1].jsx == '<Button type="save" onClick={update}>저장</Button>'
    assert buttons[2].jsx == '<Button type="register" onClick={insertRow}>등록</Button>'
    assert buttons[3].jsx == '<Button type="delete" onClick={deleteRow}>삭제</Button>'


def test_extract_buttons_empty():
    """버튼이 없는 화면에서 '버튼 사용하지 않음' 출력 검증."""
    code = """
public class EmptyScreen {
    public EmptyScreen() {}
}
"""
    buttons = extract_buttons(code, file_path="EmptyScreen.java")
    assert len(buttons) == 0

    md = render_events_markdown("EmptyScreen.java", [], [], buttons=buttons)
    assert "## 사용된 버튼들" in md
    assert "버튼 사용하지 않음" in md


def test_extract_buttons_real_files():
    """실제 AS-IS 소스 파일이 존재하는 경우 버튼 추출 골든 검증."""
    erp_file = Path("/home/kdy987/oms-data/src/Asset-ERP/application/src/main/java/myApp/client/vi/sys/Sys01_Tab_Company.java")
    if erp_file.is_file():
        buttons = extract_buttons(erp_file.read_text(encoding="utf-8"), file_path=erp_file)
        labels = [b.label for b in buttons]
        assert "조회" in labels
        assert "등록" in labels
        assert "삭제" in labels
        assert "매뉴권한복사(초기)" in labels
        assert "문서개요복사" in labels

        b_search = next(b for b in buttons if b.label == "조회")
        assert b_search.button_type == "search"
        assert b_search.handler == "retrieve"

    edit_file = Path("/home/kdy987/oms-data/src/Asset-ERP/application/src/main/java/myApp/client/vi/sys/Sys01_Edit_Company.java")
    if edit_file.is_file():
        buttons = extract_buttons(edit_file.read_text(encoding="utf-8"), file_path=edit_file)
        labels = [b.label for b in buttons]
        assert "등록" in labels
        assert "닫기" in labels

        b_close = next(b for b in buttons if b.label == "닫기")
        assert b_close.button_type == "unknown"  # 표에 없으므로 unknown
        assert b_close.handler == "hide"


def test_extract_buttons_custom_tsv(tmp_path: Path):
    """임시 TSV 파일을 지정했을 때 사용자 정의 버튼 매핑이 우선 적용되는지 검증."""
    custom_tsv = tmp_path / "button-types.tsv"
    custom_tsv.write_text("닫기\tclose\n사용자정의\tcustom\n", encoding="utf-8")

    code = """
public class CustomScreen {
    private ColorButtonBottom closeButton = new ColorButtonBottom("닫기");
    public CustomScreen() {
        closeButton.addSelectHandler(e -> hide());
    }
    public void hide() {}
}
"""
    # 1. 기본 매핑 시: 닫기 -> unknown
    btns_default = extract_buttons(code, file_path="CustomScreen.java")
    assert btns_default[0].button_type == "unknown"

    # 2. 커스텀 TSV 지정 시: 닫기 -> close
    btns_custom = extract_buttons(code, file_path="CustomScreen.java", button_types_path=custom_tsv)
    assert btns_custom[0].button_type == "close"
    assert btns_custom[0].jsx == '<Button type="close" onClick={hide}>닫기</Button>'


def test_cli_events_button_types_option(tmp_path: Path):
    """CLI --button-types 옵션 동작 검증."""
    custom_tsv = tmp_path / "button-types.tsv"
    custom_tsv.write_text("닫기\tclose\n", encoding="utf-8")

    runner = CliRunner()
    target_file = Path("/home/kdy987/oms-data/src/Asset-ERP/application/src/main/java/myApp/client/vi/sys/Sys01_Edit_Company.java")
    if target_file.is_file():
        res = runner.invoke(
            cli.app,
            ["events", str(target_file), "--button-types", str(custom_tsv)],
        )
        assert res.exit_code == 0
        assert '<Button type="close" onClick={hide}>닫기</Button>' in res.output




