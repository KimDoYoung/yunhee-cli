import tempfile
from pathlib import Path

from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.page_style import (
    UNKNOWN,
    analyze,
    classify,
    compare_pages,
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
