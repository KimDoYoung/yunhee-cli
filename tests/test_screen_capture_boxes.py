"""screen-capture --boxes 기능 단위 테스트 (수정사항 057, boxes-json 규격)."""

from __future__ import annotations

from pathlib import Path

from yunhee.tools.screen_capture import (
    COLLECT_BOXES_JS,
    get_png_dimensions,
)

MOCK_HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Mock Screen for Boxes Test</title>
    <style>
        body { margin: 0; padding: 20px; font-family: sans-serif; }
        .toolbar { display: flex; gap: 8px; margin-bottom: 20px; }
        button { padding: 6px 12px; cursor: pointer; }
        .ant-form-item { display: flex; align-items: center; margin-bottom: 12px; }
        .ant-form-item-label { width: 100px; }
        .ant-modal-content {
            position: absolute;
            top: 150px;
            left: 200px;
            width: 400px;
            height: 300px;
            background: #fff;
            border: 1px solid #ccc;
            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            padding: 16px;
        }
        .ant-modal-title { font-size: 16px; font-weight: bold; margin-bottom: 12px; }
        .ag-root { margin-top: 20px; border: 1px solid #e0e0e0; }
        .ag-header-cell { display: inline-block; width: 120px; padding: 8px; background: #fafafa; font-weight: bold; }
        .ag-row { display: flex; border-bottom: 1px solid #eee; }
        .ag-cell { width: 120px; padding: 8px; }
        .hidden-el { display: none; }
    </style>
</head>
<body>
    <div class="toolbar">
        <button class="ant-btn">조회</button>
        <button class="ant-btn">조회</button> <!-- 중복 이름 테스트 (#2) -->
        <button class="ant-btn">등록</button>
        <button class="ant-btn" aria-label="search"><svg class="anticon anticon-search"><path/></svg></button>
    </div>

    <div class="ant-form-item">
        <div class="ant-form-item-label">
            <label>*책무구분 :</label>
        </div>
        <div class="ant-form-item-control">
            <input class="ant-input" type="text" value="테스트구분" />
        </div>
    </div>

    <div class="ant-form-item">
        <div class="ant-form-item-label">
            <label>승인상태</label>
        </div>
        <div class="ant-form-item-control">
            <div class="ant-select" style="width: 150px; height: 32px;"></div>
        </div>
    </div>

    <label class="ant-checkbox-wrapper">
        <input type="checkbox" />
        <span>전체보기</span>
    </label>

    <button class="ant-btn hidden-el">안보이는버튼</button>

    <div class="ag-root">
        <div class="ag-header-row">
            <div class="ag-header-cell" col-id="col_role"><span class="ag-header-cell-text">책무유형</span></div>
            <div class="ag-header-cell" col-id="col_edit"><span class="ag-header-cell-text">관리</span></div>
        </div>
        <div class="ag-row">
            <div class="ag-cell" col-id="col_role">일반책무</div>
            <div class="ag-cell" col-id="col_edit">
                <button class="ant-btn edit-btn" title="수정"><svg class="anticon anticon-edit"><path/></svg></button>
            </div>
        </div>
        <div class="ag-row">
            <div class="ag-cell" col-id="col_role">특별책무</div>
            <div class="ag-cell" col-id="col_edit">
                <button class="ant-btn edit-btn" title="수정"><svg class="anticon anticon-edit"><path/></svg></button>
            </div>
        </div>
    </div>

    <!-- 팝업 모달 -->
    <div class="ant-modal-content">
        <div class="ant-modal-title">책무 등록</div>
        <div class="ant-form-item">
            <div class="ant-form-item-label"><label>팝업항목</label></div>
            <input class="ant-input" type="text" />
        </div>
        <button class="ant-btn">저장</button>
        <button class="ant-btn ant-modal-close">닫기</button>
    </div>
</body>
</html>
"""


def test_get_png_dimensions(tmp_path: Path):
    """PNG IHDR 헤더 파싱 함수 검증."""
    # 간단한 10x20 크기 PNG 바이너리 생성 (IHDR 청크 직접 작성)
    # PNG signature: 8 bytes
    # IHDR chunk: 4 bytes length (13) + 4 bytes "IHDR" + 13 bytes data + 4 bytes CRC
    png_data = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\r"
        b"IHDR"
        b"\x00\x00\x00\x0a"  # width: 10
        b"\x00\x00\x00\x14"  # height: 20
        b"\x08\x06\x00\x00\x00"
        b"\x00\x00\x00\x00"
    )
    p = tmp_path / "test.png"
    p.write_bytes(png_data)

    w, h = get_png_dimensions(p)
    assert w == 10
    assert h == 20


def test_collect_boxes_full_page():
    """Playwright 브라우저에서 COLLECT_BOXES_JS 실행 및 전체 화면 캡처 기준 검증."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_content(MOCK_HTML)

        # 全体 화면 캡처 시 clipElem=None
        res = page.evaluate(COLLECT_BOXES_JS, None)

        assert res["viewport"] == [1280, 800]
        assert res["origin"] == [0, 0]
        elements = res["elements"]
        assert len(elements) > 0

        # 1. 중복 이름 처리 확인: '조회'와 '조회#2'
        names = [e["name"] for e in elements]
        assert "조회" in names
        assert "조회#2" in names
        assert "등록" in names
        assert "안보이는버튼" not in names  # display:none은 수집되지 않아야 함

        # 2. 모든 이름이 유일한지 확인
        assert len(names) == len(set(names)), f"중복된 이름 발견: {names}"

        # 3. 폼 라벨 및 인풋 매핑 확인
        assert "책무구분" in names
        # input의 name으로 '책무구분' 매핑 확인
        input_elem = next(e for e in elements if e["kind"] == "input" and "책무구분" in e["name"])
        assert input_elem is not None

        # 4. 아이콘 버튼 확인
        assert "search" in names

        # 5. 모달 및 모달 타이틀 확인
        modal_elem = next(e for e in elements if e["kind"] == "modal")
        assert modal_elem["name"] == "책무 등록"
        assert modal_elem["area"] == "modal"

        title_elem = next(e for e in elements if e["kind"] == "modal-title")
        assert title_elem["name"] == "책무 등록:제목"
        assert title_elem["parent"] == "책무 등록"

        # 6. 모달 내부 버튼 확인
        save_btn = next(e for e in elements if e["name"] == "저장")
        assert save_btn["parent"] == "책무 등록"
        assert save_btn["area"] == "modal"

        # 7. 그리드 요소 확인
        assert "grid1" in names
        assert "헤더:책무유형" in names
        assert "grid1.행1" in names
        assert "grid1.행2" in names
        assert "grid1.행1.책무유형" in names
        assert "grid1.행1.수정" in names

        # 8. 좌표 정합성 검증: '등록' 버튼의 box가 실제 getBoundingClientRect와 일치하는지
        reg_btn_rect = page.locator("button:has-text('등록')").first.bounding_box()
        reg_elem = next(e for e in elements if e["name"] == "등록")
        # box: [x, y, w, h]
        assert abs(reg_elem["box"][0] - reg_btn_rect["x"]) <= 1
        assert abs(reg_elem["box"][1] - reg_btn_rect["y"]) <= 1
        assert abs(reg_elem["box"][2] - reg_btn_rect["width"]) <= 1
        assert abs(reg_elem["box"][3] - reg_btn_rect["height"]) <= 1

        browser.close()


def test_collect_boxes_modal_only():
    """--modal-only 지정 시 모달 기준 origin 및 상대 좌표 변환 검증."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        page.set_content(MOCK_HTML)

        modal_loc = page.locator(".ant-modal-content").first
        modal_rect = modal_loc.bounding_box()
        modal_handle = modal_loc.element_handle()

        # modal_only 캡처 시 clipElem으로 modal_handle 전달
        res = page.evaluate(COLLECT_BOXES_JS, modal_handle)

        # origin은 모달의 top-left여야 함
        assert abs(res["origin"][0] - modal_rect["x"]) <= 1
        assert abs(res["origin"][1] - modal_rect["y"]) <= 1

        elements = res["elements"]
        names = [e["name"] for e in elements]

        # 모달 내부 요소들만 포함되거나 모달 영역 내에 위치해야 함
        assert "책무 등록" in names
        assert "책무 등록:제목" in names
        assert "저장" in names
        assert "닫기" in names

        # 모달 자체의 box는 [0, 0, width, height] 근처여야 함
        modal_item = next(e for e in elements if e["kind"] == "modal")
        assert modal_item["box"][0] == 0
        assert modal_item["box"][1] == 0
        assert abs(modal_item["box"][2] - modal_rect["width"]) <= 1
        assert abs(modal_item["box"][3] - modal_rect["height"]) <= 1

        # 모달 내부 '저장' 버튼의 box 검증 (상대 좌표)
        save_btn_rect = page.locator(".ant-modal-content button:has-text('저장')").first.bounding_box()
        save_elem = next(e for e in elements if e["name"] == "저장")
        expected_x = round(save_btn_rect["x"] - modal_rect["x"])
        expected_y = round(save_btn_rect["y"] - modal_rect["y"])

        assert abs(save_elem["box"][0] - expected_x) <= 1
        assert abs(save_elem["box"][1] - expected_y) <= 1

        # 모달 밖에 있는 메인 화면 버튼('등록', '조회')은 모달 영역 밖이므로 제외되어야 함
        assert "등록" not in names
        assert "조회" not in names

        browser.close()


def test_boxes_overlay_on_image(tmp_path: Path):
    """수용 기준 2: 실제 PNG 스크린샷과 boxes.json의 box 좌표가 픽셀 단위로 정확히 겹치는지 검증."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 810})
        page.set_content("""
        <!DOCTYPE html>
        <html>
        <body style="margin:0; background:#ffffff;">
            <button id="target-btn" style="position:absolute; left:100px; top:120px; width:80px; height:30px; background:#0000ff; color:#fff; border:none;">클릭</button>
            <div id="target-modal" style="position:absolute; left:300px; top:200px; width:200px; height:150px; background:#00ff00; padding:10px;">
                <div class="ant-modal-title">테스트모달</div>
                <button id="modal-btn" style="position:absolute; left:20px; top:40px; width:60px; height:25px; background:#ff0000; color:#fff; border:none;">확인</button>
            </div>
        </body>
        </html>
        """)

        # 1. 전체 캡처 검증
        full_png = tmp_path / "full.png"
        page.screenshot(path=str(full_png), full_page=False)
        full_res = page.evaluate(COLLECT_BOXES_JS, None)
        img_w, img_h = get_png_dimensions(full_png)
        assert (img_w, img_h) == (1440, 810)

        # target-btn의 box 확인
        btn_elem = next(e for e in full_res["elements"] if e["name"] == "클릭")
        bx, by, bw, bh = btn_elem["box"]

        # 브라우저 Canvas를 통해 실제 캡처 PNG의 해당 box 중심 픽셀 색상 검증
        png_bytes = full_png.read_bytes()
        import base64
        b64_data = base64.b64encode(png_bytes).decode("ascii")

        pixel_color = page.evaluate(
            """
            async ([b64, x, y]) => {
                const img = new Image();
                img.src = 'data:image/png;base64,' + b64;
                await img.decode();
                const cvs = document.createElement('canvas');
                cvs.width = img.width;
                cvs.height = img.height;
                const ctx = cvs.getContext('2d');
                ctx.drawImage(img, 0, 0);
                const p = ctx.getImageData(x, y, 1, 1).data;
                return [p[0], p[1], p[2]]; // [r, g, b]
            }
            """,
            [b64_data, bx + bw // 2, by + bh // 2],
        )
        # target-btn의 배경색: 파란색 [0, 0, 255]
        assert pixel_color == [0, 0, 255], f"중심 픽셀 색상 불일치: {pixel_color}"

        # 2. modal-only 캡처 검증
        modal_loc = page.locator("#target-modal")
        modal_png = tmp_path / "modal.png"
        modal_loc.screenshot(path=str(modal_png))
        modal_res = page.evaluate(COLLECT_BOXES_JS, modal_loc.element_handle())
        m_img_w, m_img_h = get_png_dimensions(modal_png)
        assert (m_img_w, m_img_h) == (220, 170)

        modal_btn_elem = next(e for e in modal_res["elements"] if e["name"] == "확인")
        mbx, mby, mbw, mbh = modal_btn_elem["box"]

        m_b64 = base64.b64encode(modal_png.read_bytes()).decode("ascii")
        m_pixel_color = page.evaluate(
            """
            async ([b64, x, y]) => {
                const img = new Image();
                img.src = 'data:image/png;base64,' + b64;
                await img.decode();
                const cvs = document.createElement('canvas');
                cvs.width = img.width;
                cvs.height = img.height;
                const ctx = cvs.getContext('2d');
                ctx.drawImage(img, 0, 0);
                const p = ctx.getImageData(x, y, 1, 1).data;
                return [p[0], p[1], p[2]];
            }
            """,
            [m_b64, mbx + mbw // 2, mby + mbh // 2],
        )
        # modal-btn의 배경색: 빨간색 [255, 0, 0]
        assert m_pixel_color == [255, 0, 0], f"모달 내부 버튼 중심 픽셀 색상 불일치: {m_pixel_color}"

        browser.close()


def test_boxes_viewport_custom():
    """수용 기준 4: --viewport 1440x810 등 커스텀 뷰포트 변경 시 정합성 검증."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 810})
        page.set_content("<button class='ant-btn'>검색</button>")

        res = page.evaluate(COLLECT_BOXES_JS, None)
        assert res["viewport"] == [1440, 810]
        assert res["scale"] == 1.0
        assert res["origin"] == [0, 0]

        elem = res["elements"][0]
        assert elem["name"] == "검색"
        assert elem["kind"] == "button"

        browser.close()

