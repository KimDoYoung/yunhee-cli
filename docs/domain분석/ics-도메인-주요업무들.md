# ics (내부통제 / 법규준수 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `ics` (내부통제 / 법규준수 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/ics/*`, `myApp/server/ics/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`ics##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`ics` 도메인은 **내부통제 / 법규준수 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **ICS-01** | **기타** | 기타 관련 화면 및 처리 모듈 | 2개 화면 |
| **ICS-02** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 7개 화면 |
| **ICS-03** | **내부통제** | 내부통제 관련 화면 및 처리 모듈 | 6개 화면 |
| **ICS-04** | **내부통제 체크리스트** | 내부통제 체크리스트 관련 화면 및 처리 모듈 | 5개 화면 |
| **ICS-05** | **대외활동** | 대외활동 관련 화면 및 처리 모듈 | 2개 화면 |
| **ICS-06** | **문서작성** | 문서작성 관련 화면 및 처리 모듈 | 1개 화면 |
| **ICS-07** | **법규관리** | 법규관리 관련 화면 및 처리 모듈 | 4개 화면 |
| **ICS-08** | **법규정보** | 법규정보 관련 화면 및 처리 모듈 | 3개 화면 |
| **ICS-09** | **법규통제 현황(사용X)** | 법규통제 현황(사용X) 관련 화면 및 처리 모듈 | 1개 화면 |
| **ICS-10** | **임직원 내부통제 준수** | 임직원 내부통제 준수 관련 화면 및 처리 모듈 | 3개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### ICS-01. 기타
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **준감인 사전확인대장** | `Ics40_Tab_DcrPreConfirm` | 1425 | 준감인 사전확인대장 기능 처리 |
| 2 | **심사필 확인대장** | `Ics40_Tab_DcrReviewConfirm` | 1499 | 심사필 확인대장 기능 처리 |

### ICS-02. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **서식파일** | `Ics01_Page_IcsFile` | - | 서식파일 기능 처리 |
| 4 | **등록일** | `Ics01_Page_RevisionHistory` | - | 등록일 기능 처리 |
| 5 | **법규명/서식파일명** | `Ics01_Tab_FileList` | - | 법규명/서식파일명 기능 처리 |
| 6 | **검색** | `Ics01_Tab_IcsFileUser` | - | 검색 기능 처리 |
| 7 | **직원추가** | `Ics04_Page_Share` | - | 직원추가 기능 처리 |
| 8 | **중분류명** | `Ics23_TabPage_CheckList` | - | 중분류명 기능 처리 |
| 9 | **행 추가** | `Ics33_TabPage_ComplianceAnswer` | - | 행 추가 기능 처리 |

### ICS-03. 내부통제
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 10 | **법규관리(관리자)** | `Ics01_Tab_ClassTree` | 1012 | 내부통제 분류 (관리자 메뉴등록) |
| 11 | **법규보고 서식파일 등록** | `Ics01_Tab_IcsFileUpload` | 1107 | 내부통제 서식파일 등록(관리자) |
| 12 | **내부통제 체크리스트(관리자)** | `Ics10_Tab_ChecklistAdmin` | 1232 | 내부통제 체크리스트 (관리자 메뉴등록) |
| 13 | **법규등록신청확인** | `Ics17_Tab_UserRequestAdmin` | 1339 | 법규등록신청확인 화면 |
| 14 | **법규개정내역 등록** | `Ics20_Tab_RevisionHistoryAdmin` | 1257 | 법규정보 개정내역 (관리자 메뉴등록) |
| 15 | **임직원 내부통제 준수리스트** | `Ics30_Tab_Compliance` | 1313 | 임직원 내부통제 준수리스트(관리자전용) (관리자 메뉴등록) |

### ICS-04. 내부통제 체크리스트
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 16 | **내부통제 체크리스트 관리** | `Ics10_Tab_Checklist` | 1228 | 내부통제 체크리스트 - 사용여부 및 작성자그룹지정 |
| 17 | **내부통제내역 확인(부서장)** | `Ics15_Tab_ChecklistConfirm` | 1230 | 내부통제 체크리스트 확인 및 문서상신 |
| 18 | **내부통제내역 현황(준감인)** | `Ics15_Tab_ChecklistStatus` | 1231 | 내부통제 월/분기 체크리스트 현황판 |
| 19 | **내부통제내역 상세(준감인)** | `Ics15_Tab_ChecklistStatusDetail` | 1235 | 내부통제 체크리스트 상세현황 |
| 20 | **내부통제 체크리스트 작성** | `Ics15_Tab_ChecklistWrite` | 1229 | 내부통제 체크리스트 작성 |

### ICS-05. 대외활동
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 21 | **대외활동신청** | `Ics35_Tab_ExtrActivity` | 1431 | 대외활동 승인신청 |
| 22 | **대외활동 신청내역** | `Ics35_Tab_ExtrActivityList` | 1432 | 대외활동 신청내역조회 |

### ICS-06. 문서작성
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 23 | **법규별 문서작성** | `Ics01_Tab_ApprList` | 1014 | 내부통제 관리 |

### ICS-07. 법규관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 24 | **관리그룹별 법규조회(????)** | `Ics01_Tab_ClassTreeByGroup` | 1444 | 관리그룹별 법규조회 |
| 25 | **법규관리** | `Ics01_Tab_ClassTreeUser` | 1013 | 내부통제 분류 |
| 26 | **법규 관리그룹 등록** | `Ics02_Tab_Manager` | 1213 | 법규 공유자 지정 |
| 27 | **법규등록신청** | `Ics17_Tab_UserRequest` | 1338 | 법규정보 등록 신청 |

### ICS-08. 법규정보
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 28 | **법규조회** | `Ics01_Tab_ClassTreeUserView` | 1336 | 법규조회전용 |
| 29 | **월별 법규조회** | `Ics01_Tab_PeriodList` | 1255 | 기간별 법규정보내역 |
| 30 | **법규개정내역** | `Ics20_Tab_RevisionHistory` | 1256 | 법규정보 개정내역 |

### ICS-09. 법규통제 현황(사용X)
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 31 | **법규통제 운영현황표** | `Ics02_Tab_IcsList` | 1016 | 운영현황표 |

### ICS-10. 임직원 내부통제 준수
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 32 | **내부통제 준수점검(준감인)** | `Ics31_Tab_ComplianceConfirm` | 1311 | 준법감시인 점검 및 확인처리 |
| 33 | **내부통제 준수보고(준감인)** | `Ics31_Tab_ComplianceReport` | 1312 | 준수현황 조회 및 상신처리 |
| 34 | **내부통제 준수확인서 작성** | `Ics31_Tab_ComplianceWrite` | 1310 | 임직원별 작성 및 확정처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/ics/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Ics00_PDF7` | Ics00_PDF7 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Ics01_ClassTree` | Ics01_ClassTree 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Ics02_Manager` | Ics02_Manager 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Ics03_CompanyInfo` | Ics03_CompanyInfo 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Ics04_Share` | Ics04_Share 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Ics05_RelateManager` | Ics05_RelateManager 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Ics10_Checklist` | Ics10_Checklist 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Ics11_ChecklistCompany` | Ics11_ChecklistCompany 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Ics15_ChecklistWrite` | Ics15_ChecklistWrite 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Ics16_RelateAppr` | Ics16_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Ics17_UserRequest` | Ics17_UserRequest 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Ics19_RevisionRelateIcs` | Ics19_RevisionRelateIcs 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Ics20_RevisionHistory` | Ics20_RevisionHistory 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Ics21_ChecklistLClass` | Ics21_ChecklistLClass 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Ics22_ChecklistLClassCompany` | Ics22_ChecklistLClassCompany 비즈니스 로직 및 RPC 서비스 처리 |
| 16 | `Ics23_ChecklistMClass` | Ics23_ChecklistMClass 비즈니스 로직 및 RPC 서비스 처리 |
| 17 | `Ics24_ChecklistMClassCompany` | Ics24_ChecklistMClassCompany 비즈니스 로직 및 RPC 서비스 처리 |
| 18 | `Ics30_Compliance` | Ics30_Compliance 비즈니스 로직 및 RPC 서비스 처리 |
| 19 | `Ics31_ComplianceWrite` | Ics31_ComplianceWrite 비즈니스 로직 및 RPC 서비스 처리 |
| 20 | `Ics32_RelateAppr` | Ics32_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 21 | `Ics33_ComplianceAnswer` | Ics33_ComplianceAnswer 비즈니스 로직 및 RPC 서비스 처리 |
| 22 | `Ics35_ExtrActivity` | Ics35_ExtrActivity 비즈니스 로직 및 RPC 서비스 처리 |
| 23 | `Ics40_DcrPreconfirm` | Ics40_DcrPreconfirm 비즈니스 로직 및 RPC 서비스 처리 |
| 24 | `Ics41_DcrType` | Ics41_DcrType 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/ics/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `ics01_class_tree.xml` | `ics01_class_tree` 테이블 관련 쿼리 매핑 |
| 2 | `ics02_manager.xml` | `ics02_manager` 테이블 관련 쿼리 매핑 |
| 3 | `ics03_company_info.xml` | `ics03_company_info` 테이블 관련 쿼리 매핑 |
| 4 | `ics04_share.xml` | `ics04_share` 테이블 관련 쿼리 매핑 |
| 5 | `ics05_relate_manager.xml` | `ics05_relate_manager` 테이블 관련 쿼리 매핑 |
| 6 | `ics10_checklist.xml` | `ics10_checklist` 테이블 관련 쿼리 매핑 |
| 7 | `ics11_checklist_company.xml` | `ics11_checklist_company` 테이블 관련 쿼리 매핑 |
| 8 | `ics15_checklist_write.xml` | `ics15_checklist_write` 테이블 관련 쿼리 매핑 |
| 9 | `ics16_relate_appr.xml` | `ics16_relate_appr` 테이블 관련 쿼리 매핑 |
| 10 | `ics17_user_request.xml` | `ics17_user_request` 테이블 관련 쿼리 매핑 |
| 11 | `ics19_revision_relate_ics.xml` | `ics19_revision_relate_ics` 테이블 관련 쿼리 매핑 |
| 12 | `ics20_revision_history.xml` | `ics20_revision_history` 테이블 관련 쿼리 매핑 |
| 13 | `ics21_checklist_l_class.xml` | `ics21_checklist_l_class` 테이블 관련 쿼리 매핑 |
| 14 | `ics22_checklist_l_class_company.xml` | `ics22_checklist_l_class_company` 테이블 관련 쿼리 매핑 |
| 15 | `ics23_checklist_m_class.xml` | `ics23_checklist_m_class` 테이블 관련 쿼리 매핑 |
| 16 | `ics24_checklist_m_class_company.xml` | `ics24_checklist_m_class_company` 테이블 관련 쿼리 매핑 |
| 17 | `ics30_compliance.xml` | `ics30_compliance` 테이블 관련 쿼리 매핑 |
| 18 | `ics31_compliance_write.xml` | `ics31_compliance_write` 테이블 관련 쿼리 매핑 |
| 19 | `ics32_relate_appr.xml` | `ics32_relate_appr` 테이블 관련 쿼리 매핑 |
| 20 | `ics33_compliance_answer.xml` | `ics33_compliance_answer` 테이블 관련 쿼리 매핑 |
| 21 | `ics35_extr_activity.xml` | `ics35_extr_activity` 테이블 관련 쿼리 매핑 |
| 22 | `ics40_dcr_preconfirm.xml` | `ics40_dcr_preconfirm` 테이블 관련 쿼리 매핑 |
| 23 | `ics41_dcr_type.xml` | `ics41_dcr_type` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `ics01_class_tree` | 내부통제 분류 | 13 | `ics01_class_tree_id` |
| 2 | `ics02_manager` | 내부통제 회사별 담당자정보 | 6 | `ics02_manager_id` |
| 3 | `ics03_company_info` | 내부통제 회사별 관리 | 7 | `ics03_company_info_id` |
| 4 | `ics04_share` | 내부통제 공유 | 6 | `ics04_share_id` |
| 5 | `ics05_relate_manager` | 담당자 연결 | 4 | `ics05_relate_manager_id` |
| 6 | `ics10_checklist` | 내부통제 체크리스트 | 7 | `ics10_checklist_id` |
| 7 | `ics11_checklist_company` | 내부통제 체크리스트(고객사정보관리) | 5 | `ics11_checklist_company_id` |
| 8 | `ics15_checklist_write` | 내부통제 체크리스트 작성 | 14 | `ics15_checklist_write_id` |
| 9 | `ics16_relate_appr` | 상신 연관문서 매핑 | 7 | `ics16_relate_appr_id` |
| 10 | `ics17_user_request` | 법규등록요청 | 14 | `ics17_user_request_id` |
| 11 | `ics19_revision_relate_ics` | 개정내역 법규 연결 | 3 | `ics19_revision_relate_ics_id` |
| 12 | `ics20_revision_history` | 법규정보 개정내역 | 10 | `ics20_revision_history_id` |
| 13 | `ics21_checklist_l_class` | 내부통제 체크리스트 대분류 | 7 | `ics21_checklist_l_class_id` |
| 14 | `ics22_checklist_l_class_company` | 내부통제 체크리스트 대분류(고객사별정보) | 6 | `ics22_checklist_l_class_company_id` |
| 15 | `ics23_checklist_m_class` | 내부통제 체크리스트 중분류 | 8 | `ics23_checklist_m_class_id` |
| 16 | `ics24_checklist_m_class_company` | 내부통제 체크리스트 중분류(고객사별정보) | 6 | `ics24_checklist_m_class_company_id` |
| 17 | `ics30_compliance` | 임직원 내부통제 준수리스트 | 11 | `ics30_compliance_id` |
| 18 | `ics31_compliance_write` | 임직원 내부통제 준수서약서 | 15 | `ics31_compliance_write_id` |
| 19 | `ics32_relate_appr` | 임직원 내부통제 준수서약서 상신문서 연결 | 5 | `ics32_relate_appr_id` |
| 20 | `ics33_compliance_answer` | 임직원 내부통제 준수리스트 준수답변 | 10 | `ics33_compliance_answer_id` |
| 21 | `ics35_extr_activity` | 대외활동신청 | 12 | `ics35_extr_activity_id` |
| 22 | `ics40_dcr_preconfirm` | 준감인 사전확인대장 | 24 | `ics40_dcr_preconfirm_id` |
| 23 | `ics41_dcr_type` | 준감인 사전확인대장분류 | 6 | `ics41_dcr_type_id` |
| 24 | `ics99_class_tree_del` | 내부통제 삭제이력 | 16 | `ics99_class_tree_del_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **34개**
- **UI 컴포넌트 수**: 총 92개 (Tab/Page: 33개, Lookup/Popup/기타: 59개)
- **서버 서비스 클래스 수**: **24개**
- **MyBatis 매퍼 XML 수**: **23개**
- **DB 테이블 수**: **24개**
