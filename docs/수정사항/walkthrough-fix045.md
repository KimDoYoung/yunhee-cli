# Walkthrough - 수정사항 045 구현 및 v0.7.0 판올림

## 1. 개요
`docs/수정사항/수정사항045.md`의 핵심 과제인:
1. **`compare` API 서버 오류(HTTP 500/4xx/업무예외) 발생 시 즉시 실패 판정 및 원인/추적 로그 안내**
2. **MyBatis 분기 조건식(`<if>`, `<when>`) 평가기 확장 및 미평가 분기 안전 가드(`--branch` 지원)**
를 구현하고, 버전 `0.7.0`으로 판올림했습니다.

---

## 2. 주요 변경 사항

### 1) `src/yunhee/tools/comparator.py` & `src/yunhee/cli.py`
- **API 오류 즉시 실패 처리**:
  - `request_api` 응답이 HTTP 4xx/5xx이거나 응답 본문의 `success=false`인 경우, 더 이상 행 수 비교(`rows=0 ✅`)로 빠지지 않고 즉시 실패 처리합니다.
  - HTTP 500 또는 서버 장애: `❌ API 실패: HTTP 500 INTERNAL_ERROR (추적ID: ...) — yunhee log trace ... --raw`
  - HTTP 4xx 또는 업무 예외: `❌ API 업무 오류: HTTP 400 INVALID_INPUT ...`
  - trace ID가 존재할 경우 서버 로그 trace에서 에러/경고 요약 1~2줄을 추출하여 함께 표시합니다.
  - CLI 종료 코드를 `1`로 반환하여 스크립트 및 `yunhee run`에서 깨진 API를 즉시 포착합니다.
- **미평가 분기 안내**:
  - 조건식 평가 불가 분기가 존재할 경우 대조 결과 요약 줄에 `(분기 N개 평가 불가)`를 표시합니다.
- **`--branch` 옵션 추가**:
  - `yunhee compare`에서 `--branch "<식|변수>=on|off"`를 전달받아 SQL 분기를 명시적으로 강제할 수 있도록 지원합니다.

### 2) `src/yunhee/tools/as_is/mybatis_render.py`
- **MyBatis 분기 조건식 평가기 확장**:
  - `x.equals('lit')`, `'lit'.equals(x)`, `!x.equals('lit')`, `x.equalsIgnoreCase('lit')` 지원 (`car03_booking.selectByDate` 등 해결)
  - 컬렉션 프로퍼티 형태의 `.size` (`fundIdList.size != 0`, `.size()`와 둘 다 지원)
  - Long 리터럴 접미사 `0l`, `0L` 지원 (`personId != 0l`, `orgCodeId != 0L`)
  - `&&` 및 `||` 복합 논리 연산자 분리 및 `isEmpty()` 지원
  - **AS-IS 레거시 전체 526개 매퍼 XML의 307개 조건식 중 미평가 16건을 전수 해소 (미평가율 0% 달성)**.
- **미평가 분기 안전 가드**:
  - 평가할 수 없는 미지의 식이 발생할 경우 종전처럼 본문 SQL을 그대로 실행(항상 ON)하지 않고, 안전하게 주석(`/* ⚠ 분기 평가 불가(기본 OFF): ... */`) 처리하여 실행을 차단합니다.
  - stderr로 경고 및 `--branch '<식>'=on|off` 사용 안내를 출력합니다.
- **분기 강제 인자(`branch_overrides`) 전파**:
  - `render_node`, `render_with_meta`, `render`, `render_from_xml_with_meta`, `render_from_xml`에 `branch_overrides`를 전달할 수 있도록 확장했습니다.

### 3) `src/yunhee/tools/analysis/sql.py`
- `analysis sql`에 `--branch "<식>=on|off"` 옵션을 연결하여 분기 강제 제어가 가능하도록 지원합니다.

### 4) 문서 및 버전 업데이트
- [`docs/help/ops-and-log.md`](file:///home/kdy987/work/yunhee-cli/docs/help/ops-and-log.md): `compare` 명령어의 API 오류 즉시 실패 동작 및 `--branch` 옵션 가이드 추가
- [`docs/help/analysis.md`](file:///home/kdy987/work/yunhee-cli/docs/help/analysis.md): `analysis sql` 명령어의 분기 조건식 자동 평가 및 `--branch` 옵션 가이드 추가
- [`pyproject.toml`](file:///home/kdy987/work/yunhee-cli/pyproject.toml) & [`uv.lock`](file:///home/kdy987/work/yunhee-cli/uv.lock): 버전 `0.7.0`으로 판올림
- [`src/yunhee/CHANGELOG.md`](file:///home/kdy987/work/yunhee-cli/src/yunhee/CHANGELOG.md): 0.7.0 릴리즈 노트 작성

---

## 3. 검증 결과

- **신규 검증 테스트**: `tests/test_fix045.py` 11개 항목 통과 (HTTP 500 즉시 실패, HTTP 400 업무 오류, CLI 종료 코드 1, 문자열 equals 분기, .size/0L 리터럴, 복합 논리식, 미평가 주석 가드, `--branch` 강제 오버라이드, 평가 불가 분기 수 요약 표기)
- **회귀 테스트**: 전체 테스트 스위트 545개 통과 (`uv run pytest`)
- **린트 검사**: `uv run ruff check .` 통과
- **실제 SQL 검증**:
  - `car03_booking.selectByDate --param type=all` -> `car03_person_id` 조건 제외 (OFF 확인)
  - `car03_booking.selectByDate --param type=my` -> `AND car03_person_id = 1` 포함 (ON 확인)
  - `car03_booking.selectByDate --param type=all --branch "type.equals('my')=on"` -> 강제 ON 확인
  - AS-IS 레거시 전수 조사 결과: 미평가 조건식 0건 확인
