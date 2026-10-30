# Implementation Plan - 수정사항 045 (1번 & 2번)

AssetERP T13~T16 마이그레이션 세션에서 도출된 `docs/수정사항/수정사항045.md` 중 이미 완료된 3번(`page-style` 체계 개편)에 이어, 남은 핵심 과제인 **1번(`compare` API 서버 오류 500/4xx/업무예외 즉시 실패 처리)** 및 **2번(`compare`와 `analysis sql`의 MyBatis `/* if */` 분기 조건식 평가기 확장 및 미평가 분기 안전 가드)**을 구현합니다.

---

## Goal Description

1. **Item 1: `compare` 명령의 API 실패(HTTP 500, 4xx, `ApiResponse.success=false`) 즉시 실패 처리**
   - 현재 `compare`는 API 호출이 실패(HTTP 500, 400 등)하여 본문이 비어있거나 에러 JSON인 경우 `rows=0`으로 잘못 간주하여, AS-IS SQL 결과도 0행인 경우 `rows=0 ✅`로 판정하거나 단순 행수 불일치로 오도함.
   - API 응답이 4xx/5xx이거나 공통 응답 봉투에서 `success=false`인 경우 행 수 비교를 즉시 중단하고 `❌ API 실패: HTTP 500 INTERNAL_ERROR (추적ID: ...) — yunhee log trace ... --raw` 형태로 명확히 출력하고 종료 코드 1로 실패 처리.
   - 업무 예외(4xx, `INVALID_INPUT` 등)는 `API 업무 오류: <message>`로 구분하여 출력.
   - 가능한 경우 해당 trace의 서버 에러/경고 로그 1~2줄을 함께 표시.

2. **Item 2: MyBatis 분기 조건식(`<if test="...">`, `<when test="...">`) 평가기 확장 및 미평가 분기 안전 가드**
   - 현재 `car03_booking.selectByDate`의 `<when test="type.equals('my') ">`와 같은 문자열 메서드 호출이 미평가되어 `/* if ... */` 블록이 원문 SQL로 실행(항상 켜짐)됨. `--param type=all`이어도 `car03_person_id` 필터가 적용되어 행수가 어긋남.
   - OGNL/MyBatis 조건식 파서(`eval_test_condition_status`, `_eval_single_condition_status`)를 확장:
     - `x.equals('lit')`, `'lit'.equals(x)`, `!x.equals('lit')`, `x.equalsIgnoreCase('lit')`
     - 컬렉션 프로퍼티 형태의 `.size` (`fundIdList.size != 0`, `.size()`와 둘 다 지원)
     - Long/숫자 리터럴 접미사 `0l`, `0L` 지원 (`personId != 0l`)
     - `&&` 및 `||` 연산자 분리 지원
     - `x.isEmpty()`, `!x.isEmpty()`, `x.length() > 0`
     - 실제 AS-IS 레거시 전체 526개 매퍼 XML의 307개 조건식 중 미평가되던 16개(100%)를 전부 정상 평가하도록 확장 (전체 커버리지 100% 달성).
   - **미평가 분기 안전 가드**: 향후 평가할 수 없는 미지의 식이 발생할 경우, SQL 본문을 임의로 켜서 실행하지 않고 안전하게 주석(`/* ⚠ 분기 평가 불가(기본 OFF): ... */`) 처리하여 실행 차단.
   - stderr 경고 출력 및 대조 결과에 `(분기 N개 평가 불가)` 표기.
   - `--branch '<식|변수>'=on|off` 옵션을 신설하여 사용자가 임의 분기를 강제할 수 있도록 지원.

---

## User Review Required

> [!IMPORTANT]
> - `compare`에서 API 서버 오류(HTTP 500/400) 또는 `success=false` 발생 시 기존의 `API rows=0 ...` 대조를 건너뛰고 **종료 코드 1과 함께 즉시 중단**됩니다. 이는 CI/스크립트나 `yunhee run`에서 깨진 API를 즉시 감지할 수 있게 하기 위함입니다.
> - 평가할 수 없는 분기 조건식의 기본 동작이 종전의 "SQL 본문 실행(항상 켜짐)"에서 **"SQL 본문 실행 차단(기본 OFF, 주석 처리)"**으로 변경됩니다. 필요한 경우 `--branch '<식>'=on`으로 강제할 수 있습니다.

---

## Proposed Changes

### Component 1: `src/yunhee/tools/as_is/mybatis_render.py`
MyBatis 조건식 평가기 확장 및 미평가 분기 안전 가드, `--branch` 강제 옵션 지원

#### [MODIFY] `src/yunhee/tools/as_is/mybatis_render.py`
- `_eval_single_condition_status(expr, params)` 확장:
  - 문자열 `.equals()` 및 `!....equals()` (`x.equals('lit')`, `'lit'.equals(x)`, `!x.equals('lit')`, `!'lit'.equals(x)`)
  - 대소문자 무시 `.equalsIgnoreCase(...)`
  - `.size` 프로퍼티 (`r"^(\w+)\.size(?:\(\))?\s*([><!=]=?)\s*(\d+)$"`)
  - Long 리터럴 접미사 `0L`, `0l` (`r"^(\w+)\s*([><!=]=?)\s*(-?\d+(?:\.\d+)?)[lL]?$"`)
  - `x.isEmpty()`, `!x.isEmpty()`, `x.length() > 0`
- `eval_test_condition_status(test, params, branch_overrides=None)` 확장:
  - `or_parts = re.split(r"\b(?:or|OR)\b|\|\|", test)`
  - `and_parts = re.split(r"\b(?:and|AND)\b|&&", or_part)`
  - `branch_overrides` 사전 검사: test 식 또는 var_name이 `branch_overrides`에 있으면 사용자 지정 boolean 반환
- `render_node` 수정:
  - `<if>` 및 `<choose>`에서 `eval_res is None`인 경우:
    - 본문을 실행 가능한 SQL로 두지 않고 `/* ⚠ 분기 평가 불가(기본 OFF): {test}\n{body}\n*/`로 주석 처리
    - `sys.stderr.write(f"⚠ 분기 평가 불가: {test} — 양쪽(켬/끔) 모두 보려면 --branch '{test}'=on|off\n")`
    - `branch_log`에 `f"⚠ {test} 평가 불가"` 기록
- `render_with_meta`, `render`, `render_from_xml_with_meta`에 `branch_overrides: dict[str, bool] | None = None` 인자 추가

```python
# _eval_single_condition_status 예시
m_equals = re.match(r"^(!?)\s*(\w+)\.equals\(\s*['\"]([^'\"]*)['\"]\s*\)$", expr)
if m_equals:
    neg, var, lit = m_equals.group(1), m_equals.group(2), m_equals.group(3)
    val = str(params.get(var, "")) if var in params else ""
    return (val != lit) if neg else (val == lit)
```

---

### Component 2: `src/yunhee/tools/comparator.py`
API 호출 실패 감지, 업무 예외 구분, 서버 로그 요약 부착, 미평가 분기 수 결과 요약 표기

#### [MODIFY] `src/yunhee/tools/comparator.py`
- `compare_api_sql`:
  - `api_res = request_api(...)` 호출 직후 `api_res.ok` 및 JSON 봉투의 `success` 검사
  - HTTP 4xx, 5xx 또는 `ApiResponse.success=false`인 경우 즉시 실패 판정:
    - 4xx 또는 `INVALID_INPUT` / `success=false`: `❌ API 업무 오류: HTTP {code} {message} (추적ID: ...) — yunhee log trace ... --raw`
    - 5xx 또는 기타 에러: `❌ API 실패: HTTP {code} {message} (추적ID: ...) — yunhee log trace ... --raw`
    - trace_id가 있는 경우 `get_trace_summary`를 통해 서버 에러 로그 1~2줄 추출 부착
    - `ToolResult(ok=False, data=api_res.data, error=err_str)` 즉시 반환
  - `branch_log`에서 `평가 불가` 항목을 카운트하여 결과 요약 줄에 `(분기 N개 평가 불가)` 표기
  - `branch_overrides` 인자 수용 및 `render_with_meta`로 전달

---

### Component 3: `src/yunhee/tools/analysis/sql.py` & `src/yunhee/cli.py`
CLI 옵션 `--branch` 추가 및 에러 출력 서식 정리

#### [MODIFY] `src/yunhee/tools/analysis/sql.py`
- `resolve` 및 `render`에서 `--branch` 옵션 파싱 및 `branch_overrides`를 `mr_render`로 전달

#### [MODIFY] `src/yunhee/cli.py`
- `compare_cmd`:
  - `--branch` 옵션 추가 (`--branch "<식>=on|off"` 반복 가능)
  - `not res.ok` 시 에러 메시지가 `❌`로 시작하는 경우 `[ERROR]` 중복 접두사 없이 출력하고 `typer.Exit(code=1)`
- `analysis_cmd`:
  - `--branch` 옵션 추가

---

### Component 4: 테스트 및 문서

#### [NEW] `tests/test_fix045.py`
- 1번 API 오류 즉시 실패 검증:
  - HTTP 500 발생 시 `rows=0 ✅`가 아니라 `❌ API 실패: HTTP 500 ...` 및 `ok=False` 반환
  - HTTP 400 및 `ApiResponse.success=false` 시 `❌ API 업무 오류: ...` 반환
  - trace ID 안내 문구 및 서버 에러 요약 포함 확인
- 2번 조건식 평가기 및 분기 가드 검증:
  - `car03_booking.selectByDate` 조건 `type.equals('my')`:
    - `--param type=all` -> 조건 OFF, `car03_person_id` 제외
    - `--param type=my` -> 조건 ON, `car03_person_id` 포함
  - 확장 조건식 검증:
    - `checkBox.equals('true')`, `'lit'.equals(x)`, `!x.equals('lit')`
    - `fundIdList.size != 0` (프로퍼티 접근)
    - `personId != 0l`, `orgCodeId != 0L` (Long 리터럴)
    - `&&`, `||` 복합 조건
  - 미평가 조건식 안전 가드 검증:
    - 알 수 없는 식 `unknownFunc(x)` -> 기본 OFF (주석 처리되어 SQL 미실행), stderr 경고
    - `compare` 요약에 `(분기 1개 평가 불가)` 표기
    - `--branch "unknownFunc(x)=on"` 지정 시 강제 ON 적용
- 회귀 검증:
  - 044의 `endCheck != true`, `infoId != null` 정상 동작 확인

#### [MODIFY] `docs/help/ops-and-log.md`
- `compare` 및 `analysis sql`에 `--branch` 옵션 설명 추가 및 API 실패 시 즉시 에러 안내 추가

#### [MODIFY] `src/yunhee/CHANGELOG.md` & `pyproject.toml`
- 버전 0.7.0 업데이트 및 변경 내역 작성

---

## Verification Plan

### Automated Tests
1. 전체 단위 테스트 실행:
   ```bash
   uv run pytest
   ```
2. 신규 `test_fix045.py` 단독 실행:
   ```bash
   uv run pytest tests/test_fix045.py -v
   ```
3. 기존 `test_comparator.py` 및 `test_fix044.py` 회귀 검증:
   ```bash
   uv run pytest tests/test_comparator.py tests/test_fix044.py -v
   ```
4. 린트 검사:
   ```bash
   uv run ruff check .
   ```

### Manual Verification
1. `car03_booking.selectByDate` SQL 펼치기 검증:
   ```bash
   uv run yunhee analysis sql car03_booking.selectByDate -o sql --param companyId=28000 --param startDate=2026-05-29 --param type=all --param personId=1
   ```
   -> `car03_person_id` 조건이 없어야 함 (분기 OFF)
   ```bash
   uv run yunhee analysis sql car03_booking.selectByDate -o sql --param companyId=28000 --param startDate=2026-05-29 --param type=my --param personId=1
   ```
   -> `AND car03_person_id = 1` 조건이 포함되어야 함 (분기 ON)
2. 미평가 분기 강제 옵션 검증:
   ```bash
   uv run yunhee analysis sql car03_booking.selectByDate -o sql --param companyId=28000 --param startDate=2026-05-29 --branch "type.equals('my')=on" --param personId=1
   ```
   -> `--branch`로 강제 ON되어 `car03_person_id` 조건이 포함되어야 함
3. AS-IS 매퍼 전체 307개 조건식 평가 커버리지 검사:
   -> 미평가 조건식 0건 확인
4. ntfy 완료 알림 전송:
   ```bash
   curl -s -d "agy message: 수정사항045 1번 및 2번 구현 완료" ntfy.sh/asseterp-framework-gwtgxt-2-sbreact-2026
   ```
