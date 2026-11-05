from __future__ import annotations

from pathlib import Path

from yunhee.tools.analysis.callers import render as render_callers_md
from yunhee.tools.analysis.callers import resolve as resolve_callers
from yunhee.tools.api_client import format_table_tracks
from yunhee.tools.as_is.sql_checker import resolve_service_to_sql_id
from yunhee.tools.trace.gap import trace_stubs
from yunhee.tools.trace.resolve import TraceContext


def test_resolve_service_to_sql_id(tmp_path: Path) -> None:
    srv_dir = tmp_path / "myApp" / "server" / "ics"
    srv_dir.mkdir(parents=True)
    java_file = srv_dir / "Ics40_DcrPreconfirm.java"
    java_file.write_text(
        """
package myApp.server.ics;
public class Ics40_DcrPreconfirm {
    private String mapperName = "ics40_dcr_preconfirm";
    public void selectByApprId(SqlSession sqlSession, ServiceRequest request, ServiceResult result) {
        sqlSession.selectList(mapperName + ".selectByApprId", request.getParam());
    }
    public void saveMulti(SqlSession sqlSession) {
        sqlSession.insert(mapperName + ".insertOne");
        sqlSession.update(mapperName + ".updateTwo");
    }
}
""",
        encoding="utf-8",
    )

    from yunhee.tools.as_is.mybatis_render import Node, Statement

    stmts = {
        "ics40_dcr_preconfirm.selectByApprId": Statement(
            ns="ics40_dcr_preconfirm",
            sid="selectByApprId",
            kind="select",
            rel=Path("dummy.xml"),
            line=10,
            node=Node("select", {}, ["SELECT 1"]),
        ),
        "ics40_dcr_preconfirm.insertOne": Statement(
            ns="ics40_dcr_preconfirm",
            sid="insertOne",
            kind="insert",
            rel=Path("dummy.xml"),
            line=20,
            node=Node("insert", {}, ["INSERT INTO t VALUES (1)"]),
        ),
        "ics40_dcr_preconfirm.updateTwo": Statement(
            ns="ics40_dcr_preconfirm",
            sid="updateTwo",
            kind="update",
            rel=Path("dummy.xml"),
            line=30,
            node=Node("update", {}, ["UPDATE t SET a=1"]),
        ),
    }

    resolved, note, multi, cands = resolve_service_to_sql_id("ics.Ics40_DcrPreconfirm.selectByApprId", tmp_path, stmts)
    assert resolved == "ics40_dcr_preconfirm.selectByApprId"
    assert note == "서비스 ics.Ics40_DcrPreconfirm.selectByApprId → 매퍼 ics40_dcr_preconfirm.selectByApprId"
    assert multi == []
    assert cands == []

    resolved_m, _, multi_m, _ = resolve_service_to_sql_id("ics.Ics40_DcrPreconfirm.saveMulti", tmp_path, stmts)
    assert resolved_m is None
    assert "ics40_dcr_preconfirm.insertOne" in multi_m
    assert "ics40_dcr_preconfirm.updateTwo" in multi_m

    resolved_no, _, _, cands_no = resolve_service_to_sql_id("ics.Ics40_DcrPreconfirm.selectByAppr", tmp_path, stmts)
    assert resolved_no is None
    assert "ics40_dcr_preconfirm.selectByApprId" in cands_no


def test_analyze_callers_branches_and_tobe(tmp_path: Path) -> None:
    client_dir = tmp_path / "asis" / "myApp" / "client" / "vi" / "biz"
    client_dir.mkdir(parents=True)
    (client_dir / "Biz01_TabPage_List.java").write_text(
        """
package myApp.client.vi.biz;
public class Biz01_TabPage_List {
    private void openLookupTargetInfo(boolean readOnly) {
        Crm09_Lookup_SelectSingle lookup = new Crm09_Lookup_SelectSingle();
        if (readOnly) {
            lookup.view("emp", 10L);
        } else {
            lookup.open("emp", res -> {});
        }
    }
}
""",
        encoding="utf-8",
    )
    tobe_dir = tmp_path / "tobe" / "pages" / "biz"
    tobe_dir.mkdir(parents=True)
    (tobe_dir / "Biz01_TabPage_List.tsx").write_text(
        """
export const Biz01_TabPage_List = () => (
  <Crm09_Lookup_SelectSingle open={open} code="emp" onClose={() => {}} />
);
""",
        encoding="utf-8",
    )

    data = resolve_callers(
        "Crm09_Lookup_SelectSingle",
        {
            "src": tmp_path / "asis",
            "src_index": tmp_path / "index",
            "tobe": tmp_path / "tobe",
        },
    )
    rendered = render_callers_md(data)
    assert "view/open" in rendered
    assert '"emp"' in rendered
    assert "openLookupTargetInfo" in rendered
    assert 'code="emp"' in rendered


def test_trace_stubs_collects_and_excludes_normal(tmp_path: Path) -> None:
    front = tmp_path / "frontend" / "src"
    pages_emp = front / "pages" / "emp"
    pages_emp.mkdir(parents=True)
    (front / "pages" / "screens.ts").write_text(
        "export const screens = { Emp21_Tab_UnLeaveList };\n",
        encoding="utf-8",
    )
    (pages_emp / "Emp21_Tab_UnLeaveList.tsx").write_text(
        """/**
 * [1185] 연차휴가 사용촉진
 * 1단계: 하위 탭에서 문자발송은 다음 단계
 */
import { Emp21_TabPage_UnLeaveList1 } from './Emp21_TabPage_UnLeaveList1';
export const Emp21_Tab_UnLeaveList = () => <Emp21_TabPage_UnLeaveList1 />;
""",
        encoding="utf-8",
    )
    (pages_emp / "Emp21_TabPage_UnLeaveList1.tsx").write_text(
        """import { message } from 'antd';
export const Emp21_TabPage_UnLeaveList1 = () => {
  const ok = () => message.info('저장이 완료되었습니다');
  // [E13] msgBox.DialogHide [YES] → sendMessage
  const send = () => message.info('문자발송은 아직 변환 전입니다(다음 단계).');
  return null;
};
""",
        encoding="utf-8",
    )
    menus_dir = tmp_path / "docs" / "as-is"
    menus_dir.mkdir(parents=True)
    (menus_dir / "menus.tsv").write_text(
        "1185\t경영관리 > 02. 근태 > 연차휴가 사용촉진\tEmp21_Tab_UnLeaveList\ttrue\n",
        encoding="utf-8",
    )

    ctx = TraceContext(side="tobe")
    res = trace_stubs(ctx, tobe=tmp_path)
    joined = "\n".join(res.facts)
    assert "Emp21_TabPage_UnLeaveList1.tsx:5" in joined
    assert "#1185 (Emp21_Tab_UnLeaveList)" in joined
    assert "연차휴가 사용촉진 #1185 (`Emp21_Tab_UnLeaveList`)" in joined
    assert "저장이 완료되었습니다" not in joined
    assert "본문 안내 없음(머리만 남음)" in joined


def test_format_table_tracks(monkeypatch) -> None:
    before = {
        "biz05_relate_appr": {
            "schema": "public",
            "table": "biz05_relate_appr",
            "pk_cols": ["biz05_relate_appr_id"],
            "count": 40,
            "pks": {(1,), (2,)},
            "max_pks": None,
        },
        "biz02_person": {
            "schema": "public",
            "table": "biz02_person",
            "pk_cols": ["biz02_person_id"],
            "count": 10,
            "pks": {(100,)},
            "max_pks": None,
        },
    }
    after = {
        "biz05_relate_appr": {
            "schema": "public",
            "table": "biz05_relate_appr",
            "pk_cols": ["biz05_relate_appr_id"],
            "count": 41,
            "pks": {(1,), (2,), (202611059009067,)},
            "max_pks": None,
        },
        "biz02_person": {
            "schema": "public",
            "table": "biz02_person",
            "pk_cols": ["biz02_person_id"],
            "count": 10,
            "pks": {(100,)},
            "max_pks": None,
        },
    }
    monkeypatch.setattr("yunhee.tools.api_client.snapshot_tables", lambda *_a, **_kw: after)
    lines = format_table_tracks(before)
    assert lines == [
        "biz05_relate_appr: 40 → 41 (+1: biz05_relate_appr_id=202611059009067)",
        "biz02_person: 10 → 10 (변화 없음)",
    ]
