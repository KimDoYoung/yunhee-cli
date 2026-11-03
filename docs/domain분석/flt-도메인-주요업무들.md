# flt (임직원 자기매매 통제) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `flt` (임직원 자기매매 통제) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/flt/*`, `myApp/server/flt/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`flt##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`flt` 도메인은 **임직원 자기매매 통제** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **FLT-01** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 6개 화면 |
| **FLT-02** | **내부통제** | 내부통제 관련 화면 및 처리 모듈 | 1개 화면 |
| **FLT-03** | **임직원매매** | 임직원매매 관련 화면 및 처리 모듈 | 10개 화면 |
| **FLT-04** | **임직원매매(준감인)** | 임직원매매(준감인) 관련 화면 및 처리 모듈 | 9개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### FLT-01. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **신고일자** | `Flt03_TabPage_Account` | - | 신고일자 기능 처리 |
| 2 | **폐쇄취소** | `Flt06_TabPage_AccountClose` | - | 폐쇄취소 기능 처리 |
| 3 | **보고구분** | `Flt10_TabPage_Appr` | - | 보고구분 기능 처리 |
| 4 | **이름** | `Flt10_TabPage_ReportPerson` | - | 이름 기능 처리 |
| 5 | **인적사항** | `Flt10_TabPage_TrList` | - | 인적사항 기능 처리 |
| 6 | **승인** | `Flt10_Tab_PreApproveAdd` | - | 승인 기능 처리 |

### FLT-02. 내부통제
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 7 | **임직원매매 종목유형관리** | `Flt05_Tab_ItemTypeAdmin` | 1267 | 자기매매 종목유형설정(관리자) |

### FLT-03. 임직원매매
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 8 | **화면사용순서** | `Flt00_Tab_Info` | 1369 | 화면사용순서 기능 처리 |
| 9 | **계좌신고** | `Flt03_Tab_AccountReport` | 1125 | 계좌 개설 및 폐쇄 신고 |
| 10 | **계좌대체** | `Flt10_Tab_AcntTransfer` | 1371 | 계좌대체 기능 처리 |
| 11 | **매수 사전신고** | `Flt10_Tab_BuyReport` | 1126 | 자기매매 사전신고(매수) |
| 12 | **정기보고** | `Flt10_Tab_RealTransaction` | 1142 | 자기매매 실거래 보고 |
| 13 | **권리행사/기타입출고** | `Flt10_Tab_RightsExercise` | 1372 | 권리행사로 인한 입고처리 및 기타 입출고 처리 |
| 14 | **매도 사전신고** | `Flt10_Tab_SellReport` | 1127 | 자기매매 사전신고(매도) |
| 15 | **매매내역조회** | `Flt10_Tab_TrList` | 1144 | 자기매매 매매내역 조회 |
| 16 | **위반내역조회** | `Flt10_Tab_ViolateUser` | 1370 | 자기매매 위반내역 |
| 17 | **보유내역조회** | `Flt11_Tab_BookList` | 1143 | 자기매매 보유내역 조회 |

### FLT-04. 임직원매매(준감인)
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 18 | **기준관리** | `Flt01_Tab_CompanyStd` | 1145 | 임직원 자기매매 기준관리 |
| 19 | **임직원매매현황** | `Flt02_Tab_EmpInfo` | 1351 | 임직원매매 정보조회 |
| 20 | **계좌신고현황** | `Flt03_Tab_AccountAdmin` | 1488 | 계좌신고현황 기능 처리 |
| 21 | **책임자보고** | `Flt10_Tab_CeoReport` | 1464 | 임직원 자기매매 대표이사 보고용 화면 |
| 22 | **정기보고현황** | `Flt10_Tab_EmpAppr` | 1152 | 자기매매 주기보고현황 |
| 23 | **사전승인** | `Flt10_Tab_PreApprove` | 1128 | 자기매매 사전승인 |
| 24 | **매매내역조회** | `Flt10_Tab_TrListAdmin` | 1153 | 임직원 매매내역(관리자) |
| 25 | **위반내역조회** | `Flt10_Tab_Violate` | 1157 | 위반내역조회 기능 처리 |
| 26 | **보유내역조회** | `Flt11_Tab_BookListAdmin` | 1154 | 임직원매매 보유내역(관리자) |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/flt/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Flt01_CompanyStd` | Flt01_CompanyStd 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Flt02_Emp` | Flt02_Emp 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Flt03_Account` | Flt03_Account 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Flt04_Oath` | Flt04_Oath 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Flt05_ItemType` | Flt05_ItemType 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Flt06_AccountClose` | Flt06_AccountClose 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Flt07_FamilyConsent` | Flt07_FamilyConsent 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Flt08_BuyLockup` | Flt08_BuyLockup 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Flt10_Tr` | Flt10_Tr 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Flt11_Book` | Flt11_Book 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Flt12_BookMonth` | Flt12_BookMonth 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Flt13_BookInit` | Flt13_BookInit 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Flt14_RelateAppr` | Flt14_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Flt15_TrStatus` | Flt15_TrStatus 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Flt16_ExceptPerson` | Flt16_ExceptPerson 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/flt/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `flt01_company_std.xml` | `flt01_company_std` 테이블 관련 쿼리 매핑 |
| 2 | `flt02_emp.xml` | `flt02_emp` 테이블 관련 쿼리 매핑 |
| 3 | `flt03_account.xml` | `flt03_account` 테이블 관련 쿼리 매핑 |
| 4 | `flt04_oath.xml` | `flt04_oath` 테이블 관련 쿼리 매핑 |
| 5 | `flt05_item_type.xml` | `flt05_item_type` 테이블 관련 쿼리 매핑 |
| 6 | `flt06_account_close.xml` | `flt06_account_close` 테이블 관련 쿼리 매핑 |
| 7 | `flt07_family_consent.xml` | `flt07_family_consent` 테이블 관련 쿼리 매핑 |
| 8 | `flt08_buy_lockup.xml` | `flt08_buy_lockup` 테이블 관련 쿼리 매핑 |
| 9 | `flt09_fund_item.xml` | `flt09_fund_item` 테이블 관련 쿼리 매핑 |
| 10 | `flt10_tr.xml` | `flt10_tr` 테이블 관련 쿼리 매핑 |
| 11 | `flt11_book.xml` | `flt11_book` 테이블 관련 쿼리 매핑 |
| 12 | `flt12_book_month.xml` | `flt12_book_month` 테이블 관련 쿼리 매핑 |
| 13 | `flt13_book_init.xml` | `flt13_book_init` 테이블 관련 쿼리 매핑 |
| 14 | `flt14_relate_appr.xml` | `flt14_relate_appr` 테이블 관련 쿼리 매핑 |
| 15 | `flt15_tr_status.xml` | `flt15_tr_status` 테이블 관련 쿼리 매핑 |
| 16 | `flt16_except_person.xml` | `flt16_except_person` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `flt01_company_std` | 임직원매매 기준관리 - 회사 | 21 | `flt01_company_std_id` |
| 2 | `flt02_emp` | 임직원매매 기준관리 - 직원별 | 6 | `flt02_emp_id` |
| 3 | `flt03_account` | 임직원 계좌 | 14 | `flt03_account_id` |
| 4 | `flt04_oath` | 임직원 서약서 | 6 | `flt04_oath_id` |
| 5 | `flt05_item_type` | 자기매매 종목유형정보 | 11 | `flt05_item_type_id` |
| 6 | `flt06_account_close` | 임직원 폐쇄계좌 | 5 | `flt06_account_close_id` |
| 7 | `flt07_family_consent` | 가족금융거래정보 이용동의서 | 2 | `flt07_family_consent_id` |
| 8 | `flt08_buy_lockup` | 매수제한주식종목 | 6 | `flt08_buy_lockup_id` |
| 9 | `flt09_fund_item` | 임직원매매체크용-펀드보유주식 | 6 | `flt09_fund_item_id` |
| 10 | `flt10_tr` | 임직원 금융상품 매매 | 32 | `flt10_tr_id` |
| 11 | `flt11_book` | 임직원 금융상품 보유내역 | 14 | `flt11_book_id` |
| 12 | `flt12_book_month` | 임직원 금융상품 보유내역(월말잔고 직접입력) | 9 | `flt12_book_month_id` |
| 13 | `flt13_book_init` | 임직원 금융상품 보유내역(최초원장) | 11 | `flt13_book_init_id` |
| 14 | `flt14_relate_appr` | 임직원매매 정기보고 상신문서 연결 | 5 | `flt14_relate_appr_id` |
| 15 | `flt15_tr_status` | 임직원매매현황 | 5 | `flt15_tr_status_id` |
| 16 | `flt90_tr_back` | 임직원 금융상품 매매(백업) | 35 | `flt90_tr_back_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **26개**
- **UI 컴포넌트 수**: 총 51개 (Tab/Page: 26개, Lookup/Popup/기타: 25개)
- **서버 서비스 클래스 수**: **15개**
- **MyBatis 매퍼 XML 수**: **16개**
- **DB 테이블 수**: **16개**
