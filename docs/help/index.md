# yunhee AI Agent Router (진입 가이드)

> 이 문서는 작업 프로젝트(Target)에서 실행 중인 AI 에이전트(Claude CLI, Antigravity CLI, Gemini CLI 등)가 토큰을 최소화하면서 작업을 완벽히 수행할 수 있도록 돕는 **중앙 색인(Router)**입니다.
> 
> 필요할 때 아래의 **상황별 결정 트리**를 보고 해당하는 전문 세부 가이드를 열람(`cat` 또는 파일 읽기 도구)하세요.

---

## 🧭 상황별 결정 트리 (어떤 문서를 읽어야 할까요?)

| 작업 상황 | 권장 명령어 | 상세 가이드 문서 |
| :--- | :--- | :--- |
| **코드 구조 파악 / 특정 줄 읽기** | `yunhee outline`, `yunhee cat` | [`ops-and-log.md`](file:///home/kdy987/work/yunhee-cli/docs/help/ops-and-log.md) |
| **DB 테이블 / 스키마 확인** | `yunhee table`, `yunhee sql`, `yunhee make-dbml` | [`ops-and-log.md`](file:///home/kdy987/work/yunhee-cli/docs/help/ops-and-log.md) |
| **빌드 / 테스트 / 명령 실행** | `yunhee run "<명령>"`, `yunhee last-run` | [`ops-and-log.md`](file:///home/kdy987/work/yunhee-cli/docs/help/ops-and-log.md) |
| **API 스모크 테스트 / 서버 로그** | `yunhee api`, `yunhee log <trace\|req\|errors\|tail>` | [`ops-and-log.md`](file:///home/kdy987/work/yunhee-cli/docs/help/ops-and-log.md) |
| **AS-IS 화면 구조 / 폼 레이아웃 / 그리드 컬럼** | `yunhee analysis <screen\|ui\|grid\|layout>` | [`analysis.md`](file:///home/kdy987/work/yunhee-cli/docs/help/analysis.md) |
| **AS-IS 메서드 로직 / 실행 가능 SQL 전개** | `yunhee analysis <method\|sql\|model\|servlet>` | [`analysis.md`](file:///home/kdy987/work/yunhee-cli/docs/help/analysis.md) |
| **업무 흐름 추적 (메뉴→화면→이벤트→RPC→SQL→DB)** | `yunhee trace-menu`, `trace-screen`, `trace-flow` | [`trace.md`](file:///home/kdy987/work/yunhee-cli/docs/help/trace.md) |
| **테이블 CRUD 매트릭스 / 컬럼 상태 전이 로직** | `yunhee trace-table`, `trace-crud`, `trace-state` | [`trace.md`](file:///home/kdy987/work/yunhee-cli/docs/help/trace.md) |
| **AS-IS ↔ TOBE 비교 / 갭(Gap) 분석** | `yunhee trace-pair`, `trace-diff`, `trace-gap` | [`trace.md`](file:///home/kdy987/work/yunhee-cli/docs/help/trace.md) |
| **AS-IS SQL/CUD → TOBE 매퍼/DTO 코드 생성** | `yunhee port-sql`, `yunhee port-save` | [`migration.md`](file:///home/kdy987/work/yunhee-cli/docs/help/migration.md) |
| **화면 스타일 판별 / AS-IS 원본 변경(Drift) 감지** | `yunhee page-style`, `yunhee drift`, `yunhee sql-check`| [`migration.md`](file:///home/kdy987/work/yunhee-cli/docs/help/migration.md) |

---

## ⚡ 전체 명령어 1줄 요약표

### 1. 코드 탐색 및 일상 개발 (`ops-and-log.md`)
- `outline <paths...>`: 소스 파일·디렉터리의 클래스·메서드 시그니처와 줄 번호를 추출합니다.
- `cat <specs...>`: 파일의 특정 줄 범위(예: `file.java:10-50`)만 핀포인트로 읽어옵니다.
- `table <names...> [--page <PAGE>]`: 스키마 스냅샷에서 지정 테이블 또는 화면 연관 테이블 DBML만 추출합니다.
- `sql [query]`: PostgreSQL 읽기 전용 쿼리 실행 또는 `--rollback` 트랜잭션 시험 실행을 지원합니다.
- `run "<command>"`: 외부 명령을 실행하고 로그를 파일에 격리하며, 성공 시 1줄 / 실패 시 핵심 에러만 요약합니다.
- `last-run` / `runs`: 직전 실행 결과 확인 및 최근 실행 이력 테이블을 표시합니다.
- `api <method> <path>`: 자동 로그인 세션 기반으로 API를 호출하고 응답 요약(상태, 행 수, 키 목록)만 출력합니다.
- `compare <method> <path> --sql <sql_id>`: TOBE 조회 API 응답과 AS-IS SQL 결과를 대조하여 행 수 및 컬럼 커버리지를 검증합니다.
- `log <trace|req|errors|tail>`: 서버 로그에서 trace ID 상세(실행 SQL/파라미터), 최근 요청, 에러 묶음, 접은 흐름을 분석합니다.
- `config` / `value [KEY]`: Target/Source 경로, 브랜치 상태, DB 접속 정보 등 환경 설정을 조회합니다.

### 2. 정적 분석 전문 (`analysis.md`)
- `analysis method <클래스.메서드>`: AS-IS 메서드 본문 요약, 호출 흐름 및 클라이언트/서버 연계 분석
- `analysis sql <namespace.id>`: MyBatis 매퍼 statement 분석 및 파라미터 바인딩 실행 가능 SQL 전개
- `analysis model <모델클래스>`: 화면 모델 속성 → `@Path` 필드 → MyBatis/DB 컬럼 간 매핑 관계 분석
- `analysis grid <클래스>`: ColumnModel 구성 순서, GridType 판정 및 DB 컬럼 부재 검증
- `analysis screen <화면클래스>`: 색인 화면 파일에서 클래스 목록 통계(`--list`)나 특정 절(`--section layout`) 추출
- `analysis ui <화면클래스>`: AS-IS 대비 TOBE 이벤트 구현율 및 단계별 버튼/이벤트/그리드 현황 분석
- `analysis tobe <tobe_경로>`: TOBE 소스 파일(TSX/TS/Java)의 패턴 골격 및 주요 API 호출 요약
- `analysis run [last|run_id]`: 외부 명령 실행 결과 로그에서 stdout/stderr/json 분리 추출
- `analysis save-script <메서드>`: 서버 저장 메서드의 모든 CUD 쓰기 SQL을 파라미터 대입 단일 롤백 스크립트로 생성
- `analysis servlet <서블릿클래스>`: 서블릿 클래스 및 fileType 분기 처리 로직 분석

### 3. 업무 파악 및 종합 추적 (`trace.md`)
- `trace-map`: 업무 영역별 화면 수, 테이블 수, 매핑 진행 상태 요약
- `trace-menu [menu_path]`: AS-IS 메뉴 트리 구조 → 화면 클래스 → TOBE 화면/API 연계 경로 추적
- `trace-screen <screen_id>`: 단일 화면의 종합 팩트시트(라벨, 그리드, 버튼, 이벤트, RPC, SQL, 테이블, DB함수) 추출
- `trace-table <table_name>`: 테이블 컬럼 정보, C/R/U/D SQL, 사용 화면, 동명 컬럼 테이블 추적
- `trace-column <table.column>`: 컬럼을 참조하는 SQL, 표시 라벨, 코드값 분포 추적
- `trace-code <code_group>`: 공통 코드 그룹의 상세 코드값, 명칭, 콤보 및 SQL 리터럴 사용처 추적
- `trace-state <table.column>`: 특정 컬럼에 값을 쓰는 모든 INSERT/UPDATE 문의 대입 값과 조건식(상태 전이 로직) 추적
- `trace-crud`: 화면 × 테이블 × C/R/U/D 매트릭스를 ASIS와 TOBE 나란히 대조 추적
- `trace-flow <screen_id>`: 화면 이벤트(E0~En)부터 핸들러 → 서비스 RPC → 서버 메서드 → SQL → 테이블까지 전체 사슬 추적
- `trace-branch <target>`: 화면 또는 매퍼 SQL 내의 모든 조건 분기(if, switch, `<if test>`, CASE WHEN 등) 지점 추출
- `trace-dblogic [name]`: DB 저장 함수, 프로시저, 트리거 본문과 이를 호출하는 SQL 추적
- `trace-pair <screen_id>`: ASIS 화면과 TOBE 구현체 간 짝지어진 항목 및 매칭 근거 확인
- `trace-diff <target>`: ASIS와 TOBE 간 SQL 정규화 diff, 조건 분기 대응표, UI 필드/버튼 대응표 대조
- `trace-gap`: ASIS에만 있거나 TOBE에만 있는 요소, 아직 추적되지 않은 누락 지점(Gap) 분석
- `trace-rule <action> [target]`: 마이그레이션 규칙을 저장·조회하고 근거의 정합성을 검증 (`verify` 등)
- `trace-term [term]`: 화면 라벨, DB 컬럼명, 공통 코드명 간의 용어 교차 참조 사전 검색
- `trace-doc <domain>`: 신규 담당자를 위해 카탈로그와 팩트를 체계적인 업무 인수인계 문서 골격으로 자동 조립

### 4. 마이그레이션 코드 생성 및 형상 관리 (`migration.md`)
- `port-sql <sql_id>`: AS-IS MyBatis SQL을 TOBE 매퍼 XML 조각 및 Java 21 Record DTO로 결정적 변환
- `port-save <table> --cols <cols>`: 테이블 스키마 기반으로 명시적인 INSERT/UPDATE/DELETE 및 채번/사이드이펙트 생성
- `mapper-run <target>`: TOBE 매퍼 statement 실행 및 AS-IS SQL 결과 비교
- `sql-check [src_root]`: MyBatis 매퍼 XML의 동적 SQL을 펼쳐 대상 DB에서 EXPLAIN 정합성 및 SQL Drift 검증
- `page-style <targets...>`: 화면 파일(.tsx / .java)의 구조를 정적 분석하여 페이지 스타일 ID(SID) 판별 및 대조
- `events <target>`: AS-IS GXT 화면 파일의 이벤트(E0~En), 메서드 테이블, Grid Spec, 버튼 목록 추출
- `drift [screens...]`: 색인 또는 기준선(baseline) 대비 AS-IS 화면 및 의존 파일의 변경(drift) 감지
