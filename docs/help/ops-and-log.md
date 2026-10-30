# yunhee 개발 일상 및 로그 분석 가이드 (`ops-and-log.md`)

> AI 코딩 어시스턴트가 일상적으로 소스를 탐색하고, 빌드/테스트를 수행하며, API 및 서버 로그를 점검할 때 컨텍스트를 극적으로 절약하는 핵심 도구 모음입니다.

---

## 1. 정적 소스 탐색 (`outline`, `cat`)

### `yunhee outline <paths...>`
소스 파일·디렉터리의 클래스·메서드 시그니처와 줄 번호를 LLM 없이 정적 파싱하여 추출합니다.
- **주요 옵션**:
  - `-m, --members`: interface/type의 필드(멤버) 목록 표시
  - `-s, --symbol <SYM>`: 특정 symbol만 추출
  - `-r, --range <RANGE>`: 특정 줄 번호 범위 출력 (예: `1-50`, `L10-60`)
- **예시**:
  ```bash
  yunhee outline src/main/java/kr/co/kfs/asseterp/biz/sys/service/SysService.java
  yunhee outline frontend/src/api/sys.ts -m
  yunhee outline src/main/resources/mapper/
  ```

### `yunhee cat <specs...>`
지정한 파일들의 줄 범위를 핀포인트로 안전하게 출력합니다.
- **예시**:
  ```bash
  yunhee cat SysService.java:1-35 SysMapper.xml:100-140
  ```

---

## 2. DB 스키마 및 안전 쿼리 (`table`, `sql`, `make-dbml`)

### `yunhee table <names...> [--page <PAGE>]`
스키마 스냅샷에서 지정 테이블(glob 패턴 지원) 또는 화면 연관 테이블 DBML만 추출합니다.
- **예시**:
  ```bash
  yunhee table sys04_role
  yunhee table 'sys0*' 'act01_*'
  yunhee table --page ast01
  ```

### `yunhee sql [query]`
PostgreSQL 읽기 전용 쿼리를 실행하거나 `--rollback` 트랜잭션 격리 하에 시험 실행합니다.
- **주요 옵션**:
  - `--rollback`: 쓰기 문장을 허용하되 반드시 종료 시 ROLLBACK
  - `--scalar`: 첫 행 첫 열 값만 단일 문자열로 출력 (스크립트용)
  - `-o, --output <FORMAT>`: `table`(기본), `tsv`, `csv`, `json`
- **예시**:
  ```bash
  yunhee sql "SELECT count(*) FROM sys01_company" --scalar
  yunhee sql "UPDATE sys04_role SET note='test' WHERE role_cd='ADMIN'" --rollback
  ```

### `yunhee make-dbml [ENV_VAR]` (별칭: `dbml`)
환경변수의 PostgreSQL DB 카탈로그를 추출해 DBML 마크다운 및 JSON 스냅샷으로 저장합니다.
- **예시**: `yunhee make-dbml LOCAL_DB`

---

## 3. 외부 명령 실행 및 에러 압축 (`run`, `last-run`, `runs`)

### `yunhee run "<command>"` (별칭: `exec`)
외부 명령(mvn, gradle, npm, pytest 등)을 실행하고 로그를 파일에 격리하며, 성공 시 1줄 / 실패 시 로컬 Qwen으로 핵심 에러만 10~20줄 요약합니다.
- **주요 옵션**:
  - `-C, --cwd <DIR>`: 실행 작업 디렉터리
  - `-t, --timeout <SEC>`: 실행 타임아웃 (기본: 120초)
  - `--raw`: 요약 없이 원본 출력 그대로 보기
- **예시**:
  ```bash
  yunhee run "mvn compile"
  yunhee run "./gradlew test"
  yunhee run "npm run build"
  ```

### `yunhee last-run` / `yunhee runs`
- `last-run`: 가장 최근 실행 결과 및 에러 요약 재확인
- `runs`: 최근 실행 이력(Run ID, 종료코드, 소요시간, 로그 경로) 테이블 출력

---

## 4. API 스모크 테스트 및 서버 로그 분석 (`api`, `compare`, `log`)

### `yunhee api <method> <path>`
자동 로그인 세션 기반으로 API를 호출하고 응답 요약(HTTP 상태, 행 수, 키 목록)만 2~3줄로 압축 출력합니다.
- **주요 옵션**:
  - `-c, --company <CODE>`: 로그인 회사 코드 (예: `kfstest`)
  - `-t, --tenant <TENANT>`: 테넌트 식별자
  - `-p, --param <key=val>`: 쿼리 파라미터
  - `-b, --body <JSON>`: JSON 요청 본문
  - `--log`: API 호출 직후 서버가 실제로 실행한 SQL 및 파라미터 요약 출력
- **예시**:
  ```bash
  yunhee api GET /api/v1/sys/roles
  yunhee api GET /api/v1/sys/companies -c kfstest -t admin --log
  yunhee api POST /api/v1/sys/roles -b '{"role_cd":"TEST","role_nm":"테스트"}'
  ```

### `yunhee compare <method> <path> --sql <sql_id>`
TOBE 조회 API 응답과 AS-IS SQL 결과를 대조하여 행 수 및 그리드 컬럼 커버리지를 검증합니다.
- **주요 옵션**:
  - `-p, --param-api <key=val>`: API 요청 파라미터 (반복 가능)
  - `--param <key=val>`: AS-IS SQL 파라미터 (반복 가능)
  - `--branch <expr=on|off>`: MyBatis 조건 분기 강제 제어 (반복 가능)
  - `--grid <Screen#method>`: 대조할 화면 클래스 및 그리드 빌더 메서드 지정
  - `-c, --company <CODE>`: 회사 코드 지정 (예: `kfstest`, `admin`)
  - `-t, --tenant <TENANT>`: 테넌트 식별자 지정
  - `-u, --as <ROLE>`: 로그인 계정/역할 지정 (기본: `admin`)
  - `--from-log`: 최근 로그 trace에서 바인딩 파라미터를 읽어 기본값으로 사용
- **검증 및 안전 동작**:
  - **API 오류 즉시 실패**: HTTP 4xx/5xx 또는 `ApiResponse.success=false`인 경우 행 수 비교(`rows=0 ✅`)로 빠지지 않고 즉시 실패(`❌ API 실패...` 또는 `❌ API 업무 오류...`)를 출력하며 종료 코드 1로 종료합니다. trace ID 및 서버 에러 요약이 함께 표시됩니다.
  - **분기 조건식 평가**: `x.equals('lit')`, `.size`, `0L` 등 MyBatis OGNL 조건식을 정밀 평가하며, 평가할 수 없는 분기는 안전하게 기본 OFF(주석 처리)되고 결과 요약에 `(분기 N개 평가 불가)`가 표시됩니다.
- **예시**:
  ```bash
  yunhee compare GET /api/v1/sys/roles --sql sys04_role.selectByName -c kfstest
  yunhee compare GET v1/car/bookings -p date=2026-05-29 -p type=all \
    --sql car03_booking.selectByDate --param companyId=28000 --param startDate=2026-05-29 \
    --param type=all --param personId=-28656 --grid Car03_Tab_DayofMonth
  ```

### `yunhee log <subcommand>`
- `yunhee log trace <trace_id>`: 단일 요청 trace ID의 실행 흐름 요약 및 실행 SQL/바인딩 파라미터 확인 (`--sql` 지원)
- `yunhee log req <method> <path>`: 접근 로그에서 특정 HTTP 메서드/경로 패턴의 최근 요청 검색 (`--trace` 지원)
- `yunhee log errors`: 서버 로그의 WARN/ERROR 묶음 발생 빈도 및 스택 요약 (`--since 1h`, `--explain` 지원)
- `yunhee log tail`: 최근 전체 서버 로그 흐름을 trace 단위로 접어서 요약 출력 (`--since 10m` 지원)

---

## 5. 환경 설정 및 유틸리티 (`config`, `value`, `changelog`, `init`, `intro`)

- `yunhee init`: 현재 작업 디렉터리를 yunhee 프로젝트로 등록 및 필수 폴더/파일(`.yunhee/project.json`, `mcp.json`, `memory.md`, `sessions/`, `runs/`, `.gitignore`) 초기화
- `yunhee config`: 작업 디렉터리(Work Dir), TOBE/ASIS 소스 경로 및 브랜치 상태, DB 접속 정보 등 환경 설정 확인
- `yunhee value [KEY]`: 단일 설정값 텍스트 출력 (`--list` 시 전체 목록, `tobe-src`, `asis-src`, `work-dir` 등 지원)
- `yunhee intro`: yunhee 에이전트 자기소개 및 전문 영역 안내 (`자기소개?` 도 지원)
- `yunhee changelog`: 버전별 변경 이력 및 릴리즈 노트 확인
