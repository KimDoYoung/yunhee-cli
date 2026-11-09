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
