# yunhee 정적 분석 가이드 (`analysis.md`)

> `yunhee analysis <type> <target> [options...]` 명령어는 AS-IS 및 TOBE 소스를 직접 열어보지 않고도 필요한 정보(메서드 본문 요약, 실행 가능 SQL, 그리드 컬럼 스펙 등)를 정밀 추출하여 컨텍스트 토큰을 절약합니다.

전체 지원 유형 확인:
```bash
yunhee analysis --list
```

---

## 1. 화면 및 UI 분석 (`screen`, `ui`, `grid`)

### `yunhee analysis screen <화면클래스>`
색인 화면 파일에서 필요한 클래스 목록 통계나 특정 절(section)을 추출합니다.
- **주요 옵션**:
  - `--list`: 화면에 포함된 모든 클래스 목록과 라인 수, 버튼/이벤트/그리드 통계 (`--no-linked` 지원)
  - `--section <NAME>`: 특정 절만 핀포인트 추출
    - `layout`: 폼 탭의 컴포넌트 크기, 라벨 폭, 행 구조, readOnly/disable 속성
    - `ui`: 버튼, 이벤트 핸들러, 그리드 정의
    - `methods`: 클래스 내 메서드 목록 및 시그니처
    - `tables`: 화면에서 사용하는 DB 테이블 목록
    - `source`: 색인 시점의 소스 커밋 및 의존 파일 요약
  - `-o, --output json`: JSON 형식 출력
- **예시**:
  ```bash
  yunhee analysis screen Emp00_Tab_TransInfo --list
  yunhee analysis screen Emp00_Tab_TransInfo --section layout
  ```

### `yunhee analysis ui <화면클래스>`
AS-IS 화면 대비 TOBE 이벤트 구현율 및 단계별 버튼/이벤트/그리드 현황을 분석합니다.
- **주요 옵션**:
  - `--done <CLASSES>`: 1단계 완료 클래스 목록 (콤마 구분)
  - `--later <TEXT>`: 2단계 등 이후 구현 예정 클래스 목록
  - `--layout`: 폼 레이아웃 상세를 함께 출력
- **예시**:
  ```bash
  yunhee analysis ui Emp00_Tab_TransInfo --done Emp00_Tab_TransInfo
  yunhee analysis ui Emp00_Tab_TransInfo --done Emp00_Tab_TransInfo --later "2단계=Emp02_TabPage_Others"
  ```

### `yunhee analysis grid <클래스>[.필드]`
그리드의 ColumnModel 구성 순서, GridType 판정 및 DB 컬럼 부재 여부를 정밀 분석합니다.
- **주요 옵션**:
  - `-m, --method <MET>`: 특정 메서드 내의 그리드 생성 로직만 필터링
  - `--check-columns / --no-check-columns`: 그리드 컬럼의 Model 속성, 매퍼 SQL, DB 컬럼 존재 여부 검증 (기본: 켬)
- **예시**:
  ```bash
  yunhee analysis grid Org00_Lookup_Fund
  ```

---

## 2. 비즈니스 로직 및 SQL 분석 (`method`, `sql`, `model`, `servlet`, `save-script`)

### `yunhee analysis method <클래스>.<메서드>`
AS-IS 및 TOBE 메서드의 본문 요약, 호출 흐름, 클라이언트/서버 연계 분석을 수행합니다.
- **주요 옵션**:
  - `--raw`: 요약뿐만 아니라 원문 코드까지 함께 출력
  - `--follow`: 서버 메서드 단순 위임(호출)을 1~2단계 추적
  - `--all-overloads`: 오버로드된 모든 메서드를 한 번에 출력
  - `--called-from <CLASS>`: 특정 호출 클래스 기준 오버로드 선택
- **예시**:
  ```bash
  yunhee analysis method Emp03_TabPage_Detail.saveDetail
  yunhee analysis method SysService.saveCompany --follow
  ```

### `yunhee analysis sql <namespace.id>`
MyBatis 매퍼 statement를 분석하고 파라미터가 바인딩된 실제 실행 가능 SQL을 펼쳐냅니다.
- **주요 옵션**:
  - `--param <key=val>`: 파라미터 값 바인딩 (반복 가능, `s:`, `n:`, `b:`, `null:` 타입 접두사 지원)
  - `--branch <expr=on|off>`: MyBatis 조건 분기(`<if>`, `<when>`) 강제 ON/OFF 지정 (반복 가능)
  - `--count`: SQL 행 수만 카운트하는 SELECT COUNT(*) 형태로 변환
  - `--no-cte`: CTE(WITH ...) 블록을 생략하고 본문 SELECT/WHERE만 출력
  - `-o, --output <FORMAT>`: `md`, `sql`, `code`, `json`
- **동작 특징**:
  - `x.equals('lit')`, `'lit'.equals(x)`, `!x.equals('lit')`, `.size`, `0L` 등 MyBatis OGNL 조건식을 자동 평가합니다.
  - 평가할 수 없는 분기식은 임의로 켜지지 않고 주석(`/* ⚠ 분기 평가 불가(기본 OFF): ... */`) 처리되어 실행을 차단하며, `--branch`로 명시적 제어가 가능합니다.
- **예시**:
  ```bash
  yunhee analysis sql emp00_trans_info.selectByText --param text=홍길동
  yunhee analysis sql car03_booking.selectByDate --param type=all --param personId=1 -o sql
  yunhee analysis sql car03_booking.selectByDate --branch "type.equals('my')=on" -o sql
  ```

### `yunhee analysis model <모델클래스>`
화면 모델 속성 → `@Path` 필드 → MyBatis/DB 컬럼 간 매핑 관계를 분석합니다.
- **주요 옵션**:
  - `--sql <SQL_ID>`: 연관 MyBatis SQL ID 지정
- **예시**:
  ```bash
  yunhee analysis model Sys05_UserRole --sql sys05_user_role.selectList
  ```

### `yunhee analysis save-script <ns.Class.method>`
서버 저장 메서드의 모든 CUD 쓰기 SQL들을 파라미터 대입 단일 롤백 스크립트로 생성합니다.
- **주요 옵션**:
  - `--param <key=val>`: 바인딩 파라미터 지정 (반복 가능)
  - `--branch <key=val>`: 분기 조건 지정
- **예시**:
  ```bash
  yunhee analysis save-script apr.Apr90_Disposal.save \
    --param disposalCode=D01 \
    --param confirmEmpId=EMP001 \
    --param companyId=28000
  ```

### `yunhee analysis servlet <서블릿클래스>`
서블릿 클래스 및 fileType 분기 처리 로직을 분석합니다.
- **주요 옵션**:
  - `--type <FILE_TYPE>`: 특정 fileType 분기만 필터링
- **예시**:
  ```bash
  yunhee analysis servlet FileDownload --type apprList
  ```

---

## 3. TOBE 코드 및 실행 결과 분석 (`tobe`, `run`)

### `yunhee analysis tobe <TOBE 파일·폴더>`
TOBE 소스 파일(TSX/TS/Java)의 패턴 골격, 컴포넌트 구조, 훅, 주요 API 호출 패턴을 요약합니다.
- **예시**:
  ```bash
  yunhee analysis tobe frontend/src/pages/sys/SysRole.tsx
  yunhee analysis tobe backend/src/main/java/kr/co/kfs/asseterp/biz/sys/
  ```

### `yunhee analysis run [last | run_id]`
외부 명령어 실행 결과 로그(`.yunhee/runs/<run_id>.log`)에서 필요한 부분만 분리 추출합니다.
- **주요 옵션**:
  - `--stderr`: 에러 및 예외 출력 부분만 확인
  - `--stdout`: 표준 출력 부분만 확인
  - `-n, --limit <LINES>`: 출력 줄 수 제한
  - `--tests`: 테스트 실행 결과 통계 요약 (통과/실패 수)
  - `--json`: 출력 로그 중 마지막 JSON 블록만 파싱
- **예시**:
  ```bash
  yunhee analysis run last --stderr
  yunhee analysis run last --stdout -n 50
  ```
