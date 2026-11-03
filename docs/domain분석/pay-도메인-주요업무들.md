# pay (급여 / 연봉 / 사업비 지출결의) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `pay` (급여 / 연봉 / 사업비 지출결의) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/pay/*`, `myApp/server/pay/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`pay##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`pay` 도메인은 **급여 / 연봉 / 사업비 지출결의** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **PAY-01** | **급여관리** | 급여관리 관련 화면 및 처리 모듈 | 13개 화면 |
| **PAY-02** | **급여관리(Old)** | 급여관리(Old) 관련 화면 및 처리 모듈 | 6개 화면 |
| **PAY-03** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 34개 화면 |
| **PAY-04** | **사업비 신청** | 사업비 신청 관련 화면 및 처리 모듈 | 3개 화면 |
| **PAY-05** | **사업비관리** | 사업비관리 관련 화면 및 처리 모듈 | 6개 화면 |
| **PAY-06** | **연봉관리** | 연봉관리 관련 화면 및 처리 모듈 | 3개 화면 |
| **PAY-07** | **자산&경영** | 자산&경영 관련 화면 및 처리 모듈 | 3개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### PAY-01. 급여관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **원천징수영수증(사본)** | `Pay08_Tab_TaxWithholding` | 1219 | 원천징수영수증 |
| 2 | **원천징수영수증 업로드** | `Pay08_Tab_TaxWithholdingAdmin` | 1220 | 원천징수업로드 |
| 3 | **급여대장** | `Pay10_Tab_List` | 1271 | 급여대장 |
| 4 | **급여관리** | `Pay10_Tab_Month` | 1270 | 급여, 상여금, 퇴직정산 등록 |
| 5 | **급여관리(항목별)** | `Pay10_Tab_MonthItem` | 1281 | 급여관리(항목별) |
| 6 | **급여항목조회** | `Pay10_Tab_MonthSearch` | 1285 | 급여항목조회 |
| 7 | **급여명세서** | `Pay10_Tab_PersonList` | 1272 | 사원용 급여명세서 |
| 8 | **급여명세서(경영관리팀)** | `Pay10_Tab_PersonListManager` | 1273 | 급여명세서(경영관리팀) |
| 9 | **퇴직정산** | `Pay10_Tab_Retire` | 1274 | 퇴직정산 |
| 10 | **급여기초정보** | `Pay20_Tab_Deduct` | 1278 | 급여 기초정보 관리 |
| 11 | **4대보험신고(EDI)** | `Pay31_Tab_InsureApply` | 1275 | 4대보험 자격취득/보수변동/착오정정/보수총액신고/납부방법변경 처리 |
| 12 | **4대보험 정산내역** | `Pay32_Tab_InsurePay` | 1276 | 4대보험 정산내역 |
| 13 | **갑근세확인서 발급** | `Pay40_Tab_TaxWithholding` | 1364 | 갑근세확인서 발급 기능 처리 |

### PAY-02. 급여관리(Old)
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 14 | **급여대장(old)** | `Pay02_Tab_List` | 1084 | 급여대장 |
| 15 | **급여관리(old)** | `Pay02_Tab_Month` | 1083 | 급여관리 |
| 16 | **급여명세서(old)** | `Pay02_Tab_PersonList` | 1085 | 급여명세서 |
| 17 | **급여명세서(경영관리팀)(old)** | `Pay02_Tab_PersonListManager` | 1183 | 급여명세서(경영관리팀) |
| 18 | **회사계좌관리(X)** | `Pay03_Tab_Account` | 1086 | 회사계좌관리 |
| 19 | **퇴직정산서(old)** | `Pay07_Tab_Retire` | 1139 | 퇴직정산서 |

### PAY-03. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 20 | **생성** | `Pay04_TabPage_Formula` | - | 생성 기능 처리 |
| 21 | **연봉계약현황** | `Pay06_TabPage_ActMapping` | - | 연봉계약현황 기능 처리 |
| 22 | **퇴직정산서** | `Pay06_TabPage_RetireMapping` | - | 퇴직정산서 기능 처리 |
| 23 | **상신** | `Pay07_TabPage_RetireStatement1` | - | 상신 기능 처리 |
| 24 | **Pay07_TabPage_RetireStatement2** | `Pay07_TabPage_RetireStatement2` | - | Pay07_TabPage_RetireStatement2 기능 처리 |
| 25 | **상신** | `Pay10_TabPage_Retire` | - | 상신 기능 처리 |
| 26 | **행 추가** | `Pay11_TabPage_MonthItem` | - | 행 추가 기능 처리 |
| 27 | **출력/다운로드** | `Pay12_TabPage_RetireInsure` | - | 출력/다운로드 기능 처리 |
| 28 | **출력/다운로드** | `Pay13_TabPage_RetireTax` | - | 출력/다운로드 기능 처리 |
| 29 | **입사일기준 연차휴가 - 회계일기준 연차휴가** | `Pay15_TabPage_RetireLeave` | - | 입사일기준 연차휴가 - 회계일기준 연차휴가 기능 처리 |
| 30 | **항목구분** | `Pay20_TabPage_Item` | - | 항목구분 기능 처리 |
| 31 | **율 구분** | `Pay21_TabPage_Rate` | - | 율 구분 기능 처리 |
| 32 | **엑셀업로드** | `Pay22_TabPage_SimpleTax` | - | 엑셀업로드 기능 처리 |
| 33 | **생성** | `Pay23_Popup_SimpleTaxTableCreate` | - | 생성 기능 처리 |
| 34 | **적용기준시작일** | `Pay23_TabPage_SimpleTaxTable` | - | 적용기준시작일 기능 처리 |
| 35 | **근로소득 공제표** | `Pay24_Lookup_DeductTable` | - | 근로소득 공제표 기능 처리 |
| 36 | **생성** | `Pay24_Popup_DeductTableCreate` | - | 생성 기능 처리 |
| 37 | **공제한도** | `Pay24_TabPage_Deduct` | - | 공제한도 기능 처리 |
| 38 | **적용시작일** | `Pay24_TabPage_DeductTable` | - | 적용시작일 기능 처리 |
| 39 | **구분** | `Pay25_TabPage_Deduct` | - | 구분 기능 처리 |
| 40 | **적용시작일** | `Pay25_TabPage_PersonDeduct` | - | 적용시작일 기능 처리 |
| 41 | **산출세액표** | `Pay26_Lookup_TaxCalcTable` | - | 산출세액표 기능 처리 |
| 42 | **과세표준(원)** | `Pay26_TabPage_TaxCalc` | - | 과세표준(원) 기능 처리 |
| 43 | **적용시작일** | `Pay26_TabPage_TaxCalcTable` | - | 적용시작일 기능 처리 |
| 44 | **산출기준** | `Pay27_Lookup_TaxDeductTable` | - | 산출기준 기능 처리 |
| 45 | **생성** | `Pay27_Popup_TaxDeductTableCreate` | - | 생성 기능 처리 |
| 46 | **산출세액** | `Pay27_TabPage_TaxDeduct` | - | 산출세액 기능 처리 |
| 47 | **적용시작일** | `Pay27_TabPage_TaxDeductTable` | - | 적용시작일 기능 처리 |
| 48 | **최대분할회차** | `Pay29_TabPage_OtherSetup` | - | 최대분할회차 기능 처리 |
| 49 | **적용시작일** | `Pay29_TabPage_OtherSetupDate` | - | 적용시작일 기능 처리 |
| 50 | **신고일** | `Pay31_TabPage_InsureApply1` | - | 신고일 기능 처리 |
| 51 | **엑셀업로드** | `Pay31_TabPage_InsureApply2` | - | 엑셀업로드 기능 처리 |
| 52 | **생성** | `Pay31_TabPage_InsureApply3` | - | 생성 기능 처리 |
| 53 | **템플릿** | `Pay31_TabPage_InsureApply4` | - | 템플릿 기능 처리 |

### PAY-04. 사업비 신청
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 54 | **지출결의서** | `Pay50_Tab_Expense` | 1407 | 발생직원 직접 지출결의서 작성용 |
| 55 | **사업비 지출승인(부서장)** | `Pay50_Tab_ExpenseConfirm` | 1384 | 사업비 지출승인(부서장) 기능 처리 |
| 56 | **사업비 지출요청** | `Pay50_Tab_ExpenseRequest` | 1383 | 사업비 지출요청 기능 처리 |

### PAY-05. 사업비관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 57 | **사업비발생현황** | `Pay50_Tab_AccountSumList` | 1399 | 사업비발생현황 기능 처리 |
| 58 | **사업비 회계처리** | `Pay50_Tab_ExpenseJournal` | 1387 | 사업비 회계처리 기능 처리 |
| 59 | **지출결의서(경영관리)** | `Pay50_Tab_ExpenseManager` | 1385 | 지출요청, 화환신청 지출결의서 작성 |
| 60 | **자금집행결의서 조회** | `Pay50_Tab_ExpensePay` | 1400 | 자금집행결의서 조회 기능 처리 |
| 61 | **자금집행결의서** | `Pay50_Tab_ExpensePayWrite` | 1386 | 자금집행결의서 기능 처리 |
| 62 | **미지급반제처리** | `Pay50_Tab_ExpenseSettle` | 1390 | 미지급반제처리 기능 처리 |

### PAY-06. 연봉관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 63 | **연봉계약관리** | `Pay01_Tab_Annual` | 1037 | 연봉계약관리 |
| 64 | **연봉계약현황** | `Pay01_Tab_AnnualList` | 1082 | 연봉계약현황 |
| 65 | **연봉조회** | `Pay01_Tab_AnnualPerson` | 1104 | 연봉내역조회 |

### PAY-07. 자산&경영
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 66 | **임금계산방법(x)** | `Pay04_Tab_Formula` | 1111 | 임금계산방법 |
| 67 | **급여기초정보관리** | `Pay20_Tab_DeductAdmin` | 1279 | 급여기초정보관리 |
| 68 | **근로시간기준관리** | `Pay34_Tab_WorkTimeConfig` | 1489 | 근로시간기준관리 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/pay/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Pay00_PDF7` | Pay00_PDF7 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Pay01_Annual` | Pay01_Annual 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Pay02_Month` | Pay02_Month 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Pay03_Account` | Pay03_Account 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Pay04_Formula` | Pay04_Formula 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Pay04_Formula_20230620` | Pay04_Formula_20230620 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Pay05_RelateAppr` | Pay05_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Pay06_ActMapping` | Pay06_ActMapping 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Pay07_Retire` | Pay07_Retire 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Pay08_TaxWithholding` | Pay08_TaxWithholding 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Pay09_RelateNote` | Pay09_RelateNote 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Pay10_Month` | Pay10_Month 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Pay11_MonthItem` | Pay11_MonthItem 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Pay12_RetireInsure` | Pay12_RetireInsure 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Pay13_RetireTax` | Pay13_RetireTax 비즈니스 로직 및 RPC 서비스 처리 |
| 16 | `Pay14_RetireTaxItem` | Pay14_RetireTaxItem 비즈니스 로직 및 RPC 서비스 처리 |
| 17 | `Pay15_RetireLeave` | Pay15_RetireLeave 비즈니스 로직 및 RPC 서비스 처리 |
| 18 | `Pay20_Item` | Pay20_Item 비즈니스 로직 및 RPC 서비스 처리 |
| 19 | `Pay21_Rate` | Pay21_Rate 비즈니스 로직 및 RPC 서비스 처리 |
| 20 | `Pay22_SimpleTaxTable` | Pay22_SimpleTaxTable 비즈니스 로직 및 RPC 서비스 처리 |
| 21 | `Pay23_SimpleTaxTableOther` | Pay23_SimpleTaxTableOther 비즈니스 로직 및 RPC 서비스 처리 |
| 22 | `Pay24_DeductTable` | Pay24_DeductTable 비즈니스 로직 및 RPC 서비스 처리 |
| 23 | `Pay25_PersonDeduct` | Pay25_PersonDeduct 비즈니스 로직 및 RPC 서비스 처리 |
| 24 | `Pay26_TaxCalcTable` | Pay26_TaxCalcTable 비즈니스 로직 및 RPC 서비스 처리 |
| 25 | `Pay27_TaxDeductTable` | Pay27_TaxDeductTable 비즈니스 로직 및 RPC 서비스 처리 |
| 26 | `Pay28_TaxDeductLimit` | Pay28_TaxDeductLimit 비즈니스 로직 및 RPC 서비스 처리 |
| 27 | `Pay29_OtherSetup` | Pay29_OtherSetup 비즈니스 로직 및 RPC 서비스 처리 |
| 28 | `Pay30_BasicSetup` | Pay30_BasicSetup 비즈니스 로직 및 RPC 서비스 처리 |
| 29 | `Pay31_InsureApply` | Pay31_InsureApply 비즈니스 로직 및 RPC 서비스 처리 |
| 30 | `Pay32_InsurePay` | Pay32_InsurePay 비즈니스 로직 및 RPC 서비스 처리 |
| 31 | `Pay34_WorkTimeConfig` | Pay34_WorkTimeConfig 비즈니스 로직 및 RPC 서비스 처리 |
| 32 | `Pay40_IncomeTaxWithholding` | Pay40_IncomeTaxWithholding 비즈니스 로직 및 RPC 서비스 처리 |
| 33 | `Pay50_Expense` | Pay50_Expense 비즈니스 로직 및 RPC 서비스 처리 |
| 34 | `Pay51_ExpenseForm` | Pay51_ExpenseForm 비즈니스 로직 및 RPC 서비스 처리 |
| 35 | `Pay52_FavoriteAccount` | Pay52_FavoriteAccount 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/pay/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `pay01_annual.xml` | `pay01_annual` 테이블 관련 쿼리 매핑 |
| 2 | `pay02_month.xml` | `pay02_month` 테이블 관련 쿼리 매핑 |
| 3 | `pay03_account.xml` | `pay03_account` 테이블 관련 쿼리 매핑 |
| 4 | `pay04_formula.xml` | `pay04_formula` 테이블 관련 쿼리 매핑 |
| 5 | `pay04_formula_20230620.xml` | `pay04_formula_20230620` 테이블 관련 쿼리 매핑 |
| 6 | `pay05_relate_appr.xml` | `pay05_relate_appr` 테이블 관련 쿼리 매핑 |
| 7 | `pay06_act_mapping.xml` | `pay06_act_mapping` 테이블 관련 쿼리 매핑 |
| 8 | `pay07_retire.xml` | `pay07_retire` 테이블 관련 쿼리 매핑 |
| 9 | `pay08_tax_withholding.xml` | `pay08_tax_withholding` 테이블 관련 쿼리 매핑 |
| 10 | `pay09_relate_note.xml` | `pay09_relate_note` 테이블 관련 쿼리 매핑 |
| 11 | `pay10_month.xml` | `pay10_month` 테이블 관련 쿼리 매핑 |
| 12 | `pay11_month_item.xml` | `pay11_month_item` 테이블 관련 쿼리 매핑 |
| 13 | `pay12_retire_insure.xml` | `pay12_retire_insure` 테이블 관련 쿼리 매핑 |
| 14 | `pay13_retire_tax.xml` | `pay13_retire_tax` 테이블 관련 쿼리 매핑 |
| 15 | `pay14_retire_tax_item.xml` | `pay14_retire_tax_item` 테이블 관련 쿼리 매핑 |
| 16 | `pay15_retire_leave.xml` | `pay15_retire_leave` 테이블 관련 쿼리 매핑 |
| 17 | `pay20_item.xml` | `pay20_item` 테이블 관련 쿼리 매핑 |
| 18 | `pay21_rate.xml` | `pay21_rate` 테이블 관련 쿼리 매핑 |
| 19 | `pay22_simple_tax_table.xml` | `pay22_simple_tax_table` 테이블 관련 쿼리 매핑 |
| 20 | `pay23_simple_tax_table_other.xml` | `pay23_simple_tax_table_other` 테이블 관련 쿼리 매핑 |
| 21 | `pay24_deduct_table.xml` | `pay24_deduct_table` 테이블 관련 쿼리 매핑 |
| 22 | `pay25_person_deduct.xml` | `pay25_person_deduct` 테이블 관련 쿼리 매핑 |
| 23 | `pay26_tax_calc_table.xml` | `pay26_tax_calc_table` 테이블 관련 쿼리 매핑 |
| 24 | `pay27_tax_deduct_table.xml` | `pay27_tax_deduct_table` 테이블 관련 쿼리 매핑 |
| 25 | `pay28_tax_deduct_limit.xml` | `pay28_tax_deduct_limit` 테이블 관련 쿼리 매핑 |
| 26 | `pay29_other_setup.xml` | `pay29_other_setup` 테이블 관련 쿼리 매핑 |
| 27 | `pay30_basic_setup.xml` | `pay30_basic_setup` 테이블 관련 쿼리 매핑 |
| 28 | `pay31_insure_apply.xml` | `pay31_insure_apply` 테이블 관련 쿼리 매핑 |
| 29 | `pay32_insure_pay.xml` | `pay32_insure_pay` 테이블 관련 쿼리 매핑 |
| 30 | `pay34_work_time_config.xml` | `pay34_work_time_config` 테이블 관련 쿼리 매핑 |
| 31 | `pay40_income_tax_withholding.xml` | `pay40_income_tax_withholding` 테이블 관련 쿼리 매핑 |
| 32 | `pay50_expense.xml` | `pay50_expense` 테이블 관련 쿼리 매핑 |
| 33 | `pay51_expense_form.xml` | `pay51_expense_form` 테이블 관련 쿼리 매핑 |
| 34 | `pay52_favorite_account.xml` | `pay52_favorite_account` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `pay01_annual` | 연봉관리 | 20 | `pay01_annual_id` |
| 2 | `pay02_month` | 월급여관리(사용X) | 36 | `pay02_month_id` |
| 3 | `pay03_account` | 회사계좌관리 | 8 | `pay03_account_id` |
| 4 | `pay04_formula` | 임금계산방법 | 8 | `pay04_formula_id` |
| 5 | `pay05_relate_appr` | 상신 연관급여대장 | 7 | `pay05_relate_appr_id` |
| 6 | `pay06_act_mapping` | 계약서 맵핑 | 8 | `pay06_act_mapping_id` |
| 7 | `pay07_retire` | 퇴직정산서 | 45 | `pay07_retire_id` |
| 8 | `pay08_tax_withholding` | 원천징수영수증관리 | 5 | `pay08_tax_withholding_id` |
| 9 | `pay09_relate_note` | 비고 | 7 | `pay09_relate_note_id` |
| 10 | `pay10_month` | 급여 | 12 | `pay10_month_id` |
| 11 | `pay11_month_item` | 급여항목상세 | 5 | `pay11_month_item_id` |
| 12 | `pay12_retire_insure` | 퇴직정산-4대보험 | 15 | `pay12_retire_insure_id` |
| 13 | `pay13_retire_tax` | 퇴직정산-소득세 | 18 | `pay13_retire_tax_id` |
| 14 | `pay14_retire_tax_item` | 퇴직정산-소득세-항목상세 | 6 | `pay14_retire_tax_item_id` |
| 15 | `pay15_retire_leave` | 퇴직정산-잔여휴가일수 계산상세 | 7 | `pay15_retire_leave_id` |
| 16 | `pay16_retire_rem_leave` | 퇴직정산-잔여휴가(임시계산용) | 6 | `pay16_retire_rem_leave_id` |
| 17 | `pay20_item` | 급여항목관리 | 8 | `pay20_item_id` |
| 18 | `pay21_rate` | 율관리 | 5 | `pay21_rate_id` |
| 19 | `pay22_simple_tax_table` | 근로소득 간이세액표 | 15 | `pay22_simple_tax_table_id` |
| 20 | `pay23_simple_tax_table_other` | 근로소득 간이세액표(천만원초과) | 8 | `pay23_simple_tax_table_other_id` |
| 21 | `pay24_deduct_table` | 근로소득 공제표 | 9 | `pay24_deduct_table_id` |
| 22 | `pay25_person_deduct` | 인적공제금액 | 5 | `pay25_person_deduct_id` |
| 23 | `pay26_tax_calc_table` | 과세표준 구간별 세액 계산표 | 7 | `pay26_tax_calc_table_id` |
| 24 | `pay27_tax_deduct_table` | 근로소득세액공제표 | 7 | `pay27_tax_deduct_table_id` |
| 25 | `pay28_tax_deduct_limit` | 근로소득세액공제한도 | 8 | `pay28_tax_deduct_limit_id` |
| 26 | `pay29_other_setup` | 급여공제 기타설정 | 10 | `pay29_other_setup_id` |
| 27 | `pay30_basic_setup` | 급여공제 회사별 기본설정 | 7 | `pay30_basic_setup_id` |
| 28 | `pay31_insure_apply` | 사원별 4대보험 신고정보 | 18 | `pay31_insure_apply_id` |
| 29 | `pay32_insure_pay` | 4대보험 정산금액 납부정보 | 12 | `pay32_insure_pay_id` |
| 30 | `pay33_insure_adjust` | 4대보험 연말정산금액 계산내역 | 16 | `pay33_insure_adjust_id` |
| 31 | `pay34_work_time_config` | 근로시간 기준관리 | 11 | `pay34_work_time_config_id` |
| 32 | `pay40_income_tax_withholding` | 갑근세원천징수확인서 발급 | 10 | `pay40_income_tax_withholding_id` |
| 33 | `pay50_expense` | 지출결의서 | 39 | `pay50_expense_id` |
| 34 | `pay51_expense_form` | 사업비 지출요청 상세양식 | 4 | `pay51_expense_form_id` |
| 35 | `pay52_favorite_account` | 자주쓰는 계정과목(지출결의서용) | 4 | `pay52_favorite_account_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **68개**
- **UI 컴포넌트 수**: 총 133개 (Tab/Page: 68개, Lookup/Popup/기타: 65개)
- **서버 서비스 클래스 수**: **35개**
- **MyBatis 매퍼 XML 수**: **34개**
- **DB 테이블 수**: **35개**
