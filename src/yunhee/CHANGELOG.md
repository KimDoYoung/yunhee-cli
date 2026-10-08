# yunhee 변경 이력

버전을 올릴 때 맨 위에 `## [버전] - YYYY-MM-DD` 항목을 추가한다 (`yunhee changelog`가 이 파일을 읽는다).

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
