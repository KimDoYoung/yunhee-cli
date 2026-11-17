"""test-gen-screen 명령어 및 정적 단계 생성기 단위 테스트."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.test.gen_screen import (
    _handler_may_warn,
    _preceding_text_label,
    _strip_comments_preserve_newlines,
    load_screen_test_rules,
    render_gen_cjs,
    run_test_gen_screen,
)

runner = CliRunner()


def _setup_mock_tobe_project(tmp_path: Path) -> Path:
    """테스트용 가상 TOBE 프로젝트 디렉터리를 구성한다."""
    pages = tmp_path / "frontend" / "src" / "pages" / "dcr"
    lookup_dir = tmp_path / "frontend" / "src" / "components" / "lookup"
    pages.mkdir(parents=True)
    lookup_dir.mkdir(parents=True)

    (tmp_path / "frontend" / "src" / "pages" / "screens.ts").write_text(
        "export const S = { Dcr10_Tab_MailHistory, Apr30_Tab_ApprStepGroup };\n",
        encoding="utf-8",
    )

    # 1. 모달 컴포넌트들
    (lookup_dir / "Fnd01_Lookup_SelectSingle.tsx").write_text(
        """import React from 'react';
export const Fnd01_Lookup_SelectSingle = ({ open, onClose }: any) => (
  <LookupModal open={open} title="연관펀드" onCancel={onClose}>
    <Button type="select">확인</Button>
  </LookupModal>
);
""",
        encoding="utf-8",
    )
    (pages / "Dcr10_Lookup_MailViwer.tsx").write_text(
        """import React from 'react';
export const Dcr10_Lookup_MailViwer = ({ mail, onClose }: any) => (
  <LookupModal open={!!mail} title="상세보기" onCancel={onClose}>
    <Button type="close">닫기</Button>
  </LookupModal>
);
""",
        encoding="utf-8",
    )

    # 2. #1023 SG 화면 (SearchBar + DateRange + 단독 Select + LookupInput + SearchBar.Input + SingleGrid + iconCell)
    (pages / "Dcr10_Tab_MailHistory.tsx").write_text(
        """/**
 * [1023] 문서작성 > 05. 메일관리 > 발신메일목록 (G14)
 * 레이아웃: 툴바 [발신일자 시작~끝][메일구분 콤보 100][연관펀드 300][검색 200 빈칸 "제목"][조회] + 그리드
 * 스타일: SG
 */
import React, { useMemo, useState } from 'react';
import { DatePicker, Select, message } from 'antd';
import { Fnd01_Lookup_SelectSingle } from '@/components/lookup/Fnd01_Lookup_SelectSingle';
import { SingleGrid, gbFor } from '@/components/grid';
import { iconCell } from '@/components/grid/iconCell';
import { SearchBar } from '@/components/search';
import { LookupInput } from '@/components/lookup/LookupInput';
import { LookupModal } from '@/components/lookup/LookupModal';
import { Dcr10_Lookup_MailViwer } from './Dcr10_Lookup_MailViwer';

const gb = gbFor<any>();

export const Dcr10_Tab_MailHistory: React.FC = () => {
  const [mailGubun, setMailGubun] = useState('전체');
  const [fundOpen, setFundOpen] = useState(false);
  const [viewing, setViewing] = useState<any>(null);
  const [docOpen, setDocOpen] = useState(false);
  const openLookupOpr = () => setFundOpen(true);

  const title = (<span>동적타이틀</span>);

  const columnDefs = useMemo(() => [
    gb.text('sendTimeString', 150, '보낸시간'),
    iconCell<any>('view', 'contentCell', 60, '내용', row => setViewing(row)),
    iconCell<any>('view', 'docCell', 60, '문서', row => {
      if (!row.aprId) {
        message.warning('해당 메일의 연관된 문서가 존재하지않습니다');
        return;
      }
      setDocOpen(true);
    }),
  ], []);

  return (
    <div>
      <SearchBar onSearch={() => {}} loading={false}>
        <SearchBar.Field label="발신일자">
          <DatePicker />
          <DatePicker />
        </SearchBar.Field>
        <Select value={mailGubun} onChange={setMailGubun} />
        <SearchBar.Field label="연관펀드">
          <LookupInput width={300} value="전체" onOpen={openLookupOpr} />
        </SearchBar.Field>
        <SearchBar.Field label="검색">
          <SearchBar.Input placeholder="제목" />
        </SearchBar.Field>
      </SearchBar>
      <SingleGrid rowData={[]} columnDefs={columnDefs} />
      <Dcr10_Lookup_MailViwer mail={viewing} onClose={() => setViewing(null)} />
      <Fnd01_Lookup_SelectSingle open={fundOpen} onClose={() => setFundOpen(false)} />
      <LookupModal open={docOpen} title={title} onCancel={() => setDocOpen(false)} />
    </div>
  );
};
""",
        encoding="utf-8",
    )

    # 3. #1282 GDP 화면 (메인 Tab + 하위 Page, 동일 버튼 글자 '조회'·'등록'·'저장'·'삭제' 및 조건부·type 없는 버튼 검증)
    apr_dir = tmp_path / "frontend" / "src" / "pages" / "apr"
    apr_dir.mkdir(parents=True)
    (apr_dir / "Apr31_Page_ApprStepGroupMember.tsx").write_text(
        """import React, { useState } from 'react';
import { Button } from '@/components/button';
import { MultiGrid } from '@/components/grid';
import { Fnd01_Lookup_SelectSingle } from '@/components/lookup/Fnd01_Lookup_SelectSingle';

export const Apr31_Page_ApprStepGroupMember: React.FC<{ apprStepGroupId: number | null }> = () => {
  const [pickOpen, setPickOpen] = useState(false);
  return (
    <div>
      <Button type="search" onClick={() => {}}>조회</Button>
      <Button type="register" onClick={() => setPickOpen(true)}>등록</Button>
      <Button type="save" onClick={() => {}}>저장</Button>
      <Button type="delete" onClick={() => {}}>삭제</Button>
      <MultiGrid rowData={[]} columnDefs={[]} />
      <Fnd01_Lookup_SelectSingle open={pickOpen} onClose={() => setPickOpen(false)} />
    </div>
  );
};
""",
        encoding="utf-8",
    )
    (apr_dir / "Apr30_Tab_ApprStepGroup.tsx").write_text(
        """/**
 * [1282] 관리자 > 03. 문서관리 > 문서결재선 그룹관리
 * 스타일: GDP
 */
import React, { useState } from 'react';
import { Button } from '@/components/button';
import { CellEditGrid } from '@/components/grid';
import { Apr31_Page_ApprStepGroupMember } from './Apr31_Page_ApprStepGroupMember';

export const Apr30_Tab_ApprStepGroup: React.FC = () => {
  const [isAdmin] = useState(false);
  return (
    <div>
      <Button type="search" onClick={() => {}}>조회</Button>
      <Button type="register" onClick={() => {}}>등록</Button>
      <Button type="save" onClick={() => {}}>저장</Button>
      <Button type="delete" onClick={() => {}}>삭제</Button>
      {isAdmin && <Button type="primary" onClick={() => {}}>관리자전용</Button>}
      <Button onClick={() => {}} />
      <CellEditGrid crud={{} as any} columnDefs={[]} />
      <Apr31_Page_ApprStepGroupMember apprStepGroupId={1} />
    </div>
  );
};
""",
        encoding="utf-8",
    )
    return tmp_path


def test_gen_screen_searchbar_and_steps(tmp_path: Path) -> None:
    tobe_root = _setup_mock_tobe_project(tmp_path)
    out_dir = tmp_path / "gen"

    res = run_test_gen_screen(
        targets=["1023"],
        target_dir=out_dir,
        tobe=tobe_root,
    )
    assert res.ok
    items = res.data["items"]
    assert len(items) == 1
    item = items[0]
    assert item.screen_no == "1023"
    assert item.sid == "SG"
    assert len(item.unknown) == 2
    assert item.unknown[0]["reason"] == "label 없음 — 위치로 대신"
    assert item.unknown[1]["reason"] == "모달 제목이 동적 — expectModal:true"

    by_id = {s["id"]: s for s in item.steps}
    assert "open" in by_id
    # 9.1절: SearchBar onSearch -> click:조회 (via="SearchBar")
    search_step = by_id["Dcr10_Tab_MailHistory/click:조회"]
    assert search_step["do"] == "click"
    assert search_step["button"] == "조회"
    assert search_step["type"] == "search"
    assert search_step["via"] == "SearchBar"
    assert "danger" not in search_step

    # 9.1절 & 071: 발신일자(dateRange), 메일구분(selectEach 위치 기반 #1), 연관펀드(lookup), 제목(fill:text)
    date_step = by_id["Dcr10_Tab_MailHistory/fill:발신일자"]
    assert date_step["kind"] == "dateRange"
    assert date_step["then"] == "Dcr10_Tab_MailHistory/click:조회"

    combo_step = by_id["Dcr10_Tab_MailHistory/selectEach:#1"]
    assert combo_step["do"] == "selectEach"
    assert combo_step["in"] == "SearchBar"
    assert combo_step["index"] == 1
    assert combo_step["then"] == "Dcr10_Tab_MailHistory/click:조회"

    lookup_step = by_id["Dcr10_Tab_MailHistory/lookup:연관펀드"]
    assert lookup_step["expectModal"] == "연관펀드"
    assert lookup_step["via"] == "LookupInput"

    title_step = by_id["Dcr10_Tab_MailHistory/fill:제목"]
    assert title_step["kind"] == "text"
    assert title_step["then"] == "Dcr10_Tab_MailHistory/click:조회"

    assert by_id["Dcr10_Tab_MailHistory/rowClick:0"]["grid"] == 0
    assert by_id["Dcr10_Tab_MailHistory/cellIcon:0.내용"]["expectModal"] == "상세보기"

    doc_step = by_id["Dcr10_Tab_MailHistory/cellIcon:0.문서"]
    assert doc_step["expectModal"] is True
    assert doc_step["mayWarn"] is True

    gen_file = out_dir / "screen-test-1023.gen.cjs"
    assert gen_file.is_file()
    cjs_text = gen_file.read_text(encoding="utf-8")
    assert "module.exports = {" in cjs_text
    assert 'screenNo: "1023"' in cjs_text
    # 072: index 세는 규칙을 머리 주석에 적는다(index 단계가 있을 때만)
    assert "// index: 컨테이너(in) 안 최상위 입력 칸 순서(0부터)" in cjs_text


def test_gen_screen_component_scope_danger_and_overwrite(tmp_path: Path) -> None:
    tobe_root = _setup_mock_tobe_project(tmp_path)
    out_dir = tmp_path / "gen"

    res = run_test_gen_screen(
        targets=["1282"],
        target_dir=out_dir,
        tobe=tobe_root,
    )
    assert res.ok
    item = res.data["items"][0]
    by_id = {s["id"]: s for s in item.steps}

    # 9.2절: 메인 컴포넌트와 하위 Page의 동일 버튼 글자가 컴포넌트 범위로 격리됨
    assert "Apr30_Tab_ApprStepGroup/click:조회" in by_id
    assert "Apr31_Page_ApprStepGroupMember/click:조회" in by_id
    assert by_id["Apr30_Tab_ApprStepGroup/rowClick:0"]["grid"] == 0
    assert by_id["Apr31_Page_ApprStepGroupMember/rowClick:1"]["grid"] == 1

    # 8절 결정 1·2·3: 위험 type, AntD primary(type 없음 취급), 조건부, 모달 여는 위험 버튼, 글자 없는 버튼 unknown
    reg_sub = by_id["Apr31_Page_ApprStepGroupMember/click:등록"]
    assert reg_sub["danger"] is True
    assert reg_sub["enabled"] is False
    assert reg_sub["expectModal"] == "연관펀드"

    cond_btn = by_id["Apr30_Tab_ApprStepGroup/click:관리자전용"]
    assert cond_btn["danger"] is True
    assert cond_btn["enabled"] is False
    assert cond_btn["conditional"] is True
    assert "type" not in cond_btn  # AntD primary는 button-types가 아니므로 제외

    # 글자 없는 버튼은 unknown에 기록
    assert len(item.unknown) == 1
    assert "버튼 글자·라벨 없음" in item.unknown[0]["reason"]

    # 두 번째 실행 시 동일 내용이면 unchanged, --force 시 forced
    res2 = run_test_gen_screen(targets=["1282"], target_dir=out_dir, tobe=tobe_root)
    assert res2.data["items"][0].status == "unchanged"

    res3 = run_test_gen_screen(targets=["1282"], target_dir=out_dir, tobe=tobe_root, force=True)
    assert res3.data["items"][0].status == "forced"

    # CLI --stdout 및 복수 화면 인자 테스트
    cli_res = runner.invoke(
        app,
        ["test-gen-screen", "1023,1282", "--tobe", str(tobe_root), "--stdout"],
    )
    assert cli_res.exit_code == 0
    assert 'screenNo: "1023"' in cli_res.stdout
    assert 'screenNo: "1282"' in cli_res.stdout
    assert render_gen_cjs(item).strip() in cli_res.stdout


def test_load_screen_test_rules_defaults(tmp_path: Path) -> None:
    rules = load_screen_test_rules(tmp_path)
    assert "search" in rules.safe_button_types
    assert "goto" in rules.safe_button_types
    assert "save" in rules.danger_button_types
    assert "addRow" in rules.danger_button_types
    assert "bookmark" in rules.danger_button_types
    assert not rules.is_safe_button_type("primary")
    assert not rules.is_safe_button_type(None)


def test_may_warn_excludes_error_072() -> None:
    """072: mayWarn은 warning·info만. message.error는 실제 실패라 넣지 않는다."""
    assert _handler_may_warn("() => message.warning('선택된 행이 없습니다')", {}) is True
    assert _handler_may_warn("() => message.info('x')", {}) is True
    assert _handler_may_warn("() => Modal.warning({ title: 'x' })", {}) is True
    assert _handler_may_warn("() => void createRdExcel()", {"createRdExcel": "try {} catch (e) { message.error('다운로드 실패') }"}) is False
    assert _handler_may_warn("() => Modal.error({ title: 'x' })", {}) is False


def test_preceding_text_label_072() -> None:
    """072: 컨트롤 바로 앞에 화면에 보이는 글자(Typography.Text 등)를 label로. 주석은 쓰지 않는다."""
    jsx = (
        "<Space wrap>\n"
        "  <Typography.Text strong>적용상품</Typography.Text>\n"
        "  {/* [E1] erpProductComboBox 처음 \"전체\" */}\n"
        "  <SystemCodeComboBox kindCd=\"ErpProductCode\" />\n"
        "</Space>"
    )
    clean = _strip_comments_preserve_newlines(jsx)
    assert _preceding_text_label(clean, clean.index("<SystemCodeComboBox")) == "적용상품"
    # 앞에 다른 컨트롤이 끼어 있으면 쓰지 않는다
    jsx2 = "<span>기준일</span><DatePicker /><Select />"
    assert _preceding_text_label(jsx2, jsx2.index("<Select")) is None
    # 주석만 있으면 label 없음
    jsx3 = _strip_comments_preserve_newlines("<Space>{/* 메일구분 */}<Select /></Space>")
    assert _preceding_text_label(jsx3, jsx3.index("<Select")) is None
