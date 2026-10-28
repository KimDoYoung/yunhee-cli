"""수정사항 044 (22~26번 및 3~8번) 검증 테스트."""

import json
import sys
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
from tools.hook_guard import inspect_command
from yunhee.tools.analysis.grid import resolve as resolve_grid
from yunhee.tools.analysis.method import resolve as resolve_method
from yunhee.tools.analysis.ui import resolve as resolve_ui
from yunhee.tools.as_is.events import extract_events_and_methods
from yunhee.tools.as_is.mybatis_render import (
    _strip_type_prefix,
    eval_test_condition,
)
from yunhee.tools.as_is.sql_checker import check_tobe_sql
from yunhee.tools.as_is.sql_porter import port_sql
from yunhee.tools.base import ToolResult
from yunhee.tools.comparator import _field_covered, compare_api_sql
from yunhee.tools.sql_runner import run_sql


def test_044_22_toggle_group_reachability():
    """Item 22 (a): ToggleGroup에 add된 라디오가 툴바에 연결되면 도달 가능 판정."""
    java_src = """
    public class Emp20_Tab_YearList extends ContentPanel {
        private ToggleGroup toggleMonthStdDateType = new ToggleGroup();
        private Radio radioNow = new Radio();
        private Radio radioYear = new Radio();

        public Emp20_Tab_YearList() {
            toggleMonthStdDateType.add(radioNow);
            toggleMonthStdDateType.add(radioYear);

            HorizontalLayoutContainer hlc = new HorizontalLayoutContainer();
            hlc.add(radioNow);
            hlc.add(radioYear);
            this.add(hlc);

            toggleMonthStdDateType.addValueChangeHandler(new ValueChangeHandler<HasValue<Boolean>>() {
                @Override
                public void onValueChange(ValueChangeEvent<HasValue<Boolean>> event) {
                    retrieve();
                }
            });
        }

        public void retrieve() {
        }
    }
    """
    events, _methods = extract_events_and_methods(java_src, "Emp20_Tab_YearList.java")
    e1 = next((e for e in events if e.id == "E1"), None)
    assert e1 is not None
    assert not e1.is_unreachable, f"E1 should be reachable, but was marked unreachable: {e1.unreachable_reason}"


def test_044_22_lookup_open_entrypoint_reachability():
    """Item 22 (b): Lookup/Dialog 클래스의 open()은 entrypoint이므로 미도달/도달 불가로 오판하지 않음."""
    java_src = """
    public class Emp21_Lookup_Insert extends Window {
        public Emp21_Lookup_Insert() {
            TextButton btnCreate = new TextButton("생성");
            btnCreate.addSelectHandler(new SelectHandler() {
                @Override
                public void onSelect(SelectEvent event) {
                    createData();
                }
            });
            buttonBar.add(btnCreate);
        }

        public void open(String name, InterfaceCallback callback) {
            this.show();
        }

        private void createData() {
        }
    }
    """
    events, _methods = extract_events_and_methods(java_src, "Emp21_Lookup_Insert.java")
    e1 = next((e for e in events if e.id == "E1"), None)
    assert e1 is not None
    assert not e1.is_unreachable, f"E1 should be reachable: {e1.unreachable_reason}"


def test_044_23_ui_tobe_missing_path_error(tmp_path: Path):
    """Item 23: --tobe 경로가 존재하지 않으면 침묵하지 않고 명시적 오류 발생."""
    screens_dir = tmp_path / "emp" / "screens"
    screens_dir.mkdir(parents=True)
    screen_md = screens_dir / "Emp21_Tab_UnLeaveList.md"
    screen_md.write_text("# Emp21_Tab_UnLeaveList\n## UI\n- 버튼: [생성]\n", encoding="utf-8")
    with pytest.raises(ValueError, match=r"\[ERROR\] --tobe 경로를 찾을 수 없습니다"):
        resolve_ui("Emp21_Tab_UnLeaveList", {"tobe": "non_existent_folder/page.tsx", "src_index": tmp_path})


def test_044_24_sql_check_single_file_and_only_candidate(tmp_path: Path):
    """Item 24: sql-check --tobe 파일 경로 직접 지정 및 --only 후보 제시."""
    mapper_file = tmp_path / "EmpYearLeaveMapper.xml"
    mapper_file.write_text("""<?xml version="1.0" encoding="UTF-8" ?>
    <!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
    <mapper namespace="kr.co.kfs.asseterp.biz.emp.mapper.EmpYearLeaveMapper">
        <select id="selectCount" resultType="int">
            SELECT count(*) FROM sys01_company
        </select>
    </mapper>
    """, encoding="utf-8")

    # 1. 단일 파일 검증
    with mock.patch("yunhee.tools.as_is.sql_checker.explain", return_value=None):
        res = check_tobe_sql(mapper_file)
        assert res.ok
        assert res.data["total"] == 1

    # 2. --only 불일치 시 후보 제시
    res_only = check_tobe_sql(mapper_file, only=["NonExistent"])
    assert not res_only.ok
    assert "일치하는 매퍼가 없습니다" in res_only.error
    assert "EmpYearLeaveMapper" in res_only.error


def test_044_25_port_sql_raw(tmp_path: Path):
    """Item 25: port-sql --raw 원본 CDATA 추출, :param -> #{param} 치환, SELECT * + JOIN 경고, --insert-into 생성."""
    xml_content = """<?xml version="1.0" encoding="UTF-8" ?>
    <!DOCTYPE mapper PUBLIC "-//mybatis.org//DTD Mapper 3.0//EN" "http://mybatis.org/dtd/mybatis-3-mapper.dtd">
    <mapper namespace="emp01_person">
        <select id="selectRawSample" parameterType="HashMap" resultType="HashMap">
            SELECT *
              FROM emp01_person
              JOIN emp02_others ON emp02_person_id = emp01_person_id
             WHERE emp01_company_id = :companyId
               AND emp01_hire_date::date &lt;= :stdDate
        </select>
    </mapper>
    """
    mapper_dir = tmp_path / "mapper"
    mapper_dir.mkdir()
    (mapper_dir / "emp01_person.xml").write_text(xml_content, encoding="utf-8")

    res = port_sql(
        "emp01_person.selectRawSample",
        src_root=tmp_path,
        raw=True,
        insert_into="sys99_print",
        insert_cols="sys99_print_id=nextval('seq'),sys99_company_id=#{companyId},emp_id",
    )
    assert res.ok
    output = res.data["output"]
    assert '<sql id="selectRawSample">' in output
    assert "<![CDATA[" in output
    assert "#{companyId}" in output
    assert "#{stdDate}" in output
    assert "::date" in output  # ::cast 보존
    assert "SELECT *와 JOIN이 함께 사용되어" in res.data["warnings"][0]
    assert '<insert id="insertPrint">' in output
    assert "sys99_print_id" in output
    assert "y.emp_id" in output


def test_044_26_sql_scalar():
    """Item 26: sql --scalar 결과 첫 행 첫 열 값만 단일 문자열 출력."""
    with mock.patch("yunhee.tools.sql_runner.psycopg.connect") as mock_conn:
        mock_cursor = mock.MagicMock()
        col_mock = mock.MagicMock()
        col_mock.name = "cnt"
        mock_cursor.description = [col_mock]
        mock_cursor.fetchall.return_value = [(42,)]
        mock_conn.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        res = run_sql("SELECT count(*) FROM sys01_company", scalar=True)
        assert res.ok
        assert res.data["summary"] == "42"
        assert res.data["scalar"] == "42"


def test_044_3_boolean_type_prefix():
    """Item 3: b:true, b:false 접두사 처리 및 불리언 분기 평가."""
    pfx, val = _strip_type_prefix("b:true")
    assert pfx == "b"
    assert val is True

    pfx_f, val_f = _strip_type_prefix("b:false")
    assert pfx_f == "b"
    assert val_f is False

    # 분기 평가: endCheck != true
    res_t = eval_test_condition("endCheck != true", {"endCheck": "b:true"})
    assert not res_t, "When endCheck=b:true, endCheck != true should be False"

    res_f = eval_test_condition("endCheck != true", {"endCheck": "b:false"})
    assert res_f, "When endCheck=b:false, endCheck != true should be True"


def test_044_4_field_covered_fullname_and_grid_property():
    """Item 4: FullName <-> FNm 변형 커버 및 grid 프로퍼티 보존."""
    assert _field_covered("classTreeFullName", {"classTreeFullName"})
    assert _field_covered("classTreeFNm", {"classTreeFullName"})
    assert _field_covered("classTreeFullName", {"classTreeFNm"})
    assert _field_covered("linkCode", {"linkCd"})


def test_044_5_compare_scalar_count():
    """Item 5: compare 건수 단일 스칼라 SQL 대조."""
    with mock.patch("yunhee.tools.comparator.request_api") as mock_api, \
         mock.patch("yunhee.tools.as_is.mybatis_render.render_with_meta") as mock_render, \
         mock.patch("yunhee.tools.comparator.find_screen_grid_info") as mock_grid, \
         mock.patch("yunhee.tools.comparator.psycopg.connect") as mock_conn:
        mock_api.return_value = ToolResult(
            ok=True,
            data={"status": 200, "text": json.dumps({"success": True, "data": {"total": 12, "rows": [{"id": 1}]}})},
        )
        mock_render.return_value = ("SELECT count(*) FROM bbs02_notice", [], [])
        mock_grid.return_value = {"cols": set(), "label": "", "not_found": False}
        mock_cursor = mock.MagicMock()
        mock_cursor.fetchall.return_value = [(12,)]
        mock_cursor.description = [("count",)]
        mock_conn.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = mock_cursor

        res = compare_api_sql("GET", "/api/v1/bbs/notices", "sys04_role.selectByName")
        assert res.ok
        assert res.data["rows_match"]
        assert "API total=12, SQL count=12 ✅" in res.data["summary"]


def test_044_6_analysis_method_all_overloads(tmp_path: Path):
    """Item 6: analysis method --all-overloads 오버로드 일괄 출력."""
    java_file = tmp_path / "Dcr30_Lookup_Link.java"
    java_file.write_text("""
    public class Dcr30_Lookup_Link {
        public void open(InterfaceCallback callback) {
            insertCheck();
        }
        public void open(String linkCodeList, InterfaceCallback callback) {
            insertCheck();
        }
    }
    """, encoding="utf-8")

    res = resolve_method("Dcr30_Lookup_Link.open", {"src": tmp_path, "all_overloads": True})
    assert "multi_methods" in res
    assert len(res["multi_methods"]) == 2


def test_044_7_analysis_grid_my_text_area(tmp_path: Path):
    """Item 7: addTextArea(..., new MyTextArea()) -> editor_kind: largeText."""
    java_file = tmp_path / "Emp01_Tab.java"
    java_file.write_text("""
    public class Emp01_Tab {
        public void buildGrid() {
            GridBuilder<Emp01_Model> gb = new GridBuilder<Emp01_Model>();
            gb.addTextArea(properties.addTitle(), 250, "겸직사항", new MyTextArea());
            gb.addTextArea(properties.note(), 200, "비고");
        }
    }
    """, encoding="utf-8")

    res = resolve_grid("Emp01_Tab", {"src": tmp_path})
    cols = res["columns"]
    # cols[0] is rowNumberer
    assert cols[1]["editor"] == "largeText"
    assert cols[2]["editor"] is None  # read-only addTextArea


def test_044_8_hook_guard_cat_hint():
    """Item 8: 훅 차단 안내에 yunhee cat 파일:범위 최우선 제시."""
    blocked, _trigger, reason = inspect_command("cat backend/src/main/java/Foo.java")
    assert blocked
    assert "yunhee cat <파일>:<시작>-<끝>" in reason
