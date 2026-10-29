# yunhee 마이그레이션 & 코드 생성 가이드 (`migration.md`)

> AS-IS 레거시(GWT/Java 8/MyBatis)에서 TOBE(Spring Boot/React/Java 21)로 코드를 변환할 때, 수작업 실수를 방지하고 기계적으로 정확한 SQL/DTO/스타일을 생성 및 검증하는 도구 모음입니다.

---

## 1. 코드 및 SQL 생성 도구

### `yunhee port-sql <sql_id>`
AS-IS MyBatis SQL을 TOBE 매퍼 XML 조각(`<select>`, `<sql id="...">`) 및 Java 21 Record DTO로 결정적 변환합니다.
- **주요 옵션**:
  - `--cols <COLS>`: 추출할 컬럼 목록 (쉼표 구분)
  - `--getter-defaults`: AS-IS 모델 getter null 기본값을 COALESCE로 적용
  - `--package <PKG>`: 생성될 DTO 패키지명 (resultType FQN에 사용)
  - `--raw`: 원본 SQL을 그대로 `#{var}` 치환하여 CDATA `<sql id>`로 출력
- **예시**:
  ```bash
  yunhee port-sql sys04_role.selectByName --package kr.co.kfs.asseterp.biz.sys.dto
  yunhee port-sql sys04_role.selectByName --cols role_cd,role_nm,note
  ```

### `yunhee port-save <table> --cols <cols>`
테이블 스키마 및 UpdateDataModel을 기반으로 명시적인 INSERT/UPDATE/DELETE 쿼리 및 채번/사이드이펙트 로직을 생성합니다.
- **주요 옵션**:
  - `--cols <COLS>`: INSERT/UPDATE 대상 컬럼 목록 (필수)
  - `--insert-cols <COLS>`: INSERT에만 포함할 컬럼 목록 (UPDATE SET 제외)
  - `--company-col <COL>`: 회사 ID 컬럼명 (테넌트 격리)
  - `--id-col <COL>`: PK ID 컬럼명
- **예시**:
  ```bash
  yunhee port-save sys04_role --cols role_cd,role_nm,seq,note --id-col role_id
  ```

---

## 2. 화면 스타일 및 정적 이벤트 추출

### `yunhee page-style <targets...>`
화면 파일(.tsx / .java)의 컴포넌트·레이아웃을 정적 분석하여 페이지 스타일 ID(SID 19종: SG, SGP, SGVF, SGEF, SGTP, SGT, TG, GG, CG, STP, TP, SR, GCG, SGHF, TO, GO, DSBRD, GDP, IN)를 판별하고 대조합니다.
- **주요 SID (19종)**:
  - `SG`: SearchBar + 그리드 하나
  - `SGP`: SG + 편집 팝업(`*_Edit_*`)
  - `SGVF`: 위아래 분할 + 그리드 + 읽기 전용 폼
  - `SGEF`: 위아래 분할 + 그리드 + 편집 폼
  - `SGTP`: 위아래 분할 + 그리드 + 아래 탭 영역
  - `SGT`: 툴바 전체 폭 + 좌(그리드)·우(트리) 분할
  - `TG`: 트리 + 오른쪽 내용 좌우 분할
  - `GG`: 그리드 2개 이상 (마스터·상세)
  - `CG`: 편집 가능한 그리드 하나 (`CellEditGrid`, `useGridCrud` 등)
  - `STP`: 툴바 + 탭 컨테이너 (`PageTabs`/`Tabs`), 그리드 없음
  - `TP`: 툴바 없이 탭 컨테이너만 있음
  - `SR`: 툴바 + RD 영역 (`*_Rd_*`/`iframe`), 그리드 없음
  - `GCG`: 위아래 분할 + 그리드 둘 + 달력(`Calendar`)
  - `SGHF`: 좌우 분할 + 그리드 + 편집 폼
  - `TO`: 트리 중심 (단독 또는 팝업 편집), 오른쪽 일반 그리드 없음
  - `GO`: 그리드 하나 + 직접 만든 조건 줄 또는 조건 줄 없음
  - `DSBRD`: 그리드·트리·툴바 없이 카드/요약 영역 (조회 API 또는 rdApi 호출)
  - `GDP`: 좌우 분할 + 버튼 줄 + 그리드 + 오른쪽 상세 페이지 (`*_Page_*`/`*_TabPage_*`)
  - `IN`: 조회·저장 없는 안내 문서/링크
- **주요 기능 및 판정 규칙**:
  - **머리 주석 선언 우선**: `스타일: XXX` (블록 주석 및 `//` 한 줄 주석 모두 지원)을 파싱하여 선언과 판별 불일치 검증
  - **상속 껍데기 화면 위임**: 부모 `_Tab_` 컴포넌트를 렌더링하거나 상속(`extends`)하는 화면은 부모의 SID를 자동 계승
  - **공통 팝업 예외**: `Apr01_Edit_ApprDoc` 등 타 화면 열람용 공통 팝업은 본 화면의 편집 팝업(SGP)으로 오인하지 않음
  - **CG 오탐 방지**: 일반 `SingleGrid`/`MultiGrid` 내 `<Button type="save">` 버튼 존재만으로 CG로 오탐하지 않고 `CellEditGrid`, `useGridCrud`, `editable: true` 등 실제 셀 편집 스펙 검증
- **주요 옵션**:
  - `-c, --compare`: AS-IS Java와 TOBE TSX의 스타일 일치 여부 비교 (일치하지 않으면 exit 1)
  - `-a, --all [DIR]`: 디렉터리 내 모든 화면의 스타일 판별 및 19종 SID별 분포 요약
  - `--json`: 판별 특징 및 근거 JSON 출력
- **예시**:
  ```bash
  yunhee page-style Fnd01_Tab_FundSearch.tsx
  yunhee page-style --compare Fnd01_Tab_FundSearch.java Fnd01_Tab_FundSearch.tsx
  yunhee page-style --all frontend/src/pages
  ```

### `yunhee events <target>`
AS-IS GXT 화면 파일의 생성자 라이프사이클(E0), 위젯 이벤트(E1..En), 모든 메서드 가시성 테이블, Grid Spec(TOBE 스타일), 버튼 목록을 정밀 추출합니다.
- **주요 옵션**:
  - `--ids`: E-id 목록 및 트리 구조만 간단히 출력
  - `--json`: JSON 구조로 출력
- **예시**:
  ```bash
  yunhee events src/main/java/.../Sys01_Tab_Company.java
  yunhee events Sys01_Tab_Company --ids
  ```

---

## 3. SQL 정합성 및 변경 감지 (Drift)

### `yunhee sql-check [src_root]`
MyBatis 매퍼 XML의 동적 SQL(`<if>`, `<choose>`, `<foreach>`)을 펼쳐 대상 DB에서 `psql EXPLAIN` 정합성 및 소스 간 SQL Drift를 검증합니다.
- **주요 옵션**:
  - `--tobe <DIR>`: TOBE 매퍼 디렉터리 경로 (TOBE SQL 정합성 및 Record DTO 매핑 검증 모드)
  - `--changed`: git diff (+untracked) 변경된 매퍼 XML만 검증
  - `--old <DIR> --new <DIR>`: 이전 소스와 새 소스 간 SQL Drift 검증 모드
  - `--db <DB>`: 검증 대상 DB명 (기본: `asseterpdb`)
- **예시**:
  ```bash
  yunhee sql-check ~/workspace26/Asset-OMS --db asseterpdb
  yunhee sql-check --tobe src/main/resources/mapper --changed
  ```

### `yunhee mapper-run <target>`
TOBE MyBatis 매퍼 statement를 직접 실행하고 AS-IS SQL 결과와 건수/데이터를 비교합니다.
- **주요 옵션**:
  - `-p, --param <key=val>`: 쿼리 파라미터
  - `--compare <ASIS_SQL_ID>`: 비교할 AS-IS SQL ID
  - `--rollback`: 트랜잭션 실행 후 롤백 (쓰기 쿼리 필수)
- **예시**:
  ```bash
  yunhee mapper-run backend/src/main/resources/mapper/SysRoleMapper.xml#selectRoles -p roleName=관리자
  ```

### `yunhee drift [screens...]`
소스 색인 또는 기준선(baseline) 대비 AS-IS 화면 및 의존 파일의 변경(drift)을 감지합니다.
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
