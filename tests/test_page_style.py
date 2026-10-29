import tempfile
from pathlib import Path

from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.page_style import (
    UNKNOWN,
    analyze,
    classify,
    compare_pages,
    extract_declared,
    extract_java,
    extract_tsx,
    scan_tab_files,
)

runner = CliRunner()


def test_classify_rules():
    # SGVF
    sid, why = classify({"grids": 1, "trees": 0, "edit": "view", "layout": "vertical"})
    assert sid == "SGVF"
    assert "읽기 전용" in why

    # SGEF
    sid, why = classify({"grids": 1, "trees": 0, "edit": "edit", "layout": "vertical"})
    assert sid == "SGEF"
    assert "편집" in why

    # SGTP
    sid, why = classify({"grids": 1, "trees": 0, "tabpage": True, "layout": "vertical"})
    assert sid == "SGTP"
    assert "아래 탭 영역" in why

    # SGT vs TG
    sid, _ = classify({"grids": 1, "trees": 1, "layout": "horizontal", "top_search": True})
    assert sid == "SGT"

    sid, _ = classify({"grids": 1, "trees": 1, "layout": "horizontal", "top_search": False})
    assert sid == "TG"

    # GG
    sid, _ = classify({"grids": 2, "trees": 0, "layout": "none"})
    assert sid == "GG"

    # SGP
    sid, _ = classify({"grids": 1, "trees": 0, "popup": True, "search": True})
    assert sid == "SGP"

    # CG
    sid, _ = classify({"grids": 1, "trees": 0, "editable_grid": True, "search": True})
    assert sid == "CG"

    # SG
    sid, _ = classify({"grids": 1, "trees": 0, "search": True})
    assert sid == "SG"

    # 미분류
    sid, _ = classify({"grids": 0, "trees": 0})
    assert sid == UNKNOWN


def test_tsx_extraction():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # Edit 컴포넌트 (읽기 전용)
        edit_file = tdp / "Test_Edit_Sub.tsx"
        edit_file.write_text("""
        import React from 'react';
        export const Test_Edit_Sub = () => (
            <input readOnly />
        );
        """, encoding="utf-8")

        # Tab 컴포넌트
        tab_file = tdp / "Test_Tab_Main.tsx"
        tab_file.write_text("""
        /**
         * 스타일: SGVF
         */
        import React from 'react';
        import { Splitter } from 'antd';
        import { SingleGrid } from '@/components/grid';
        import { SearchBar } from '@/components/search';
        import { Test_Edit_Sub } from './Test_Edit_Sub';

        export const Test_Tab_Main = () => (
            <div>
                <SearchBar />
                <Splitter layout="vertical">
                    <SingleGrid />
                    <Test_Edit_Sub />
                </Splitter>
            </div>
        );
        """, encoding="utf-8")

        features, declared = extract_tsx(tab_file)
        assert declared == "SGVF"
        assert features["search"] is True
        assert features["top_search"] is True
        assert features["layout"] == "vertical"
        assert features["grids"] == 1
        assert features["edit"] == "view"

        res = analyze(tab_file)
        assert res["sid"] == "SGVF"
        assert res["declared"] == "SGVF"
        assert "위아래 분할" in res["why"]


def test_java_extraction():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # Java 자식 컴포넌트 (편집 폼)
        edit_file = tdp / "Sys01_Edit_Company.java"
        edit_file.write_text("""
        package myApp.client.vi.sys;
        public class Sys01_Edit_Company {
            public Sys01_Edit_Company() {
                // Not read-only
            }
        }
        """, encoding="utf-8")

        # Java 메인 탭 컴포넌트
        tab_file = tdp / "Sys01_Tab_Company.java"
        tab_file.write_text("""
        package myApp.client.vi.sys;
        public class Sys01_Tab_Company {
            private Grid<Model> grid;
            public Sys01_Tab_Company() {
                setNorthWidget(new ColorButtonBar("조회"));
                setSouthWidget(new Sys01_Edit_Company());
            }
        }
        """, encoding="utf-8")

        features, declared = extract_java(tab_file)
        assert declared is None
        assert features["search"] is True
        assert features["layout"] == "vertical"
        assert features["grids"] == 1
        assert features["edit"] == "edit"

        res = analyze(tab_file)
        assert res["sid"] == "SGEF"


def test_compare_and_scan():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        f_java = tdp / "Fnd01_Tab_Test.java"
        f_java.write_text("""
        public class Fnd01_Tab_Test {
            private Grid<Model> grid;
            public Fnd01_Tab_Test() {
                setNorthWidget(new Button("조회"));
            }
        }
        """, encoding="utf-8")

        f_tsx = tdp / "Fnd01_Tab_Test.tsx"
        f_tsx.write_text("""
        export const Fnd01_Tab_Test = () => (
            <div>
                <SearchBar />
                <SingleGrid />
            </div>
        );
        """, encoding="utf-8")

        # scan
        files = scan_tab_files(tdp)
        assert len(files) == 2

        # compare
        comp = compare_pages(f_java, f_tsx)
        assert comp["same"] is True
        assert comp["a"]["sid"] == "SG"
        assert comp["b"]["sid"] == "SG"


def test_cli_page_style_single_and_json():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        f_tsx = tdp / "Sample_Tab_Page.tsx"
        f_tsx.write_text("""
        export const Sample_Tab_Page = () => (
            <div>
                <SearchBar />
                <SingleGrid />
            </div>
        );
        """, encoding="utf-8")

        # 1. 단일 파일 기본 실행 -> SID만 출력
        res = runner.invoke(app, ["page-style", str(f_tsx)])
        assert res.exit_code == 0
        assert res.output.strip() == "SG"

        # 2. JSON 모드
        res_json = runner.invoke(app, ["page-style", "--json", str(f_tsx)])
        assert res_json.exit_code == 0
        assert '"sid": "SG"' in res_json.output


def test_cli_page_style_compare_and_all():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        f_java = tdp / "Sample_Tab_Page.java"
        f_java.write_text("""
        public class Sample_Tab_Page {
            private Grid<M> g;
            public Sample_Tab_Page() {
                setNorthWidget(new Button("조회"));
            }
        }
        """, encoding="utf-8")

        f_tsx = tdp / "Sample_Tab_Page.tsx"
        f_tsx.write_text("""
        export const Sample_Tab_Page = () => (
            <div>
                <SearchBar />
                <SingleGrid />
            </div>
        );
        """, encoding="utf-8")

        # compare
        res_comp = runner.invoke(app, ["page-style", "--compare", str(f_java), str(f_tsx)])
        assert res_comp.exit_code == 0
        assert "일치" in res_comp.output

        # all
        res_all = runner.invoke(app, ["page-style", "--all", str(tdp)])
        assert res_all.exit_code == 0
        assert "# SID별 분포 (2개)" in res_all.output
        assert "SG       2" in res_all.output


def test_sgtp_tsx_and_java():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # 1. TSX SGTP
        tab_sub = tdp / "Test01_TabPage_Detail.tsx"
        tab_sub.write_text("export const Test01_TabPage_Detail = () => <div />;", encoding="utf-8")

        main_tsx = tdp / "Test01_Tab_Main.tsx"
        main_tsx.write_text("""
        import React from 'react';
        import { Splitter } from 'antd';
        import { SingleGrid } from '@/components/grid';
        import { SearchBar } from '@/components/search';
        import { Test01_TabPage_Detail } from './Test01_TabPage_Detail';

        export const Test01_Tab_Main = () => (
            <div>
                <SearchBar />
                <Splitter layout="vertical">
                    <SingleGrid />
                    <Test01_TabPage_Detail />
                </Splitter>
            </div>
        );
        """, encoding="utf-8")

        res_tsx = analyze(main_tsx)
        assert res_tsx["sid"] == "SGTP"
        assert res_tsx["features"]["tabpage"] is True

        # 2. Java SGTP
        tab_sub_java = tdp / "Test01_TabPage_Detail.java"
        tab_sub_java.write_text("public class Test01_TabPage_Detail {}", encoding="utf-8")

        main_java = tdp / "Test01_Tab_Main.java"
        main_java.write_text("""
        public class Test01_Tab_Main {
            private Grid<M> g;
            public Test01_Tab_Main() {
                setNorthWidget(new Button("조회"));
                setSouthWidget(new Test01_TabPage_Detail());
            }
        }
        """, encoding="utf-8")

        res_java = analyze(main_java)
        assert res_java["sid"] == "SGTP"
        assert res_java["features"]["tabpage"] is True

        # 3. Compare
        comp = compare_pages(main_java, main_tsx)
        assert comp["same"] is True
        assert comp["a"]["sid"] == "SGTP"
        assert comp["b"]["sid"] == "SGTP"


def test_declared_parsing_and_warning():
    # 1. Block comment with extra explanation
    txt1 = """
    /**
     * 스타일: STP (견본 — docs/page-style.md)
     */
    """
    decl1, warn1 = extract_declared(txt1)
    assert decl1 == "STP"
    assert warn1 is None

    # 2. Single-line comment
    txt2 = "// 스타일: IN (임직원매매 화면사용순서 안내)"
    decl2, warn2 = extract_declared(txt2)
    assert decl2 == "IN"
    assert warn2 is None

    # 3. Invalid SID
    txt3 = "// 스타일: UNKNOWN_FOO"
    decl3, warn3 = extract_declared(txt3)
    assert decl3 == "UNKNOWN_FOO"
    assert warn3 is not None
    assert "유효한 SID 목록에 없습니다" in warn3

    # 4. Deprecated DB -> DSBRD with warning
    txt4 = "// 스타일: DB"
    decl4, warn4 = extract_declared(txt4)
    assert decl4 == "DSBRD"
    assert warn4 is not None
    assert "DSBRD" in warn4

    # 5. Valid 5-letter DSBRD
    txt5 = "// 스타일: DSBRD"
    decl5, warn5 = extract_declared(txt5)
    assert decl5 == "DSBRD"
    assert warn5 is None


def test_new_sids_classification():
    # SGHF
    sid, _ = classify({"grids": 1, "edit": "edit", "layout": "horizontal"})
    assert sid == "SGHF"

    # GDP
    sid, _ = classify({
        "grids": 1,
        "layout": "horizontal",
        "search": False,
        "children": ["Sms02_TabPage_Detail"],
    })
    assert sid == "GDP"

    # SGEF (위 SearchBar + 그리드, 아래 Edit 폼 - layout=none 이어도 SGEF)
    sid_sgef, _ = classify({"grids": 1, "edit": "edit", "layout": "none"})
    assert sid_sgef == "SGEF"

    # TO
    sid, _ = classify({"trees": 1, "layout": "none"})
    assert sid == "TO"

    # GO
    sid, _ = classify({"grids": 1, "search": False})
    assert sid == "GO"

    # DSBRD
    sid, _ = classify({"grids": 0, "api_calls": True})
    assert sid == "DSBRD"

    # IN
    sid, _ = classify({"grids": 0, "menu_link": True})
    assert sid == "IN"

    # STP vs TP
    sid_stp, _ = classify({"grids": 0, "tabs": True, "search": True})
    assert sid_stp == "STP"

    sid_tp, _ = classify({"grids": 0, "tabs": True, "search": False})
    assert sid_tp == "TP"

    # SR
    sid_sr, _ = classify({"grids": 0, "rd": True, "search": True})
    assert sid_sr == "SR"

    # GCG
    sid_gcg, _ = classify({"grids": 2, "calendar": True})
    assert sid_gcg == "GCG"


def test_wrapper_delegation_tsx():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # Parent screen (TG)
        mgr = tdp / "Dcr01_Tab_DcrManager.tsx"
        mgr.write_text("""
        import React from 'react';
        import { Splitter, Tree } from 'antd';
        export const Dcr01_Tab_DcrManager = () => (
            <Splitter>
                <Splitter.Panel><Tree /></Splitter.Panel>
                <Splitter.Panel><div>Content</div></Splitter.Panel>
            </Splitter>
        );
        """, encoding="utf-8")

        # Wrapper screen (renders parent)
        usr = tdp / "Dcr01_Tab_DcrUser.tsx"
        usr.write_text("""
        import React from 'react';
        import { Dcr01_Tab_DcrManager } from './Dcr01_Tab_DcrManager';
        export const Dcr01_Tab_DcrUser = () => <Dcr01_Tab_DcrManager />;
        """, encoding="utf-8")

        res = analyze(usr)
        assert res["sid"] == "TG"
        assert "Dcr01_Tab_DcrManager 위임" in res["why"]


def test_popup_grid_not_counted_and_save_button_not_cg():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # 1. Popup with grid should NOT increase parent grid count
        edit_popup = tdp / "Test_Edit_Popup.tsx"
        edit_popup.write_text("""
        import React from 'react';
        import { Modal } from 'antd';
        import { SingleGrid } from '@/components/grid';
        export const Test_Edit_Popup = () => (
            <Modal open onClose={() => {}}>
                <SingleGrid />
            </Modal>
        );
        """, encoding="utf-8")

        main_sgp = tdp / "Test_Tab_MainSgp.tsx"
        main_sgp.write_text("""
        import React from 'react';
        import { SingleGrid } from '@/components/grid';
        import { SearchBar } from '@/components/search';
        import { Test_Edit_Popup } from './Test_Edit_Popup';
        export const Test_Tab_MainSgp = () => (
            <div>
                <SearchBar />
                <SingleGrid />
                <Test_Edit_Popup />
            </div>
        );
        """, encoding="utf-8")

        res_sgp = analyze(main_sgp)
        assert res_sgp["sid"] == "SGP"
        assert res_sgp["features"]["grids"] == 1

        # 2. Button type='save' without CellEditGrid should remain SG, not CG
        main_sg = tdp / "Test_Tab_MainSg.tsx"
        main_sg.write_text("""
        import React from 'react';
        import { SingleGrid } from '@/components/grid';
        import { SearchBar } from '@/components/search';
        import { Button } from '@/components/button';
        export const Test_Tab_MainSg = () => (
            <div>
                <SearchBar extra={<Button type="save">확인</Button>} />
                <SingleGrid />
            </div>
        );
        """, encoding="utf-8")

        res_sg = analyze(main_sg)
        assert res_sg["sid"] == "SG"
        assert res_sg["features"]["editable_grid"] is False


def test_tabpage_grids_not_counted_and_custom_search_stp():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # 1. TabPage child with grids should NOT increase parent's grid count (Sms02 scenario)
        tab_page_detail = tdp / "Sms02_TabPage_Detail.tsx"
        tab_page_detail.write_text("""
        import React from 'react';
        import { SingleGrid } from '@/components/grid';
        export const Sms02_TabPage_Detail = () => (
            <div>
                <SingleGrid />
                <SingleGrid />
            </div>
        );
        """, encoding="utf-8")

        main_sms02 = tdp / "Sms02_Tab_TotalCount.tsx"
        main_sms02.write_text("""
        import React from 'react';
        import { Splitter, Checkbox } from 'antd';
        import { Button } from '@/components/button';
        import { SingleGrid } from '@/components/grid';
        import { Sms02_TabPage_Detail } from './Sms02_TabPage_Detail';

        export const Sms02_Tab_TotalCount = () => (
            <Splitter>
                <Splitter.Panel>
                    <div>
                        <Button type="search">조회</Button>
                        <Checkbox>사용고객만 보기</Checkbox>
                    </div>
                    <SingleGrid />
                </Splitter.Panel>
                <Splitter.Panel>
                    <Sms02_TabPage_Detail />
                </Splitter.Panel>
            </Splitter>
        );
        """, encoding="utf-8")

        res_sms = analyze(main_sms02)
        assert res_sms["sid"] == "GDP"
        assert res_sms["features"]["grids"] == 1
        assert res_sms["features"]["tabpage"] is True
        assert res_sms["features"]["custom_search"] is True

        # 2. Custom search row with Tabs -> STP (Tdm50 scenario)
        tab_page_check = tdp / "Tdm50_TabPage_CheckJob.tsx"
        tab_page_check.write_text("export const Tdm50_TabPage_CheckJob = () => <div />;", encoding="utf-8")

        main_tdm50 = tdp / "Tdm50_Tab_CheckJob.tsx"
        main_tdm50.write_text("""
        import React from 'react';
        import { Tabs } from 'antd';
        import { Button } from '@/components/button';
        import { QuickMoveField } from '@/components/form/QuickMoveField';
        import { Tdm50_TabPage_CheckJob } from './Tdm50_TabPage_CheckJob';

        export const Tdm50_Tab_CheckJob = () => (
            <div>
                <div>
                    <b>점검년월</b>
                    <QuickMoveField year={2026} month={10} />
                    <Button type="search">조회</Button>
                </div>
                <Tabs items={[{ key: '1', label: 'Tab 1' }]} />
                <Tdm50_TabPage_CheckJob />
            </div>
        );
        """, encoding="utf-8")

        res_tdm = analyze(main_tdm50)
        assert res_tdm["sid"] == "STP"
        assert res_tdm["features"]["custom_search"] is True
        assert res_tdm["features"]["grids"] == 0


def test_gg_vs_sgtp_tabpage_distinction():
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        # 1. Single child with a grid -> GG
        detail_grid = tdp / "Dcr30_TabPage_Company.tsx"
        detail_grid.write_text("""
        import React from 'react';
        import { MultiGrid } from '@/components/grid';
        export const Dcr30_TabPage_Company = () => <MultiGrid />;
        """, encoding="utf-8")

        main_gg = tdp / "Dcr30_Tab_LinkAdmin.tsx"
        main_gg.write_text("""
        import React from 'react';
        import { Splitter } from 'antd';
        import { SingleGrid } from '@/components/grid';
        import { Dcr30_TabPage_Company } from './Dcr30_TabPage_Company';
        export const Dcr30_Tab_LinkAdmin = () => (
            <Splitter layout="vertical">
                <SingleGrid />
                <Dcr30_TabPage_Company />
            </Splitter>
        );
        """, encoding="utf-8")

        res_gg = analyze(main_gg)
        assert res_gg["sid"] == "GG"
        assert "자식 TabPage에 그리드 포함" in res_gg["why"]

        # 2. Multiple TabPage children -> SGTP
        tab1 = tdp / "Emp00_TabPage_Tab1.tsx"
        tab1.write_text("export const Emp00_TabPage_Tab1 = () => <div />;", encoding="utf-8")
        tab2 = tdp / "Emp00_TabPage_Tab2.tsx"
        tab2.write_text("export const Emp00_TabPage_Tab2 = () => <div />;", encoding="utf-8")

        main_sgtp_multi = tdp / "Emp00_Tab_TransInfo.tsx"
        main_sgtp_multi.write_text("""
        import React from 'react';
        import { Splitter } from 'antd';
        import { SingleGrid } from '@/components/grid';
        import { Emp00_TabPage_Tab1 } from './Emp00_TabPage_Tab1';
        import { Emp00_TabPage_Tab2 } from './Emp00_TabPage_Tab2';
        export const Emp00_Tab_TransInfo = () => (
            <Splitter layout="vertical">
                <SingleGrid />
                <Emp00_TabPage_Tab1 />
                <Emp00_TabPage_Tab2 />
            </Splitter>
        );
        """, encoding="utf-8")

        res_sgtp_multi = analyze(main_sgtp_multi)
        assert res_sgtp_multi["sid"] == "SGTP"
        assert "다중 탭 전환" in res_sgtp_multi["why"]



