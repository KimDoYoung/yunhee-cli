# trace-* 업무분석용 명령어 설계

- 기준: yunhee **0.5.10** (명령어 18개는 껍질(stub)만 구현됨 — `src/yunhee/tools/trace/`)
- 상태: 설계 확정, 본 구현은 §7 순서대로 진행

---

## 1. 개요

### 1.1 목적

yunhee의 기존 명령은 **변환 작업의 대상**(화면, SQL, 파일)을 중심으로 동작한다(`analysis`, `sql`, `port-sql`, `compare` 등). `trace-*`는 그 앞 단계인 **업무파악 단계**를 위한 조회 계층이다. 화면·데이터·규칙 같은 **업무 개념을 따라가며** "이 업무가 어떻게 돌아가는가"를 묻는다.

- 모든 명령은 `trace-<이름>` 형태의 인자형 명령이다 (`trace-screen <화면ID> [옵션]`).
- 새 파서를 만들지 않는다. 이미 있는 색인 위에 얹는 **뷰**다: `index-src`(ASIS 소스 색인), `events`, `analysis`, `make-dbml` 스냅샷, `mapper_index`.
- **사실 추출은 결정적**이다. 정규식·파서·DB 카탈로그로만 만들고 LLM(Qwen)은 쓰지 않는다. 서술, 판정, 전이도 작성 같은 해석은 상용 에이전트(Claude 등)의 몫이다.
- 토큰 절약이 목적이므로 `--max`로 출력 상한을 강제한다(§3). 예산 관리는 tools 레이어에서 한다는 기존 원칙을 따른다.

### 1.2 이름 충돌 정리

기존 `log trace <traceId>`(서버 요청 추적)와 `trace-*`가 혼동될 수 있다. `log trace`의 별칭으로 `log request`(단축 `req`)를 추가했다(0.5.10). 기존 `log trace`는 그대로 동작한다.

---

## 2. 명령어 (5계층, 18개)

### 2.1 탐색 — 어디서부터 볼까

| 명령어 | 인자·고유 옵션 | 출력하는 사실 |
|---|---|---|
| `trace-map` | `--domain/-d <영역>` | 업무 영역별 화면 수, 테이블 수, ASIS↔TOBE 매핑 상태 요약 |
| `trace-menu` | `[<메뉴경로>]` | 메뉴 트리 → ASIS 화면 클래스 → TOBE 화면/API |
| `trace-screen` | `<화면>`(클래스명·접두사·메뉴 번호 `#1029`) `--class <하위클래스>` `--tobe <경로>` | 화면 팩트 시트: 필드·라벨, 그리드 컬럼, 버튼, 이벤트, 호출 RPC/API, SQL, 테이블, 사용 코드 그룹 |

### 2.2 데이터 중심 — 이 데이터는 누가 만들고 바꾸나

| 명령어 | 인자·고유 옵션 | 출력하는 사실 |
|---|---|---|
| `trace-table` | `<테이블>` `--stats` `--db <스냅샷>` | 컬럼·코멘트, 이 테이블을 C/R/U/D 하는 SQL과 화면, 같은 이름 컬럼을 가진 테이블, 행 수(최근 갱신일은 갱신 일시 컬럼 규칙 확정 후 추가) |
| `trace-column` | `<테이블.컬럼>` | 이 컬럼을 읽는/쓰는/WHERE에 쓰는 SQL, 표시되는 화면 라벨, 값 분포 |
| `trace-code` | `<코드그룹>` | 코드값과 명칭, 사용처(콤보, SQL 리터럴, Java/TS 상수 비교) |
| `trace-state` | `<테이블.컬럼>` | 이 컬럼에 값을 쓰는 모든 INSERT/UPDATE, 대입 값, 그 SQL의 WHERE 조건 |
| `trace-crud` | `--domain/-d`, `--screen/-s`, `--table/-t` | CRUD 매트릭스 |

`trace-state`는 업무 흐름 파악에 특히 효과가 크다. 전이도를 그리는 것은 에이전트 몫이지만, "어느 SQL이 어떤 조건에서 어떤 값을 쓰는가"는 순수한 사실이므로 yunhee가 뽑는다.

### 2.3 규칙 위치 — 조건이 걸린 곳은 어디인가

| 명령어 | 인자·고유 옵션 | 출력하는 사실 |
|---|---|---|
| `trace-flow` | `<화면ID> --event/-e <En>` | 이벤트 하나의 끝까지 이어진 사슬: 버튼 → 핸들러 → RPC/API → 서비스 → mapper → SQL → 테이블 |
| `trace-branch` | `<화면ID\|클래스\|mapper id>` | 조건 지점 전체 목록: if/switch/throw, validator, 버튼 활성 조건, `<if test>`, CASE WHEN, TSX disabled·조건부 렌더링 |
| `trace-dblogic` | `[<이름>]` | 함수·프로시저·트리거 본문과 이를 호출하는 SQL |

### 2.4 ASIS↔TOBE 대조 — 제대로 옮겨졌나

| 명령어 | 인자·고유 옵션 | 출력하는 사실 |
|---|---|---|
| `trace-pair` | `<화면ID>` | 짝지어진 항목과 매칭 근거(같은 mapper id, 같은 테이블 조합, 같은 이름) |
| `trace-diff` | `<화면ID\|mapper id>` `--sql` `--branch` `--ui` | SQL 정규화 diff, 분기 대응표, UI 필드 대응표 |
| `trace-gap` | `--domain/-d` | ASIS에만 있는 것, TOBE에만 있는 것, 추적하지 못한 지점 전체 |

### 2.5 카탈로그 — 에이전트의 판정을 저장

| 명령어 | 동작 |
|---|---|
| `trace-rule add\|list\|show\|update <대상> [--note <내용>]` | 규칙 저장·조회. 판정(일치/누락/변경/의도적 변경)과 사유를 기록 |
| `trace-rule verify` | 저장된 규칙의 근거 위치(파일:라인, mapper id)가 실제로 존재하고 내용이 바뀌지 않았는지 확인 |
| `trace-term [<단어>]` | 용어 교차 참조: 화면 라벨 ↔ 컬럼 ↔ 코드명 |
| `trace-doc <영역>` | 카탈로그와 팩트를 신규 인원용 문서 골격으로 조립 (서술은 에이전트) |
| `trace-guide` | 에이전트용 업무파악 워크플로우 지침 (`agent-guide`의 업무파악판) |

---

## 3. 공통 옵션

| 옵션 | 값 | 기본 | 설명 |
|---|---|---|---|
| `--side` | `asis`, `tobe`, `both` | `both` | 분석 대상 쪽 |
| `--format`, `-o` | `md`, `json` | `md` | 출력 형식 |
| `--max` | N | 없음 | 출력 항목 상한. 초과 시 "나머지 N건" 표시 |

**`--refs-only`(사실 없이 근거 위치만)는 공통 옵션에서 제외했다.** `--max`와 `--format json`으로 출력량 조절이 가능하고, 근거는 `## evidence`에 항상 나온다. 18개 명령 전부에서 "사실 없이 위치만"의 의미가 명확하지도 않다(`trace-guide`, `trace-rule`, `trace-term` 등). 후속으로 목록이 큰 `trace-screen`, `trace-branch`, `trace-table`에 한해 개별 추가를 검토한다.

---

## 4. 출력 규격

모든 `trace-*`는 같은 세 블록을 낸다.

```
## facts        추출된 사실
## evidence     파일:라인 / mapper id / 스냅샷 시각
## unresolved   추적하지 못한 호출, ${} 치환, 파싱 실패 등
```

- `unresolved`는 "모른다"를 명시하기 위한 블록이다. 동적 호출이나 파싱 실패를 사실처럼 보이지 않게 따로 모아, 에이전트가 직접 소스를 확인할 지점을 알 수 있게 한다.
- `--format json`은 같은 구조를 키로 쓴다: `command`, `description`, `side`, `options`, `params`, `facts`, `evidence`, `unresolved`.

현재 stub 출력 예 (`yunhee trace-table sys01_company --max 20`):

```
## facts
[STUB] 테이블 컬럼·코멘트, 이 테이블을 C/R/U/D 하는 SQL과 화면, ...
- command: yunhee trace-table
- side: both
- options: format=md, max=20
- arguments:
  - table_name: sys01_company

## evidence
[STUB] (근거 위치: 소스 코드 줄번호, mapper ID, DBML 스냅샷 시각 등이 여기에 표시됩니다)

## unresolved
[STUB] (추적되지 않은 동적 호출이나 미해결 참조가 여기에 표시됩니다)
```

---

## 5. 설계 포인트

- **`trace-rule verify`는 에이전트의 환각을 잡는 장치다.** 에이전트가 규칙의 근거로 적은 위치(파일:라인, mapper id)가 실제로 있는지, 내용이 바뀌지 않았는지를 yunhee가 결정적으로 확인한다. `drift`(원본 변경 감지)와 연결하면 원본이 바뀐 규칙도 자동으로 표시된다.
- **`trace-state`**는 상태 전이도의 재료(어느 SQL이 어떤 WHERE 조건에서 어떤 값을 쓰는가)만 제공한다. 전이도 작성은 에이전트가 한다.
- **사실과 해석의 분리**: yunhee는 사실·근거·미해결만 낸다. 판정과 서술은 에이전트가 하고, 그 판정은 `trace-rule`에 저장해 `verify`로 재검증한다.

---

## 6. 에이전트 워크플로우 예시

```
trace-map → trace-menu → trace-screen FND0101
  → trace-flow FND0101 --event E3
  → trace-branch FND0101 --side both
  → trace-diff FND0101 --branch
  → trace-state FND_MST.STAT_CD
  → trace-rule add ... → trace-rule verify
```

---

## 7. 구현 현황과 로드맵

### 7.1 현황 (0.6.5)

- **18개 명령 모두 구현됐다.** 등록은 `src/yunhee/tools/trace/__init__.py`(`register_trace_commands`), 명령 본체는 같은 폴더의 모듈이고, 공통 출력(§4)은 `render.py`, 대상 해석은 `resolve.py`가 맡는다. 구현 계획과 단계별 결과, 실제 실행 예는 [trace-업무분석용-구현.md](trace-업무분석용-구현.md)에 있다.
- 기반 모듈: `tools/sql_parse.py`(MyBatis 전개 + PostgreSQL AST), `tools/trace/tobe.py`(TOBE 호출 체인과 AS-IS 주석 색인), `tools/trace/sqlscan.py`(mapper 전체 해석 캐시), `store/trace_rules.py`(규칙 저장소).
- `tests/test_trace_*.py`가 명령별 동작을, `tests/test_trace_commands.py`가 18개 명령의 등록과 공통 계약을 검증한다.

### 7.2 구현 순서

1. `trace-screen`, `trace-table` — 기존 색인을 재조합하면 되므로 가장 빠르고 활용도가 높다.
2. `trace-branch`, `trace-flow` — 규칙 파악의 핵심.
3. `trace-pair`, `trace-diff`, `trace-gap` — 변환 검증용.
4. `trace-rule`(verify 포함), `trace-state`, `trace-doc`.

### 7.3 구현 시 따를 기존 원칙

- 추출 로직은 `tools/` 레이어의 독립 함수로 두고 `ToolResult`(ok/data/error/truncated)를 반환한다. CLI는 그것을 3블록으로 렌더링만 한다.
- 토큰 예산(`--max`, 문자 상한)은 tools 레이어에서 강제한다.
- 작업 대상은 `WORK_DIR` 기준, AssetERP 스키마 스냅샷은 `YUNHEE_DIR/data/schema/<ENV>.json` 기준이다.
- DB 조회가 필요하면(`trace-table`의 행 수·최근 갱신일, `trace-column`의 값 분포) `SELECT`만 허용하는 가드를 둔다. 사무실 외부에서는 접속할 수 없으므로 DB가 없으면 `unresolved`에 남기고 스냅샷 정보만 낸다.

---

## 8. 미결 사항

- `trace-screen` 출력 형식(섹션 구성, `--max` 적용 단위) 구체화 — 구현 1순위.
- `trace-rule` 저장소: sqlite `data/db/yunhee.db`에 `project` 컬럼으로 구분해 저장하는 방향(기존 결정과 동일). 스키마(규칙 ID, 판정, 사유, 근거 위치, 근거 해시) 설계 필요.
- `--refs-only`의 개별 명령 추가 여부(§3).
