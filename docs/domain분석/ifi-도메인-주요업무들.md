# ifi (대외 인터페이스 / OpenAPI 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `ifi` (대외 인터페이스 / OpenAPI 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/ifi/*`, `myApp/server/ifi/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`ifi##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`ifi` 도메인은 **대외 인터페이스 / OpenAPI 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **IFI-01** | **I/F 관리** | I/F 관리 관련 화면 및 처리 모듈 | 3개 화면 |
| **IFI-02** | **OpenAPI** | OpenAPI 관련 화면 및 처리 모듈 | 3개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### IFI-01. I/F 관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **I/F 설정** | `Ifi90_Tab_Config` | 1445 | I/F 설정 기능 처리 |
| 2 | **파일송수신관리** | `Ifi95_Tab_FileConfig` | 1449 | 파일송수신관리 기능 처리 |
| 3 | **파일레이아웃** | `Ifi96_Tab_FileLayout` | 1450 | 파일레이아웃 기능 처리 |

### IFI-02. OpenAPI
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 4 | **고객사Key 등록** | `Ifi01_Tab_ApiCompany` | 1448 | 고객사Key 등록 기능 처리 |
| 5 | **API 관리** | `Ifi91_Tab_ApiConfig` | 1446 | API 관리 기능 처리 |
| 6 | **API 레이아웃** | `Ifi92_Tab_ApiLayout` | 1447 | API 레이아웃 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/ifi/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Ifi90_Config` | Ifi90_Config 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/ifi/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `ifi21_api_data.xml` | `ifi21_api_data` 테이블 관련 쿼리 매핑 |
| 2 | `ifi30_fund.xml` | `ifi30_fund` 테이블 관련 쿼리 매핑 |
| 3 | `ifi34_stk.xml` | `ifi34_stk` 테이블 관련 쿼리 매핑 |
| 4 | `ifi90_config.xml` | `ifi90_config` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `ifi01_company_api` | AssetAPI고객사정보 | 8 | `ifi01_company_api_id` |
| 2 | `ifi05_job_schedule` | 작업스케줄 관리 | 7 | `ifi05_job_schedule_id` |
| 3 | `ifi10_law` | 인터페이스_법규정보 | 23 | `ifi10_law_id` |
| 4 | `ifi11_law_record` | 인터페이스_법규정보 이력 | 13 | `ifi11_law_record_id` |
| 5 | `ifi20_dart_corp` | 발행기관정보(DART,KRX) | 20 | `ifi20_dart_corp_id` |
| 6 | `ifi21_api_data` | API수집데이터 | 11 | `ifi21_api_data_id` |
| 7 | `ifi29_am_corp_mapping` | 수신파일-사무수탁사별 운용사 맵핑 | 8 | `ifi29_am_corp_mapping_id` |
| 8 | `ifi30_fund` | 수신파일-펀드정보 | 38 | `ifi30_fund_id` |
| 9 | `ifi31_fund_fee` | 수신파일-일별펀드보수 | 12 | `ifi31_fund_fee_id` |
| 10 | `ifi32_fund_price` | 수신파일-일별펀드기준가 | 18 | `ifi32_fund_price_id` |
| 11 | `ifi33_adv` | 수신파일-일임(자문)계좌정보 | 13 | `ifi33_adv_id` |
| 12 | `ifi34_stk` | 수신파일-보유상장주식 | 11 | `ifi34_stk_id` |
| 13 | `ifi90_config` | I/F설정정보 | 18 | `ifi90_config_id` |
| 14 | `ifi91_config_api` | API관리 | 13 | `ifi91_config_api_id` |
| 15 | `ifi92_api_layout` | API레이아웃 | 15 | `ifi92_api_layout_id` |
| 16 | `ifi95_config_file` | 파일송수신관리 | 10 | `ifi95_config_file_id` |
| 17 | `ifi96_file_layout` | 파일레이아웃 | 10 | `ifi96_file_layout_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **6개**
- **UI 컴포넌트 수**: 총 2개 (Tab/Page: 1개, Lookup/Popup/기타: 1개)
- **서버 서비스 클래스 수**: **1개**
- **MyBatis 매퍼 XML 수**: **4개**
- **DB 테이블 수**: **17개**
