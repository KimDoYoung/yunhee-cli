# emp (인사 / 사원정보 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `emp` (인사 / 사원정보 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/emp/*`, `myApp/server/emp/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`emp##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`emp` 도메인은 **인사 / 사원정보 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **EMP-01** | **경영관리** | 경영관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **EMP-02** | **고객관리** | 고객관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **EMP-03** | **급여관리** | 급여관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **EMP-04** | **기본정보** | 기본정보 관련 화면 및 처리 모듈 | 1개 화면 |
| **EMP-05** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 28개 화면 |
| **EMP-06** | **대외보고서** | 대외보고서 관련 화면 및 처리 모듈 | 2개 화면 |
| **EMP-07** | **메일관리** | 메일관리 관련 화면 및 처리 모듈 | 2개 화면 |
| **EMP-08** | **사업비 신청** | 사업비 신청 관련 화면 및 처리 모듈 | 2개 화면 |
| **EMP-09** | **사업비관리** | 사업비관리 관련 화면 및 처리 모듈 | 2개 화면 |
| **EMP-10** | **외출/출장/휴가** | 외출/출장/휴가 관련 화면 및 처리 모듈 | 5개 화면 |
| **EMP-11** | **인사평가** | 인사평가 관련 화면 및 처리 모듈 | 5개 화면 |
| **EMP-12** | **자산&경영** | 자산&경영 관련 화면 및 처리 모듈 | 2개 화면 |
| **EMP-13** | **전자결재** | 전자결재 관련 화면 및 처리 모듈 | 2개 화면 |
| **EMP-14** | **조직 및 사원관리** | 조직 및 사원관리 관련 화면 및 처리 모듈 | 4개 화면 |
| **EMP-15** | **화면권한관리** | 화면권한관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **EMP-16** | **휴가/출장 관리** | 휴가/출장 관리 관련 화면 및 처리 모듈 | 7개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### EMP-01. 경영관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **조직별 사원조회(관리자)** | `Emp00_Tab_OrgEmpManager` | 1031 | 조직별 사원조회(관리자) |

### EMP-02. 고객관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 2 | **사용자정보 조회** | `Emp01_Tab_UserInfo` | 1325 | 사용자 연락처 조회 |

### EMP-03. 급여관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **급여공제정보** | `Emp35_Tab_DeductPerson` | 1277 | 사원별 급여공제 정보관리 |

### EMP-04. 기본정보
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 4 | **사원정보 등록** | `Emp00_Tab_TransInfo` | 1452 | 사원정보 등록 기능 처리 |

### EMP-05. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 5 | **Emp00_RDPage_ColComments** | `Emp00_RDPage_ColComments` | - | Emp00_RDPage_ColComments 기능 처리 |
| 6 | **미입력시 자동정렬** | `Emp01_TabPage_Person` | - | 미입력시 자동정렬 기능 처리 |
| 7 | **기준년월** | `Emp01_Tab_PersonState` | - | 기준년월 기능 처리 |
| 8 | **생년월일 미입력** | `Emp02_TabPage_Others` | - | 생년월일 미입력 기능 처리 |
| 9 | **특정직위 및 알림설정** | `Emp03_TabPage_Trans` | - | 특정직위 및 알림설정 기능 처리 |
| 10 | **겸직발령** | `Emp04_TabPage_AddTitle` | - | 겸직발령 기능 처리 |
| 11 | **학력정보** | `Emp05_TabPage_Academic` | - | 학력정보 기능 처리 |
| 12 | **가족사항** | `Emp06_TabPage_Family` | - | 가족사항 기능 처리 |
| 13 | **경력사항** | `Emp07_TabPage_Career` | - | 경력사항 기능 처리 |
| 14 | **자격사항** | `Emp08_TabPage_License` | - | 자격사항 기능 처리 |
| 15 | **고과(평가)내역** | `Emp09_TabPage_Evaluation` | - | 고과(평가)내역 기능 처리 |
| 16 | **상벌내역** | `Emp11_TabPage_Reward` | - | 상벌내역 기능 처리 |
| 17 | **행사내역** | `Emp12_TabPage_Event` | - | 행사내역 기능 처리 |
| 18 | **경력사항** | `Emp13_TabPage_Project` | - | 경력사항 기능 처리 |
| 19 | **급여계좌** | `Emp14_TabPage_Account` | - | 급여계좌 기능 처리 |
| 20 | **행 추가** | `Emp16_TabPage_CertMapping` | - | 행 추가 기능 처리 |
| 21 | **연관파일** | `Emp17_TabPage_RelateFile` | - | 연관파일 기능 처리 |
| 22 | **연관파일** | `Emp18_TabPage_RelateFile` | - | 연관파일 기능 처리 |
| 23 | **일괄등록** | `Emp19_TabPage_education` | - | 일괄등록 기능 처리 |
| 24 | **생성** | `Emp21_TabPage_UnLeaveList1` | - | 생성 기능 처리 |
| 25 | **생성** | `Emp21_TabPage_UnLeaveList2` | - | 생성 기능 처리 |
| 26 | **포상휴가를 먼저 선택해주세요** | `Emp23_Page_EtcLeavePerson` | - | 포상휴가를 먼저 선택해주세요 기능 처리 |
| 27 | **금융투자전문인력구분** | `Emp32_TabPage_RelateLicense` | - | 금융투자전문인력구분 기능 처리 |
| 28 | **적용시작일** | `Emp35_Page_DeductDate` | - | 적용시작일 기능 처리 |
| 29 | **적용시작일** | `Emp35_TabPage_DeductDate` | - | 적용시작일 기능 처리 |
| 30 | **추가인적공제** | `Emp35_TabPage_DeductInsert` | - | 추가인적공제 기능 처리 |
| 31 | **구분** | `Emp57_TabPage_Insert` | - | 구분 기능 처리 |
| 32 | **사원** | `Emp93_Tabpage_SmsNoticeTargetList` | - | 사원 기능 처리 |

### EMP-06. 대외보고서
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 33 | **인력현황** | `Emp01_Tab_DueDiligence` | 1324 | 인력현황 |
| 34 | **기간별 입퇴사현황** | `Emp01_Tab_InoutState` | 1287 | 기간별 입퇴사현황 |

### EMP-07. 메일관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 35 | **주소록 관리** | `Emp10_Tab_AddrBook` | 1025 | 주소록 관리 |
| 36 | **공용주소록 관리** | `Emp10_Tab_PublicAddrBook` | 1211 | 공용주소록 관리 |

### EMP-08. 사업비 신청
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 37 | **복리후생비 신청** | `Emp17_Tab_Benefit` | 1221 | 복리후생비 신청 |
| 38 | **여비교통비 신청** | `Emp50_Tab_TransportExpense` | 1349 | 여비교통비 신청 |

### EMP-09. 사업비관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 39 | **복리후생비 관리** | `Emp17_Tab_BenefitManager` | 1222 | 복리후생비 관리 |
| 40 | **여비교통비 관리** | `Emp50_Tab_TransportExpenseMng` | 1348 | 여비교통비 관리 |

### EMP-10. 외출/출장/휴가
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 41 | **휴가신청** | `Emp20_Tab_Leave` | 1032 | 휴가신청 |
| 42 | **휴가신청조회** | `Emp20_Tab_LeaveList` | 1034 | 휴가신청조회 |
| 43 | **연월차휴가 지정통보** | `Emp21_Tab_PersonList` | 1184 | 미사용 연차휴가지정통보 |
| 44 | **출장품의 및 결과보고** | `Emp53_Tab_BizTrip` | 1359 | insert menu |
| 45 | **외출등록** | `Emp54_Tab_Errand` | 1358 | 외출등록 기능 처리 |

### EMP-11. 인사평가
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 46 | **인사평가수행(평가자)** | `Emp43_Tab_EvalExecute` | 1393 | 인사평가수행(평가자) 기능 처리 |
| 47 | **인사평가 결과조회** | `Emp43_Tab_EvalResult` | 1396 | 인사평가 결과조회 기능 처리 |
| 48 | **인사평가 대상자** | `Emp43_Tab_EvalTarget` | 1392 | 인사평가 대상자 기능 처리 |
| 49 | **인사평가보고(대표이사)** | `Emp43_Tab_FinalAppr` | 1395 | 인사평가보고(대표이사) 기능 처리 |
| 50 | **인사평가결과(인사부)** | `Emp43_Tab_FirstAppr` | 1394 | 인사평가결과(인사부) 기능 처리 |

### EMP-12. 자산&경영
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 51 | **인사평가 항목(Admin)** | `Emp41_Tab_EvalList` | 1398 | 인사평가 항목(Admin) 기능 처리 |
| 52 | **복리후생비 코드관리** | `Emp55_Tab_benefitInfoManager` | 1373 | Emp55_Tab_benefitInfoManager |

### EMP-13. 전자결재
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 53 | **결재선 예외처리** | `Emp30_Tab_ApprStepExcept` | 1439 | 결재선 예외처리 |
| 54 | **결재서명관리** | `Emp60_Tab_Sign` | 1501 | 결재서명관리 기능 처리 |

### EMP-14. 조직 및 사원관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 55 | **사원정보 변경조회** | `Emp00_Tab_ChangeHistory` | 1474 | 사원정보 변경조회 기능 처리 |
| 56 | **조직별 사원조회** | `Emp00_Tab_OrgPerson` | 1030 | 조직별 사원조회 |
| 57 | **증명서 발급** | `Emp15_Tab_Cert` | 1115 | 재직증명서, 경력증명서, 퇴직증명서, 징계내역 확인서를 발급하는 화면 |
| 58 | **임원정보 관리** | `Emp31_Tab_Director` | 1294 | 임원정보 관리 |

### EMP-15. 화면권한관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 59 | **사원별 메뉴권한(View)** | `Emp00_Tab_RoleMenu` | 1283 | 사원별 메뉴권한(View) |

### EMP-16. 휴가/출장 관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 60 | **휴가관리(경영관리팀)** | `Emp20_Tab_LeaveManager` | 1033 | 휴가관리(경영관리팀) |
| 61 | **연월차휴가 현황** | `Emp20_Tab_YearList` | 1035 | 연차/월차 휴가 현황-연차수당 산정내역 |
| 62 | **연차휴가 사용촉진** | `Emp21_Tab_UnLeaveList` | 1185 | 미사용 연차휴가관리 (잔여 연월차 사용촉진, 지정통보) |
| 63 | **포상휴가관리** | `Emp22_Tab_EtcLeave` | 1234 | 포상휴가관리 |
| 64 | **공동연차관리** | `Emp24_Tab_JointLeave` | 1233 | 공동연차관리 |
| 65 | **출장관리** | `Emp53_Tab_BizTripManager` | 1381 | 출장관리 기능 처리 |
| 66 | **외출관리** | `Emp54_Tab_ErrandManager` | 1465 | 외출관리 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/emp/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Emp00_TransInfo` | Emp00_TransInfo 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Emp01_Person` | Emp01_Person 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Emp02_Others` | Emp02_Others 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Emp03_Trans` | Emp03_Trans 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Emp04_AddTitle` | Emp04_AddTitle 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Emp05_Academic` | Emp05_Academic 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Emp06_Family` | Emp06_Family 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Emp07_Career` | Emp07_Career 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Emp08_License` | Emp08_License 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Emp09_Evaluation` | Emp09_Evaluation 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Emp10_AddrBook` | Emp10_AddrBook 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Emp11_Reward` | Emp11_Reward 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Emp12_Event` | Emp12_Event 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Emp13_Project` | Emp13_Project 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Emp14_Account` | Emp14_Account 비즈니스 로직 및 RPC 서비스 처리 |
| 16 | `Emp15_Cert` | Emp15_Cert 비즈니스 로직 및 RPC 서비스 처리 |
| 17 | `Emp16_CertMapping` | Emp16_CertMapping 비즈니스 로직 및 RPC 서비스 처리 |
| 18 | `Emp17_Benefit` | Emp17_Benefit 비즈니스 로직 및 RPC 서비스 처리 |
| 19 | `Emp18_RelateFile` | Emp18_RelateFile 비즈니스 로직 및 RPC 서비스 처리 |
| 20 | `Emp19_Education` | Emp19_Education 비즈니스 로직 및 RPC 서비스 처리 |
| 21 | `Emp20_Leave` | Emp20_Leave 비즈니스 로직 및 RPC 서비스 처리 |
| 22 | `Emp21_UnLeave` | Emp21_UnLeave 비즈니스 로직 및 RPC 서비스 처리 |
| 23 | `Emp22_EtcLeave` | Emp22_EtcLeave 비즈니스 로직 및 RPC 서비스 처리 |
| 24 | `Emp23_EtcLeavePerson` | Emp23_EtcLeavePerson 비즈니스 로직 및 RPC 서비스 처리 |
| 25 | `Emp24_JointLeave` | Emp24_JointLeave 비즈니스 로직 및 RPC 서비스 처리 |
| 26 | `Emp25_MypageNotice` | Emp25_MypageNotice 비즈니스 로직 및 RPC 서비스 처리 |
| 27 | `Emp26_InitLeave` | Emp26_InitLeave 비즈니스 로직 및 RPC 서비스 처리 |
| 28 | `Emp28_JointLeaveExcept` | Emp28_JointLeaveExcept 비즈니스 로직 및 RPC 서비스 처리 |
| 29 | `Emp30_ApprStepExcept` | Emp30_ApprStepExcept 비즈니스 로직 및 RPC 서비스 처리 |
| 30 | `Emp31_Director` | Emp31_Director 비즈니스 로직 및 RPC 서비스 처리 |
| 31 | `Emp32_RelateLicense` | Emp32_RelateLicense 비즈니스 로직 및 RPC 서비스 처리 |
| 32 | `Emp33_ExceptBiz` | Emp33_ExceptBiz 비즈니스 로직 및 RPC 서비스 처리 |
| 33 | `Emp35_Deduct` | Emp35_Deduct 비즈니스 로직 및 RPC 서비스 처리 |
| 34 | `Emp36_AddDeduct` | Emp36_AddDeduct 비즈니스 로직 및 RPC 서비스 처리 |
| 35 | `Emp40_EvalListStd` | Emp40_EvalListStd 비즈니스 로직 및 RPC 서비스 처리 |
| 36 | `Emp41_EvalList` | Emp41_EvalList 비즈니스 로직 및 RPC 서비스 처리 |
| 37 | `Emp42_EvalGrade` | Emp42_EvalGrade 비즈니스 로직 및 RPC 서비스 처리 |
| 38 | `Emp43_EvalTarget` | Emp43_EvalTarget 비즈니스 로직 및 RPC 서비스 처리 |
| 39 | `Emp44_EvalWrite` | Emp44_EvalWrite 비즈니스 로직 및 RPC 서비스 처리 |
| 40 | `Emp45_EvalRelateAppr` | Emp45_EvalRelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 41 | `Emp50_TransportExpense` | Emp50_TransportExpense 비즈니스 로직 및 RPC 서비스 처리 |
| 42 | `Emp51_RelateAppr` | Emp51_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 43 | `Emp52_RelateAppr` | Emp52_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 44 | `Emp53_BizTrip` | Emp53_BizTrip 비즈니스 로직 및 RPC 서비스 처리 |
| 45 | `Emp54_Errand` | Emp54_Errand 비즈니스 로직 및 RPC 서비스 처리 |
| 46 | `Emp55_BenefitInfo` | Emp55_BenefitInfo 비즈니스 로직 및 RPC 서비스 처리 |
| 47 | `Emp56_Share` | Emp56_Share 비즈니스 로직 및 RPC 서비스 처리 |
| 48 | `Emp57_AddrBookGroup` | Emp57_AddrBookGroup 비즈니스 로직 및 RPC 서비스 처리 |
| 49 | `Emp60_Sign` | Emp60_Sign 비즈니스 로직 및 RPC 서비스 처리 |
| 50 | `Emp90_Notice` | Emp90_Notice 비즈니스 로직 및 RPC 서비스 처리 |
| 51 | `Emp91_MenuInfoNotice` | Emp91_MenuInfoNotice 비즈니스 로직 및 RPC 서비스 처리 |
| 52 | `Emp92_SmsNotice` | Emp92_SmsNotice 비즈니스 로직 및 RPC 서비스 처리 |
| 53 | `Emp93_SmsNoticeTarget` | Emp93_SmsNoticeTarget 비즈니스 로직 및 RPC 서비스 처리 |
| 54 | `Hire` | Hire 비즈니스 로직 및 RPC 서비스 처리 |
| 55 | `License` | License 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/emp/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `emp00_trans_info.xml` | `emp00_trans_info` 테이블 관련 쿼리 매핑 |
| 2 | `emp01_person.xml` | `emp01_person` 테이블 관련 쿼리 매핑 |
| 3 | `emp02_others.xml` | `emp02_others` 테이블 관련 쿼리 매핑 |
| 4 | `emp03_trans.xml` | `emp03_trans` 테이블 관련 쿼리 매핑 |
| 5 | `emp04_add_title.xml` | `emp04_add_title` 테이블 관련 쿼리 매핑 |
| 6 | `emp05_academic.xml` | `emp05_academic` 테이블 관련 쿼리 매핑 |
| 7 | `emp06_family.xml` | `emp06_family` 테이블 관련 쿼리 매핑 |
| 8 | `emp07_career.xml` | `emp07_career` 테이블 관련 쿼리 매핑 |
| 9 | `emp08_license.xml` | `emp08_license` 테이블 관련 쿼리 매핑 |
| 10 | `emp09_evaluation.xml` | `emp09_evaluation` 테이블 관련 쿼리 매핑 |
| 11 | `emp10_addr_book.xml` | `emp10_addr_book` 테이블 관련 쿼리 매핑 |
| 12 | `emp11_reward.xml` | `emp11_reward` 테이블 관련 쿼리 매핑 |
| 13 | `emp12_event.xml` | `emp12_event` 테이블 관련 쿼리 매핑 |
| 14 | `emp13_project.xml` | `emp13_project` 테이블 관련 쿼리 매핑 |
| 15 | `emp14_account.xml` | `emp14_account` 테이블 관련 쿼리 매핑 |
| 16 | `emp15_cert.xml` | `emp15_cert` 테이블 관련 쿼리 매핑 |
| 17 | `emp16_cert_mapping.xml` | `emp16_cert_mapping` 테이블 관련 쿼리 매핑 |
| 18 | `emp17_benefit.xml` | `emp17_benefit` 테이블 관련 쿼리 매핑 |
| 19 | `emp18_relate_file.xml` | `emp18_relate_file` 테이블 관련 쿼리 매핑 |
| 20 | `emp19_education.xml` | `emp19_education` 테이블 관련 쿼리 매핑 |
| 21 | `emp20_leave.xml` | `emp20_leave` 테이블 관련 쿼리 매핑 |
| 22 | `emp21_un_leave.xml` | `emp21_un_leave` 테이블 관련 쿼리 매핑 |
| 23 | `emp22_etc_leave.xml` | `emp22_etc_leave` 테이블 관련 쿼리 매핑 |
| 24 | `emp23_etc_leave_person.xml` | `emp23_etc_leave_person` 테이블 관련 쿼리 매핑 |
| 25 | `emp24_joint_leave.xml` | `emp24_joint_leave` 테이블 관련 쿼리 매핑 |
| 26 | `emp25_mypage_notice.xml` | `emp25_mypage_notice` 테이블 관련 쿼리 매핑 |
| 27 | `emp26_init_leave.xml` | `emp26_init_leave` 테이블 관련 쿼리 매핑 |
| 28 | `emp28_joint_leave_except.xml` | `emp28_joint_leave_except` 테이블 관련 쿼리 매핑 |
| 29 | `emp30_appr_step_except.xml` | `emp30_appr_step_except` 테이블 관련 쿼리 매핑 |
| 30 | `emp31_director.xml` | `emp31_director` 테이블 관련 쿼리 매핑 |
| 31 | `emp32_relate_license.xml` | `emp32_relate_license` 테이블 관련 쿼리 매핑 |
| 32 | `emp33_except_biz.xml` | `emp33_except_biz` 테이블 관련 쿼리 매핑 |
| 33 | `emp35_deduct.xml` | `emp35_deduct` 테이블 관련 쿼리 매핑 |
| 34 | `emp36_add_deduct.xml` | `emp36_add_deduct` 테이블 관련 쿼리 매핑 |
| 35 | `emp40_eval_list_std.xml` | `emp40_eval_list_std` 테이블 관련 쿼리 매핑 |
| 36 | `emp41_eval_list.xml` | `emp41_eval_list` 테이블 관련 쿼리 매핑 |
| 37 | `emp42_eval_grade.xml` | `emp42_eval_grade` 테이블 관련 쿼리 매핑 |
| 38 | `emp43_eval_target.xml` | `emp43_eval_target` 테이블 관련 쿼리 매핑 |
| 39 | `emp44_eval_write.xml` | `emp44_eval_write` 테이블 관련 쿼리 매핑 |
| 40 | `emp45_eval_relate_appr.xml` | `emp45_eval_relate_appr` 테이블 관련 쿼리 매핑 |
| 41 | `emp50_transport_expense.xml` | `emp50_transport_expense` 테이블 관련 쿼리 매핑 |
| 42 | `emp51_relate_appr.xml` | `emp51_relate_appr` 테이블 관련 쿼리 매핑 |
| 43 | `emp52_relate_appr.xml` | `emp52_relate_appr` 테이블 관련 쿼리 매핑 |
| 44 | `emp53_biz_trip.xml` | `emp53_biz_trip` 테이블 관련 쿼리 매핑 |
| 45 | `emp54_errand.xml` | `emp54_errand` 테이블 관련 쿼리 매핑 |
| 46 | `emp55_benefit_info.xml` | `emp55_benefit_info` 테이블 관련 쿼리 매핑 |
| 47 | `emp56_share.xml` | `emp56_share` 테이블 관련 쿼리 매핑 |
| 48 | `emp57_addr_book_group.xml` | `emp57_addr_book_group` 테이블 관련 쿼리 매핑 |
| 49 | `emp60_sign.xml` | `emp60_sign` 테이블 관련 쿼리 매핑 |
| 50 | `emp90_notice.xml` | `emp90_notice` 테이블 관련 쿼리 매핑 |
| 51 | `emp91_menu_info_notice.xml` | `emp91_menu_info_notice` 테이블 관련 쿼리 매핑 |
| 52 | `emp92_sms_notice.xml` | `emp92_sms_notice` 테이블 관련 쿼리 매핑 |
| 53 | `emp93_sms_notice_target.xml` | `emp93_sms_notice_target` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `emp01_person` | 개인정보 | 18 | `emp01_person_id` |
| 2 | `emp02_others` | Others 개인정보 | 21 | `emp02_others_id` |
| 3 | `emp03_trans` | 발령정보 | 19 | `emp03_trans_id` |
| 4 | `emp04_add_title` | 겸직발령 | 9 | `emp04_add_title_id` |
| 5 | `emp05_academic` | 학력정보 | 11 | `emp05_academic_id` |
| 6 | `emp06_family` | 가족사항 | 12 | `emp06_family_id` |
| 7 | `emp07_career` | 경력사항 | 14 | `emp07_career_id` |
| 8 | `emp08_license` | 자격사항 | 10 | `emp08_license_id` |
| 9 | `emp09_evaluation` | 고과평가 | 8 | `emp09_evaluation_id` |
| 10 | `emp10_addr_book` | 주소록 | 10 | `emp10_addr_book_id` |
| 11 | `emp11_reward` | 상벌내역 | 8 | `emp11_reward_id` |
| 12 | `emp12_event` | 행사내역 | 7 | `emp12_event_id` |
| 13 | `emp13_project` | 프로젝트 | 6 | `emp13_project_id` |
| 14 | `emp14_account` | 급여계좌관리 | 7 | `emp14_account_id` |
| 15 | `emp15_cert` | 증명서발급 | 9 | `emp15_cert_id` |
| 16 | `emp16_cert_mapping` | 증명서 맵핑 => com10_form_mapping 사용으로 안쓰는 테이블이 됨 | 7 | `emp16_cert_mapping_id` |
| 17 | `emp17_benefit` | 복리후생비 | 15 | `emp17_benefit_id` |
| 18 | `emp18_relate_file` | 사원 연관파일 | 3 | `emp18_relate_file_id` |
| 19 | `emp19_education` | 교육사항 | 7 | `emp19_education_id` |
| 20 | `emp20_leave` | 휴가관리 | 21 | `emp20_leave_id` |
| 21 | `emp21_un_leave` | 미사용휴가관리 | 10 | `emp21_un_leave_id` |
| 22 | `emp22_etc_leave` | 기타휴가 | 9 | `emp22_etc_leave_id` |
| 23 | `emp23_etc_leave_person` | 기타휴가-대상직원 | 3 | `emp23_etc_leave_person_id` |
| 24 | `emp24_joint_leave` | 공동휴가 | 8 | `emp24_joint_leave_id` |
| 25 | `emp25_mypage_notice` | MyPage알림권한 | 6 | `emp25_mypage_notice_id` |
| 26 | `emp26_init_leave` | 사용휴가일수 초기설정 | 5 | `emp26_init_leave_id` |
| 27 | `emp27_leave_old` | 휴가사용내역(AssetERP 사용전) | 10 | `emp27_leave_old_id` |
| 28 | `emp28_joint_leave_except` | 공동휴가 제외사원 | 4 | `emp28_joint_leave_except_id` |
| 29 | `emp29_over_leave` | 초과연차 | 4 | `emp29_over_leave_id` |
| 30 | `emp30_appr_step_except` | 문서결재라인 예외 | 6 | `emp30_appr_step_except_id` |
| 31 | `emp31_director` | 임원정보 | 13 | `emp31_director_id` |
| 32 | `emp32_relate_license` | 금융투자전문인력구분연결 | 4 | `emp32_relate_license_id` |
| 33 | `emp33_except_biz` | 사원별 예외업무 관리 | 8 | `emp33_except_biz_id` |
| 34 | `emp35_deduct` | 급여공제항목 | 11 | `emp35_deduct_id` |
| 35 | `emp36_add_deduct` | 추가인적공제정보 | 4 | `emp36_add_deduct_id` |
| 36 | `emp40_eval_list_std` | 인사평가리스트 적용기준 | 4 | `emp40_eval_list_std_id` |
| 37 | `emp41_eval_list` | 인사평가 평가리스트 | 7 | `emp41_eval_list_id` |
| 38 | `emp42_eval_grade` | 인사평가 평가등급관리 | 7 | `emp42_eval_grade_id` |
| 39 | `emp43_eval_target` | 인사평가 대상자 | 23 | `emp43_eval_target_id` |
| 40 | `emp44_eval_write` | 인사평가수행 | 6 | `emp44_eval_write_id` |
| 41 | `emp45_eval_relate_appr` | 인사평가 상신문서 연결 | 6 | `emp45_eval_relate_appr_id` |
| 42 | `emp50_transport_expense` | 여비교통비 | 12 | `emp50_transport_expense_id` |
| 43 | `emp51_relate_appr` | 여비교통비 신청서 | 9 | `emp51_relate_appr_id` |
| 44 | `emp52_relate_appr` | 여비교통비 지출결의서 | 4 | `emp52_relate_appr_id` |
| 45 | `emp53_biz_trip` | 출장 | 16 | `emp53_biz_trip_id` |
| 46 | `emp54_errand` | 외출 | 13 | `emp54_errand_id` |
| 47 | `emp55_benefit_info` | 복리후생비 고객사별 설정 | 7 | `emp55_benefit_info_id` |
| 48 | `emp56_share` | 출장,외출등 공유지정 | 6 | `emp56_share_id` |
| 49 | `emp57_addr_book_group` | 주소록그룹 | 8 | `emp57_addr_book_group_id` |
| 50 | `emp60_sign` | 결재서명관리 | 5 | `emp60_sign_id` |
| 51 | `emp90_notice` | 캘린더알림 | 4 | `emp90_notice_id` |
| 52 | `emp91_menu_info_notice` | 매뉴소개 알람여부 | 4 | `emp91_menu_info_notice_id` |
| 53 | `emp92_sms_notice` | SMS 알림 | 7 | `emp92_sms_notice_id` |
| 54 | `emp93_sms_notice_target` | SMS구분코드별 알림 | 5 | `emp93_sms_notice_target_id` |
| 55 | `emp99_person_del` | - | 21 | `emp99_person_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **66개**
- **UI 컴포넌트 수**: 총 136개 (Tab/Page: 66개, Lookup/Popup/기타: 70개)
- **서버 서비스 클래스 수**: **55개**
- **MyBatis 매퍼 XML 수**: **53개**
- **DB 테이블 수**: **55개**
