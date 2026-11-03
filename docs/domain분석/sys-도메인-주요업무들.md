# sys (시스템 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `sys` (시스템 관리) 도메인에 존재하는 전체 주요 업무를 누락 없이 식별하고, 업무 영역별로 체계적으로 분류한 1차 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/sys/*`, `myApp/server/sys/*`, `MenuOpener.java`), 매퍼 XML (`sys##_*.xml`), DB 테이블 및 메뉴 메타데이터 (`sys06_menu`, `sys01`~`sys99`).

---

## 1. 업무 영역별 분류 요약

`sys` 도메인은 **SaaS 멀티테넌트 환경의 기반 플랫폼**으로서 다음 9가지 핵심 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 |
|:---:|:---|:---|:---|
| **SYS-01** | **테넌트(회사/고객사) 관리** | 고객사 생성/설정, 도메인, 결재선 잠금, 모듈 정책, 초기 데이터 셋업 | `Sys01_Company`, `Sys03_CompanyMenu` |
| **SYS-02** | **사용자 및 계정/인증 관리** | 사용자 계정 생성, 비밀번호 초기화, 잠금 해제, 관리자(Admin) 계정 | `Sys02_User`, `Sys25_Password`, `Sys80_Admin` |
| **SYS-03** | **권한 관리 (Role & Permission)** | 권한그룹 등록, 권한별 메뉴/기능 맵핑, 사용자-권한 맵핑, 테넌트간 권한복사 | `Sys04_Role`, `Sys05_UserRole`, `Sys07_RoleMenu` |
| **SYS-04** | **메뉴 체계 및 화면 가이드 관리** | 전체 메뉴 트리 구조, 매뉴얼 URL/첨부 연결, 화면별 도움말(가이드) 관리 | `Sys06_Menu`, `Sys55_MenuGuide` |
| **SYS-05** | **특정화면(민감화면) 사용요청 및 통제** | 민감 화면(급여, 인사 등) 임시 권한 신청/승인/사용 이력 관리 | `Sys50`~`Sys54_SpecificMenu` |
| **SYS-06** | **공통 코드 및 기준정보 관리** | 시스템/고객사 공통코드(Kind/Code), 거래처(기관), 휴일/영업일 달력, 연차기준 | `Sys08`, `Sys09`, `Sys12`, `Sys14`, `Sys15`, `Sys30` |
| **SYS-07** | **시스템 보안 / 접속 제어 / 파일 정책** | 로그인 이력, 접속 허용 IP/MAC 통제, 2차 인증, 실시간 세션, 파일 확장자/보안 정책 | `Sys26`~`Sys29`, `Sys60_FilePolicy`, `Sys83` |
| **SYS-08** | **감사 로그 / 모니터링 / 웹소켓 알림** | 실시간 접속자 모니터링, 공지/강제 로그아웃 웹소켓, 화면 실사용 로그, 서버 디스크 사용량 | `Sys10_TotalSize`, `Sys86_Websocket`, `Sys96_MenuLog` |
| **SYS-09** | **운영 지원 / 유지보수 (A/S, 매뉴얼)** | 고객사 오류 접수 및 개선 요청(A/S), 공식 사용자 매뉴얼, 자문위원/관리팀 정보 | `Sys90_AfterService`, `Sys91`, `Sys92`, `Sys95_Manual` |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### SYS-01. 테넌트 (회사 / 고객사) 관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 서버 클래스 및 테이블 | 업무 설명 |
|:---:|:---|:---|:---|:---|
| 1 | **고객사(회사) 기본정보 관리** | `Sys01_Tab_Company` | `Sys01_Company`<br>(`sys01_company`) | 회사명, 법인/사업자번호, 대표자, 설립일, 서브도메인, 메일서버 설정 |
| 2 | **회사별 모듈 정책 및 결재잠금 설정** | `Sys01_TabPage_Info03, 04` | `Sys01_Company`<br>(`sys01_company`) | 전자결재 결재선 잠금 여부, 내부통제 사용 여부, 회계/휴가 결산월 등 회사별 운영 정책 |
| 3 | **고객사 신규 생성 및 초기 데이터 복사** | `Sys01_Tab_Company` | `Sys01_Company` | 신규 고객사 등록 시 표준 메뉴 권한, 문서 개요 등 기본 마스터 일괄 복사 |
| 4 | **회사별 사용 메뉴 맵핑** | `Sys03_Tab_CompanyMenu` | `Sys03_CompanyMenu`<br>(`sys03_company_menu`) | 각 회사(테넌트)별로 서비스할 메뉴를 선택적으로 활성화/비활성화 |

---

### SYS-02. 사용자 및 계정 / 인증 관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 서버 클래스 및 테이블 | 업무 설명 |
|:---:|:---|:---|:---|:---|
| 5 | **사용자 계정 관리** | `Sys02_Tab_User`, `TabPage_User` | `Sys02_User`<br>(`sys02_user`) | 사용자 ID, 성명, 이메일, 전화번호, 사진, 로그인 상태 및 기본 정보 등록/수정 |
| 6 | **비밀번호 초기화 및 변경** | `Sys25_Tab_ResetPassword` | `Sys25_Password`<br>(`sys25_password`) | 비밀번호 오류 초과 계정 잠금 해제, 임시 비밀번호 발급 및 변경 |
| 7 | **Admin(시스템 관리자) 계정 관리** | `Sys80_Tab_AdminUserList` | `Sys80_AdminUserList`<br>(`sys80_admin_user_list`) | 최상위 시스템 관리자(슈퍼유저) 계정 등록 및 임시 비밀번호 SMS 발송 |
| 8 | **Admin 접속 이력 조회** | `Sys81_Tab_AdminUserHistory` | `Sys81_AdminUserHistory`<br>(`sys81_admin_user_history`) | 시스템 관리자 계정의 로그인 일시, 접속 정보 이력 추적 |
| 9 | **2차 인증(추가 인증) 관리** | `Sys83_SecondaryAuthUser` | `Sys83_SecondaryAuthUser`<br>(`sys83_secondary_auth_user`) | 민감 권한자에 대한 2차 인증(OTP/SMS 임시번호) 대상자 지정 및 인증 처리 |

---

### SYS-03. 권한 관리 (Role & Permission)
| 번호 | 업무명 | GXT 화면 컴포넌트 | 서버 클래스 및 테이블 | 업무 설명 |
|:---:|:---|:---|:---|:---|
| 10 | **권한그룹(Role) 관리** | `Sys04_Tab_Role`, `Sys04_Tab_RoleAdmin` | `Sys04_Role`<br>(`sys04_role`) | 회사별 권한그룹(일반사용자, 부서장, 준법감시인, 관리자 등) 생성 및 속성 부여 |
| 11 | **권한그룹별 메뉴 맵핑** | `Sys07_Tab_RoleMenu`, `Sys07_Tree_RoleMenu` | `Sys07_RoleMenu`<br>(`sys07_role_menu`) | 특정 권한그룹에 접근 가능한 메뉴 트리 체크 및 읽기/쓰기 권한 부여 |
| 12 | **사용자별 권한그룹 맵핑** | `Sys05_Tab_UserRole`, `Sys05_Tab_PersonRole` | `Sys05_UserRole`<br>(`sys05_user_role`) | 사원(사용자)에게 하나 이상의 권한그룹 매핑 (부서/직책/개인별 부여) |
| 13 | **고객사간 권한 복사** | `Sys07_Tab_Company` | `Sys07_RoleMenu` | 기설정된 회사의 권한그룹 및 메뉴 권한 체계를 타 고객사로 일괄 복사 |
| 14 | **고객사별 메뉴/권한 현황 일괄 관리** | `Sys07_Tab_CompanyRoleMenu` | `Sys07_RoleMenu` | 슈퍼관리자 화면에서 전 고객사의 메뉴 권한 매핑을 일괄 모니터링/수정 |
| 15 | **권한 현황 조회 (View)** | `Sys06_Tab_MenuView`, `Sys04_Page_RoleView` | `Sys06_Menu`, `Sys04_Role` | 메뉴 기준 권한그룹 조회, 또는 권한그룹 기준 사용자 매핑 상태 역방향 조회 |

---

### SYS-04. 메뉴 체계 및 화면 가이드 관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 서버 클래스 및 테이블 | 업무 설명 |
|:---:|:---|:---|:---|:---|
| 16 | **전체 메뉴 마스터 관리** | `Sys06_Tab_Menu` | `Sys06_Menu`<br>(`sys06_menu`) | 대/중/소 메뉴 트리 구조, 메뉴번호(Code), 화면 클래스명, 정렬순서, 사용여부 관리 |
| 17 | **화면별 업무 안내(가이드) 등록** | `Sys06_Tab_MenuGuide`, `Sys55_Tab_MenuGuideCompany` | `Sys55_MenuGuideCompany` | 화면별 팝업 안내 문구, 화면 설명 및 고객사 맞춤 가이드 등록 |
| 18 | **사용자 북마크(즐겨찾기)** | `Sys40_Lookup_Bookmark` | `Sys40_Bookmark`<br>(`sys40_bookmark`) | 사용자가 자주 사용하는 메뉴를 개인 즐겨찾기로 등록/관리 |

---

### SYS-05. 특정화면 (민감화면) 사용요청 및 통제
| 번호 | 업무명 | GXT 화면 컴포넌트 | 서버 클래스 및 테이블 | 업무 설명 |
|:---:|:---|:---|:---|:---|
| 19 | **특정업무(민감메뉴) 기준 관리** | `Sys50_TabPage_SpecificMenu` | `Sys50_SpecificMenu`<br>(`sys50_specific_menu`) | 사전 승인이 필요한 통제 대상 메뉴/기능(급여, 민감정보 등) 마스터 정의 |
| 20 | **특정화면 사용 권한 요청** | `Sys53_Tab_SpecificMenuRequest` | `Sys53_SpecificMenuRequest`<br>(`sys53_specific_menu_request`) | 일반 사용자가 특정 민감 메뉴에 대해 사용 사유와 사용 기간을 명시하여 신청 |
| 21 | **특정화면 사용요청 승인/관리 (관리자)** | `Sys53_Tab_SpecificMenuRequestAdmin` | `Sys53_SpecificMenuRequest` | 회사 관리자가 신청 내역을 검토하여 기간 한정 사용 권한 승인 |
| 22 | **특정화면 사용 이력 추적** | `Sys54_Lookup_SpecificMenuHistory` | `Sys54_SpecificMenuHistory`<br>(`sys54_specific_menu_history`) | 특정화면 신청, 승인, 사용 및 반납 이력 전체 감사 추적 |

---

### SYS-06. 공통 코드 및 기준정보 관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 서버 클래스 및 테이블 | 업무 설명 |
|:---:|:---|:---|:---|:---|
| 23 | **시스템 공통코드 관리 (관리자용)** | `Sys08_Tab_CodeKindAdmin` | `Sys08_CodeKind`<br>(`sys08_code_kind`) | 시스템 전체 표준 코드 분류(Kind) 및 시스템 예약 코드 정의 |
| 24 | **고객사 공통코드 관리 (고객사별)** | `Sys08_Tab_CodeKindClient`, `Sys09_Grid_Code` | `Sys08_CodeKind`, `Sys09_Code`<br>(`sys09_code`) | 회사별로 확장 가능한 공통코드 상세값(Key-Value, 순서, 사용여부) 관리 및 복사 |
| 25 | **공통코드 그룹 매핑** | `Sys13_TabPage_Code` | `Sys13_CodeGroup`<br>(`sys13_code_group`) | 코드 간의 상-하위 종속 관계 및 업무 그룹 매핑 관리 |
| 26 | **거래처(기관) 정보 관리** | `Sys15_Tab_Corp`, `Sys17_Grid_CorpAccount` | `Sys15_Corp`, `Sys17_CorpAccount`<br>(`sys15_corp`, `sys17_corp_account`) | 금융기관, 관공서, 협력업체 등 거래처 기본정보 및 계좌정보 관리 |
| 27 | **영업일 및 달력(Calendar) 관리** | `Sys12_Tab_Calendar` | `Sys12_Calendar`<br>(`sys12_calendar`) | 연간 영업일/휴일 여부 설정, 이전/다음 영업일 판정 기준 제공 |
| 28 | **법정/임시 공휴일 관리** | `Sys14_Lookup_Holiday` | `Sys14_Holiday`<br>(`sys14_holiday`) | 국경일, 대체공휴일 등 휴일 마스터 등록 및 연간 달력 자동 반영 |
| 29 | **근속년수별 연차 발생 기준 관리** | `Sys30_Tab_LeaveYear` | `Sys30_LeaveYear`<br>(`sys30_leave_year`, `sys31_leave_company`) | 회사별 근속 연수(1년~N년)에 따른 연차휴가 자동 부여 일수 규칙 관리 |
| 30 | **자격증/면허 코드 관리** | `Sys21_Tab_LicenseCode` | `Sys21_LicenseCode`<br>(`sys21_license_code`) | 임직원 인적사항 입력에 쓰이는 전문 자격증 및 면허 마스터 코드 관리 |

---

### SYS-07. 시스템 보안 / 접속 제어 / 파일 정책
| 번호 | 업무명 | GXT 화면 컴포넌트 | 서버 클래스 및 테이블 | 업무 설명 |
|:---:|:---|:---|:---|:---|
| 31 | **사용자 로그인 이력 조회** | `Sys26_Tab_LoginHistory` | `Sys26_Login`<br>(`sys26_login`) | 사용자 로그인/로그아웃 일시, IP, 웹/모바일 접속 구분, 성공/실패 기록 조회 |
| 32 | **로그인 허용 단말(MAC 주소) 관리** | `Sys27_Tab_LoginManage` | `Sys27_LoginManage`<br>(`sys27_login_manage`) | 사용자별/회사별 등록된 PC MAC 주소 기반 접속 인가 및 미인가 단말 통제 |
| 33 | **보안 로그인(공인 IP) 관리** | `Sys29_Lookup_PublicIpList` | `Sys29_LoginSecure`<br>(`sys29_login_secure`) | 사내 고정 공인 IP에서만 접속을 허용하는 보안 로그인 정책 관리 |
| 34 | **첨부파일 업로드 보안 정책** | `Sys60_Tab_FilePolicy` | `Sys60_FilePolicy`<br>(`sys60_file_policy`) | 업로드 차단 확장자(exe, bat, sh 등) 및 허용 정책 정의 |
| 35 | **삭제 파일 보관 및 복구** | `Sys61_TabPage_DelList` | `Sys61_FileDel`<br>(`sys61_file_del`) | 사용자에 의해 삭제된 첨부파일의 임시 보관 및 관리자 복구 처리 |

---

### SYS-08. 감사 로그 / 모니터링 / 웹소켓 알림
| 번호 | 업무명 | GXT 화면 컴포넌트 | 서버 클래스 및 테이블 | 업무 설명 |
|:---:|:---|:---|:---|:---|
| 36 | **고객사별 메뉴 실사용 로그 분석** | `Sys96_Tab_OpenMenuLogAdmin` | `Sys96_OpenMenuLog`<br>(`sys96_open_menu_log`) | 고객사/사용자/메뉴별 실제 화면 오픈 및 사용 통계 추적 |
| 37 | **고객별 서버 저장공간(디스크) 사용량** | `Sys10_Tab_TotalSize` | `Sys10_File` | 테넌트별 첨부파일 총 용량 및 연도/월별 사용 추이 모니터링 |
| 38 | **미사용(쓰레기) 파일 정리** | `Sys10_Tab_TrashFileList` | `Sys10_File` | 본문 DB 레코드와 연결이 끊어진 고아(Orphan) 파일 탐색 및 일괄 정리 |
| 39 | **실시간 접속자 모니터링 & 웹소켓 알림** | `Sys86_Tab_Websocket` | `Sys28_LoginRealTime`<br>(`sys28_login_real_time`) | 현재 접속 중인 세션 실시간 확인, 긴급 공지 전송 및 강제 로그아웃 지시 |

---

### SYS-09. 운영 지원 / 유지보수 (A/S, 매뉴얼)
| 번호 | 업무명 | GXT 화면 컴포넌트 | 서버 클래스 및 테이블 | 업무 설명 |
|:---:|:---|:---|:---|:---|
| 40 | **개선사항 및 오류 통보 (고객용 A/S 접수)** | `Sys90_Tab_AfterService` | `Sys90_AfterService`<br>(`sys90_after_service`) | 고객사 사용자가 시스템 오류 및 개선 희망사항을 접수하고 처리상태 조회 |
| 41 | **오류/개선사항 처리 및 답변 (운영자용)** | `Sys90_Tab_AfterServiceAdmin` | `Sys90_AfterService` | 운영팀이 접수된 A/S 티켓에 원인(HappenReason) 및 조치내역(Remedy) 등록 |
| 42 | **AssetERP 사용자 매뉴얼 열람** | `Sys95_Tab_Manual` | `Sys95_Manual`<br>(`sys95_manual`) | 업무별 공식 사용자 매뉴얼(PDF/문서) 조회 및 다운로드 |
| 43 | **매뉴얼 마스터 등록 및 관리** | `Sys95_Tab_ManualAdmin` | `Sys95_Manual` | 업무 분류별 신규 매뉴얼 파일 업로드 및 개정 관리 |
| 44 | **자문위원 및 운영 관리팀 소개** | `Sys91_Tab_AdviceMember`, `Sys92_Tab_ManagementTeam` | `Sys91_AdviceMember`, `Sys92_ManagementTeam`<br>(`sys91_advice_member`, `sys92_management_team`) | AssetERP 자문위원 명단/약력 및 고객지원 운영팀 조직/담당업무 안내 |

---

## 3. 요약 통계

- **총 주요 업무 수**: **44개 업무**
- **관련 DB 테이블 수**: **53개 테이블** (`sys01` ~ `sys99`)
- **화면(UI) 컴포넌트**: 탭/페이지 **57개**, 팝업/조회 **90개** (총 147개 Java 파일)
- **서버 서비스 및 매퍼**: **51개 서비스 클래스**, **49개 MyBatis 매퍼 XML**
- **특징**: 단순 일반 설정뿐 아니라 **SaaS 고객사(테넌트) 격리**, **역할 기반 화면/기능 인가**, **민감 화면 사전승인제**, **보안 단말/IP 통제** 등 전사 포털 보안 인프라 성격이 강하게 반영되어 있습니다.
