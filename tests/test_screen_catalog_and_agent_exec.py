"""테스트: screen_catalog, GridCol 하위 호환성, execute_python 및 에이전트 파서 별칭."""

from dataclasses import replace

from yunhee import config
from yunhee.agent.parser import extract_tool_calls_from_text
from yunhee.agent.registry import create_default_registry
from yunhee.agent.tools.core_exec import execute_python
from yunhee.tools.trace import screen_catalog
from yunhee.tools.trace.grid_search import trace_grid
from yunhee.tools.trace.screen_catalog import (
    extract_modals_from_tsx,
    iter_screens,
    resolve_menu_info,
)
from yunhee.tools.trace.tobe import GridCol, parse_tsx


def test_grid_col_backward_compatibility_and_attributes():
    tsx_code = """
    const buildGrid = () => [
      gb.text('korNm', 100, '성명'),
      gb.boolean('orgHeadYn', 80, '조직장', { editable: true }),
      tgb.booleanYn2('mainTitleYn', 70, '본업무'),
    ];
    """
    info = parse_tsx(tsx_code, "Emp03_TabPage_Trans.tsx")
    assert len(info.grid_cols) == 3

    # 1. 기존 (field, label) 2-튜플 비교 및 언패킹 하위 호환성
    assert info.grid_cols == [
        ("korNm", "성명"),
        ("orgHeadYn", "조직장"),
        ("mainTitleYn", "본업무"),
    ]
    unpacked = [(f, lab) for f, lab in info.grid_cols]
    assert unpacked[1] == ("orgHeadYn", "조직장")

    # 2. 확장된 속성(col_type, field, label, width) 접근
    c0, c1, c2 = info.grid_cols
    assert isinstance(c1, GridCol)
    assert (c0.col_type, c0.field, c0.label, c0.width) == ("text", "korNm", "성명", 100)
    assert (c1.col_type, c1.field, c1.label, c1.width) == ("boolean", "orgHeadYn", "조직장", 80)
    assert (c2.col_type, c2.field, c2.label, c2.width) == ("booleanYn2", "mainTitleYn", "본업무", 70)


def test_extract_modals_from_tsx():
    tsx_code = """
    export const Sample = () => {
      const remove = () => {
        Modal.confirm({
          title: '삭제 확인',
          content: '정말 삭제하시겠습니까?',
        });
      };
      return (
        <div>
          <LookupModal open={open} title="계정과목" width={800} onCancel={onClose}>
            <div />
          </LookupModal>
          <Modal
            open
            title="계정코드"
            footer={<div style={{ textAlign: 'center' }}><Button>저장</Button></div>}
          >
            <div />
          </Modal>
          <EditModal title={isEdit ? '권한 수정' : '권한 등록'} open={editOpen} />
          <Modal open={howView} title={<b style={{ color: '#0069B4' }}>점검방법</b>} />
        </div>
      );
    };
    """
    modals = extract_modals_from_tsx(tsx_code)
    titles = [(m.kind, m.title) for m in modals]
    assert ("LookupModal", "계정과목") in titles
    assert ("Modal", "계정코드") in titles
    assert ("EditModal", "권한 수정") in titles
    assert ("EditModal", "권한 등록") in titles
    assert ("Modal", "점검방법") in titles
    assert ("Modal.confirm", "삭제 확인") in titles


def test_screen_catalog_default_tobe_and_reverse_menu_lookup(world):
    # Emp00_Tab_TransInfo가 하위 모달 Emp00_Lookup_AccountModal을 import하도록 추가
    lookup_tsx = """/**
     * 계정과목 선택 팝업
     */
    import { LookupModal } from '@/components/lookup/LookupModal';
    const buildGrid = () => [
      gb.boolean('orgHeadYn', 80, '조직장'),
    ];
    export const Emp00_Lookup_AccountModal = ({ target }: any) => (
      <>
        <LookupModal open title="계정과목">
          <div />
        </LookupModal>
        <EditModal open={!!target} title={target?.titleName} />
      </>
    );
    """
    lookup_path = world.tobe / "frontend/src/components/lookup/Emp00_Lookup_AccountModal.tsx"
    lookup_path.parent.mkdir(parents=True, exist_ok=True)
    lookup_path.write_text(lookup_tsx, encoding="utf-8")

    tab_path = world.tobe / "frontend/src/pages/emp/Emp00_Tab_TransInfo.tsx"
    orig_tab = tab_path.read_text(encoding="utf-8")
    tab_path.write_text(
        "import { Emp00_Lookup_AccountModal } from '@/components/lookup/Emp00_Lookup_AccountModal';\n"
        + orig_tab
        + "\n// setEditTarget({ actionCode: 'edit', titleName: '법규분류 수정' });\n"
        + "\n// <Emp00_Lookup_AccountModal />\n",
        encoding="utf-8",
    )

    screen_catalog._cached_catalog.cache_clear()

    # side 생략 시 기본값은 "tobe"
    screens = iter_screens(tobe=world.tobe, src_index=world.index)
    assert all(s.side == "tobe" for s in screens)

    by_name = {s.name: s for s in screens}
    assert "Emp00_Lookup_AccountModal" in by_name
    modal_screen = by_name["Emp00_Lookup_AccountModal"]

    # 팝업 컴포넌트가 상위 탭(Emp00_Tab_TransInfo)을 역추적하여 메뉴 번호 #1029와 메뉴명을 얻어야 함
    assert "Emp00_Tab_TransInfo" in modal_screen.opening_tabs
    assert modal_screen.menu_no == "1029"
    assert "사원정보 관리" in modal_screen.menu_path
    modal_titles = [m.title for m in modal_screen.modals]
    assert "계정과목" in modal_titles
    assert "법규분류 수정" in modal_titles
    assert modal_screen.grid_cols[0].col_type == "boolean"
    assert modal_screen.grid_cols[0].label == "조직장"

    hit_line = modal_screen.format_hit('LookupModal title="계정과목"')
    assert "#1029" in hit_line
    assert "사원정보 관리" in hit_line
    assert "Emp00_Lookup_AccountModal" in hit_line
    assert "LookupModal title=\"계정과목\"" in hit_line

    # resolve_menu_info 확인
    info = resolve_menu_info("Emp00_Lookup_AccountModal", tobe=world.tobe)
    assert info["menu_no"] == "1029"

    # trace_grid 유틸리티 동작 확인
    ctx = replace(world.ctx, side="tobe")
    res_modal = trace_grid(ctx, tobe=world.tobe, modal="계정과목")
    assert any("Emp00_Lookup_AccountModal" in f and "#1029" in f for f in res_modal.facts)

    res_col = trace_grid(ctx, tobe=world.tobe, col_type="check", label_re=r"^[가-힣]{3}$")
    assert any("orgHeadYn" in f and "조직장" in f for f in res_col.facts)


def test_execute_python_tool_and_aliases(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORK_DIR", tmp_path)

    # 1. 마크다운 코드펜스가 포함된 파이썬 코드 실행 및 yunhee import 확인
    code = """```python
from yunhee.tools.trace.tobe import GridCol
c = GridCol('fssYn', '금감원', col_type='boolean', width=70)
print(f"RESULT={c.col_type}:{c.field}:{c.label}:{c.width}")
```"""
    out = execute_python(code, description="테스트 스크립트")
    assert "Exit Code: 0" in out
    assert "RESULT=boolean:fssYn:금감원:70" in out

    # 스크립트 파일이 .yunhee/scratch/ 아래에 생성되었는지 확인
    scratch_files = list((tmp_path / ".yunhee" / "scratch").glob("agent_script_*.py"))
    assert len(scratch_files) == 1

    # 2. 문법 오류 시 STDERR 반환 확인
    err_out = execute_python("def broken(:\n    pass")
    assert "Exit Code: 1" in err_out
    assert "STDERR:" in err_out
    assert "SyntaxError" in err_out

    # 3. 파서 및 레지스트리 별칭(execute_code, run_python) 호환 확인
    reg = create_default_registry(load_mcp=False)
    assert reg.has_tool("execute_python")
    assert reg.has_tool("execute_code")
    assert reg.has_tool("run_python")

    calls = extract_tool_calls_from_text('{"name": "execute_code", "arguments": {"code": "print(123)"}}')
    assert calls == [("execute_python", {"code": "print(123)"})]
    res = reg.dispatch("execute_code", {"code": "print(42 * 2)"})
    assert "84" in res

    # 4. 코드 내부에 이스케이프되지 않은 큰따옴표(")가 섞인 비표준 JSON 구출 확인
    malformed_json = (
        '{\n'
        '  "name": "execute_python",\n'
        '  "arguments": {\n'
        '    "code": "print(f\'gb.boolean("{c.field}", "{c.label}")\')",\n'
        '    "description": "test"\n'
        '  }\n'
        '}'
    )
    rescued = extract_tool_calls_from_text(malformed_json)
    assert len(rescued) == 1
    assert rescued[0][0] == "execute_python"
    assert 'gb.boolean("{c.field}"' in rescued[0][1]["code"]


def test_tobe_rag_index_status_search_and_reset(world, monkeypatch):
    from unittest.mock import MagicMock

    from yunhee.tools.trace import tobe_rag

    monkeypatch.setattr(config, "TOBE_SRC_DIR", world.tobe)

    # In-memory fake ChromaDB collection
    store: dict[str, tuple[str, dict]] = {}
    mock_col = MagicMock()

    def _get(include=None):
        return {
            "ids": list(store.keys()),
            "metadatas": [v[1] for v in store.values()],
        }

    def _upsert(ids, documents, metadatas):
        for i, d, m in zip(ids, documents, metadatas):
            store[i] = (d, m)

    def _delete(ids):
        for i in ids:
            store.pop(i, None)

    def _query(query_texts, n_results=3):
        docs = [v[0] for v in list(store.values())[:n_results]]
        metas = [v[1] for v in list(store.values())[:n_results]]
        return {
            "documents": [docs],
            "distances": [[0.25 for _ in docs]],
            "metadatas": [metas],
        }

    mock_col.get.side_effect = _get
    mock_col.upsert.side_effect = _upsert
    mock_col.delete.side_effect = _delete
    mock_col.query.side_effect = _query
    mock_col.count.side_effect = lambda: len(store)

    monkeypatch.setattr(tobe_rag, "get_tobe_rag_collection", lambda: mock_col)
    monkeypatch.setattr(tobe_rag, "get_collection", lambda name="": mock_col)
    monkeypatch.setattr(tobe_rag, "delete_collection", lambda name: (store.clear() or True))

    # 1. 최초 rag_index: 전체 화면이 upsert 되어야 함
    res1 = tobe_rag.rag_index(tobe=world.tobe)
    assert res1["ok"] is True
    assert res1["screen_count"] >= 1
    assert res1["upserted"] == res1["screen_count"]
    assert res1["skipped"] == 0
    assert (world.tobe / ".yunhee" / "tobe_catalog.json").is_file()
    assert (world.tobe / "docs" / "to-be" / "menus.md").is_file()

    # 2. 변경 없이 2번째 rag_index: 모든 화면이 skip 되어야 함
    res2 = tobe_rag.rag_index(tobe=world.tobe)
    assert res2["upserted"] == 0
    assert res2["skipped"] == res2["screen_count"]

    # 3. rag_status 확인 (최신 상태이므로 stale_count == 0)
    st = tobe_rag.rag_status(tobe=world.tobe)
    assert st["snapshot_exists"] is True
    assert st["stale_count"] == 0

    # 4. lookup_tobe 및 prefetch_tobe_rag 확인 ("1029 화면의 파일명은?")
    looked = tobe_rag.lookup_tobe("1029", tobe=world.tobe)
    assert "#1029" in looked
    assert "Emp00_Tab_TransInfo.tsx" in looked

    prefetched = tobe_rag.prefetch_tobe_rag("1029 화면의 파일명은?", enable_vector=False)
    assert "#1029" in prefetched
    assert "Emp00_Tab_TransInfo.tsx" in prefetched

    # 5. rag_reset: 컬렉션 및 스냅샷 초기화 후 재적재 확인
    res_reset = tobe_rag.rag_reset(tobe=world.tobe, reindex=True)
    assert res_reset["reset_performed"] is True
    assert res_reset["upserted"] == res1["screen_count"]


