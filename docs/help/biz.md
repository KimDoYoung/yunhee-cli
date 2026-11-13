# 업무분석 및 검증 (`biz.md`)

> **핵심 원칙**: `biz-*` 명령어군은 TOBE 시스템의 비즈니스 로직 분석, 권한 검사, 전자결재 흐름 검증, 안전한 데이터 조작 및 이벤트 문서 자동 생성을 지원하는 도구 모음입니다.

---

## 🧭 명령어 요약표

| 명령어 | 주요 기능 | 주요 옵션 |
| :--- | :--- | :--- |
| `biz-endpoints [target]` | Spring Boot 컨트롤러 엔드포인트·DTO·서비스·권한 가드 정적 분석 (클래스명 직접 지원, target 생략 시 전체 컨트롤러 스캔) | `-o md\|json\|tsv`, `--path` (반복/쉼표), `--screen` (복수/쉼표) |
| `biz-authz <target>` | API URL과 메뉴 인가를 대조하여 허용 여부 판정 및 취약 엔드포인트 진단 | `-u`, `-c`, `--probe-write`, `--probe-appr`, `--path`, `--screen`, `--dry-run`, `--lint-delete-by-id` |
| `biz-appr <link_code>` | 업무 문서와 결재 연동 상신·연결·승인/반려 단계 자동화 | `--ref` (반복), `--pre`, `--link-path`, `--seed-arg`, `--title`, `--content`, `--link-body`, `-u`, `-c`, `--approver`, `--confirm`, `--reject` |
| `biz-orphans <parent_table>` | FK 부모-자식 관계 기반 고아(Orphan) 행 탐색 및 누락된 자식 삭제 API 진단 | `-c`, `--children` |
| `biz-patch <method> <path>` | 조회된 API 데이터를 수정하여 저장하고 필드 누락 검증 | `--set key=val`, `-b/--raw-body`, `--where "k=v"`, `--list`, `--drop-suffix` |
| `biz-code [kind]` | 공통코드 종류(종류명/코드값) 및 상세 코드 목록 조회 (회사별 명칭 지원) | `--like`, `-c`, `--db` |
| `biz-db-write` | 로컬 DB 대상 안전한 쓰기 실행 (자동 `pg_dump` 백업 및 되돌리기 안내) | `-f`, `-e`, `--no-backup`, `--dry-run` |
| `biz-event-new <ID>` | AS-IS/TOBE 화면 색인을 바탕으로 비즈니스 이벤트 분석 문서 골격 생성 (정제된 단계, 관련 이벤트/의심번호 연동) | `--screens`, `--title`, `-c`, `--force`, `--out` |
| `api` (확장) | 계정 보호(3회 실패 잠금 방지) 및 수동 비밀번호 지정 지원, 단일 텍스트 값 추출 | `--password`, `--force-login`, `--get` |

---

## 1. `biz-endpoints` — 컨트롤러 엔드포인트 정적 분석

Spring Boot 컨트롤러, DTO, 서비스 소스를 정적으로 분석하여 HTTP 메서드, 경로, 본문 DTO 필드, 호출 서비스, 권한 검사(Guards)를 추출합니다.

```bash
# 특정 도메인(pay, att 등) 또는 컨트롤러 클래스명 직접 분석 (생략 시 전체 컨트롤러 스캔)
yunhee biz-endpoints
yunhee biz-endpoints pay
yunhee biz-endpoints AstRelateApprController

# 특정 경로 필터링 (복수 지정 및 쉼표 구분 가능) 및 출력 형식 지정 (md, json, tsv)
yunhee biz-endpoints pay --path work-times -o json
yunhee biz-endpoints ast --path owner-capitals --path invest-limits

# 화면 번호 연관 API 자동 필터링 (복수 및 쉼표 지정 지원)
yunhee biz-endpoints --screen 1299
yunhee biz-endpoints --screen '1299, 1300'
```

- **권한 가드(Guards) 판정**:
  - `KFS관리자`: `@RequireSysAdmin` 또는 `requireSysAdmin()`
  - `메뉴/역할`: `@PreAuthorize`, `@Secured`, 역할 검사
  - `본인`: 세션 사용자 본인 ID 일치 검사 (`requireSelf` 등)
  - `회사`: 세션 회사 ID 조건 (`companyId` 매핑)
  - `서비스내부(메서드명)`: 서비스 진입부 검사 메서드(`check*`, `require*`, `verify*`, `load*`)
  - `⚠없음`: 컨트롤러 및 서비스에 권한 검사 로직이 감지되지 않음 (쓰기 a·조회 b 요약 표시)

---

## 2. `biz-authz` — API 접근 인가 및 권한 갭 진단

프론트엔드 TSX/API 매핑 및 사원 권한 정보를 기반으로, 특정 사용자/회사가 호출 가능한 엔드포인트를 분석하고 안전한 GET/쓰기 프로브로 권한 누락(의심 취약점)을 진단합니다.

```bash
# 사원(401) 계정으로 pay 도메인의 인가 상태 분석 (안전 GET 프로브 포함)
yunhee biz-authz pay -u 401 -c kalpa

# 특정 경로 또는 화면 번호에 대해 빈 페이로드({})로 쓰기 권한 검사 프로브 (--dry-run 시 실제 요청 없이 시뮬레이션)
yunhee biz-authz pay --path work-times -u 401 -c kalpa --probe-write
yunhee biz-authz ast --screen 1299 -u 401 -c kalpa --probe-write --dry-run

# 결재 ID 바꿔치기(apprId=1) 프로브 시험 (원복 보장)
yunhee biz-authz pay --probe-appr -u 401 -c kalpa

# DELETE API에서 companyId 조건 누락 취약점 검출 (정적 코드 분석)
yunhee biz-authz pay --lint-delete-by-id
```

---

## 3. `biz-appr` — 전자결재 상신·연결·승인 자동화

업무 화면 연동 결재(A74 연장근무, A73 휴가, D01 지출, A02/A05/X01/A63/A64 등)의 상신(Draft), 업무 테이블 연결(Link), 결재선 승인(Confirm) 또는 반려(Reject) 과정을 한 번에 수행합니다.

```bash
# 연장근무 신청(A74) 건(ref_id=12345)에 대해 401 사원이 상신하고 301 과장이 승인 완료
yunhee biz-appr A74 --ref 12345 -u 401 -c kalpa --approver 301 --confirm

# 상신 전 선행 업무 데이터 자동 생성 후 결재 연동
yunhee biz-appr A02 --pre 'POST /api/v1/fnd/funds {"fundCode": "F01"}' -u 401 -c kalpa --confirm

# 복수 ref 건 지정 및 커스텀 연결 경로/시드 인자/제목/본문 전달
yunhee biz-appr A64 --ref 101 --ref 102 --link-path /api/v1/ast/relate-apprs --seed-arg "relateType=1" -u 401 -c kalpa
yunhee biz-appr A60 --ref 501 --title "투자한도 결재" --link-body '{"limitId": {ref}, "apprId": {apprId}}' -u 401 -c kalpa

# 반려 처리
yunhee biz-appr A74 --ref 12345 -u 401 -c kalpa --approver 301 --reject

# 승인 대기 상태까지만 상신 및 연결 생성
yunhee biz-appr A74 --ref 12345 -u 401 -c kalpa --approver 301
```

---

## 4. `biz-orphans` — 고아(Orphan) 행 탐색 및 무결성 진단

FK 부모-자식 관계를 분석하여 부모가 삭제되었으나 자식 테이블에 남아있는 고아 데이터가 있는지 조회하고, 컨트롤러에 자식 데이터 삭제 누락 여부를 진단합니다.

```bash
# 부모 테이블 기준 자식 테이블의 고아 행 검사
yunhee biz-orphans ast01_invest_limit -c kalpa
```

---

## 5. `biz-patch` — API 단일 객체/목록 필드 안전 수정

현재 API 응답 데이터를 읽어와서 지정한 필드만 변경한 뒤 PUT/POST로 다시 저장합니다. 저장 시 원본 필드가 소실되는지(`wiped_fields`) 자동으로 검증합니다.

```bash
# 단일 객체 API의 특정 플래그 값 수정 (--set key=value 지원)
yunhee biz-patch PUT /api/v1/att/work-policies/current -u 401 -c kalpa --set commutePopupYn=false

# 목록형 API에서 특정 조건 행만 수정하여 저장
yunhee biz-patch PUT /api/v1/pay/work-times -u admin -c admin \
  --list --where "startDate=2026-01-01" --set weekMaxAddHours=16
```

---

## 5. `biz-code` — 공통코드 조회 및 회사별 코드명 매핑

공통코드 분류(`sys08_code_kind`)와 상세 코드(`sys09_code`)를 조회하며, 회사별 오버라이드 명칭(`sys10_company_code`)을 대조하여 표시합니다.

```bash
# 코드 종류명으로 상세 코드 조회
yunhee biz-code WorkTypeCode -c kalpa

# 유사 코드 종류 검색
yunhee biz-code --like Work
```

---

## 6. `biz-db-write` — 안전한 로컬 DB 쓰기 및 자동 백업

로컬 PostgreSQL 개발 DB(`localhost` / `127.0.0.1`)에 한하여 자동 `pg_dump` 백업을 생성하고 SQL 쓰기(UPDATE, INSERT, DELETE)를 수행합니다.

```bash
# 환경변수 안전 가드 필요 (YUNHEE_DB_WRITE=1)
# 파일에 저장된 SQL 스크립트 실행 (실행 전 자동 pg_dump 백업 생성 및 복원 명령어 안내)
YUNHEE_DB_WRITE=1 yunhee biz-db-write -f patch.sql

# 단일 문장 직접 실행 (--no-backup 옵션)
YUNHEE_DB_WRITE=1 yunhee biz-db-write -e "UPDATE att01_work_policy SET att01_note = '테스트' WHERE att01_work_policy_id = 1;" --no-backup

# WHERE 절 없는 전체 DELETE/UPDATE 및 DDL 차단 (실행 시 에러로 보호)
```

---

## 7. `biz-event-new` — 비즈니스 이벤트 분석 문서 틀 생성

AS-IS `menus.md` 및 화면 색인(이벤트 E0~En, 서비스, 메서드, 테이블)과 TOBE 컨트롤러/API 엔드포인트를 결합하여 이벤트 분석 마크다운 문서를 기계적으로 생성합니다. 버튼 이벤트만 단계로 정제하고, 확인창 결합, 팝업 단계명(`#{screen} → {popup}`) 표기, 관련 이벤트/의심 번호 연동, 화면 쓰기 API 표 및 biz-authz 후속 안내를 자동 삽입합니다.

```bash
# 1489 화면에 대한 비즈니스 이벤트 문서 뼈대 생성
yunhee biz-event-new PAY-BZ-0004 --screens 1489 --title "근로시간 기준 설정" --company kalpa
# 생성 경로: docs/2-업무분석/biz-event/PAY/PAY-BZ-0004-근로시간기준설정.md

# 복수 화면 번호 지정
yunhee biz-event-new ATT-BZ-0005 --screens 1270,1281,1285 --title "근태관리 관리자" --company kalpa
```

---

## 8. `api` 명령 확장 (계정 보호 및 값 추출)

- `--password <비밀번호>`: DB 조회나 환경변수 기본값을 타지 않고 명시적으로 비밀번호 전달.
- `--force-login`: 3회 이상 로그인 실패로 인한 계정 잠금 가드를 무시하고 강제 로그인 시도.
- `--get <path>`: 응답 JSON에서 특정 키/경로의 값만 단일 텍스트로 출력 (예: `data.trId`, `data.items[0].id`). 스크립트 변수 바인딩용.
