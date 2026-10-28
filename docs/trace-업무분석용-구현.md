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

### 사용예
```
$ yunhee trace-screen Fnd01_Tab_FundSearch --max 5
$ yunhee trace-screen FND9999
## facts
(없음)
## unresolved
- 화면 'FND9999'를 색인에서 찾지 못함. 후보: Fnd01_Tab_FundSearch, Fnd09_Tab_Report
```

---

## Step 0-b. SQL 파싱 어댑터

`trace-table`, `trace-column`, `trace-state`, `trace-crud`, `trace-branch`, `trace-diff`가 모두 SQL을 해석하므로 먼저 만든다. 현재 `src_indexer`의 `TABLE_KEYWORD_RE`는 정규식이라 `UPDATE`/`INSERT INTO` 대상과 CTE 구분이 부정확하다(수정사항 021 A-2 참고).

### 구현내용
`src/yunhee/tools/sql/parse.py` (신규 의존성 `pglast>=7` — PostgreSQL 서버 파서 `libpg_query`의 Python 바인딩, PostgreSQL 전용).

1. **MyBatis 전개**: `mybatis_render.py` / `comparator.render_mybatis_sql`을 재사용한다.
   - `#{x}` → `$n` 또는 `NULL`, `<include>` 전개, CDATA 보존.
   - `<if>`/`<choose>`는 **모든 분기를 켠 최대형 SQL**과 **분기별 변형**을 모두 만든다. 테이블·컬럼 추출은 최대형으로, `trace-branch`는 분기별 변형으로 쓴다.
   - `${}` 치환은 풀 수 없으므로 `unresolved`에 남긴다.
2. **AST 파싱**: `pglast.parse_sql()`.
   - 테이블: `RangeVar`. 읽기/쓰기는 최상위 노드 종류(Select/Insert/Update/Delete)로 구분하고 CTE 이름은 제외한다.
   - 컬럼: `ColumnRef`. UPDATE의 SET 대입(`ResTarget`)과 WHERE는 별도로 모은다(`trace-state` 재료). INSERT 컬럼 목록도 모은다.
3. **별칭 해석**: FROM/JOIN의 `RangeVar.alias`로 `{별칭: 테이블}` 맵을 만들어 직접 해석한다. 한정자 없는 컬럼과 `SELECT *`는 스냅샷 스키마(`schema_snapshot`)로 보강하고, 보강할 수 없으면 `unresolved`.
4. **실패 폴백**: 파싱이 실패하면 기존 정규식으로 추정하되 결과에 `파싱 실패, 정규식 추정`을 표시한다. 틀린 값을 사실처럼 내지 않는다.
5. 파서 호출은 이 모듈 한 곳에만 둔다(나중에 교체 가능하도록).

### 구현검증
- `uv add pglast` 후 실제 사용 Python에서 `import pglast`가 되는지, **바이너리 휠로 설치되는지(소스 빌드 없음)** 확인한다. pglast 7.x는 Python 3.14 바이너리 휠을 제공한다고 알려져 있으므로 `requires-python`(현재 `>=3.13`)과 맞는지 먼저 확인하고, 안 맞으면 `pyproject.toml`을 조정한다.
- `tests/test_trace_sqlparse.py` 단위 테스트: `WITH upsert AS (...) INSERT ...`(CTE 제외), `::` 캐스트, `ON CONFLICT`, `RETURNING`, `f_create_seq()` 호출, UPDATE SET/WHERE 추출, 별칭 해석, `${}` → `unresolved`.
- **스모크**: `mapper_index`(또는 ASIS `mapper/*.xml`) 전체를 전개 + 파싱해 성공률과 실패 목록을 출력하는 스크립트(`tools/` 아래). 실패는 원인별로 분류해 어댑터를 보강한다. 이 결과를 이후 단계의 정확도 기준선으로 삼는다.
- (선택) 서버 로그의 실제 실행 SQL(`log trace`)에서 뽑은 테이블 집합과 비교한다.

### 사용예
내부 모듈이라 CLI는 없다. 코드 사용:
```python
from yunhee.tools.sql.parse import parse_statement
res = parse_statement(xml_path, "emp02_others.upsert")
res.data.tables   # {"emp02_others": "W"}          (upsert는 CTE라 제외)
res.data.ctes     # ["upsert"]
res.unresolved    # []
```

---

## Step 0-c. 기존 SQL 해석 코드 통합

pglast 어댑터(Step 0-b)가 생기면 같은 일을 정규식·괄호 깊이 계산으로 하던 기존 코드가 어댑터와 다른 결과를 내게 된다. `trace-*`와 기존 명령(`analysis sql`, `prepare`, `index-src`)이 서로 다른 테이블 목록을 말하지 않도록, 기존 코드를 어댑터로 옮긴다. `trace-*`의 정확도 기준을 한 곳에 두는 선행 작업이다.

### 현황 (교체 대상)

| 위치 | 하는 일 | 문제 |
|---|---|---|
| `tools/parse_mapper.py` `TABLE_RE` | mapper 참조 테이블을 `mapper_index`에 저장 | `from\|join\|into\|update` 뒤 단어를 그대로 잡는다. CTE 제외가 없고 `EXTRACT(year FROM col)`의 `FROM`도 테이블로 잡는다. 노이즈는 `"_" in n` 관례로만 거른다. |
| `tools/as_is/src_indexer.py` `parse_mappers` | 화면→SQL→테이블 호출 경로 색인 | 별도 정규식(`TABLE_KEYWORD_RE`, `CTE_RE`). `CTE_RE`는 `\w+ as (`라 CTE가 아닌 곳도 잡고, `known_tables`와 같은 단어는 전부 테이블로 간주해 컬럼명과 겹치면 오탐이 난다. |
| `tools/analysis/sql.py` | `analysis sql`의 테이블·CTE 추출, CTE 접기, WHERE 분리 | `'` 토글과 괄호 깊이를 직접 세는 스캐너(`''` 이스케이프, 주석 미처리). UPDATE/INSERT 대상을 못 잡는다(수정사항021 A-2). |
| `tools/analysis/model.py` | 모델 ↔ SQL 대조 | `FROM\|JOIN`만 보고, "컬럼"을 본문의 모든 단어로 둔다. |
| `tools/as_is/events.py` `find_mapper_for_model` | 모델의 대표 테이블 | XML의 첫 `from` 뒤 단어를 테이블로 본다. |
| `tools/as_is/sql_checker.py` `select_output_names` 외 | SELECT 출력 이름 추출 | `_mask_sql`, `_depth0_matches`, `split_top_level`을 직접 구현. AS 없는 별칭은 정규식 휴리스틱. |

mapper를 읽는 경로도 3가지가 따로 있다: `parse_mapper.py`(`xml.etree`), `src_indexer.parse_mappers`(정규식 + `strip_sql`), `mybatis_render.load_statements`(자체 `parse_xml`, 별개의 `Statement` 클래스). 그래서 `mapper_index`(`page_schema`, `mapper_verify`, `prepare`가 사용)와 색인의 테이블 목록이 달라질 수 있다.

### 구현내용
통합 기준은 **`mybatis_render.render(mode="explain")`로 만든 SQL을 Step 0-b 어댑터에 넣는 것**이다. 이 모드가 이미 `#{}`와 `<if>`를 풀어 EXPLAIN 가능한 SQL을 만든다. `<include>` 조각도 전개되므로 조각의 테이블 상속(`src_indexer`의 `resolve()`)이 렌더링 결과로 해결된다.

1. `parse_mapper.py`: `_extract_tables()`를 어댑터 호출로 교체(CTE 제외, 쓰기 대상 포함). `"_" in n` 필터는 제거하되, 파싱 실패 문장은 기존 정규식으로 폴백한다. `mapper_index`의 컬럼 구성은 유지한다(`page_schema`, `mapper_verify` 호환). 필요하면 쓰기/읽기 구분 컬럼은 후속으로 추가.
2. `src_indexer.parse_mappers`: `st.tables`, `st.ctes`, `st.functions` 계산을 어댑터로 교체한다. 호출 경로 색인 형식(`Statement` 필드, 출력 md)은 바꾸지 않는다.
3. `analysis/sql.py`: 테이블·CTE 추출과 `_fold_cte_and_section`의 CTE 판별을 어댑터 결과로 교체한다. WHERE 분리는 AST의 `whereClause` 위치(`location`)를 쓰되 출력 문자열 형식은 그대로 둔다. 수정사항021 A-2의 기대 출력(`테이블`/`CTE` 줄)을 만족시킨다.
4. `analysis/model.py`, `events.find_mapper_for_model`: 테이블 탐색을 어댑터 호출로 교체한다.
5. `sql_checker.select_output_names`: `SelectStmt.targetList`의 `ResTarget`(별칭), `ColumnRef`(컬럼명), `FuncCall`(함수명), `A_Star`(`*`면 `None`)로 교체하고 `_mask_sql`, `_depth0_matches`(sql_checker 내부 사용분), 별칭 휴리스틱을 제거한다. `sql_porter`가 `_depth0_matches`를 import하므로 **그 함수는 삭제하지 않고** 남긴다.
6. mapper 로더 통합은 이번 단계에서 하지 않는다(범위 초과). 대신 위 1~2번이 모두 같은 어댑터를 쓰게 해서 결과만 일치시킨다.

**제외 (후속 과제)**: `sql_porter`는 SQL을 재작성하는 코드라 위험이 커서 이번에는 건드리지 않는다(AST의 `location` 기반 부분 교체는 나중에 검토). `sql_drift.normalize_sql_for_drift`는 MyBatis 태그가 섞인 텍스트를 비교하므로 유지한다(렌더링 후 AST 지문 비교는 선택 사항).

### 구현검증
**회귀 방지 절차 (교체 전에 먼저 만든다)**
1. 교체 전 코드로 전체 mapper의 `(namespace.sqlId → 테이블 집합, CTE 집합)` 덤프를 JSON으로 저장한다(스냅샷 A).
2. 교체 후 같은 덤프를 만든다(스냅샷 B).
3. A와 B의 차이를 목록으로 만들어 항목마다 분류한다: ① 오탐 제거(좋음) ② 신규 누락(나쁨) ③ 파싱 실패 폴백. ②가 0이 될 때까지 어댑터를 보강한다. 분류 결과는 CHANGELOG에 요약한다.

**테스트**
- `tests/test_parse_mapper.py`(신규 또는 보강): `EXTRACT(year FROM col_name)`가 테이블로 잡히지 않음, CTE 제외, `UPDATE`/`INSERT INTO`/`DELETE FROM` 대상 포함, `ON CONFLICT DO UPDATE SET`이 테이블로 오인되지 않음.
- `tests/test_analysis.py`: 수정사항021 A-2의 `emp02_others.upsert`(테이블 `emp02_others`, CTE `upsert`), `emp00_trans_info.selectByText`(`emp00`, `org00`이 CTE로 분리, 중복 제거) 기대 출력.
- `tests/test_sql_checker.py`: `select_output_names`의 기존 케이스(`count(*) cnt`, `t.col c`, 캐스트, 함수 호출, `*` → `None`)를 그대로 통과 + 서브쿼리/CASE/`DISTINCT ON` 추가 케이스.
- 기존 전체 테스트(`uv run pytest`) 통과. 실제 ASIS 소스에 의존하는 기존 테스트의 현재 실패 5건(`test_comparator`, `test_events`)은 이번 변경과 무관하게 유지되는지 확인한다.
- 출력 형식 불변 확인: `yunhee analysis sql …`, `index-src` 결과의 기존 문자열을 grep하는 검증 스크립트(수정사항 문서의 `*-check.sh`)가 있다면 다시 돌린다.

### 사용예
사용자 명령은 그대로고, 결과가 정확해진다.
```
$ uv run tools/parse_mapper.py          # mapper_index 재빌드 (CTE/EXTRACT 오탐이 사라진 테이블 목록)
$ yunhee analysis sql emp02_others.upsert
### `emp02_others.upsert` (server/emp/mapper/emp02_others.xml:66)
- **테이블**: emp02_others
- **CTE**: upsert
$ yunhee table --page ast01              # page_schema가 정리된 mapper_index를 사용
```

---

## Step 1. `trace-screen`, `trace-table`

가장 빨리 나오고 활용도가 가장 높다. 기존 색인을 재조합한다.

### 구현내용

**trace-screen `<화면ID>`**
- 입력: 색인 `screens/<클래스>.md`와 `_index.json`, `tools/analysis/{screen,ui,grid}.py`, `events.extract_events_and_methods`.
- 출력 facts: 필드·라벨, 그리드 컬럼, 버튼, 이벤트(En), 호출 RPC/API(ServiceRequest 키), SQL(sqlId), 테이블, 사용 코드 그룹.
- evidence: 항목마다 `파일:줄` 또는 `mapper id`.
- `--side tobe`: `tools/analysis/tobe.py`로 TSX/Java 요약(컴포넌트, API 호출).
- unresolved: 동적으로 만들어지는 서비스 키, 색인에 없는 하위 클래스.

**trace-table `<테이블>`**
- 입력: DBML 스냅샷(`schema_snapshot`), 색인 `tables/<도메인>.md`, Step 0-b의 SQL 파싱.
- 출력 facts: 컬럼·코멘트, 이 테이블을 C/R/U/D 하는 SQL과 화면, 같은 이름의 컬럼을 가진 테이블.
- 행 수·최근 갱신일은 DB 접속이 될 때만(`SELECT`만 허용). 접속 불가 시 `unresolved`.

### 구현검증
- `tests/test_trace_screen.py`, `tests/test_trace_table.py`: 가짜 색인 디렉터리(tmp_path)로 단위 테스트.
- 실제 ASIS 소스가 있으면 `Emp00_Tab_TransInfo` 같은 기존 검증 화면으로 `analysis screen`/`events` 결과와 필드·버튼·이벤트 수가 일치하는지 대조(없으면 skip).
- `trace-table`의 C/R/U/D 분류를 `mapper_index`와 Step 0-b 스모크의 결과로 샘플 대조한다.
- md/json 구조, `--max` 절단, `--side` 분기 확인.

### 사용예
```
$ yunhee trace-screen Fnd01_Tab_FundSearch
## facts
- 버튼: 조회(E1), 저장(E2), 삭제(E3)
- 그리드: 펀드목록 (펀드코드, 펀드명, 상태)
- SQL: fnd01_fund.selectList, fnd01_fund.update
- 테이블: fnd01_fund(R,U), sys05_code(R)
## evidence
- Fnd01_Tab_FundSearch.java:142 (E1 handler)
- mapper/fnd01_fund.xml:23 (selectList)
## unresolved
- Fnd01_Tab_FundSearch.java:210 서비스 키가 변수로 구성됨

$ yunhee trace-table fnd01_fund --side asis -o json   # 키: command, side, facts, evidence, unresolved
```

---

## Step 2. `trace-branch`, `trace-flow`

규칙 파악의 핵심이다.

### 구현내용

**trace-branch `<화면ID|클래스|mapper id>`**
- 화면/클래스: 이벤트 핸들러의 if/switch/throw(`events.extract_if_condition`, `events.detect_condition`), validator, 버튼 활성 조건.
- mapper id: Step 0-b의 분기별 변형에서 `<if test>`, `<choose>`, CASE WHEN을 목록화.
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

### 사용예
```
$ yunhee trace-flow Fnd01_Tab_FundSearch --event E3
## facts
- E3 삭제 버튼 → onDelete() → fnd01.FundService.delete → fnd01_fund.delete → fnd01_fund(D)
## evidence
- Fnd01_Tab_FundSearch.java:188, FundService.java:57, mapper/fnd01_fund.xml:140

$ yunhee trace-branch fnd01_fund.selectList
## facts
- <if test="stat != null"> (mapper/fnd01_fund.xml:31)
- CASE WHEN use_yn = 'Y' ... (mapper/fnd01_fund.xml:35)
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

### 사용예
```
$ yunhee trace-pair Fnd01_Tab_FundSearch
## facts
- fnd01_fund.selectList ↔ FundMapper.selectList (근거: 같은 mapper id, 같은 테이블)
- 저장 버튼(E2) ↔ FundPage.tsx handleSave (근거: 이름 유사 — 약함)

$ yunhee trace-diff fnd01_fund.selectList --sql
$ yunhee trace-gap --domain fnd
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

### 사용예
```
$ yunhee trace-rule add Fnd01_Tab_FundSearch --note "삭제는 상태가 N일 때만 가능" 
$ yunhee trace-rule list Fnd01_Tab_FundSearch
$ yunhee trace-rule verify
## facts
- R-001 OK
- R-002 STALE (mapper/fnd01_fund.xml:140 내용이 바뀜)
- R-003 MISSING (Fnd09_Tab_Report.java:77 줄이 없음)

$ yunhee trace-state fnd01_fund.stat_cd
$ yunhee trace-doc fnd
```

---

## Step 5. 나머지 8개

| 명령 | 구현내용 | 구현검증 | 사용예 |
|---|---|---|---|
| `trace-map [--domain]` | 색인 `_index.json`을 도메인별로 집계: 화면 수, 테이블 수, ASIS↔TOBE 매핑 상태(TOBE 소스 존재 여부, `drift` baseline) | 가짜 색인으로 도메인 집계, `--domain` 필터 | `yunhee trace-map --domain fnd` |
| `trace-menu [<경로>]` | 색인 `menus.md`의 메뉴 트리 → ASIS 화면 클래스 → TOBE 화면/API | 경로 일부로 검색, 매핑 없는 메뉴는 `unresolved` | `yunhee trace-menu "시스템관리 > 권한관리"` |
| `trace-column <테이블.컬럼>` | Step 0-b로 이 컬럼을 읽는/쓰는/WHERE에 쓰는 SQL, 표시 화면 라벨. 값 분포는 DB 접속 시만(`SELECT`, 상한 있음) | 존재하지 않는 컬럼 안내, DB 미접속 시 `unresolved` | `yunhee trace-column fnd01_fund.stat_cd` |
| `trace-code <코드그룹>` | 공통 코드 테이블의 값·명칭, 사용처(콤보 정의, SQL 리터럴, Java/TS 상수 비교) | 가짜 코드/사용처 샘플, 코드 테이블 위치 설정(`config`) 확인 | `yunhee trace-code USE_YN` |
| `trace-crud [--domain\|--screen\|--table]` | Step 0-b 결과로 화면×테이블 CRUD 매트릭스. 필터 조합 지원 | 단일/복합 필터, 행·열 상한 `--max` | `yunhee trace-crud --domain fnd` |
| `trace-dblogic [<이름>]` | DBML 스냅샷의 function/procedure/trigger 본문, 이를 호출하는 SQL(Step 0-b의 함수 호출) | 이름 없음 → 목록, 이름 있음 → 본문+호출처 | `yunhee trace-dblogic f_create_seq` |
| `trace-term [<단어>]` | 화면 라벨 ↔ 컬럼(코멘트) ↔ 코드명 교차 참조 | 한글/영문 검색, 다중 일치 | `yunhee trace-term 펀드` |
| `trace-guide` | 에이전트용 업무파악 워크플로우 지침 마크다운 (`agent-guide`의 업무파악판). 정적 문서 | 출력에 18개 명령이 모두 언급되는지 테스트 | `yunhee trace-guide` |

---

## 2. 공통 검증 (전 단계)

- `uv run pytest`, `uv run ruff check .` 통과.
- 18개 명령의 `--help`, md/json 3블록 구조, `--max` 절단, `--side` 분기가 계속 통과(`tests/test_trace_stubs.py` 유지·확장).
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
