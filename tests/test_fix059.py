"""수정사항 059 관련 단위 테스트 모음.

수용 기준 7가지 검증:
1. §1: 팝업/모달에 가려진 본 화면(area: main) 요소가 수집에서 배제됨 (isElementCovered).
2. §2: 레이어(main vs modal) 단위로 요소 이름 번호가 독립 부여되어 캡처 방식 간 이름 일관성 유지.
3. §3: 아이콘 컬럼 헤더/셀 이름 ID 매핑 (__rownum -> 번호, ag-Grid-SelectionColumn -> 선택, 왼쪽 헤더 결합).
4. §4: 행 선택 체크박스는 grid1.행1.선택, 값 체크박스는 컬럼 이름, 크기 16x16 정합성.
5. §5: mark에서 지원되지 않는 type은 오류 + difflib 후보 추천.
6. §6: 팝업 안 체크박스 Form.Item 라벨 취득 및 모달 이름과 폼 요소 라벨 충돌 방지.
7. §7: mark에서 anchor: outside-* 지원 및 gap 간격 배치.
"""

import pytest
from playwright.sync_api import sync_playwright

from yunhee.tools.marker import compute_anchor_point, resolve_draw_items
from yunhee.tools.screen_capture import COLLECT_BOXES_JS

MOCK_FIX059_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body { margin: 0; padding: 20px; font-family: sans-serif; }
  .btn { display: inline-block; padding: 6px 12px; border: 1px solid #ccc; cursor: pointer; }
  .grid-header-cell { display: inline-block; width: 80px; height: 30px; border: 1px solid #ddd; }
  .grid-cell { display: inline-block; width: 80px; height: 30px; border: 1px solid #eee; }
  .modal-mask {
    position: fixed; top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(0,0,0,0.5); z-index: 1000;
  }
  .modal-wrap {
    position: fixed; top: 50px; left: 100px; width: 500px; height: 350px;
    background: #fff; z-index: 1001; padding: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.15);
  }
  .ant-form-item { margin-bottom: 12px; display: flex; align-items: center; }
  .ant-form-item-label { width: 100px; }
  .ant-checkbox-wrapper { display: inline-flex; align-items: center; cursor: pointer; }
  .ant-checkbox-inner { width: 16px; height: 16px; border: 1px solid #d9d9d9; display: inline-block; }
  .ant-checkbox-input { width: 16px; height: 16px; }
</style>
</head>
<body>

  <!-- 본 화면 (모달 마스크 뒤에 가려짐) -->
  <div id="main-content">
    <button id="main-search-btn" class="btn">조회</button>
    <button id="main-reg-btn" class="btn">등록</button>
    
    <!-- 본 화면의 그리드 -->
    <div id="grid1" class="ag-root" style="width: 600px; height: 200px; margin-top: 20px;">
      <!-- 헤더 -->
      <div class="ag-header-row">
        <div class="ag-header-cell grid-header-cell" col-id="__rownum"></div>
        <div class="ag-header-cell grid-header-cell" col-id="ag-Grid-SelectionColumn"></div>
        <div class="ag-header-cell grid-header-cell" col-id="col_detail_title"><span class="ag-header-cell-text">세부내용</span></div>
        <div class="ag-header-cell grid-header-cell" col-id="editDetail"></div>
        <div class="ag-header-cell grid-header-cell" col-id="commonDuty"><span class="ag-header-cell-text">공통책무</span></div>
      </div>
      <!-- 행 1 -->
      <div class="ag-row" row-index="0" style="height: 30px;">
        <div class="ag-cell grid-cell" col-id="__rownum">1</div>
        <div class="ag-cell grid-cell" col-id="ag-Grid-SelectionColumn">
          <input type="checkbox" class="ag-input-field-input" style="width: 16px; height: 16px;" />
        </div>
        <div class="ag-cell grid-cell" col-id="col_detail_title">경영기획</div>
        <div class="ag-cell grid-cell" col-id="editDetail"><span class="anticon anticon-edit" title="수정"></span></div>
        <div class="ag-cell grid-cell" col-id="commonDuty">
          <label class="ant-checkbox-wrapper">
            <span class="ant-checkbox"><span class="ant-checkbox-inner"></span></span>
          </label>
        </div>
      </div>
    </div>
  </div>

  <!-- 모달 창 및 배경 어두운 막 -->
  <div class="ant-modal-mask modal-mask"></div>
  <div class="ant-modal-wrap">
    <div class="ant-modal-content modal-wrap">
      <div class="ant-modal-title" style="font-size: 18px; font-weight: bold; margin-bottom: 16px;">책무</div>
      
      <!-- 폼 아이템: Form.Item 라벨과 텍스트영역 -->
      <div class="ant-form-item">
        <label class="ant-form-item-label">책무</label>
        <textarea class="ant-input" style="width: 200px; height: 60px;"></textarea>
      </div>

      <!-- 폼 아이템: Form.Item 라벨과 체크박스 -->
      <div class="ant-form-item">
        <label class="ant-form-item-label">공통책무</label>
        <label class="ant-checkbox-wrapper">
          <span class="ant-checkbox"><span class="ant-checkbox-inner"></span></span>
        </label>
      </div>

      <!-- 모달 내부 버튼 -->
      <div style="margin-top: 20px;">
        <button class="btn ant-btn-primary">저장</button>
        <button class="btn">닫기</button>
      </div>
    </div>
  </div>

</body>
</html>
"""


def test_fix059_covered_elements_and_modal_isolation():
    """§1, §2, §6: 모달에 가려진 본 화면 요소 배제 및 레이어 격리, 모달 이름 충돌 방지 검증."""
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_content(MOCK_FIX059_HTML)

        res = page.evaluate(COLLECT_BOXES_JS, None)
        elements = res["elements"]
        names = [e["name"] for e in elements]

        # 1. §1 검증: 모달 마스크 뒤에 완전히 가려진 본 화면 버튼('조회', '등록')은 제외되어야 함
        assert "조회" not in names
        assert "등록" not in names

        # 2. §6 모달 이름 검증: 모달 창 이름은 '책무(모달)' 형태여야 함
        modal_elem = next(e for e in elements if e["kind"] == "modal")
        assert modal_elem["name"] == "책무(모달)"

        # 3. §6 텍스트영역 검증: textarea는 Form.Item 라벨인 '책무'를 이름으로 취득
        textarea_elem = next(e for e in elements if e["kind"] == "input" and e["name"] == "책무")
        assert textarea_elem is not None
        assert textarea_elem["parent"] == "책무(모달)"

        # 4. §6 체크박스 검증: Form.Item 라벨인 '공통책무'를 체크박스 이름으로 취득
        chk_elem = next(e for e in elements if e["kind"] == "checkbox" and e["name"] == "공통책무")
        assert chk_elem is not None
        assert chk_elem["parent"] == "책무(모달)"

        # 5. §2 레이어 격리: 모달 내부 요소에는 불필요한 '#2'가 붙지 않아야 함
        assert "저장" in names
        assert "닫기" in names
        assert "저장#2" not in names

        browser.close()


def test_fix059_grid_headers_and_checkbox():
    """§3, §4: 모달이 없을 때 그리드 헤더 고정 매핑, 왼쪽 결합 매핑 및 체크박스 크기 검증."""
    # 모달 없는 HTML 버전 생성 (마스크와 모달 랩 제거)
    html_without_modal = MOCK_FIX059_HTML.replace('class="ant-modal-mask modal-mask"', 'style="display:none"')
    html_without_modal = html_without_modal.replace('class="ant-modal-wrap"', 'style="display:none"')

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_content(html_without_modal)

        res = page.evaluate(COLLECT_BOXES_JS, None)
        elements = res["elements"]
        names = [e["name"] for e in elements]

        # §3 헤더 매핑 검증
        # __rownum -> 헤더:번호
        assert "헤더:번호" in names
        assert "헤더:__rownum" not in names

        # ag-Grid-SelectionColumn -> 헤더:선택
        assert "헤더:선택" in names
        assert "헤더:ag-Grid-SelectionColumn" not in names

        # editDetail -> 바로 왼쪽 헤더('세부내용') + '수정'
        assert "헤더:세부내용 수정" in names
        assert "헤더:editDetail" not in names

        # §4 행 셀 및 체크박스 검증
        # 행 선택 체크박스는 grid1.행1.선택
        assert "grid1.행1.선택" in names
        sel_chk = next(e for e in elements if e["name"] == "grid1.행1.선택")
        assert sel_chk["box"][2] == 16
        assert sel_chk["box"][3] == 16

        # 값 체크박스는 컬럼 이름(grid1.행1.공통책무)
        assert "grid1.행1.공통책무" in names
        val_chk = next(e for e in elements if e["name"] == "grid1.행1.공통책무")
        assert val_chk["box"][2] == 16
        assert val_chk["box"][3] == 16

        # 셀 아이콘 매핑: grid1.행1.세부내용 수정
        assert "grid1.행1.세부내용 수정" in names

        browser.close()


def test_fix059_unknown_type_error_and_suggestions():
    """§5: mark에서 알려지지 않은 type은 ValueError 발생 및 difflib 후보 추천."""
    # 1. 완전한 오타 type
    raw_items = [{"type": "circel-number", "text": "1", "x": 10, "y": 10}]
    with pytest.raises(ValueError) as excinfo:
        resolve_draw_items(raw_items, None, (800, 600))
    msg = str(excinfo.value)
    assert "알 수 없는 타입입니다" in msg
    assert "circle-number" in msg  # difflib 추천에 포함됨

    # 2. 미래 예정이지만 미지원 type
    raw_items_future = [{"type": "orthogonal-arrow", "from": [0, 0], "to": [10, 10]}]
    with pytest.raises(ValueError) as excinfo2:
        resolve_draw_items(raw_items_future, None, (800, 600))
    msg2 = str(excinfo2.value)
    assert "아직 지원하지 않는 타입입니다" in msg2


def test_fix059_anchor_outside():
    """§7: anchor: outside-* 지원 및 gap 거리 배치 검증."""
    box = [100, 100, 80, 32]  # [bx, by, bw, bh] 버튼
    radius = 20.0
    gap = 4.0

    # 1. outside-top-left: x = bx, y = by - radius - gap
    pt_tl = compute_anchor_point(box, "outside-top-left", radius=radius, gap=gap)
    assert pt_tl == (100.0, 100.0 - 20.0 - 4.0)

    # 2. outside-top: x = bx + bw/2, y = by - radius - gap
    pt_top = compute_anchor_point(box, "outside-top", radius=radius, gap=gap)
    assert pt_top == (140.0, 100.0 - 20.0 - 4.0)

    # 3. outside-right: x = bx + bw + radius + gap, y = by + bh/2
    pt_right = compute_anchor_point(box, "outside-right", radius=radius, gap=gap)
    assert pt_right == (100.0 + 80.0 + 20.0 + 4.0, 116.0)

    # 4. outside-bottom: x = bx + bw/2, y = by + bh + radius + gap
    pt_bottom = compute_anchor_point(box, "outside-bottom", radius=radius, gap=gap)
    assert pt_bottom == (140.0, 100.0 + 32.0 + 20.0 + 4.0)

    # 5. resolve_draw_items를 통한 실제 circle-number 바깥 배치 검증
    boxes_data = {
        "elements": [
            {"name": "저장", "box": [200, 200, 60, 30]}
        ]
    }
    draw_items = [
        {
            "type": "circle-number",
            "target": "저장",
            "anchor": "outside-top-left",
            "gap": 5,
            "style": {"fontSize": 20},
        }
    ]
    resolved, _warnings = resolve_draw_items(draw_items, boxes_data, (1000, 800))
    assert len(resolved) == 1
    item = resolved[0]
    # fontSize 20 -> radius = 20 * 1.05 = 21
    # y = 200 - 21 - 5 = 174
    assert item["x"] == 200
    assert item["y"] == 174
