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
지정한 파일들의 줄 범위를 핀포인트로 안전하게 출력합니다 (출력 상한 200줄, 초과 시 `… N줄 더 있음 — 범위를 좁히세요` 표시).
- **주요 옵션**:
  - `--head <N>`: 범위(또는 파일) 앞 N줄만 출력
  - `--tail <N>`: 범위(또는 파일) 뒤 N줄만 출력 (`--head`와 동시 지정 불가)
  - `--no-number`: 줄 번호 생략
- **예시**:
  ```bash
  yunhee cat SysService.java:1-35 SysMapper.xml:100-140
  yunhee cat docs/05-작업방법.md --head 20
  yunhee cat docs/08-회차인계.md --tail 3
  yunhee cat frontend/src/types/ast.ts:1200-1292 --tail 5
  ```

### `yunhee grep <pattern> <paths...>`
문맥 출력 전용 안전 grep 도구입니다 (항상 `파일:줄: 내용` 형식 출력, 겹치는 문맥 자동 병합, 호출당 출력 상한 80줄).
- **주요 옵션**:
  - `-C, --context <N>`: 일치 줄 앞뒤 문맥 줄 수 (기본 0, 상한 10)
  - `-A, --after-context <N>`: 일치 줄 뒤 문맥 줄 수 (상한 20)
  - `-B, --before-context <N>`: 일치 줄 앞 문맥 줄 수 (상한 20)
  - `--max, -m <M>`: 최대 일치 건수 (기본 20건, 초과 시 `… 일치 N건 더 있음` 표시)
  - `-F, --fixed-strings`: 정규식 대신 고정 문자열 검색
  - `-i, --ignore-case`: 대소문자 무시
- **예시**:
  ```bash
  yunhee grep 'interface BookFundFee' frontend/src/types/ast.ts -A 12
  yunhee grep import frontend/src -C 3
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
  - `-p, --param <key=val>`: 쿼리 파라미터 (**LIKE용 `%`는 `-p k=%`로 준다**. `%25` 등 이미 `%XX` 인코딩된 값은 이중 인코딩하지 않으며, 문자 그대로 `%25`를 보내야 할 때만 `--raw-param` 사용)
  - `--raw-param`: `-p` 값의 `%XX` 패턴을 디코딩하지 않고 문자 그대로 다시 URL 인코딩
  - `-b, --body <JSON>`: JSON 요청 본문
  - `--log`: API 호출 직후 서버가 실제로 실행한 SQL 및 파라미터 요약 출력
  - `--track <테이블>[,<테이블>]`: 호출 전후 지정 테이블의 행 수 변화 및 새로 생긴 PK(`information_schema` 기준)를 한 줄로 출력 (예: `biz05_relate_appr: 40 → 41 (+1: biz05_relate_appr_id=202611059009067)`, 삭제 시 `41 → 40 (-1)`, 실패 시 `변화 없음`)
- **예시**:
  ```bash
  yunhee api GET /api/v1/sys/roles
  yunhee api GET /api/v1/sys/companies -c kfstest -t admin --log
  yunhee api POST /api/v1/biz/relate-apprs/promo -t admin -c kfstest -b '{"promoId":202204280115828,"apprId":202509189046469}' --track biz05_relate_appr
  yunhee api DELETE /api/v1/biz/relate-apprs -t admin -c kfstest -b '[202611059009067]' --track biz05_relate_appr
  ```

### `yunhee compare <method> <path> --sql <sql_id 또는 dom.Class.method>`
TOBE 조회 API 응답과 AS-IS SQL 결과를 대조하여 행 수 및 그리드 컬럼 커버리지를 검증합니다 (`--sql`에 매퍼 ID뿐 아니라 서비스 이름 `dom.Class.method`도 그대로 줄 수 있습니다).
- **주요 옵션**:
  - `-p, --param-api <key=val>`: API 요청 파라미터 (반복 가능, **LIKE용 `%`는 `-p k=%`로 준다**)
  - `--raw-param`: `-p` 값의 `%XX` 패턴을 디코딩하지 않고 문자 그대로 다시 URL 인코딩
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

### `yunhee screen-capture <screen_id> [login=<company>/<user>/<pw>]`
Headless Chromium(Playwright)으로 TOBE 프론트엔드에 자동 로그인하고(겸직선택 `Emp04_Lookup_AddTitleList` 자동 탐색·통과 포함), 대상 화면을 열어 **초기 화면 → [조회] 클릭 → 첫 행 선택 → 서브 탭 전환 → 팝업/Lookup 모달 오픈** 순으로 캡처 이미지를 저장합니다.
- **주요 옵션**:
  - `login=<company>/<user>/<pw>` 또는 `--login, -l`: 로그인 지정자 (예: `login=kfstest/104/1111`)
  - `--url, -u`: 접속할 TOBE 기본 URL (기본: `http://localhost:8082/AssetERP`)
  - `--out, -o`: 캡처 루트 폴더 (기본: `.yunhee/screen-capture`, 하위에 `<화면번호_클래스명>/` 폴더 자동 생성)
  - `--title, -t`: 겸직선택 시 특정 부서/직책/사원ID 강제 지정 (미지정 시 대상 화면 권한 보유 겸직 자동 선택)
  - `--no-popups`: 팝업/Lookup 모달 순회를 생략하고 본 화면만 빠르게 캡처
  - `--headed`: 브라우저 창을 화면에 표시 (디버깅용)
- **예시**:
  ```bash
  yunhee screen-capture 1048 login=kfstest/104/1111
  yunhee screen-capture Fnd01_Tab_FundCode login=kfstest/104/1111 --url http://localhost:8082/AssetERP --out .yunhee/screen-capture
  ```

---

## 5. 환경 설정 및 유틸리티 (`config`, `value`, `changelog`, `init`, `intro`)

- `yunhee init`: 현재 작업 디렉터리를 yunhee 프로젝트로 등록 및 필수 폴더/파일(`.yunhee/project.json`, `mcp.json`, `memory.md`, `sessions/`, `runs/`, `.gitignore`) 초기화
- `yunhee config`: 작업 디렉터리(Work Dir), TOBE/ASIS 소스 경로 및 브랜치 상태, DB 접속 정보 등 환경 설정 확인
- `yunhee value [KEY]`: 단일 설정값 텍스트 출력 (`--list` 시 전체 목록, `tobe-src`, `asis-src`, `work-dir` 등 지원)
- `yunhee intro`: yunhee 에이전트 자기소개 및 전문 영역 안내 (`자기소개?` 도 지원)
- `yunhee changelog`: 버전별 변경 이력 및 릴리즈 노트 확인
