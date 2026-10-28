# yunhee 변경 이력

버전을 올릴 때 맨 위에 `## [버전] - YYYY-MM-DD` 항목을 추가한다 (`yunhee changelog`가 이 파일을 읽는다).

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
