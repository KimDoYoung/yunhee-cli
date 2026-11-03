# fnd (펀드 / 기준정보 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `fnd` (펀드 / 기준정보 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/fnd/*`, `myApp/server/fnd/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`fnd##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`fnd` 도메인은 **펀드 / 기준정보 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **FND-01** | **공모주청약** | 공모주청약 관련 화면 및 처리 모듈 | 3개 화면 |
| **FND-02** | **기관정보관리** | 기관정보관리 관련 화면 및 처리 모듈 | 4개 화면 |
| **FND-03** | **기관정보관리(관리자)** | 기관정보관리(관리자) 관련 화면 및 처리 모듈 | 3개 화면 |
| **FND-04** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 10개 화면 |
| **FND-05** | **상품기획** | 상품기획 관련 화면 및 처리 모듈 | 4개 화면 |
| **FND-06** | **펀드관리** | 펀드관리 관련 화면 및 처리 모듈 | 10개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### FND-01. 공모주청약
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **공모주 수요예측** | `Fnd30_Tab_DemandOpr` | 1341 | 공모주 수요예측 신청화면 |
| 2 | **공모주청약 운용지시** | `Fnd30_Tab_Opr` | 1227 | 공모주청약 운용지시서 작성 |
| 3 | **공모주 참여계좌 관리** | `Fnd32_Tab_Account` | 1290 | 공모주 참여계좌 관리 |

### FND-02. 기관정보관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 4 | **수탁사정보 관리** | `Fnd03_Tab_Consignment` | 1051 | 수탁사정보 관리 |
| 5 | **사무수탁사정보 관리** | `Fnd06_Tab_OfficeWork` | 1052 | 사무수탁사정보 관리 |
| 6 | **발행기관정보 관리** | `Fnd07_Tab_IssuingEntity` | 1053 | 발행기관정보 관리 |
| 7 | **수탁은행정보 관리** | `Fnd09_Tab_TrustBank` | 1100 | 수탁은행정보 관리 |

### FND-03. 기관정보관리(관리자)
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 8 | **수탁사정보 관리(관리자)** | `Fnd03_Tab_ConsignmentManager` | 1102 | 수탁사정보 관리(관리자) |
| 9 | **사무수탁사정보 관리(관리자)** | `Fnd06_Tab_OfficeWorkManager` | 1094 | 사무수탁사정보 관리(관리자) |
| 10 | **수탁은행정보 관리(관리자)** | `Fnd09_Tab_TrustBankManager` | 1103 | 수탁은행정보 관리(관리자) |

### FND-04. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 11 | **문서분류** | `Fnd01_TabPage_FundCode` | - | 문서분류 기능 처리 |
| 12 | **펀드유형** | `Fnd01_Tab_FundInfoLoad` | - | 펀드유형 기능 처리 |
| 13 | **펀드유형** | `Fnd01_Tab_FundSearch_20240730` | - | 펀드유형 기능 처리 |
| 14 | **펀드조회** | `Fnd01_Tab_MultiFund` | - | 펀드조회 기능 처리 |
| 15 | **매매처코드** | `Fnd05_Tab_Memeco` | - | 매매처코드 기능 처리 |
| 16 | **조직명** | `Fnd08_Page_OrgAuth` | - | 조직명 기능 처리 |
| 17 | **문서분류** | `Fnd20_TabPage_Plan` | - | 문서분류 기능 처리 |
| 18 | **펀드별 일정목록** | `Fnd20_TabPage_PlanEmp` | - | 펀드별 일정목록 기능 처리 |
| 19 | **템플릿** | `Fnd31_Page_DemandOprFund` | - | 템플릿 기능 처리 |
| 20 | **템플릿** | `Fnd31_Page_OprFund` | - | 템플릿 기능 처리 |

### FND-05. 상품기획
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 21 | **신규기획펀드 등록** | `Fnd01_Tab_FundPlan` | 1046 | 신규기획펀드등록 (임시펀드 등록) |
| 22 | **신규기획펀드 권한설정** | `Fnd08_Tab_OrgAuthTempFund` | 1047 | 신규기획펀드 권한설정 (임시펀드권한 관리) |
| 23 | **상품기획일정 등록** | `Fnd20_Tab_Plan` | 1105 | 상품기획일정 등록 |
| 24 | **상품기획문서 등록** | `Fnd20_Tab_PlanEmp` | 1106 | 상품기획문서 등록 |

### FND-06. 펀드관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 25 | **펀드 등록 및 변경** | `Fnd01_Tab_FundCode` | 1048 | 펀드정보 관리 |
| 26 | **펀드 조회(변경이력)** | `Fnd01_Tab_FundIcamHistory` | 1327 | 펀드 조회(변경이력) 기능 처리 |
| 27 | **펀드 조회** | `Fnd01_Tab_FundSearch` | 1049 | 펀드정보 조회 |
| 28 | **펀드 조회 (ICAM)** | `Fnd01_Tab_FundSearchIcam` | 1099 | ICAM에서 관리하는 펀드 상세조회 |
| 29 | **펀드 권한설정** | `Fnd08_Tab_OrgAuth` | 1050 | 펀드별 권한 등록 |
| 30 | **펀드별 자산 조회(ICAM)** | `Fnd10_Tab_RelateAst` | 1123 | 펀드별 운용자산 |
| 31 | **자산별 펀드 조회(ICAM)** | `Fnd10_Tab_RelateFnd` | 1124 | 자산별 운용펀드 |
| 32 | **펀드보유주식등록(타사무)** | `Fnd11_Tab_BookExtr` | 1426 | 타사무수탁사에서 관리되는 펀드의 상장주식 보유종목을 등록합니다. (임직원매매 펀드보유종목 체크용) |
| 33 | **펀드규약** | `Fnd25_Tab_FundTerms` | 1504 | 펀드규약 기능 처리 |
| 34 | **펀드규약 등록** | `Fnd25_Tab_FundTermsManager` | 1503 | 펀드규약 등록 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/fnd/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Fnd00_Fund` | Fnd00_Fund 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Fnd01_FundCode` | Fnd01_FundCode 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Fnd02_FundInfo` | Fnd02_FundInfo 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Fnd03_Consignment` | Fnd03_Consignment 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Fnd05_Memeco` | Fnd05_Memeco 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Fnd06_OfficeWork` | Fnd06_OfficeWork 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Fnd06_OfficeWorkPDF` | Fnd06_OfficeWorkPDF 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Fnd07_IssuingEntity` | Fnd07_IssuingEntity 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Fnd08_OrgAuth` | Fnd08_OrgAuth 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Fnd09_TrustBank` | Fnd09_TrustBank 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Fnd10_Book` | Fnd10_Book 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Fnd11_BookExtr` | Fnd11_BookExtr 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Fnd20_Plan` | Fnd20_Plan 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Fnd25_Terms` | Fnd25_Terms 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Fnd26_TermsDetail` | Fnd26_TermsDetail 비즈니스 로직 및 RPC 서비스 처리 |
| 16 | `Fnd30_Opr` | Fnd30_Opr 비즈니스 로직 및 RPC 서비스 처리 |
| 17 | `Fnd31_OprFund` | Fnd31_OprFund 비즈니스 로직 및 RPC 서비스 처리 |
| 18 | `Fnd32_Account` | Fnd32_Account 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/fnd/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `fnd00_fund.xml` | `fnd00_fund` 테이블 관련 쿼리 매핑 |
| 2 | `fnd01_fund_code.xml` | `fnd01_fund_code` 테이블 관련 쿼리 매핑 |
| 3 | `fnd02_fund_info.xml` | `fnd02_fund_info` 테이블 관련 쿼리 매핑 |
| 4 | `fnd03_consignment.xml` | `fnd03_consignment` 테이블 관련 쿼리 매핑 |
| 5 | `fnd04_sales.xml` | `fnd04_sales` 테이블 관련 쿼리 매핑 |
| 6 | `fnd05_memeco.xml` | `fnd05_memeco` 테이블 관련 쿼리 매핑 |
| 7 | `fnd06_office_work.xml` | `fnd06_office_work` 테이블 관련 쿼리 매핑 |
| 8 | `fnd07_issuing_entity.xml` | `fnd07_issuing_entity` 테이블 관련 쿼리 매핑 |
| 9 | `fnd08_org_auth.xml` | `fnd08_org_auth` 테이블 관련 쿼리 매핑 |
| 10 | `fnd09_trust_bank.xml` | `fnd09_trust_bank` 테이블 관련 쿼리 매핑 |
| 11 | `fnd10_book.xml` | `fnd10_book` 테이블 관련 쿼리 매핑 |
| 12 | `fnd11_book_extr.xml` | `fnd11_book_extr` 테이블 관련 쿼리 매핑 |
| 13 | `fnd20_plan.xml` | `fnd20_plan` 테이블 관련 쿼리 매핑 |
| 14 | `fnd25_terms.xml` | `fnd25_terms` 테이블 관련 쿼리 매핑 |
| 15 | `fnd26_terms_detail.xml` | `fnd26_terms_detail` 테이블 관련 쿼리 매핑 |
| 16 | `fnd30_opr.xml` | `fnd30_opr` 테이블 관련 쿼리 매핑 |
| 17 | `fnd31_opr_fund.xml` | `fnd31_opr_fund` 테이블 관련 쿼리 매핑 |
| 18 | `fnd32_account.xml` | `fnd32_account` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `fnd01_fund_code` | 펀드/상품코드정보 | 10 | `fnd01_fund_code_id` |
| 2 | `fnd02_fund_info` | 펀드/상품정보 | 44 | `fnd02_fund_info_id` |
| 3 | `fnd03_consignment` | 수탁사 | 16 | `fnd03_consignment_id` |
| 4 | `fnd04_sales` | 판매사 | 6 | `fnd04_sales_id` |
| 5 | `fnd06_office_work` | 사무수탁사 | 17 | `fnd06_office_work_id` |
| 6 | `fnd07_issuing_entity` | 발행기관 | 10 | `fnd07_issuing_entity_id` |
| 7 | `fnd08_org_auth` | - | 5 | `fnd08_org_auth_id` |
| 8 | `fnd09_trust_bank` | 수탁은행 | 16 | `fnd09_trust_bank_id` |
| 9 | `fnd10_book` | 펀드별 운용자산 | 18 | `fnd10_book_id` |
| 10 | `fnd11_book_extr` | 펀드별 운용자산(외부) | 8 | `fnd11_book_extr_id` |
| 11 | `fnd20_plan` | 기획펀드일정 | 9 | `fnd20_plan_id` |
| 12 | `fnd25_terms` | 펀드규약 | 7 | `fnd25_terms_id` |
| 13 | `fnd26_terms_detail` | 펀드규약_상세 | 10 | `fnd26_terms_detail_id` |
| 14 | `fnd30_opr` | 펀드회계 운용지시 | 26 | `fnd30_opr_id` |
| 15 | `fnd31_opr_fund` | 펀드회계 운용지시(펀드별) | 10 | `fnd31_opr_fund_id` |
| 16 | `fnd32_account` | 운용사명의 계좌관리(펀드에서 공모주 참여시 운용사명의 계좌 사용) | 15 | `fnd32_account_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **34개**
- **UI 컴포넌트 수**: 총 61개 (Tab/Page: 34개, Lookup/Popup/기타: 27개)
- **서버 서비스 클래스 수**: **18개**
- **MyBatis 매퍼 XML 수**: **18개**
- **DB 테이블 수**: **16개**
