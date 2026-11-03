# dbm (DB 테이블 명세 / RD·PDF 도구) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `dbm` (DB 테이블 명세 / RD·PDF 도구) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/dbm/*`, `myApp/server/dbm/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`dbm##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`dbm` 도메인은 **DB 테이블 명세 / RD·PDF 도구** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **DBM-01** | **기타** | 기타 관련 화면 및 처리 모듈 | 2개 화면 |
| **DBM-02** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 7개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### DBM-01. 기타
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **Table Spec,(Model)Properties** | `Dbm01_Tab_TabComments` | 1081 | Table Spec,(Model)Properties |
| 2 | **PDF 생성 테스트** | `Dbm10_Tab_MakePdf` | 1108 | PDF 생성 테스트 |

### DBM-02. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **오류** | `Dbm01_Lookup_Tables` | - | 오류 기능 처리 |
| 4 | **Dbm01_RDPage_ColComments** | `Dbm01_RDPage_ColComments` | - | Dbm01_RDPage_ColComments 기능 처리 |
| 5 | **Dbm01_RD_TabComments** | `Dbm01_RD_TabComments` | - | Dbm01_RD_TabComments 기능 처리 |
| 6 | **Dbm02_TabPage_ColComments** | `Dbm02_TabPage_ColComments` | - | Dbm02_TabPage_ColComments 기능 처리 |
| 7 | **Dbm99_Tab_RDTest** | `Dbm99_Tab_RDTest` | - | Dbm99_Tab_RDTest 기능 처리 |
| 8 | **고객명** | `TabPage_Company` | - | 고객명 기능 처리 |
| 9 | **기관구분** | `Tab_RD` | - | 기관구분 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/dbm/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Dbm00_DDLRun` | Dbm00_DDLRun 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Dbm01_TabComments` | Dbm01_TabComments 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Dbm02_ColComments` | Dbm02_ColComments 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Dbm02_ColCommentsPDF` | Dbm02_ColCommentsPDF 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Dbm03_TabColumns` | Dbm03_TabColumns 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/dbm/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `dbm01_tab_comments.xml` | `dbm01_tab_comments` 테이블 관련 쿼리 매핑 |
| 2 | `dbm02_col_comments.xml` | `dbm02_col_comments` 테이블 관련 쿼리 매핑 |
| 3 | `dbm03_tab_columns.xml` | `dbm03_tab_columns` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
- 전용 도메인 테이블 없음 (공통 또는 타 도메인 참조)

---

## 4. 요약 통계

- **총 세부 업무 화면**: **9개**
- **UI 컴포넌트 수**: 총 10개 (Tab/Page: 9개, Lookup/Popup/기타: 1개)
- **서버 서비스 클래스 수**: **5개**
- **MyBatis 매퍼 XML 수**: **3개**
- **DB 테이블 수**: **0개**
