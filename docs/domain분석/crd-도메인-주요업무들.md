# crd (법인카드 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `crd` (법인카드 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/crd/*`, `myApp/server/crd/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`crd##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`crd` 도메인은 **법인카드 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **CRD-01** | **법인카드 등록** | 법인카드 등록 관련 화면 및 처리 모듈 | 1개 화면 |
| **CRD-02** | **법인카드관리** | 법인카드관리 관련 화면 및 처리 모듈 | 3개 화면 |
| **CRD-03** | **자산&경영** | 자산&경영 관련 화면 및 처리 모듈 | 1개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### CRD-01. 법인카드 등록
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **법인카드 내역 업로드** | `Crd02_Tab_DataUpload` | 1479 | 법인카드 내역 업로드 기능 처리 |

### CRD-02. 법인카드관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 2 | **(X)법인카드 내역 복사** | `Crd00_Tab_SlipCopy` | 1040 | 내역 복사 |
| 3 | **법인카드 및 사용자등록** | `Crd01_Tab_Card` | 1038 | 법인카드 및 사용자등록 |
| 4 | **(X)법인카드 내역 관리** | `Crd05_Tab_Slip` | 1041 | 내역 관리 |

### CRD-03. 자산&경영
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 5 | **법인카드 업로드 기초자료(관리자)** | `Crd10_Tab_ExcelCompanyAdmin` | 1352 | 카드업로드 기초자료 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/crd/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Cev05_CDPPDF` | Cev05_CDPPDF 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Crd01_Card` | Crd01_Card 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Crd02_Data` | Crd02_Data 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Crd03_Trans` | Crd03_Trans 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Crd10_ExcelCompany` | Crd10_ExcelCompany 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Crd11_ExcelCode` | Crd11_ExcelCode 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `CreateChart01` | CreateChart01 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `SpiderWebPlotPatch` | SpiderWebPlotPatch 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/crd/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `crd01_card.xml` | `crd01_card` 테이블 관련 쿼리 매핑 |
| 2 | `crd02_data.xml` | `crd02_data` 테이블 관련 쿼리 매핑 |
| 3 | `crd03_trans.xml` | `crd03_trans` 테이블 관련 쿼리 매핑 |
| 4 | `crd10_excel_company.xml` | `crd10_excel_company` 테이블 관련 쿼리 매핑 |
| 5 | `crd11_excel_code.xml` | `crd11_excel_code` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `crd01_card` | 법인카드관리 | 12 | `crd01_card_id` |
| 2 | `crd02_data` | 법인카드내역 | 27 | `crd02_data_id` |
| 3 | `crd03_trans` | 법인카드 관리자 | 7 | `crd03_trans_id` |
| 4 | `crd05_slip_backup` | (사용안함) | 20 | `crd05_slip_id` |
| 5 | `crd06_guest_backup` | (사용안함) | 6 | `crd06_guest_id` |
| 6 | `crd10_excel_company` | - | 4 | `crd10_excel_company_id` |
| 7 | `crd10_slip_backup` | 법인카드내역(사용안함) | 27 | `crd10_slip_id` |
| 8 | `crd11_excel_code` | - | 6 | `crd11_excel_code_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **5개**
- **UI 컴포넌트 수**: 총 9개 (Tab/Page: 3개, Lookup/Popup/기타: 6개)
- **서버 서비스 클래스 수**: **8개**
- **MyBatis 매퍼 XML 수**: **5개**
- **DB 테이블 수**: **8개**
