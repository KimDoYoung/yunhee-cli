# boxes.json 규격 (screen-capture 요소 좌표 파일)

`yunhee screen-capture`가 PNG를 저장할 때 **그 PNG에 보이는 요소들의 위치**를 같은 시점에 함께 저장하는 파일의 규격이다.
`yunhee mark`(수정사항058)가 이 파일을 읽어, 요소 이름만으로 번호 원·사각형·화살표를 그린다(`draw.json` 규격은 11절).

- 상태: **초안**(2026-11-12). yunhee 요청 사항으로 구현 대기.
- 배경: 매뉴얼(A-Man)용 이미지는 버튼·행·팝업에 번호 배지, 빨간 사각형, 화살표를 그려 넣는다. 위치를 이미지에서 다시 찾는 것(OCR 등)보다 캡처할 때 DOM에서 바로 얻는 것이 정확하다.

## 1. 흐름

```
yunhee screen-capture 1412 --boxes
   → 01_initial.png + 01_initial.boxes.json
   → 05_popup_01_등록.png + 05_popup_01_등록.boxes.json

yunhee mark 01_initial.png draw.json --out 01_initial-alpha.png
   (draw.json 안의 "target": "등록" 을 boxes.json 에서 찾아 그린다)
```

## 2. 파일 위치와 이름

- PNG 하나마다 JSON 하나. **PNG와 같은 폴더, 같은 이름, 확장자만 `.boxes.json`.**
  - `01_initial.png` → `01_initial.boxes.json`
- 옵션: `--boxes`를 줄 때만 만든다(기본 꺼짐).
- `report.json`의 캡처 목록 항목에 `boxes` 키로 파일 이름을 적는다.

## 3. 파일 구조

```json
{
  "version": 1,
  "image": "05_popup_01_등록.png",
  "image-size": [1217, 680],
  "viewport": [1920, 1080],
  "scale": 1.0,
  "origin": [0, 0],
  "screen": "1412",
  "elements": [
    {
      "name": "등록",
      "kind": "button",
      "text": "등록",
      "box": [820, 62, 72, 28],
      "area": "main"
    }
  ]
}
```

| 키 | 설명 |
|:---|:---|
| `version` | 규격 버전. 지금은 `1`. |
| `image` | 대응하는 PNG 파일 이름. |
| `image-size` | PNG 실제 크기 `[너비, 높이]` (픽셀). `mark`가 크기 불일치를 검사한다. |
| `viewport` | 캡처 때 브라우저 뷰포트 `[너비, 높이]` (CSS 픽셀). |
| `scale` | PNG 픽셀 ÷ CSS 픽셀 (devicePixelRatio). 보통 `1.0`. |
| `origin` | PNG 왼쪽 위가 뷰포트의 어느 점인지 `[x, y]` (CSS 픽셀). 전체 화면 캡처는 `[0, 0]`, `--modal-only`는 모달 영역의 왼쪽 위. |
| `screen` | 화면번호(메뉴 번호). 모르면 생략. |
| `elements` | 요소 배열. 아래 4절. |

### 좌표 규칙 (가장 중요)

- **`box`는 PNG 이미지 기준 픽셀 좌표**이며 `[x, y, w, h]` (왼쪽 위 + 크기)이다.
  `mark`는 `box`를 그대로 쓰면 되도록, **yunhee가 변환해서 저장한다**:
  `box = ((rect.x - origin.x) * scale, (rect.y - origin.y) * scale, rect.w * scale, rect.h * scale)`
  (`rect`는 `getBoundingClientRect()`의 값. 스크롤이 있으면 뷰포트 기준이므로 그대로 쓴다.)
- 이미지 밖으로 걸친 요소는 이미지 영역으로 잘라(clip) 저장한다. 완전히 밖이면 넣지 않는다.
- 숨겨진 요소(`display:none`, 크기 0, 다른 탭, 가려져 PNG에 안 보이는 요소)는 넣지 않는다. **PNG에 보이는 것만** 기록한다.
- 정수로 반올림한다.

## 4. 요소 (`elements[]`)

| 키 | 필수 | 설명 |
|:---|:---:|:---|
| `name` | O | `draw.json`이 `target`으로 부르는 이름. 5절 규칙. 파일 안에서 **유일**해야 한다. |
| `kind` | O | 요소 종류. 6절 목록. |
| `box` | O | `[x, y, w, h]` (3절). |
| `text` | | 화면에 보이는 글자(버튼 문구, 라벨 문구 등). 없으면 생략. |
| `area` | | 속한 영역. `main`(본 화면) · `modal`(모달/팝업) · `lookup`(Lookup 모달). 여러 층이면 가장 위 층이 `modal`. |
| `parent` | | 이 요소가 속한 요소의 `name`(예: 모달 안 버튼 → 그 모달). 없으면 생략. |
| `row` | | 그리드 행 번호(1부터). 그리드 요소에만. |
| `col` | | 그리드 컬럼 헤더 이름. 그리드 요소에만. |
| `disabled` | | 비활성이면 `true`. 아니면 생략. |

## 5. 이름(`name`) 규칙

`mark`와 Claude가 사람 말로 가리킬 수 있어야 하므로, **화면에 보이는 글자를 이름으로 한다.**

1. 보이는 글자가 있으면 그것을 그대로: 버튼 `등록`, 라벨 `책무구분`.
   - 공백·줄바꿈은 한 칸으로 줄이고 앞뒤를 자른다. 글자 사이의 `저 장`처럼 넣은 공백은 **원문 그대로** 둔다(화면에 보이는 대로).
2. 같은 이름이 둘 이상이면 DOM 순서(위→아래, 왼→오)로 **`이름#2`, `이름#3`**을 붙인다. 첫 번째는 `#1`을 붙이지 않는다.
3. 글자가 없는 요소(아이콘 버튼, 체크박스)는 의미를 이름으로 한다:
   - 아이콘 버튼은 `aria-label`·`title`·아이콘 이름(`edit`·`delete`·`search`·`calendar`)에서 얻는다. 얻지 못하면 `icon#n`.
   - 체크박스는 옆 라벨 글자(`전체보기`). 라벨이 없으면 `checkbox#n`.
4. 그리드 요소는 아래 방식.
   - 컬럼 헤더: `헤더:책무유형` (kind `grid-header`).
   - 행: `grid1.행2` (kind `grid-row`, `row: 2`). 그리드가 하나뿐이면 `grid.행2`처럼 번호 생략.
   - 셀: `grid1.행2.책무유형` (kind `grid-cell`, `row: 2`, `col: "책무유형"`).
   - 행 안의 아이콘 버튼·체크박스: `grid1.행2.수정` (kind `grid-icon`) / `grid1.행2.체크` (kind `grid-check`).
   - 그리드 전체: `grid1` (kind `grid`).
5. 모달은 제목 글자: `책무`(kind `modal`), 제목 줄은 `책무:제목`(kind `modal-title`), 모달 안 요소는 `parent: "책무"`.
   - 이름이 같은 모달이 뜬 상태에서 또 뜨면 `#2`.

## 6. 요소 종류 (`kind`)

| kind | 대상 | 비고 |
|:---|:---|:---|
| `button` | 글자가 있는 버튼 (`<Button>`, ColorButtonBar 버튼 포함) | 글자는 `text` |
| `icon-button` | 아이콘만 있는 버튼(연필·돋보기·달력 등) | |
| `input` | 입력칸(텍스트·숫자·textarea) | `name`은 앞 라벨 글자 |
| `select` | 드롭다운 | 〃 |
| `date` | 날짜 선택칸 | 〃 |
| `checkbox` | 체크박스 | |
| `radio` | 라디오 | |
| `label` | 조회조건·폼의 라벨 글자 | |
| `tab` | 서브 탭 | |
| `grid` | 그리드 전체 영역 | |
| `grid-header` | 그리드 컬럼 헤더 셀 | `col` |
| `grid-row` | 그리드 한 행 전체 | `row` |
| `grid-cell` | 그리드 셀 | `row`, `col` |
| `grid-icon` | 셀 안의 아이콘 버튼 | `row`, `col` |
| `grid-check` | 행 선택 체크박스 | `row` |
| `modal` | 모달/팝업 전체(`.ant-modal-content`) | |
| `modal-title` | 모달 제목 줄 | |
| `toolbar` | 버튼 줄(조회·등록·삭제가 있는 줄) 전체 | |
| `search-bar` | 조회조건 줄 전체 | |

- 처음 구현은 **button·icon-button·input·select·date·checkbox·label·tab·grid·grid-header·grid-row·grid-cell·grid-icon·grid-check·modal·modal-title**이면 된다. 나머지는 필요할 때 더한다.
- 모르는 kind는 `mark`가 무시하지 않고 그대로 읽는다(새 kind를 더해도 호환).

## 7. 그리드 요소 범위

- 가상 스크롤이라 **DOM에 그려진 행만** 있다. 그 중 PNG에 보이는 행만 넣는다.
- 행·셀 수가 많아 파일이 커지므로 기본은 **행 20개까지**, 셀은 **`grid-icon`·`grid-check`와 헤더·첫 5행의 셀**만 넣는다(옵션으로 늘림).
- 행 번호는 **PNG에 보이는 행 순서(1부터)**이다. 데이터 정렬 순서가 바뀌면 번호가 바뀐다. 매뉴얼은 캡처 때의 번호로 쓴다.

## 8. 예 (1412 책무 등록: 등록 버튼 → 팝업)

```json
{
  "version": 1,
  "image": "05_popup_01_책무.png",
  "image-size": [1217, 680],
  "viewport": [1920, 1080],
  "scale": 1.0,
  "origin": [0, 0],
  "screen": "1412",
  "elements": [
    { "name": "조회", "kind": "button", "text": "조회", "box": [744, 64, 72, 28], "area": "main" },
    { "name": "등록", "kind": "button", "text": "등록", "box": [820, 64, 72, 28], "area": "main" },
    { "name": "삭제", "kind": "button", "text": "삭제", "box": [896, 64, 72, 28], "area": "main" },
    { "name": "grid1", "kind": "grid", "box": [0, 110, 1217, 570], "area": "main" },
    { "name": "grid1.행1.수정", "kind": "grid-icon", "row": 1, "col": "수정", "box": [30, 140, 24, 24], "area": "main" },
    { "name": "책무", "kind": "modal", "box": [255, 180, 635, 390], "area": "modal" },
    { "name": "책무:제목", "kind": "modal-title", "box": [255, 180, 635, 42], "area": "modal", "parent": "책무" },
    { "name": "책무구분", "kind": "select", "box": [375, 258, 475, 28], "area": "modal", "parent": "책무" },
    { "name": "저장", "kind": "button", "text": "저장", "box": [642, 522, 72, 28], "area": "modal", "parent": "책무" },
    { "name": "닫기", "kind": "button", "text": "닫기", "box": [730, 522, 72, 28], "area": "modal", "parent": "책무" }
  ]
}
```

(좌표는 이해를 위한 예시이며 실제 화면 값이 아니다.)

`draw.json`은 이 이름으로 가리킨다(11절 규격):

```json
{
  "version": 1,
  "items": [
    { "type": "box", "target": "등록" },
    { "type": "box", "target": "책무" },
    { "type": "circle-number", "text": "1", "target": "등록", "anchor": "top-right" },
    { "type": "circle-number", "text": "2", "target": "책무:제목", "anchor": "top-left" },
    { "type": "arrow", "from": "등록", "to": "책무:제목" }
  ]
}
```

## 9. 구현 메모 (yunhee 쪽)

- 요소 수집은 캡처 직전에 `page.evaluate`로 한 번에 모아 반환한다(요소마다 `bounding_box()`를 부르면 느리다).
- 수집 대상 선택자(참고): AntD `.ant-btn`, `.ant-input`, `.ant-select`, `.ant-picker`, `.ant-checkbox-wrapper`, `.ant-tabs-tab`, `.ant-modal-content`, `.ant-modal-title`; AG Grid `.ag-root`, `.ag-header-cell`, `.ag-row`, `.ag-cell`. 공통 부품(`ColorButtonBar` 등)이 별도 클래스를 쓰면 그것도 포함한다.
- 보이는지 판단은 기존 `screen_capture.py`의 `isVisible()`을 재사용한다.
- 같은 화면에서 PNG가 여러 장이면 각 PNG 직전에 따로 수집한다(팝업이 열린 시점, 탭이 바뀐 시점의 DOM이 다르므로).
- 검증: 수집한 `box`로 PNG에 빨간 사각형을 그려 눈으로 맞는지 확인하는 작은 테스트를 둔다(`scale`·`origin` 오류가 가장 흔하다).

## 10. 미정 사항

- 요소 `name`을 만들 때 AntD `Form.Item` 라벨을 어디까지 따라가 입력칸의 이름으로 삼을지.
- 행 아이콘이 있는 컬럼이 "수정" 같은 헤더 글자 없이 아이콘만인 경우의 이름(`col` 값).
- `--modal-only`일 때 `origin` 계산(모달 영역 padding을 포함할지).
- 한 화면 PNG가 많을 때 boxes.json 합계 용량(예상 수십 KB/장 이하).

---

## 11. draw.json 규격 (`yunhee mark`의 입력)

캡처 PNG 위에 **번호 원·강조 상자·화살표·말풍선·글자**를 그리고, 필요하면 가리거나 자른다. 구현은 수정사항058.

### 11.1 A-Man 이미지 편집기의 요소 어휘를 그대로 쓴다

A-Man(`~/work/aman/frontend/src/components/imageditor/`)에 사람이 쓰는 이미지 편집기가 이미 있다. 같은 요소 이름과 `style` 키를 쓰면
(1) 사람이 손으로 만든 기존 매뉴얼 이미지와 **같은 모양**이 나오고, (2) 나중에 `items`를 A-Man 편집기에 넣어 사람이 손볼 수 있다.
근거 코드: `image_editor_types.ts`(요소 모델), `image_items_defaults.ts`(기본값), `ActionImageEditor.tsx`(그리기), `canvasDrawHelpers.ts`·`arrowStamp.ts`·`calloutStamp.ts`.

### 11.2 파일 구조

```json
{
  "version": 1,
  "items": [ … ]
}
```

- 최상위가 배열이면 `items`로 본다(짧게 쓸 때).
- 그리는 순서: **`mask` → 나머지 `items`(배열 순서대로) → `crop`**. 번호 원이 상자 위에 오도록 뒤에 쓴다.

### 11.3 요소 공통 키 (A-Man `CanvasItem`과 같음)

| 키 | 설명 |
|:---|:---|
| `type` | 요소 종류(11.5). |
| `x`, `y` | 위치. 요소마다 기준이 다르다(11.5). 픽셀, PNG 기준. |
| `width`, `height` | 크기. `arrow`는 **끝점까지의 차이**(11.5). |
| `text` | 글자(번호 원의 숫자, 글, 말풍선 내용). |
| `style` | 모양. 키는 A-Man과 같다: `borderColor` `borderWidth` `backgroundColor` `textColor` `fontSize` `lineStyle`(`solid`/`dashed`) `opacity` `borderRadius` `shape` `rotation` `headSize` 등. **모두 생략 가능**(11.6 기본값). |

### 11.4 우리가 더한 키 (A-Man에 없음) — 이름으로 위치 지정

픽셀 좌표를 직접 쓰는 대신 `boxes.json`의 요소 `name`으로 가리킨다. `mark`가 이름을 찾아 `x, y, width, height`를 채운 뒤 그린다.

| 키 | 쓰는 요소 | 설명 |
|:---|:---|:---|
| `target` | 모든 요소 | boxes.json 요소 이름. 그 요소의 `box`가 곧 요소의 `x, y, width, height`(`box`·`mask`·`crop`) 또는 기준 상자(나머지). |
| `anchor` | `circle-number` `text` `symbol` | 대상 상자의 어느 지점에 놓을지: `top-left`(기본) `top` `top-right` `right` `bottom-right` `bottom` `bottom-left` `left` `center`. 번호 원은 **원의 중심**이 그 지점에 온다. |
| `offset` | 위 요소 | `[dx, dy]` 픽셀만큼 더 이동. 기본 `[0, 0]`. |
| `from`, `to` | `arrow` | 시작·끝. 각각 요소 이름 또는 `[x, y]`. 이름이면 **상대 요소를 향한 쪽 변의 가운데**를 쓴다(자동). |
| `side`, `gap` | `callout` `text` | 대상 상자의 어느 쪽(`top` `bottom` `left` `right`)에 `gap` 픽셀(기본 40) 떨어뜨려 놓을지. 말풍선 꼬리는 대상 상자의 가까운 변을 가리킨다. |
| `padding` | `box` `crop` | 대상 상자를 사방으로 `padding` 픽셀 키운다(강조 상자가 요소에 딱 붙지 않게). 기본 `box` 4, `crop` 0. |

- `target`과 `x/y/width/height`를 함께 쓰면 **직접 좌표가 우선**한다(`target`은 무시).
- **없는 이름은 오류**다(조용히 건너뛰지 않는다). 오류 메시지에 비슷한 이름 후보를 보여 준다(`등록` → `등록#2`, `신규등록`).
- `target` 하나가 boxes.json에서 모호한 경우(`#2`가 있는데 `등록`만 쓴 경우)는 첫 번째(`#1`)를 쓰고 경고한다.

### 11.5 처음 구현할 요소

| type | 용도 | 기준 | 비고 |
|:---|:---|:---|:---|
| `circle-number` | 번호 원 ①②… | `x, y` = **원의 중심**. 반지름 = `fontSize × 1.05`. | `text`는 숫자(문자열). `shape`: `circle`(기본)·`rect`. 약한 그림자 있음. |
| `box` | 강조 사각형(빨간 테두리) | `x, y` = **왼쪽 위**, `width, height`. | `shape`: `rect`(기본)·`circle`(타원). `backgroundColor`가 있으면 `opacity`(기본 0.3)로 채운다. |
| `arrow` | 화살표 | `x, y` = **시작점**, `width, height` = 끝점까지의 차이(`끝 = x+width, y+height`). | `style.headSize`(머리 크기, 기본 2). |
| `text` | 글자 | `x, y` = 왼쪽 위. 굵은 `sans-serif`. | 줄바꿈 `\n`. `backgroundColor`가 있으면 글 주위 배경 상자. |
| `callout` | 말풍선·설명선 | `x, y, width, height`(기본 140×70). | `style.calloutShape`: `speech-rect`(기본)·`speech-oval`·`line`. 꼬리 끝은 `style.calloutTailX/Y`(없으면 `target`에서 계산). |
| `mask` | 실데이터 가리기 | `target` 또는 `x, y, width, height`. | `style.mode`: `fill`(기본, 단색 `backgroundColor` 기본 `#9ca3af`)·`blur`·`pixelate`. 가장 먼저 그려 나머지가 위에 얹힌다. |
| `crop` | 영역만 남기기 | `target` 또는 `x, y, width, height`. | **마지막에** 적용. 영역 밖 요소는 버리고 안쪽은 좌표를 옮긴다(A-Man 편집기와 같은 동작). 출력 이미지 크기가 바뀐다. |

- 나중에 필요할 때 더할 요소(A-Man에 있음): `orthogonal-arrow`(꺾인 화살표, `style.orthogonalRouting`·`midX/midY`), `bracket-arrow`, `block-arrow-stamp`(손가락·커서·블록 화살표), `symbol`(이모지), `image`.
- 모르는 `type`은 오류다.
- `mask`와 `crop`은 A-Man 편집기 요소가 아니라 우리가 더한 것이다(편집기에 넣을 때는 제외).

### 11.6 기본값 (A-Man `SYSTEM_ITEM_DEFAULTS`와 같다 — 바꾸지 말 것)

| 요소 | 기본 |
|:---|:---|
| `circle-number` | 배경 `#ef4444`, 글자 `#ffffff`, 테두리 `#f59e0b` 굵기 3, `fontSize` 28, `shape` `circle` |
| `box` | 테두리 `#ef4444` 굵기 2, `lineStyle` `solid`, 배경 없음, `borderRadius` 7, `shape` `rect` |
| `arrow` | 색 `#ef4444`, 굵기 3, `lineStyle` `solid`, `headSize` 2 |
| `text` | 글자 `#3b82f6`, `fontSize` 16, 배경 없음 |
| `callout` | 배경 `#eff6ff`, 테두리 `#3b82f6` 굵기 2, 글자 `#3b82f6`, `fontSize` 14, `borderRadius` 8 |

- 색은 `#rrggbb`·`#rrggbbaa`·`transparent`. 색 이름(`red`)은 `red`·`blue`·`green`·`yellow`·`white`·`black` 정도만 허용하고 A-Man 기본 팔레트로 바꾼다(`red`=`#ef4444`, `blue`=`#3b82f6`, `green`=`#10b981`, `yellow`=`#ffff00`).
- 매뉴얼 이미지는 모두 이 기본 모양을 쓰는 것이 원칙이다(사람이 만든 이미지와 통일). `style`은 예외일 때만 쓴다.

### 11.7 `yunhee mark` 호출

```bash
yunhee mark 01_initial.png draw.json --out 01_initial-alpha.png
yunhee mark 01_initial.png draw.json            # --out 생략 = 01_initial-alpha.png
```

- `--boxes <파일>`: 기본은 PNG와 같은 이름의 `.boxes.json`. `target`이 없으면 필요 없다.
- `--json`: 해석된 최종 요소(이름 → 좌표)를 JSON으로 출력(디버깅·검증용).
- 검사: PNG 실제 크기와 boxes.json `image-size`가 다르면 오류. 원본 PNG는 덮어쓰지 않는다.

### 11.8 예 (1412 책무 등록: 등록 → 팝업, 삭제 대상 행)

```json
{
  "version": 1,
  "items": [
    { "type": "mask", "target": "grid1.행3.책무유형" },
    { "type": "box", "target": "등록" },
    { "type": "box", "target": "책무" },
    { "type": "circle-number", "text": "1", "target": "등록", "anchor": "top-right" },
    { "type": "circle-number", "text": "2", "target": "책무:제목", "anchor": "top-left" },
    { "type": "arrow", "from": "등록", "to": "책무:제목" },
    { "type": "callout", "text": "필수 입력", "target": "책무구분", "side": "right" }
  ]
}
```

### 11.9 구현 메모

- **권장 구현: Playwright(헤드리스 Chromium)로 Canvas 2D에 그린다.** yunhee가 이미 Chromium을 쓰고, A-Man의 그리기 코드(`drawArrow`, `drawCallout`, `roundRect` 등)를 거의 그대로 옮길 수 있어 모양이 같다. 한글 글꼴도 브라우저가 처리한다.
  Pillow로도 가능하지만 화살표 머리·그림자·말풍선 꼬리를 다시 만들어야 하고 모양이 달라지기 쉽다. 어느 쪽이든 이 규격은 같다.
- **합격 기준**: 같은 `items`를 A-Man 편집기와 `yunhee mark`로 각각 그려 눈으로 같은 모양인지 비교한다(번호 원 크기·그림자, 상자 모서리, 화살표 머리).
- `mask`의 `blur`·`pixelate`는 규격에만 두고 처음 구현은 `fill`만 해도 된다.

### 11.10 미정 사항

- `crop` 뒤에 새 이미지에 맞춰 boxes.json도 옮겨 저장할지(여러 단계로 그릴 때 필요).
- 대상 상자가 이미지 가장자리에 있어 번호 원이 이미지 밖으로 나갈 때 안쪽으로 밀지 그대로 잘릴지.
- `mask`의 기본 색.
