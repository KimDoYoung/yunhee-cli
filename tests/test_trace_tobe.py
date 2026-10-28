"""TOBE 호출 체인·AS-IS 주석 색인(tools/trace/tobe.py)."""

from pathlib import Path

from yunhee.tools.trace.tobe import (
    build_index,
    event_ids,
    find_layout,
    normalize_url,
    parse_api_ts,
    parse_controller,
    parse_mapper_xml,
    parse_service,
    parse_tsx,
)


def test_normalize_url():
    assert normalize_url("v1/emp/trans-infos") == "/api/v1/emp/trans-infos"
    assert normalize_url("v1/emp/persons/${id}/trans?x=1") == "/api/v1/emp/persons/{}/trans"
    assert normalize_url("/api/v1/x/{id}") == "/api/v1/x/{}"


def test_event_ids_follow_021_rules():
    text = "// [E0] a\n// [E4]\n// [E4] 중복\n// [E5]~[E7] 범위\n// [E1]~[E3 생략] 생략 범위\n// [E9 생략]\n"
    impl, skip = event_ids(text)
    assert impl == {"E0", "E4", "E5", "E6", "E7"}
    assert skip == {"E1", "E2", "E3", "E9"}
    assert event_ids("[E1 생략] [E1]")[1] == set()  # 같은 번호가 구현에도 있으면 구현


def test_parse_api_ts(world):
    fns = parse_api_ts((world.tobe / "frontend/src/api/emp.ts").read_text(), "emp.ts")
    by = {f.name: f for f in fns}
    assert (by["searchTransInfos"].verb, by["searchTransInfos"].url) == ("GET", "/api/v1/emp/trans-infos")
    assert by["searchTransInfos"].keys == ["emp.Emp00_TransInfo.selectByText"]
    assert by["brandNew"].url == "/api/v1/emp/brand/{}" and by["brandNew"].keys == []


def test_parse_controller_joins_prefix_and_collects_calls(world):
    eps = parse_controller((world.tobe / "backend/src/main/java/x/EmpTransInfoController.java").read_text(), "C.java")
    by = {e.method: e for e in eps}
    assert (by["searchTransInfos"].verb, by["searchTransInfos"].path) == ("GET", "/api/v1/emp/trans-infos")
    assert by["searchTransInfos"].keys == ["emp.Emp00_TransInfo.selectByText"]
    assert by["searchTransInfos"].service_calls == [("empTransInfoService", "searchTransInfos")]
    assert by["brand"].path == "/api/v1/emp/brand/{}" and by["brand"].keys == []


def test_service_key_ignores_korean_particles():
    eps = parse_controller(
        'package x;\n@RequestMapping("/api/v1/a")\npublic class A {\n  /** AS-IS emp.Emp00_TransInfo.selectByText의 변형 */\n  @GetMapping("/x")\n  public R get() { return null; }\n}\n', "A.java"
    )
    assert eps[0].keys == ["emp.Emp00_TransInfo.selectByText"]


def test_parse_service_and_mapper_xml(world):
    svc = parse_service((world.tobe / "backend/src/main/java/x/EmpTransInfoService.java").read_text(), "S.java")
    assert svc[0].name == "searchTransInfos" and svc[0].mapper_calls == [("empTransInfoMapper", "searchTransInfos")]
    xml = (world.tobe / "backend/src/main/resources/mapper/EmpTransInfoMapper.xml").read_text()
    stmts, asis_ns, header_ids = parse_mapper_xml(xml, "M.xml")
    by = {s.id: s for s in stmts}
    assert asis_ns == "emp00_trans_info" and header_ids == ["selectByText"]
    assert by["searchTransInfos"].as_is_ids == ["emp00_trans_info.selectByText"]
    assert by["untracked"].as_is_ids == []  # AS-IS를 말하지 않는 주석의 `t2.emp03_trans_id`는 SQL id가 아니다


def test_parse_tsx(world):
    t = parse_tsx((world.tobe / "frontend/src/pages/emp/Emp00_Tab_TransInfo.tsx").read_text(), "Emp00_Tab_TransInfo.tsx")
    assert t.header_menu_nos == ["1029"] and t.as_is_file.endswith("Emp00_Tab_TransInfo.java")
    assert t.api_calls == [("empApi", "searchTransInfos")]
    assert t.grid_cols == [("korNm", "성명"), ("hireDate", "입사일"), ("newCol", "신규")]
    assert "엑셀" in t.buttons and "조회" in t.buttons  # <Button> 글자 + 이벤트 주석의 버튼 라벨
    assert t.impl_events == {"E0", "E1"}


def test_find_layout_accepts_root_or_frontend_src(world):
    assert find_layout(world.tobe).pages_dir == world.tobe / "frontend/src/pages"
    assert find_layout(world.tobe / "frontend" / "src").root == world.tobe
    assert not find_layout(world.tobe / "nothing").usable


def test_build_index_chain_from_endpoint_to_statement(world):
    idx = build_index(str(world.tobe))
    assert set(idx.tsx) == {"Emp00_Tab_TransInfo", "Emp77_Tab_Brand"}
    fn = idx.api_fns[("empApi", "searchTransInfos")]
    ep = idx.endpoint_of(fn)[0]
    assert [s.id for s in idx.statements_of(ep)] == ["searchTransInfos"]
    assert idx.endpoints_for_key("emp.Emp00_TransInfo.selectByText") == [ep]
    assert idx.rel(world.tobe / "frontend/src/api/emp.ts") == "frontend/src/api/emp.ts"
    assert Path(idx.mapper_files["x.EmpTransInfoMapper"]).name == "EmpTransInfoMapper.xml"
