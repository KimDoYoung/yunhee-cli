# icam (ICAM 연계 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `icam` (ICAM 연계 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/icam/*`, `myApp/server/icam/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`icam##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`icam` 도메인은 **ICAM 연계 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **ICAM-01** | **ICAM** | ICAM 관련 화면 및 처리 모듈 | 8개 화면 |
| **ICAM-02** | **ICAM 계약사관리** | ICAM 계약사관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **ICAM-03** | **ICAM 사용자ID 관리** | ICAM 사용자ID 관리 관련 화면 및 처리 모듈 | 4개 화면 |
| **ICAM-04** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 2개 화면 |
| **ICAM-05** | **사무보수관리** | 사무보수관리 관련 화면 및 처리 모듈 | 3개 화면 |
| **ICAM-06** | **운용현황** | 운용현황 관련 화면 및 처리 모듈 | 3개 화면 |
| **ICAM-07** | **펀드운용보수관리** | 펀드운용보수관리 관련 화면 및 처리 모듈 | 3개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### ICAM-01. ICAM
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **ICAM 연계정보구분 관리** | `Icam01_Tab_DataInfo` | 1095 | ICAM 연계정보구분 관리 |
| 2 | **ICAM 현금흐름** | `Icam02_Tab_CashFlow` | 1433 | ICAM 현금흐름 |
| 3 | **ICAM 연계정보** | `Icam02_Tab_Data` | 1101 | ICAM 연계정보(기일 등) |
| 4 | **ICAM 연계정보(관리자용)** | `Icam02_Tab_DataAdmin` | 1109 | ICAM 연계정보(관리자용) |
| 5 | **ICAM 펀드정보** | `Icam03_Tab_Fund` | 1096 | ICAM 펀드정보 가져오기 |
| 6 | **ICAM 보수(관리자용)** | `Icam10_Tab_FeeAdmin` | 1203 | ICAM 보수(관리자용) |
| 7 | **ICAM DB Source Get** | `Icam50_Tab_DbSource` | 1269 | ICAM DB Source Get (Function, Procedure, Trigger) |
| 8 | **작업용** | `Icam99_Tab_Test` | 1097 | 작업용 |

### ICAM-02. ICAM 계약사관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 9 | **펀드예정일정보** | `Icam00_Tab_FundExpectDate` | 1374 | 펀드 설정/상환 예정일 정보 조회 (ICAM 2700 화면) |

### ICAM-03. ICAM 사용자ID 관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 10 | **사용자ID 처리결과 등록** | `Icam55_Tab_UserApprResult` | 1316 | ICAM 사용자ID 신청서 처리결과 등록 |
| 11 | **사용자ID 신청서 작성** | `Icam55_Tab_UserRegAppr` | 1314 | ICAM 사용자ID 신청서 작성 test112 |
| 12 | **미사용ID 기록관리** | `Icam55_Tab_UserStopAuth` | 1317 | ICAM 미사용ID 기록 관리 TE211111 |
| 13 | **미사용ID 권한정지 신청** | `Icam55_Tab_UserStopAuthAppr` | 1315 | ICAM 미사용 사용자ID 권한정지 신청서 작성 |

### ICAM-04. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 14 | **예정일자** | `Icam02_TabPage_CashFlowDate` | - | 예정일자 기능 처리 |
| 15 | **종목코드** | `Icam02_TabPage_CashFlowItem` | - | 종목코드 기능 처리 |

### ICAM-05. 사무보수관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 16 | **ICAM 펀드보수 발생내역** | `Icam10_Tab_OfficeMngFee` | 1199 | ICAM 사무관리 펀드보수 적요별 내역 |
| 17 | **펀드별 보수입금계좌 등록** | `Icam11_Tab_OfficeMngFeeDeposit` | 1204 | 펀드별 사무관리보수 입금계좌 등록 |
| 18 | **ICAM 펀드보수 월말잔액** | `Icam12_Tab_OfficeMngFeeBook` | 1200 | ICAM 사무관리 펀드보수 월말잔액 |

### ICAM-06. 운용현황
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 19 | **펀드운용현황(펀드합계)** | `Icam06_Tab_FundOperateStatus` | 1323 | 펀드운용현황(펀드합계)  - ICAM TR 9985 |
| 20 | **펀드별 기준가 현황** | `Icam06_Tab_FundPrice` | 1475 | 펀드별 기준가 현황 |
| 21 | **펀드별 발생보수현황** | `Icam10_Tab_CurrentFeeByFund` | 1268 | 펀드별 발생보수현황 |

### ICAM-07. 펀드운용보수관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 22 | **ICAM 운용보수 발생내역** | `Icam10_Tab_FundMngFee` | 1214 | ICAM 펀드운용보수 적요별 발생내역 |
| 23 | **운용보수 입금계좌 관리** | `Icam11_Tab_FundMngFeeDeposit` | 1217 | 펀드별 운용보수  입금계좌 관리 |
| 24 | **ICAM 운용보수 월말잔액** | `Icam12_Tab_FundMngFeeBook` | 1215 | ICAM 운용보수 월말잔액 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/icam/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Icam00_Common` | Icam00_Common 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Icam01_DataInfo` | Icam01_DataInfo 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Icam02_Data` | Icam02_Data 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Icam03_Fund` | Icam03_Fund 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Icam06_FundBook` | Icam06_FundBook 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Icam10_Fee` | Icam10_Fee 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Icam11_FeeDeposit` | Icam11_FeeDeposit 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Icam12_FeeBook` | Icam12_FeeBook 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Icam13_FeeBookCheck` | Icam13_FeeBookCheck 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Icam20_Price` | Icam20_Price 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Icam50_Source` | Icam50_Source 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Icam55_IcamUser` | Icam55_IcamUser 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Icam99_Test` | Icam99_Test 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/icam/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `icam00_common.xml` | `icam00_common` 테이블 관련 쿼리 매핑 |
| 2 | `icam01_data_info.xml` | `icam01_data_info` 테이블 관련 쿼리 매핑 |
| 3 | `icam02_data.xml` | `icam02_data` 테이블 관련 쿼리 매핑 |
| 4 | `icam03_fund.xml` | `icam03_fund` 테이블 관련 쿼리 매핑 |
| 5 | `icam06_fund_book.xml` | `icam06_fund_book` 테이블 관련 쿼리 매핑 |
| 6 | `icam10_fee.xml` | `icam10_fee` 테이블 관련 쿼리 매핑 |
| 7 | `icam11_fee_deposit.xml` | `icam11_fee_deposit` 테이블 관련 쿼리 매핑 |
| 8 | `icam12_fee_book.xml` | `icam12_fee_book` 테이블 관련 쿼리 매핑 |
| 9 | `icam13_fee_book_check.xml` | `icam13_fee_book_check` 테이블 관련 쿼리 매핑 |
| 10 | `icam20_price.xml` | `icam20_price` 테이블 관련 쿼리 매핑 |
| 11 | `icam25_ipo.xml` | `icam25_ipo` 테이블 관련 쿼리 매핑 |
| 12 | `icam50_source.xml` | `icam50_source` 테이블 관련 쿼리 매핑 |
| 13 | `icam55_icam_user.xml` | `icam55_icam_user` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `icam01_data_info` | ICAM 데이터 정보기본 | 7 | `icam01_data_info_id` |
| 2 | `icam02_data` | ICAM 데이터 | 22 | `icam02_data_id` |
| 3 | `icam03_fund` | ICAM 펀드기본 | 41 | `icam03_fund_id` |
| 4 | `icam04_item` | ICAM 종목기본 | 10 | `icam04_item_id` |
| 5 | `icam05_fund_item` | ICAM 펀드별 보유종목 | 7 | `icam05_fund_item_id` |
| 6 | `icam06_fund_book` | ICMA 펀드원장 | 22 | `icam06_fund_book_id` |
| 7 | `icam10_fee` | ICAM펀드보수 당일발생내역 | 20 | `icam10_fee_id` |
| 8 | `icam11_fee_deposit` | ICAM펀드보수 입금계좌 | 7 | `icam11_fee_deposit_id` |
| 9 | `icam12_fee_book` | ICAM펀드보수 월말잔액 | 15 | `icam12_fee_book_id` |
| 10 | `icam13_fee_book_check` | ICAM펀드보수 월말 잔액대사 결과 | 7 | `icam13_fee_book_check_id` |
| 11 | `icam20_price` | ICAM시세정보 | 13 | `icam20_price_id` |
| 12 | `icam25_ipo` | ICMA공모주 | 10 | `icam25_ipo_id` |
| 13 | `icam50_source` | ICAM DB소스 | 9 | `icam50_source_id` |
| 14 | `icam51_source_tmp` | ICAM all_source | 9 | `icam51_source_tmp_id` |
| 15 | `icam55_icam_user` | ICAM 사용자ID 관리 | 22 | `icam55_icam_user_id` |
| 16 | `icam90_fee_back` | ICAM펀드보수 당일발생내역(백업) | 23 | `icam90_fee_back_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **24개**
- **UI 컴포넌트 수**: 총 39개 (Tab/Page: 24개, Lookup/Popup/기타: 15개)
- **서버 서비스 클래스 수**: **13개**
- **MyBatis 매퍼 XML 수**: **13개**
- **DB 테이블 수**: **16개**
