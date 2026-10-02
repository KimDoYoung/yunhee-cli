# yunhee 변경 이력

버전을 올릴 때 맨 위에 `## [버전] - YYYY-MM-DD` 항목을 추가한다 (`yunhee changelog`가 이 파일을 읽는다).

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
