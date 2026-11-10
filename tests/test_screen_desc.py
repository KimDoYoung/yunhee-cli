"""screen-desc 명령어 및 파서/렌더러 단위 테스트."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.trace.screen_desc import (
    describe_screens,
    parse_screen_targets,
    render_screen_desc_json,
    render_screen_desc_md,
)

runner = CliRunner()


def test_parse_screen_targets_mixed_comma_and_space() -> None:
    raw = ["1111,2222,3333,", "4444", " #1111 , 5555 "]
    assert parse_screen_targets(raw) == ["1111", "2222", "3333", "4444", "5555"]
    assert parse_screen_targets("1002, 1029  #1085") == ["1002", "1029", "1085"]


def test_screen_desc_cli_md_and_json(tmp_path: Path) -> None:
    pages = tmp_path / "frontend" / "src" / "pages" / "sample"
    pages.mkdir(parents=True)
    (tmp_path / "frontend" / "src" / "pages" / "screens.ts").write_text(
        "export const S = { Smp01_Tab_Main };\n",
        encoding="utf-8",
    )
    (pages / "Smp01_Tab_Main.tsx").write_text(
        """/**
 * [1111] 샘플관리 > 01. 기본 > 샘플메인
 * 스타일: SGP
 */
import React from 'react';
import { Smp01_Edit_Modal } from './Smp01_Edit_Modal';
export const Smp01_Tab_Main = () => {
  const cols = [gb.text('smpCd', 100, '샘플코드')];
  return (
    <div>
      <SearchBar.Field label="검색어"><input /></SearchBar.Field>
      <Button>조회</Button>
      <Smp01_Edit_Modal />
    </div>
  );
};
""",
        encoding="utf-8",
    )
    (pages / "Smp01_Edit_Modal.tsx").write_text(
        """import React from 'react';
export const Smp01_Edit_Modal = () => (
  <EditModal title="샘플 상세 수정">
    <Button>저장</Button>
  </EditModal>
);
""",
        encoding="utf-8",
    )

    data = describe_screens(["1111,9999,", "1111"], tobe=tmp_path)
    assert data["count"] == 2
    assert data["found_count"] == 1
    first = data["screens"][0]
    assert first["screen_no"] == "1111"
    assert first["found"] is True
    assert first["tobe"]["main_screen"] == "Smp01_Tab_Main"
    assert first["tobe"]["page_style"] == "SGP"
    assert first["tobe"]["search_fields"] == ["검색어"]
    assert len(first["tobe"]["popups"]) == 1
    assert first["tobe"]["popups"][0]["name"] == "Smp01_Edit_Modal"
    assert first["tobe"]["all_modals"][0]["title"] == "샘플 상세 수정"

    md_text = render_screen_desc_md(data)
    assert "[#1111]" in md_text
    assert "Smp01_Edit_Modal" in md_text
    assert "샘플 상세 수정" in md_text

    json_text = render_screen_desc_json(data)
    parsed_json = json.loads(json_text)
    assert parsed_json["screens"][0]["tobe"]["main_screen"] == "Smp01_Tab_Main"

    # CLI 호출 검증 (쉼표 + 공백 혼합 인자 및 --format=json, --format=md)
    res_json = runner.invoke(
        app,
        ["screen-desc", "1111,9999,", "1111", "--format=json", "--tobe", str(tmp_path)],
    )
    assert res_json.exit_code == 0
    cli_obj = json.loads(res_json.stdout)
    assert cli_obj["count"] == 2
    assert cli_obj["screens"][0]["screen_no"] == "1111"

    res_md = runner.invoke(
        app,
        ["screen-desc", "1111", "--format=md", "--tobe", str(tmp_path)],
    )
    assert res_md.exit_code == 0
    assert "Smp01_Tab_Main" in res_md.stdout

    # --summary 옵션 검증
    res_summary = runner.invoke(
        app,
        ["screen-desc", "1111", "--summary", "--tobe", str(tmp_path)],
    )
    assert res_summary.exit_code == 0
    assert "Smp01_Tab_Main" in res_summary.stdout

    # --section 옵션 검증 (backend 섹션만 요청 시 TOBE 화면 구성 섹션 2는 제외)
    res_sec = runner.invoke(
        app,
        ["screen-desc", "1111", "--section", "popup", "--tobe", str(tmp_path)],
    )
    assert res_sec.exit_code == 0
    assert "3. 사용되는 팝업·모달 창" in res_sec.stdout
    assert "2. TOBE 프론트엔드 화면 구성" not in res_sec.stdout


def test_screen_desc_button_and_multigrid_parsing(tmp_path: Path) -> None:
    pages = tmp_path / "frontend" / "src" / "pages" / "multi"
    pages.mkdir(parents=True)
    (tmp_path / "frontend" / "src" / "pages" / "screens.ts").write_text(
        "export const S = { Multi01_Tab_Main };\n",
        encoding="utf-8",
    )
    (pages / "Multi01_Tab_Main.tsx").write_text(
        """/**
 * [2222] 복합그리드 > 메뉴관리
 * 스타일: TG
 */
import React from 'react';
export const Multi01_Tab_Main = () => {
  const cols01 = [gb1.text('p1', 100, '경로'), gb1.text('m1', 100, '메뉴')];
  const cols02 = [gb2.text('c1', 100, '고객'), gb2.textCenter('p2', 50, '상품')];
  return (
    <div>
      <Button type="reset" onClick={() => retrieve()}>새로고침</Button>
      <Button type="register" onClick={() => insertMenu(0)}>루트매뉴 등록</Button>
      <Button type="register" onClick={insertChildMenu}>하위매뉴 등록</Button>
      <MultiGrid columnDefs={cols01} />
      <MultiGrid columnDefs={cols02} />
    </div>
  );
};
""",
        encoding="utf-8",
    )

    data = describe_screens(["2222"], tobe=tmp_path)
    first = data["screens"][0]
    tb = first["tobe"]
    assert "새로고침" in tb["buttons"]
    assert "루트매뉴 등록" in tb["buttons"]
    assert "하위매뉴 등록" in tb["buttons"]
    assert len(tb["grid_cols"]) == 4

    md = render_screen_desc_md(data)
    assert "루트매뉴 등록" in md
    assert "하위매뉴 등록" in md

