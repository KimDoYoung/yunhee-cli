"""yunhee analysis 도구 및 서브모듈 단위 테스트."""

import json
from pathlib import Path

import pytest

from yunhee.tools import analysis
from yunhee.tools.analysis import (
    method,
    run,
    screen,
    tobe,
    ui,
)
from yunhee.tools.analysis.common import AmbiguousTargetError


def test_registry_list_types():
    types_list = analysis.list_types()
    names = [t["name"] for t in types_list]
    for expected in ["method", "sql", "model", "grid", "screen", "ui", "tobe", "run"]:
        assert expected in names


def test_analysis_method_resolve_and_render(tmp_path: Path):
    src_dir = tmp_path / "src"
    client_dir = src_dir / "client" / "vi" / "emp"
    client_dir.mkdir(parents=True, exist_ok=True)

    java_file = client_dir / "Emp01_Tab.java"
    java_file.write_text("""
package test;

public class Emp01_Tab {
    public void retrieve() {
        if (selected == null) {
            new SimpleMessage("사원을 선택해주세요");
            return;
        }
        ServiceRequest req = new ServiceRequest("emp.Emp01.search");
        req.addParam("companyId", "1000");
    }

    public void retrieve(String text) {
        // overload
    }
}
""", encoding="utf-8")

    opts = {"src": src_dir}

    # 1. 모호한 타겟 -> AmbiguousTargetError (Exit 2 조건)
    with pytest.raises(AmbiguousTargetError) as exc_info:
        method.resolve("Emp01_Tab.retrieve", opts)
    assert len(exc_info.value.candidates) == 2

    # 2. 번호 선택 (#1)
    res = method.resolve("Emp01_Tab.retrieve#1", opts)
    assert res["cls"] == "Emp01_Tab"
    assert res["method"] == "retrieve"

    # 3. md 렌더링
    md_out = method.render(res, fmt="md")
    assert "Emp01_Tab.retrieve()" in md_out
    assert 'SimpleMessage "사원을 선택해주세요"' in md_out
    assert "emp.Emp01.search" in md_out

    # 4. code 렌더링
    code_out = method.render(res, fmt="code")
    assert "Emp01_Tab.java:" in code_out
    assert "public void retrieve() {" in code_out


def test_analysis_tobe_resolve_and_render(tmp_path: Path):
    tsx_file = tmp_path / "Sys01_Tab_Company.tsx"
    tsx_file.write_text("""
// 화면번호: SYS01
// AS-IS: Sys01_Tab_Company.java
import React, { useState } from 'react';

export const Sys01_Tab_Company: React.FC = () => {
    const [selectedId, setSelectedId] = useState<number | null>(null);
    const crud = useGridCrud({
        idField: 'companyId',
        search: sysApi.getCompanies,
        save: sysApi.saveCompany,
    });

    // [E1] 조회 버튼 클릭
    const handleSearch = () => {
        sysApi.getCompanies();
    };

    return (
        <Splitter vertical>
            <Panel>
                <SingleGrid />
            </Panel>
            <Panel>
                <Tabs />
            </Panel>
        </Splitter>
    );
};
""", encoding="utf-8")

    res = tobe.resolve(str(tsx_file), {})
    assert len(res["files"]) == 1
    f_info = res["files"][0]
    assert any("Sys01_Tab_Company" in exp[0] for exp in f_info["exports"])
    assert any("useGridCrud" in h for h in f_info["hooks"])

    md_out = tobe.render(res, fmt="md")
    assert "Sys01_Tab_Company.tsx" in md_out
    assert "useGridCrud" in md_out
    assert "[E1] 조회 버튼 클릭" in md_out


def test_analysis_run_render_json_and_tests(tmp_path: Path):
    log_file = tmp_path / "run_test.log"
    log_content = """=== Command: ./gradlew test ===
=== Exit Code: 0 ===
--- STDOUT ---
{"errs": [], "msgs": ["성공"], "items": [1, 2, 3, 4, 5]}
--- STDERR ---
"""
    log_file.write_text(log_content, encoding="utf-8")

    obj = {
        "run_record": {
            "id": "run_01",
            "command": "./gradlew test",
            "exit_code": 0,
            "duration_ms": 1200,
            "log_path": str(log_file),
            "summary": "성공",
        },
        "log_path": log_file,
        "stdout": '{"errs": [], "msgs": ["성공"], "items": [1, 2, 3, 4, 5]}',
        "log_text": log_content,
    }

    # 1. --stdout
    out_stdout = run.render(obj, opts={"stdout": True})
    assert '{"errs": [], "msgs": ["성공"]' in out_stdout

    # 2. --json with keys
    out_json = run.render(obj, opts={"json": True, "keys": "errs,msgs,items"})
    data = json.loads(out_json)
    assert data["errs"] == []
    assert data["msgs"] == ["성공"]
    assert data["items"] == 5  # 길이를 요약


def test_analysis_run_stderr(tmp_path: Path):
    """025: analysis run --stderr 동작 및 옵션 검증."""
    # 1. 일반 케이스 (stdout + stderr 둘 다 있음)
    log_content = """=== Command: test ===
=== Exit Code: 1 ===
--- STDOUT ---
stdout line 1
stdout line 2
--- STDERR ---
stderr line 1
stderr line 2
stderr line 3
"""
    log_file = tmp_path / "run_err.log"
    log_file.write_text(log_content, encoding="utf-8")

    from yunhee.store import run_tracker
    run_record = {
        "id": "run_test_err",
        "command": "test",
        "exit_code": 1,
        "duration_ms": 100,
        "log_path": str(log_file),
    }

    # resolve 테스트
    import sqlite3
    conn = sqlite3.connect(":memory:")
    run_tracker.init_db(conn)
    run_tracker.save_run(
        run_id="run_test_err",
        project="default",
        command="test",
        exit_code=1,
        duration_ms=100,
        log_path=str(log_file),
        summary="실패",
        conn=conn,
    )

    resolved = {
        "run_record": run_record,
        "log_path": log_file,
        "stdout": "stdout line 1\nstdout line 2",
        "stderr": "stderr line 1\nstderr line 2\nstderr line 3",
        "has_stderr_section": True,
        "log_text": log_content,
    }

    # --stderr 단독
    out_err = run.render(resolved, opts={"stderr": True})
    assert out_err == "stderr line 1\nstderr line 2\nstderr line 3"

    # --stderr with limit (-n 2)
    out_err_limit = run.render(resolved, opts={"stderr": True, "limit": 2})
    assert out_err_limit == "stderr line 1\nstderr line 2"

    # --stdout과 --stderr 동시 지정 (STDOUT, 빈 줄, STDERR 순서)
    out_both = run.render(resolved, opts={"stdout": True, "stderr": True})
    expected_both = "stdout line 1\nstdout line 2\n\nstderr line 1\nstderr line 2\nstderr line 3"
    assert out_both == expected_both

    # 2. STDERR 절이 비었을 때 -> (STDERR 없음)
    resolved_empty_err = {
        "run_record": run_record,
        "log_path": log_file,
        "stdout": "only stdout",
        "stderr": "",
        "has_stderr_section": True,
        "log_text": "--- STDOUT ---\nonly stdout\n--- STDERR ---\n",
    }
    out_empty = run.render(resolved_empty_err, opts={"stderr": True})
    assert out_empty == "(STDERR 없음)"

    # 3. --- STDERR --- 표시가 없는 옛 로그 -> 빈 문자열
    resolved_old_log = {
        "run_record": run_record,
        "log_path": log_file,
        "stdout": "old stdout",
        "stderr": "",
        "has_stderr_section": False,
        "log_text": "old log without stderr delimiter",
    }
    out_old = run.render(resolved_old_log, opts={"stderr": True})
    assert out_old == ""


def test_026_analysis_screen_and_ui_linked_components(tmp_path: Path):
    """026-1: analysis screen 및 ui에서 연결 컴포넌트 처리 검증."""
    src_index = tmp_path / "docs" / "as-is" / "src"
    sys_screens = src_index / "sys" / "screens"
    sys_comps = src_index / "sys" / "components"
    apr_comps = src_index / "apr" / "components"
    sys_screens.mkdir(parents=True, exist_ok=True)
    sys_comps.mkdir(parents=True, exist_ok=True)
    apr_comps.mkdir(parents=True, exist_ok=True)

    # 1. 같은 도메인 연결 컴포넌트: Sys01_Lookup_SelectMulti.md
    (sys_comps / "Sys01_Lookup_SelectMulti.md").write_text("""# Sys01_Lookup_SelectMulti

- 종류: 컴포넌트
- 파일: `client/vi/sys/Sys01_Lookup_SelectMulti.java`

## UI

### Sys01_Lookup_SelectMulti (`client/vi/sys/Sys01_Lookup_SelectMulti.java`, 166줄)

## Grid Spec
const buildGrid = () => [
  { id: 'companyId', label: '회사' },
];

## 사용된 버튼들
1. <Button type="submit">조회</Button>
2. <Button type="button">확인</Button>
3. <Button type="button">취소</Button>

## 이벤트
[E0] 생성자 초기화
[E1] 조회 버튼 클릭
[E2] 확인 버튼 클릭
[E3] 취소 버튼 클릭
[E4] 행 더블클릭
""", encoding="utf-8")

    # 2. 다른 도메인 연결 컴포넌트: Apr01_Edit_ApprDoc.md
    (apr_comps / "Apr01_Edit_ApprDoc.md").write_text("""# Apr01_Edit_ApprDoc

- 종류: 컴포넌트
- 파일: `client/vi/apr/Apr01_Edit_ApprDoc.java`

## UI

### Apr01_Edit_ApprDoc (`client/vi/apr/Apr01_Edit_ApprDoc.java`, 200줄)

## Grid Spec
const buildGrid = () => [];

## 사용된 버튼들
1. <Button>결재</Button>

## 이벤트
[E0] 초기화
""", encoding="utf-8")

    # 3. 링크가 없는 단순 화면: SimpleScreen.md
    (sys_screens / "SimpleScreen.md").write_text("""# SimpleScreen

## UI

### SimpleScreen (`SimpleScreen.java`, 100줄)
1. <Button>확인</Button>
[E0] 초기화
const buildGrid = () => [];
""", encoding="utf-8")

    # 4. 링크가 있는 복합 화면: Sys08_Tab_CodeKindClient.md
    (sys_screens / "Sys08_Tab_CodeKindClient.md").write_text("""# Sys08_Tab_CodeKindClient

- 종류: 화면
- 연결 화면·컴포넌트 (각 파일 참고): [`Sys01_Lookup_SelectMulti`](../../sys/components/Sys01_Lookup_SelectMulti.md), [`Apr01_Edit_ApprDoc`](../../apr/components/Apr01_Edit_ApprDoc.md)

## UI

### Sys08_Tab_CodeKindClient (`client/vi/sys/Sys08_Tab_CodeKindClient.java`, 285줄)
1. <Button>조회</Button>
2. <Button>복사</Button>
[E0] 초기화
[E1] 복사 확인 → copyChk() 에서 조회창 Sys01_Lookup_SelectMulti 열기
const buildGrid = () => [];

### Sys09_Grid_Code (`client/vi/sys/Sys09_Grid_Code.java`, 219줄)
1. <Button>저장</Button>
[E0] 초기화
const buildGrid = () => [];
""", encoding="utf-8")

    opts = {"src_index": src_index}

    # [검증 A] 링크가 없는 화면은 지금과 같은 출력
    res_simple = screen.resolve("SimpleScreen", opts)
    out_simple = screen.render(res_simple, opts={"list": True})
    assert "SimpleScreen" in out_simple
    assert "(연결)" not in out_simple
    assert "| **합계** |" in out_simple

    # [검증 B] 화면 파일에서 연결 컴포넌트 추출 (--list)
    res_main = screen.resolve("Sys08_Tab_CodeKindClient", opts)
    out_list = screen.render(res_main, opts={"list": True})

    # 같은 도메인은 `(연결)` 표시
    assert "Sys01_Lookup_SelectMulti (연결)" in out_list
    # 다른 도메인은 `(연결·다른 도메인)` 표시
    assert "Apr01_Edit_ApprDoc (연결·다른 도메인)" in out_list

    # 합계 계산:
    # Sys08(버튼 2, 이벤트 2, 그리드 1) + Sys09(버튼 1, 이벤트 1, 그리드 1) = 본 화면 (버튼 3, 이벤트 3, 그리드 2)
    # Sys01_Lookup_SelectMulti: 버튼 3, 이벤트 5, 그리드 1 (같은 도메인이라 기본 합계 포함)
    # Apr01_Edit_ApprDoc: 버튼 1, 이벤트 1, 그리드 1 (다른 도메인은 합계 제외!)
    # 총 합계: 버튼 3 + 3 = 6, 이벤트 3 + 5 = 8, 그리드 2 + 1 = 3
    assert "| **합계** |" in out_list
    assert "| **6** | **8** | **3** |" in out_list

    # [검증 C] --no-linked 옵션 시 연결 컴포넌트 제외
    out_no_linked = screen.render(res_main, opts={"list": True, "no_linked": True})
    assert "(연결)" not in out_no_linked
    # 본 화면만 합산: 버튼 3, 이벤트 3, 그리드 2
    assert "| **3** | **3** | **2** |" in out_no_linked

    # [검증 D] components 파일 직접 조회: screen Sys01_Lookup_SelectMulti --section buttons
    res_comp = screen.resolve("Sys01_Lookup_SelectMulti", opts)
    out_buttons = screen.render(res_comp, opts={"section": "buttons"})
    assert "조회" in out_buttons
    assert "확인" in out_buttons
    assert "취소" in out_buttons

    # [검증 E] 메인 화면에서 --class Sys01_Lookup_SelectMulti --section buttons 조회
    out_comp_sec = screen.render(res_main, opts={"class": "Sys01_Lookup_SelectMulti", "section": "buttons"})
    assert "조회" in out_comp_sec
    assert "확인" in out_comp_sec
    assert "취소" in out_comp_sec

    # [검증 F] analysis ui --tobe: 같은 도메인 연결 컴포넌트가 대조표에 포함됨
    tobe_dir = tmp_path / "frontend" / "src" / "pages" / "sys"
    tobe_dir.mkdir(parents=True, exist_ok=True)
    # TOBE tsx 작성
    (tobe_dir / "Sys08_Tab_CodeKindClient.tsx").write_text("<Button>조회</Button><Button>복사</Button><SingleGrid />", encoding="utf-8")
    (tobe_dir / "Sys01_Lookup_SelectMulti.tsx").write_text("<Button>조회</Button><Button>확인</Button><Button>취소</Button><SingleGrid />", encoding="utf-8")

    ui_res = ui.resolve("Sys08_Tab_CodeKindClient", {"src_index": src_index, "tobe": tobe_dir})
    ui_out = ui.render(ui_res)

    assert "Sys01_Lookup_SelectMulti" in ui_out
    assert "3/3" in ui_out  # 버튼 3개 대조
    assert "1/1" in ui_out  # 그리드 1개 대조
    # 다른 도메인 Apr01은 ui 대조표에 포함되지 않음
    assert "Apr01_Edit_ApprDoc" not in ui_out


def test_027_grid_counting_and_multi_grid(tmp_path: Path):
    """027-1, 027-2: 그리드 수 카운트 정밀화 및 analysis grid 다중 그리드 분리 검증."""
    from yunhee.tools.analysis import grid
    from yunhee.tools.analysis.common import count_as_is_grids, count_tobe_grids

    # 1. count_as_is_grids 검증
    # (1) 0개
    c0, w0 = count_as_is_grids("public class Simple { void test() {} }")
    assert c0 == 0 and not w0

    # (2) 1개 (buildGrid)
    c1, w1 = count_as_is_grids("""
- 그리드 `grid` (buildGrid(), 체크박스):
  - col1 100 "열1"
const buildGrid = () => [];
""")
    assert c1 == 1 and not w1

    # (3) 2개 (buildUserGrid, buildRoleGrid)
    c2, w2 = count_as_is_grids("""
- 그리드 `userGrid` (buildUserGrid(), 체크박스):
  - orgKorName 200 "부서명"
- 그리드 `userRoleGrid` (buildRoleGrid(), 체크박스):
  - roleName 200 "권한명"
const buildUserGrid = () => [];
const buildRoleGrid = () => [];
""")
    assert c2 == 2 and not w2

    # (4) 트리 그리드 포함 (- 트리 및 getTreeGrid)
    c_tree, w_tree = count_as_is_grids("""
- 트리 `orgTree` (getTreeGrid()):
  - orgName 200 "조직명"
getTreeGrid()
""")
    assert c_tree == 1 and not w_tree

    # (5) 두 방법의 값이 다르면 큰 값 + ⚠
    c_diff, w_diff = count_as_is_grids("""
- 그리드 `userGrid` (buildUserGrid(), 체크박스):
- 그리드 `userRoleGrid` (buildRoleGrid(), 체크박스):
const buildUserGrid = () => [];
""")
    assert c_diff == 2 and w_diff

    # 2. count_tobe_grids 주석 필터링 검증
    tsx_sample = """
// <SingleGrid /> 주석 1
/*
  <MultiGrid /> 주석 2
*/
export const View = () => (
    <div>
        <SingleGrid />
        <CellEditGrid />
    </div>
);
"""
    assert count_tobe_grids(tsx_sample) == 2

    # 3. analysis grid 다중 그리드 분리 및 --method 검증
    src_dir = tmp_path / "src"
    client_dir = src_dir / "client" / "vi" / "sys"
    client_dir.mkdir(parents=True, exist_ok=True)

    java_code = """
package test;

public class Sys05_Tab_PersonRole {
    private Grid<Emp00_TransInfoModel> userGrid = this.buildUserGrid();
    private Grid<Sys04_RoleModel> userRoleGrid = this.buildRoleGrid();

    public Grid<Emp00_TransInfoModel> buildUserGrid() {
        GridBuilder<Emp00_TransInfoModel> gb = new GridBuilder<Emp00_TransInfoModel>();
        gb.setChecked(SelectionMode.SINGLE);
        gb.addText(properties.orgKorName(), 200, "부서명");
        gb.addText(properties.emailAddress(), 200, "이메일주소");
        return gb.getGrid();
    }

    public Grid<Sys04_RoleModel> buildRoleGrid() {
        GridBuilder<Sys04_RoleModel> gb = new GridBuilder<Sys04_RoleModel>();
        gb.setChecked(SelectionMode.SINGLE);
        gb.addText(properties.roleName(), 200, "권한명");
        gb.addBoolean(properties.userRoleYn(), 40, "권한");
        gb.addText(properties.seq(), 80, "순서");
        gb.addText(properties.note(), 600, "비고");
        return gb.getGrid();
    }
}
"""
    (client_dir / "Sys05_Tab_PersonRole.java").write_text(java_code, encoding="utf-8")

    opts = {"src": src_dir}

    # 전체 다중 그리드 resolve & render
    res_all = grid.resolve("Sys05_Tab_PersonRole", opts)
    assert len(res_all["grids"]) == 2
    md_all = grid.render(res_all, fmt="md")
    assert "buildUserGrid" in md_all
    assert "buildRoleGrid" in md_all
    assert "userGrid = buildUserGrid()" in md_all
    assert "userRoleGrid = buildRoleGrid()" in md_all

    # --method buildRoleGrid 필터링
    res_meth = grid.resolve("Sys05_Tab_PersonRole", {"src": src_dir, "method": "buildRoleGrid"})
    assert len(res_meth["grids"]) == 1
    md_meth = grid.render(res_meth, fmt="md")
    assert "userRoleYn" in md_meth
    assert "orgKorName" not in md_meth

    # -o json 검증
    json_out = grid.render(res_all, fmt="json")
    parsed_json = json.loads(json_out)
    assert isinstance(parsed_json, list)
    assert len(parsed_json) == 2


