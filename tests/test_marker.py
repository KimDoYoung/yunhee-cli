"""yunhee mark 기능 단위 및 통합 테스트 (수정사항 058, boxes-json 11절 규격)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from yunhee.cli import app
from yunhee.tools.marker import (
    compute_anchor_point,
    get_box_edge_center_towards,
    mark_image,
    normalize_color,
    resolve_draw_items,
)
from yunhee.tools.screen_capture import get_png_dimensions


def _create_test_png(path: Path, width: int = 400, height: int = 300, bg_color: str = "#ffffff") -> None:
    """테스트용 간단한 PNG 이미지를 Playwright로 생성한다."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.set_content(f"<body style='margin:0; background:{bg_color};'></body>")
        page.screenshot(path=str(path), full_page=False)
        browser.close()


def test_normalize_color():
    assert normalize_color("red") == "#ef4444"
    assert normalize_color("blue") == "#3b82f6"
    assert normalize_color("green") == "#10b981"
    assert normalize_color("#123456") == "#123456"
    assert normalize_color(None) == "transparent"


def test_compute_anchor_point():
    box = [100, 200, 80, 40]
    assert compute_anchor_point(box, "top-left") == (100.0, 200.0)
    assert compute_anchor_point(box, "top") == (140.0, 200.0)
    assert compute_anchor_point(box, "top-right") == (180.0, 200.0)
    assert compute_anchor_point(box, "right") == (180.0, 220.0)
    assert compute_anchor_point(box, "bottom-right") == (180.0, 240.0)
    assert compute_anchor_point(box, "bottom") == (140.0, 240.0)
    assert compute_anchor_point(box, "bottom-left") == (100.0, 240.0)
    assert compute_anchor_point(box, "left") == (100.0, 220.0)
    assert compute_anchor_point(box, "center") == (140.0, 220.0)


def test_get_box_edge_center_towards():
    # A 상자가 왼쪽에 있고, B 중심이 오른쪽에 있을 때
    box_a = [100, 100, 100, 60]  # 중심 (150, 130)
    target_right = (350.0, 130.0)
    pt = get_box_edge_center_towards(box_a, target_right)
    # A의 오른쪽 변 가운데 (200, 130)
    assert pt == (200.0, 130.0)

    target_below = (150.0, 300.0)
    pt2 = get_box_edge_center_towards(box_a, target_below)
    # A의 아래쪽 변 가운데 (150, 160)
    assert pt2 == (150.0, 160.0)


def test_resolve_draw_items():
    boxes_data = {
        "version": 1,
        "image": "test.png",
        "image-size": [800, 600],
        "elements": [
            {"name": "조회", "kind": "button", "box": [100, 50, 60, 30]},
            {"name": "등록", "kind": "button", "box": [200, 50, 60, 30]},
            {"name": "등록#2", "kind": "button", "box": [300, 50, 60, 30]},
            {"name": "모달", "kind": "modal", "box": [150, 150, 300, 200]},
        ],
    }

    raw_items = [
        {"type": "mask", "target": "조회"},
        {"type": "box", "target": "등록", "padding": 6},
        {"type": "circle-number", "text": "1", "target": "등록", "anchor": "top-right"},
        {"type": "arrow", "from": "등록", "to": "모달"},
        {"type": "callout", "text": "안내", "target": "모달", "side": "right"},
        {"type": "crop", "x": 0, "y": 0, "width": 500, "height": 400},
    ]

    resolved, warnings = resolve_draw_items(raw_items, boxes_data, (800, 600))
    # 렌더링 순서 검증: mask -> 나머지 -> crop
    assert resolved[0]["type"] == "mask"
    assert resolved[-1]["type"] == "crop"

    # box 좌표 검증 (padding 6 반영: [200-6, 50-6, 60+12, 30+12])
    box_item = next(it for it in resolved if it["type"] == "box")
    assert (box_item["x"], box_item["y"], box_item["width"], box_item["height"]) == (194, 44, 72, 42)

    # circle-number 좌표 검증 (anchor top-right: [200+60, 50])
    circle_item = next(it for it in resolved if it["type"] == "circle-number")
    assert (circle_item["x"], circle_item["y"]) == (260, 50)

    # 모호성 경고 검증 ('등록#2'가 있는데 '등록'만 쓴 경우)
    assert any("등록#2" in w for w in warnings)


def test_resolve_draw_items_missing_target():
    boxes_data = {
        "version": 1,
        "image": "test.png",
        "image-size": [800, 600],
        "elements": [
            {"name": "신규등록", "kind": "button", "box": [100, 50, 60, 30]},
        ],
    }
    raw_items = [{"type": "box", "target": "신규등"}]

    with pytest.raises(ValueError) as excinfo:
        resolve_draw_items(raw_items, boxes_data, (800, 600))

    err_msg = str(excinfo.value)
    assert "신규등" in err_msg
    assert "신규등록" in err_msg  # 추천 후보 노출 확인


def test_mark_image_full_cycle(tmp_path: Path):
    """실제 PNG 이미지에 마킹을 렌더링하고 결과 파일 및 픽셀 색상 검증."""
    src_png = tmp_path / "test.png"
    _create_test_png(src_png, width=600, height=400, bg_color="#ffffff")

    boxes_json = tmp_path / "test.boxes.json"
    boxes_json.write_text(
        json.dumps(
            {
                "version": 1,
                "image": "test.png",
                "image-size": [600, 400],
                "elements": [
                    {"name": "버튼1", "kind": "button", "box": [100, 100, 80, 40]},
                    {"name": "버튼2", "kind": "button", "box": [300, 200, 80, 40]},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    draw_json = tmp_path / "draw.json"
    draw_json.write_text(
        json.dumps(
            {
                "version": 1,
                "items": [
                    {"type": "mask", "target": "버튼1"},  # #9ca3af로 채움
                    {"type": "box", "target": "버튼2"},   # #ef4444 테두리
                    {"type": "circle-number", "text": "1", "target": "버튼2", "anchor": "center"},
                    {"type": "arrow", "from": "버튼1", "to": "버튼2"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # mark_image 실행
    out_png = tmp_path / "test-alpha.png"
    res = mark_image(src_png, draw_json, boxes_path=boxes_json, out_path=out_png)

    assert res.ok is True
    assert out_png.exists()
    assert src_png.exists()

    # 원본 파일 크기와 출력 파일 크기 일치 검증
    in_w, in_h = get_png_dimensions(src_png)
    out_w, out_h = get_png_dimensions(out_png)
    assert (in_w, in_h) == (600, 400)
    assert (out_w, out_h) == (600, 400)

    # 브라우저 캔버스를 통해 마킹된 픽셀 색상 검증
    # 1) 버튼1 중심점(140, 120)은 mask 색상 #9ca3af (rgb: 156, 163, 175)이어야 함
    # 2) 버튼2 중심점(340, 220)은 circle-number 배경색 #ef4444 (rgb: 239, 68, 68)이어야 함
    from playwright.sync_api import sync_playwright

    b64_out = base64.b64encode(out_png.read_bytes()).decode("ascii")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<html><body></body></html>")

        pixel_data = page.evaluate(
            """
            async (b64) => {
                const img = new Image();
                await new Promise((res, rej) => {
                    img.onload = res;
                    img.onerror = rej;
                    img.src = 'data:image/png;base64,' + b64;
                });
                const cvs = document.createElement('canvas');
                cvs.width = img.naturalWidth;
                cvs.height = img.naturalHeight;
                const ctx = cvs.getContext('2d');
                ctx.drawImage(img, 0, 0);

                const pMask = ctx.getImageData(140, 120, 1, 1).data;
                const pCircle = ctx.getImageData(340, 220, 1, 1).data;
                return {
                    mask: [pMask[0], pMask[1], pMask[2]],
                    circle: [pCircle[0], pCircle[1], pCircle[2]]
                };
            }
            """,
            b64_out,
        )
        browser.close()

    assert pixel_data["mask"] == [156, 163, 175]  # #9ca3af
    # circle-number 중앙은 숫자 텍스트('1' 흰색) 또는 배경색(#ef4444)
    # 흰색 [255, 255, 255] 또는 빨간색 [239, 68, 68]
    assert pixel_data["circle"] in ([255, 255, 255], [239, 68, 68])


def test_mark_image_crop(tmp_path: Path):
    """crop 아이템 지정 시 최종 출력 이미지 크기가 잘라낸 크기로 변경되는지 검증."""
    src_png = tmp_path / "crop_test.png"
    _create_test_png(src_png, width=800, height=600)

    draw_items = [
        {"type": "crop", "x": 50, "y": 60, "width": 300, "height": 200},
    ]

    out_png = tmp_path / "cropped.png"
    res = mark_image(src_png, draw_items, out_path=out_png)

    assert res.ok is True
    w, h = get_png_dimensions(out_png)
    assert (w, h) == (300, 200)


def test_cli_mark_help():
    runner = CliRunner()
    result = runner.invoke(app, ["mark", "--help"])
    assert result.exit_code == 0
    assert "draw.json" in result.output
    assert "--boxes" in result.output
    assert "--out" in result.output
