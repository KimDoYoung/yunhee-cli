# tdm (책무구조도 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `tdm` (책무구조도 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/tdm/*`, `myApp/server/tdm/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`tdm##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`tdm` 도메인은 **책무구조도 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **TDM-01** | **기본정보** | 기본정보 관련 화면 및 처리 모듈 | 7개 화면 |
| **TDM-02** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 18개 화면 |
| **TDM-03** | **대시보드** | 대시보드 관련 화면 및 처리 모듈 | 3개 화면 |
| **TDM-04** | **부서책무매뉴얼** | 부서책무매뉴얼 관련 화면 및 처리 모듈 | 5개 화면 |
| **TDM-05** | **책무** | 책무 관련 화면 및 처리 모듈 | 5개 화면 |
| **TDM-06** | **책무관리현황** | 책무관리현황 관련 화면 및 처리 모듈 | 5개 화면 |
| **TDM-07** | **책무구조도** | 책무구조도 관련 화면 및 처리 모듈 | 4개 화면 |
| **TDM-08** | **책무이행점검** | 책무이행점검 관련 화면 및 처리 모듈 | 6개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### TDM-01. 기본정보
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **임원 등록** | `Tdm01_Tab_Hr` | 1411 | 임원 등록 기능 처리 |
| 2 | **회의체 등록** | `Tdm05_Tab_Cncl` | 1415 | 회의체 등록 기능 처리 |
| 3 | **책무담당자 등록** | `Tdm08_Tab_Manager` | 1454 | 책무담당자 등록 기능 처리 |
| 4 | **직책별 부서승인선 등록** | `Tdm09_Tab_ApprStep` | 1463 | 직책별 부서승인선 등록 기능 처리 |
| 5 | **책무 등록** | `Tdm10_Tab_Task` | 1412 | 책무 등록 기능 처리 |
| 6 | **관리의무 등록** | `Tdm13_Tab_TaskDuty` | 1413 | 관리의무 등록 기능 처리 |
| 7 | **직책별 책무 등록** | `Tdm20_Tab_Role` | 1414 | 직책별 책무 등록 기능 처리 |

### TDM-02. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 8 | **책무 세부내용** | `Tdm12_TabPage_TaskRelateDetail` | - | 책무 세부내용 기능 처리 |
| 9 | **관리의무** | `Tdm13_TabPage_TaskDuty` | - | 관리의무 기능 처리 |
| 10 | **조회기간** | `Tdm32_Tab_RoleDigm_20260310` | - | 조회기간 기능 처리 |
| 11 | **상신문서가 없습니다** | `Tdm34_TabPage_RoleAllcDetail` | - | 상신문서가 없습니다 기능 처리 |
| 12 | **임원동의서 상신** | `Tdm34_TabPage_RoleAllcDetail_20260406` | - | 임원동의서 상신 기능 처리 |
| 13 | **상신** | `Tdm36_TabPage_RoleReport` | - | 상신 기능 처리 |
| 14 | **전체선택** | `Tdm41_TabPage_ManlDutyOrg` | - | 전체선택 기능 처리 |
| 15 | **추가** | `Tdm43_Page_Relate` | - | 추가 기능 처리 |
| 16 | **관리의무별 불러오기** | `Tdm43_TabPage_ManlItemReg` | - | 관리의무별 불러오기 기능 처리 |
| 17 | **관련조문** | `Tdm45_TabPage_Relate` | - | 관련조문 기능 처리 |
| 18 | **잠금** | `Tdm50_TabPage_CheckJob` | - | 잠금 기능 처리 |
| 19 | **새로고침** | `Tdm50_Tab_Dashboard` | - | 새로고침 기능 처리 |
| 20 | **새로고침** | `Tdm50_Tab_DashboardExct` | - | 새로고침 기능 처리 |
| 21 | **새로고침** | `Tdm50_Tab_DashboardOrg` | - | 새로고침 기능 처리 |
| 22 | **기준년월** | `Tdm50_Tab_DutyReconStatusAdmin` | - | 기준년월 기능 처리 |
| 23 | **전체선택** | `Tdm51_TabPage_CheckOrg` | - | 전체선택 기능 처리 |
| 24 | **직책** | `Tdm52_TabPage_CheckManl` | - | 직책 기능 처리 |
| 25 | **승인시작** | `Tdm59_TabPage_CheckAppr` | - | 승인시작 기능 처리 |

### TDM-03. 대시보드
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 26 | **책무진행 상태** | `Tdm50_Tab_DutyProgress` | 1496 | 책무진행 상태 기능 처리 |
| 27 | **책무마감 검증** | `Tdm50_Tab_DutyRecon` | 1497 | 책무마감 검증 기능 처리 |
| 28 | **책무점검 현황** | `Tdm50_Tab_TotalDashboard` | 1495 | 책무점검 현황 기능 처리 |

### TDM-04. 부서책무매뉴얼
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 29 | **매뉴얼 작업대상 선정** | `Tdm40_Tab_ManlJob` | 1420 | 매뉴얼 작업대상 선정 기능 처리 |
| 30 | **매뉴얼 부서지정** | `Tdm41_Tab_ManlDutyOrg` | 1421 | 책무매뉴얼 작업을 위해 관리의무별 담당부서를 지정한다 |
| 31 | **매뉴얼 관리(관리자)** | `Tdm42_Tab_ManlManager` | 1424 | 책무매뉴얼 작성현황 확인 및 사용기간을 관리한다 |
| 32 | **매뉴얼 보고(부서별)** | `Tdm42_Tab_ManlOrgAppr` | 1423 | 매뉴얼 보고(부서별) 기능 처리 |
| 33 | **매뉴얼(점검항목) 작성** | `Tdm43_Tab_ManlItemReg` | 1422 | 부서별 매뉴얼 점검항목을 등록(작성)한다 |

### TDM-05. 책무
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 34 | **책무기술서 재생성** | `Tdm31_Tab_RoleDescAdmin` | 1493 | 결재가 완료된 기술서를 재생성하여 다시 첨부 |
| 35 | **책무체계도 재생성** | `Tdm32_Tab_RoleDigmAdmin` | 1498 | 완료된 문서의 책무체계도를 재생성 하는 화면 |
| 36 | **책무매뉴얼 재생성** | `Tdm42_Tab_ManlManagerAdmin` | 1502 | 책무 매뉴얼을 재생성하여 문서에 다시 연결해주는 화면입니다. |
| 37 | **책무진행 상태** | `Tdm50_Tab_DutyProgressAdmin` | 1511 | insert menu |
| 38 | **책무마감 검증** | `Tdm50_Tab_DutyReconAdmin` | 1512 | insert menu |

### TDM-06. 책무관리현황
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 39 | **조치대상조회(변화관리)** | `Tdm00_Tab_ChangeList` | 1466 | 조치대상조회(변화관리) 기능 처리 |
| 40 | **책무조회** | `Tdm35_Tab_TaskList` | 1467 | 직책 배정이 확정된 책무-세무-관리의무 조회 |
| 41 | **매뉴얼 규정/양식 연결** | `Tdm43_Tab_ManlItemList` | 1468 | 매뉴얼 규정/양식 연결 기능 처리 |
| 42 | **이행점검 연관양식 등록** | `Tdm43_Tab_RelateFormFileUpload` | 1481 | 이행점검 연관양식 등록 기능 처리 |
| 43 | **책무관리 시스템설정** | `Tdm91_Tab_CompanySetup` | 1469 | 책무관리 시스템설정 기능 처리 |

### TDM-07. 책무구조도
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 44 | **임원별 직책배정** | `Tdm30_Tab_RoleAllc` | 1417 | 임원별 직책배정 기능 처리 |
| 45 | **임원별 책무기술서** | `Tdm31_Tab_RoleDesc` | 1418 | 임원별 책무기술서 기능 처리 |
| 46 | **책무체계도** | `Tdm32_Tab_RoleDigm` | 1419 | 책무체계도 기능 처리 |
| 47 | **책무구조도 제출** | `Tdm36_Tab_RoleReport` | 1480 | 책무구조도 제출 기능 처리 |

### TDM-08. 책무이행점검
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 48 | **이행점검 작업지시 및 보고** | `Tdm50_Tab_CheckJob` | 1455 | 회사책무담당자가 부서별 책무이행점검 작업등록 및 임원별 이행점검보고서  생성, 대표상신 |
| 49 | **업무점검자 지정 및 승인요청** | `Tdm51_Tab_CheckOrg` | 1456 | 부서책무담당자가 점검항목별 점검자지정 및 임원보고 |
| 50 | **책무이행점검** | `Tdm52_Tab_CheckManl` | 1457 | 점검자가 책무이행점검 등록 |
| 51 | **미흡내역 조치** | `Tdm54_Tab_CheckInsuff` | 1459 | 미흡/개선내역 조치등록 |
| 52 | **대표이행점검 보고** | `Tdm57_Tab_CeoReport` | 1460 | 반기or분기별 대표이사 총괄관리의무 이행점검 보고서 상신 |
| 53 | **책무이행점검 승인** | `Tdm59_Tab_CheckAppr` | 1458 | **상위조직~임원**은 이행내역 승인 및 의견입력 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/tdm/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Tdm01_Hr` | Tdm01_Hr 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Tdm02_HrRecord` | Tdm02_HrRecord 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Tdm03_AddTitle` | Tdm03_AddTitle 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Tdm05_Cncl` | Tdm05_Cncl 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Tdm08_ManagerInfo` | Tdm08_ManagerInfo 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Tdm09_ApprStep` | Tdm09_ApprStep 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Tdm10_Task` | Tdm10_Task 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Tdm11_TaskRelateRule` | Tdm11_TaskRelateRule 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Tdm12_TaskRelateDetail` | Tdm12_TaskRelateDetail 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Tdm13_TaskRelateDuty` | Tdm13_TaskRelateDuty 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Tdm14_TaskType` | Tdm14_TaskType 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Tdm20_Role` | Tdm20_Role 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Tdm21_RoleRelateTask` | Tdm21_RoleRelateTask 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Tdm22_RoleRelateCncl` | Tdm22_RoleRelateCncl 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Tdm23_RoleRelateOrg` | Tdm23_RoleRelateOrg 비즈니스 로직 및 RPC 서비스 처리 |
| 16 | `Tdm30_RoleAllc` | Tdm30_RoleAllc 비즈니스 로직 및 RPC 서비스 처리 |
| 17 | `Tdm31_RoleDesc` | Tdm31_RoleDesc 비즈니스 로직 및 RPC 서비스 처리 |
| 18 | `Tdm32_RoleDigm` | Tdm32_RoleDigm 비즈니스 로직 및 RPC 서비스 처리 |
| 19 | `Tdm33_RoleDigmFile` | Tdm33_RoleDigmFile 비즈니스 로직 및 RPC 서비스 처리 |
| 20 | `Tdm34_RoleAllcDetail` | Tdm34_RoleAllcDetail 비즈니스 로직 및 RPC 서비스 처리 |
| 21 | `Tdm35_RoleAllcTask` | Tdm35_RoleAllcTask 비즈니스 로직 및 RPC 서비스 처리 |
| 22 | `Tdm36_RoleReport` | Tdm36_RoleReport 비즈니스 로직 및 RPC 서비스 처리 |
| 23 | `Tdm40_ManlJob` | Tdm40_ManlJob 비즈니스 로직 및 RPC 서비스 처리 |
| 24 | `Tdm41_ManlDuty` | Tdm41_ManlDuty 비즈니스 로직 및 RPC 서비스 처리 |
| 25 | `Tdm42_ManlOrg` | Tdm42_ManlOrg 비즈니스 로직 및 RPC 서비스 처리 |
| 26 | `Tdm43_Manl` | Tdm43_Manl 비즈니스 로직 및 RPC 서비스 처리 |
| 27 | `Tdm44_ManlDutyOrg` | Tdm44_ManlDutyOrg 비즈니스 로직 및 RPC 서비스 처리 |
| 28 | `Tdm45_ManlRelateIcs` | Tdm45_ManlRelateIcs 비즈니스 로직 및 RPC 서비스 처리 |
| 29 | `Tdm46_ManlRelateIcr` | Tdm46_ManlRelateIcr 비즈니스 로직 및 RPC 서비스 처리 |
| 30 | `Tdm47_ManlRelateDcr` | Tdm47_ManlRelateDcr 비즈니스 로직 및 RPC 서비스 처리 |
| 31 | `Tdm50_ChckJob` | Tdm50_ChckJob 비즈니스 로직 및 RPC 서비스 처리 |
| 32 | `Tdm51_ChckOrg` | Tdm51_ChckOrg 비즈니스 로직 및 RPC 서비스 처리 |
| 33 | `Tdm52_ChckManl` | Tdm52_ChckManl 비즈니스 로직 및 RPC 서비스 처리 |
| 34 | `Tdm53_ChckExct` | Tdm53_ChckExct 비즈니스 로직 및 RPC 서비스 처리 |
| 35 | `Tdm54_ChckInsuff` | Tdm54_ChckInsuff 비즈니스 로직 및 RPC 서비스 처리 |
| 36 | `Tdm55_ChckRecord` | Tdm55_ChckRecord 비즈니스 로직 및 RPC 서비스 처리 |
| 37 | `Tdm56_ChckRelateAppr` | Tdm56_ChckRelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 38 | `Tdm58_ChckApprStep` | Tdm58_ChckApprStep 비즈니스 로직 및 RPC 서비스 처리 |
| 39 | `Tdm59_ChckApprCmnt` | Tdm59_ChckApprCmnt 비즈니스 로직 및 RPC 서비스 처리 |
| 40 | `Tdm60_ChckManlAppr` | Tdm60_ChckManlAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 41 | `Tdm61_ChckInsuffAppr` | Tdm61_ChckInsuffAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 42 | `Tdm63_ChckInsuffRecord` | Tdm63_ChckInsuffRecord 비즈니스 로직 및 RPC 서비스 처리 |
| 43 | `Tdm64_ChckEvidExtr` | Tdm64_ChckEvidExtr 비즈니스 로직 및 RPC 서비스 처리 |
| 44 | `Tdm91_CompanySetup` | Tdm91_CompanySetup 비즈니스 로직 및 RPC 서비스 처리 |
| 45 | `Tdm95_ChangeHistory` | Tdm95_ChangeHistory 비즈니스 로직 및 RPC 서비스 처리 |
| 46 | `Tdm96_ChangeDetail` | Tdm96_ChangeDetail 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/tdm/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `tdm01_hr.xml` | `tdm01_hr` 테이블 관련 쿼리 매핑 |
| 2 | `tdm02_hr_record.xml` | `tdm02_hr_record` 테이블 관련 쿼리 매핑 |
| 3 | `tdm03_add_title.xml` | `tdm03_add_title` 테이블 관련 쿼리 매핑 |
| 4 | `tdm05_cncl.xml` | `tdm05_cncl` 테이블 관련 쿼리 매핑 |
| 5 | `tdm08_manager_info.xml` | `tdm08_manager_info` 테이블 관련 쿼리 매핑 |
| 6 | `tdm09_appr_step.xml` | `tdm09_appr_step` 테이블 관련 쿼리 매핑 |
| 7 | `tdm10_task.xml` | `tdm10_task` 테이블 관련 쿼리 매핑 |
| 8 | `tdm11_task_relate_rule.xml` | `tdm11_task_relate_rule` 테이블 관련 쿼리 매핑 |
| 9 | `tdm12_task_relate_detail.xml` | `tdm12_task_relate_detail` 테이블 관련 쿼리 매핑 |
| 10 | `tdm13_task_relate_duty.xml` | `tdm13_task_relate_duty` 테이블 관련 쿼리 매핑 |
| 11 | `tdm14_task_type.xml` | `tdm14_task_type` 테이블 관련 쿼리 매핑 |
| 12 | `tdm20_role.xml` | `tdm20_role` 테이블 관련 쿼리 매핑 |
| 13 | `tdm21_role_relate_task.xml` | `tdm21_role_relate_task` 테이블 관련 쿼리 매핑 |
| 14 | `tdm22_role_relate_cncl.xml` | `tdm22_role_relate_cncl` 테이블 관련 쿼리 매핑 |
| 15 | `tdm23_role_relate_org.xml` | `tdm23_role_relate_org` 테이블 관련 쿼리 매핑 |
| 16 | `tdm30_role_allc.xml` | `tdm30_role_allc` 테이블 관련 쿼리 매핑 |
| 17 | `tdm31_role_desc.xml` | `tdm31_role_desc` 테이블 관련 쿼리 매핑 |
| 18 | `tdm32_role_digm.xml` | `tdm32_role_digm` 테이블 관련 쿼리 매핑 |
| 19 | `tdm33_role_digm_file.xml` | `tdm33_role_digm_file` 테이블 관련 쿼리 매핑 |
| 20 | `tdm34_role_allc_detail.xml` | `tdm34_role_allc_detail` 테이블 관련 쿼리 매핑 |
| 21 | `tdm35_role_allc_task.xml` | `tdm35_role_allc_task` 테이블 관련 쿼리 매핑 |
| 22 | `tdm36_role_report.xml` | `tdm36_role_report` 테이블 관련 쿼리 매핑 |
| 23 | `tdm40_manl_job.xml` | `tdm40_manl_job` 테이블 관련 쿼리 매핑 |
| 24 | `tdm41_manl_duty.xml` | `tdm41_manl_duty` 테이블 관련 쿼리 매핑 |
| 25 | `tdm42_manl_org.xml` | `tdm42_manl_org` 테이블 관련 쿼리 매핑 |
| 26 | `tdm43_manl.xml` | `tdm43_manl` 테이블 관련 쿼리 매핑 |
| 27 | `tdm44_manl_duty_org.xml` | `tdm44_manl_duty_org` 테이블 관련 쿼리 매핑 |
| 28 | `tdm45_manl_relate_ics.xml` | `tdm45_manl_relate_ics` 테이블 관련 쿼리 매핑 |
| 29 | `tdm46_manl_relate_icr.xml` | `tdm46_manl_relate_icr` 테이블 관련 쿼리 매핑 |
| 30 | `tdm47_manl_relate_dcr.xml` | `tdm47_manl_relate_dcr` 테이블 관련 쿼리 매핑 |
| 31 | `tdm50_chck_job.xml` | `tdm50_chck_job` 테이블 관련 쿼리 매핑 |
| 32 | `tdm51_chck_org.xml` | `tdm51_chck_org` 테이블 관련 쿼리 매핑 |
| 33 | `tdm52_chck_manl.xml` | `tdm52_chck_manl` 테이블 관련 쿼리 매핑 |
| 34 | `tdm53_chck_exct.xml` | `tdm53_chck_exct` 테이블 관련 쿼리 매핑 |
| 35 | `tdm54_chck_insuff.xml` | `tdm54_chck_insuff` 테이블 관련 쿼리 매핑 |
| 36 | `tdm55_chck_record.xml` | `tdm55_chck_record` 테이블 관련 쿼리 매핑 |
| 37 | `tdm56_chck_relate_appr.xml` | `tdm56_chck_relate_appr` 테이블 관련 쿼리 매핑 |
| 38 | `tdm58_chck_appr_step.xml` | `tdm58_chck_appr_step` 테이블 관련 쿼리 매핑 |
| 39 | `tdm59_chck_appr_cmnt.xml` | `tdm59_chck_appr_cmnt` 테이블 관련 쿼리 매핑 |
| 40 | `tdm60_chck_manl_appr.xml` | `tdm60_chck_manl_appr` 테이블 관련 쿼리 매핑 |
| 41 | `tdm61_chck_insuff_appr.xml` | `tdm61_chck_insuff_appr` 테이블 관련 쿼리 매핑 |
| 42 | `tdm63_chck_insuff_record.xml` | `tdm63_chck_insuff_record` 테이블 관련 쿼리 매핑 |
| 43 | `tdm64_chck_evid_extr.xml` | `tdm64_chck_evid_extr` 테이블 관련 쿼리 매핑 |
| 44 | `tdm91_company_setup.xml` | `tdm91_company_setup` 테이블 관련 쿼리 매핑 |
| 45 | `tdm95_change_history.xml` | `tdm95_change_history` 테이블 관련 쿼리 매핑 |
| 46 | `tdm96_change_detail.xml` | `tdm96_change_detail` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `tdm01_hr` | 인사(임원)정보 | 15 | `tdm01_hr_id` |
| 2 | `tdm02_hr_record` | 인사변동사항 반영정보 | 12 | `tdm02_hr_record_id` |
| 3 | `tdm03_add_title` | 직무겸직정보 | 9 | `tdm03_add_title_id` |
| 4 | `tdm05_cncl` | 위원회(회의체) 정보 | 10 | `tdm05_cncl_id` |
| 5 | `tdm06_cncl_record` | 이사회 의결기록 | 7 | `tdm06_cncl_record_id` |
| 6 | `tdm07_rule` | 내규관리 | 7 | `tdm07_rule_id` |
| 7 | `tdm08_manager_info` | 책무관리자 | 9 | `tdm08_manager_info_id` |
| 8 | `tdm09_appr_step` | 책무승인단계 | 10 | `tdm09_appr_step_id` |
| 9 | `tdm09_appr_step_20260512` | - | 10 | `-` |
| 10 | `tdm10_task` | 책무정보 | 11 | `tdm10_task_id` |
| 11 | `tdm11_task_relate_rule` | 책무연결정보-규정(법규/내규) | 8 | `tdm11_task_relate_rule_id` |
| 12 | `tdm12_task_relate_detail` | 책무연결정보-세부내용 | 7 | `tdm12_task_relate_detail_id` |
| 13 | `tdm13_task_relate_duty` | 책무연결정보-관리의무 | 8 | `tdm13_task_relate_duty_id` |
| 14 | `tdm14_task_type` | 책무유형정의 | 8 | `tdm14_task_type_id` |
| 15 | `tdm20_role` | 직책정보 | 11 | `tdm20_role_id` |
| 16 | `tdm21_role_relate_task` | 직책연결정보-책무 | 3 | `tdm21_role_relate_task_id` |
| 17 | `tdm22_role_relate_cncl` | 직책연결정보-위원회 | 6 | `tdm22_role_relate_cncl_id` |
| 18 | `tdm23_role_relate_org` | 직책연결정보-담당부서 | 3 | `tdm23_role_relate_org_id` |
| 19 | `tdm30_role_allc` | 직책(책무)배분 | 9 | `tdm30_role_allc_id` |
| 20 | `tdm31_role_desc` | 임원별 직책(책무)기술서 | 12 | `tdm31_role_desc_id` |
| 21 | `tdm32_role_digm` | 책무체계도 | 9 | `tdm32_role_digm_id` |
| 22 | `tdm33_role_digm_file` | 책무체계도_파일정보 | 3 | `tdm33_role_digm_file_id` |
| 23 | `tdm34_role_allc_detail` | 직책(책무)배분-상세정보 | 8 | `tdm34_role_allc_detail_id` |
| 24 | `tdm35_role_allc_task` | 직책(책무)배분-확정책무 | 12 | `tdm35_role_allc_task_id` |
| 25 | `tdm36_role_report` | 책무구조도 제출 | 18 | `tdm36_role_report_id` |
| 26 | `tdm40_manl_job` | 책무매뉴얼 작업 | 13 | `tdm40_manl_job_id` |
| 27 | `tdm41_manl_duty` | 책무매뉴얼 작업_관리의무 | 9 | `tdm41_manl_duty_id` |
| 28 | `tdm42_manl_org` | 부서 책무매뉴얼 | 12 | `tdm42_manl_org_id` |
| 29 | `tdm43_manl` | 책무매뉴얼 점검항목 | 31 | `tdm43_manl_id` |
| 30 | `tdm44_manl_duty_org` | 책무매뉴얼 작업_부서지정 | 8 | `tdm44_manl_duty_org_id` |
| 31 | `tdm45_manl_relate_ics` | 책무매뉴얼 점검항목 연결법규 | 3 | `tdm45_manl_relate_ics_id` |
| 32 | `tdm46_manl_relate_icr` | 책무매뉴얼 점검항목 연결내규 | 3 | `tdm46_manl_relate_icr_id` |
| 33 | `tdm47_manl_relate_dcr` | 책무매뉴얼 점검항목 연결문서분류 | 3 | `tdm47_manl_relate_dcr_id` |
| 34 | `tdm50_chck_job` | 이행점검 작업 | 9 | `tdm50_chck_job_id` |
| 35 | `tdm51_chck_org` | 이행점검_부서점검현황 | 10 | `tdm51_chck_org_id` |
| 36 | `tdm52_chck_manl` | 이행점검 | 11 | `tdm52_chck_manl_id` |
| 37 | `tdm53_chck_exct` | 이행점검_임원승인현황 | 10 | `tdm53_chck_exct_id` |
| 38 | `tdm54_chck_insuff` | 미흡/개선 내역 | 17 | `tdm54_chck_insuff_id` |
| 39 | `tdm55_chck_record` | 이행점검 기록 | 10 | `tdm55_chck_record_id` |
| 40 | `tdm56_chck_relate_appr` | 이행점검 연결 상신문서(임원책무 이행점검 보고) | 5 | `tdm56_chck_relate_appr_id` |
| 41 | `tdm57_chck_ceo_report` | 대표이사 총괄관리의무 이행점검 보고 | 8 | `tdm57_chck_ceo_report_id` |
| 42 | `tdm58_chck_appr_step` | 이행점검_부서승인단계설정 | 6 | `tdm58_chck_appr_step_id` |
| 43 | `tdm59_chck_appr_cmnt` | 이행점검_종합의견 | 12 | `tdm59_chck_appr_cmnt_id` |
| 44 | `tdm60_chck_manl_appr` | 이행점검_승인 | 8 | `tdm60_chck_manl_appr_id` |
| 45 | `tdm61_chck_insuff_appr` | 미흡/개선 내역 승인 | 10 | `tdm61_chck_insuff_appr_id` |
| 46 | `tdm62_chck_cmnt_relate_org` | 이행점검_종합의견 연결 부서점검현황 | 3 | `tdm62_chck_cmnt_relate_org_id` |
| 47 | `tdm63_chck_insuff_record` | 미흡/개선 조치기록 | 8 | `tdm63_chck_insuff_record_id` |
| 48 | `tdm64_chck_evid_extr` | 이행점검_증빙자료(외부시스템 문서정보) | 10 | `tdm64_chck_evid_extr_id` |
| 49 | `tdm91_company_setup` | 책무사용 기본설정 | 10 | `tdm91_company_setup_id` |
| 50 | `tdm95_change_history` | 책무데이터 변경이력 | 9 | `tdm95_change_history_id` |
| 51 | `tdm96_change_detail` | 책무데이터 변경이력 상세 | 6 | `tdm96_change_detail_id` |
| 52 | `tdm98_load` | - | 17 | `tdm98_load_id` |
| 53 | `tdm98_task_check` | - | 11 | `tdm98_company_id, tdm98_no` |
| 54 | `tdm99_conv` | - | 11 | `tdm99_fr_company_id, tdm99_to_company_id, tdm99_fr_key_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **53개**
- **UI 컴포넌트 수**: 총 116개 (Tab/Page: 52개, Lookup/Popup/기타: 64개)
- **서버 서비스 클래스 수**: **46개**
- **MyBatis 매퍼 XML 수**: **46개**
- **DB 테이블 수**: **54개**
