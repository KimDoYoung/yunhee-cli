# att (근태관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `att` (근태관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/att/*`, `myApp/server/att/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`att##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`att` 도메인은 **근태관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **ATT-01** | **근태관리** | 근태관리 관련 화면 및 처리 모듈 | 4개 화면 |
| **ATT-02** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 1개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### ATT-01. 근태관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **근태관리(관리자)** | `Att02_Tab_CommuteAdmin` | 1485 | 근태관리(관리자) 기능 처리 |
| 2 | **근태현황(관리자)** | `Att02_Tab_CommuteStatus` | 1487 | 근태현황(관리자) 기능 처리 |
| 3 | **근태현황** | `Att02_Tab_PersonStatus` | 1492 | 근태현황 기능 처리 |
| 4 | **연장근무관리** | `Att03_Tab_OvertimeReq` | 1486 | 연장근무관리 기능 처리 |

### ATT-02. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 5 | **승인** | `Att03_Tab_OvertimeReq_20260923` | - | 승인 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/att/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Att01_WorkPolicy` | Att01_WorkPolicy 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Att02_Commute` | Att02_Commute 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Att03_OvertimeReq` | Att03_OvertimeReq 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Att04_CommuteHist` | Att04_CommuteHist 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Att05_PmWork` | Att05_PmWork 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Att13_OvertimeReqHist` | Att13_OvertimeReqHist 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/att/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `att01_work_policy.xml` | `att01_work_policy` 테이블 관련 쿼리 매핑 |
| 2 | `att02_commute.xml` | `att02_commute` 테이블 관련 쿼리 매핑 |
| 3 | `att03_overtime_req.xml` | `att03_overtime_req` 테이블 관련 쿼리 매핑 |
| 4 | `att04_commute_hist.xml` | `att04_commute_hist` 테이블 관련 쿼리 매핑 |
| 5 | `att05_pm_work.xml` | `att05_pm_work` 테이블 관련 쿼리 매핑 |
| 6 | `att13_overtime_req_hist.xml` | `att13_overtime_req_hist` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `att01_work_policy` | 근태 기준 정책 (회사별 출퇴근 기준) | 14 | `att01_work_policy_id` |
| 2 | `att02_commute` | 출퇴근 기록 | 17 | `att02_commute_id` |
| 3 | `att03_overtime_req` | 연장근무 신청 | 14 | `att03_overtime_req_id` |
| 4 | `att04_commute_hist` | 출퇴근 수정 이력 | 9 | `att04_commute_hist_id` |
| 5 | `att05_excluded_person` | 출퇴근 미사용 사원 | 9 | `att05_excluded_person_id` |
| 6 | `att05_pm_work` | 오후근무 신청 | 6 | `att05_pm_work_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **5개**
- **UI 컴포넌트 수**: 총 17개 (Tab/Page: 5개, Lookup/Popup/기타: 12개)
- **서버 서비스 클래스 수**: **6개**
- **MyBatis 매퍼 XML 수**: **6개**
- **DB 테이블 수**: **6개**
