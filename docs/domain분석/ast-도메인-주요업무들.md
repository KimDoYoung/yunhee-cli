# ast (자산관리 (고유자산·펀드자산)) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `ast` (자산관리 (고유자산·펀드자산)) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/ast/*`, `myApp/server/ast/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`ast##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`ast` 도메인은 **자산관리 (고유자산·펀드자산)** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **AST-01** | **결산** | 결산 관련 화면 및 처리 모듈 | 2개 화면 |
| **AST-02** | **고유자산 거래처리** | 고유자산 거래처리 관련 화면 및 처리 모듈 | 7개 화면 |
| **AST-03** | **고유자산 등록** | 고유자산 등록 관련 화면 및 처리 모듈 | 3개 화면 |
| **AST-04** | **고유자산 현황** | 고유자산 현황 관련 화면 및 처리 모듈 | 6개 화면 |
| **AST-05** | **관리회계** | 관리회계 관련 화면 및 처리 모듈 | 2개 화면 |
| **AST-06** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 6개 화면 |
| **AST-07** | **사무보수관리** | 사무보수관리 관련 화면 및 처리 모듈 | 2개 화면 |
| **AST-08** | **사업비관리** | 사업비관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **AST-09** | **예금관리** | 예금관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **AST-10** | **자금관리** | 자금관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **AST-11** | **자산&경영** | 자산&경영 관련 화면 및 처리 모듈 | 1개 화면 |
| **AST-12** | **특수회계처리** | 특수회계처리 관련 화면 및 처리 모듈 | 4개 화면 |
| **AST-13** | **특수회계처리(외화)** | 특수회계처리(외화) 관련 화면 및 처리 모듈 | 3개 화면 |
| **AST-14** | **펀드운용보수관리** | 펀드운용보수관리 관련 화면 및 처리 모듈 | 4개 화면 |
| **AST-15** | **펀드자산** | 펀드자산 관련 화면 및 처리 모듈 | 5개 화면 |
| **AST-16** | **회계장부** | 회계장부 관련 화면 및 처리 모듈 | 1개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### AST-01. 결산
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **외화예금 환평가처리** | `Ast06_Tab_FxEvalDeposit` | 1174 | 고유자산 외화예금 환평가 |
| 2 | **펀드보수 결산처리** | `Ast30_Tab_OfficeMngFeeClose` | 1202 | 사무관리 펀드보수 월/연말 결산처리 - 미수보수 발생 |

### AST-02. 고유자산 거래처리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **감가상각처리** | `Ast06_Tab_EvalDepn` | 1175 | 감가상각처리 |
| 4 | **금융상품 평가처리** | `Ast06_Tab_EvalFinance` | 1167 | 고유자산 평가처리 |
| 5 | **금융상품 계좌대체** | `Ast06_Tab_TrAcntTransfer` | 1208 | 금융자산 계좌대체 |
| 6 | **금융상품 거래처리** | `Ast06_Tab_TrFinance` | 1158 | 금융상품 거래처리 |
| 7 | **금융상품 거래처리(외화)** | `Ast06_Tab_TrForFinance` | 1365 | 금융상품 거래처리(외화) 기능 처리 |
| 8 | **청약처리** | `Ast06_Tab_TrIPO` | 1288 | 공모주,채권,유상 청약금 납입/환불, 입고 거래처리 |
| 9 | **금융상품 시세관리** | `Ast25_Tab_Price` | 1295 | 금융상품 시세관리 |

### AST-03. 고유자산 등록
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 10 | **고유자산 기본등록 ①** | `Ast01_Tab_ClassTreeIntrinsic` | 1087 | 고유자산 종목기본 |
| 11 | **고유자산 상세등록 ②** | `Ast01_Tab_InfoIntrinsic` | 1088 | 고유자산 종목상세 |
| 12 | **자기자본/투자한도 등록** | `Ast40_Tab_OwnerCapital` | 1299 | 자기자본 및 투자한도 등록 |

### AST-04. 고유자산 현황
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 13 | **금융상품 보유내역** | `Ast09_Tab_FinanceBook` | 1160 | 금융상품 보유내역 |
| 14 | **금융상품 운용내역** | `Ast09_Tab_FinanceBookOpr` | 1300 | 금융상품 운용내역 |
| 15 | **금융상품 보유내역(기간조회)** | `Ast09_Tab_FinanceBookPeriod` | 1239 | 금융상품 잔고조회(기간조회) |
| 16 | **금융상품 보유내역(외화)** | `Ast09_Tab_FinanceForBook` | 1366 | 금융상품 보유내역(외화) 기능 처리 |
| 17 | **감가상각대장** | `Ast13_Tab_DepnBook` | 1181 | 구 비품대장 |
| 18 | **비품관리대장** | `Ast13_Tab_OfficeAssets` | 1397 | 비품관리대장 기능 처리 |

### AST-05. 관리회계
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 19 | **거래유형 등록** | `Ast05_Tab_TrCodeIntrinsic` | 1090 | 거래유형 코드관리(고유) |
| 20 | **거래유형 등록(관리자)** | `Ast05_Tab_TrCodeAdmin` | 1165 | 거래코드 관리(관리자) |

### AST-06. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 21 | **거래내역** | `Ast06_TabPage_FinanceBookOpr` | - | 거래내역 기능 처리 |
| 22 | **평가여부** | `Ast06_TabPage_InterestEval` | - | 평가여부 기능 처리 |
| 23 | **평가여부** | `Ast06_TabPage_MarketEval` | - | 평가여부 기능 처리 |
| 24 | **평가처리** | `Ast06_Tab_EvalFinance_20260204` | - | 평가처리 기능 처리 |
| 25 | **찾기** | `Ast15_Page_TrCodeWindow` | - | 찾기 기능 처리 |
| 26 | **기준일자** | `Ast30_Tab_OfficeMngFeeState` | - | 기준일자 기능 처리 |

### AST-07. 사무보수관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 27 | **보수원장(기간조회)** | `Ast30_Tab_OfficeMngFeeStatePeriod` | 1249 | 일별보수현황(기간조회) |
| 28 | **이관펀드 등록(사무관리)** | `Ast33_Tab_OfficeMngFundTrans` | 1251 | 이관펀드 정보등록 (사무관리사용) |

### AST-08. 사업비관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 29 | **세금/4대보험 등록** | `Ast06_Tab_TrTax` | 1196 | 원천세, 부가세, 4대보험 납부 |

### AST-09. 예금관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 30 | **예금잔고대사** | `Ast09_Tab_DepositBook` | 1473 | 예금잔고대사 기능 처리 |

### AST-10. 자금관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 31 | **예금잔고조회** | `Ast09_Tab_DepositBookPeriod` | 1238 | 예금잔고조회(기간조회) |

### AST-11. 자산&경영
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 32 | **자산상세 항목관리** | `Ast01_Tab_InfoManager` | 1089 | 자산상세 디폴트 항목 관리 |

### AST-12. 특수회계처리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 33 | **미수/미지급** | `Ast06_Tab_AccruedIntrinsic` | 1092 | 고유자산 미수/미지급 처리 |
| 34 | **계좌이체** | `Ast06_Tab_TrDeposit` | 1166 | 계좌이체(원화) |
| 35 | **예금/예치금 이자수령** | `Ast06_Tab_TrDepositInt` | 1205 | 예금/예치금 이자수령 |
| 36 | **고유자산 거래처리** | `Ast06_Tab_TrIntrinsic` | 1091 | 고유자산 거래처리 |

### AST-13. 특수회계처리(외화)
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 37 | **미수/미지급(외화)** | `Ast06_Tab_AccruedForIntrinsic` | 1173 | 미수/미지급(외화) |
| 38 | **계좌이체(외화)** | `Ast06_Tab_TrForDeposit` | 1172 | 계좌이체(외화) |
| 39 | **고유자산 거래처리(외화)** | `Ast06_Tab_TrForIntrinsic` | 1171 | 고유자산 거래처리(외화) |

### AST-14. 펀드운용보수관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 40 | **펀드보수현황** | `Ast30_Tab_FundMngFee` | 1401 | 펀드보수현황 기능 처리 |
| 41 | **운용보수 회계처리** | `Ast30_Tab_FundMngFeeClose` | 1218 | 운용보수 월/연말 결산처리 - 미수보수 발생 |
| 42 | **펀드보수원장** | `Ast30_Tab_FundMngFeeState` | 1216 | 일별 운용보수 현황 |
| 43 | **이관펀드 등록** | `Ast33_Tab_FundMngTrans` | 1252 | 이관펀드 정보등록 (운용사용) |

### AST-15. 펀드자산
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 44 | **펀드자산 종목기본** | `Ast01_Tab_ClassTreeManagement` | 1117 | 운용자산 종목기본 |
| 45 | **펀드자산 종목상세** | `Ast01_Tab_InfoManagement` | 1118 | 운용자산 종목상세 |
| 46 | **거래코드 관리(운용)** | `Ast05_Tab_TrCodeManagement` | 1120 | 거래코드 관리(펀드) |
| 47 | **펀드자산 미수/미지급** | `Ast06_Tab_AccruedManagement` | 1129 | 펀드자산 미수/미지급 |
| 48 | **펀드자산 거래관리** | `Ast06_Tab_TrManagement` | 1119 | 운용자산 거래관리 |

### AST-16. 회계장부
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 49 | **선급금/선급비용 조회** | `Ast09_Tab_PreDepositBook` | 1342 | 선급금/선급비용 조회 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/ast/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Ast01_ClassTree` | Ast01_ClassTree 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Ast02_Detail` | Ast02_Detail 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Ast03_CfInfo` | Ast03_CfInfo 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Ast04_Cf` | Ast04_Cf 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Ast05_TrCode` | Ast05_TrCode 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Ast06_Tr` | Ast06_Tr 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Ast07_Settle` | Ast07_Settle 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Ast08_TrFinance` | Ast08_TrFinance 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Ast09_Book` | Ast09_Book 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Ast10_Manager` | Ast10_Manager 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Ast12_BookReal` | Ast12_BookReal 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Ast13_BookDepn` | Ast13_BookDepn 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Ast14_BookFundFee` | Ast14_BookFundFee 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Ast15_TrCodeWindow` | Ast15_TrCodeWindow 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Ast16_NonDeductTax` | Ast16_NonDeductTax 비즈니스 로직 및 RPC 서비스 처리 |
| 16 | `Ast20_TrTax` | Ast20_TrTax 비즈니스 로직 및 RPC 서비스 처리 |
| 17 | `Ast21_Tr4Insure` | Ast21_Tr4Insure 비즈니스 로직 및 RPC 서비스 처리 |
| 18 | `Ast24_FxRate` | Ast24_FxRate 비즈니스 로직 및 RPC 서비스 처리 |
| 19 | `Ast25_Price` | Ast25_Price 비즈니스 로직 및 RPC 서비스 처리 |
| 20 | `Ast30_BookFundFee` | Ast30_BookFundFee 비즈니스 로직 및 RPC 서비스 처리 |
| 21 | `Ast33_FundTrans` | Ast33_FundTrans 비즈니스 로직 및 RPC 서비스 처리 |
| 22 | `Ast40_OwnerCapital` | Ast40_OwnerCapital 비즈니스 로직 및 RPC 서비스 처리 |
| 23 | `Ast41_InvestLimit` | Ast41_InvestLimit 비즈니스 로직 및 RPC 서비스 처리 |
| 24 | `Ast80_RelateAppr` | Ast80_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/ast/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `ast01_class_tree.xml` | `ast01_class_tree` 테이블 관련 쿼리 매핑 |
| 2 | `ast02_detail.xml` | `ast02_detail` 테이블 관련 쿼리 매핑 |
| 3 | `ast03_cf_info.xml` | `ast03_cf_info` 테이블 관련 쿼리 매핑 |
| 4 | `ast04_cf.xml` | `ast04_cf` 테이블 관련 쿼리 매핑 |
| 5 | `ast05_tr_code.xml` | `ast05_tr_code` 테이블 관련 쿼리 매핑 |
| 6 | `ast06_tr.xml` | `ast06_tr` 테이블 관련 쿼리 매핑 |
| 7 | `ast07_settle.xml` | `ast07_settle` 테이블 관련 쿼리 매핑 |
| 8 | `ast08_tr_finance.xml` | `ast08_tr_finance` 테이블 관련 쿼리 매핑 |
| 9 | `ast09_book.xml` | `ast09_book` 테이블 관련 쿼리 매핑 |
| 10 | `ast10_manager.xml` | `ast10_manager` 테이블 관련 쿼리 매핑 |
| 11 | `ast12_book_real.xml` | `ast12_book_real` 테이블 관련 쿼리 매핑 |
| 12 | `ast13_book_depn.xml` | `ast13_book_depn` 테이블 관련 쿼리 매핑 |
| 13 | `ast15_tr_code_window.xml` | `ast15_tr_code_window` 테이블 관련 쿼리 매핑 |
| 14 | `ast16_non_deduct_tax.xml` | `ast16_non_deduct_tax` 테이블 관련 쿼리 매핑 |
| 15 | `ast20_tr_tax.xml` | `ast20_tr_tax` 테이블 관련 쿼리 매핑 |
| 16 | `ast21_tr_4insure.xml` | `ast21_tr_4insure` 테이블 관련 쿼리 매핑 |
| 17 | `ast24_fx_rate.xml` | `ast24_fx_rate` 테이블 관련 쿼리 매핑 |
| 18 | `ast25_price.xml` | `ast25_price` 테이블 관련 쿼리 매핑 |
| 19 | `ast30_book_fund_fee.xml` | `ast30_book_fund_fee` 테이블 관련 쿼리 매핑 |
| 20 | `ast33_fund_trans.xml` | `ast33_fund_trans` 테이블 관련 쿼리 매핑 |
| 21 | `ast40_owner_capital.xml` | `ast40_owner_capital` 테이블 관련 쿼리 매핑 |
| 22 | `ast41_invest_limit.xml` | `ast41_invest_limit` 테이블 관련 쿼리 매핑 |
| 23 | `ast80_relate_appr.xml` | `ast80_relate_appr` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `ast01_class_tree` | 자산분류 | 29 | `ast01_class_tree_id` |
| 2 | `ast02_detail` | 자산상세 | 10 | `ast02_detail_id` |
| 3 | `ast03_cf_info` | 현금흐름표 기본정보 | 17 | `ast03_cf_info_id` |
| 4 | `ast04_cf` | 현금흐름표 | 9 | `ast04_cf_id` |
| 5 | `ast05_tr_code` | 거래코드관리 | 14 | `ast05_tr_code_id` |
| 6 | `ast06_tr` | 거래내역 | 24 | `ast06_tr_id` |
| 7 | `ast07_settle` | 결제내역(미수/미지급내역관리) | 13 | `ast07_settle_id` |
| 8 | `ast08_tr_finance` | 금융상품 거래상세 | 25 | `ast08_tr_finance_id` |
| 9 | `ast09_book` | 고유자산(금융상품) 보유원장 | 25 | `ast09_book_id` |
| 10 | `ast10_manager` | 담당자정보 | 8 | `ast10_manager_id` |
| 11 | `ast11_book_close` | 고유자산 마감원장 | 26 | `ast11_book_close_id` |
| 12 | `ast12_book_real` | 실제잔고(대사용으로 입력) | 9 | `ast12_book_real_id` |
| 13 | `ast13_book_depn` | 비품 보유원장 | 11 | `ast13_book_depn_id` |
| 14 | `ast14_book_init` | 신규고객사 초기보유원장 (ast09 생성용) | 25 | `ast14_book_init_id` |
| 15 | `ast15_tr_code_window` | 화면별 사용 거래코드 | 5 | `ast15_tr_code_window_id` |
| 16 | `ast16_non_deduct_tax` | 유/무형자산 불공제세액 추가분 관리 | 5 | `ast16_non_deduct_tax_id` |
| 17 | `ast20_tr_tax` | 세금납부 | 7 | `ast20_tr_tax_id` |
| 18 | `ast21_tr_4insure` | 4대보험납부 | 17 | `ast21_tr_4insure_id` |
| 19 | `ast24_fx_rate` | 환율관리 | 7 | `ast24_fx_rate_id` |
| 20 | `ast25_price` | 고유자산시세정보 | 8 | `ast25_price_id` |
| 21 | `ast30_book_fund_fee` | 펀드보수원장 | 22 | `ast30_book_fund_fee_id` |
| 22 | `ast31_book_fund_fee_close` | 펀드보수 결산원장 | 24 | `ast31_book_fund_fee_close_id` |
| 23 | `ast32_book_fund_fee_recovery` | 펀드보수원장 복구용 | 23 | `ast32_book_fund_fee_recovery_id` |
| 24 | `ast33_fund_trans` | 이관펀드정보 | 11 | `ast33_fund_trans_id` |
| 25 | `ast40_owner_capital` | 자기자본 | 5 | `ast40_owner_capital_id` |
| 26 | `ast41_invest_limit` | 자기자본투자한도 | 7 | `ast41_invest_limit_id` |
| 27 | `ast80_relate_appr` | 연관문서(고유자산) | 5 | `ast80_relate_appr_id` |
| 28 | `ast90_tr_back` | 거래내역(백업) | 27 | `ast90_tr_back_id` |
| 29 | `ast91_settle_back` | 결제내역(미수/미지급내역관리)(백업) | 16 | `ast91_settle_back_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **49개**
- **UI 컴포넌트 수**: 총 119개 (Tab/Page: 49개, Lookup/Popup/기타: 70개)
- **서버 서비스 클래스 수**: **24개**
- **MyBatis 매퍼 XML 수**: **23개**
- **DB 테이블 수**: **29개**
