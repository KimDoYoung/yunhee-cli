# yunhee 업무 파악 및 추적 가이드 (`trace.md`)

> `yunhee trace-*` 명령어 18종은 복잡한 금융/자산운용 도메인의 구조, 화면 라이프사이클, 데이터 흐름, ASIS↔TOBE 대조 상태를 정밀하게 추적합니다.
> 
> **공통 옵션**:
> - `-o, --format <md|json>`: 출력 포맷 지정 (기본: `md`)
> - `--side <asis|tobe|both>`: 분석 대상 (기본: `both`)
> - `--max <N>`: 출력 항목 상한 제한
> - `--tobe <DIR>`: TOBE 프로젝트 루트 (기본: 현재 작업 디렉터리)

---

## 1. 탐색 계층 (Navigation & Screen Fact Sheet)

### `yunhee trace-map`
업무 영역(도메인)별 화면 수, 테이블 수, ASIS↔TOBE 매핑 진행 상태를 요약합니다.
- **옵션**: `-d, --domain <도메인>` (예: `sys`, `emp`, `fnd`)
- **예시**: `yunhee trace-map -d sys`

### `yunhee trace-menu [menu_path]`
메뉴 트리 구조 → ASIS 화면 클래스 → TOBE 화면/API 추적 경로를 출력합니다.
- **인자**: 메뉴 경로 문자열, 메뉴 번호(예: `#1029`), 또는 화면 클래스명
- **예시**:
  ```bash
  yunhee trace-menu "조직 및 사원관리 > 사원정보"
  yunhee trace-menu '#1029'
  ```

### `yunhee trace-screen <screen_id>`
단일 화면의 종합 팩트시트를 출력합니다. (라벨, 그리드 컬럼, 버튼, 이벤트, RPC, SQL, 테이블, DB 함수 포함)
- **인자**: 화면 클래스명, 접두사, 또는 메뉴 번호
- **예시**:
  ```bash
  yunhee trace-screen Emp00_Tab_TransInfo
  yunhee trace-screen '#1029'
  ```

---

## 2. 데이터 중심 계층 (Data & State Lifecycle)

### `yunhee trace-table <table_name>`
테이블의 컬럼 목록, 코멘트, C/R/U/D SQL과 사용 화면, 동명 컬럼 테이블을 추적합니다.
- **옵션**: `--stats` (DB에 직접 접속해 실제 행 수 조회)
- **예시**:
  ```bash
  yunhee trace-table sys06_menu
  yunhee trace-table apr01_appr --stats
  ```

### `yunhee trace-column <table.column>`
특정 컬럼을 읽는(SELECT), 쓰는(INSERT/UPDATE), 조건(WHERE)에 쓰는 SQL과 표시 화면 라벨을 추적합니다.
- **옵션**: `--stats` (코드성 컬럼의 고유 값 분포 조회)
- **예시**:
  ```bash
  yunhee trace-column apr01_appr.apr01_status_cd --stats
  ```

### `yunhee trace-code <code_group>`
공통 코드 그룹의 상세 코드값, 명칭(DB 조회)과 소스 내 콤보박스/SQL 리터럴 사용처를 추적합니다.
- **예시**:
  ```bash
  yunhee trace-code AprStatusCode
  ```

### `yunhee trace-state <table.column>`
특정 컬럼에 값을 쓰는 모든 INSERT/UPDATE 문의 대입 값과 조건식(상태 전이 로직)을 추적합니다.
- **예시**:
  ```bash
  yunhee trace-state apr01_appr.apr01_status_cd
  ```

### `yunhee trace-crud`
화면 × 테이블 × C/R/U/D 매트릭스를 ASIS와 TOBE 나란히 대조하여 추적합니다.
- **옵션**: `-d, --domain <영역>`, `-s, --screen <화면>`, `-t, --table <테이블>`
- **예시**:
  ```bash
  yunhee trace-crud -d emp
  yunhee trace-crud -s Emp00_Tab_TransInfo
  ```

---

## 3. 실행 사슬 및 비즈니스 룰 추적 (Execution Chain & Logic)

### `yunhee trace-flow <screen_id>`
특정 이벤트 하나의 끝까지 이어진 전체 실행 사슬을 추적합니다. (이벤트 → 핸들러 → 서비스 RPC → 서버 메서드 → SQL → 테이블)
- **옵션**: `-e, --event <이벤트번호>` (예: `E3`), `-c, --class <하위클래스>`
- **예시**:
  ```bash
  yunhee trace-flow Emp00_Tab_TransInfo -e E3
  ```

### `yunhee trace-branch <target>`
화면 또는 매퍼 SQL 내의 모든 조건 분기 지점(if, switch, `<if test>`, CASE WHEN 등) 목록을 추출합니다.
- **예시**:
  ```bash
  yunhee trace-branch Emp00_Tab_TransInfo
  yunhee trace-branch emp00_trans_info.selectByText
  ```

### `yunhee trace-dblogic [name]`
DB 저장 함수, 프로시저, 트리거 본문(스냅샷)과 이를 호출하는 SQL을 추적합니다.
- **예시**:
  ```bash
  yunhee trace-dblogic f_cdnm
  yunhee trace-dblogic
  ```

---

## 4. ASIS ↔ TOBE 대조 계층 (Comparison & Gap Analysis)

### `yunhee trace-pair <screen_id>`
ASIS 화면과 TOBE 구현체 간 짝지어진 항목 및 매칭 근거(주석, 테이블 조합, 명칭)를 확인합니다.
- **예시**:
  ```bash
  yunhee trace-pair Emp00_Tab_TransInfo
  ```

### `yunhee trace-diff <target>`
ASIS와 TOBE 간 SQL 정규화 diff, 조건 분기 대응표, UI 필드 대응표를 대조합니다.
- **옵션**: `--sql` (SQL diff만), `--branch` (분기만), `--ui` (UI 필드만)
- **예시**:
  ```bash
  yunhee trace-diff '#1029'
  yunhee trace-diff emp00_trans_info.selectByText --sql
  ```

### `yunhee trace-gap`
ASIS에만 있거나 TOBE에만 있는 요소, 아직 추적되지 않은 마이그레이션 누락 지점(Gap)을 분석합니다.
- **옵션**: `-d, --domain <영역>`
- **예시**:
  ```bash
  yunhee trace-gap -d emp
  ```

---

## 5. 카탈로그 및 지침 계층 (Rules & Guide)

### `yunhee trace-rule <action> [target]`
마이그레이션 판정 규칙 및 근거를 저장/조회하고 근거 파일/라인의 유효성을 검증합니다.
- **action**: `add`, `list`, `show`, `update`, `verify`
- **예시**:
  ```bash
  yunhee trace-rule list Emp00
  yunhee trace-rule verify R-001
  yunhee trace-rule add Emp00 --verdict 일치 --note "완료 검증됨"
  ```

### `yunhee trace-term [term]`
화면 라벨, DB 컬럼명/코멘트, 공통 코드명 간의 용어 교차 참조 사전을 검색합니다.
- **예시**:
  ```bash
  yunhee trace-term 성명
  yunhee trace-term 결재
  ```

### `yunhee trace-doc <domain>`
신규 담당자를 위해 카탈로그와 팩트를 체계적인 업무 인수인계 문서 골격으로 자동 조립합니다.
- **예시**:
  ```bash
  yunhee trace-doc sys
  ```

### `yunhee trace-guide`
에이전트를 위한 trace-* 기반 업무 파악 표준 워크플로우 지침을 출력합니다.
- **예시**:
  ```bash
  yunhee trace-guide
  ```
