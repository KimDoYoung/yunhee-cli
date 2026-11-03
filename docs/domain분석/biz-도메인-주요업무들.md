# biz (이익제공(수령) / 사업비·계약사) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `biz` (이익제공(수령) / 사업비·계약사) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/biz/*`, `myApp/server/biz/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`biz##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`biz` 도메인은 **이익제공(수령) / 사업비·계약사** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **BIZ-01** | **ERP 계약사관리** | ERP 계약사관리 관련 화면 및 처리 모듈 | 2개 화면 |
| **BIZ-02** | **ICAM 계약사관리** | ICAM 계약사관리 관련 화면 및 처리 모듈 | 2개 화면 |
| **BIZ-03** | **기타** | 기타 관련 화면 및 처리 모듈 | 1개 화면 |
| **BIZ-04** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 14개 화면 |
| **BIZ-05** | **법인카드관리** | 법인카드관리 관련 화면 및 처리 모듈 | 4개 화면 |
| **BIZ-06** | **이익제공(수령)현황** | 이익제공(수령)현황 관련 화면 및 처리 모듈 | 10개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### BIZ-01. ERP 계약사관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **AssetERP 계약사관리** | `Biz51_Tab_ErpContCorp` | 1402 | AssetERP 계약사관리 |
| 2 | **AssetERP 사용료청구** | `Biz55_Tab_ErpFeeCharge` | 1403 | AssetERP 사용료청구 기능 처리 |

### BIZ-02. ICAM 계약사관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **ICAM 계약사 관리** | `Biz10_Tab_ContCorp` | 1209 | 계약사 관리 |
| 4 | **최저보수 청구** | `Biz20_Tab_FeeCharge` | 1210 | 최저보수 청구 |

### BIZ-03. 기타
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 5 | **기준가 정정내역 보고** | `Biz60_Tab_FundPriceModiReport` | 1505 | 기준가 정정내역 보고 기능 처리 |

### BIZ-04. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 6 | **제공/수령** | `Biz01_TabPage_CompanyYear` | - | 제공/수령 기능 처리 |
| 7 | **사용자** | `Biz01_TabPage_EntertmExpenseHistory` | - | 사용자 기능 처리 |
| 8 | **상대처 관리 바로가기** | `Biz01_TabPage_List` | - | 상대처 관리 바로가기 기능 처리 |
| 9 | **상신** | `Biz01_TabPage_MonthEntertmExpense` | - | 상신 기능 처리 |
| 10 | **제공/수령** | `Biz01_TabPage_PersonDay` | - | 제공/수령 기능 처리 |
| 11 | **제공/수령** | `Biz01_TabPage_PersonYear` | - | 제공/수령 기능 처리 |
| 12 | **회사명** | `Biz02_TabPage_CompanyEntertmExpense` | - | 회사명 기능 처리 |
| 13 | **자동연장** | `Biz11_TabPage_ContHistory` | - | 자동연장 기능 처리 |
| 14 | **운용사명** | `Biz13_Page_WithCorp` | - | 운용사명 기능 처리 |
| 15 | **운용사코드 등록** | `Biz13_TabPage_WithCorp` | - | 운용사코드 등록 기능 처리 |
| 16 | **문서분류지정** | `Biz16_TabPage_EachCont` | - | 문서분류지정 기능 처리 |
| 17 | **펀드** | `Biz17_TabPage_DualManageFund` | - | 펀드 기능 처리 |
| 18 | **생성** | `Biz55_Tab_ErpFeeCharge_new` | - | 생성 기능 처리 |
| 19 | **생성** | `Biz55_Tab_ErpFeeCharge_original` | - | 생성 기능 처리 |

### BIZ-05. 법인카드관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 20 | **법인카드 내역관리** | `Biz01_Tab_CardManagement` | 1141 | 법인카드 내역관리 |
| 21 | **법인카드 현황** | `Biz01_Tab_CardReport` | 1333 | 법인카드 현황 |
| 22 | **법인카드 실사용자 배분** | `Biz01_Tab_CardUserAllocation` | 1406 | insert menu |
| 23 | **접대비 현황** | `Biz01_Tab_EntertmExpenseReport` | 1335 | 접대비 현황 화면 |

### BIZ-06. 이익제공(수령)현황
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 24 | **이익제공 입력(법인카드)** | `Biz01_Tab_Card` | 1131 | 이익제공 입력(법인카드) |
| 25 | **법인카드 사용내역 조회** | `Biz01_Tab_CardContents` | 1138 | 법인카드 사용내역 조회 |
| 26 | **(s)법인카드사용내역** | `Biz01_Tab_CardContentsSimple` | 1321 | 법인카드 사용내역 조회 간소화 버전 |
| 27 | **(s)이익제공입력(카드)** | `Biz01_Tab_CardSimple` | 1319 | 이익제공 입력(법인카드) 간소화 버전 : 거래상대방, 인원 직접입력 |
| 28 | **이익제공 한도초과현황** | `Biz01_Tab_LimitCheckList` | 1133 | 이익제공(수령) 한도초과현황 |
| 29 | **이익제공 입력(현금,물품)** | `Biz01_Tab_Other` | 1132 | 로그인한 사용자가 등록한 건만 조회 |
| 30 | **(s)이익제공입력(현금,물품)** | `Biz01_Tab_OtherSimple` | 1320 | 이익제공 입력 간소화 버전 : 거래상대방, 인원 직접입력 |
| 31 | **이익제공 상세현황** | `Biz01_Tab_PriorApproval` | 1136 | 이익제공(수령) 현황 |
| 32 | **(s)이익제공 상세현황** | `Biz01_Tab_PriorApprovalSimple` | 1322 | 이익제공 상세현황 간호화 버전 |
| 33 | **이익제공 기준관리(준감인)** | `Biz90_Tab_Limit` | 1130 | 이익제공(수령) 기준관리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/biz/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Biz01_Excel` | Biz01_Excel 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Biz01_Promo` | Biz01_Promo 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Biz02_Person` | Biz02_Person 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Biz03_AccountMap` | Biz03_AccountMap 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Biz04_ProvideSetup` | Biz04_ProvideSetup 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Biz05_RelateAppr` | Biz05_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Biz10_ContCorp` | Biz10_ContCorp 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Biz11_ContHistory` | Biz11_ContHistory 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Biz11_PDF7` | Biz11_PDF7 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Biz12_FeeInfo` | Biz12_FeeInfo 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Biz13_WithCorp` | Biz13_WithCorp 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Biz14_RelateAppr` | Biz14_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Biz15_Share` | Biz15_Share 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Biz16_EachCont` | Biz16_EachCont 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Biz17_DualManageFund` | Biz17_DualManageFund 비즈니스 로직 및 RPC 서비스 처리 |
| 16 | `Biz20_FeeCharge` | Biz20_FeeCharge 비즈니스 로직 및 RPC 서비스 처리 |
| 17 | `Biz21_Excel` | Biz21_Excel 비즈니스 로직 및 RPC 서비스 처리 |
| 18 | `Biz21_FeeChargeDtl` | Biz21_FeeChargeDtl 비즈니스 로직 및 RPC 서비스 처리 |
| 19 | `Biz21_PDF` | Biz21_PDF 비즈니스 로직 및 RPC 서비스 처리 |
| 20 | `Biz22_FeeChargeCalc` | Biz22_FeeChargeCalc 비즈니스 로직 및 RPC 서비스 처리 |
| 21 | `Biz29_Account` | Biz29_Account 비즈니스 로직 및 RPC 서비스 처리 |
| 22 | `Biz50_ErpSetup` | Biz50_ErpSetup 비즈니스 로직 및 RPC 서비스 처리 |
| 23 | `Biz51_ErpContCorp` | Biz51_ErpContCorp 비즈니스 로직 및 RPC 서비스 처리 |
| 24 | `Biz52_ErpFee` | Biz52_ErpFee 비즈니스 로직 및 RPC 서비스 처리 |
| 25 | `Biz55_ErpFeeCharge` | Biz55_ErpFeeCharge 비즈니스 로직 및 RPC 서비스 처리 |
| 26 | `Biz60_FundPriceModi` | Biz60_FundPriceModi 비즈니스 로직 및 RPC 서비스 처리 |
| 27 | `Biz61_ModiRptRelateAppr` | Biz61_ModiRptRelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 28 | `Biz90_Limit` | Biz90_Limit 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/biz/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `biz01_promo.xml` | `biz01_promo` 테이블 관련 쿼리 매핑 |
| 2 | `biz02_person.xml` | `biz02_person` 테이블 관련 쿼리 매핑 |
| 3 | `biz03_account_map.xml` | `biz03_account_map` 테이블 관련 쿼리 매핑 |
| 4 | `biz04_provide_setup.xml` | `biz04_provide_setup` 테이블 관련 쿼리 매핑 |
| 5 | `biz05_relate_appr.xml` | `biz05_relate_appr` 테이블 관련 쿼리 매핑 |
| 6 | `biz10_cont_corp.xml` | `biz10_cont_corp` 테이블 관련 쿼리 매핑 |
| 7 | `biz11_cont_history.xml` | `biz11_cont_history` 테이블 관련 쿼리 매핑 |
| 8 | `biz12_fee_info.xml` | `biz12_fee_info` 테이블 관련 쿼리 매핑 |
| 9 | `biz13_with_corp.xml` | `biz13_with_corp` 테이블 관련 쿼리 매핑 |
| 10 | `biz14_relate_appr.xml` | `biz14_relate_appr` 테이블 관련 쿼리 매핑 |
| 11 | `biz15_share.xml` | `biz15_share` 테이블 관련 쿼리 매핑 |
| 12 | `biz16_each_cont.xml` | `biz16_each_cont` 테이블 관련 쿼리 매핑 |
| 13 | `biz17_dual_manage_fund.xml` | `biz17_dual_manage_fund` 테이블 관련 쿼리 매핑 |
| 14 | `biz20_fee_charge.xml` | `biz20_fee_charge` 테이블 관련 쿼리 매핑 |
| 15 | `biz21_fee_charge_dtl.xml` | `biz21_fee_charge_dtl` 테이블 관련 쿼리 매핑 |
| 16 | `biz22_fee_charge_calc.xml` | `biz22_fee_charge_calc` 테이블 관련 쿼리 매핑 |
| 17 | `biz29_account.xml` | `biz29_account` 테이블 관련 쿼리 매핑 |
| 18 | `biz50_erp_setup.xml` | `biz50_erp_setup` 테이블 관련 쿼리 매핑 |
| 19 | `biz51_erp_cont_corp.xml` | `biz51_erp_cont_corp` 테이블 관련 쿼리 매핑 |
| 20 | `biz52_erp_fee.xml` | `biz52_erp_fee` 테이블 관련 쿼리 매핑 |
| 21 | `biz55_erp_fee_charge.xml` | `biz55_erp_fee_charge` 테이블 관련 쿼리 매핑 |
| 22 | `biz60_fund_price_modi.xml` | `biz60_fund_price_modi` 테이블 관련 쿼리 매핑 |
| 23 | `biz61_modi_rpt_relate_appr.xml` | `biz61_modi_rpt_relate_appr` 테이블 관련 쿼리 매핑 |
| 24 | `biz90_limit.xml` | `biz90_limit` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `biz01_promo` | 이익제공(수령) 내역 | 25 | `biz01_promo_id` |
| 2 | `biz02_person` | 이익제공(수령) 인원정보 | 7 | `biz02_person_id` |
| 3 | `biz03_account_map` | 법인카드 사용항목별 계정과목 맵핑 | 5 | `biz03_account_map_id` |
| 4 | `biz04_provide_setup` | 이익제공(수령) 설정정보 | 4 | `biz04_provide_setup_id` |
| 5 | `biz05_relate_appr` | 상신문서 연결 | 7 | `biz05_relate_appr_id` |
| 6 | `biz10_cont_corp` | 계약사 관리 | 2 | `biz10_cont_corp_id` |
| 7 | `biz11_cont_history` | 계약사별 이력관리 | 18 | `biz11_cont_history_id` |
| 8 | `biz12_fee_info` | 보수정보 | 9 | `biz12_fee_info_id` |
| 9 | `biz13_with_corp` | 계약사 운영정보 | 7 | `biz13_with_corp_id` |
| 10 | `biz14_relate_appr` | 연관문서 | 3 | `biz14_relate_appr_id` |
| 11 | `biz15_share` | 계약사 공유자관리 | 6 | `biz15_share_id` |
| 12 | `biz16_each_contract` | 개별계약서 | 13 | `biz16_each_contract_id` |
| 13 | `biz17_dual_manage_fund` | 이중사무관리 펀드 | 9 | `biz17_dual_manage_fund_id` |
| 14 | `biz20_fee_charge` | 최저보수청구 | 27 | `biz20_fee_charge_id` |
| 15 | `biz21_fee_charge_dtl` | 최저보수청구 상세내역 | 16 | `biz21_fee_charge_dtl_id` |
| 16 | `biz22_fee_charge_calc` | 최저보수청구 구간계산정보 | 27 | `biz22_fee_charge_calc_id` |
| 17 | `biz29_account` | 보수입금계좌 | 9 | `biz29_account_id` |
| 18 | `biz50_erp_setup` | AssetERP 기본설정 | 15 | `biz50_erp_setup_id` |
| 19 | `biz51_erp_cont_corp` | AssetERP 계약사 관리 | 17 | `biz51_erp_cont_corp_id` |
| 20 | `biz52_erp_fee` | AssetERP 계약사별 사용료 설정 | 21 | `biz52_erp_fee_id` |
| 21 | `biz55_erp_fee_charge` | AssetERP 사용료 청구 | 26 | `biz55_erp_fee_charge_id` |
| 22 | `biz60_fund_price_modi` | 기준가정정보고 | 34 | `biz60_fund_price_modi_id` |
| 23 | `biz61_modi_rpt_relate_appr` | 기준가정정보고 월상신 | 4 | `biz61_modi_rpt_relate_appr_id` |
| 24 | `biz90_limit` | 이익제공(수령) 한도관리 | 9 | `biz90_limit_id` |
| 25 | `biz95_cont_corp_back` | 계약사관리(백업) | 7 | `biz95_cont_corp_back_id` |
| 26 | `biz96_cont_history_back` | 계약사별 이력관리(백업) | 23 | `biz96_cont_history_back_id` |
| 27 | `biz97_fee_info_back` | 보수정보(백업) | 14 | `biz97_fee_info_back_id` |
| 28 | `biz98_with_corp_back` | 계약사 운영정보(백업) | 12 | `biz98_with_corp_back_id` |
| 29 | `biz99_dual_manage_fund_back` | 이중사무관리 펀드(백업) | 14 | `biz99_dual_manage_fund_back_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **33개**
- **UI 컴포넌트 수**: 총 78개 (Tab/Page: 33개, Lookup/Popup/기타: 45개)
- **서버 서비스 클래스 수**: **28개**
- **MyBatis 매퍼 XML 수**: **24개**
- **DB 테이블 수**: **29개**
