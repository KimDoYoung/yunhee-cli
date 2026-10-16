from pathlib import Path

from typer.testing import CliRunner

from yunhee import cli
from yunhee.tools.analysis.common import count_tobe_buttons
from yunhee.tools.analysis.screen import (
    _extract_undefined_sqls,
    _format_service_rows,
    _inject_dynamic_services,
    parse_fields,
)
from yunhee.tools.analysis.ui import render as render_ui
from yunhee.tools.api_client import summarize_response
from yunhee.tools.as_is.events import extract_buttons
from yunhee.tools.log_reader import recover_mapper_name
from yunhee.tools.outliner import _outline_typescript


def test_031_1_searchbar_button_counting(tmp_path: Path):
    """031-1: <SearchBar onSearch>는 조회 버튼 1개로 집계, onReset은 무시, extra 내 Button 집계, 설정 오버라이드."""
    tobe_code = """
import React from 'react';
import SearchBar from '@/components/search/SearchBar';
import { Button } from '@/components/ui/button';

export const MyPage = () => {
    return (
        <div>
            <SearchBar
                onSearch={() => {}}
                onReset={() => {}}
                extra={<Button type="excel">엑셀다운</Button>}
            />
            <Button type="register">신규등록</Button>
        </div>
    );
};
"""
    # 1. SearchBar onSearch (+1) + extra Button (+1) + outer Button (+1) = 3개 (onReset 무시)
    btns = count_tobe_buttons(tobe_code)
    assert btns == 3

    # 2. onReset만 있는 경우 (+0)
    reset_only_code = """
<SearchBar onReset={() => {}} />
"""
    assert count_tobe_buttons(reset_only_code) == 0

    # 3. 설정 오버라이드
    custom_code = "<CustomBar />"
    cfg = {"tobe": {"components": {"CustomBar": ["search", "excel"]}}}
    assert count_tobe_buttons(custom_code, config=cfg) == 2


def test_031_2_ui_missing_events_and_no_e0():
    """031-2: analysis ui에서 AS-IS에만 있는 E-id 목록(생략·미구현 구분) 표시 및 --no-e0 지원."""
    # 모의 obj 데이터
    obj = {
        "screen": "Sys90_Tab_AfterServiceAdmin",
        "as_is": {
            "Sys90_Edit_BoardAdmin": {
                "buttons": 2,
                "events": 13,
                "grids": 1,
                "event_ids": set(range(13)),
            }
        },
        "tobe": {
            "Sys90_Edit_BoardAdmin": {
                "buttons": 2,
                "events": 11,
                "grids": 1,
                "impl_event_ids": {i for i in range(13) if i not in (6, 11)},
                "skipped_event_ids": {6},  # E6은 주석으로 생략 명시, E11은 미구현
            }
        },
        "done": "",
        "later": "",
    }

    # 기본 렌더링
    rendered = render_ui(obj, opts={})
    assert "13/11" in rendered
    assert "없음: E6(생략), E11(미구현)" in rendered

    # --no-e0 옵션 적용 시: E0 제외
    rendered_no_e0 = render_ui(obj, opts={"no_e0": True})
    assert "12/10" in rendered_no_e0
    assert "없음: E6(생략), E11(미구현)" in rendered_no_e0


def test_031_3_dynamic_sql_injection():
    """031-3: service.retrieve("..." + sql) 동적 SQL 이름 및 분기 조건 표시."""
    java_code = """
    if(checkBox01.getValue()) {
        sql = "selectByIncomplete";
    }else {
        sql = "selectByAdmin";
    }
    service.retrieve("sys.Sys90_AfterService." + sql, new InterfaceCallback() {});
    """
    initial_srv = """
| 서비스 | 호출 위치 | 서버 | SQL ID |
|:---|:---|:---|:---|
"""
    res = _inject_dynamic_services(initial_srv, java_code, "Sys90_Tab_AfterServiceAdmin")
    assert "sys.Sys90_AfterService.selectByAdmin" in res
    assert "sys.Sys90_AfterService.selectByIncomplete" in res
    assert "(동적 이름)" in res
    assert "(if (checkBox01.getValue()))" in res
    assert "sys90_after_service.selectByAdmin" in res
    assert "sys90_after_service.selectByIncomplete" in res


def test_031_4_undefined_sql_warning():
    """031-4: 매퍼에 없는 SQL 경고 태그 및 화면 상단 미정의 SQL 요약."""
    srv_text = """
| `sys.Sys27_LoginManage.updateCollapse` | Sys27_Tab_LoginManage:239 | `Sys27_LoginManage.java` | `sys27_login_manage.updateCollapse`(없음) |
"""
    formatted = _format_service_rows(srv_text)
    assert "(없음) ⚠ 매퍼에 SQL 없음 — 원본에서도 실패" in formatted

    undef_list = _extract_undefined_sqls(srv_text)
    assert undef_list == ["updateCollapse (Sys27_Tab_LoginManage:239)"]


def test_031_5_unknown_button_candidates():
    """031-5: unknown 버튼 이유 구분 및 가장 가까운 type 후보 추천."""
    code = """
    ColorButtonBottom btn1 = new ColorButtonBottom("파일등록");
    ColorButtonBottom btn2 = new ColorButtonBottom("파일관리");
    ColorButtonBottom btn3 = new ColorButtonBottom("닫기");
    ColorButtonBottom btn4 = new ColorButtonBottom("전체");
    """
    btn_map = {
        "조회": "search",
        "등록": "register",
        "파일업로드": "upload",
        "첨부파일관리": "view",
        "닫기": "close",
    }
    buttons = extract_buttons(code, btn_map=btn_map)
    jsx_list = [b.jsx for b in buttons]

    # 파일등록 -> 후보: upload (파일업로드)
    assert any('type="unknown" /* 후보: upload (파일업로드) */' in j for j in jsx_list)
    # 파일관리 -> 후보: view (첨부파일관리)
    assert any('type="unknown" /* 후보: view (첨부파일관리) */' in j for j in jsx_list)
    # 닫기 -> 바로 close로 풀림 (btn_map 또는 동의어 후보)
    assert any('type="close"' in j for j in jsx_list)
    # 전체 -> 일반 범용 문구는 후보 추천 없이 미등록 문구 이유
    assert any('type="unknown (미등록 문구)"' in j and ">전체</Button>" in j for j in jsx_list)


def test_031_6_method_called_from_overload():
    """031-6: --called-from으로 overload 자동 선택 및 위임 체인/단추/그리드 요약."""
    runner = CliRunner()
    res = runner.invoke(
        cli.app,
        ["analysis", "method", "Emp00_Lookup_SelectSingle.open", "--called-from", "Sys27_Tab_LoginManage"],
    )
    assert res.exit_code == 0
    assert "open(Long, Date, cb) L124 → open(Date, cb) L165 : 단추 확인·전체·취소, 그리드 SINGLE" in res.output


def test_031_7_screen_section_fields():
    """031-7: --section fields로 상태 필드, 초기값, 읽기/쓰기 위치 추출."""
    java_code = """
    public class Emp00_Lookup_SelectSingle {
        private Boolean isSeparateAddTitle = false;
        private Long companyId = null;
        private TextField nameField = new TextField();

        public void open(Date date, Boolean isSeparateAddTitle) {
            this.isSeparateAddTitle = isSeparateAddTitle;
        }

        public void retrieve() {
            if (isSeparateAddTitle) {
                doSomething();
            }
        }
    }
    """
    fields_str = parse_fields(java_code)
    # 위젯인 nameField는 제외
    assert "nameField" not in fields_str
    # isSeparateAddTitle 상태 필드 추출
    assert "isSeparateAddTitle Boolean = false" in fields_str
    assert "open L8 설정" in fields_str
    assert "retrieve L12 읽음" in fields_str


def test_031_8_outline_members_symbol_and_api():
    """031-8: outline --members / --symbol 필드 출력 및 API 함수 이름(인자): 반환 출력."""
    ts_code = """
export interface TransInfo {
    // 사원 식별자
    personId: number;
    transId: number;
    transDate?: string | null;
}

export const sysApi = {
    getRoles: (params: RoleReq): Promise<RoleRes[]> => axios.get('/api/roles'),
};
"""
    # 1. --symbol TransInfo
    out_sym = _outline_typescript(ts_code, symbol="TransInfo")
    joined_sym = "\n".join(out_sym)
    assert "export interface TransInfo" in joined_sym
    assert "// 사원 식별자" in joined_sym
    assert "personId: number" in joined_sym
    assert "transId: number" in joined_sym
    assert "transDate?: string | null" in joined_sym
    assert "sysApi" not in joined_sym

    # 2. API 함수 반환형 확인: 이름(인자): 반환
    out_all = _outline_typescript(ts_code)
    joined_all = "\n".join(out_all)
    assert "getRoles(params: RoleReq): Promise<RoleRes[]>" in joined_all


def test_031_9_mapper_disambiguation_and_api_404_hint():
    """031-9: namespace 약어 매퍼 식별 시 req_path로 disambiguate, 404 No static resource 시 /api 힌트."""
    # 1. 404 No static resource 힌트
    s_404 = summarize_response(
        status_code=404,
        text='{"message": "No static resource v1/sys/after-services/admin."}',
        duration_ms=50,
        path="/v1/sys/after-services/admin",
    )
    assert "💡 '/api' 접두가 필요한가요?" in s_404

    # /api로 시작하는 경우 힌트 없음
    s_ok = summarize_response(
        status_code=404,
        text='{"message": "No static resource api/v1/..."}',
        duration_ms=50,
        path="/api/v1/test",
    )
    assert "💡 '/api' 접두가 필요한가요?" not in s_ok

    # 2. req_path 기반 recover_mapper_name
    # 모의 캐시 데이터와 함께 테스트
    import yunhee.tools.log_reader as lr

    old_cache = lr._MAPPER_CACHE
    try:
        lr._MAPPER_CACHE = {
            "selectById": [
                ("SysSpecificMenuMapper", "kr.co.kfs.asseterp.biz.sys.mapper.SysSpecificMenuMapper"),
                ("SysAfterServiceMapper", "kr.co.kfs.asseterp.biz.sys.mapper.SysAfterServiceMapper"),
            ]
        }
        # req_path 없이 호출 시 모호하므로 logger_str 그대로 반환
        unresolved = recover_mapper_name("k.c.k.a.b.s.m.S.selectById", req_path="")
        assert unresolved == "k.c.k.a.b.s.m.S.selectById"

        # req_path가 after-services를 포함하면 SysAfterServiceMapper로 해소
        resolved = recover_mapper_name(
            "k.c.k.a.b.s.m.S.selectById",
            req_path="/api/v1/sys/after-services/admin",
        )
        assert resolved == "SysAfterServiceMapper.selectById"
    finally:
        lr._MAPPER_CACHE = old_cache
