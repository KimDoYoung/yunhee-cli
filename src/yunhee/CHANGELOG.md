# yunhee 변경 이력

버전을 올릴 때 맨 위에 `## [버전] - YYYY-MM-DD` 항목을 추가한다 (`yunhee changelog`가 이 파일을 읽는다).

## [0.9.5] - 2026-11-13
수정사항 064 반영: `biz-appr` 결재 연동 안전성 및 유연성 보강 · `biz-authz` / `biz-endpoints` 권한 진단 정밀화 · `biz-orphans` 신설 및 `api` 데이터 추적 강화 · `compare` & `sql` 쿼리 검증 정밀화 · `trace-crud` 도달 불가 분기 인지 · `log trace` 로컬 8080 폴백
- **`biz-appr`: 결재 연동 안전성 및 옵션 확장 (`src/yunhee/tools/biz/appr.py`, `src/yunhee/cli.py`)**:
  - `seed_data` 부재 시 `AttributeError` 방어 가드 적용 (`#1`).
  - `--title`, `--content` 옵션 지원으로 문서 제목/본문 직접 지정 가능 (`#1`).
  - `--link-body` 템플릿 지원 (`{ref}`, `{id}`, `{apprId}`) 및 미등록 코드에 대한 후보 API 제안 (`#10`).
  - 결재자 로그인 실패 시 실패한 계정/회사/사유 상세 안내 (`#1`).
- **`biz-endpoints` & `biz-authz` 진단 정밀화 (`src/yunhee/tools/biz/endpoints.py`, `src/yunhee/tools/biz/authz.py`, `src/yunhee/cli.py`)**:
  - `biz-endpoints`: target 생략 시 전체 컨트롤러 스캔 지원, 복수/쉼표 구분 다중 `--screen` 필터링 지원 (`#6`).
  - 서비스 내부 진입부 검사 메서드(`check*`, `require*`, `verify*`, `load*`)를 `서비스내부(메서드명)` 가드로 인식하여 `⚠없음` 허위 경고 제외 (`#7`).
  - `biz-authz --probe-write`: 쓰기 API 200 반환 시 실제 행 생성 경고 표기 및 `--dry-run` 사전 시뮬레이션 지원 (`#9`).
  - `biz-authz --lint-delete-by-id`: DELETE API에서 companyId 조건 누락 취약점 검출 정적 린터 신설 (`#13`).
- **`biz-orphans` 신설 및 `api` 자식 추적 (`src/yunhee/tools/biz/orphans.py`, `src/yunhee/tools/api_client.py`, `src/yunhee/cli.py`)**:
  - `yunhee biz-orphans <table>`: FK 부모-자식 관계 기반 고아(orphan) 행 탐색 및 컨트롤러 자식 행 삭제 누락 진단 (`#4`).
  - `yunhee api --track <table> --children`: 부모 테이블뿐 아니라 연관 FK 자식 테이블 행 수 변화도 함께 추적 (`#4`).
  - `api --fields`: 미존재 필드 요청 시 difflib 오타 추천 및 경고, 누락 필드는 `-`로 표기 (`#2`).
  - `api`: 400 Validation failed 에러 상세 원인 추출 요약, rows=0 응답 시 미사용 선택 파라미터(`?`) 힌트 제공 (`#8`, `#14`).
- **`compare` & `sql` 쿼리 검증 정밀화 (`src/yunhee/tools/comparator.py`, `src/yunhee/tools/as_is/mybatis_render.py`, `src/yunhee/tools/sql_runner.py`)**:
  - `${isPostgreSql}` = true, `${isOracle}` = false 자동 바인딩 및 OGNL 리터럴 평가 지원 (`#3`).
  - 미치환 `${...}` 잔존 시 경고 출력 및 불완전 SQL 실행 결과 신뢰 경고 (`#3`).
  - 필수 파라미터 누락 시 사전 안내 출력 (`#3`).
  - `sql --rollback`: 트랜잭션 내에서 DDL 실행을 허용하는 `--allow-ddl` (`--ddl-in-tx`) 옵션 지원 (COMMIT은 안전 차단 유지) (`#12`).
- **`trace-crud` 비도달 메서드 감지 및 `log trace` 로컬 폴백 (`src/yunhee/tools/trace/crud.py`, `src/yunhee/tools/log_reader.py`, `src/yunhee/tools/outliner.py`)**:
  - AS-IS 화면 내 미호출/도달 불가 메서드에서만 실행되는 D(Delete) 작업은 `ASIS RU(D 도달 불가)`로 표기하여 허위 누락 경고(`⚠ TOBE에 D 없음`)에서 자동 제외 (`#5`).
  - `log trace` / `log errors`: Docker 소스 미발견 시 로컬 8080 로그(`YUNHEE_LOG_DIR` / `~/tmp/asseterp-data/logs`) 자동 폴백 (`#11`).
  - `outliner.py`: 허용 읽기 경로에 로그 디렉터리(`LOG_DIR`, `YUNHEE_LOG_DIR`, `~/tmp`) 포함 (`#11`).
수정사항 061, 062, 063 통합 반영: `compare` 정합성 및 파라미터 보완 · `biz-appr` 결재 연동 확장 · `api` / `sql` / `analysis` 유틸리티 강화 · `biz-endpoints` & `biz-authz` 진단 도구 고도화 · `biz-event-new` 문서 자동 생성 지능화 · `grep` & `drift` 편의성 개선
- **`compare`: URL 쿼리 파라미터 보존, 사원 정보 자동 보충 및 0 바인딩 경고 (`src/yunhee/tools/comparator.py`)**:
  - API 경로에 포함된 쿼리 스트링(`?k=v`)을 `api_params`에 자동 병합하여 누락 방지 및 `API params:` 라인 출력 (`061 #8`).
  - 로그인 사원 정보(`userId`, `personId`, `orgId`, `companyId`)를 미입력 SQL 파라미터에 자동 채우고 불일치 수동 입력 시 경고 (`062 #2`).
  - 파라미터 값이 0일 때 MyBatis dynamic SQL `!= null` 검사 경고 출력 (`062 #1 방안 2`).
- **`biz-appr`: 전자결재 연동 코드 확장, 선행 데이터 자동 생성 및 복수 ref 지원 (`src/yunhee/tools/biz/appr.py`, `src/yunhee/cli.py`)**:
  - `A02`, `A05`, `X01`, `A63`, `A64` 연동 코드 기본 등록 및 미등록 시 안내 후 차단 (`061 #3, #9`).
  - `--pre '<METHOD> <path> <json>'` 옵션 추가로 상신 전 선행 업무 데이터 자동 생성 후 결재 연동 (`061 #4`).
  - 복수 `--ref` 지정 및 `ids-body` 스타일 지원, 커스텀 `--link-path`, `--seed-arg` 지원.
- **`api --get` 및 SQL 읽기전용 함수 반환 경고 (`src/yunhee/cli.py`, `src/yunhee/tools/sql_runner.py`)**:
  - `yunhee api --get <path>`: 응답 JSON에서 특정 키/경로의 값만 머리말 없이 단일 텍스트로 추출 (스크립트 바인딩용, `062 #4`).
  - read-only 쿼리에서 `nextval`, `f_create_seq` 등 쓰기 함수가 NULL을 반환할 때 원인 안내 경고 메시지 출력 (`062 #3`).
- **`analysis function` 신설 (`src/yunhee/tools/analysis/function.py`, `src/yunhee/cli.py`)**:
  - 색인된 PostgreSQL DB 함수(SP) 마크다운 및 본문 소스 정밀 추출 (`-o md|code`, `--lines A-B`, `--grep 패턴`, `062 #5`).
- **`biz-endpoints` & `biz-authz` 고도화 (`src/yunhee/tools/biz/endpoints.py`, `src/yunhee/tools/biz/authz.py`, `src/yunhee/cli.py`)**:
  - 컨트롤러 클래스명 직접 지원(`AstRelateApprController`), 요약에 `⚠없음 N개(쓰기 a·조회 b)` 명시 (`062 #6`).
  - `--path` 복수/쉼표 지원 및 `--screen <번호>` 연관 API 자동 필터링 (`063 #5`).
  - 선택 파라미터 기본값 채우기, 404 DATA_NOT_FOUND 처리, rows=0 항목은 `⚠?(0행)`으로 분류하여 ⚠ 카운트 제외 (`061 #5`).
  - `--probe-appr`: 결재 ID 바꿔치기(apprId=1) 시험 및 try/finally 원복 보장 (`061 #6`).
- **`biz-event-new` 문서 자동 생성 지능화 (`src/yunhee/tools/biz/eventdoc.py`)**:
  - "따라 하기" 단계에서 비버튼 위젯 잡음 제거, 확인창 `(확인창 [예])` 결합, 팝업 단계명(`#{screen} → {popup}`) 표기 (`063 #4`).
  - 앞선 관련 이벤트(`> 관련 이벤트: ...`) 및 `<!-- 다음 의심 번호: #N -->` 자동 삽입 (`061 #7`).
  - 업무 규칙에 화면 쓰기 API 표 및 biz-authz 후속 검사 안내 자동 연동 (`063 #4`).
- **`grep` 옵션 편의성 개선 (`src/yunhee/tools/outliner.py`, `src/yunhee/cli.py`)**:
  - `yunhee grep -c/--count`: 파일별 일치 줄 수(`파일:건수`) 출력 (`063 #1`).
  - `-n`(줄 번호), `-r`(재귀) no-op 호환 옵션 추가 (`063 #1`).
  - 모르는 옵션 입력 시 사용 가능한 옵션 안내 가이드 출력 (`063 #1`).
- **`drift` 줄바꿈(CRLF) 판별 및 대장 해당없음 공유 변경 단위 제외 (`src/yunhee/tools/as_is/drift.py`, `src/yunhee/cli.py`)**:
  - `--strict` 미지정 시 줄바꿈(CRLF) 및 끝 공백 차이를 기본 무시하여 `+0/-0 (줄바꿈만)`으로 동일 판정 (`063 #2`).
  - `drift --record`: 줄바꿈만 바뀐 경우 `--force` 없이 `줄바꿈만 바뀜 → 기준 이동`으로 자동 기록 (`063 #2`).
  - `drift --done-only`: 대장에 `해당없음`/`반영` 처리된 공유 변경 단위를 호출하지 않는 화면을 변경 목록에서 제외하고 `판단 끝난 공유 변경 n건 제외` 요약 표시 (`063 #3`).

## [0.9.3] - 2026-11-13
수정사항 060 반영: 업무분석용 `biz-*` 명령 묶음 및 API 로그인 계정 보호 강화
- **TOBE API 엔드포인트 목록 및 DTO 분석 (`yunhee biz-endpoints`)**:
  - 도메인명 또는 컨트롤러 소스 경로 기반으로 전체 API 엔드포인트 수집 (`-o md|json|tsv`, `--path` 경로 필터).
  - 메서드, HTTP 경로, 파라미터/쿼리, 요청 DTO, 서비스 호출 메서드, 인가 권한 검사 여부를 구조화하여 일괄 출력.
- **도메인 API 권한 훑기 및 BOLA/IDOR 검사 (`yunhee biz-authz`)**:
  - 사원 권한(`-u`, 기본 401)으로 도메인 API를 호출하여 관리자 자료 노출 여부 기계적 판정.
  - `--probe-write` (빈 본문 안전 프로빙), `--probe-delete`, `--emit-rows` (보안 의심 행 마크다운 보고서) 지원.
- **전자결재 상신·업무 행 연결·결재자 승인 자동화 (`yunhee biz-appr`)**:
  - 전자결재 연동 코드(`link_code`, 예: A74, A73) 및 업무 행 ID(`--ref`) 기반으로 상신부터 결재선 순차 승인(`--confirm`) 및 반려(`--reject`) 원스톱 실행.
  - `--dry-run` 지원으로 상신 본문 JSON 사전 확인 가능.
- **조회(GET) 데이터의 지정 필드 부분 수정(PUT) 및 안전 검증 (`yunhee biz-patch`)**:
  - 기존 데이터 조회 $\to$ 지정 필드(`--set key=val`) 수정 $\to$ 저장(PUT) 및 미지정 필드 유실 여부 검증.
  - 목록 응답 처리(`--list`, `--where`), 읽기 전용 접미사 자동 제거(`--drop-suffix`), `--dry-run` 지원.
- **공통코드 조회 및 f_cdnm 규칙 검증 (`yunhee biz-code`)**:
  - `sys08_code_kind`, `sys09_code` 테이블 기반 공통코드 목록 및 회사별 우선 적용 행(`f_cdnm` 규칙) 표 형식 출력.
  - `--like` 검색어 및 오타 시 비슷한 종류 코드 자동 추천.
- **로컬 DB 안전 SQL 실행 및 자동 백업 (`yunhee biz-db-write`)**:
  - 로컬 DB(`127.0.0.1`/`localhost`) 대상 쓰기 전용 실행기. 실행 전 스키마/데이터 자동 백업(`data/backup/`).
  - 트랜잭션 안전 가드: `--dry-run` (자동 롤백), DDL 및 WHERE 절 없는 UPDATE/DELETE 차단 (`--allow-ddl`로 해제).
- **이벤트 분석 문서 틀 자동 생성 (`yunhee biz-event-new`)**:
  - 이벤트 ID 및 연관 화면 번호(`--screens`) 지정 시 AS-IS/TOBE 화면 색인을 결합하여 업무분석 마크다운 문서 뼈대 자동 생성.
- **API 로그인 보안 및 세션 잠금 방지 (`src/yunhee/tools/api_client.py`)**:
  - `--password` 직접 지정 옵션 추가 (DB 및 환경변수보다 최우선).
  - 회사 지정 시 회사 소속 사원 우선 매핑, 연속 실패 시 계정 잠금 경고 및 강제 시도 플래그(`--force-login`) 지원.

## [0.9.2] - 2026-11-12
수정사항 059 반영: `--boxes` 및 `mark` 7가지 결함 보완 (가려진 요소 배제 · 레이어 격리 네이밍 · 아이콘 헤더 매핑 · 체크박스 정합성 · 미지원 type 차단 · 팝업 폼 라벨 취득 · 바깥 앵커)
- **팝업에 가려진 본 화면 요소 자동 배제 (`src/yunhee/tools/screen_capture.py`)**:
  - `document.elementFromPoint` 기반 다중 샘플링 검사(`isElementCovered`)를 도입하여 모달 마스크나 창 뒤에 가려져 보이지 않는 본 화면(`area: main`) 요소를 `.boxes.json` 수집에서 완전 제외.
- **레이어(main vs modal) 단위 요소 이름 번호 매기기 (`src/yunhee/tools/screen_capture.py`)**:
  - `layerKey`를 기준으로 번호 카운트를 격리하여, 본 화면의 요소 존재 여부에 관계없이 모달 내부 요소가 전체 캡처와 `--modal-only` 캡처에서 일관된 이름(`책무구분`, 불필요한 `#2` 제거) 유지.
- **아이콘 컬럼 헤더 및 셀 이름 ID 매핑 (`src/yunhee/tools/screen_capture.py`)**:
  - `__rownum` $\to$ `헤더:번호` / `grid1.행1.번호`, `ag-Grid-SelectionColumn` $\to$ `헤더:선택` / `grid1.행1.선택` 고정 매핑.
  - 글자 없는 아이콘 컬럼은 바로 왼쪽 헤더 글자와 결합하여 `헤더:세부내용 수정`, `grid1.행1.세부내용 수정` 등 사람이 식별 가능한 이름으로 자동 매핑.
- **행 체크박스 이름 및 크기 정합성 확보 (`src/yunhee/tools/screen_capture.py`)**:
  - 행 선택 체크박스는 `grid1.행1.선택`, 값 체크박스는 컬럼 헤더 이름(`grid1.행1.공통책무`)으로 분기.
  - 셀 안쪽 체크박스 크기를 내부 박스 기준 16x16 픽셀 크기로 정밀 보정.
- **`mark`: 지원되지 않는 `type` 오류 차단 및 추천 (`src/yunhee/tools/marker.py`, `src/yunhee/cli.py`)**:
  - 알려지지 않은 type 입력 시 무시되지 않고 `ValueError` 발생, 종료코드 1 및 출력 파일 미생성 가드 강제.
  - `difflib` 기반 오타 후보 추천(예: `circel-number` $\to$ `circle-number`) 및 향후 지원 예정 타입(`orthogonal-arrow` 등) 별도 안내.
- **팝업 안 폼 요소 라벨 및 모달 이름 충돌 방지 (`src/yunhee/tools/screen_capture.py`)**:
  - 모달 창 이름을 `[이름](모달)`로 명명하여 내부 라벨과의 이름 충돌 원천 방지.
  - AntD `Form.Item` 안의 라벨(왼쪽/오른쪽)을 체크박스/라디오 및 textarea 이름으로 정확히 추출.
- **`mark`: 대상 상자 바깥 배치 `anchor` 지원 (`src/yunhee/tools/marker.py`)**:
  - `outside-top-left`, `outside-top`, `outside-top-right`, `outside-bottom-*`, `outside-left`, `outside-right` 8종 앵커 추가.
  - 대상 요소의 텍스트를 가리지 않고 `radius` 및 `gap`(기본 4px)만큼 대상 테두리 바깥으로 이격 배치.

## [0.9.1] - 2026-11-12
수정사항 058 반영: `mark` 캡처 PNG 위에 번호 원·강조 상자·화살표·말풍선·마스킹 렌더링 (A-Man 매뉴얼 이미지 자동 제작)
- **A-Man 호환 매뉴얼 이미지 마킹 도구 (`src/yunhee/tools/marker.py`, `src/yunhee/cli.py`)**:
  - `yunhee mark <png> <draw.json> [--boxes <boxes.json>] [--out <png>] [--json]` 신설.
  - A-Man 이미지 편집기(`CanvasItem`, `SYSTEM_ITEM_DEFAULTS`, `drawArrow`, `traceSpeechRectPath`)와 100% 동일한 렌더링 어휘 및 모양 지원.
  - `boxes.json` 요소 이름 기반 위치 참조(`target`, `anchor`, `padding`, `side`, `gap`, `from`/`to` 변 중앙 자동 연결).
  - 유효성 검사 및 유사 이름 추천: 존재하지 않는 `target` 시 `difflib` 기반 비슷한 후보 목록 출력 및 에러 차단.
  - 렌더링 순서 보장: `mask` (실데이터 가림 단색 fill) $\to$ 일반 요소 $\to$ `crop` (영역 잘라내기).
  - 원본 PNG 보존 및 안전 가드: 원본 이미지를 덮어쓰지 않고 `<이름>-alpha.png`로 저장.
  - Playwright Chromium Canvas 2D 기반으로 외부 무거운 의존성 없이 정밀 픽셀 렌더링.

## [0.8.9] - 2026-11-12
수정사항 057 반영: `screen-capture --boxes` 화면 요소 좌표 파일(`*.boxes.json`) 함께 저장
- **DOM 요소 좌표 일괄 수집 및 `.boxes.json` 생성 (`src/yunhee/tools/screen_capture.py`, `src/yunhee/cli.py`)**:
  - `yunhee screen-capture`에 `--boxes` 플래그 추가 (기본 꺼짐, 지정 시 PNG마다 동일 이름의 `.boxes.json` 생성).
  - 브라우저 단 1회의 `page.evaluate` JS 실행으로 화면에 보이는 16종 UI 요소(`button`, `icon-button`, `input`, `select`, `date`, `checkbox`, `radio`, `label`, `tab`, `grid`, `grid-header`, `grid-row`, `grid-cell`, `grid-icon`, `grid-check`, `modal`, `modal-title`) 좌표 및 메타데이터 일괄 수집.
  - 좌표 변환: 브라우저 CSS 픽셀을 실제 PNG 이미지 픽셀 기준으로 변환(`((rect - origin) * scale)`), 경계 밖 요소 클리핑, 정수 반올림.
  - `--modal-only` 지원: 잘라낸 모달의 border-box `(left, top)`을 `origin`으로 삼아 모달 내부 요소의 상대 좌표 자동 보정.
  - 유일한 이름 명명: 화면 노출 글자 우선 적용, 중복 이름 발생 시 DOM 순서 기반 `이름#2`, `이름#3` 번호 매김.
  - 그리드 계층 명명: `grid1`, `헤더:컬럼`, `grid1.행1`, `grid1.행1.컬럼`, `grid1.행1.수정`, `grid1.행1.체크` 등 구조화 및 가시 영역 최대 20행·첫 5행 셀 제한으로 파일 경량화.
  - 리포트 연동: `report.json`의 `captures` 항목에 `boxes` 키로 해당 JSON 파일명 기록 및 콘솔 출력 연동.

## [0.8.8] - 2026-11-11
수정사항 055 반영: `drift-done` 대장 칸 동적 매핑, `확인` 칸 지원 및 검증, 파일 기준선 범위 정상화 / `drift-diff` SQL statement 블록 격리 diff
- **대장 표 머리줄 기반 열 동적 위치 매핑 (`src/yunhee/tools/as_is/drift_ops.py`, `src/yunhee/cli.py`)**:
  - `drift-done` 및 `drift-ledger`에서 대장 표 헤더(`| 키 | ... |`)를 정적 분석하여 컬럼 위치(`키`, `상태`, `확인`, `처리일`, `비고`, `TOBE 대응` 등)를 동적으로 찾아 값을 기록.
  - 12칸 대장(`확인` 칸 신설)에서 발생하던 한 칸 밀림 버그 원천 해결 및 열 순서가 변경된 커스텀 대장에서도 완벽 지원.
  - 머리줄과 칸 수가 다른 줄은 수정하지 않고 경고 로깅, 필수 칸(`키`, `상태`, `처리일`) 누락 시 안전하게 중단.
  - `--dry-run`: 실제 대장 및 `baseline.json`을 수정하지 않고 전/후 변경 diff 미리보기 출력.
- **`확인` 칸 관리 및 `--status 반영` 엄격 검증 (`src/yunhee/tools/as_is/drift_ops.py`, `src/yunhee/cli.py`)**:
  - `--check "<문구>"` 옵션 추가: `확인` 칸에 반영 방법/근거(compare 일치, 테스트 클래스명 등) 기록.
  - `--status 반영`일 때 `--check`가 없고 기존 `확인` 칸도 비어 있으면 작업을 중단하고 경고 (`--force` 지정 시에만 강제 진행). `해당없음`/`보류`/`넘김`은 `--check` 생략 가능.
  - `--tobe "<파일·id>"` 옵션 추가: 대장의 `TOBE 대응` 칸을 직접 갱신 가능.
  - `--note` 기본 덮어쓰기 및 `--note-append` 옵션 신설: 기존 비고 뒤에 ` · <note>`로 안전하게 덧붙이기 지원.
- **파일 기준선(`__files__`) 보류 로직 및 화면 변경 감지 누락 방지 (`src/yunhee/tools/as_is/drift_ops.py`, `src/yunhee/tools/as_is/drift.py`)**:
  - 단위 하나 처리 시 파일 전체를 `__files__`로 갱신하던 문제를 해결하여, 대장 내 해당 파일의 바뀐 단위 중 `대기` 상태가 남아있으면 `__files__` 갱신을 보류하고 `__units__`만 갱신(`파일 기준선 보류: ... 대기 단위 n건`).
  - 해당 파일의 모든 단위가 처리되었을 때만 `__files__` 기준선 최신화.
  - `drift`(화면 drift)에서 파일 내 특정 단위 하나만 완료되어 있어도 파일 전체를 스킵하던 버그를 제거하여, 미완료 단위가 남아있는 화면이 변경 없음으로 누락되는 문제 차단.
- **`drift-diff <ns.id>` SQL statement 블록 단위 격리 diff (`src/yunhee/tools/as_is/drift_ops.py`)**:
  - SQL 단위 비교 시 파일 전체 git diff를 출력하던 문제를 해결하고, 기준 커밋과 현재 작업 트리의 대상 `<select|insert|update|delete id="...">` 블록만 추출하여 블록 대 블록 unified diff(`-w` 공백 무시) 수행.
  - 신규 생성 블록(`[신규 추가]`), 삭제된 블록(`[삭제됨]`), 동일 블록(`(해당 SQL 변경 없음)`)을 명확히 구분.
  - 해당 SQL이 참조하는 `<include refid="...">` 조각의 변경 diff 덧붙이기 및 `resultMap` 신규 컬럼 변경 요약 출력.
  - TOBE 대응 매핑 시 단순 ID 일치가 아닌 네임스페이스(`ns.sid`) 및 AS-IS 주석 일치 기준으로 정밀 필터링하여 무관한 타 파일 매퍼 노출 차단.
수정사항 054 반영: 변경반영용 `drift-*` 명령군 (단위 감지·대장·파일 기준선) 및 호출 색인 누락 보완
- **`drift-unit` 바뀐 파일의 SQL ID·메서드·UI·모델 단위 세분화 (`src/yunhee/tools/as_is/drift_ops.py`, `src/yunhee/cli.py`)**:
  - 변경된 파일 전체가 아닌 hunk가 걸친 `<select|insert|update|delete id="...">` 및 자바 메서드(`Class#method()`) 단위로 분해.
  - 단위마다 영향받는 화면 번호(`#1029`), TOBE 대응 후보, 변경 줄 수, 마지막 커밋 표시. 쓰는 화면 없는 단위는 접어서 표시(`--all-units` 지원).
- **파일·단위 기준선 + `drift-done` (`src/yunhee/tools/as_is/drift.py`, `src/yunhee/tools/as_is/drift_ops.py`, `src/yunhee/cli.py`)**:
  - `baseline.json`에 `__units__` 및 `__files__` 기준선을 함께 관리.
  - `drift-done <키…|단위…> [--status 반영|해당없음] [--note "…"]` 명령으로 단위/파일 기준선을 최신 커밋으로 이동하고 대장의 상태·처리일·비고를 자동 기록.
  - `drift`(화면 단위)에서 파일이 변경되었더라도 해당 파일 또는 연관 단위가 `drift-done`으로 반영/해당없음 처리되어 있으면 화면 변경 목록에서 제외하여 "동일" 판정.
- **`drift-ledger` (= `drift-list`) 대장 자동 덧붙이기 및 갱신 (`src/yunhee/tools/as_is/drift_ops.py`, `src/yunhee/cli.py`)**:
  - `drift-unit` 결과를 `docs/3-변경반영/변경반영-대장.md` 끝에 `CH-` 다음 번호를 매겨 `대기` 행으로 자동 덧붙임 (`--dry-run` 지원).
  - 같은 단위가 이미 `대기` 상태로 존재하면 최신 커밋·변경 요약만 갱신.
- **`drift-diff <단위>` AS-IS diff 및 TOBE 대응 비교 (`src/yunhee/tools/as_is/drift_ops.py`, `src/yunhee/cli.py`)**:
  - 단일 SQL ID 또는 Java 메서드의 AS-IS hunk diff와 TOBE 매퍼 문장/서비스 메서드 본문을 나란히 출력.
- **`drift-db` DBML 스냅샷 구조 차이 비교 (`src/yunhee/tools/as_is/drift_ops.py`, `src/yunhee/cli.py`)**:
  - 이전 DBML과 새 DBML 간 테이블 추가/삭제, 컬럼 추가/삭제/타입 변경, DB 함수 추가/삭제/본문 변경을 비교 추출.
- **`drift-log` 기준 이후 커밋 요약 (`src/yunhee/tools/as_is/drift_ops.py`, `src/yunhee/cli.py`)**:
  - 기준선/커밋 이후 변경된 파일들을 커밋별로 종류(DB·SQL·LOGIC·MODEL·UI·ETC)별 개수로 접어 1줄 요약 출력.
- **호출 색인 누락 보완 (`src/yunhee/tools/as_is/src_indexer.py`)**:
  - `new ServiceRequest("ics.Ics32_RelateAppr.selectApprList")` 생성자 인자 추적.
  - `serviceName = "dcr.Dcr00_DocList.selectNoAuthByText"` 등 변수에 할당되거나 분기문에 나타난 서비스 키 리터럴 인식.
  - 서버 `sqlSession.selectList(mapperName + ".selectApprList", ...)` 형태의 동적 문자열 결합 SQL 호출 추적.
  - 매퍼 `<include refid="..."/>` 조각 의존성 전파.
수정사항 053 반영: `run` 시험 요약 개선, `trace-crud` `INSERT…SELECT` 대상 R 오탐 해소 및 근거(`--why`), `compare` 파라미터 자동 상속·`--no-grid`, 메뉴 없는 클래스 역추적(`analysis ui`, `drift`), 호출자 탐색(`grep -l`, `analysis callers --server`)
- **`run "gradle test …"` 복수 테스트 클래스 합산 및 상세 분석 (`src/yunhee/tools/runner.py`, `src/yunhee/context/run_analyzer.py`, `src/yunhee/tools/analysis/run.py`)**:
  - `re.findall` 기반 복수 `--tests` 패턴 필터링을 지원하여 여러 테스트 클래스를 동시에 실행했을 때 마지막 클래스만 세던 문제를 해결하고 전체 합산(`tests 14 ... · 클래스 3`) 표기.
  - `yunhee analysis run last --tests`에서 실패한 테스트의 `클래스.메서드`명과 `failure message` 첫 줄, 프로젝트 스택(`kr.co.kfs...` 등) 한 줄을 함께 출력하여 로그를 수동으로 열어보지 않고도 원인을 즉시 파악 가능.
- **`trace-crud` `INSERT … SELECT` 대상 테이블 쓰기 전용 판정 및 근거(`--why`) (`src/yunhee/tools/sql_parse.py`, `src/yunhee/tools/trace/crud.py`, `src/yunhee/tools/trace/__init__.py`)**:
  - `<choose>` 분기에서 문법 에러로 정규식 fallback 발생 시 `INTO` 뒤의 대상 테이블을 R(읽기)로 오탐하여 `RW`로 집계되던 버그 수정 (대상 테이블은 줄바꿈과 무관하게 `W`(C)만 할당).
  - `--why <테이블>` 옵션 신설: 지정한 테이블의 C/R/U/D 출처 SQL ID, 서비스 키, UDM, 서블릿 근거를 상세 출력하고 JSON 출력에 `sources` 맵 제공.
- **`compare` 파라미터 자동 상속 및 자동 그리드 대조 억제 (`src/yunhee/tools/comparator.py`, `src/yunhee/cli.py`)**:
  - `--param`에 명시하지 않은 API 요청 파라미터(`-p`)를 동일 이름의 SQL 파라미터로 자동 상속하며 `SQL params:` 줄에 `(← -p)` 표기.
  - `--no-grid` 옵션 추가 및 `--grid` 미지정 시 해당 SQL이 `GridRetrieveData` 등 그리드 조회용 SQL이 아닌 단일 집계/요약 조회일 경우 그리드 열 대조를 자동 생략(`grid: -`).
- **메뉴가 없는 클래스(편집 폼·탭 페이지) 역추적 (`src/yunhee/tools/analysis/ui.py`, `src/yunhee/tools/as_is/drift.py`)**:
  - 색인 화면 문서(`screens/*.md`)가 없는 하위 클래스(예: `Emp20_Edit_Leave`, `Sys01_TabPage_Info04`)를 전달했을 때 이를 연결 클래스로 가진 부모 화면을 찾아 `--class`로 자동 처리 (`analysis ui`).
  - `drift` 실행 시 해당 클래스 파일의 변경사항만 한정하여 drift를 계산.
- **호출자 탐색 편의 개선 (`src/yunhee/tools/outliner.py`, `src/yunhee/tools/analysis/callers.py`, `src/yunhee/cli.py`)**:
  - `yunhee grep -l` (`--files-with-matches`): 일치 내용 대신 일치하는 파일 경로 목록만 한 줄에 하나씩 출력.
  - `yunhee analysis callers <클래스[.메서드]> [--server]`: AS-IS 서버 소스 및 일반 클래스/메서드 참조 위치(파일:줄, 감싼 메서드)를 역추적하여 테이블 출력.
API 객체 내 위임 함수 추적, AS-IS 서블릿(FileDelete/FileUpload) 테이블 작업 반영 및 실행 속도 획기적 단축
- **API 객체 함수 위임 체인 추적 (`src/yunhee/tools/trace/tobe.py`)**:
  - `parse_api_ts`에서 함수 본문 내 `apiClient`뿐만 아니라 `fileApi.xxx` / `this.xxx` 등 객체 내 다른 함수 위임 호출을 수집하고, `build_index`에서 엔드포인트/AS-IS 키를 자동 전파.
  - 서비스 클래스 내 다른 서비스 주입 호출(`fileService.upload` 등)을 1~2단계 추적하여 상속된 매퍼 문장의 CRUD 작업 집계 보완.
- **AS-IS 서블릿(`FileDelete` / `FileUpload`) 작업 집계 (`src/yunhee/tools/trace/crud.py`, `src/yunhee/tools/as_is/src_indexer.py`)**:
  - AS-IS 화면 자바 파일 및 `## 서블릿 호출`에서 `FileDelete` 감지 시 `sys10_file: {D, R}`, `FileUpload` 감지 시 `sys10_file: {C}`를 추가하여 TOBE와 정확한 대조 지원 (`#1298`, `#1353` 오탐 해소).
- **디스크 캐시 도입 및 복수 화면 조회 속도 단축 (`src/yunhee/tools/trace/sqlscan.py`, `src/yunhee/tools/trace/tobe.py`, `src/yunhee/tools/trace/crud.py`)**:
  - 매퍼 XML 파싱(`scan_asis`, `scan_tobe`) 및 TOBE 색인(`build_index`)에 파일 `mtime` 기반 디스크 캐시(`.yunhee/cache/`)를 적용하여 단일 화면 실행 속도를 ~24초에서 **3.4초**로 단축.
  - `trace-crud --screen`에 쉼표 구분 복수 화면(`--screen '#1353,#1404,#1298'`) 지원으로 수 개 화면을 단 한 번의 스캔으로 일괄 분석.

## [0.8.4] - 2026-11-10
`trace-crud`·`trace-pair` 오탐 해결, `api` 테넌트·세션·응답 필터, `log trace` 원인 표시 및 편의 기능 개선
- **`trace-crud` 쓰기(C/U/D) 집계 및 오탐 해소 (`src/yunhee/tools/trace/crud.py`, `src/yunhee/tools/trace/tobe.py`)**:
  - TSX 내 다중 엔드포인트(`PUT`/`POST` 등)가 묶인 API 함수(`saveMenu` 등)의 CRUD 작업을 완전 추적하여 `#1077`, `#1078`, `#1197` 등의 쓰기 누락 오탐 해결.
  - AS-IS `UpdateDataModel`의 `updateModel` 호출로 부여된 가상 C 작업에 대해 TOBE에서 U(수정)가 이미 충족된 경우 `⚠ TOBE에 C 없음` 경고 대신 `(ASIS UDM 등록·수정 공용)`으로 안내.
- **`trace-pair` 함수 객체 속성 참조 추적 및 원본 변경 의심 감지 (`src/yunhee/tools/trace/tobe.py`, `src/yunhee/tools/trace/pair.py`)**:
  - `save: sysApi.updateCodeKinds` 등 함수 호출 괄호 없이 객체 속성이나 인자로 전달된 API 함수 참조를 호출부로 인식하고 `파일:줄` 표시.
  - TOBE 주석의 AS-IS 서비스 키와 현재 AS-IS 화면 호출 서비스 간 불일치(예: `updateByMenuYn` ↔ `insertByMenuYn`) 탐지 시 `💡 원본 변경 의심` 안내 출력.
- **`api` 테넌트 자동 동기화, `--fresh` 세션 갱신 및 응답 필터 (`src/yunhee/config.py`, `src/yunhee/tools/api_client.py`, `src/yunhee/cli.py`)**:
  - `-c <회사>` 지정 시 기본 테넌트를 해당 회사로 자동 설정하고 base URL 서브도메인 테넌트 반영. 머리 줄에 실제 접속 호스트 및 `login=new|reused` 표시.
  - `--fresh` / `--no-session` 옵션으로 로그인 세션 재사용 방지 및 세션 갱신 지원.
  - 응답 배열 필터링 옵션 `--fields a,b,c` (TSV 출력), `--where k=v` (행 조건 필터), `--count-by k` (값별 빈도 집계) 추가.
- **`log trace` 원인 표시 및 편의 기능 (`src/yunhee/tools/log_reader.py`, `src/yunhee/tools/sql_runner.py`, `src/yunhee/tools/analysis/method.py`, `src/yunhee/cli.py`)**:
  - HTTP 500 등 예외 발생 시 가장 안쪽 `Caused by:` / `### Cause:` 예외 메시지(SQLState 등)를 단일 요약 줄에 표시 (`api --log` 연동).
  - 전체 Typer 명령어에 `-h`를 `--help`의 단축 옵션으로 지원.
  - `yunhee analysis method <클래스>`(메서드 생략 시) 해당 클래스 내 정의된 전체 메서드 목록 출력.
  - `sql` 실행 중 열 이름 오류 발생 시 스키마 스냅샷 기반 "비슷한 열" 추천.

## [0.8.3] - 2026-11-09
`screen-desc` 복수 화면번호 처리 보강 및 종합 요약 기능 개선
- 복수 화면번호 쉼표/공백 구분 일괄 조회 및 각 화면별 요약 섹션 분리 지원.
복수 화면번호 종합 조회 명령어 `yunhee screen-desc` (`--format=md|json`) 신설
- **`yunhee screen-desc` 명령어 및 REPL `/screen-desc` 추가 (`src/yunhee/tools/trace/screen_desc.py`, `src/yunhee/cli.py`, `src/yunhee/ui/repl.py`)**:
  - `yunhee screen-desc 1111,2222,3333, 4444 [--format=md|json]`: 쉼표(`,`)와 공백(` `)이 혼합된 복수의 화면번호(또는 화면 클래스명)를 받아 메뉴명·메뉴 경로·프론트엔드 파일 경로·페이지 스타일·조회조건(`SearchBar`)·버튼·그리드 컬럼·**사용되는 모든 팝업/모달 창**·하위 탭페이지·백엔드 API·파일·MyBatis SQL ID·참조 DB 테이블·AS-IS 레거시 요약을 마크다운 또는 JSON으로 일괄 반환.
  - 범용 공통 모달의 동적 타이틀 전파 시 무관한 호출부 리터럴 제외 및 화살표 함수(`onClick={() => ...}`) 버튼 라벨 정규화 개선.

## [0.8.1] - 2026-11-09
TOBE 프로젝트 에이전트 RAG 종합 학습 시스템(`rag-index`, `rag-reset`, `rag-status`, `rag-search`, `lookup_tobe`) 및 사용 가이드(`docs/yunhee-agent-사용법.md`) 신설
- **TOBE 3계층 RAG 학습 및 `rag-*` CLI 명령어 4종 (`src/yunhee/tools/trace/tobe_rag.py`, `src/yunhee/cli.py`, `src/yunhee/ui/repl.py`)**:
  - `yunhee rag-index` (`/rag-index`): TOBE 전체 화면·컴포넌트·메뉴번호·조회조건(`SearchBar`)·모달·그리드·버튼·호출 API·백엔드 파일·SQL ID·참조 테이블을 스캔하여 `.yunhee/tobe_catalog.json` 고속 스냅샷과 `docs/to-be/`(`menus.md`, `domains/*.md`)를 생성하고, ChromaDB `yunhee_tobe_kb` 컬렉션에 `bge-m3` 배치 임베딩으로 증분 학습(`upsert` 및 삭제 파일 자동 `delete`).
  - `yunhee rag-reset` (`/rag-reset`): ChromaDB `yunhee_tobe_kb` 컬렉션과 스냅샷을 완전히 삭제한 뒤 처음부터 재학습 (`--all` 지정 시 수동 노하우 컬렉션까지 초기화).
  - `yunhee rag-status` (`/rag-status`): 마지막 학습 시각, 인덱싱된 화면/벡터 건수, 마지막 학습 이후 변경된 TOBE 파일(Stale) 건수 점검.
  - `yunhee rag-search <질의>` (`/rag-search <질의>`): 결정적 카탈로그 매칭 + ChromaDB 벡터 검색 결과 카드 조회.
- **하이브리드 Prefetch RAG 및 `lookup_tobe` 에이전트 도구 (`src/yunhee/agent/loop.py`, `src/yunhee/agent/registry.py`)**:
  - 질문에 화면번호(`1002` 등), 컴포넌트명, 메뉴명, API, 테이블명이 포함되면 1턴 시작 전 관련 TOBE 학습 카드를 프롬프트에 자동 주입하여 단건 질문에 0-스텝 즉시 응답.
  - `.yunhee/tobe_catalog.json` 스냅샷 로드로 `execute_python`의 `iter_screens()` 실행 속도를 약 5.5초 → 0.25초로 단축.
  - 에이전트 사용 설명서(`docs/yunhee-agent-사용법.md`) 및 설계 문서(`docs/tobe_agent_rag-설계.md`) 추가.

## [0.7.9] - 2026-11-09
`screen_catalog` 동적 모달 타이틀 부모 화면 역추적(`titleName`·`title`·JSX) 및 `agent` 빈 출력 환각 방지 가드
- **동적 모달 타이틀 호출부 역추적 (`src/yunhee/tools/trace/screen_catalog.py`)**:
  - `<EditModal title={target?.titleName}>`, `<LookupModal title={title}>` 등 모달 타이틀이 동적 변수로 선언된 경우, 역방향 import 그래프를 통해 부모 화면이 전달하는 `titleName: '...'` / `title: '...'` / `insert*`·`editData` 인자(예: `Ics01_Tab_ClassTree` → `Ics01_Edit_ClassTree`의 `'법규분류 수정'`, `'하위분류 등록'`, `'루트등록'`) 및 상단 JSDoc 설명을 `s.modals`에 자동 연결.
  - `title={<b style={{...}}>점검방법</b>}` 형태의 중첩 중괄호·JSX 태그 내부 타이틀 추출 및 삼항 연산자 비교 리터럴(`=== 'edit'`) 제외 처리.
- **`agent` 루프 빈 출력(`출력 없음`) 환각 방지 (`src/yunhee/agent/loop.py`)**:
  - `execute_python` 실행 결과가 `(출력 없음)`일 때 로컬 LLM이 가짜 `[execute_python 결과]`나 존재하지 않는 화면번호·파일 경로를 생성하지 못하도록 후속 안내 프롬프트 가드 강화.

## [0.7.8] - 2026-11-09
`yunhee agent` 자연어 화면/모달/그리드 조건 탐색(`execute_python` 및 `screen_catalog`) 신설
- **통합 화면 카탈로그 (`src/yunhee/tools/trace/screen_catalog.py`) 및 `GridCol` 확장 (`src/yunhee/tools/trace/tobe.py`)**:
  - `iter_screens(side="tobe")`를 통해 TOBE(기본값) 및 AS-IS 화면의 프론트엔드(`modals`, `grid_cols`, `buttons`, `raw_text`)와 백엔드(`apis`, `sql_ids`, `backend_files`) 정보를 `ScreenRecord`로 통합 제공.
  - `GridCol`을 `(field, label)` 2-튜플 하위 호환 서브클래스로 확장하여 `.col_type`, `.field`, `.label`, `.width` 속성과 `tgb.*`(`TreeGridBuilder`) 파싱을 지원.
  - 팝업/모달(`Lookup`, `Modal`, `Edit`) 파일을 역방향 import 그래프로 추적하여 자신을 여는 상위 `_Tab_` 화면 및 메뉴 번호(`#번호`, 메뉴 경로)를 자동 매핑.
- **에이전트 Python 코드 생성·실행 도구 (`execute_python`) 및 `yunhee agent` CLI 명령어**:
  - 로컬 LLM(`qwen2.5-coder:14b`)이 자연어 조건을 Python 스크립트로 작성·실행(`execute_python`)하여 `[화면번호(#), 메뉴명, 컴포넌트명, 파일 경로, 일치 상세]` 마크다운 표로 응답.
  - Ollama 네이티브 `/api/chat` 래퍼 적용으로 다중 도구 등록 시에도 `num_ctx=16384` 보장.
  - 단발성 에이전트 실행 명령어 `yunhee agent "<질문>"` 및 `yunhee ask --agent` (`-a`) 추가.

## [0.7.7] - 2026-11-08
수정사항 049 완료: `screen-capture` 조회 조건(`--range`·`--set`) 지정, `--modal-only`/`--click-all`, 화면 품질 텍스트 신호 리포트 추가
- **`--range <YYYY-MM-DD~YYYY-MM-DD>` 옵션 (수정사항 049 §1)**:
  - 조회 줄(SearchBar/SearchPanel/일반 툴바)에서 날짜 범위 입력(시작일·종료일 두 칸 쌍)을 모두 찾아 지정한 범위로 채운 뒤 `[조회]`를 클릭한다.
  - AntD DatePicker에 타이핑 후 `Enter`로 확정하고 달력 팝업이 남으면 `Esc`로 닫는다. 날짜 칸이 없는 화면은 무시하고 리포트에 `"날짜 범위 없음"`으로 기록한다.
- **`--set <라벨=값>` 옵션 및 미발견 라벨 후보 안내 (수정사항 049 §2·§3)**:
  - 조회 줄(SearchBar) 안의 입력만 대상으로 라벨 텍스트 옆 위젯 유형(텍스트, 단일 날짜, 날짜 범위, Select 드롭다운, 체크박스, 라디오, 조회창 필드)을 자동 판별해 값을 넣는다 (`--range`와 함께 주면 `--set`이 우선, 중복 라벨은 `라벨#2`로 지정, 조회창 필드는 `"미지원"` 기록).
  - 라벨을 못 찾으면 실패로 중단하지 않고 `⚠ 라벨 '...' 못 찾음. 조회 줄 후보: ...` 경고를 출력한 뒤 기본값으로 캡처를 계속 진행한다.
- **리포트(`--json`·텍스트)에 화면 품질 텍스트 신호 추가 (수정사항 049 §4)**:
  - 이미지 열람 전 텍스트 신호만으로 이상 화면을 선별할 수 있도록 그리드별 행 수·빈 그리드 여부·헤더 줄바꿈/잘림(`wrapped_headers`, 예: 1131 `"인당 경제적가치"`)·가로 스크롤, 화면 버튼 목록과 비활성 여부(`pointer-events: none` 부모 포함), 화면/그리드 가로 스크롤 여부, 팝업 순회 결과(열린 모달, 미오픈 버튼 및 토스트 알림/추정 사유, 안전 제외된 위험 버튼), 콘솔 에러 및 4xx/5xx 실패 건수, `anomalies` 요약을 출력 및 `report.json`에 저장한다.
- **`--modal-only`, `--click-all`, `--viewport` 프리셋 지원 (수정사항 049 §5)**:
  - `--modal-only`: 팝업/Lookup 캡처 시 전체 페이지 대신 `.ant-modal-content` 영역만 잘라 저장하여 이미지 토큰 크기를 줄인다.
  - 위험 버튼(`저장`, `삭제`, `승인`, `상신`, `확정` 등)은 기본으로 클릭하지 않으며(`skipped_dangerous`), `--click-all` 지정 시에만 클릭을 시도한다(네트워크 CUD 차단 가드는 유지).
  - `--viewport`: `720p`(`1280x720`), `810p`(`1440x810`), `1080p`(`1920x1080`) 프리셋 및 `WIDTHxHEIGHT` 지정 지원.

## [0.7.6] - 2026-11-08
`page-style --all`(Tab 판별)에서 모달 파일 제외
- 이름에 `_Tab_`이 든 모달(`Cmp10_Edit_Tab_MailBook` 등)이 Tab 판별에 MF로 섞이던 것을 제외한다.

## [0.7.5] - 2026-11-08
`page-style` 모달 SID(MF·MG·MFG·MH) 판별 및 `--all --modal` 신설
- **모달 판별**: `*_Edit_*`·`*_Lookup_*`·`*_Popup_*`(.tsx)는 Tab 규칙 대신 내용 구조로 판별한다 — HtmlView/HtmlEditor → `MH`, 그리드 + 폼(조회 줄 없음) → `MFG`, 그리드 → `MG`, 그 외 → `MF`. 파일 이름 접미로는 가르지 않는다(`docs/page-style.md` "모달 스타일").
- **`yunhee page-style --all --modal [디렉터리]`**: `*_Tab_*` 대신 모달 파일 전체를 판별하고 SID별 분포를 낸다.
- 유효 SID 목록에 `MF`·`MG`·`MFG`·`MH`를 항상 포함(별도 절의 표라서 `## 스타일 목록` 표 파싱에 안 잡힘).

## [0.7.4] - 2026-11-05
수정사항 048 완료: `port-sql`/`analysis sql` DB 부재 객체 즉시 경고 및 서비스명(`dom.Class.method`) 해석, `analysis callers` 창 호출부/인자 추출, `trace-gap --stubs` TOBE 미연결 안내 수집, `api --track` 테이블 행 수/PK 변화 추적
- **`port-sql` · `analysis sql` DB 부재 객체 즉시 경고 및 `sql-check --new-since-index` (수정사항 048 §1)**:
  - 단일 문장 `EXPLAIN` 및 `sql-check.md` 대조를 통해 DB에 없는 테이블·뷰·함수 참조 시 `⚠ DB에 없는 객체: ... — 변환 가이드 1절에 따라 보류 검토` 경고 및 `sql-check` 상태 줄 즉시 출력 (`port-sql`은 첫 줄 주석으로 출력).
  - `yunhee sql-check --new-since-index` (`--changed-asis`): 마지막 색인/`sql-check.md` 이후 AS-IS에 새로 추가·변경된 매퍼 XML만 선별 검증.
- **`analysis sql` · `port-sql` · `compare --sql` 서비스 이름(`dom.Class.method`) 자동 해석 (수정사항 048 §2)**:
  - 인자가 `ics.Ics40_DcrPreconfirm.selectByApprId` 꼴이면 `server/{dom}/{ClassName}.java`의 메서드가 부르는 매퍼 문장을 추적하여 `서비스 ... → 매퍼 ...` 안내와 함께 SQL을 반환하고, 실패 시 같은 매퍼 내 후보 문장을 제시.
- **`yunhee analysis callers <클래스> [--tobe <경로>]` 신설 (수정사항 048 §4)**:
  - AS-IS에서 특정 팝업·조회창·편집창을 `new`하여 여는 모든 호출부의 `파일:줄 | 부른 메서드(open/view/edit 등) | 리터럴 인자 | 감싼 메서드 | 메뉴` 표 출력 및 `--tobe` 지정 시 TOBE `<클래스 ...>` 렌더링 위치/props 대조.
- **`yunhee trace-gap --stubs` TOBE 미연결 자리 수집 (수정사항 048 §3)**:
  - TOBE `frontend/src`에서 `message.info/warning`의 미연결 안내(`다음 단계`·`아직 변환`·`연결됩니다` 등, 템플릿 헬퍼 포함), `// [E… 생략]` 주석, 화면 머리에 남은 `1단계:`/`다음 단계:` 주석을 역방향 import `_Tab_` 화면 및 `#메뉴번호`와 함께 표 및 `13-누락대장.md` 체크리스트 형식으로 출력.
- **`yunhee api --track <테이블>[,<테이블>]` 행 수 및 신규 PK 추적 (수정사항 048 §5)**:
  - API 호출 전후로 지정 테이블의 행 수 변화와 새로 생긴 PK(`information_schema` 기준)를 한 줄로 출력 (예: `biz05_relate_appr: 40 → 41 (+1: biz05_relate_appr_id=...)`, 삭제 시 `(-1)`, 실패 시 `(변화 없음)`).

## [0.7.3] - 2026-11-03
수정사항 047 완료: `mapper-run` 및 MyBatis `<foreach>` 컬렉션 파라미터 바인딩 지원
- **`mapper-run` / `mybatis_render` `<foreach>` 목록 파라미터 바인딩 (수정사항 047)**:
  - `<foreach collection="coll" item="item">` 문장에 대해 `-p coll=1,2`, `-p 'coll=[1,2]'`, 또는 반복 옵션(`-p coll=1 -p coll=2`)으로 목록 값을 전달하면 전개된 각 자리마다 컬렉션 요소를 순서대로 치환·바인딩하도록 개선.
  - `item` 이름의 파라미터는 요구하지 않으며, 컬렉션 파라미터 누락 시 `item`이 아닌 `collection` 이름을 누락 파라미터로 결론(`❌ 파라미터 부족 (1건): <collection>`) 보고.
  - 요소 타입은 숫자로 읽히면 숫자 리터럴, 아니면 문자열 리터럴로 치환하며 명시적 타입 접두사(`s:`, `n:`, `null:`, `b:`) 규칙을 승계.
  - `--help` 및 `docs/help/migration.md`, `docs/yunhee-사용설명서.md`에 `<foreach>`는 `-p <collection>=a,b,c`로 준다는 안내 추가.

## [0.7.2] - 2026-11-02
수정사항 046 완료: `api`/`compare` `%25` 이중 인코딩 방지, `sql-check --tobe` `record` DTO 열 누락 오류 승격 및 `<include>` 프로퍼티 전개, `page-style` `GGH`/`SG` 규칙, `cat --head/--tail` 및 `grep` 명령 신설, `trace-crud` 타 화면 안내 및 `mapper-run` 파라미터 부족 결론 표시
- **`api` / `compare` `-p` 쿼리 파라미터 `%XX` 이중 인코딩 방지 (수정사항 046 §1)**:
  - `-p k=v` 값에 `%25` 등 이미 `%XX`(16진 두 자리) 패턴이 있으면 이중 인코딩(`%25` → `%2525`)하지 않도록 정규화하고, 문자 그대로 보내야 할 때를 위한 `--raw-param` 옵션 추가.
  - `--help` 및 `docs/help/ops-and-log.md`에 "LIKE용 `%`는 `-p k=%`로 준다" 안내 명시.
- **`sql-check --tobe` Java `record` DTO 열 누락 오류 승격 및 `<include>` 프로퍼티 전개 (수정사항 046 §2)**:
  - `resultType`(및 `resultMap`)의 DTO가 Java `record`인 경우 `SELECT` 결과 열에 record 컴포넌트가 하나라도 빠지면 런타임 500(`Constructor auto-mapping … not found in the result set`)을 유발하므로 일반 경고(`⚠`) 대신 오류(`❌ record <DTO> 열 누락: ...`)로 판정하고 종료 코드를 비-0으로 반환.
  - 일반(setter) 클래스 DTO의 필드 누락은 기존처럼 `⚠` 경고로 유지하고, DTO에 없는 잉여 별칭(`미사용 별칭`) 경고는 제거.
  - `<include refid="..."><property name="cols" value="..."/></include>` (`${cols}`) 치환 전개를 지원하고, 미해결 `<include>`가 남으면 거짓 `❌` 대신 `? include 미해결 — mapper-run으로 확인`으로 표시.
- **page-style: 새 SID `GGH`(좌우 분할 마스터-상세) 판별 및 `SG` 선언 우선 (수정사항 046 §3)**:
  - 위 조회 줄(`SearchBar`) + 가로 `Splitter`(`layout == "horizontal"` / GXT `West`·`East`) + 그리드 2개 이상인 화면(`Pay50_Tab_ExpensePay` 등)을 `GGH`로 판별.
  - 단일 그리드에서 머리 주석 선언이 `스타일: SG`이고 조회 툴바가 있으면 셀 편집 그리드(`editable_grid`)여도 선언된 `SG`를 우선 판정(`Pay50_Tab_ExpensePayWrite`).
- **`yunhee cat --head/--tail` 및 문맥 출력 전용 `yunhee grep` 신설 (수정사항 046 §4)**:
  - `yunhee cat`에 `--head N`, `--tail N` 옵션 추가 (`<파일>:<범위>`와 조합 가능, 200줄 상한 초과 시 `… N줄 더 있음 — 범위를 좁히세요` 표시).
  - `yunhee grep <패턴> <파일|폴더…> [-C n | -A n | -B n] [--max M] [-F] [-i]` 명령 추가 (출력 상한 80줄, 겹치는 문맥 자동 병합, 항상 `파일:줄: 내용` 출력, 허용 범위 밖 시스템 경로 `/etc/passwd` 등 차단).
- **`trace-crud --screen` 타 화면 변환 테이블 위치 안내 및 `mapper-run` 파라미터 부족 결론 표시 (수정사항 046 §5)**:
  - `trace-crud --screen`에서 현재 화면의 TOBE 파일에 없는 테이블이라도 저장소 내 다른 TOBE 화면/연결 컴포넌트(`Act02_Grid_JournalFix` 등)에 있으면 `⚠ TOBE에 없음` 대신 `(다른 화면에 있음: ...)`으로 표시.
  - `mapper-run`에서 필수 파라미터 누락 시 마지막 줄에 `❌ 파라미터 부족 (N건): ...` 결론 출력.

## [0.7.1] - 2026-11-02
신규 프로젝트 환경 초기화, 자료 셋업 스크립트(`data-setup.sh`), MyBatis `<bind>` 리터럴 지원:
- **신규 프로젝트 격리 및 2단계 계층형 환경설정 캐스케이딩**:
  - `yunhee init` 및 REPL `/init`을 통해 작업 디렉터리 내 `.yunhee/` 필수 파일(`project.json`, `mcp.json`, `memory.md`, `sessions/`, `runs/`, `.gitignore`) 자동 생성.
  - 전역 설정(`~/.yunhee/.env.yunhee`) 로드 후 프로젝트 로컬(`.env.yunhee`) 오버라이드 계층형 로딩 구현.
  - `YUNHEE_TOBE_SRC_DIR` 환경변수 추가로 새 프로젝트 폴더에서도 TOBE 소스 경로 자동 참조.
- **데이터 및 색인 관리 스크립트 (`data-setup.sh`) 제공**:
  - 현재 working 폴더(pwd) 기준 격리 실행 지원 (상태 조회, DB/SRC 자료 삭제, 준비, 재설치 대화형 메뉴).
  - DB 카탈로그 스냅샷(`make-dbml`, `index-db`) 및 로컬 `.yunhee/` 스냅샷 JSON 격리 저장 지원.
  - AS-IS 소스/UI 호출경로 색인(`index-src --menus-from-db`) 및 `parse_mapper.py` 자동 연동.
- **MyBatis `<bind>` 태그 단순 리터럴 지원**:
  - `eval_bind()` 파서에 따옴표 리터럴 문자열(`'regDate'`, `"xyz"`) 및 숫자/불리언 매칭을 추가하여 `⚠ bind 식 건너뜀` 경고 제거 및 파라미터 바인딩 처리.
- **`index-src`의 `--menus-from-db` 자동 생성 오류 수정**:
  - 메뉴 파일이 없는 신규 작업 폴더에서도 `--menus-from-db` 지정 시 DB(`sys06_menu`)에서 `menus.tsv`를 먼저 생성한 후 색인을 정상 진행하도록 수정.

## [0.7.0] - 2026-10-30
수정사항 045 완료: `compare` API 오류 처리 강화 및 MyBatis 조건식 평가기 확장/가드
- **`compare` API 서버 오류(HTTP 500/4xx/업무예외) 즉시 실패 처리**:
  - API 호출 결과가 HTTP 4xx/5xx이거나 `ApiResponse.success=false`인 경우 기존처럼 0행(`rows=0 ✅`)으로 대조하지 않고 즉시 실패 판정(`❌ API 실패...` / `❌ API 업무 오류...`) 및 종료 코드 1 반환.
  - 추적 ID 및 원인 로그 요약(`yunhee log trace <id> --raw`) 가이드를 에러 메시지에 함께 출력.
- **MyBatis 분기 조건식 평가기 확장 (AS-IS 100% 커버리지 달성)**:
  - 문자열 메서드 비교(`x.equals('lit')`, `'lit'.equals(x)`, `!x.equals('lit')`, `x.equalsIgnoreCase('lit')`) 정규식 지원 (`car03_booking.selectByDate` 등).
  - 프로퍼티 형태의 `.size` 접근(`fundIdList.size != 0`) 및 `0l`/`0L` Long 리터럴 접미사 지원.
  - `&&` 및 `||` 복합 논리 연산자 분리 및 `isEmpty()` 지원.
  - AS-IS 레거시 전체 526개 XML 매퍼의 307개 조건식 중 미평가 16건을 전수 해소 (미평가율 0%).
- **미평가 분기 안전 가드 및 `--branch` 강제 옵션 신설**:
  - 평가할 수 없는 미지의 식은 임의로 켜서 쿼리를 실행하지 않고 안전하게 주석(`/* ⚠ 분기 평가 불가(기본 OFF): ... */`) 처리하여 실행 차단.
  - stderr 경고 출력 및 대조 결과 요약 줄에 `(분기 N개 평가 불가)` 표기.
  - `compare` 및 `analysis sql`에 `--branch '<식|변수>'=on|off` 옵션을 추가하여 분기 강제 제어 지원.
`page-style` SID 체계 개편 (DB→DSBRD, MG 폐지, GDP 신설):
- **SID `DB` → `DSBRD` 변경**: 대시보드 SID명을 `DSBRD`로 변경 및 옛 이름 `DB` 선언 시 경고 및 자동 매핑, 탭 없는 다운로드/요약 화면(`Tdm35_Tab_TaskList`) 판별 지원.
- **SID `MG` 폐지 및 `SGEF` 통합**: `MG` 분기를 제거하고 고정 높이 폼 구조를 SGEF로 통합 판별 (`Sys90_Tab_AfterService`, `Ics20_Tab_RevisionHistory` 등 4개 화면 SGEF 판정).
- **새 SID `GDP` (Grid+DetailPage) 신설**: 좌우 분할 + 버튼 줄 + 그리드 + 우측 상세 페이지(`*_Page_*`/`*_TabPage_*`) 구조 판정 (`Sms02_Tab_TotalCount`, `Sys10_Tab_TotalSize`, `Sms03_Tab_SendAdmin`, `Ics02_Tab_Manager` 4개 화면 GDP 판정).

## [0.6.8] - 2026-10-29
`page-style` GG와 SGTP 판별 정밀화:
- 자식 `*_TabPage_*` 이름만으로 무조건 SGTP로 분류하지 않고, 자식이 `<Tabs>`/`<PageTabs>`를 갖거나 다중 탭(2개 이상)일 때만 SGTP로 판별하며, 단일 자식에 그리드가 포함된 경우 GG(마스터·상세)로 정상 판정 (`Dcr30_Tab_LinkAdmin` 등 10개 화면 GG 전환, SGTP 3개로 정립).

## [0.6.7] - 2026-10-29
`page-style` 버그 수정:
- `_TabPage_` 자식 컴포넌트의 내부 그리드가 메인 화면 그리드 수로 잘못 합산되던 문제 수정 (`Sms02_Tab_TotalCount`, `Sys10_Tab_TotalSize`가 `grids: 1` 및 GO로 정상 판정).
- `custom_search` 판별 강화 (`SearchBar` 외에 `Button type="search"`, `QuickMoveField`, `Typography.Text`/`DatePicker` 등 직접 구성한 조건 줄을 인식하여 `Tdm50_Tab_CheckJob` 등이 STP로 정상 판정).

## [0.6.6] - 2026-10-29
`page-style` 기능 대폭 보완 및 확장 (19개 SID 체계 지원):
- `docs/page-style.md` 문서에 정의된 확장 19종 SID(`SG`, `SGP`, `SGVF`, `SGEF`, `SGTP`, `SGT`, `TG`, `GG`, `CG`, `STP`, `TP`, `SR`, `GCG`, `SGHF`, `MG`, `TO`, `GO`, `DB`, `IN`) 완벽 지원.
- `load_valid_sids()`를 통한 유효 SID 동적 로드 및 헤더 주석(`//` 및 `/* */` 블록 주석) 선언 판별/검증, 미정의 SID 경고 표기.
- 모달 다이얼로그 팝업(`BaseDialog`, `Dialog`, `Modal`, `Window` 등) 내부 그리드를 화면 그리드 수 집계에서 제외하여 팝업을 가진 단일 그리드 화면의 TG 오판정 방지.
- `<Button type="save">` 버튼의 단순 저장 액션으로 인한 CG(직접 편집 그리드) 오판정 방지 (CellEditing/RowEditing/EditorGrid/editableCol 실질 검사).
- 단일 자식 위임형 래퍼 컴포넌트(`delegate_to`) 추적 및 분석.
- `--compare` 대조 시 AS-IS ↔ TOBE 간 호환 가능한 스타일군(SG/SGP, SGT/SGTP, SGEF/SGVF/CG 등) 유연 매칭.

## [0.6.5] - 2026-10-28
`trace-column`, `trace-code`, `trace-crud` 구현 (trace-* Step 5, 묶음 A: SQL 해석 기반) + `trace-map`, `trace-menu`, `trace-term` (묶음 B: 색인 집계) + `trace-dblogic`, `trace-guide` (묶음 C). **`trace-*` 18개가 모두 구현됐다.**
- `trace-column <테이블.컬럼>`: 그 컬럼을 **읽는**(SELECT 목록·SET 식·RETURNING) / **조건에 쓰는**(WHERE·JOIN·HAVING) / **정렬·그룹**(ORDER·GROUP) / **쓰는**(INSERT·UPDATE) SQL을 SQL AST의 절로 구분해 ASIS·TOBE 각각 낸다. 화면 표시 라벨은 컬럼명에서 만든 속성 이름(`emp01_kor_nm`→`korNm`)이 ASIS 색인의 Grid Spec·TOBE 그리드 필드명과 같은 곳에서 찾는다. `--stats`는 읽기 전용으로 값 분포를 조회하되 **고유 값이 30종 이하인 코드성 컬럼만 값을 낸다** (이름·주민번호 같은 개인정보가 컨텍스트에 새지 않게 개수만 알림)
- `trace-code <코드그룹>`: DB(`sys08_code_kind`·`sys09_code`, 읽기 전용)에서 코드값·명칭·사용 중지·회사별 사본 수를 읽고, ASIS·TOBE 소스에서 그룹 이름이 따옴표 문자열로 적힌 곳을 SQL 리터럴 / 콤보·선택 목록 / 상수 비교 / 그 밖의 참조로 나눠 낸다 (주석 속 코드는 제외). 이름 일부만 주면 후보 목록(종료 코드 2). DB를 쓸 수 없으면 값은 건너뛰고 사용처만 낸다
- `trace-crud [--screen|--domain|--table]`: 화면 → 서비스 → SQL → 테이블로 ASIS의 C/R/U/D를 만들고(`UpdateDataModel` 동적 쓰기 포함), TOBE는 TSX → api → 컨트롤러 → 서비스 → mapper 문장으로 만들어 **나란히 비교**한다. TOBE에 없는 테이블·작업에 ⚠를 붙인다. 범위를 안 주면 영역별 요약
- `sql_parse`: `ParsedSql.column_usage`(테이블 → 컬럼 → 쓰인 절) 추가. `tools/trace/sqlscan.py`: mapper 전체 해석 캐시. `tools/trace/db.py`: 읽기 전용 DB 조회(실패는 unresolved)
- `trace-map [--domain]`: 업무 영역별 ASIS 화면·컴포넌트·서비스·SQL·테이블 수와 TOBE 이식 현황(이식 화면 수·비율, TSX, 엔드포인트, mapper 문장)을 낸다. 이식 여부는 같은 클래스명의 TSX 또는 TSX 헤더의 AS-IS로 판정(trace-pair와 같은 기준). 영역의 대표 메뉴 이름은 그 영역 화면이 가장 많이 속한 최상위 메뉴. 영역이 아닌 이름(`pages/` 바로 아래 파일 등)은 거른다
- `trace-menu [<경로|번호|화면>]`: 색인 `menus.md`의 메뉴 트리를 ASIS 화면 클래스 → TOBE 화면·API 호출로 이어서 낸다. 경로 조각(`'조직 및 사원관리 > 사원정보'`)은 각 단계에 순서대로 부분 일치, `#1029`·화면 클래스명도 받는다. 사용 안 함·화면 클래스 없는 메뉴를 표시. 인자가 없으면 최상위 메뉴 요약
- `trace-term [<용어>]`: 용어가 들어간 DB 컬럼 이름·코멘트, 테이블 설명, ASIS·TOBE 화면 라벨(Grid Spec·버튼), 공통 코드 그룹·코드값 이름(DB, 읽기 전용)을 모은다. 라벨의 속성 이름이 컬럼명에서 만든 이름(`korNm`)과 같고 후보가 3개 이하일 때만 라벨 ↔ 컬럼을 이어 근거를 밝힌다 (이름이 흔하거나 규칙에 안 맞으면 이어 붙이지 않음). 백업·임시 테이블은 제외
- `test_trace_map_menu_term.py`가 검증한다

- `trace-dblogic [<이름>]`: 스냅샷의 함수·프로시저·트리거 본문(줄 번호, 80줄 상한)·시그니처·언어, 본문이 참조하는 테이블, 본문이 부르는 다른 DB 함수, 이 함수를 실행하는 트리거, DB 안에서 이를 부르는 다른 함수, mapper 전체를 해석한 **ASIS·TOBE SQL 호출처**를 낸다. 이름이 없으면 DB 로직 규모와 SQL에서 가장 많이 호출되는 함수(`f_cdnm` 935문장 등), 호출되지 않는 함수를 요약. 부분 이름이 하나뿐이면 그것, 여럿이면 후보(종료 코드 2). JDBC `{call}`과 동적 SQL은 못 찾는다고 밝힌다
- `trace-guide`: 에이전트용 업무파악 지침(출력 읽는 법, 준비물, 워크플로우, 명령 목록, 지켜야 할 원칙, 알려진 한계). **명령 목록은 등록된 `trace-*` 명령에서 직접 읽어** 코드와 어긋나지 않는다 (테스트가 분류와 등록 명령의 일치를 검증)
- `trace-table`이 TOBE 쪽도 낸다: TOBE mapper 문장의 C/R/U/D(`--side tobe|both`)와, 그 문장에 닿는 API를 부르는 TOBE 화면(TSX → api → 컨트롤러 → 서비스 → mapper). `trace-table`·`trace-flow`가 `--tobe`를 받는다(`trace-flow`의 TOBE 사슬은 아직 없어 옵션만 받고 `trace-pair`·`trace-crud`로 대조하게 안내). 실제 데이터 점검에서 이 둘만 `--tobe`를 거부(종료 코드 2)하던 것을 발견해 고쳤다
- TOBE 체인 색인: 컨트롤러·서비스의 호출 필드를 이름뿐 아니라 **필드 타입**(`…Service`/`…Mapper`)으로도 찾고, 서비스 메서드 정규식의 들여쓰기 가정(정확히 4칸)을 2~8칸으로 넓혔다
- 모든 명령이 구현되어 `trace/stub.py`와 stub 테스트를 없애고 `test_trace_commands.py`가 18개 명령의 등록·`--help`·공통 옵션·설명을 검증한다
- `test_trace_column/code/crud.py`가 묶음 A를 검증한다. `conftest.py`의 `fake_schema`·`world.ctx_for(side)`

## [0.6.4] - 2026-10-28
`trace-rule`, `trace-state`, `trace-doc` 구현 (trace-* Step 4).
- `trace-rule add|list|show|update|verify`: 에이전트의 판정(일치·누락·변경·의도적 변경)과 사유, **근거 위치**를 sqlite(`data/db/yunhee.db`의 `trace_rule`·`trace_rule_evidence`, 프로젝트별)에 저장한다. 근거는 `파일:줄`·`파일:시작-끝`·파일·mapper id(ASIS `ns.id`, TOBE `Mapper클래스.id`). `add`는 근거를 **그 자리에서 읽어 존재를 확인하고**(없는 파일·줄·문장은 저장 전에 거부) 본문의 정규화 해시를 함께 저장한다
- `trace-rule verify [R-NNN|대상]`: 근거를 다시 읽어 `OK`(같음) / `MOVED`(내용은 같고 줄만 이동 — 빈 줄·서식 변경 포함) / `STALE`(내용이 바뀜) / `MISSING`(파일·줄·문장이 없어짐 또는 근거 없음)로 판정한다. 줄 번호가 아니라 **내용**으로 판정하고 mapper는 `normalize_sql_for_drift`로 공백·대소문자·주석을 무시한다. MISSING·STALE이 있으면 종료 코드 1(MOVED는 0). `--accept R-NNN`은 MOVED를 새 위치로 옮기고 STALE을 현재 내용으로 갱신한다
- `trace-state <테이블.컬럼>`: 그 컬럼에 값을 쓰는 모든 INSERT/UPDATE(CTE 안의 UPDATE·`ON CONFLICT` 포함)의 대입 값과 WHERE 조건을 대입 값별·SQL별로 낸다. 파라미터는 `#{statusCode}`로 남겨 상수와 호출자가 정하는 값을 구분하고, `UpdateDataModel`의 동적 쓰기는 값을 추측하지 않고 서비스 목록만 낸다. ASIS와 TOBE의 대입 값을 비교한다(`statCd`≡`stat_cd`)
- `trace-doc <영역>`: 화면(메뉴 번호·TOBE 이식 여부)·테이블(스냅샷 설명)·서비스·규칙 카탈로그·대응 현황을 마크다운 문서 골격으로 조립하고, 서술 자리는 `<!-- 서술(에이전트): … -->` 표지와 체크리스트로 남긴다. 근거·미해결은 문서 뒤에 붙는다
- `sql_parse`: 대입(`Assignment`)에 작업 종류(`UPDATE`/`INSERT`/`CONFLICT`)와 WHERE를 붙이고 CTE 안의 UPDATE도 대입으로 본다. `parse_statement(keep_params=True)`는 `#{name}`을 `NULL` 대신 이름이 남는 식별자로 렌더링한다. `render.py`는 `options["document"]`로 문서형 출력을 지원한다
- 구현된 명령 10개가 stub 테스트에서 빠지고 `test_trace_rule/state/doc.py`가 검증한다. 규칙 테스트는 임시 sqlite를 쓴다(`conftest.py`의 `rule_db`)

## [0.6.3] - 2026-10-28
`trace-pair`, `trace-diff`, `trace-gap` 구현 (trace-* Step 3) + TOBE 호출 체인 색인.
- `tools/trace/tobe.py`: TOBE의 `TSX → api/*.ts 함수 → 컨트롤러 엔드포인트 → 서비스 → mapper 인터페이스 → XML 문장` 체인과 `AS-IS` 주석(서비스 키 `emp.Emp00_TransInfo.selectByText`, SQL id, TSX 헤더의 메뉴 번호·AS-IS 클래스)을 색인한다. 이름이 비슷하다는 이유만으로 짝짓지 않고 TOBE 소스에 적힌 AS-IS 주석을 근거로 쓴다
- `trace-pair <화면>`: 화면(같은 클래스명·TSX 헤더 AS-IS·메뉴 번호 일치), 서비스(RPC)↔API, SQL↔mapper 문장, 테이블 집합 비교를 **근거와 함께** 낸다. ASIS에만 있는 항목과 TOBE에만 있는 API(AS-IS 주석 없음 포함)를 따로 보이고, 같은 ASIS SQL을 다른 화면 쪽에서 이식한 문장은 "이 화면의 API 체인 밖"으로 표시한다. 테이블 조합만 같은 짝은 후보가 하나일 때만 "약한 근거"로 짝짓는다
- `trace-diff <화면|mapper id> [--sql|--branch|--ui]` (옵션이 없으면 셋 다): `--sql`은 짝지어진 두 문장을 AST로 비교(테이블·쓰기 작업·사용 컬럼·출력 이름·WHERE 조건·CTE·함수·CASE 수·정규화 SQL 동일 여부), `--branch`는 식별자 집합이 같은 조건끼리 짝짓는 분기 대응표(`isSeparateAddTitle`↔`separateAddTitle`), `--ui`는 라벨로 짝짓는 그리드 열(필드명 변경 포함)·버튼·이벤트(구현/생략/도달 불가/표시 없음)
- `trace-gap [--domain <영역>]`: 화면·서비스(RPC)·SQL의 ASIS에만/TOBE에만 있는 것과, 근거를 찾지 못한 지점(AS-IS 주석이 없는 엔드포인트·mapper 문장·TSX, 컨트롤러까지 이어지지 않는 API 호출)을 따로 집계한다
- 모든 `trace-*`의 `--tobe`는 TOBE 프로젝트 루트 또는 `frontend/src`를 받는다 (생략하면 작업 폴더). `sql_parse`의 `SELECT *` 미해석 문구를 사유별로 정리
- 구현된 명령 7개가 stub 테스트에서 빠지고 `test_trace_tobe/pair/diff/gap.py`가 검증한다. 공용 fixture는 `tests/conftest.py`의 `world`

## [0.6.2] - 2026-10-28
`trace-flow`, `trace-branch` 구현 (trace-* Step 2).
- `trace-flow <화면> --event <En>`: 이벤트 → 핸들러 메서드 → 서비스(RPC) → 서버 메서드 → SQL → 테이블 사슬. 화면 색인의 이벤트·메서드(줄 범위)·서비스 호출 위치(`클래스:줄`)를 **줄 범위로** 이어 결정적으로 만든다. 메서드 표의 호출처를 따라 `E5 → insert() → retrieve()`처럼 간접 호출 경로를 보존하고, 인라인 핸들러·생성자(E0)도 줄 범위로 처리한다. SQL의 테이블은 `sql_parse`로 R/C/U/D 해석, `UpdateDataModel` 동적 쓰기 포함. 이벤트가 여는 하위 화면은 `--class`로 이어서 추적하도록 안내한다. `--event`를 생략하면 이벤트 목록, 없는 이벤트는 가능한 목록과 그 이벤트가 있는 다른 클래스를 알려 준다
- `trace-branch <화면|mapper id>`: mapper는 `<if test>`/`<when test>`/`<otherwise>`/`<foreach>`(`<include>` 조각 안까지, 조각이 있는 파일:줄을 근거로), DB 방언 분기(`isTibero`/`isPostgreSql`)를 따로, SQL의 `CASE WHEN`을 낸다. 화면·클래스는 이벤트 조건(`[Enter]` 등)과 도달 불가 이벤트, Java의 `if`/`else if`/`switch`/`throw`(여러 줄 조건, 주석·문자열 속 코드는 무시, 메서드·생성자별 묶음), `setEnabled`/`setVisible`/`setReadOnly`(고정값과 식 구분). `--side tobe`는 TSX의 `disabled`/`readOnly`/`hidden`, `&&`·삼항 조건부 렌더링, `if`
- 조건식은 소스에 적힌 그대로 내고 참/거짓 판정은 하지 않는다. 읽지 못한 조건과 `${}`는 unresolved
- `sql_parse`: `ParsedSql.cases`(CASE WHEN 식) 추가. `screen.py`: 이벤트·메서드 표를 구조화(`EventRow`, `MethodRow`)
- 구현된 명령 4개가 stub 테스트에서 빠지고 `test_trace_flow.py`, `test_trace_branch.py`가 검증한다

## [0.6.1] - 2026-10-28
`trace-screen`, `trace-table` 구현 (trace-* Step 1).
- `trace-screen <화면>`: 화면 색인 문서(`index-src` 결과)를 읽어 facts/evidence/unresolved로 재구성. 종류·메뉴(번호)·소스·함께 쓰는 클래스, 레이아웃·툴바·입력 위젯, 그리드 컬럼, 이벤트(도달 불가 표시), 버튼(인라인 핸들러는 줄 범위), 서비스(RPC)→SQL ID, 테이블, DB 함수, 서블릿 호출. 근거는 호출 위치(`클래스:줄`)·서버 메서드 줄·SQL의 mapper 파일:줄·색인 커밋/시각, 해석 못 한 호출은 unresolved
- 화면 지정: 클래스명(대소문자 무시), 접두사(`Emp00`), **메뉴 번호**(`#1029` 또는 `1029`, 색인의 `menus.md`). 모호하면 후보와 함께 종료 코드 2, 찾지 못하면 1
- `--class <하위클래스>`: 그 클래스의 UI와 그 클래스가 호출하는 서비스만 상세 출력. `--side tobe|both`는 같은 클래스명의 TSX를 찾아 `analysis tobe` 요약을 붙인다(`--tobe`로 frontend/src 지정)
- `trace-table <테이블>`: 스키마 스냅샷의 컬럼·PK·UNIQUE·코멘트, 같은 이름의 컬럼을 가진 테이블(FK가 없어 조인 후보로 제시, 백업·임시 테이블 제외), 참조하는 뷰, mapper 전체를 `sql_parse`로 해석한 C/R/U/D SQL 목록(AST 해석 불가 statement는 `*` 표시), 이 테이블을 쓰는 서비스(`UpdateDataModel` 동적 쓰기 포함)와 호출 클라이언트 클래스·소속 화면(메뉴 번호). `--stats`는 읽기 전용으로 행 수를 조회(최근 갱신일은 컬럼 규칙 미확정이라 제외)
- 공통: `--src`, `--src-index`로 소스·색인 위치 지정, `--max`는 facts·evidence에만 적용. 구현된 두 명령은 stub 테스트에서 빠지고 `test_trace_screen.py`, `test_trace_table.py`가 검증한다

## [0.6.0] - 2026-10-28
`trace-*` 구현 기반(공통 렌더러·대상 해석기, SQL 해석 어댑터)과 기존 SQL 해석 코드를 pglast 기반으로 통합.
- 신규 의존성 `pglast>=8.7` (PostgreSQL 서버 파서 libpg_query 바인딩, 바이너리 휠)
- `tools/trace/render.py`·`resolve.py`: `trace-*` 공통 출력(facts/evidence/unresolved 3블록, `--max` 절단은 unresolved를 숨기지 않음)과 `--side`/색인/화면 이름 해석. 기존 `trace-*` stub 출력은 이 렌더러를 쓴다 (md의 facts 첫 줄에도 `- ` 표시가 붙는다)
- `tools/sql_parse.py`: MyBatis를 `explain` 모드로 전개해 AST로 해석하는 어댑터. 테이블(R/W)·CTE·함수·컬럼 귀속·SELECT 출력 이름(`SELECT *`는 스냅샷으로 확장)·UPDATE/INSERT 대입·WHERE를 구한다. 문법 오류는 정규식 추정(`fallback`)으로 되돌리고, `${}`는 unresolved로 알린다. `<choose>`는 분기를 바꿔 가며 전개해 테이블을 합친다
- `mybatis_render`: `explain` 모드의 `<choose>` 분기를 `__pick__` 파라미터로 고를 수 있다 (기본값은 기존 동작과 동일)
- 통합: `tools/parse_mapper.py`(`mapper_index`), `src_indexer.parse_mappers`(호출 경로 색인), `analysis sql`(md), `analysis model`, `events.find_mapper_for_model`, `sql_checker.select_output_names`가 어댑터를 쓴다. 해석할 수 없는 statement와 `<sql>` 조각은 기존 정규식 경로를 유지한다
- **결과 변화**: 주석 처리된 SQL(`<!-- -->`)의 테이블, `AS 별칭`, `EXTRACT(... FROM 컬럼)`, CTE 이름, `<include refid>` 조각 이름이 테이블로 잡히던 오탐이 사라지고, `<include>`로 가져온 테이블이 포함된다. Tibero 전용 분기(`isTibero`)의 테이블은 제외된다. `mapper_index`가 바뀌므로 `uv run tools/parse_mapper.py`를 다시 실행해야 한다
- `tools/dump_sql_tables.py`: 교체 전후 테이블 해석 결과를 덤프·비교하는 회귀 확인 스크립트

## [0.5.10] - 2026-10-28
`trace-*` 업무파악 인자형 명령어 계층 껍질(stub) 18개 구현 및 log request 별칭 추가.
- `trace-*`: 업무 개념(탐색·데이터·규칙·대조·카탈로그) 중심의 18개 명령어 껍질(stub) 등록 (`trace-map`, `trace-menu`, `trace-screen`, `trace-table`, `trace-column`, `trace-code`, `trace-state`, `trace-crud`, `trace-flow`, `trace-branch`, `trace-dblogic`, `trace-pair`, `trace-diff`, `trace-gap`, `trace-rule`, `trace-term`, `trace-doc`, `trace-guide`)
- 공통 옵션 지원: 모든 `trace-*` 명령어에 `--side (asis|tobe|both)`, `--format/-o (md|json)`, `--max <N>` 지원
- 표준 3단계 블록 출력: Markdown(`## facts`, `## evidence`, `## unresolved`) 및 JSON 일관된 규격 반환
- `log request`: 실시간 요청 로그 명령어 `yunhee log trace`와 신규 `trace-*` 간 혼동 방지를 위해 `yunhee log request` (단축 `req`) 별칭 추가 및 상호 호환 보존

## [0.5.9] - 2026-10-28
수정사항 044 (도달 불가 오판 개선, ui --tobe 경로 오류, sql-check 단일 파일 및 후보 제시, port-sql --raw, sql --scalar, 불리언 파라미터, 그리드 속성 보존, 단일 스칼라 비교, 오버로드 일괄 출력, MyTextArea, 훅 안내 개선) 반영.
- `events`: `ToggleGroup` 등 컨테이너에 `add`된 위젯이 툴바에 부착되면 그룹 이벤트도 도달 가능으로 판정, `Lookup`/`Dialog`/`Window` 클래스의 `open()`/`show()` 등 공개 진입점 메서드의 도달 불가 오판 수정 (044-22)
- `analysis ui`: `--tobe` 경로가 cwd 기준 미존재 시 프로젝트 루트/frontend 경로 자동 폴백 및 미발견 시 명시적 오류 발생 (044-23)
- `sql-check`: `--tobe`에 XML 단일 파일 경로 직접 전달 허용, `--only` 매퍼 필터 0건 일치 시 후보 목록 안내 및 대소문자 무시 부분 일치 지원 (044-24)
- `port-sql`: `--raw` (또는 `--verbatim`) 옵션 추가로 원본 SQL을 변경 없이 `:param → #{param}`만 치환하여 `<![CDATA[ ]]>` 블록으로 출력, `SELECT *` + `JOIN` 모호 열 경고, `--insert-into` / `--insert-cols`를 통한 명시적 INSERT-SELECT 매퍼 생성 지원 (044-25)
- `sql`: `--scalar` 옵션 추가로 첫 행 첫 열 값만 단일 문자열로 출력 (쉘 스크립트 변수 할당용), `--help`에 쉘 변수 할당 예시 추가 (044-26)
- `mybatis_render`: `b:true` / `b:false` 타입 강제 접두사 지원 및 불리언 분기 조건(`x == true`, `x != true`, `!x`) 정확한 평가 (044-3)
- `comparator`: 그리드 스펙 속성명 보존(비범용 속성명의 DB 약어 치환 방지) 및 `FullName` ↔ `FNm`, `Code` ↔ `Cd` 필드 커버리지 매칭 추가 (044-4)
- `comparator`: 1행 1열 반환 단일 집계(count/sum 등) SQL에 대해 API `total`/행 수/스칼라 응답과 직접 비교 지원 (044-5)
- `analysis method`: `--all-overloads` 옵션 추가로 오버로드된 모든 메서드 본문/요약을 Exit 2 중단 없이 한 번에 확인 (044-6)
- `analysis grid`: `addTextArea(..., new MyTextArea())` 등 편집기 인자가 있는 경우 `editor_kind: largeText`로 표시 (044-7)
- `tools/hook_guard`: 훅 차단 시 안내 메시지 최상단에 `yunhee cat <파일>:<시작>-<끝>` 최우선 제시 (044-8)

## [0.5.8] - 2026-10-28
수정사항 044-1: compare --src-index 지원 및 하위 디렉터리 색인 자동 감지/일관성 개선.
- `compare`: `--src-index` 옵션 추가 및 `compare_api_sql`, `find_screen_grid_info`에 `src_index` 경로 전달 지원 (044-1)
- `resolve_as_is_paths`: `compare`와 `analysis`가 공통 경로 해석기를 공유하여 `YUNHEE_SRC_INDEX_DIR` 환경변수 및 `.yunhee.toml`의 `[as_is] src_index` 우선순위 지원 (044-1)
- `find_as_is_dir`: 저장소 루트(`framework-sprt`)에서 실행 시 하위 프로젝트 디렉터리(`AssetERP/docs/as-is/src` 등) 자동 탐색 폴백 추가 (044-1)
- `config`: `YUNHEE_SRC_INDEX_DIR` 환경변수 및 `src-index` 설정값 조회(`yunhee value src-index`, `yunhee config`) 추가 (044-1)

## [0.5.7] - 2026-10-27
화면 파일 페이지 스타일 판별기(`page-style`)에 신규 SID `SGTP` 추가 반영.
- `page-style`: 신규 페이지 스타일 ID `SGTP`(SearchGrid+TabPage: 위아래 분할 + 그리드 + 아래 탭 영역 `*_TabPage_*`) 추가
  - TSX 및 Java에서 하위 탭 영역 컴포넌트(`*_TabPage_*`) 임포트 및 인스턴스화 추적 (`tabpage: true`)
  - `*_TabPage_*` 내부의 그리드/폼은 메인 화면의 그리드 수에 중복 합산되지 않도록 격리 처리
  - 위아래 분할 레이아웃 + 그리드 1개 + 아래 탭 영역인 경우 `SGTP`로 결정적 판별

## [0.5.6] - 2026-10-27
화면 파일(.tsx / .java) 페이지 스타일 ID(SID) 판별 및 대조를 위한 인자형 명령어 `page-style` 추가.
- `page-style`: 화면 파일(.tsx/.java)의 페이지 스타일 ID(SID: SG, SGP, SGVF, SGEF, SGT, TG, GG, CG, 미분류) 판별 및 대조 신규 명령어 추가
  - 단일 화면 SID 판별(`yunhee page-style <file>`) 및 머리 주석 선언 스타일(`스타일: XXX`) 불일치 경고
  - AS-IS와 TOBE 화면 간 SID 일치 여부 검증(`yunhee page-style --compare <asis.java> <tobe.tsx>`) (종료 코드: 일치 0, 불일치 1)
  - 디렉터리 내 모든 `*_Tab_*` 화면 일괄 판별 및 SID별 분포 통계 집계(`yunhee page-style --all [디렉터리]`)
  - 특징(features: 그리드·트리·폼·팝업·분할 레이아웃 등) 및 판별 근거(why) JSON 출력 지원(`--json`)
  - 파일명 지정 시 현재 작업 경로, WORK_DIR, ASIS_SRC_DIR 자동 경로 탐색 지원

## [0.5.5] - 2026-10-26
수정사항 043 (인자형 명령어 개선, null: 파라미터 지원, 훅 회피용 파일 부분 읽기 `cat`/`outline --range`, API 사전 경로 보정 및 401 재시도, compare 오류 간소화, 도달 판정 정상화) 반영.
- `cat`: 지정한 파일들의 특정 줄 범위를 핀포인트로 읽는 신규 명령어 `yunhee cat <file>:<range>...` 추가 (예: `yunhee cat a.java:1-30 b.xml:100-140`), 외부 훅 차단 방지 (043-7)
- `outline`: 특정 줄 번호 범위(`--range`/`-r L1-60`)를 지정하여 원문 코드를 직접 읽을 수 있는 옵션 추가 (043-7)
- `mapper-run` / `compare` / `analysis sql`: `-p key=null:` (또는 `--param key=null:`) 접두사 구문 지원으로 SQL `NULL` 바인딩 및 MyBatis `<if test="key != null">` 미진입 처리 (043-10)
- `api` / `compare`: `-c` / `--company` 옵션의 도움말을 명확화하고, 로그인 실패 시 `-c`는 회사코드(예: `admin`, `kfstest`)이며 숫자 입력 시 companyId 오해 여부 힌트 출력 (043-18)
- `api`: 요청 전 `auto_prefix`(`/api/v1/`)를 사전에 적용하여 서버 404 및 불필요한 리소스 부재 로그 방지 (043-11), `TOKEN_EXPIRED` 수신 시 저장된 세션을 폐기하고 자동 1회 재로그인/재시도 (043-19)
- `compare`: AS-IS SQL 실행 실패 시 200줄의 SQL 전문 덤프를 생략하고 간결한 1줄 에러와 `TOBE API 결과: rows=N` 출력 (043-15)
- `analysis sql`: CTE를 `-- CTE ... (생략)`으로 접는 `--no-cte` 옵션 및 WHERE 절 이후만 분리 출력하는 `--section where` 옵션 추가 (043-16)
- `analysis ui`: `--tobe` 옵션에 쉼표 구분 복수 경로(`dir1,dir2`) 지정 지원 (043-3), `--done` 또는 `--later`에 명시된 클래스는 타 도메인이더라도 대조표에서 제외하지 않고 보존 (043-3)
- `drift`: `--note-file`로 전달된 파일이 존재하지 않는 경우 신규 생성하지 않고 오류로 안전하게 중단 (043-21)
- `events`: `this.getButtonBar().add(w)` 및 `getButtonBar().insert(w, ...)` 형태의 창/패널 단추 도달 불가 오판 해결 (043-9, 043-13), `닫기` 버튼 및 `closeButton.hide()` 핸들러는 `type="close"`로 확정 매핑 (043-9)
- `port-sql`: include 대상 펼침 시 외곽 `<sql id="...">` 태그를 제거하여 MyBatis 구문 오류 방지 (043-11)
- `hook_guard`: 훅 차단 시 `⚠ 이 명령은 실행되지 않았습니다(앞 명령 포함).` 문구 명시 (043-20)

## [0.5.4] - 2026-10-25
수정사항 042 그룹 D (`table` 테이블 반환 함수 DBML 변환, `outline` 마크다운 제목 및 `--tail` 지원, `analysis` 수용 기준 전 항목 마무리) 반영.
- `table` / `analysis sql`: `RETURNS TABLE(...)` 정의를 가진 PostgreSQL 함수(`getPerson`, `getOrg`, `getTdm30RoleAllc` 등) 및 매퍼 namespace(`emp00_trans_info` 등)를 가상 DBML `Table` 블록으로 출력하고, `analysis sql`의 `- **함수**:` 절에 `(열은 yunhee table <함수명>)` 안내 표시 (042-10)
- `outline`: 마크다운(`.md`/`.markdown`) 파일의 `#`~`######` 제목(코드 펜스 내부 제외) 추출 지원 및 파일 끝부분 N줄을 함께 확인하는 `--tail N` 옵션 추가 (042-12)
- `analysis ui`: 화면 색인(`.md`)에 하위 팝업이 병합된 경우 클래스 단독 이벤트/그리드 수 분리 집계, `*_Common.tsx` import 추적 및 TOBE `// [E#]` 주석 부재 시 안내 문구 출력 (042-3, 042-8, 042-18)
- `analysis screen` / `events`: 색인(`.md`)이 없는 독립 컴포넌트(`Org00_Lookup_SelectSingle` 등) 조회 시 `.java` 소스를 직접 분석하는 폴백 지원 (042-4), 필드 초기화 `QuickMoveField` 익명 `InterfaceCallback` 이벤트(`callbackOnCreate`/`callbackOnCollapse`) 추출 (042-9), 핸들러 내 `callback.execute(...)` 호출(`callback(null), hide()`) 표시 (042-16), `GridGroupBuilder` 지원 및 `addHeaderGroupMap` 가짜 열 제외 (042-6, 042-18), `"생성"` 포함 버튼 `generate` 자동 매핑 및 `"작성"`/`"복제"` 후보 제시 (042-19)
- `analysis method` / `layout` / `grid`: 생성자(`ClassName.ClassName -o code`) 본문 추출 및 오버로드 위임 체인(`open(...)`) 자동 합산 요약 (042-5, 042-17), `buttonBar.add(...)` 툴바 아이템 순서·너비·빈칸(`LabelToolItem("")`) 및 HTML/CSS 스타일 상수 추출 (042-5), `HeaderGroupMap` 다중 행 열 범위·고정 열(`frozen_cnt`)·동적 헤더 변경 메서드 추출 (042-6)

## [0.5.3] - 2026-10-25
수정사항 042 그룹 C (`analysis ui` · `screen` · `grid` · `method` · `layout` 정적 분석 고도화) 반영.
- `analysis ui`: 화면 컨테이너/분할/탭 구조(`BorderLayout` 영역·크기·split·collapsible·min, `TabPanel` 탭 구성, 모달 `setPixelSize`) 자동 추출 (042-3), 조회바·입력 비버튼 위젯(`CodeComboBox`, `SimpleComboBox`, `DateField`, `Radio`, `CheckBox`, `LookupTriggerField`, `TextField` 및 Enter 키 바인딩) 순서대로 추출 (042-8), `--layout` 옵션으로 클래스별 폼 레이아웃 상세 동시 출력 (042-18)
- `analysis screen` / `events`: 메서드 표의 `-` 및 `상태 처리` 항목을 `executeService`, `GridInsertRow`/`GridUpdate`, 팝업 `.open()`/`.show()`, `fireEvent`, `editDriver.edit/flush`, 스토어 조작, 파일 입출력 등으로 구체화 및 동적 보강 (042-4), `--section methods` 일괄 상세 요약 추가 (042-5), `## 컴포넌트 간 이벤트 흐름`(`fireEvent` ──▶ `addChangeHandler`, `--section flow`) 추출 (042-9), `## Lookup 팝업 연결`(`--section lookup`) 추출 (042-16), `## 파일 입출력`(`FileUploadField`, `FormPanel MULTIPART`, `SubmitCompleteHandler`, 엑셀 입출력, `--section file`) 확장 (042-19)
- `analysis grid`: 2단 헤더 그룹(`addHeaderGroup`, `HeaderGroupConfig`, `HeaderGroupMap`), 합계/집계 행(`AggregationRowConfig`, `SummaryType`), 커스텀 셀 렌더러(`AbstractCell`), 체크박스 편집 가능 여부(`checkbox(편집가능)` / `checkbox(읽기전용)`), 콤보박스/Lookup 편집기 상세 표시 (042-6)
- `analysis method`: 다중 메서드 동시 조회(`analysis method <클래스> <m1> <m2>` 또는 `<클래스>.<m1>,<m2>`), `--raw` 요약+원문 동시 출력 (042-5), `SimpleComboBox.add(...)` 및 `CodeComboBox` 생성자 선택지 목록 자동 추출 (042-17)
- `analysis layout`: `HBoxLayoutContainer`/`VBoxLayoutContainer`/`BoxLayoutData` 지원 추가 및 필드별 위젯 타입(`(TextField)` 등), 필수 입력(`*`), 읽기전용·비활성(`[readOnly]`/`[disable]`) 인라인 표기 (042-18)

## [0.5.2] - 2026-10-25
수정사항 042 그룹 B (`compare` 파라미터/분기·타입 바인딩·이름 규칙 차이·페이징 대조 개선 및 `api -F` 멀티파트 파일 업로드 지원) 반영.
- `compare`: `admin` 계정(`org_id=0`)이거나 `<when>`/`<if>` 분기 조건 변수(`orgId`, `empId`)인데 명시하지 않은 경우 세션 `user_info` 자동 주입을 방지하여 비활성 분기 진입 및 `-- 필요: retrieveType` 오탐 해결, `SQL params: ... (branch: ...)` 분기 판정 표시 및 행 수 불일치 시 `mapper-run` 힌트 안내 (042-2)
- `compare` / `mybatis_render`: `--param key=s:val`(문자열 강제) 및 `n:val`(숫자 강제) 구문 지원, 코드/구분 변수(`managerType` 등)에 숫자 형태 값 전달 시 문자열 리터럴(`'21'`)로 자동 바인딩하여 `character varying = integer` 타입 오류 방지 (042-14)
- `compare` / `index-src`: `addHeaderGroupMap` 등에서 오인된 가짜 열(`new`) 제외, `Sys99_PrintModel`(`string01..`, `long01..`) 등 범용 모델 컬럼이나 명명 규칙 차이 시 `⚠️` 대신 `ℹ 이름 규칙 차이로 이름 대조 생략` 안내 (042-7)
- `compare`: 페이징 응답(`PageRes` `{total, rows}`) 비교 시 현재 페이지 `rows` 길이와 SQL 결과 행 수를 기본 대조하고 `--total-sql`(`--sql-total`) 지정 시 페이지 행 수와 전체 건수를 함께 검증 (042-20)
- `api`: `-F` / `--form <name>=@<파일경로>[;type=<MIME>]` 및 `<name>=<값>` 멀티파트 파일 업로드 옵션 추가, `--body`와 동시 사용 차단 및 업로드 파일명·크기 요약 출력 (042-15)

## [0.5.1] - 2026-10-25
수정사항 042 그룹 A (`port-sql` 서브쿼리 `t.*` 확장 및 계산 열 타입 추론, `port-save` `--insert-cols` 및 자동 채움 표시) 반영.
- `port-sql`: `FROM ( SELECT ... ) t` 서브쿼리의 바깥 SELECT에 `t.*`와 계산식(`* 100.0` 등)이 함께 있을 때 곱셈 연산자 `*`를 와일드카드로 오인하던 정규식 버그 수정, 서브쿼리 내부 SELECT 별칭 목록으로 `t.*` 자동 확장, Model 필드 타입(`Double`, `Long` 등) 연동으로 DTO record 필드 타입 정밀 결정 (042-1)
- `port-save`: INSERT 문에만 포함하고 UPDATE SET에서는 제외하는 `--insert-cols` 옵션 추가, `UpdateDataModel`이 자동으로 채우는 `*_upd_nm` / `*_upd_date` 컬럼이 테이블에 있을 때 부수 효과 절에 `자동 채움:` 안내 표시 (042-11)

## [0.5.0] - 2026-10-23
자율 에이전트 하네스(Agentic Harness), 하이브리드 장기 기억, Gotenberg 산출물 발간 및 단일 DB 자율 질의 통합 메이저 릴리즈.
- **Agentic Harness & REPL 자율 루프**: `yunhee` 서브커맨드 없이 실행 시 진입하는 대화형 REPL 에이전트 하네스 구축. Rich 라이브 스피너, ESC 2회 즉시 취소, 모델-도구 자율 루프 및 자기 수정(Self-correction) 지원.
- **하이브리드 장기 기억 (L1 Rules + L2 Semantic Knowledge)**: L1 규칙(.yunhee/memory.md, 40줄 가드) 자동 프롬프트 주입 및 L2 ChromaDB(bge-m3) 벡터 스토어 연동 에러 해결 노하우/지식 축적 및 시맨틱 프리페치 지원.
- **MCP (Model Context Protocol) 확장**: `/init` 시 `.yunhee/mcp.json` 자동 생성 (time, fetch 기본 내장), 백그라운드 이벤트 루프 스레드 기반 `MCPManager`로 MCP 서버 도구 동적 확장.
- **마이그레이션 기술 명세서 및 Gotenberg PDF 발간 (`/out`, `/out:pdf`)**: 화면 코드로부터 UI 이벤트, AG Grid Spec, 버튼 JSX, DBML 테이블 스키마, 소스 Outline을 자동 집약한 명세서 마크다운 생성 및 Gotenberg Chromium 연동 공식 PDF 원클릭 발간. `/out:pdf session`으로 전체 대화록 PDF 발간 지원.
- **자율 DB 쿼리 및 통합 객체 정의 조회 (`run_sql`, `get_db_definition`)**: PostgreSQL(`YUNHEE_DB`) 안전한 읽기 전용 쿼리 실행, 테이블 DDL(DBML)과 스토어드 함수/프로시저(341개) PL/pgSQL 본체 소스코드, 뷰 정의를 한 번에 조회하는 통합 도구 추가. `\d`, `\df+`, `\sf` 등 psql 메타 커맨드 자동 라우팅.
- **설정 단순화 및 단일 DB 고정**: `.env.yunhee` 우선 로드 (`.env.yunhee.sample` 템플릿 제공, `.gitignore` 완비), `YUNHEE_DB` 단일 고정 및 `LOCAL_DB` 100% 하위 호환.

## [0.4.7] - 2026-10-21
- 개발 작업 진행 중

## [0.4.6] - 2026-10-21
- `value`: 현재 설정값 단일 텍스트 출력(스크립트 치환용) 및 키 목록 확인 커맨드 추가 (`yunhee value [KEY]`, `--list`, `--keys`, `--raw` 지원). 대소문자 및 별칭(`asis-src`, `work-dir`, `local-db` 등) 유연 매칭.
- `config`: 독립 설치(`uv tool install`) 환경에서도 `YUNHEE_DIR`(`.env.local` 및 `data/`)를 자동 탐지(`_find_yunhee_dir`)하도록 개선하여, 개발 중 소스 변경이 전역 CLI에 영향을 주지 않도록 독립 배포 지원.

## [0.4.5] - 2026-10-20
수정사항 041 (매퍼 XML 정형 검사, 기동 실패 감지, deploy 명령 후 자동 헬스체크) 반영.
- `sql-check --tobe`: 각 매퍼 XML 대상 XML well-formed 구문 검사(`ET.fromstring`) 사전 수행, 파싱 실패 시 `❌ XML 오류: <파일>:<줄>:<열>` 및 특수문자(`<`, `<=`, `<>`, `&`) 이스케이프 힌트 출력, `--summary`에 `XML ❌` 집계 (041-1)
- `log`: `--since-deploy` 범위 계산 시 마지막 배포 이후의 기동 실패(`Application run failed`·`Context initialization failed`·`Error creating bean`)를 먼저 탐지하여 최상단에 `🚨 마지막 배포(HH:MM) 뒤 앱 기동 실패: <원인>` 경고 출력 및 매퍼 파일명 안내 (041-2)
- `run`: 배포(`deploy`) 관련 명령어 종료 후 최대 N초 동안 로그를 감시하는 자동 헬스체크 추가, 기동 성공 시 `✅ 앱 기동 확인 (N초)`, 실패 시 `❌ 앱 기동 실패: <원인>` 출력 및 실행 종료 상태를 실패(exit 1)로 변경, `--health-timeout`(기본 90초) 및 `--no-health` 옵션 지원 (041-3)

## [0.4.4] - 2026-10-20
수정사항 040 (`log --since-deploy` Docker exec 공백 인자 버그 수정) 반영.
- `log`: `find_deploy_time_docker`에서 `sh` 옵션 문자열의 선행 공백(`" -c"` → `"-c"`)을 제거하여 Docker 컨테이너(`t3600-tomcat`) 내 배포 시각 탐색 시 `sh: 0: cannot open  -c: No such file` 오류가 발생하는 결함 수정 (040-1)

## [0.4.3] - 2026-10-20
수정사항 039 (서버 위임 추적, 서블릿 분석, compare 페이징 및 --from-log, sql-check 필터, PreToolUse 훅, API 자동 경로 보정, run -C, analysis sql grep 및 파라미터 대입, save-script, 배포 대기, -u 사원 가장, mapper-run, 미도달 이벤트 감지) 반영.
- `analysis method` & `screen`: 서버 위임 메서드 추적(`getInDocument` → `makeDocument` 줄 범위/SQL 수 표시), `<패키지>.<클래스>.<메서드>` 패키지 명시 지원, 미발견 시 후보 목록 및 Exit code 2, 위임 전용 시 `⚠ 결과 없음` 경고 억제 (039-1, 039-16)
- `analysis servlet`: 서블릿 다운로드/보고서 분석 커맨드 추가, `analysis screen --section servlet` 지원, `src_indexer` 서블릿 URL 색인 생성 (039-2)
- `compare`: 페이징 응답 자동 감지(`{rows, total}`), 행수 및 총합 비교, `--sql-total <ns.id>` 지정 및 자동 `COUNT(*)` 비교, `[compare] paging_keys` 설정 지원 (039-3)
- `sql-check --tobe`: `--only <glob>` 특정 매퍼 필터, `--changed` 변경/추가 매퍼 자동 탐지, `--summary` 성공/실패 요약 행, 대상 범위 실패 시에만 Exit code 1 반환 (039-4)
- PreToolUse Hook: `hook_guard.py` 명령 토큰화(따옴표/플래그 안전 파싱), `&&`/`||`/`;` 체이닝 지원, `yunhee-guard.sh` 연동 (039-5)
- `api`: 404 발생 시 `/api/v1/` 자동 재시도 및 `ℹ 경로를 /api/v1/... 로 보정` 안내, `[api] auto_prefix` 설정 지원 (039-6)
- `run`: `-C/--cwd <경로>` 작업 폴더 지정 옵션 추가, 실행 전 `cwd: <경로>` 명시, `[run] cwd` 설정 지원 (039-7)
- `analysis sql`: 중복 include 정형화, `--grep <패턴> -C <줄수>` 옵션 추가 (039-8)
- `analysis sql`: 파라미터 대입 모드(숫자 리터럴, 문자열 따옴표, 누락 변수 `-- 필요: k`), if/choose 분기 조건 평가 및 `-- 분기 제외: <var>` 주석 표시 (039-9)
- `analysis save-script`: 서버 저장 메서드 쓰기 SQL들을 순서대로 추출하고 파라미터를 대입하여 트랜잭션 롤백 스크립트로 생성하는 커맨드 추가 (039-10)
- `api` / `compare`: 배포 직후 기동 중 감지 안내(`ℹ 배포 후 앱이 아직 올라오는 중일 수 있음`), `--wait-deploy [초]` 대기 옵션 지원 (039-11)
- `api` / `compare` / `sql`: `-u/--as <사원번호|이름>` 사원 가장 로그인, `emp00_trans_info` 기반 부서/회사 자동 조회 및 세션 격리, `empId/orgId/companyId` 파라미터 자동 바인딩 (039-12)
- `compare`: `--from-log` 지정 시 직전 trace 로그의 바인딩 파라미터를 자동 추출하여 AS-IS SQL에 매핑, `사용한 파라미터:` 안내 (039-13)
- `mapper-run`: TOBE MyBatis 매퍼의 XML statement를 실제 DB에서 안전하게 실행하는 도구 추가, 쓰기문 `--rollback` 강제, `--compare <ns.id>` AS-IS SQL 비교 지원 (039-14)
- `analysis ui`: 도달 불가능한 이벤트 핸들러(호출되지 않는 메서드, 컬럼/툴바 미연결 위젯) 감지, `--unreachable count|ignore` 옵션 지원 (039-15)

## [0.4.2] - 2026-10-18
수정사항 037 (`analysis model`/`grid` 와일드카드 테이블 열 검증, `port-sql` 계산 getter 지원, `analysis method -o code` 짧은 오버로드/위임 인라인 출력, `analysis ui --tobe` E0 안내) 반영.
- `analysis model --sql`: `테이블.*` 또는 `*` 와일드카드 매칭 시 실제 DB 테이블(DBML/스키마 스냅샷)에 해당 컬럼이 존재하는지 대조해 없으면 `⚠ 테이블에 열 없음`으로 표시 (037-1)
- `analysis grid`: 그리드 열이 모델 `resultMap` → 화면 조회 SQL → DB 테이블까지 이어지는지 검증하는 `컬럼 검증` 열(`✅` / `계산` / `⚠ SQL에 없음` / `⚠ 테이블에 없음`) 및 `--check-columns/--no-check-columns` 옵션 추가 (037-2)
- `port-sql`: `--cols`에 모델 계산 getter가 포함될 때 `// ⚠ SQL 열 없음` 대신 getter 본문 주석(`// getAdminYn L146-149: ...`), 단순 비교식의 SQL 표현식 후보 주석, getter 반환 타입(`Boolean` 등) 반영 (037-3)
- `analysis method -o code`: 오버로드 후보들이 5줄 이하이거나 다른 오버로드로 위임(`→ #1 위임`)하는 경우 후보 목록 아래에 본문을 바로 이어 출력하고 `Exit 0`으로 종료 (037-4)
- `analysis ui --tobe`: `E0(미구현)` 발생 시 표 아래에 생성자 이벤트 주석(`// [E0] …`) 안내 출력 (037-5)

## [0.4.1] - 2026-10-17
수정사항 035 (`analysis sql -o json` 렌더링 실패) 반영.
- `analysis sql -o json`: `file`을 문자열(상대 경로)로 변환해 `Object of type PosixPath is not JSON serializable` 오류 수정. `sql`·`screen --list`·`ui`의 `-o json`에 `default=str` 안전장치 추가 (035-1)

## [0.4.0] - 2026-10-17
수정사항 034 (`index-src` 바깥 git 저장소 오인, `analysis screen --list` 열 의미, `-o json`) 반영.
- `index-src`: 소스 폴더가 git 저장소의 루트가 아니면(`.git` 없는 하위 폴더) 바깥 저장소를 무시하고 `vcs: none`(파일 sha256)으로 기록하며 경고 출력. 하위 폴더를 소스로 쓰려면 `--vcs-root <저장소 루트>` 지정, `_source.json`에 `vcs_root`/`outer_repo` 기록 (034-1)
- `drift`: 색인이 `vcs: none`이면 머리에 `소스 (git 정보 없음 — sha256 비교)` 안내 (034-1)
- `analysis screen --list`: 열을 `줄(원본)`(원본 Java 파일 줄 수)·`줄(UI절)`(색인 절 줄 수)로 분리하고 열 정의·`※ 합계는 연결·다른 도메인 클래스 제외` 주석 추가 (034-2)
- `analysis screen --list`·`ui`·`sql`에 `-o json` 추가 (034-3)

## [0.3.9] - 2026-10-16
수정사항 033 (`yunhee sql` 출력 형식·파일 저장·내장 SQL, `drift --record-from` 일괄 기록, `index-src`·`drift` 화면 수 요약 표기) 반영.
- `yunhee sql`: `-o/--output table|tsv|csv|json`, `--no-header`, `--null`, `--out <파일>`(원자적 저장 및 1줄 요약), 마크다운 표 `|` 이스케이프 지원 (033-1)
- `yunhee drift`: `--record-from <표 파일>` / `--record-all` 일괄 baseline 기록, `--status`·`--dry-run`·`--force` 지원, 해시 변경 시 덮어쓰기 방지 가드 (033-2)
- `yunhee index-src` & `drift`: 총 화면 수와 구성(`화면 N개(메뉴 M + 프레임 K)`) 통일 표기, `--menus` 미지정 시 `연결 안 됨(--menus 없음)` 안내, `_source.json`에 `screens_menu`·`screens_frame` 분리 저장 (033-3)
- `yunhee sql --builtin menus` 및 `index-src --menus-from-db`: `psql` 없이 메뉴 TSV 생성 지원 및 색인 `README.md` 안내 갱신 (033-4)

## [0.3.8] - 2026-10-16
수정사항 032 (AS-IS 소스 변경(drift) 감지 및 화면 완성 기준선 기록) 반영.
- `index-src` 소스 기준(커밋·파일 해시·역색인 `_files.json`) 기록 및 직전 색인 `_prev/` 보존, `analysis screen --section source` 지원 (032-1, 032-4)
- `yunhee drift`: 색인/완성 기준선 대비 AS-IS 화면·파일 변경 감지 (`table`/`diff`/`full`/`json`, `--new`, `--fail-on-drift`) (032-2)
- `yunhee drift --record`: 화면 완성 시점의 AS-IS 기준선 기록 (`.yunhee/baseline.json`, `--note-file`, `--show-baseline`) (032-3)
- 다중 PC 작업 시 소스 커밋·브랜치 불일치 경고 (`index-src`, `drift`, `config`) (032-5)

## [0.3.7] - 2026-10-16
수정사항 031 (analysis ui SearchBar 버튼 집계 및 E-id 차이 목록, 동적 SQL 이름·미정의 SQL 경고, 버튼 type 미등록 구분, overload 선택 체인 요약, 클래스 필드 초기값, outline 타입 필드) 반영.
- analysis ui: TOBE `<SearchBar>` 컴포넌트(`<SearchBar onSearch=...>`)를 조회 버튼 1개로 집계, `onReset`은 무시, `extra={<Button .../>}` 내부 버튼 집계, `.yunhee.toml`의 `[tobe.components]` 설정 오버라이드 지원 (031-1)
- analysis ui: AS-IS에만 있는 E-id 목록(`없음: E6(생략), E11(미구현)`) 한 줄 표시, TOBE 주석 `// [E6 생략]` 사유 인식, 생성자 초기화 제외 `--no-e0` 옵션 지원 (031-2)
- analysis screen: `service.retrieve("..." + sql)` 동적 SQL 이름 변수 분기(`if`/`else`)를 추적하여 후보 SQL 행들을 `(동적 이름)` 및 조건식과 함께 서비스 표에 모두 표시 (031-3)
- analysis screen & method: 매퍼에 없는 SQL 호출 시 `(없음) ⚠ 매퍼에 SQL 없음 — 원본에서도 실패` 경고 표기 및 화면 요약 상단에 `⚠ 미정의 SQL 호출 N개` 배너 표시 (031-4)
- as-is events: 버튼 type 판별 실패 시 `unknown (미등록 문구)` / `unknown (제목 인식 실패 — 생성 코드 L...)` 원인 구분 및 가장 가까운 type 후보 추천(`/* 후보: upload (파일업로드) */`), `extract_buttons`의 `btn_map` 오버라이드 지원 (031-5)
- analysis method: `--called-from <호출 클래스>` 옵션 추가로 호출부 인자 타입 기반 overload 자동 선택 및 위임 체인(`open L124 → open L165`), 버튼·그리드 설정 요약 (031-6)
- analysis screen: `--section fields` 지원으로 상태 필드 이름·타입·초기값 및 사용처(읽는 곳/쓰는 곳 줄 번호) 추출 (031-7)
- outline: `--members` / `-m`, `--symbol` / `-s` 옵션 추가로 TypeScript interface/type의 필드 목록 및 주석 추출, API 함수 반환 타입(`name(args): ReturnType`) 표기 (031-8)
- log_reader & api_client: 약어 namespace(`...m.S`) 매퍼 식별 시 요청 URL 토큰 기반 명확화 및 중복 파라미터 매핑 개선, 404 No static resource 응답 시 `/api` 접두 힌트 제공 (031-9)

## [0.3.6] - 2026-10-15
수정사항 030 (port-sql 서브쿼리 FROM 오류 해결, port-save 회사 컬럼명 보정, analysis grid 아이콘 셀 오판 방지, compare 0건/컴포넌트 탐색 개선, analysis sql 단일 집계값 출력) 반영.
- port-sql: 괄호/서브쿼리/OVER/CASE 깊이 0 기준 SELECT 열 분리(`split_depth0_commas`) 및 최상위 `FROM` 절 원문 보존으로 상관 서브쿼리·서브쿼리 JOIN이 있는 복합 SQL의 열 누락 및 중복 `FROM {table}` 문법 오류 해결
- port-sql: `--cols` 지정 시 매칭 컬럼을 별칭/DTO에 반영하고 매칭 순서대로 정렬, SQL에 없는 속성은 `⚠ SQL 열 없음: x` 경고 안내
- port-save: `--company-col`에 접두사 없는 이름을 지정해도 `{prefix}company_id` 자동 보정, 파라미터명 `#{companyId}` 통일 및 delete 문 `<foreach>`의 item 변수를 분리하여 `#{companyId}`와의 파라미터 충돌 방지
- port-save: 테이블 컬럼 분석을 통한 화면 INSERT 후보 열(person_id, start_date 등) 자동 안내 경고 추가
- analysis grid & src_indexer: `addCell`, `ActionCell`, `ImageCell`을 편집기로 오인하지 않고 아이콘 셀로 판정하여 `SingleGrid` 분류 유지 및 표 편집기 열 비움/아이콘 표기
- compare: `actionCell`, `rowNumberer`, `checkBoxSelection` 등 비데이터 화면 컬럼을 그리드 대조 대상에서 제외하여 불필요한 missing 경고 제거
- compare: API 응답이 0건일 때 불필요한 필드 누락 경고 대신 `필드 비교 못 함 (행 0건)`으로 명확히 안내
- compare: `**/screens/*.md`뿐 아니라 `**/components/*.md` 경로까지 컴포넌트 그리드 색인 탐색 확장, 미발견 시 탐색 디렉터리 경로 안내
- analysis sql: `SELECT count(...)`, `SELECT sum(...)` 등 단일 집계 쿼리에 대해 `SELECT count(*) FROM (sql) z` 래핑 대신 직접 실행하여 `rows=1 count=<val>` 단일 요약값 출력
- yunhee-guard.sh: heredoc/리다이렉션 쓰기(`cat >`, `<<`, `sed -i`) 및 출력 파이프(`| tail`) 분리 파싱 지원, 차단 시 원인 명령어(`[차단 원인: ...]`) 명시

## [0.3.5] - 2026-10-15
MyBatis XML 조건식 태그 파싱 오류 수정 및 수치 비교 연산자 지원.
- mybatis_render: `<if test="personId > 1">` 등 따옴표 내부의 `>` 또는 `<` 문자를 태그 끝으로 오인하지 않도록 XML 토크나이저(`TOKEN_RE`) 및 `mask_sql_preserve`의 따옴표 보호 처리
- mybatis_render: 태그 속성 파싱 시 `&gt;`, `&lt;`, `&amp;` 등 XML 엔티티 자동 unescape 지원
- mybatis_render: `eval_test_condition`에 수치 비교 연산자(`>`, `>=`, `<`, `<=`, `==`, `!=`) 및 역방향 비교 지원 추가
- sql_porter & src_indexer: 태그 제거 정규식을 따옴표 보호 정규식으로 보강하여 XML 속성 내 특수문자 누출 방지
- analysis sql & compare: AS-IS SQL 렌더링 시 태그 잔여 문자열(` 1">`) 누출 및 SQL 깨짐 방지

## [0.3.4] - 2026-10-15
수정사항 029 (sql-check 주석 범위 분리, XML 태그 OGNL 대소문자 보존, diff 요약 길이 제한) 반영.
- sql-check: statement 앞 주석 범위를 바로 앞 요소(`</select>`, `</sql>`, `<mapper>` 등)의 끝부터로 한정하여 `<sql>` 조각 및 이전 statement 본문 주석의 오인 전파 방지
- sql-check: TOBE 주석에서 추출한 statement ID가 원본 매퍼에 존재하는 경우에만 출처로 인식하고, 일반 설명 문장 단어는 무시 (명시적 `L숫자`/`(L숫자)` 표기만 부재 시 `(미존재)` 처리)
- sql-check: `(IDMS-IC)` 등 새 원본 반영 표시 주석을 단일 주석(`<!-- ... -->`) 내부에서만 감지하여 다중 주석/SQL에 걸친 잘못된 반영 감지 방지
- sql-check: Drift 정규화 시 XML 태그 전체(`<...>` 안의 태그명, 속성명, OGNL 조건식)의 대소문자를 원문 그대로 보존하여 `test="isA == true"` 등 속성 대소문자 변경점 정상 감지
- sql-check: diff 요약 생성 시 SQL 키워드 대소문자 차이는 무시하되 출력 토큰은 원문 대소문자로 표기
- sql-check: diff 요약 덩어리를 최대 30토큰/200자에서 자르고 `… (+N토큰)` 표기, 3개 초과 시 `· 외 N곳` 표기, 줄 전체 400자 제한 적용 및 `-o json`에 `diff_full` 전체 목록 제공

## [0.3.3] - 2026-10-15
수정사항 028 (compare 그리드 탐색 보강, sql-check Drift 정밀화 및 잡음 제거) 반영.
- compare: `build\w*Grid\w*` 패턴 확장으로 `buildGridRole()`, `buildGridCompany()` 등 메서드 추출 지원 및 analysis와 정규식 통일
- compare: 다중 그리드 불릿 파싱 시 중첩 괄호(예: `체크박스(다중)`) 처리 보강 및 변수명(`#gridRole`)으로도 해당 메서드 바인딩 지원
- compare: 필드 대응에 `Address` ↔ `Addr` 줄임 매핑 추가 (`emailAddress` ↔ `emailAddr`, `zipAddress` ↔ `zipAddr`)
- sql-check: 매퍼 머리 주석의 경로 첫 단어(`server`)가 statement ID로 오인되는 문제 수정 (`server (미존재)` 방지)
- sql-check: TOBE 매퍼 주석의 `({새 원본명})`(예: `(IDMS-IC)`) 표시 감지하여 바뀐 원본 영향 목록에서 제외하고 `#### 새 원본 반영 표시됨` 절에 분리 표시
- sql-check: Drift 비교 시 문자열 리터럴/파라미터 밖은 대소문자 무시(PostgreSQL 식별자 표준)하여 불필요한 변경점 제거
- sql-check: diff 토큰화 개선으로 `'false'`, `#{companyId}`, `!=`, `</when>` 등이 쪼개지지 않도록 원형 보존
- sql-check: `--only-tobe` 출력에도 TOBE statement 하단에 바뀐 원본 SQL diff 요약 한 줄 인덴트 출력
- sql-check: `--old` 지정 시 `-t`/`--target` 옵션을 줄 경우에만 해당 파일로 저장하고, 미지정 시 stdout 출력 전용 동작 지원 및 도움말 갱신

## [0.3.2] - 2026-10-15
수정사항 027 (다중 그리드 집계 및 분리 정밀화, SQL Drift 감지, 배포 전 기동 상태 감지) 반영.
- analysis screen & ui: 클래스별 그리드 수 집계 시 `1 if ... else 0` 대신 불릿(`^- 그리드 ` / `^- 트리`) 및 Grid Spec(`const build*Grid` / `getTreeGrid`) 실제 출현 횟수 집계, 불일치 시 `⚠` 경고 표기
- analysis ui: TOBE `<SingleGrid|MultiGrid|CellEditGrid|ModalEditGrid>` 컴포넌트 출현 횟수 카운트 시 주석(/* ... */, // ...) 제외
- analysis grid: 다중 그리드를 메서드 단위(`GridBuilder` 선언 기준)로 독립 분리하여 제목별(`buildGrid()`) 복수 표 출력 및 `--method` 필터링 지원, `-o json` 그리드 배열 반환
- compare: `--grid <Class>[#<method>]` 옵션 지원, 메서드 미지정 시 API 필드와 최대 일치 그리드 자동 선택, 비존재 그리드 fallback 방지 및 경고 출력, 결과 요약에 대조 그리드명 및 컬럼 수 표기
- sql-check: `--old <구 AS-IS 소스경로>` 옵션 추가로 신/구 AS-IS 소스 간 statement 단위 SQL Drift(변경점) 감지, `--only-tobe` 필터링 및 TOBE 매퍼 영향 분석 리포트 제공
- log: 배포(`deploy`) 실행 직후 컨테이너가 아직 기동되지 않은 상태에서 `log errors --since-deploy` 등 호출 시 미기동 경고 표기

## [0.3.1] - 2026-10-13
수정사항 026 (연결 컴포넌트 화면 분석 및 UI 대조 포함, `api --log`·`log trace` SQL 파라미터 이름 매핑) 반영.
- analysis screen: `screens/` 외에 `components/` 디렉터리 파일 직접 조회 지원 (`analysis screen <컴포넌트명>`)
- analysis screen: `--list`에 화면의 "연결 화면·컴포넌트" 링크 및 `조회창 X 열기` 대상을 파악하여 연결 컴포넌트 행 추가 (`(연결)` 및 타 도메인 의존 시 `(연결·다른 도메인)` 표기)
- analysis screen: 같은 도메인 연결 컴포넌트는 기본적으로 합계에 포함, 타 도메인은 합계 제외, `--no-linked` 옵션 지정 시 연결 컴포넌트 목록 및 합계 제외 지원
- analysis screen: `--class <연결컴포넌트>` 및 `--section` (buttons, events, grid, layout 등) 연결 컴포넌트 내용 기반 동작 보강
- analysis ui: TOBE 대조표에 같은 도메인 연결 컴포넌트 행 자동 포함 및 대조 지원
- log reader: TOBE 매퍼 XML 파싱 기반으로 SQL `==> Parameters:` 값에 대응하는 `#{...}` 파라미터 이름 매핑 (`이름=값` 표기)
- log reader: `<foreach>` 동적 파라미터 및 개수 불일치/매퍼 부재 시 기존 값 형식으로 조용히 fallback
- agent-guide & CLI: screen 및 ui 분석 명령어 설명에 연결 컴포넌트 포함 안내 갱신

## [0.2.9] - 2026-10-13
수정사항 025 (analysis run에 --stderr 추가 및 실패 요약 STDERR 안내) 반영.
- analysis run: `--stderr` 옵션 추가 (STDERR 절 단독 추출, `-n` 줄 수 제한, 비어 있을 시 `(STDERR 없음)` 처리)
- analysis run: `--stdout`과 `--stderr` 동시 지정 시 STDOUT, 빈 줄, STDERR 순서로 둘 다 출력
- run: 실패 요약(Exit ≠ 0)에 STDERR 첫 줄 및 `→ yunhee analysis run last --stderr` 안내 표기
- agent-guide & CLI: `analysis run last --stderr` 안내 및 `--list` 설명 추가

## [0.2.8] - 2026-10-12
수정사항 024 (`log --since-run` 시작 시각 보정) 반영.
- run & save_run: `created_at`에 명령어 시작 시각(UTC ISO)을 저장하여 `yunhee runs`의 Created At 및 기록이 실제 시작 시각으로 일치
- run_tracker: `get_last_run`, `list_runs` 정렬 기준을 `ORDER BY created_at DESC, id DESC`로 보강
- log --since-run: `find_run_time`이 `RunTimeInfo(run_id, cmd, start_dt, end_dt)`를 반환하고, 끝 시각(`start_dt + duration_ms`) 및 옛 기록(끝 시각 저장분)의 run ID 타임스탬프(`yyyyMMdd_HHmmss` UTC) 자동 보정 지원
- log --since-run: 머리 줄 태그를 `· run <id> (<명령>) HH:MM:SS~HH:MM:SS KST 이후` 형식으로 표기하고 `--to` 미지정 시 끝 시각을 열어두어 실행 중 및 실행 후 발생 로그 정상 수집

## [0.2.7] - 2026-10-12
수정사항 023 (`yunhee log --archived` 마무리) 반영.
- log req & errors & tail: `--archived` 지정 시 시간 범위(UTC 변환 기준)에 해당하는 날짜의 압축 로그(archived/yyyy-MM/*.gz) 및 분할 파일(.0, .1) 정밀 조회 및 오늘 날짜 포함 시 오늘 파일 병합
- log req & errors & tail: 범위 미지정 시 `--archived` 안내 (`(--archived: 범위가 오늘이라 지난 파일을 읽지 않음)`) 표시 및 불필요한 지난 파일 조회 생략
- log req & errors & tail: `--archived` 없이 오늘 이전 시각 조회 시 안내 (`오늘 파일은 HH:MM부터 — 그 전은 --archived`) 표시
- log trace & req & tail: 오늘(로그 시간대)이 아닌 레코드 시각에 날짜 표기 (`YYYY-MM-DD HH:MM:SS UTC (MM-DD HH:MM:SS KST)` 및 `MM-DD HH:MM:SS`)
- log trace: `--archived`로 찾았을 때 원문 실행 안내에 `--archived` 추가 (`원문: yunhee log trace <id> --raw --archived`)
- log trace: `--archived`로도 못 찾았을 때 안내 문구 개선 (`trace <id>: 로그에 없음 (오늘 파일 + archived gz N개 검색)`)

## [0.2.6] - 2026-10-12
수정사항 022 (`yunhee log` 결함 해결 및 사용성 개선) 반영.
- log errors & tail: 첫 줄이 빈 WARN/ERROR(Spring Boot 기동 로그 등) 파싱 시 IndexError 방지 및 비어 있지 않은 첫 줄/본문 탐색
- log 마스킹: Spring Security 자동 생성 비밀번호(`Using generated security password: <UUID>`)를 `****`로 자동 마스킹
- log trace & errors & tail: info 및 error 로그 파일 간 동일 WARN/ERROR 중복 기록 de-duplicate 및 `--raw` 시각순 정렬 출력
- log tail: `--level` 필터 동작(해당 레벨 이상 포함 trace/standalone 필터링), `--grep` 시 trace 단위 전체 보존 및 SQL 개수 보존
- log tail: 요청 줄 끝에 해당 trace의 `⚠WARN`/`⚠ERROR` 및 첫 에러 메시지 요약 표시
- log tail: 비-HTTP 요청 및 WebSocket(`/ws`, 101) 노이즈 기본 숨김 및 요약 줄 표시, `--all` 옵션 지원
- log trace: 16진수 trace ID(8~32자) 유효성 검사(위반 시 Exit 2), `--archived` 옵션 지원 및 안내 문구 정합

## [0.2.5] - 2026-10-12
수정사항 021 (정적 분석 고도화, 테스트 실패 메시지 추출, 서버 로그 분석 명령 신설) 반영.
- analysis ui: TOBE E-id 범위([E5]~[E9]), 중복 E-id 카운트 배제, 생략 표기([E1 생략], [E1]~[E3 생략]) 감지 및 10/7 (생략 3) 형식 집계
- analysis sql: CTE(WITH ...) 추출 및 중복/테이블 목록 제외, DML 변경 대상(UPDATE/INSERT/DELETE) 명시 및 -o code 안내
- analysis method: 클라이언트 콜백 블록(callback: 접두어), editDriver.flush/edit, result.getResult, 스토어 갱신, 분기문(if/else if/else) 및 값 대입 추출 보강
- analysis method --server: 결과 설정(result.setResult/setRetrieveResult) 및 위임 없는 메서드에 '⚠ 결과 없음' 경고 추가
- events: 연속되지 않은 반복 호출(update(), autodecCtzNo(), update()) 순서 보존
- analysis screen: 정적 폼 레이아웃 파서 `--section layout` 신설 (라벨 폭, 행 구조, 위젯 크기/마진, readOnly/disabled 속성 추출)
- run: JUnit XML 파싱 기반 테스트 실패 메시지(message:, at:) 추출 및 Qwen 요약 생략으로 속도 개선
- log & api: 서버 로그 분석 명령(`yunhee log trace|req|errors|tail`) 신설, Docker(t3600-tomcat) 직접 조회, 시간대(UTC/KST) 변환, 민감정보(주민등록번호/JWT/패스워드) 마스킹, api 호출 시 `trace={id}` 태그 및 `--log` 옵션 지원

## [0.2.4] - 2026-10-08
수정사항 020 (019 시험 결과 보강 및 색인 성능 최적화) 반영.
- analysis tobe: JSX 렌더 트리 전용 토크나이저 도입 (자체 닫힘 태그, 중첩 화살표 함수/제네릭, Fragment 완전 지원 및 형제 요소 들여쓰기 밀림 해결)
- analysis grid: 정적 숨김(빌더 `setHidden(true)`, `setRowNumHidden`)만 `숨김` 열에 표시하고 조건부 숨김은 동적 호출 목록으로 분리, `addBoolean`·`addBooleanHtml` 체크박스 렌더러 지원
- analysis method: `addParam` 값식 괄호 밸런싱으로 닫는 괄호 잘림 해결, `addChange` 속성 및 값(`prop ← value`) 완전 추출, 클래스 필드 `mapperName` 상수 연결 SQL ID 자동 해석
- index-src & events: 매퍼 XML 목록, Properties 파일 맵, DBML 테이블 인메모리 사전 캐싱으로 반복 파일 I/O 제거 및 색인 속도 대폭 개선

## [0.2.3] - 2026-10-08
수정사항 019 (018 시험 결과 및 검증 스크립트 정합성 해결) 반영.
- analysis method: 메서드 시작 줄 계산 정밀화(실제 선언/어노테이션 기준), E-id caller 기본 표시, UpdateDataModel·연결 SQL ID·addParam 키-값식 요약 보강
- analysis grid: ColumnModel 복합 인자 및 탭/공백 정렬 파싱 완벽 지원, setHidden 상위 조건 및 컬럼 매핑, CellEditGrid/SingleGrid 정확한 판정
- analysis screen: 대상 지정 시 `--list`의 화면 클래스 목록(`list_classes`) 위임, `--section services` 한글 제목 대응 및 `--class` 결합 필터링, 그리드 중복 카운트 제거
- analysis ui: TOBE TSX 내 인라인 및 JSX 주석 이벤트 집계 보강, AS-IS 그리드 수 중복 카운트 제거
- analysis tobe: TSX 렌더 트리 중첩 컴포넌트 전체 계층 반영, useGridCrud 제네릭 인터페이스 필드 및 훅 반환값 추출, Java 메서드 본문 throw 조기종료 방지 및 전체 호출 순서 추적
- analysis & index-src: MyBatis resultMap association 및 Model @Path 매핑 기반 연관 테이블 컬럼 추적으로 Grid Spec ⚠DB없음 오탐 완전 해결
- compare: 서비스 호출 역추적 기반 화면 하위 페이지 그리드 컬럼 정밀 대조
- runs: 최상위 프로젝트 루트(`CLAUDE.md`, `.yunhee/project.json`) 우선 판정으로 하위 디렉터리 실행 집계 누락 방지, CWD 컬럼 줄임표 방지
- cli: 무거운 모듈(chromadb, prompt_toolkit) 지연 임포트(lazy import)로 CLI 시작 및 실행 속도 단축 (1초 이내)

## [0.2.2] - 2026-10-08
수정사항 018 (분석 명령 하나로 묶기 및 MyBatis 펼치기 통합) 반영.
- analysis: 단일 분석 명령 `yunhee analysis <type> <대상>` 및 8개 분석 서브모듈(method, sql, model, grid, screen, ui, tobe, run) 신설
  - method: AS-IS 메서드 본문/호출 흐름 요약 (`-o md|code`, 오버로드 모호성 시 번호 후보 제시 및 Exit 2)
  - sql: MyBatis 매퍼 statement 분석 및 실행 가능 SQL 펼치기 (`-o md|sql|code`, `--count` 즉시 행수 조회)
  - model: 모델 속성 → @Path → resultMap column → SQL 컬럼 매핑 분석 (`-o md|json`, `--sql` 정합성 검증)
  - grid: 그리드 한 개의 정확한 모양, ColumnModel 실제 순서, 특수 렌더러, GridType(SingleGrid/MultiGrid/CellEditGrid) 판정
  - screen: 색인 화면 파일에서 필요한 클래스 및 절(`--section`, `--class`) 필터링
  - ui: UI 대조표 및 단계별(`--done`, `--later`) 버튼/이벤트/그리드 현황 집계
  - tobe: TOBE 소스 파일(TSX 화면/부품, Java 서비스) 패턴 골격 요약
  - run: 실행 결과에서 필요한 값(`--stdout`, `--json [--keys]`, `--tests`) 추출 및 분석
  - `--list`: 지원하는 모든 분석 유형과 설명, 입출력 포맷 표 출력
- mybatis-render: MyBatis SQL 펼치기 통합 렌더러(`mybatis_render.py`) 구축
  - 다른 namespace의 `<include>` 및 cross-namespace include 완전 전개 (port-sql, compare 버그 수정)
  - `<bind>` 변수 매핑 및 OGNL 문자열 연결(`'%' + x + '%'`) 지원
  - boolean 리터럴(`== true/false`), `size()`, `and/or` 복합 test 식 지원
- port-save: 회사 컬럼 없는 테이블 자동 검증 및 누락 처리, `--company-via` 서브쿼리 옵션 지원 (C-1)
- compare: SQL 호출 서비스 역추적 기반 그리드 자동 선택, `--grid` 옵션 및 별칭 정규화 매칭 지원 (C-2)
- run: gradle/mvn 테스트 결과(`tests N (fail X, skip Y)`) 자동 요약 및 실패 케이스 최상단 우선 표시 (C-3)
- runs: 상위 디렉터리 프로젝트 루트 자동 탐색(`find_project_root`), 실행 폴더(cwd) 기록 및 표 컬럼 추가 (C-4)
- outline: 여러 파일/디렉터리 경로 동시 인자 지원 (C-5)
- index-src: 기계용 색인 파일(`_index.json`) 자동 생성 및 `clean_generated` 정리 지원 (A-9)

## [0.2.1] - 2026-10-07
수정사항 016 (0.1.9 시험 결과) 반영.
- sql: **기본 모드가 실제로 읽기 전용이 됨** — 첫 문장 전에 `conn.read_only`로 `BEGIN READ ONLY`를 건다 (이전엔 `SET default_transaction_read_only`가 열린 트랜잭션에 적용되지 않아 UPDATE+COMMIT이 저장됐음)
- sql: 안전 가드를 두 모드 모두에 적용 — COMMIT/END/PREPARE/DDL 거부. 기본 모드는 INSERT/UPDATE/DELETE/MERGE/CALL/DO, `WITH … DELETE` 등 쓰기와 BEGIN/START, 읽기 전용을 끄는 SET을 실행 전에 거부("읽기 전용 모드입니다. 쓰기 시험은 --rollback"). 가드는 문장 첫 키워드 기준이라 `CASE … END`·문자열 안 `commit`은 통과
- sql: `--rollback`에서 `CALL` 대상 프로시저 본문(`pg_proc.prosrc`)에 COMMIT/ROLLBACK이 있으면 실행 전 거부
- port-save: 부수 효과 SQL id를 `{매퍼}{원본 id}` camelCase로 유일하게(`ics30ComplianceInsertFormIcs30`), 중복 시 숫자+경고. 태그는 본문 첫 키워드로(`<select>` 안 INSERT → `<insert>`, CALL → `<update>`)
- port-save: `UpdateDataModel`의 `map.put` 리터럴(`useYn="true"`, `itemTypeCodeName="PayFormulaCode"` 등)과 map에 없는 키(NULL)를 SQL에 넣고 주석으로 표시, 남은 `${값}`은 `#{값}`으로. 끝에 Mapper 인터페이스 메서드 목록 출력
- sql-check `--tobe`: record DTO를 resultType FQN 경로로 정확히 찾음(짧은 이름이 여러 개면 경고 후 대조 생략). 별칭 대조는 최상위 SELECT 목록만(AS 없는 컬럼 포함, 서브쿼리·CTE 별칭 제외)
- api·compare: 기본 테넌트 선택 순서 통일 (`-t` → `.yunhee.toml [api] tenant` → `YUNHEE_API_DEFAULT_TENANT`(신설) → `YUNHEE_TEST_COMPANY`), `-c`인데 테넌트가 없으면 둘 다 Exit 1. compare도 머리 태그 출력
- index-src: 서버 안 `sqlSession.selectOne("getSeq")`도 `dbConfig.getSeq`(→ `f_create_seq()`)로 해석, "저장 시 부수 효과"의 테이블을 DB 색인 링크로, `--db-index`가 출력 폴더에서 멀면(../ 6단계 초과) 절대 경로 링크
- port-sql: `--cols` 순서 유지, select id 영어 복수형(`searchCompanies`), `--package` 옵션(없으면 `{dto.package}.XxxRes` 자리표시+주석)
- events: Grid Spec 계산 컬럼 주석이 그 화면이 실제로 부르는 조회 서비스의 SQL(`selectById` 등) 별칭을 먼저 봄

## [0.1.9] - 2026-10-07
- index-src: `UpdateDataModel` 호출 및 동적 INSERT/UPDATE/DELETE 추적, `UpdateDataModel.java` 파싱 기반 `## 저장 시 부수 효과 (UpdateDataModel)` 절 자동 생성
- events & index-src: Grid Spec에서 MyBatis 매퍼 SELECT 별칭(alias_cols)을 조회하여 SQL 계산 컬럼을 `// L### SQL 계산 컬럼(...)`으로 식별하도록 개선 (`⚠DB없음` 오탐 제거)
- index-src: `getSeq` 서비스 호출을 `(공통) 채번` / `dbConfig.getSeq`(→ `f_create_seq()`)로 명시
- api: 작업 디렉터리 상위 탐색 기반 `.yunhee.toml` (`[api] base, tenant`) 우선 설정 지원, `-c/--company` 지정 시 테넌트 자동 주입 및 회사/테넌트별 세션 파일 완전 격리, 헤더 태그(`[AssetERP_1 · tenant=admin · company=kfstest]`) 출력
- sql: PostgreSQL 대상 읽기 전용 쿼리 실행 및 `--rollback` 모드 지원 (COMMIT/END/DDL 차단 안전 가드, `\gset` 및 `:var` 변수 치환 지원)
- sql-check: `--tobe <mapper dir>` 옵션 추가 — TOBE MyBatis XML 매퍼를 asseterpdb에서 컴파일/배포 전 `EXPLAIN` 사전 정합성 검증 (`CALL` 프로시저 `pg_proc` 검사, Record DTO 필드 매핑 검증)
- port-sql: AS-IS MyBatis SQL을 TOBE 매퍼 조각(`<sql id="...Columns">` 및 `<select>`)과 Java Record DTO로 자동 변환 (`--cols` 필터, `--getter-defaults` 기반 `COALESCE` 생성)
- port-save: AS-IS `UpdateDataModel` 대체용 명시적 `insert...`, `update...`, `delete...`, `selectNextId` 및 부수 효과 SQL 일괄 생성
- compare: HTTP 조회 API와 AS-IS SQL의 결과 행 수 및 그리드 컬럼 커버리지 일치 여부를 즉시 비교 검증 (`API rows=X, SQL rows=Y ✅ fields ⊇ grid cols ✅`)

## [0.1.8] - 2026-10-06
- index-src: 화면·컴포넌트 파일의 `## UI` 절에 클래스별 `yunhee events` 결과(`#### 이벤트`·`#### 메서드`·`#### Grid Spec`·`#### 사용된 버튼들`)를 함께 생성 — 화면마다 `events`를 따로 돌리지 않아도 됨
- index-src: `--events/--no-events`(기본 켜짐), `--button-types/-b` 옵션 추가. events를 켜면 기존 UI 요약의 `- 이벤트:`·`- 메서드:` 줄은 중복이라 생략

## [0.1.7] - 2026-10-02
- events: 버튼 타입 매핑을 외부 TSV 파일로 분리 관리하도록 개선 (`data/button-types.tsv`, `docs/as-is/button-types.tsv`, `docs/button-types.tsv` 우선순위 자동 탐색)
- events: `--button-types / -b <경로>` 옵션 추가로 사용자 정의 버튼 매핑 TSV 명시적 지정 지원
- events: 표에 없는 미정의 버튼(`type="unknown"`) 발견 시 `docs/as-is/button-types.tsv` 등록 안내 힌트(stderr) 출력

## [0.1.6] - 2026-10-02
- events: AS-IS GXT 화면 소스에서 위젯/화면 이벤트를 결정적으로 정밀 추출하는 `yunhee events <target>` 명령어 추가 (`--ids`, `--json`, 클래스명/경로 자동 탐색, 인라인 로직 및 암묵적 이벤트 포착)
- events: 모든 메서드(public/private/protected)의 호출처, 동작, 줄 범위, 업무/UI구성/유틸 구분 상세 분석 테이블 추가
- events: **## Grid Spec** 섹션 추가 — AS-IS `buildGrid()`로부터 TOBE React 스타일 `const buildGrid = () => [ gb.xxx(...) ];` 코드 자동 생성 (MyBatis 매퍼 resultMap 기반 DTO 프로퍼티명 변환, DB 컬럼 부재 `// ⚠DB없음 L###` 감지, 그리드 미사용 시 `Grid 사용하지 않음` 출력)
- events: **## 사용된 버튼들** 섹션 추가 — 화면에 사용된 버튼들을 TOBE React 규격인 `1. <Button type="{type}" onClick={handler}>{label}</Button>` 번호 매김 목록으로 출력 (AS-IS 306개 버튼 레이블 매핑 사전 내장, 미정의 레이블 `type="unknown"` 처리, 버튼 미사용 시 `버튼 사용하지 않음` 출력)

## [0.1.5] - 2026-10-02
- index-db: 대용량 DBML 마크다운을 도메인/함수별 소형 파일로 분할 색인 (`--target/-t` 옵션, 스마트 기본값, pgcrypto 암호키 마스킹)
- index-src: AS-IS GXT 소스 호출 체인(화면 → 서비스 → SQL → 테이블) 및 UI/이벤트/줄 번호 색인 빌드 (`--target/-t`, `--menus`, `--db-index` 지원)
- sql-check: MyBatis 매퍼의 동적 SQL을 전개해 대상 DB(asseterpdb)에서 `psql EXPLAIN`으로 정합성(스키마/환경 차이 및 영향 화면) 검증 (`--db`, `--target/-t`, `--src-index` 지원)

## [0.1.4] - 2026-10-02
- outline(Java): `@PostMapping(value = ...)`처럼 `=`가 든 애너테이션이 붙은 메서드가 빠지던 문제 수정
- outline(Java): `log.info(...)`, `when(...).thenReturn(...)`, `validate(req);` 같은 본문 문장이 메서드로 새던 문제 수정
- outline(Java/TS): 한글 등 유니코드 식별자 지원 (`void 권한그룹_메뉴는_...()` 테스트 메서드)
- outline(Java): `@Deprecated OLD` 같은 애너테이션 붙은 enum 상수 이름 수정, `@RequestMapping({"/a","/b"})` 중괄호 인자 처리
- api: `--timeout <초>` 추가 (기본 `YUNHEE_API_TIMEOUT` 또는 15초), 시간 초과를 연결 실패와 다른 문구로 표시
- changelog: `yunhee changelog` 명령 추가, REPL이 버전 변경을 감지하면 이후 변경사항 표시

## [0.1.3] - 2026-10-01
- outline(Java): 여러 줄 파라미터, `List<MenuRes.Level1>` 같은 점 포함 제네릭 반환형, 인터페이스 메서드, enum 상수 요약, record 구성요소 지원
- outline(TS/TSX): `export const xxxApi = { ... }` 객체 리터럴 함수, React.FC 컴포넌트, 제네릭 함수 지원
- api: `--tenant`(Host 헤더 기반 테넌트 분리, 테넌트별 세션 파일), `--company`(companyCode) 추가
- api: 공통 응답 봉투(success·code·data) 언래핑, 로그인 실패 시 즉시 중단(계정 잠금 방지)
- config: API 관련 설정 표시

## [0.1.1] - 2026-10-01
- outline: Java/MyBatis XML/TS 클래스·메서드 시그니처와 줄 번호 추출 (LLM 없음)
- api: 테스트 계정 자동 로그인 기반 API 스모크 테스트 (행수/필드 요약)
- config: 현재 Source/Target 디렉터리, DB 설정 표시
- run: 성공 시 정확히 1줄 출력
- prepare/prep 명령 제거

## [0.1.0] - 2026-10-01
- REPL(`/help`, `/clear`, `/config`, `/init`), ask/vec/index/search
- prepare/prep: ASIS 페이지 요약 + 연관 테이블 DBML
- make-dbml/dbml: PostgreSQL 스키마 → DBML 마크다운 + JSON 스냅샷
- table: 스냅샷에서 테이블 단위 DBML 추출 (`--page` 지원)
- run/exec, last-run, runs: 외부 명령 실행과 Qwen 에러 요약, 실행 이력
- agent-guide: 상용 AI 에이전트용 토큰 절약 지침서
- Ollama `num_ctx` 명시 및 프롬프트 잘림 경고
