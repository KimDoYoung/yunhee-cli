"""A-Man 호환 매뉴얼 이미지 마킹 도구 (yunhee mark).

수정사항 058 및 docs/boxes-json-규격.md 11절 규격 구현:
- draw.json의 요소들을 읽어 PNG 이미지 위에 번호 원·강조 상자·화살표·말풍선·마스킹을 렌더링
- boxes.json의 요소 이름을 target(또는 arrow from/to)으로 참조하여 좌표 자동 산출
- A-Man 이미지 편집기(SYSTEM_ITEM_DEFAULTS, drawArrow, traceSpeechRectPath)와 100% 동일한 렌더링 지원
- 렌더링 순서: mask -> 일반 items -> crop
"""

from __future__ import annotations

import base64
import difflib
import json
from pathlib import Path
from typing import Any

from yunhee.tools.base import ToolResult
from yunhee.tools.screen_capture import get_png_dimensions

COLOR_NAME_MAP: dict[str, str] = {
    "red": "#ef4444",
    "blue": "#3b82f6",
    "green": "#10b981",
    "yellow": "#ffff00",
    "white": "#ffffff",
    "black": "#0f172a",
}

DEFAULT_STYLES: dict[str, dict[str, Any]] = {
    "circle-number": {
        "backgroundColor": "#ef4444",
        "textColor": "#ffffff",
        "borderColor": "#f59e0b",
        "borderWidth": 3,
        "fontSize": 28,
        "shape": "circle",
    },
    "box": {
        "borderColor": "#ef4444",
        "borderWidth": 2,
        "lineStyle": "solid",
        "backgroundColor": "transparent",
        "opacity": 0.3,
        "borderRadius": 7,
        "shape": "rect",
    },
    "arrow": {
        "borderColor": "#ef4444",
        "borderWidth": 3,
        "lineStyle": "solid",
        "headSize": 2,
    },
    "text": {
        "textColor": "#3b82f6",
        "fontSize": 16,
        "backgroundColor": "transparent",
        "fontStyle": "normal",
        "textDecoration": "none",
        "rotation": 0,
    },
    "callout": {
        "backgroundColor": "#eff6ff",
        "borderColor": "#3b82f6",
        "borderWidth": 2,
        "lineStyle": "solid",
        "opacity": 1.0,
        "borderRadius": 8,
        "textColor": "#3b82f6",
        "fontSize": 14,
        "calloutShape": "speech-rect",
    },
    "mask": {
        "backgroundColor": "#9ca3af",
        "mode": "fill",
    },
    "crop": {},
}


def normalize_color(color_str: str | None) -> str:
    """색상 이름(red, blue 등)을 A-Man 기본 팔레트 헥스 코드로 변환한다."""
    if not color_str:
        return "transparent"
    s = color_str.strip().lower()
    return COLOR_NAME_MAP.get(s, color_str.strip())


def compute_anchor_point(box: list[int | float], anchor: str) -> tuple[float, float]:
    """대상 상자([bx, by, bw, bh])에서 anchor 기준 좌표 (x, y)를 계산한다."""
    bx, by, bw, bh = box
    anc = anchor.lower().strip()
    if anc == "top-left":
        return (float(bx), float(by))
    if anc == "top":
        return (float(bx + bw / 2), float(by))
    if anc == "top-right":
        return (float(bx + bw), float(by))
    if anc == "right":
        return (float(bx + bw), float(by + bh / 2))
    if anc == "bottom-right":
        return (float(bx + bw), float(by + bh))
    if anc == "bottom":
        return (float(bx + bw / 2), float(by + bh))
    if anc == "bottom-left":
        return (float(bx), float(by + bh))
    if anc == "left":
        return (float(bx), float(by + bh / 2))
    if anc == "center":
        return (float(bx + bw / 2), float(by + bh / 2))
    return (float(bx), float(by))


def get_box_edge_center_towards(
    box: list[int | float], target_pt: tuple[float, float]
) -> tuple[float, float]:
    """대상 상자(box)의 중심에서 target_pt를 향하는 변의 가운데 점을 반환한다."""
    bx, by, bw, bh = box
    cx = bx + bw / 2
    cy = by + bh / 2
    tx, ty = target_pt
    dx = tx - cx
    dy = ty - cy
    if dx == 0 and dy == 0:
        return (float(cx), float(cy))

    # 가로축/세로축 주요 방향 판정
    if abs(dx) * bh >= abs(dy) * bw:
        edge_x = float(bx + bw) if dx > 0 else float(bx)
        return (edge_x, float(cy))
    edge_y = float(by + bh) if dy > 0 else float(by)
    return (float(cx), edge_y)


def resolve_draw_items(
    items_raw: list[dict[str, Any]],
    boxes_data: dict[str, Any] | None,
    image_size: tuple[int, int],
) -> tuple[list[dict[str, Any]], list[str]]:
    """draw.json의 items를 파싱하고 boxes.json을 참조하여 구체적인 픽셀 좌표와 스타일을 확정한다.

    Returns:
        (resolved_items, warnings)
    """
    warnings: list[str] = []
    element_map: dict[str, dict[str, Any]] = {}
    element_names: list[str] = []

    if boxes_data and "elements" in boxes_data:
        for el in boxes_data["elements"]:
            name = el.get("name")
            if name:
                element_map[name] = el
                element_names.append(name)

    def find_target_box(target_name: str) -> list[int]:
        if target_name in element_map:
            # #2가 있는데 #1 없이 target을 쓴 경우 안내 경고
            if f"{target_name}#2" in element_map:
                warnings.append(
                    f"'{target_name}'에 '{target_name}#2'가 존재하지만 '{target_name}'만 지정되어 첫 번째 요소를 사용합니다."
                )
            return list(element_map[target_name]["box"])

        # 정확한 일치가 없을 때 비슷한 이름 후보 추천
        candidates = difflib.get_close_matches(target_name, element_names, n=3, cutoff=0.3)
        cand_str = f" (비슷한 후보: {candidates})" if candidates else ""
        raise ValueError(f"대상 요소 '{target_name}'을(를) boxes.json에서 찾을 수 없습니다.{cand_str}")

    resolved_items: list[dict[str, Any]] = []

    for idx, item in enumerate(items_raw, 1):
        item_type = item.get("type")
        if not item_type:
            raise ValueError(f"{idx}번째 아이템에 'type' 필드가 없습니다.")

        resolved = {
            "id": item.get("id") or f"item-{idx}",
            "type": item_type,
            "text": item.get("text", ""),
        }

        # 스타일 기본값 병합
        base_style = dict(DEFAULT_STYLES.get(item_type, {}))
        user_style = item.get("style") or {}
        merged_style = {**base_style, **user_style}

        # 색상 이름 치환
        for color_key in ["borderColor", "backgroundColor", "textColor", "color"]:
            if color_key in merged_style and isinstance(merged_style[color_key], str):
                merged_style[color_key] = normalize_color(merged_style[color_key])

        target = item.get("target")

        # 1. circle-number
        if item_type == "circle-number":
            font_size = merged_style.get("fontSize", 28)
            radius = font_size * 1.05

            if item.get("x") is not None and item.get("y") is not None:
                cx, cy = float(item["x"]), float(item["y"])
            elif target:
                box = find_target_box(target)
                anchor = item.get("anchor", "top-left")
                anchor_x, anchor_y = compute_anchor_point(box, anchor)
                offset = item.get("offset") or [0, 0]
                cx = anchor_x + float(offset[0])
                cy = anchor_y + float(offset[1])
            else:
                raise ValueError(f"{item_type} 아이템에 'target' 또는 직접 좌표(x, y)가 필요합니다.")

            # 이미지 가장자리 밖으로 나갈 때 원이 잘리지 않도록 캔버스 안쪽으로 부드럽게 clamp
            img_w, img_h = image_size
            cx = max(radius, min(img_w - radius, cx))
            cy = max(radius, min(img_h - radius, cy))

            resolved["x"] = round(cx)
            resolved["y"] = round(cy)
            resolved["text"] = str(item.get("text") or "1")
            resolved["style"] = merged_style

        # 2. box, mask, crop
        elif item_type in ("box", "mask", "crop"):
            padding = item.get("padding")
            if padding is None:
                padding = 4 if item_type == "box" else 0

            if item.get("x") is not None and item.get("y") is not None:
                x = float(item["x"])
                y = float(item["y"])
                w = float(item.get("width") or 0)
                h = float(item.get("height") or 0)
            elif target:
                bx, by, bw, bh = find_target_box(target)
                x = bx - padding
                y = by - padding
                w = bw + 2 * padding
                h = bh + 2 * padding
            else:
                raise ValueError(f"{item_type} 아이템에 'target' 또는 직접 좌표가 필요합니다.")

            resolved["x"] = round(x)
            resolved["y"] = round(y)
            resolved["width"] = round(w)
            resolved["height"] = round(h)
            resolved["style"] = merged_style

        # 3. arrow
        elif item_type == "arrow":
            from_spec = item.get("from")
            to_spec = item.get("to")

            if (
                item.get("x") is not None
                and item.get("y") is not None
                and item.get("width") is not None
            ):
                x = float(item["x"])
                y = float(item["y"])
                w = float(item["width"])
                h = float(item.get("height", 0))
            elif from_spec is not None and to_spec is not None:
                # from_spec 좌표 구하기
                if isinstance(from_spec, list) and len(from_spec) >= 2:
                    from_pt = (float(from_spec[0]), float(from_spec[1]))
                    box_from = None
                elif isinstance(from_spec, str):
                    box_from = find_target_box(from_spec)
                    from_pt = (box_from[0] + box_from[2] / 2, box_from[1] + box_from[3] / 2)
                else:
                    raise ValueError(f"arrow 'from' 형식이 올바르지 않습니다: {from_spec}")

                # to_spec 좌표 구하기
                if isinstance(to_spec, list) and len(to_spec) >= 2:
                    to_pt = (float(to_spec[0]), float(to_spec[1]))
                    box_to = None
                elif isinstance(to_spec, str):
                    box_to = find_target_box(to_spec)
                    to_pt = (box_to[0] + box_to[2] / 2, box_to[1] + box_to[3] / 2)
                else:
                    raise ValueError(f"arrow 'to' 형식이 올바르지 않습니다: {to_spec}")

                # 상자가 있으면 상대방을 향하는 변의 가운데 점을 정밀 계산
                if box_from is not None:
                    from_pt = get_box_edge_center_towards(box_from, to_pt)
                if box_to is not None:
                    to_pt = get_box_edge_center_towards(box_to, from_pt)

                x = from_pt[0]
                y = from_pt[1]
                w = to_pt[0] - from_pt[0]
                h = to_pt[1] - from_pt[1]
            else:
                raise ValueError("arrow 아이템에 'from'과 'to' (또는 x, y, width, height)가 필요합니다.")

            resolved["x"] = round(x)
            resolved["y"] = round(y)
            resolved["width"] = round(w)
            resolved["height"] = round(h)
            resolved["style"] = merged_style

        # 4. text
        elif item_type == "text":
            if item.get("x") is not None and item.get("y") is not None:
                x = float(item["x"])
                y = float(item["y"])
            elif target:
                box = find_target_box(target)
                side = item.get("side")
                gap = float(item.get("gap", 40))
                if side:
                    bx, by, bw, bh = box
                    if side == "right":
                        x = bx + bw + gap
                        y = by
                    elif side == "left":
                        x = bx - gap - 100
                        y = by
                    elif side == "bottom":
                        x = bx
                        y = by + bh + gap
                    elif side == "top":
                        x = bx
                        y = by - gap - 20
                    else:
                        x, y = bx, by
                else:
                    anchor = item.get("anchor", "top-left")
                    x, y = compute_anchor_point(box, anchor)

                offset = item.get("offset") or [0, 0]
                x += float(offset[0])
                y += float(offset[1])
            else:
                raise ValueError("text 아이템에 'target' 또는 직접 좌표(x, y)가 필요합니다.")

            resolved["x"] = round(x)
            resolved["y"] = round(y)
            resolved["text"] = str(item.get("text", ""))
            resolved["style"] = merged_style

        # 5. callout
        elif item_type == "callout":
            w = float(item.get("width") or 140)
            h = float(item.get("height") or 70)

            if item.get("x") is not None and item.get("y") is not None:
                x = float(item["x"])
                y = float(item["y"])
                tail_x = merged_style.get("calloutTailX")
                tail_y = merged_style.get("calloutTailY")
            elif target:
                bx, by, bw, bh = find_target_box(target)
                side = (item.get("side") or "right").lower().strip()
                gap = float(item.get("gap", 40))

                if side == "right":
                    x = bx + bw + gap
                    y = by + bh / 2 - h / 2
                    tail_x = bx + bw
                    tail_y = by + bh / 2
                elif side == "left":
                    x = bx - gap - w
                    y = by + bh / 2 - h / 2
                    tail_x = bx
                    tail_y = by + bh / 2
                elif side == "bottom":
                    x = bx + bw / 2 - w / 2
                    y = by + bh + gap
                    tail_x = bx + bw / 2
                    tail_y = by + bh
                elif side == "top":
                    x = bx + bw / 2 - w / 2
                    y = by - gap - h
                    tail_x = bx + bw / 2
                    tail_y = by
                else:
                    x = bx + bw + gap
                    y = by
                    tail_x = bx + bw
                    tail_y = by + bh / 2
            else:
                raise ValueError("callout 아이템에 'target' 또는 직접 좌표(x, y)가 필요합니다.")

            offset = item.get("offset") or [0, 0]
            x += float(offset[0])
            y += float(offset[1])

            if tail_x is not None:
                merged_style["calloutTailX"] = round(tail_x)
            if tail_y is not None:
                merged_style["calloutTailY"] = round(tail_y)

            resolved["x"] = round(x)
            resolved["y"] = round(y)
            resolved["width"] = round(w)
            resolved["height"] = round(h)
            resolved["text"] = str(item.get("text", ""))
            resolved["style"] = merged_style

        else:
            # 기타 요소
            resolved["x"] = round(float(item.get("x", 0)))
            resolved["y"] = round(float(item.get("y", 0)))
            if "width" in item:
                resolved["width"] = round(float(item["width"]))
            if "height" in item:
                resolved["height"] = round(float(item["height"]))
            resolved["style"] = merged_style

        resolved_items.append(resolved)

    # 렌더링 순서 재배열: mask -> 나머지 items -> crop
    masks = [it for it in resolved_items if it["type"] == "mask"]
    crops = [it for it in resolved_items if it["type"] == "crop"]
    others = [it for it in resolved_items if it["type"] not in ("mask", "crop")]

    ordered_items = masks + others + crops
    return (ordered_items, warnings)


CANVAS_RENDER_HTML = r"""
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body { margin: 0; padding: 0; overflow: hidden; background: transparent; }
canvas { display: block; }
</style>
</head>
<body>
<canvas id="cvs"></canvas>
<script>
// A-Man 이미지 편집기 드로잉 알고리즘 이식

function drawArrow(ctx, fromX, fromY, toX, toY, color, width, lineStyle, headSizeLevel) {
  ctx.save();
  ctx.strokeStyle = color;
  ctx.lineWidth = width;
  ctx.setLineDash(lineStyle === 'dashed' ? [4, 4] : []);

  const angle = Math.atan2(toY - fromY, toX - fromX);
  const scale = headSizeLevel === 2 ? 1.5 : headSizeLevel === 3 ? 2.0 : 1.0;
  const headLength = Math.max(12, width * 3) * scale;
  const distance = Math.sqrt((toX - fromX) ** 2 + (toY - fromY) ** 2);
  const offset = Math.min(distance * 0.8, headLength * 0.8);
  const lineToX = toX - offset * Math.cos(angle);
  const lineToY = toY - offset * Math.sin(angle);

  ctx.beginPath();
  ctx.moveTo(fromX, fromY);
  ctx.lineTo(lineToX, lineToY);
  ctx.stroke();

  const arrowAngle = Math.PI / 6;
  const leftX = toX - headLength * Math.cos(angle - arrowAngle);
  const leftY = toY - headLength * Math.sin(angle - arrowAngle);
  const rightX = toX - headLength * Math.cos(angle + arrowAngle);
  const rightY = toY - headLength * Math.sin(angle + arrowAngle);

  ctx.beginPath();
  ctx.moveTo(toX, toY);
  ctx.lineTo(leftX, leftY);
  ctx.lineTo(rightX, rightY);
  ctx.closePath();
  ctx.fillStyle = color;
  ctx.fill();

  ctx.restore();
}

function traceSpeechRectPath(ctx, x, y, w, h, radius, tailX, tailY) {
  const r = Math.max(0, Math.min(radius, w / 2, h / 2));
  const halfWidth = Math.max(2, Math.min(10, Math.min(w, h) * 0.15, w / 2 - r - 2, h / 2 - r - 2));

  const cx = x + w / 2;
  const cy = y + h / 2;
  const dx = tailX - cx;
  let dy = tailY - cy;
  if (dx === 0 && dy === 0) dy = 1;

  const edge = Math.abs(dx) * h > Math.abs(dy) * w
    ? (dx > 0 ? 'right' : 'left')
    : (dy > 0 ? 'bottom' : 'top');

  const attachX = Math.min(x + w - r - halfWidth, Math.max(x + r + halfWidth, tailX));
  const attachY = Math.min(y + h - r - halfWidth, Math.max(y + r + halfWidth, tailY));

  ctx.beginPath();
  ctx.moveTo(x + r, y);
  if (edge === 'top') {
    ctx.lineTo(attachX - halfWidth, y);
    ctx.lineTo(tailX, tailY);
    ctx.lineTo(attachX + halfWidth, y);
  }
  ctx.lineTo(x + w - r, y);
  ctx.quadraticCurveTo(x + w, y, x + w, y + r);
  if (edge === 'right') {
    ctx.lineTo(x + w, attachY - halfWidth);
    ctx.lineTo(tailX, tailY);
    ctx.lineTo(x + w, attachY + halfWidth);
  }
  ctx.lineTo(x + w, y + h - r);
  ctx.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  if (edge === 'bottom') {
    ctx.lineTo(attachX + halfWidth, y + h);
    ctx.lineTo(tailX, tailY);
    ctx.lineTo(attachX - halfWidth, y + h);
  }
  ctx.lineTo(x + r, y + h);
  ctx.quadraticCurveTo(x, y + h, x, y + h - r);
  if (edge === 'left') {
    ctx.lineTo(x, attachY + halfWidth);
    ctx.lineTo(tailX, tailY);
    ctx.lineTo(x, attachY - halfWidth);
  }
  ctx.lineTo(x, y + r);
  ctx.quadraticCurveTo(x, y, x + r, y);
  ctx.closePath();
}

function drawCalloutText(ctx, text, x, y, w, h, textColor, fontSize) {
  if (!text) return;
  ctx.save();
  ctx.font = `bold ${fontSize}px sans-serif`;
  ctx.fillStyle = textColor;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'middle';

  const padding = 8;
  ctx.rect(x + padding, y + padding, Math.max(0, w - padding * 2), Math.max(0, h - padding * 2));
  ctx.clip();

  const lines = text.split('\n');
  const lineHeight = fontSize * 1.2;
  const totalHeight = (lines.length - 1) * lineHeight;
  const startY = y + h / 2 - totalHeight / 2;
  const textX = x + padding;

  lines.forEach((line, index) => {
    ctx.fillText(line, textX, startY + index * lineHeight);
  });
  ctx.restore();
}

window.renderMarking = async function(base64Image, items) {
  const img = new Image();
  await new Promise((resolve, reject) => {
    img.onload = resolve;
    img.onerror = reject;
    img.src = 'data:image/png;base64,' + base64Image;
  });

  const canvas = document.getElementById('cvs');
  canvas.width = img.naturalWidth;
  canvas.height = img.naturalHeight;
  const ctx = canvas.getContext('2d');

  // 1. 원본 이미지 그리기
  ctx.drawImage(img, 0, 0);

  let cropRect = null;

  // 2. 아이템 렌더링
  for (const item of items) {
    if (item.type === 'crop') {
      cropRect = {
        x: Math.max(0, item.x),
        y: Math.max(0, item.y),
        width: Math.min(canvas.width - item.x, item.width),
        height: Math.min(canvas.height - item.y, item.height)
      };
      continue;
    }

    ctx.save();

    if (item.type === 'mask') {
      const bgColor = item.style.backgroundColor || '#9ca3af';
      ctx.fillStyle = bgColor;
      ctx.fillRect(item.x, item.y, item.width, item.height);
    }
    else if (item.type === 'circle-number') {
      const fontSize = item.style.fontSize || 28;
      const radius = fontSize * 1.05;
      const shape = item.style.shape || 'circle';
      const bgColor = item.style.backgroundColor || '#ef4444';
      const bColor = item.style.borderColor || '#f59e0b';
      const bWidth = item.style.borderWidth || 3;

      ctx.shadowColor = 'rgba(0,0,0,0.15)';
      ctx.shadowBlur = 4;
      ctx.shadowOffsetY = 2;
      ctx.fillStyle = bgColor;

      if (shape === 'rect') {
        const side = radius * 2;
        const rx = item.x - radius;
        const ry = item.y - radius;
        ctx.beginPath();
        if (typeof ctx.roundRect === 'function') {
          ctx.roundRect(rx, ry, side, side, 6);
        } else {
          ctx.rect(rx, ry, side, side);
        }
        ctx.fill();
        ctx.shadowColor = 'transparent';
        ctx.lineWidth = bWidth;
        ctx.strokeStyle = bColor;
        ctx.stroke();
      } else {
        ctx.beginPath();
        ctx.arc(item.x, item.y, radius, 0, 2 * Math.PI);
        ctx.fill();
        ctx.shadowColor = 'transparent';
        ctx.lineWidth = bWidth;
        ctx.strokeStyle = bColor;
        ctx.beginPath();
        ctx.arc(item.x, item.y, radius, 0, 2 * Math.PI);
        ctx.stroke();
      }

      ctx.fillStyle = item.style.textColor || '#ffffff';
      ctx.font = `bold ${fontSize}px sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(item.text || '1', item.x, item.y);
    }
    else if (item.type === 'box') {
      const shape = item.style.shape || 'rect';
      const w = item.width || 0;
      const h = item.height || 0;
      const radius = Math.min(item.style.borderRadius || 7, Math.min(Math.abs(w), Math.abs(h)) / 2);

      const buildBoxPath = () => {
        ctx.beginPath();
        if (shape === 'circle') {
          ctx.ellipse(item.x + w / 2, item.y + h / 2, Math.abs(w) / 2, Math.abs(h) / 2, 0, 0, 2 * Math.PI);
        } else if (radius > 0 && typeof ctx.roundRect === 'function') {
          ctx.roundRect(item.x, item.y, w, h, radius);
        } else {
          ctx.rect(item.x, item.y, w, h);
        }
      };

      if (item.style.backgroundColor && item.style.backgroundColor !== 'transparent') {
        ctx.save();
        ctx.globalAlpha = item.style.opacity !== undefined ? item.style.opacity : 0.3;
        ctx.fillStyle = item.style.backgroundColor;
        buildBoxPath();
        ctx.fill();
        ctx.restore();
      }

      ctx.strokeStyle = item.style.borderColor || '#ef4444';
      ctx.lineWidth = item.style.borderWidth || 2;
      ctx.setLineDash(item.style.lineStyle === 'dashed' ? [4, 4] : []);
      buildBoxPath();
      ctx.stroke();
    }
    else if (item.type === 'arrow') {
      const toX = item.x + (item.width || 0);
      const toY = item.y + (item.height || 0);
      drawArrow(
        ctx,
        item.x,
        item.y,
        toX,
        toY,
        item.style.borderColor || '#ef4444',
        item.style.borderWidth || 3,
        item.style.lineStyle || 'solid',
        item.style.headSize || 2
      );
    }
    else if (item.type === 'callout') {
      const x = item.x;
      const y = item.y;
      const w = item.width || 140;
      const h = item.height || 70;
      const borderRadius = item.style.borderRadius || 8;
      const tailX = item.style.calloutTailX !== undefined ? item.style.calloutTailX : x + w * 0.25;
      const tailY = item.style.calloutTailY !== undefined ? item.style.calloutTailY : y + h + 40;

      ctx.globalAlpha = item.style.opacity !== undefined ? item.style.opacity : 1.0;
      ctx.fillStyle = item.style.backgroundColor || '#eff6ff';
      ctx.strokeStyle = item.style.borderColor || '#3b82f6';
      ctx.lineWidth = item.style.borderWidth || 2;
      ctx.setLineDash(item.style.lineStyle === 'dashed' ? [4, 4] : []);

      traceSpeechRectPath(ctx, x, y, w, h, borderRadius, tailX, tailY);
      ctx.fill();
      ctx.stroke();

      ctx.globalAlpha = 1;
      drawCalloutText(ctx, item.text || '', x, y, w, h, item.style.textColor || '#3b82f6', item.style.fontSize || 14);
    }
    else if (item.type === 'text') {
      const fSize = item.style.fontSize || 16;
      ctx.font = `bold ${fSize}px sans-serif`;
      ctx.fillStyle = item.style.textColor || '#3b82f6';
      ctx.textBaseline = 'top';
      ctx.textAlign = 'left';

      const lines = (item.text || '').split('\n');
      const lineHeight = fSize * 1.2;

      if (item.style.backgroundColor && item.style.backgroundColor !== 'transparent') {
        let maxW = 0;
        lines.forEach(l => {
          const mw = ctx.measureText(l).width;
          if (mw > maxW) maxW = mw;
        });
        const bgW = maxW + 12;
        const bgH = (lines.length - 1) * lineHeight + fSize + 10;
        ctx.fillStyle = item.style.backgroundColor;
        ctx.fillRect(item.x - 6, item.y - 4, bgW, bgH);
        ctx.strokeStyle = item.style.borderColor || '#cbd5e1';
        ctx.lineWidth = 1;
        ctx.strokeRect(item.x - 6, item.y - 4, bgW, bgH);
      }

      ctx.fillStyle = item.style.textColor || '#3b82f6';
      lines.forEach((line, idx) => {
        ctx.fillText(line, item.x, item.y + idx * lineHeight);
      });
    }

    ctx.restore();
  }

  // 3. crop 처리
  if (cropRect && cropRect.width > 0 && cropRect.height > 0) {
    const cropCanvas = document.createElement('canvas');
    cropCanvas.width = cropRect.width;
    cropCanvas.height = cropRect.height;
    const cropCtx = cropCanvas.getContext('2d');
    cropCtx.drawImage(
      canvas,
      cropRect.x, cropRect.y, cropRect.width, cropRect.height,
      0, 0, cropRect.width, cropRect.height
    );
    return cropCanvas.toDataURL('image/png');
  }

  return canvas.toDataURL('image/png');
};
</script>
</body>
</html>
"""


def render_marked_image(
    png_bytes: bytes,
    resolved_items: list[dict[str, Any]],
) -> bytes:
    """Playwright Chromium Canvas를 통해 이미지 위에 마킹을 렌더링하고 출력 PNG 바이트를 반환한다."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright가 설치되어 있지 않습니다.") from exc

    b64_img = base64.b64encode(png_bytes).decode("ascii")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(CANVAS_RENDER_HTML)

        # 렌더링 실행 및 Base64 Data URL 수신
        result_data_url = page.evaluate(
            "([b64, items]) => window.renderMarking(b64, items)",
            [b64_img, resolved_items],
        )
        browser.close()

    if not result_data_url or not isinstance(result_data_url, str):
        raise RuntimeError("Canvas 렌더링 결과를 얻지 못했습니다.")

    # data:image/png;base64,... 분리
    _, b64_payload = result_data_url.split(",", 1)
    return base64.b64decode(b64_payload)


def mark_image(
    png_path: str | Path,
    draw_spec: str | Path | dict[str, Any] | list[Any],
    boxes_path: str | Path | None = None,
    out_path: str | Path | None = None,
) -> ToolResult:
    """원시 PNG 이미지 위에 draw_spec에 지정된 요소들을 마킹하여 새 PNG 파일로 저장한다."""
    p_png = Path(png_path).resolve()
    if not p_png.exists() or not p_png.is_file():
        return ToolResult(ok=False, error=f"원본 PNG 파일을 찾을 수 없습니다: {png_path}")

    # 출력 경로 결정
    if out_path:
        p_out = Path(out_path).resolve()
    else:
        stem = p_png.stem
        p_out = p_png.parent / f"{stem}-alpha.png"

    if p_out == p_png:
        return ToolResult(ok=False, error="원본 PNG 파일과 동일한 경로로 저장할 수 없습니다 (덮어쓰기 방지).")

    # draw_spec 로드
    raw_items: list[dict[str, Any]] = []
    if isinstance(draw_spec, (str, Path)):
        p_draw = Path(draw_spec)
        if p_draw.exists() and p_draw.is_file():
            try:
                draw_content = json.loads(p_draw.read_text(encoding="utf-8"))
            except Exception as e:  # noqa: BLE001
                return ToolResult(ok=False, error=f"draw.json 파일 파싱 실패: {e}")
        else:
            try:
                draw_content = json.loads(str(draw_spec))
            except Exception as e:  # noqa: BLE001
                return ToolResult(ok=False, error=f"draw.json 파일을 찾을 수 없거나 올바른 JSON이 아닙니다: {e}")
    else:
        draw_content = draw_spec

    if isinstance(draw_content, list):
        raw_items = draw_content
    elif isinstance(draw_content, dict):
        raw_items = draw_content.get("items", [])
    else:
        return ToolResult(ok=False, error="draw.json은 최상위 배열 또는 {'items': [...]} 형태여야 합니다.")

    # PNG 실제 크기 검사
    img_w, img_h = get_png_dimensions(p_png)
    if img_w <= 0 or img_h <= 0:
        return ToolResult(ok=False, error=f"유효한 PNG 이미지가 아니거나 크기를 읽을 수 없습니다: {p_png}")

    # boxes_path 로드
    boxes_data: dict[str, Any] | None = None
    resolved_boxes_path: Path | None = None
    if boxes_path:
        resolved_boxes_path = Path(boxes_path).resolve()
    else:
        # 자동 탐색: <name>.boxes.json
        candidate = p_png.parent / f"{p_png.name}.boxes.json"
        if candidate.exists():
            resolved_boxes_path = candidate
        else:
            candidate2 = p_png.with_suffix(".boxes.json")
            if candidate2.exists():
                resolved_boxes_path = candidate2

    if resolved_boxes_path and resolved_boxes_path.exists():
        try:
            boxes_data = json.loads(resolved_boxes_path.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            return ToolResult(ok=False, error=f"boxes.json 파일 읽기 실패: {e}")

        # 크기 불일치 검사
        box_img_size = boxes_data.get("image-size")
        if box_img_size and (box_img_size[0] != img_w or box_img_size[1] != img_h):
            return ToolResult(
                ok=False,
                error=f"PNG 실제 크기 {img_w}x{img_h}와 boxes.json의 image-size {box_img_size[0]}x{box_img_size[1]}가 일치하지 않습니다.",
            )

    # 좌표 해석
    try:
        resolved_items, warnings = resolve_draw_items(raw_items, boxes_data, (img_w, img_h))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=str(exc))

    # Canvas 렌더링
    png_bytes = p_png.read_bytes()
    try:
        output_bytes = render_marked_image(png_bytes, resolved_items)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, error=f"렌더링 실패: {exc}")

    # 파일 저장
    p_out.parent.mkdir(parents=True, exist_ok=True)
    p_out.write_bytes(output_bytes)

    out_w, out_h = get_png_dimensions(p_out)

    return ToolResult(
        ok=True,
        data={
            "input_png": str(p_png),
            "output_png": str(p_out),
            "input_size": [img_w, img_h],
            "output_size": [out_w, out_h],
            "item_count": len(resolved_items),
            "items": resolved_items,
            "warnings": warnings,
        },
    )
