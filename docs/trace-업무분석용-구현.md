# trace-* 업무분석용 구현 계획

- 기준: yunhee **0.5.10** (18개 명령은 껍질(stub)만 있음 — `src/yunhee/tools/trace/`)
- 목적과 명령 정의는 [trace-업무분석용-설계.md](trace-업무분석용-설계.md)를 따른다. 이 문서는 **어떤 순서로, 무엇을, 어떻게 검증하며 만들지**를 정한다.
- 이 문서는 계획서다. 코드는 아직 구현하지 않는다.
- 아래 "사용예"의 출력 값(화면ID, 테이블명, 줄 번호 등)은 형식을 보이기 위한 **예시 값**이다. 실제 결과가 아니다.

---

## 0. 공통 구현 원칙

1. 추출 로직은 `src/yunhee/tools/trace/<명령>.py`의 순수 함수로 두고 `ToolResult`(ok/data/error/truncated)를 반환한다. `tools/trace/__init__.py`의 stub 호출을 이 함수 호출로 하나씩 교체한다.
2. 출력은 `stub.py`의 `format_trace_stub()`을 일반화한 `render.py`가 맡는다. facts/evidence/unresolved 3블록(md)과 같은 키의 json을 만든다.
3. **LLM(Qwen)을 쓰지 않는다.** 정규식·파서·AST·DB 카탈로그로만 사실을 만든다.
4. `--max`는 tools 레이어에서 강제하고, 초과분은 "나머지 N건"으로 표시한다. `truncated=True`를 렌더러가 읽는다.
5. 의존 데이터(색인, 스냅샷, DB)가 없으면 예외 대신 `unresolved`에 안내 문구를 낸다. 읽기 전용이며 DB는 `SELECT`만 허용한다.
6. 단계가 끝날 때마다 `pyproject.toml` 버전을 올리고 `src/yunhee/CHANGELOG.md` 맨 위에 같은 버전 항목을 추가한다(`tests/test_changelog.py`가 검사). 테스트는 `tests/test_trace_<명령>.py`에 둔다. 실제 ASIS 소스에 의존하는 테스트는 원본이 없으면 `pytest.skip`한다.

### 0.1 재사용 자산 (새 파서를 만들지 않는다)

| 필요한 것 | 재사용할 코드 |
|---|---|
| ASIS 색인(`docs/as-is/src/**`: `_index.json`, `screens/`, `services/`, `sql/`, `tables/`, `menus.md`) | 생성 `tools/as_is/src_indexer.py`, 로드 `tools/analysis/common.py`의 `load_index_data`, `resolve_as_is_paths` |
| 화면 UI·이벤트·Grid Spec·버튼 | `tools/as_is/events.py`, `tools/analysis/{screen,ui,grid,method,sql}.py` |
| DB 스키마·테이블 | `tools/as_is/dbml_indexer.py`, `tools/schema_snapshot.py`, `tools/page_schema.py`, sqlite `mapper_index` |
| SQL 정규화·diff·MyBatis 전개 | `tools/as_is/sql_drift.py`(`normalize_sql_for_drift`), `tools/as_is/mybatis_render.py`, `tools/comparator.py`(`render_mybatis_sql`) |
| 원본 변경 감지 | `tools/as_is/drift.py`(`compute_source_file_hash`, frontmatter) |
| TOBE 소스 요약 | `tools/analysis/tobe.py`, `tools/outliner.py` |
| 로컬 저장소 | `store/db.py`(sqlite `data/db/yunhee.db`) |

---

## 1. 구현 순서 한눈에

| 단계 | 내용 | 가칭 버전 |
|---|---|---|
| Step 0 | 공통 기반: 렌더러, 대상 해석기 | 0.6.0 |
| Step 0-b | SQL 파싱 어댑터 (MyBatis 전개 + pglast) | 0.6.0 |
| Step 0-c | 기존 SQL 해석 코드를 어댑터로 통합 | 0.6.0 |
| Step 1 | `trace-screen`, `trace-table` | 0.6.1 |
| Step 2 | `trace-branch`, `trace-flow` | 0.6.2 |
| Step 3 | `trace-pair`, `trace-diff`, `trace-gap` | 0.6.3 |
| Step 4 | `trace-rule`(verify 포함), `trace-state`, `trace-doc` | 0.6.4 |
| Step 5 | 나머지 8개: map, menu, column, code, crud, dblogic, term, guide | 0.6.5 |

앞 단계가 뒤 단계의 기반이다. Step 0/0-b 없이는 Step 1부터 막힌다.

---

## Step 0. 공통 기반

### 구현내용
- `tools/trace/render.py`: `Fact`, `Evidence`, `Unresolved` dataclass와 `render_md()`, `render_json()`, `apply_max()`. `stub.py`의 출력 규격(`## facts` / `## evidence` / `## unresolved`)을 그대로 유지한다.
- `tools/trace/resolve.py`: 색인 경로 해석(`resolve_as_is_paths` 재사용), `--side asis|tobe|both` 처리, 대상 이름 해석. 화면ID와 클래스명을 모두 받고(`FND0101` ↔ `Fnd01_Tab_FundSearch`), 모호하면 후보 목록과 함께 오류를 낸다(`AmbiguousTargetError` 재사용).
- 색인이 없거나 낡은 경우 `load_index_data()`의 경고를 `unresolved`로 옮긴다.

### 구현검증
- 기존 `tests/test_trace_stubs.py` 전부 통과(18개 `--help`, md/json 구조, `--max`).
- `tests/test_trace_render.py`: 3블록 순서, json 키, `--max` 절단과 "나머지 N건", 빈 facts.
- `tests/test_trace_resolve.py`: 화면ID/클래스명 해석, 모호 대상 오류, 색인 없음 → `unresolved`.

### 구현 결과 (2026-10-28, 0.6.1)
- **화면ID는 메뉴 번호로 푼다**: 색인의 `menus.md`(`sys06_menu.sys06_menu_no`)가 번호 → 화면 클래스를 잇는다. `trace-screen #1029`(또는 `1029`), 클래스명, 접두사(`Emp00`)를 모두 받는다. 앞서 미결이던 "화면ID 정규화"의 답이다.
- **trace-screen은 새 파서 없이 색인 문서를 재구성한다**: `index-src`가 이미 화면 문서에 메뉴·서비스(RPC)→서버→SQL ID·테이블·DB 함수·이벤트·Grid Spec·버튼을 담아 두므로 `tools/trace/screen.py`가 그 마크다운을 구조화해 3블록으로 낸다. SQL의 mapper 파일:줄은 `_index.json`에서 찾는다. 인라인 핸들러가 있는 버튼은 줄 범위(`인라인 L269-276`)로 줄인다.
- **`--class`**: 하위 클래스(탭 페이지·팝업)의 UI와 그 클래스가 호출하는 서비스만 보여 준다. 기본 출력은 주 클래스 상세 + 하위 클래스별 이벤트·버튼·그리드 개수 요약이다.
- **trace-table의 화면 역추적**: SQL → 서버 메서드(`server_classes[].methods[].sqls`) → 서비스 키 → 호출 클라이언트 클래스(`client_classes[].services`) → 소속 화면(`refs` 역탐색)으로 잇는다. 화면을 만나면 더 올라가지 않고(화면을 여는 화면은 호스트가 아니다), 클래스당 3개까지만 보이고 나머지는 개수로 접는다. `UpdateDataModel(테이블)`의 동적 INSERT/UPDATE/DELETE도 서비스에 포함한다.
- **FK 없음**: 스냅샷의 `refs`가 비어 있어(DB에 FK가 정의돼 있지 않음) "같은 이름의 컬럼을 가진 테이블"을 조인 후보로 제시한다. 백업·임시 테이블(`_20211118`, `bak` 등)은 개수만 알리고 뺀다.
- **성능**: `trace-table`은 mapper 3,480개를 해석하므로 첫 호출에 3초쯤 걸린다(프로세스 안에서만 캐시).
- **보류**: `trace-table`의 최근 갱신일(갱신 일시 컬럼 규칙 미확정), TOBE 쪽 SQL·화면 사용처(Step 3 `trace-pair`와 함께).
- **옵션**: `--src`, `--src-index`(색인 위치), `trace-screen`의 `--class`, `--tobe`, `trace-table`의 `--stats`, `--db`(스냅샷 이름).

### 사용예
실제 실행 결과(AssetERP 색인 `~/work/framework-sprt/AssetERP/docs/as-is/src`, 줄임 표시는 `…`).
```
$ yunhee trace-screen "#1029" --side asis --src-index <색인 경로> --max 4
## facts
- 종류: 화면
- 메뉴: 경영관리 > 01. 조직 및 사원관리 > 사원정보 관리 (#1029)
- 메뉴: 기본정보 > 기본정보 > 사원정보 등록 (#1452)
- 소스: client/vi/emp/Emp00_Tab_TransInfo.java
… 나머지 12건
## evidence
- client/vi/emp/Emp00_Tab_TransInfo.java (UI 클래스 Emp00_Tab_TransInfo)
- emp.Emp00_TransInfo.selectByText 호출: Emp00_Lookup_PersonnelRecordCard:165, Emp00_Tab_TransInfo:418 / 서버 Emp00_TransInfo.java:33
… 나머지 135건
## unresolved
- 해석 못 한 서비스 호출 `Emp00_Tab_TransInfo:387` `null`
- 이벤트 주의(Emp00_Tab_TransInfo): 도달 불가: tempDownloadButton 컬럼·툴바 미연결

$ yunhee trace-screen Emp00_Tab_TransInfo --class Emp02_TabPage_Others --side asis    # 하위 클래스 상세
$ yunhee trace-screen Emp00_Tab_TransInfo --side tobe --tobe <frontend/src>            # TOBE 요약

$ yunhee trace-table emp02_others --side asis
## facts
- 테이블: public.emp02_others — Others 개인정보
- PK: …
- 컬럼(21): …
- 같은 이름의 컬럼을 가진 테이블: 없음 (컬럼명에 테이블 접두사가 붙어 있어 조인 후보를 이름으로 찾을 수 없다)
- SQL 사용 62개 (C 등록 / R 조회 / U 수정 / D 삭제):
  C(3): emp02_others.insert, emp02_others.insertCopy, emp02_others.upsert
  R(58): …
  U(2): emp02_others.updateHireDate, emp02_others.upsert
  D(1): emp02_others.deleteByPersonId
- 서비스를 호출하는 클래스와 소속 화면(71): …
## unresolved
- mapper 22개는 PostgreSQL 문법이 아니라 정규식으로 추정해 R로만 집계함 (* 표시)

$ yunhee trace-table sys06_menu --stats --side asis    # 행 수: 665 (읽기 전용 SELECT count)
$ yunhee trace-table sys06_menu -o json --max 2        # 키: command, description, side, options, params, facts, evidence, unresolved, omitted
```

---

## Step 2. `trace-branch`, `trace-flow`

규칙 파악의 핵심이다.

### 구현내용

**trace-branch `<화면ID|클래스|mapper id>`**
- 화면/클래스: 이벤트 핸들러의 if/switch/throw(`events.extract_if_condition`, `events.detect_condition`), validator, 버튼 활성 조건.
- mapper id: 이 단계에서 만드는 분기별 변형(Step 0-b는 최대형 SQL까지만 제공)에서 `<if test>`, `<choose>`, CASE WHEN을 목록화.
- TOBE: TSX의 `disabled` 속성과 조건부 렌더링(`tools/analysis/tobe.py`의 JSX 파싱 재사용).
- unresolved: 조건식이 메서드 호출/동적 값인 지점.

**trace-flow `<화면ID> --event <En>`**
- 이벤트 하나를 끝까지 따라간다: 버튼 → 핸들러 → ServiceRequest 키(`SERVICE_KEY_LITERAL_RE`) → 서버 서비스 → sqlId → 테이블.
- 입력은 색인의 화면·서비스·SQL 파일 연결 정보. TOBE는 컨트롤러 → 서비스 → mapper 순으로 같은 형식.
- 사슬이 끊기는 곳(동적 호출 등)은 거기서 멈추고 `unresolved`.

### 구현검증
- 가짜 화면/매퍼로 분기 종류별 단위 테스트(if/switch/throw, `<if>`, CASE WHEN, `disabled`).
- 실제 ASIS 소스로 `trace-flow X --event E1`의 사슬 끝 테이블이 `analysis sql`/`events`의 결과와 같은지 대조.
- 존재하지 않는 `--event` → 오류 대신 가능한 이벤트 목록을 `unresolved`에 안내.

### 구현 결과 (2026-10-28, 0.6.2)
- **trace-flow는 줄 범위로 사슬을 잇는다**: 화면 색인 문서에 이벤트(`[E3] … → retrieve()`), 메서드 표(`retrieve() L394-432`, 호출처), 서비스 표(호출 위치 `Emp00_Tab_TransInfo:418`)가 모두 있으므로, 서비스 호출 줄이 핸들러의 줄 범위 안인지로 이벤트와 서비스를 결정적으로 잇는다. 메서드 표의 호출처로 간접 호출을 따라가고(`E5 → insert() → retrieve()`), 생성자(E0)와 인라인 핸들러는 이벤트가 알려 주는 줄 범위를 쓴다.
- **끊기는 곳은 거기서 멈춘다**: 핸들러가 다른 클래스(팝업·조회창)를 열면 "이 이벤트가 여는 하위 화면"으로 알리고 `--class`로 이어서 추적하게 한다. SQL ID가 없는 서비스, 해석 못 한 서비스 호출, 도달 불가 이벤트는 unresolved.
- **trace-branch의 대상 구분**: `ns.id` 형태가 mapper statement면 mapper 분기, 아니면 화면·클래스(메뉴 번호 포함)로 푼다. 없는 mapper id는 종료 코드 1.
- **Java 스캔**: 주석과 문자열 리터럴 속 코드를 무시하고(리터럴은 가린 텍스트에서 키워드를 찾고 표시는 원문에서 자른다), 여러 줄 조건은 괄호 짝으로 읽는다. 메서드·생성자별로 묶고, 메서드 표에 없는 구간은 "(메서드 구분 없음)"이다.
- **mapper 분기**: `<include>` 조각 안의 분기는 조각이 있는 파일:줄을 근거로 낸다. `<choose>` 자체는 `<when>`/`<otherwise>`로 충분해 빼고, `<where>`/`<trim>`/`<set>`은 속성이 있을 때만 알린다. DB 방언(`isTibero` 등) 분기는 업무 분기와 분리한다.
- **보류**: TOBE 쪽 사슬(컨트롤러 → 서비스 → mapper)과 TOBE mapper 분기는 `trace-pair`/`trace-diff --branch`(Step 3)에서 추가한다. 분기별 SQL 변형(`__pick__`)은 Step 0-c에서 이미 쓰고 있으며 `trace-diff --branch`의 분기 대응표에서 다시 쓴다.

### 사용예
실제 실행 결과(AssetERP 색인, 줄임 표시는 `…`).
```
$ yunhee trace-flow "#1029" -e E3 --side asis
## facts
- 이벤트(Emp00_Tab_TransInfo): [E3] transName[재직].Collapse (L225)
- 핸들러 메서드:
  - public retrieve() L394-432 (호출처 생성자, E1, E2, E3, E4, insert)
- 사슬(1):
  E3 → retrieve() (L418) → 서비스 emp.Emp00_TransInfo.selectByText → 서버 Emp00_TransInfo.java:33
      SQL emp00_trans_info.selectByText: emp03_trans(R), sys01_company(R), org01_code(R), …
- 쓰는 테이블: R: emp01_person, emp02_others, emp03_trans, …
## evidence
- Emp00_Tab_TransInfo:418 서비스 emp.Emp00_TransInfo.selectByText 호출 / 서버 Emp00_TransInfo.java:33

$ yunhee trace-flow "#1029" -e E5      # E5 → insert() → retrieve(), 여는 하위 화면: Emp03_Edit_Person
$ yunhee trace-flow "#1029" -e E4 --class Emp02_TabPage_Others   # 하위 클래스의 이벤트: updateOne → emp02_others(CU)
$ yunhee trace-flow "#1029"            # --event 생략: 이벤트 목록

$ yunhee trace-branch "#1029" --side asis
## facts
- 이벤트 조건(3) — 이 조건일 때만 핸들러가 실행됨:
  - [E2] searchText.KeyPress [Enter] (L209) → 조건 [Enter]
  - [E12] grid.SelectionChanged [선택>0] (L285) → 조건 [선택>0]
- 도달 불가 이벤트(1): …
- 소스 분기(12) — if / else if / switch / throw:
  생성자:
    - L95 if (LoginUser.getIsManager())
  retrieve():
    - L403 if ("겸직".equals(transName.getText()))
    - L406 else if ("퇴직".equals(transName.getText()))
- 활성·표시 조건(4, 식으로 정해지는 것 0): …

$ yunhee trace-branch emp00_trans_info.selectByText --side asis
- 동적 SQL 분기(18):
  - L1440 <when test> emp00CompanyId != null  (include common.emp00_trans_info → server/utils/db/mapper/Common.xml)
  - L381 <when test> isSeparateAddTitle == true
$ yunhee trace-branch Emp00_Tab_TransInfo --side tobe --tobe <frontend/src>   # TSX 조건
```

---

## Step 3. `trace-pair`, `trace-diff`, `trace-gap`

변환 검증용이다. ASIS와 TOBE를 모두 읽는다.

### 구현내용
- **trace-pair**: 같은 mapper id, 같은 테이블 조합, 같은 이름으로 ASIS-TOBE 항목을 짝짓고 **매칭 근거를 함께** 출력한다. 근거가 약한 짝(이름만 같음)은 따로 표시한다.
- **trace-diff `--sql|--branch|--ui`**: `--sql`은 `normalize_sql_for_drift` + `get_diff_details`로 정규화 diff, `--branch`는 Step 2 결과의 분기 대응표, `--ui`는 필드 대응표(`comparator`의 필드 매칭 로직 재사용).
- **trace-gap `[--domain]`**: ASIS에만 있는 것, TOBE에만 있는 것, 추적하지 못한 것을 집계. `--domain`으로 범위를 좁힌다.

### 구현검증
- 짝이 있는/없는/부분 일치하는 가짜 ASIS·TOBE 쌍으로 단위 테스트.
- 이미 변환이 끝난 화면(수정사항·작업기록에 있는 화면)으로 `compare`, `sql-check`의 결과와 trace-diff 결과가 모순되지 않는지 대조.
- `--sql`/`--branch`/`--ui`를 지정하지 않으면 3가지를 모두 요약하는지, 중복 지정이 가능한지 확인.

### 구현 결과 (2026-10-28, 0.6.3)
- **짝은 TOBE 소스의 AS-IS 주석을 근거로 짓는다**: 실제 TOBE에서 TSX 707/708개가 `AS-IS:` 헤더를, 컨트롤러 엔드포인트 1,501개 중 1,299개가 `AS-IS <서비스 키>` 주석을, mapper XML 문장 2,545개 중 1,445개가 `AS-IS <SQL id>` 주석을 갖고 있다. 이름이 비슷하다는 이유만으로는 짝짓지 않는다. 근거는 항목마다 `[근거: …]`로 함께 낸다.
- **TOBE 호출 체인 색인** (`tools/trace/tobe.py`): `TSX → api/*.ts → 컨트롤러 → 서비스 → mapper 인터페이스 → XML 문장`을 정규식으로 따라간다. 엔드포인트 1,501개 전부에서 서비스 호출을 찾았고 94%(1,417개)가 mapper 문장까지 이어진다. 한 번 만들면 프로세스 안에서 캐시한다(0.4초).
- **`--tobe`**: TOBE 프로젝트 루트 또는 `frontend/src`. `trace-screen`·`trace-branch`의 `--tobe`도 같은 규칙으로 통일했다.
- **trace-pair**: 화면(같은 클래스명, TSX 헤더 AS-IS, 메뉴 번호 일치), 서비스↔API, SQL↔문장, 테이블 집합 비교. ASIS에만 있는 서비스와 근거 없는 TOBE API를 따로 보인다. 같은 ASIS SQL을 다른 화면 쪽에서 이식한 문장은 "이 화면의 API 체인 밖"으로 표시한다. 테이블 조합만 같은 짝은 후보가 하나일 때만 "약한 근거"로 짓는다.
- **trace-diff**: `--sql`은 두 문장을 AST로 구조 비교(테이블·쓰기·사용 컬럼·출력 이름·WHERE·CTE·함수·CASE 수), `--branch`는 같은 식별자끼리의 분기 대응(`isSeparateAddTitle`↔`separateAddTitle`), `--ui`는 라벨로 짝짓는 그리드 열·버튼·이벤트. 차이는 사실로만 내고 의도 여부는 에이전트가 판정해 `trace-rule`에 남긴다.
- **trace-gap**: 화면·서비스·SQL의 ASIS에만/TOBE에만 있는 것과, **근거를 찾지 못한 지점**(AS-IS 주석 없는 엔드포인트·mapper 문장·TSX)을 "대응 없음"과 구분해 `unresolved`로 센다.
- **한계(출력에 명시)**: 화면 분기는 Java와 React의 식이 달라 대응이 적게 나온다. TOBE 버튼은 `<Button>` 글자와 이벤트 주석의 라벨만 센다. 결합 서비스(`dbConfig.*`)는 짝짓기 대상에서 뺀다.

### 사용예
실제 실행 결과(AssetERP 색인 + TOBE 프로젝트, 줄임 표시는 `…`).
```
$ yunhee trace-pair "#1029" --tobe ~/work/framework-sprt/AssetERP
## facts
- 화면 짝(22/29):
  - Emp00_Tab_TransInfo ↔ frontend/src/pages/emp/Emp00_Tab_TransInfo.tsx (근거: 같은 클래스명; TSX 헤더 AS-IS 일치; 메뉴 번호 일치 #1029,#1452)
- 서비스(RPC) ↔ API 짝(15/66):
  - emp.Emp00_TransInfo.selectByText ↔ GET /api/v1/emp/trans-infos (EmpTransInfoController.searchTransInfos) — TOBE 호출: Emp00_Tab_TransInfo(empApi.searchTransInfos) [근거: 컨트롤러 주석의 AS-IS 서비스 키]
- ASIS에만 있음 — TOBE에 대응 API 없음(51): …
- TOBE에만 있음 — 화면이 부르는데 이 ASIS 화면의 서비스와 짝이 없는 API(46): …  [AS-IS 주석 없음]
- SQL ↔ mapper 문장 짝(70):
  - emp00_trans_info.selectByText ↔ EmpTransInfoMapper.searchTransInfos [근거: 문장 주석의 AS-IS id]
- 테이블 비교: 같음 18 / ASIS만 18 / TOBE만 2

$ yunhee trace-diff emp00_trans_info.selectByText --sql --tobe <TOBE>
- emp00_trans_info.selectByText ↔ EmpTransInfoMapper.searchTransInfos [근거: 문장 주석의 AS-IS id]
  테이블: ASIS만 [sys01_company, sys04_role, sys05_user_role, sys06_menu, sys07_role_menu] / TOBE만 []
  WHERE 조건: ASIS만 [exists (select 1 from sys06_menu inner join sys07_role_menu … )]   ← 권한 조건이 TOBE에 없다
  함수: ASIS만 [f_org_parent_info_nm, substr, to_decrypts] / TOBE만 []
  정규화 SQL: 다름

$ yunhee trace-diff "#1029" --ui --tobe <TOBE>
  그리드 열: ASIS 18 / TOBE 17 — 같은 라벨 17 [근거: 라벨 일치]
    필드 이름이 바뀜(7): 성명(empKorName→korNm), 이메일(emailAddress→emailAddr), …
    ASIS에만: 책무임원(tdmTargetYn)
  이벤트: ASIS 14 — 구현 표시 10, 생략 표시 3, 도달 불가 1, 표시 없음 1 [E13]

$ yunhee trace-diff emp00_trans_info.selectByText --branch --tobe <TOBE>
- 분기 대응 emp00_trans_info.selectByText ↔ searchTransInfos: ASIS 15 / TOBE 5 — 대응 2, ASIS만 13, TOBE만 3
  ≈ ASIS L381 when isSeparateAddTitle == true  ↔  TOBE L120 when separateAddTitle  [근거: 같은 식별자 separateaddtitle]

$ yunhee trace-gap --domain emp --tobe <TOBE> --max 6
- 화면: ASIS 40 / TOBE 61 — TOBE에 대응 TSX가 있는 ASIS 화면 21
- 서비스(RPC): ASIS 395 / TOBE 주석에 적힌 서비스 키 95 — 대응 95
- SQL: ASIS 324 — TOBE 문장 주석이 가리키는 것 119
## unresolved
- AS-IS 서비스 키 주석이 없어 ASIS 출처를 추적하지 못한 TOBE 엔드포인트(44): …
```

---

## Step 4. `trace-rule`, `trace-state`, `trace-doc`

### 구현내용

**trace-rule `add|list|show|update|verify`**
- 저장소: sqlite `data/db/yunhee.db`의 `trace_rule` 테이블. `project` 컬럼(= `.yunhee/project.json`의 name)으로 프로젝트를 구분한다(기존 결정과 동일).
- 컬럼(안): `project`, `rule_id`, `target`, `verdict`(일치/누락/변경/의도적 변경), `note`, `evidence_path`, `evidence_line`, `evidence_hash`, `created_at`, `updated_at`.
- `add`는 근거 위치의 해시를 함께 저장한다(`drift.compute_source_file_hash` 재사용).
- **`verify`**: 저장된 근거마다 (1) 파일/줄/mapper id가 존재하는지 (2) 저장한 해시와 현재 내용이 같은지 확인한다. 결과는 `OK` / `MISSING` / `STALE`. 에이전트가 근거로 적은 위치가 실제로 없으면 `MISSING`이 되므로 환각을 결정적으로 잡는다.
- 테이블이 없으면 첫 사용 시 생성(`CREATE TABLE IF NOT EXISTS`).

**trace-state `<테이블.컬럼>`**
- Step 0-b의 UPDATE SET/INSERT 값과 WHERE를 모아, 이 컬럼에 값을 쓰는 모든 SQL의 `대입 값`과 `WHERE 조건`을 나열한다. 전이도는 그리지 않는다.

**trace-doc `<영역>`**
- 카탈로그(`trace_rule`)와 Step 1~3의 팩트를 신규 인원용 마크다운 골격으로 조립한다. 서술이 들어갈 칸은 비워 둔다.

### 구현검증
- `tests/test_trace_rule.py`: add/list/show/update CRUD, project 분리, verify의 OK/MISSING/STALE 3경우(임시 파일을 만들고 수정/삭제해서 재현).
- `tests/test_trace_state.py`: `SET stat_cd = 'A' WHERE stat_cd = 'N'` 같은 가짜 SQL로 대입 값과 WHERE 추출, CASE로 대입하는 경우.
- `trace-doc` 출력이 빈 카탈로그에서도 오류 없이 골격만 내는지 확인.
- DB 쓰기는 `trace_rule` 테이블에만 한다(다른 테이블/AssetERP DB는 읽기 전용).

### 구현 결과 (2026-10-28, 0.6.4)
- **trace-rule 저장소**: `data/db/yunhee.db`의 `trace_rule`(프로젝트·규칙 ID·대상·판정·사유·시각)과 `trace_rule_evidence`(근거 목록)를 프로젝트별(`.yunhee/project.json`의 name)로 둔다. 규칙 ID는 프로젝트마다 `R-001`부터. 판정은 `일치`·`누락`·`변경`·`의도적 변경`이고 영어·줄임말(`changed`, `의도적`)도 받는다. 테이블은 첫 사용 때 만든다.
- **근거는 내용으로 검증한다**: 근거는 `파일:줄`, `파일:시작-끝`, 파일, mapper id(ASIS `ns.id`, TOBE `Mapper클래스.id`). 저장하는 순간 **파일·줄·문장을 실제로 읽어 확인**하고(없으면 저장 거부, 종료 코드 2) 본문의 정규화 해시와 내용을 함께 저장한다. 줄 번호는 코드가 바뀌면 밀리므로 판정은 내용으로 한다: `OK`(같음), `MOVED`(내용은 같고 위치만 이동 — 빈 줄이 끼어 길이가 달라져도 줄 경계에 맞게 찾는다), `STALE`(내용이 바뀜), `MISSING`(파일·줄·문장이 없어짐, 또는 근거가 없음). mapper는 `normalize_sql_for_drift`로 공백·대소문자·주석 차이를 무시하고 SQL이 바뀐 것만 STALE로 본다.
- **verify 종료 코드**: MISSING 또는 STALE이 있으면 1, MOVED만 있으면 0. `--accept R-NNN`은 MOVED를 새 위치로 옮기고(`Sample.java:2-4` → `:3-5`) STALE을 현재 내용으로 갱신한다.
- **trace-state**: 모든 mapper를 `keep_params`로 해석해 컬럼의 대입을 모은다(CTE 안의 UPDATE·`ON CONFLICT` 포함, 첫 호출 4초). 파라미터는 `#{statusCode}`로 남겨 상수(`'99'`)와 호출자가 정하는 값을 구분한다. `UpdateDataModel` 동적 쓰기는 값을 추측하지 않고 서비스 목록만 낸다. 한계: 상태 전이의 선행 조건이 SQL이 아니라 Java에 있으면 `WHERE`에 보이지 않는다.
- **trace-doc**: facts의 각 항목이 문서의 한 절이라 `options["document"]`로 불릿 없이 마크다운 그대로 낸다(근거·미해결은 뒤에 붙음). 서술 자리는 `<!-- 서술(에이전트): … -->`와 체크리스트로 남긴다.
- **주의**: `trace-rule`은 yunhee에서 유일하게 로컬 sqlite에 **쓰는** 명령이다. 다른 trace-*는 모두 읽기 전용이다.

### 사용예
실제 실행 결과(AssetERP 색인 + TOBE, 줄임 표시는 `…`).
```
$ yunhee trace-rule add "#1029" -v "의도적 변경" --note "조회 조건 isSeparateAddTitle를 separateAddTitle로 옮김" \
    -E Emp00_Tab_TransInfo.java:394-432 -E emp00_trans_info.selectByText -E EmpTransInfoMapper.searchTransInfos -E Emp00_Tab_TransInfo.tsx
## facts
- 규칙 저장: R-001 [의도적 변경] #1029 — 조회 조건 … (근거 4건)
## evidence
- asis client/vi/emp/Emp00_Tab_TransInfo.java:394-432
- asis server/emp/mapper/emp00_trans_info.xml:339 (emp00_trans_info.selectByText)
- tobe backend/src/main/resources/mapper/EmpTransInfoMapper.xml:110 (kr.co.kfs.asseterp.biz.emp.mapper.EmpTransInfoMapper.searchTransInfos)
- tobe frontend/src/pages/emp/Emp00_Tab_TransInfo.tsx

$ yunhee trace-rule add "#1029" -v 누락 -E Emp00_Tab_TransInfo.java:9999
Emp00_Tab_TransInfo.java은 446줄인데 L9999-9999를 가리킴: Emp00_Tab_TransInfo.java:9999     # 종료 코드 2, 저장 안 됨

$ yunhee trace-rule verify                       # 모든 규칙의 근거 확인. 깨진 근거가 있으면 종료 코드 1
- 검증 결과: OK 1, MOVED 0, STALE 0, MISSING 0 (규칙 1건)
- R-001 OK [의도적 변경] #1029
    OK      Emp00_Tab_TransInfo.java:394-432
    OK      emp00_trans_info.selectByText
$ yunhee trace-rule verify R-001 --accept        # MOVED·STALE 근거를 확인한 뒤 현재 내용으로 갱신
$ yunhee trace-rule list emp00                   # 대상 접두사로 목록
$ yunhee trace-rule show R-001
$ yunhee trace-rule update R-001 --note "…" -v 변경

$ yunhee trace-state apr01_appr.apr01_status_cd --side asis
- ASIS: 쓰는 SQL 6개, 대입 값 4종
  #{statusCode} ← apr01_appr.insert(INSERT), apr01_appr.insertApprTemp(INSERT), apr01_appr.insertApproval(INSERT)
  #{apprStatusCode} ← apr01_appr.confirmUpdate(UPDATE)
  #{statusCd} ← apr01_appr.updateStepCd(UPDATE)
  '99' ← apr01_appr.cancelUpdate(UPDATE)
- ASIS SQL별 값과 조건:
  - apr01_appr.cancelUpdate [UPDATE] server/apr/mapper/apr01_appr.xml:1613
      값: '99'
      조건: apr01_appr_id = #{apprId}
- 동적 쓰기(UpdateDataModel, 2) — … 값은 클라이언트가 보내는 모델이 정하므로 SQL로는 알 수 없음:
  - apr.Apr01_Appr.modelUpdate (등록/수정)

$ yunhee trace-doc emp --tobe <TOBE> > docs/emp-개요.md      # 골격 (표는 사실, 서술은 표지)
# emp 업무 영역 — 신규 인원용 개요
## 1. 화면      화면 40개, TOBE로 이식된 화면 21개 + 표(메뉴 번호·화면·TOBE 상태·서비스 수·주요 테이블)
## 2. 테이블    이 영역의 화면이 쓰는 테이블 … (사용 화면 수 순, 설명은 스냅샷)
## 3. 서비스(RPC) · ## 4. 규칙 카탈로그 · ## 5. ASIS↔TOBE 대응 현황 · ## 6. 채워야 할 서술(체크리스트)
```

---

## Step 5. 나머지 8개

성격이 비슷한 것끼리 세 묶음으로 구현했다 (0.6.5).

### 구현 결과 (2026-10-28, 0.6.5)

**묶음 A — SQL 해석 기반: `trace-column`, `trace-code`, `trace-crud`**
- **trace-column**: 컬럼을 읽는(SELECT 목록·SET 식·RETURNING) / 조건에 쓰는(WHERE·JOIN·HAVING) / 정렬·그룹 / 쓰는 SQL을 **SQL AST의 절**로 구분한다 (`sql_parse`가 컬럼이 쓰인 절을 기록). 화면 라벨은 컬럼명에서 만든 속성 이름(`emp01_kor_nm`→`korNm`)이 Grid Spec·TOBE 그리드 필드명과 같은 곳에서 찾는다. `--stats`의 값 분포는 **고유 값 30종 이하인 코드성 컬럼만** 값을 낸다 — 실제로 `emp01_kor_nm`은 값 대신 "고유 값 776종, 값은 내지 않음"으로 나왔다(이름이 컨텍스트에 새지 않게).
- **trace-code**: DB(`sys08_code_kind`·`sys09_code`, 읽기 전용)의 코드값과, 소스에서 그룹 이름이 따옴표로 적힌 곳(SQL 리터럴 / 콤보 / 상수 비교 / 기타, 주석 제외). `AprStatusCode`는 코드 5개, ASIS 사용처 249곳(콤보 5)·TOBE 77곳.
- **trace-crud**: 화면 → 서비스 → SQL → 테이블로 ASIS의 C/R/U/D를, TOBE는 TSX → api → 컨트롤러 → 서비스 → mapper로 만들어 나란히 비교하고 TOBE에 없는 테이블·작업에 ⚠를 붙인다. `UpdateDataModel` 동적 쓰기를 `_index.json`의 `udm_calls`로 더한다 — 처음에는 서비스에 SQL ID가 하나라도 있으면 동적 쓰기를 건너뛰어 `emp04_add_title: ASIS RD / TOBE CRUD`처럼 가짜 차이가 났고, 고치자 `#1029`의 탭 테이블이 모두 일치하고 진짜 차이(`apr99_appr_del`)만 남았다.

**묶음 B — 색인 집계: `trace-map`, `trace-menu`, `trace-term`**
- **trace-map**: 영역별 ASIS 규모와 TOBE 이식 현황. 전체 화면 507개 중 275개(54%) 이식, `emp` 40개 중 21개(52%), `tdm` 97%, `ast` 9%. 영역이 아닌 이름은 거른다.
- **trace-menu**: `menus.md`의 트리를 화면 클래스 → TOBE TSX·API 호출로 잇는다. 경로 조각은 각 단계에 순서대로 부분 일치, `#번호`·클래스명도 받는다.
- **trace-term**: 컬럼 이름·코멘트, 테이블 설명, ASIS·TOBE 화면 라벨, 공통 코드 이름을 교차한다. 라벨 ↔ 컬럼은 속성 이름 규칙이 맞고 후보가 3개 이하일 때만 이어 근거를 밝힌다 (처음에는 속성 3개를 합쳐 관련 없는 컬럼 19개를 나열해 속성별·후보 수 제한으로 바꿨다).

**묶음 C: `trace-dblogic`, `trace-guide`**
- **trace-dblogic**: 스냅샷의 함수·프로시저·트리거 본문(최대 276KB라 80줄 상한)과 시그니처, 본문이 참조하는 테이블·부르는 함수, 이를 실행하는 트리거, DB 안 호출자, **ASIS·TOBE SQL 호출처**. `f_cdnm`은 ASIS 문장 935개·TOBE 399개가 호출한다.
- **trace-guide**: 명령 목록을 등록된 `trace-*` 명령에서 직접 읽어 코드와 어긋나지 않는다 (테스트가 분류와 등록 명령의 일치를 검증).

### 사용예
실제 실행 결과(줄임 표시는 `…`).
```
$ yunhee trace-column apr01_appr.apr01_status_cd --stats --side asis
- 컬럼: apr01_appr.apr01_status_cd character varying(10) — 상태코드(AprStatusCode)
- ASIS: 이 컬럼을 쓰는 SQL …개
  조건(WHERE·JOIN·HAVING)(…): …   쓰기(INSERT/UPDATE)(6): apr01_appr.insert(INSERT), apr01_appr.cancelUpdate(UPDATE), …
- 값 분포(행 951, NULL 0, 고유 값 5종):
  30: 637, 10: 173, 40: 84, 20: 38, 99: 19

$ yunhee trace-code AprStatusCode
- 코드 그룹: AprStatusCode — 문서결재상태코드 (코드 5개)
    10 상신 / 20 결재중 / 30 완료 / 40 반려 / 99 임시저장
- ASIS 사용처 249곳: SQL 리터럴(mapper)(244) — f_cdnm('AprStatusCode', …) …, 콤보·선택 목록(5) — ComboBoxField("AprStatusCode", …)

$ yunhee trace-crud --screen "#1029" --tobe <TOBE>
- 화면 Emp00_Tab_TransInfo: 테이블 36개 (ASIS 36 / TOBE 27)
  apr99_appr_del: ASIS R / TOBE -  ⚠ TOBE에 없음
  emp02_others: ASIS CRU / TOBE CRUD  (TOBE에 D 추가)
  emp03_trans: ASIS CRUD / TOBE CRUD

$ yunhee trace-map --tobe <TOBE>
- 전체: ASIS 화면 507, TOBE 이식 275 (54%)
- emp (경영관리): ASIS 화면 40, 컴포넌트 16, 서비스 395, SQL 324, 테이블 55 | TOBE 이식 21/40 (52%), TSX 61, 엔드포인트 146, mapper 문장 288

$ yunhee trace-menu "조직 및 사원관리 > 사원정보" --tobe <TOBE>
- 경영관리 > 01. 조직 및 사원관리
  - 사원정보 관리 (#1029) → Emp00_Tab_TransInfo — TOBE frontend/src/pages/emp/Emp00_Tab_TransInfo.tsx / API 1개: GET /api/v1/emp/trans-infos

$ yunhee trace-term 성명
- 용어 '성명': 컬럼 5, 테이블 0, ASIS 라벨 3종, TOBE 라벨 4종
  - '가족성명' ← Emp00_Tab_TransInfo
      familyNm ↔ 컬럼 emp06_family.emp06_family_nm  [근거: 속성 이름이 컬럼명에서 만든 이름과 같음]

$ yunhee trace-dblogic f_cdnm
- function f_cdnm(av_code_kind character varying, …) RETURNS character varying [plpgsql]
- 본문이 참조하는 테이블(3): ast05_tr_code, sys08_code_kind, sys09_code
- ASIS SQL 호출처 935개: …   TOBE SQL 호출처 399개: …

$ yunhee trace-guide > docs/trace-지침.md     # 에이전트용 지침 (명령 목록은 코드에서 생성)
```

---

## 2. 공통 검증 (전 단계)

- `uv run pytest`, `uv run ruff check .` 통과.
- 18개 명령의 `--help`, md/json 3블록 구조, `--max` 절단, `--side` 분기가 계속 통과(`tests/test_trace_commands.py` 유지·확장).
- 의존 데이터 없음(색인/스냅샷/DB) → 예외 없이 `unresolved` 안내, 종료 코드 0.
- 읽기 전용 확인: `trace-rule`의 `trace_rule` 테이블 외에는 아무것도 쓰지 않는다.
- 실제 ASIS 소스가 있는 환경에서 한 번은 Step 마무리 수동 검증(기존 검증 화면과 결과 대조)을 하고, 결과를 해당 버전의 CHANGELOG에 기록한다.

## 3. 미결 사항 / 리스크

- 화면ID 정규화: `FND0101`과 `Fnd01_Tab_FundSearch`의 대응을 색인의 어떤 필드로 풀지(Step 0에서 확정).
- TOBE 쪽 색인이 없으면 `--side tobe`의 범위가 `analysis tobe` 수준(파일 요약)으로 제한된다.
- pglast 휠이 실제 Python 버전에서 설치되는지(Step 0-b 첫 검증) — 안 되면 의존성 결정 재검토.
- Step 0-c 교체로 `mapper_index`의 테이블 목록이 바뀐다. `prepare`/`table --page`의 기존 결과가 달라질 수 있으므로 CHANGELOG에 명시하고, ASIS 소스 변경 시처럼 `parse_mapper.py` 재실행이 필요하다.
- mapper 로더 3종 통합, `sql_porter` AST 전환, `sql_drift` AST 지문 비교는 후속 과제.
- `trace-rule`의 스키마 변경 시 마이그레이션 방식(초기에는 `CREATE TABLE IF NOT EXISTS`만).
- `--refs-only`는 후속 검토(설계 문서 §3).
