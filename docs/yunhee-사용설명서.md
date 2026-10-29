# yunhee CLI 사용 설명서

> `yunhee`는 상용 AI vibe-coding 도구(Claude CLI, Antigravity CLI, Gemini CLI 등)와 협업할 때 **토큰 사용량을 절약**하기 위해 제작된 독자적인 로컬 agent 보조 CLI입니다.
> 
> 소스 파일 전체를 컨텍스트에 쏟아붓거나 수천 줄의 빌드/테스트 로그를 터미널에 출력하는 대신, 필요한 정보만 정밀하게 압축·추출하여 전달합니다.

---

## 📌 실행 방법

- **개발 환경 (uv 기반)**:
  ```bash
  uv run yunhee <command> [args...]
  ```
- **전역 설치 후 (`uv tool install .`)**:
  ```bash
  yunhee <command> [args...]
  ```
- **대화형 모드 (REPL)**:
  서브커맨드 없이 `yunhee`만 실행하면 프롬프트 대화형 REPL로 진입합니다.

---

## 📑 명령어 빠른 요약표 (1줄 설명)

### 1. 코드 및 시그니처 탐색 (토큰 95% 절약)
| 명령어 | 1줄 설명 |
| :--- | :--- |
| `outline <paths...>` | 소스 파일·디렉터리의 클래스·메서드 시그니처와 줄 번호를 LLM 없이 정적 파싱하여 추출합니다. |
| `cat <specs...>` | 파일의 특정 줄 범위(예: `file.java:10-50`)만 핀포인트로 안전하게 읽어옵니다. |

### 2. DB 스키마 및 DBML 관리 (토큰 90% 절약)
| 명령어 | 1줄 설명 |
| :--- | :--- |
| `make-dbml [ENV_VAR]` | 환경변수의 PostgreSQL DB 카탈로그를 추출해 DBML 마크다운 및 JSON 스냅샷으로 저장합니다. |
| `table <names...> [--page <PAGE>]` | 스키마 스냅샷에서 지정 테이블(패턴 지원) 또는 화면 연관 테이블 DBML만 추출합니다. |
| `sql [query] [-f <file>]` | PostgreSQL 읽기 전용 쿼리를 실행하거나 `--rollback` 트랜잭션 격리 하에 시험 실행합니다. |

### 3. 외부 명령 실행 및 빌드/로그 격리 (토큰 98% 절약)
| 명령어 | 1줄 설명 |
| :--- | :--- |
| `run "<command>"` | 외부 명령을 실행하고 로그를 파일에 격리하며, 성공 시 1줄 / 실패 시 핵심 에러만 요약합니다. |
| `last-run` | 가장 최근에 실행한 외부 명령의 실행 결과, 소요 시간, 실패 원인 요약을 재확인합니다. |
| `runs [-n 10]` | 최근 실행 이력(Run ID, 종료코드, 소요시간, 로그 경로)을 표로 출력합니다. |

### 4. API 스모크 테스트 및 서버 로그 분석 (토큰 95% 절약)
| 명령어 | 1줄 설명 |
| :--- | :--- |
| `api <method> <path>` | 자동 로그인 기반으로 API를 호출하고 응답 요약(HTTP 상태, 행 수, 키 목록)만 출력합니다. |
| `compare <method> <path> --sql <sql_id>` | TOBE 조회 API 응답과 AS-IS SQL 결과를 대조하여 행 수 및 그리드 컬럼 커버리지를 검증합니다. |
| `log trace <trace_id>` | 단일 요청 trace ID의 실행 흐름 요약 및 서버가 실제로 실행한 SQL/바인딩 파라미터 목록을 확인합니다. |
| `log req <method> <path>` | 접근 로그에서 특정 HTTP 메서드/경로 패턴과 일치하는 최근 요청들을 검색합니다. |
| `log errors` | 서버 로그의 WARN/ERROR를 묶어서 발생 빈도 및 핵심 스택 요약을 출력합니다. |
| `log tail` | 최근 전체 서버 로그 흐름을 요청(trace) 단위로 접어서 요약 출력합니다. |

### 5. 마이그레이션 포팅 및 SQL 검증
| 명령어 | 1줄 설명 |
| :--- | :--- |
| `port-sql <sql_id>` | AS-IS MyBatis SQL을 TOBE 매퍼 XML 조각 및 Java 21 Record DTO로 결정적 자동 변환합니다. |
| `port-save <table> --cols <cols>` | 테이블 스키마 기반으로 명시적인 INSERT/UPDATE/DELETE 쿼리 및 채번/사이드이펙트를 생성합니다. |
| `mapper-run <target>` | TOBE MyBatis 매퍼 statement를 직접 실행하고 AS-IS SQL 결과와 비교합니다. |
| `sql-check [src_root]` | MyBatis 매퍼 XML의 동적 SQL을 펼쳐 대상 DB에서 EXPLAIN 정합성 및 SQL Drift를 검증합니다. |

### 6. AS-IS 소스 색인 및 변경 감지 (Drift)
| 명령어 | 1줄 설명 |
| :--- | :--- |
| `index-db [dbml]` | 대용량 DBML 마크다운을 도메인·함수별 소형 파일로 분할 색인하고 암호키를 자동 마스킹합니다. |
| `index-src [src_root]` | AS-IS GXT 소스 호출 경로(화면→서비스→SQL→테이블) 및 UI/이벤트 색인을 빌드합니다. |
| `drift [screens...]` | 소스 색인 또는 기준선(baseline) 대비 AS-IS 화면 및 의존 파일의 변경(drift)을 감지합니다. |
| `events <target>` | AS-IS GXT 화면 파일의 이벤트(E0~En), 메서드 테이블, Grid Spec, 버튼 목록을 추출합니다. |
| `page-style <targets...>` | 화면 파일(.tsx / .java)의 구조를 정적 분석하여 페이지 스타일 ID(SID)를 판별하고 대조합니다. |

### 7. 통합 정적 분석 (`analysis`)
| 명령어 | 1줄 설명 |
| :--- | :--- |
| `analysis method <클래스.메서드>` | AS-IS/TOBE 메서드 본문, 호출 흐름, 클라이언트/서버 연계 요약을 분석합니다. |
| `analysis sql <namespace.id>` | MyBatis 매퍼 statement를 분석하고 파라미터가 대입된 실행 가능 SQL을 전개합니다. |
| `analysis model <모델클래스>` | 화면 모델 속성 → `@Path` 필드 → MyBatis/DB 컬럼 간 매핑 관계를 분석합니다. |
| `analysis grid <클래스>` | ColumnModel 구성 순서, GridType 및 DB 컬럼 부재 여부를 정밀 분석합니다. |
| `analysis screen <화면클래스>` | 화면 색인에서 클래스 목록 통계(`--list`)나 특정 절(`--section layout` 등)을 추출합니다. |
| `analysis ui <화면클래스>` | AS-IS 화면 대비 TOBE 이벤트 구현율 및 단계별 버튼/이벤트/그리드 현황을 분석합니다. |
| `analysis tobe <tobe_경로>` | TOBE 소스 파일의 컴포넌트 골격, 훅, 주요 API 호출 패턴을 요약합니다. |
| `analysis run [last|run_id]` | 외부 명령어 실행 결과 로그에서 stdout/stderr/json/test 통계만 분리 추출합니다. |
| `analysis save-script <메서드>` | 서버 저장 메서드의 모든 CUD 쓰기 SQL을 파라미터 대입 단일 롤백 스크립트로 생성합니다. |
| `analysis servlet <서블릿클래스>` | 서블릿 클래스 및 fileType 분기 처리 로직을 분석합니다. |

### 8. 업무 파악 및 종합 추적 (`trace-*` 계열 18종)
| 명령어 | 1줄 설명 |
| :--- | :--- |
| `trace-map` | 업무 영역별 화면 수, 테이블 수, ASIS↔TOBE 매핑 진행 상태를 요약합니다. |
| `trace-menu [menu_path]` | AS-IS 메뉴 트리 구조 → 화면 클래스 → TOBE 화면/API 연계 경로를 추적합니다. |
| `trace-screen <screen_id>` | 단일 화면의 종합 팩트시트(라벨, 그리드, 버튼, 이벤트, RPC, SQL, 테이블, DB함수)를 추출합니다. |
| `trace-table <table_name>` | 특정 테이블의 컬럼 정보, C/R/U/D SQL, 사용 화면(ASIS/TOBE), 동명 컬럼 테이블을 추적합니다. |
| `trace-column <table.column>` | 특정 컬럼을 읽기/쓰기/조건(WHERE)으로 참조하는 SQL, 화면 라벨, 코드값 분포를 추적합니다. |
| `trace-code <code_group>` | 공통 코드 그룹의 상세 코드값, 명칭, 소스 내 콤보/SQL 리터럴 사용처를 추적합니다. |
| `trace-state <table.column>` | 특정 컬럼에 값을 쓰는 모든 INSERT/UPDATE 문의 대입 값과 조건식(상태 전이 로직)을 추적합니다. |
| `trace-crud` | 화면 × 테이블 × C/R/U/D 매트릭스를 ASIS와 TOBE 나란히 대조하여 매핑 상태를 추적합니다. |
| `trace-flow <screen_id>` | 화면 이벤트(E0~En)부터 핸들러 → 서비스 RPC → 서버 메서드 → SQL → 테이블까지 전체 실행 체인을 추적합니다. |
| `trace-branch <target>` | 화면 또는 매퍼 SQL 내의 모든 조건 분기(if, switch, `<if test>`, CASE WHEN 등) 지점을 추출합니다. |
| `trace-dblogic [name]` | DB 함수, 프로시저, 트리거 본문(스냅샷)과 이를 호출하는 SQL을 추적합니다. |
| `trace-pair <screen_id>` | ASIS 화면과 TOBE 구현체 간 짝지어진 항목 및 매칭 근거(주석, 테이블 조합, 명칭)를 확인합니다. |
| `trace-diff <target>` | ASIS와 TOBE 간 SQL 정규화 diff, 조건 분기 대응표, UI 필드/버튼 대응표를 대조합니다. |
| `trace-gap` | ASIS에만 있거나 TOBE에만 있는 요소, 아직 추적되지 않은 마이그레이션 누락 지점(Gap)을 분석합니다. |
| `trace-rule <action> [target]` | 마이그레이션 판정 규칙 및 근거를 저장/조회/검증(`add`/`list`/`show`/`update`/`verify`)합니다. |
| `trace-term [term]` | 화면 라벨, DB 컬럼명/코멘트, 공통 코드명 간의 용어 교차 참조 사전을 검색합니다. |
| `trace-doc <domain>` | 신규 담당자를 위해 카탈로그와 팩트를 체계적인 업무 인수인계 문서 골격으로 자동 조립합니다. |
| `trace-guide` | 에이전트를 위한 trace-* 기반 업무 파악 표준 워크플로우 지침을 출력합니다. |

### 9. 기본 LLM/임베딩 및 환경 설정
| 명령어 | 1줄 설명 |
| :--- | :--- |
| `ask <prompt>` | 로컬 LLM(Qwen2.5-Coder:14B)에게 단발성 질문을 전달하고 답변을 출력합니다. |
| `vec <text>` | 입력한 텍스트의 bge-m3 임베딩 벡터 차원 및 앞부분 값을 확인합니다. |
| `index <text>` | 텍스트를 로컬 ChromaDB 벡터스토어에 색인 저장합니다. |
| `search <query> [-n 3]` | ChromaDB에 저장된 텍스트 중 유사한 문서를 벡터 검색합니다. |
| `config` | 작업 경로, AS-IS 소스 경로, 소스 브랜치 동기화 상태, DB 정보 등 현재 환경을 확인합니다. |
| `value [KEY]` | 특정 설정 키의 현재 값을 단일 텍스트로 출력하거나 전체 설정 목록을 확인합니다. |
| `changelog [version]` | 버전별 변경 이력 및 릴리즈 노트를 출력합니다. |
| `agent-guide` | 상용 AI 에이전트의 토큰 절약을 위한 행동 지침서(Markdown)를 출력합니다. |

---

## 🔍 명령어별 상세 사용법 및 예시

### 1. 코드 및 시그니처 탐색

#### `yunhee outline <paths...>`
- **설명**: 소스 파일·디렉터리의 클래스·메서드 시그니처와 줄 번호를 LLM 없이 정적 파싱하여 추출합니다.
- **주요 옵션**:
  - `-m, --members`: interface/type의 필드(멤버) 목록까지 함께 표시
  - `-s, --symbol <SYMBOL>`: 특정 symbol(인터페이스, 타입, 함수 등)만 필터링
  - `-r, --range <RANGE>`: 특정 줄 번호 범위 출력 (예: `1-50`, `L10-60`)
  - `--tail <N>`: 파일의 마지막 N줄 원문 함께 출력
  - `--limit <CHARS>`: 최대 글자 수 예산 제한 (기본: 30000)
- **예시**:
  ```bash
  yunhee outline src/main/java/kr/co/kfs/asseterp/biz/sys/service/SysService.java
  yunhee outline frontend/src/api/sys.ts -m
  yunhee outline src/main/resources/mapper/
  ```

#### `yunhee cat <specs...>`
- **설명**: 파일의 특정 줄 범위(예: `file.java:10-50`)만 핀포인트로 안전하게 읽어옵니다.
- **주요 옵션**:
  - `--no-number`: 줄 번호 표시 생략
- **예시**:
  ```bash
  yunhee cat SysService.java:1-35 SysMapper.xml:100-140
  ```

---

### 2. DB 스키마 및 DBML 관리

#### `yunhee make-dbml [ENV_VAR]` (별칭: `dbml`)
- **설명**: 환경변수의 PostgreSQL DB 카탈로그를 추출해 DBML 마크다운 및 JSON 스냅샷으로 저장합니다.
- **주요 옵션**:
  - `-o, --output <PATH>`: 출력 파일 경로 지정
  - `--schema <SCHEMA>`: 대상 스키마 지정 (반복 가능, 기본: public)
- **예시**:
  ```bash
  yunhee make-dbml LOCAL_DB
  ```

#### `yunhee table <names...> [--page <PAGE>]`
- **설명**: 스키마 스냅샷에서 지정 테이블(패턴 지원) 또는 화면 연관 테이블 DBML만 추출합니다. (stdout은 순수 DBML만 출력)
- **주요 옵션**:
  - `--page <PAGE_CODE>`: AS-IS 페이지 코드 (해당 페이지 매퍼가 참조하는 테이블 전체 추출)
  - `--db <DB_ENV>`: 스키마 스냅샷 환경 이름 (기본: `LOCAL_DB`)
- **예시**:
  ```bash
  yunhee table sys04_role
  yunhee table 'sys0*' 'act01_*'
  yunhee table --page ast01
  ```

#### `yunhee sql [query]`
- **설명**: PostgreSQL 읽기 전용 쿼리를 실행하거나 `--rollback` 트랜잭션 격리 하에 시험 실행합니다.
- **주요 옵션**:
  - `-f, --file <PATH>`: 실행할 SQL 파일 경로
  - `--rollback`: 쓰기(INSERT/UPDATE/DELETE)를 허용하되 트랜잭션 종료 시 반드시 ROLLBACK
  - `-o, --output <FORMAT>`: 출력 형식 (`table`, `tsv`, `csv`, `json`)
  - `--scalar`: 첫 행 첫 열 값만 단일 문자열로 출력 (스크립트 변수 할당용)
  - `--var <KEY=VAL>`: 변수 바인딩 (psql 스타일 `\gset` 지원)
  - `-c, --db <DB>`: 접속할 대상 DB 환경변수명 또는 URL (기본: `YUNHEE_DB`)
- **예시**:
  ```bash
  yunhee sql "SELECT count(*) FROM sys01_company" --scalar
  yunhee sql "UPDATE sys04_role SET note='test' WHERE role_cd='ADMIN'" --rollback
  ```

---

### 3. 외부 명령 실행 및 빌드/로그 격리

#### `yunhee run "<command>"` (별칭: `exec`)
- **설명**: 외부 명령을 실행하고 로그를 파일에 격리하며, 성공 시 1줄 / 실패 시 핵심 에러만 요약합니다.
- **주요 옵션**:
  - `-C, --cwd <DIR>`: 명령어를 실행할 작업 디렉터리
  - `-t, --timeout <SEC>`: 실행 타임아웃 초 (기본: 120초)
  - `--no-llm`: 실패 시 로컬 Qwen 요약을 건너뛰고 기본 에러 출력
  - `--raw`: 요약 없이 원본 stdout/stderr 그대로 출력
  - `--health / --no-health`: 배포 명령 실행 후 기동 완료/실패 자동 헬스체크
- **예시**:
  ```bash
  yunhee run "mvn compile"
  yunhee run "./gradlew test"
  yunhee run "npm run build"
  ```

#### `yunhee last-run`
- **설명**: 가장 최근에 실행한 외부 명령의 실행 결과, 소요 시간, 실패 원인 요약을 재확인합니다.
- **예시**:
  ```bash
  yunhee last-run
  ```

#### `yunhee runs`
- **설명**: 최근 실행 이력(Run ID, 종료코드, 소요시간, 로그 경로)을 표로 출력합니다.
- **주요 옵션**:
  - `-n, --limit <N>`: 표시할 최근 실행 수 (기본: 10)
- **예시**:
  ```bash
  yunhee runs -n 5
  ```

---

### 4. API 스모크 테스트 및 서버 로그 분석

#### `yunhee api <method> <path>`
- **설명**: 자동 로그인 기반으로 API를 호출하고 응답 요약(HTTP 상태, 행 수, 키 목록)만 출력합니다.
- **주요 옵션**:
  - `-u, --as <ROLE>`: 로그인 계정/역할 (기본: `admin`)
  - `-c, --company <CODE>`: 로그인 시 전달할 회사 코드 (예: `admin`, `kfstest`)
  - `-t, --tenant <TENANT>`: 테넌트 식별자 (세션 분리)
  - `-p, --param <KEY=VAL>`: 쿼리 파라미터 (반복 가능)
  - `-b, --body <JSON>`: JSON 요청 본문
  - `--log`: API 호출 직후 서버가 실제로 실행한 SQL 및 파라미터 요약 출력
  - `--raw`: 압축 요약 대신 원본 JSON 본문 출력
- **예시**:
  ```bash
  yunhee api GET /api/v1/sys/roles
  yunhee api GET /api/v1/sys/companies -c kfstest -t admin --log
  yunhee api POST /api/v1/sys/roles -b '{"role_cd":"TEST","role_nm":"테스트"}'
  ```

#### `yunhee compare <method> <path> --sql <sql_id>`
- **설명**: TOBE 조회 API 응답과 AS-IS SQL 결과를 대조하여 행 수 및 그리드 컬럼 커버리지를 검증합니다.
- **주요 옵션**:
  - `--sql <SQL_ID>`: 비교 대상 AS-IS SQL ID (예: `sys01_company.selectByName`)
  - `-p, --param-api <KEY=VAL>`: API 쿼리 파라미터
  - `--param <KEY=VAL>`: SQL 파라미터
  - `--grid <CLASS>`: 대조할 화면/그리드 클래스 (컬럼 커버리지 검증)
- **예시**:
  ```bash
  yunhee compare GET /api/v1/sys/roles --sql sys04_role.selectByName -c kfstest
  ```

#### `yunhee log <subcommand>`
- **설명**: 서버 로그 분석 및 요청·SQL·에러 요약 서브커맨드 모음입니다.
- **서브커맨드**:
  - `yunhee log trace <trace_id>`: 단일 요청 trace ID의 실행 흐름 요약 및 실행 SQL/바인딩 파라미터 확인 (`--sql` 지원)
  - `yunhee log req <method> <path>`: 접근 로그에서 특정 HTTP 메서드/경로 패턴의 최근 요청 검색 (`--trace` 지원)
  - `yunhee log errors`: 서버 로그의 WARN/ERROR 묶음 발생 빈도 및 스택 요약 (`--since 1h`, `--explain` 지원)
  - `yunhee log tail`: 최근 전체 서버 로그 흐름을 trace 단위로 접어서 요약 출력 (`--since 10m`, `--level WARN` 지원)

---

### 5. 마이그레이션 포팅 및 SQL 검증

#### `yunhee port-sql <sql_id>`
- **설명**: AS-IS MyBatis SQL을 TOBE 매퍼 XML 조각 및 Java 21 Record DTO로 결정적 자동 변환합니다.
- **주요 옵션**:
  - `--cols <COLS>`: 추출할 컬럼 목록 (쉼표 구분)
  - `--getter-defaults`: AS-IS 모델 getter null 기본값을 COALESCE로 적용
  - `--package <PKG>`: 생성될 DTO 패키지명 (resultType FQN에 사용)
  - `--raw`: 원본 SQL을 그대로 `#{var}` 치환하여 CDATA `<sql id>`로 출력
- **예시**:
  ```bash
  yunhee port-sql sys04_role.selectByName --package kr.co.kfs.asseterp.biz.sys.dto
  ```

#### `yunhee port-save <table> --cols <cols>`
- **설명**: 테이블 스키마 기반으로 명시적인 INSERT/UPDATE/DELETE 쿼리 및 채번/사이드이펙트를 생성합니다.
- **주요 옵션**:
  - `--cols <COLS>`: INSERT/UPDATE 대상 컬럼 목록
  - `--insert-cols <COLS>`: INSERT에만 포함할 컬럼 목록 (UPDATE SET 제외)
  - `--company-col <COL>`: 회사 ID 컬럼명
  - `--id-col <COL>`: PK ID 컬럼명
- **예시**:
  ```bash
  yunhee port-save sys04_role --cols role_cd,role_nm,seq,note --id-col role_id
  ```

#### `yunhee mapper-run <target>`
- **설명**: TOBE MyBatis 매퍼 statement를 직접 실행하고 AS-IS SQL 결과와 비교합니다.
- **주요 옵션**:
  - `-p, --param <KEY=VAL>`: 매퍼 파라미터
  - `--compare <ASIS_SQL_ID>`: 비교할 AS-IS SQL ID
  - `--rollback`: 트랜잭션 실행 후 롤백 (쓰기 쿼리 검증용)
  - `--count`: 행 수만 출력
- **예시**:
  ```bash
  yunhee mapper-run backend/src/main/resources/mapper/SysRoleMapper.xml#selectRoles -p roleName=관리자
  ```

#### `yunhee sql-check [src_root]`
- **설명**: MyBatis 매퍼 XML의 동적 SQL을 펼쳐 대상 DB에서 EXPLAIN 정합성 및 SQL Drift를 검증합니다.
- **주요 옵션**:
  - `--tobe <DIR>`: TOBE 매퍼 디렉터리 경로 (TOBE SQL 정합성 및 Record DTO 검증 모드)
  - `--old <DIR> --new <DIR>`: 이전 소스와 새 소스 간 SQL Drift 검증 모드
  - `--changed`: git 변경된 매퍼 XML만 검증
- **예시**:
  ```bash
  yunhee sql-check ~/workspace26/Asset-OMS --db asseterpdb
  yunhee sql-check --tobe src/main/resources/mapper --changed
  ```

---

### 6. AS-IS 소스 색인 및 변경 감지 (Drift)

#### `yunhee index-db [dbml]`
- **설명**: 대용량 DBML 마크다운을 도메인·함수별 소형 파일로 분할 색인하고 암호키를 자동 마스킹합니다.
- **주요 옵션**:
  - `-t, --target <DIR>`: 색인 출력 폴더 (기본: `docs/as-is/db`)
- **예시**:
  ```bash
  yunhee index-db .yunhee/LOCAL_DB-dbml.md -t docs/as-is/db
  ```

#### `yunhee index-src [src_root]`
- **설명**: AS-IS GXT 소스 호출 경로(화면→서비스→SQL→테이블) 및 UI/이벤트 색인을 빌드합니다.
- **주요 옵션**:
  - `-t, --target <DIR>`: 색인 출력 폴더 (기본: `docs/as-is/src`)
  - `--events / --no-events`: 화면 파일에 이벤트/메서드/그리드스펙/버튼 포함 여부
  - `--menus <PATH>`: 메뉴 TSV 파일 경로 (미지정 시 자동 탐색)
- **예시**:
  ```bash
  yunhee index-src ~/workspace26/Asset-OMS -t docs/as-is/src
  ```

#### `yunhee drift [screens...]`
- **설명**: 소스 색인 또는 기준선(baseline) 대비 AS-IS 화면 및 의존 파일의 변경(drift)을 감지합니다.
- **주요 옵션**:
  - `--all`: 색인된 전체 화면 검사
  - `--base <BASE>`: 비교 기준 (`index`, `baseline`, `prev-index`, `<커밋해시>`)
  - `--done-only`: 완성 기준선(baseline)에 등록된 화면만 검사
  - `--record`: 특정 화면의 현재 색인 기준을 완성 기준선(baseline)으로 기록
  - `-o, --output <FORMAT>`: 출력 형식 (`table`, `diff`, `full`, `json`)
- **예시**:
  ```bash
  yunhee drift --all --base baseline --done-only
  yunhee drift Sys01_Tab_Company -o diff
  yunhee drift --record Sys01_Tab_Company --id A01
  ```

#### `yunhee events <target>`
- **설명**: AS-IS GXT 화면 파일의 이벤트(E0~En), 메서드 테이블, Grid Spec, 버튼 목록을 추출합니다.
- **주요 옵션**:
  - `--ids`: E-id 목록 및 트리 구조만 간단히 출력
  - `--json`: JSON 구조로 출력
- **예시**:
  ```bash
  yunhee events src/main/java/.../Sys01_Tab_Company.java
  yunhee events Sys01_Tab_Company --ids
  ```

#### `yunhee page-style <targets...>`
- **설명**: 화면 파일(.tsx / .java)의 구조를 정적 분석하여 페이지 스타일 ID(SID: SG, SGP, SGVF, SGEF, SGTP, SGT, TG, GG, CG)를 판별하고 대조합니다.
- **주요 옵션**:
  - `-c, --compare`: AS-IS Java와 TOBE TSX의 스타일 일치 여부 비교
  - `-a, --all [DIR]`: 디렉터리 내 모든 화면의 스타일 판별 및 분포 요약
  - `--json`: 판별 특징 및 근거 JSON 출력
- **예시**:
  ```bash
  yunhee page-style Fnd01_Tab_FundSearch.tsx
  yunhee page-style --compare Fnd01_Tab_FundSearch.java Fnd01_Tab_FundSearch.tsx
  yunhee page-style --all frontend/src/pages
  ```

---

### 7. 통합 정적 분석 (`yunhee analysis <type> <target>`)

- **형식**: `yunhee analysis <type> <target> [options...]`
- **전체 유형 목록 조회**: `yunhee analysis --list`

| Type | 대상 (Target) | 1줄 설명 및 주요 옵션 | 예시 |
| :--- | :--- | :--- | :--- |
| **`method`** | `<클래스>.<메서드>` | AS-IS/TOBE 메서드 본문 요약, 호출 흐름 및 클라이언트/서버 연계 분석 (`--raw`, `--follow`, `--all-overloads`) | `yunhee analysis method Emp03_TabPage_Detail.saveDetail` |
| **`sql`** | `<ns.id>` | MyBatis 매퍼 statement 분석 및 파라미터가 바인딩된 실행 가능 SQL 전개 (`--param key=val`, `--count`, `--no-cte`) | `yunhee analysis sql emp00_trans_info.selectByText --param text=홍길동` |
| **`model`** | `<모델클래스>` | 화면 모델 속성 → `@Path` 필드 → MyBatis/DB 컬럼 간 매핑 관계 분석 (`--sql <SQL_ID>`) | `yunhee analysis model Sys05_UserRole --sql sys05_user_role.selectList` |
| **`grid`** | `<클래스>[.필드]` | 그리드 ColumnModel 순서, GridType 판정 및 DB 컬럼 부재 검증 (`--method <MET>`, `--check-columns`) | `yunhee analysis grid Org00_Lookup_Fund` |
| **`screen`** | `<화면클래스>` | 색인 화면 파일에서 클래스 목록 통계(`--list`)나 특정 절(`--section layout\|ui\|methods\|tables`) 추출 | `yunhee analysis screen Emp00_Tab_TransInfo --list`<br>`yunhee analysis screen Emp00_Tab_TransInfo --section layout` |
| **`ui`** | `<화면클래스>` | UI 대조표 및 단계별 버튼/이벤트/그리드 구현 현황 분석 (`--done`, `--later`, `--layout`) | `yunhee analysis ui Emp00_Tab_TransInfo --done Emp00_Tab_TransInfo` |
| **`tobe`** | `<TOBE 파일·폴더>` | TOBE 소스 파일(TSX/TS/Java)의 패턴 골격 및 주요 API 호출 요약 | `yunhee analysis tobe frontend/src/pages/sys/SysRole.tsx` |
| **`run`** | `last` 또는 `<run_id>` | 외부 명령어 실행 결과 로그에서 필요한 부분만 분리 추출 (`--stdout`, `--stderr`, `--json`, `--tests`) | `yunhee analysis run last --stderr`<br>`yunhee analysis run last --stdout -n 50` |
| **`save-script`** | `<ns.Class.method>` | 서버 저장 메서드의 쓰기 SQL들을 파라미터 대입 단일 롤백 스크립트로 생성 (`--param key=val`) | `yunhee analysis save-script apr.Apr90_Disposal.save --param disposalCode=D01` |
| **`servlet`** | `<서블릿클래스>` | 서블릿 클래스 및 fileType 분기 처리 로직 분석 (`--type <FILE_TYPE>`) | `yunhee analysis servlet FileDownload --type apprList` |

---

### 8. 업무 파악 및 종합 추적 (`yunhee trace-*` 계열 18종)

> **공통 옵션**:
> - `-o, --format <FORMAT>`: 출력 형식 (`md` 기본, `json`)
> - `--side <asis|tobe|both>`: 분석 대상 (기본: `both`)
> - `--max <N>`: 출력 항목 상한
> - `--tobe <DIR>`: TOBE 프로젝트 루트 (기본: 작업 폴더)
> - `--src <DIR>`: AS-IS 소스 루트 (기본: `YUNHEE_ASIS_SRC_DIR`)

| 명령어 | 인자 및 형식 | 1줄 설명 | 예시 |
| :--- | :--- | :--- | :--- |
| **`trace-map`** | `[-d, --domain <도메인>]` | 업무 영역별 화면 수, 테이블 수, ASIS↔TOBE 매핑 상태를 요약합니다. | `yunhee trace-map -d sys` |
| **`trace-menu`** | `[menu_path]` | 메뉴 트리 구조 → ASIS 화면 클래스 → TOBE 화면/API 연계 경로를 추적합니다. | `yunhee trace-menu "조직 및 사원관리 > 사원정보"`<br>`yunhee trace-menu '#1029'` |
| **`trace-screen`** | `<screen_id>` | 단일 화면의 종합 팩트시트(라벨, 그리드, 버튼, 이벤트, RPC, SQL, 테이블, DB함수)를 추출합니다. | `yunhee trace-screen Emp00_Tab_TransInfo`<br>`yunhee trace-screen '#1029'` |
| **`trace-table`** | `<table_name>` | 테이블의 컬럼 정보, C/R/U/D SQL, 사용 화면(ASIS/TOBE), 동명 컬럼 테이블을 추적합니다. (`--stats` 지원) | `yunhee trace-table sys06_menu`<br>`yunhee trace-table apr01_appr --stats` |
| **`trace-column`** | `<table.column>` | 특정 컬럼을 읽기/쓰기/WHERE로 참조하는 SQL, 표시 라벨, 코드값 분포를 추적합니다. (`--stats` 지원) | `yunhee trace-column apr01_appr.apr01_status_cd --stats` |
| **`trace-code`** | `<code_group>` | 공통 코드 그룹의 상세 코드값, 명칭, 콤보 및 SQL 리터럴 사용처를 추적합니다. | `yunhee trace-code AprStatusCode` |
| **`trace-state`** | `<table.column>` | 특정 컬럼에 값을 쓰는 모든 INSERT/UPDATE 문의 대입 값과 조건식(상태 전이 로직)을 추적합니다. | `yunhee trace-state apr01_appr.apr01_status_cd` |
| **`trace-crud`** | `[-d <도메인>] [-s <화면>] [-t <테이블>]` | 화면 × 테이블 × C/R/U/D 매트릭스를 ASIS와 TOBE 나란히 대조하여 매핑 상태를 추적합니다. | `yunhee trace-crud -d emp`<br>`yunhee trace-crud -s Emp00_Tab_TransInfo` |
| **`trace-flow`** | `<screen_id> [-e <이벤트ID>]` | 화면 이벤트(E0~En)부터 핸들러 → 서비스 RPC → 서버 메서드 → SQL → 테이블까지 전체 실행 체인을 추적합니다. | `yunhee trace-flow Emp00_Tab_TransInfo -e E3` |
| **`trace-branch`** | `<target>` | 화면 또는 매퍼 SQL 내의 모든 조건 분기(if, switch, `<if test>`, CASE WHEN 등) 지점을 추출합니다. | `yunhee trace-branch Emp00_Tab_TransInfo`<br>`yunhee trace-branch emp00_trans_info.selectByText` |
| **`trace-dblogic`** | `[name]` | DB 저장 함수, 프로시저, 트리거 본문(스냅샷)과 이를 호출하는 SQL을 추적합니다. | `yunhee trace-dblogic f_cdnm`<br>`yunhee trace-dblogic` |
| **`trace-pair`** | `<screen_id>` | ASIS 화면과 TOBE 구현체 간 짝지어진 항목 및 매칭 근거(주석, 테이블 조합, 명칭)를 확인합니다. | `yunhee trace-pair Emp00_Tab_TransInfo` |
| **`trace-diff`** | `<target>` | ASIS와 TOBE 간 SQL 정규화 diff, 조건 분기 대응표, UI 필드/버튼 대응표를 대조합니다. (`--sql`, `--branch`, `--ui`) | `yunhee trace-diff '#1029'`<br>`yunhee trace-diff emp00_trans_info.selectByText --sql` |
| **`trace-gap`** | `[-d <도메인>]` | ASIS에만 있거나 TOBE에만 있는 요소, 아직 추적하지 못한 지점(Gap)을 분석합니다. | `yunhee trace-gap -d emp` |
| **`trace-rule`** | `<action> [target]` | 마이그레이션 규칙을 저장·조회하고 근거 파일/라인의 정합성을 검증합니다. (`action`: add, list, show, update, verify) | `yunhee trace-rule list Emp00`<br>`yunhee trace-rule verify R-001`<br>`yunhee trace-rule add Emp00 --verdict 일치 --note "완료"` |
| **`trace-term`** | `[term]` | 화면 라벨, DB 컬럼명/코멘트, 공통 코드명 간의 용어 교차 참조 사전을 검색합니다. | `yunhee trace-term 성명`<br>`yunhee trace-term 결재` |
| **`trace-doc`** | `<domain>` | 신규 담당자를 위해 카탈로그와 팩트를 체계적인 업무 인수인계 문서 골격으로 자동 조립합니다. | `yunhee trace-doc sys` |
| **`trace-guide`** | `(인자 없음)` | 에이전트를 위한 trace-* 기반 업무 파악 표준 워크플로우 지침을 출력합니다. | `yunhee trace-guide` |

---

### 9. 기본 LLM/임베딩 및 환경 설정

#### `yunhee ask "<prompt>"`
- **설명**: 로컬 LLM(Qwen2.5-Coder:14B)에게 단발성 질문을 전달하고 답변을 출력합니다.
- **예시**:
  ```bash
  yunhee ask "PostgreSQL에서 공통 코드를 관리하는 일반적인 테이블 설계 방식을 요약해줘"
  ```

#### `yunhee vec "<text>"`
- **설명**: 입력한 텍스트의 bge-m3 임베딩 벡터 차원 및 앞부분 값을 확인합니다.
- **예시**:
  ```bash
  yunhee vec "자산운용 ERP 시스템"
  ```

#### `yunhee index "<text>"`
- **설명**: 텍스트를 로컬 ChromaDB 벡터스토어에 색인 저장합니다.
- **예시**:
  ```bash
  yunhee index "sys01_company는 운용사 및 고객 회사 정보를 관리하는 기본 테이블이다."
  ```

#### `yunhee search "<query>" [-n 3]`
- **설명**: ChromaDB에 저장된 텍스트 중 유사한 문서를 벡터 검색합니다.
- **예시**:
  ```bash
  yunhee search "회사 정보 관리" -n 3
  ```

#### `yunhee config`
- **설명**: 작업 경로, AS-IS 소스 경로, 소스 브랜치 동기화 상태, DB 정보 등 현재 환경을 확인합니다.
- **예시**:
  ```bash
  yunhee config
  ```

#### `yunhee value [KEY]`
- **설명**: 특정 설정 키의 현재 값을 단일 텍스트로 출력(스크립트 치환용)하거나 전체 설정 키 목록 테이블을 확인합니다.
- **주요 옵션**:
  - `-l, --list`: 사용 가능한 모든 설정 키 목록 및 현재 값 테이블 표시
  - `-k, --keys`: 설정 키 이름만 한 줄씩 출력 (스크립트/자동완성용)
  - `--raw`: DB URL/비밀번호 등을 마스킹 없이 실제 값 출력
- **예시**:
  ```bash
  yunhee value YUNHEE_ASIS_SRC_DIR
  yunhee value asis-src
  yunhee value --list
  ```

#### `yunhee changelog [version]`
- **설명**: 버전별 변경 이력 및 릴리즈 노트를 출력합니다.
- **주요 옵션**:
  - `--since <VERSION>`: 특정 버전 이후의 모든 변경사항 출력
  - `--all`: 전체 변경 이력 출력
- **예시**:
  ```bash
  yunhee changelog
  yunhee changelog --since 0.1.0
  ```

#### `yunhee agent-guide`
- **설명**: 상용 AI 에이전트(Claude, Antigravity, Gemini 등)의 토큰 절약을 위한 행동 지침서(Markdown)를 출력합니다.
- **예시**:
  ```bash
  yunhee agent-guide
  ```
