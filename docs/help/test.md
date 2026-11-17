# yunhee 시험(테스트) 전문 가이드 (`test.md`)

이 문서는 프로젝트의 일괄 시험 및 검증 자동화를 지원하는 `test-*` 명령군과 관련 도구들의 사용법을 안내합니다.

---

## 🧭 빠른 상황별 명령어 안내

| 목적 | 명령어 | 설명 |
|:---|:---|:---|
| **매퍼 파라미터 자동 탐색** | `yunhee test-params "<매퍼.xml>#<id>" [-c <회사>] [-o text\|json\|args]` | SQL 조건절 및 DB 실제 데이터 기반 유효한 파라미터 조합 추론 |
| **매퍼 자동 파라미터 실행** | `yunhee mapper-run "<매퍼.xml>#<id>" --auto-params --rollback` | `test-params`가 찾은 파라미터를 자동 바인딩하여 롤백 실행 |
| **JUnit 스모크 시험 뼈대 생성** | `yunhee test-gen-mapper <MapperName\|도메인> [--dry-run] [--force]` | JUnit5 `@MybatisTest` 기반 스모크 테스트 Java 클래스 자동 생성 |
| **시나리오 테스트 뼈대 생성** | `yunhee test-scenario-skel <이벤트ID> [--company kova] [--print]` | 업무분석 이벤트 YAML로부터 시나리오 파이썬 함수 뼈대 생성 |
| **테스트 커버리지 분석** | `yunhee test-coverage [--by domain\|mapper\|screen] [-o md\|tsv]` | 소스 호출 관계(정적) 및 JUnit/시나리오(동적) 기반 문장별 커버리지 집계 |
| **AS-IS 대량 대조 시험** | `yunhee test-compare <목록.tsv> [-c <회사>] [-o tsv\|junit] [--out <폴더>]` | 목록 기반 조회 API vs AS-IS SQL 일괄 비교 (0=0은 skip, JUnit 리포트 지원) |

---

## 1. `test-params` & `mapper-run --auto-params`

매퍼 statement를 테스트할 때 필요한 파라미터 값을 DB에서 스스로 탐색합니다.

```bash
# 파라미터 값과 근거 확인
yunhee test-params "backend/src/main/resources/mapper/EmpDeductMapper.xml#insertAddDeductTypes" -c 28000

# 한 줄 인수 형식으로 출력 (-p k=v ...)
yunhee test-params "backend/src/main/resources/mapper/FrmListMapper.xml#selectIcsNotice" -o args

# 자동 파라미터로 바로 롤백 실행
yunhee mapper-run "backend/src/main/resources/mapper/EmpDeductMapper.xml#insertAddDeductTypes" --auto-params --rollback

# 특정 파라미터만 직접 주고 나머지는 자동 추론
yunhee mapper-run "backend/src/main/resources/mapper/EmpDeductMapper.xml#insertAddDeductTypes" --auto-params -p personId=29043 --rollback
```

### 값 결정 원칙
1. **SQL 조건절 비교 열**: `WHERE col = #{param}`, `JOIN ... ON col = #{param}`에 매칭되는 실제 DB 컬럼 값 탐색.
2. **동일 행 묶기**: 한 테이블에서 둘 이상의 파라미터 값을 뽑을 때는 같은 행의 값을 선택하여 0행 방지.
3. **이름 규칙**:
   - `companyId`: 지정 회사 또는 기본 회사
   - `personId` / `empId` / `userId`: 해당 회사의 재직 사원(`emp01_person`)
   - `orgId` / `orgCd`: 사원의 현재 조직
   - `stdDate` / `selectDate` / `*Date`: 오늘 날짜
   - `startDate` / `closeDate`: `2000-01-01` / `2099-12-31`
4. **Java 서비스 상수**: 서비스 메서드 호출부의 `static final` 상수나 리터럴 우선 반영.
5. **열 이름 검증**: 반드시 `information_schema.columns`로 확인된 실제 컬럼만 참조.

---

## 2. `test-gen-mapper`

매퍼의 모든 메서드가 오류 없이 도는지 검증하는 JUnit5 스모크 테스트(`*SmokeDbTest.java`) 소스를 자동 생성합니다.

```bash
# 도메인 전체 매퍼에 대해 dry-run 확인
yunhee test-gen-mapper att --dry-run

# 단일 매퍼에 대해 스모크 테스트 파일 생성
yunhee test-gen-mapper AttCommuteMapper --out backend/src/test/java

# 기존 파일 덮어쓰기
yunhee test-gen-mapper AttCommuteMapper --force
```

- `@MybatisTest` 및 `@AutoConfigureTestDatabase(replace = NONE)` 사용으로 모든 DML은 자동 롤백됩니다.
- 값을 못 정한 파라미터가 있는 문장은 지어낸 값을 넣지 않고 `@Disabled("값을 못 정함: ...")`로 처리합니다.
- 프로젝트 불변 관례에 따라 DTO는 Record 생성자(`new Xxx(...)`)로 생성되며 Setter/Data/Map을 사용하지 않습니다.

---

## 3. `test-scenario-skel`

업무분석 이벤트 문서(`docs/2-업무분석/biz-event/<도메인>/<ID>-*.md`)의 시나리오 YAML로부터 파이썬 테스트 코드를 자동 생성합니다.

```bash
# 생성된 파이썬 함수 코드 화면 출력
yunhee test-scenario-skel EMP-BZ-0018 --print

# 시나리오 파일(tools/tests/scenario/emp.py)에 함수를 추가하고 all.py에 등록
yunhee test-scenario-skel EMP-BZ-0018

# 도메인 전체 이벤트 문서의 YAML 문법·중복키·자리표시·AST 일괄 점검
yunhee test-scenario-skel EMP --check
```

- **Actor 이어받기 및 역할어 해석**: `actor`가 생략된 단계는 직전 단계의 actor를 이어받으며, 주석(`# 301, { action: confirm }`)이나 단계 설명의 역할어(`직원`, `팀장`, `경영관리`)를 문서 상단 `누가` 행과 대조해 자동으로 클라이언트를 전환합니다. `company: admin`은 `Client("admin", "admin", PW)`로 보존하고 가상회사는 `COMPANY` 상수를 사용합니다.
- **자리표시 및 앞 단계 응답 변수 바인딩**: `<401>`·`<402>`는 `emp["402"]`로, `{errandId}`·`{apprId}`·`<3>` 등은 앞선 생성/조회 단계의 반환 변수(`errand_id`, `appr`, `sid`)로 연결하며, 문서분류는 `tree(cid, ...)`로 바인딩합니다. 미해결 항목은 `None  # TODO <...>`로 두어 오작동을 방지합니다.
- **본문 · 기대값 · 오류 기대(`sc.raw`)**: 주석/인라인 `{ ... }` 본문 파싱, 결재 `apr.save_body` 틀 및 누락된 `/apprs/new` 자동 삽입, 오류 기대 주석(`INVALID_INPUT`, `→ 403` 등)의 `sc.raw` 변환, `returns` $\rightarrow$ `{"": val}`, `rows` $\rightarrow$ `len(v or []) == n`, `table delta` / `tables` $\rightarrow$ 전후 `count_rows` + `sc.check` 코드화를 수행합니다.
- **안전 가드**: 주석이 포함된 dict/list는 멀티라인으로 포맷팅하고 반환 전 `ast.parse` 검증을 강제합니다.

---

## 4. `test-coverage`

어떤 매퍼 문장과 화면이 테스트되고 있는지 정적·동적·서버 로그 기반으로 추적합니다.

```bash
# 도메인별 매퍼 문장 커버리지 집계 (정적 테스트 기준)
yunhee test-coverage --by domain

# JUnit XML(<system-out> Preparing 포함) + 시나리오 + 서버 로그 구간 실행 커버리지 합산
yunhee test-coverage -d emp --junit backend/junit --scenario scenario.json --log ~/tmp/asseterp-data/logs/AssetERP-backend-info.log --from 23:08 --to 23:25

# 매퍼별 상세 커버리지 표 / 기계용 TSV 출력
yunhee test-coverage --by mapper
yunhee test-coverage -o tsv
```

- `--log <파일|docker> [--from ...] [--to ...] [--since-run <id>]`: 서버 로그의 MyBatis `==> Preparing:` 줄에서 실제 실행된 매퍼 문장을 수집합니다. 로거 이름이 축약(`k.c.k.a.b.e.m.E.selectNextId`)된 경우 도메인·매퍼 이니셜과 SQL 테이블/컬럼을 대조하여 **시험됨(확실)**과 **상한(모호 포함)**으로 나누어 집계합니다.

---

## 5. `test-compare`

조회 API 응답과 AS-IS SQL 실행 결과를 대량으로 일괄 대조합니다.

```bash
# TSV 목록 일괄 대조 및 JUnit XML 리포트 생성
yunhee test-compare tests/tests_compare.tsv -c kfstest -o junit --out build/reports/tests

# TSV 결과 출력
yunhee test-compare tests/tests_compare.tsv -c kfstest -o tsv
```

- 입력 TSV 형식: `이름\tMETHOD path\tAS-IS SQL ID\t파라미터\t옵션`
- 판정 규칙: 행 수 및 컬럼 커버리지 일치 시 `ok`, 불일치 시 `fail`, `0 == 0`인 경우 확인 불가로 판단하여 `skip`.
- 단일 로그인 세션을 재활용하여 대량 검증 시 서버 부하를 최소화합니다.

---

## 6. `test-insert-data` / `test-rollback-data`

특정 로그인 계정과 화면번호에 맞춰 화면에서 즉시 조회 가능한 테스트 데이터를 생성하고, 테스트가 끝나면 발급된 `transaction-code`로 깨끗하게 삭제(롤백)합니다.

```bash
# kfstest 회사의 121 사원 컨텍스트로 1023 화면의 대상 테이블에 테스트 데이터 3건 생성
yunhee test-insert-data kfstest-121-1111 1023

# 발급된 transaction-code로 생성했던 데이터 역순 삭제
yunhee test-rollback-data kfstest-121-1111 tx-1023-20261117-160000-a1b2

# 생성/롤백 트랜잭션 이력 조회 및 최근 트랜잭션 즉시 롤백
yunhee test-rollback-data --list
yunhee test-rollback-data kfstest-121-1111 --last
```

