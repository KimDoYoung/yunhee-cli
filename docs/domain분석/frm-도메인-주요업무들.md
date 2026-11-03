# frm (메인 프레임 / 포털 위젯) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `frm` (메인 프레임 / 포털 위젯) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/frm/*`, `myApp/server/frm/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`frm##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`frm` 도메인은 **메인 프레임 / 포털 위젯** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **FRM-01** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 10개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### FRM-01. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **미결함** | `Monitoring_Page_Appr` | - | 미결함 기능 처리 |
| 2 | **바로가기** | `Monitoring_Page_CrmProject` | - | 바로가기 기능 처리 |
| 3 | **새로고침** | `Monitoring_Page_DayList` | - | 새로고침 기능 처리 |
| 4 | **Monitoring_Page_DetailSchedule** | `Monitoring_Page_DetailSchedule` | - | Monitoring_Page_DetailSchedule 기능 처리 |
| 5 | **사원/부서명 검색** | `Monitoring_Page_Emp` | - | 사원/부서명 검색 기능 처리 |
| 6 | **법규보고공시 및 내규정보** | `Monitoring_Page_IcsNotice` | - | 법규보고공시 및 내규정보 기능 처리 |
| 7 | **보기** | `Monitoring_Page_Notice` | - | 보기 기능 처리 |
| 8 | **바로가기** | `Monitoring_Page_Outstanding` | - | 바로가기 기능 처리 |
| 9 | **나의일정** | `Monitoring_Page_Relate` | - | 나의일정 기능 처리 |
| 10 | **회사** | `Monitoring_Page_Schedule` | - | 회사 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/frm/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Calendar` | Calendar 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Frm01_List` | Frm01_List 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `ScheduleCalendar` | ScheduleCalendar 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/frm/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `frm01_list.xml` | `frm01_list` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
- 전용 도메인 테이블 없음 (공통 또는 타 도메인 참조)

---

## 4. 요약 통계

- **총 세부 업무 화면**: **10개**
- **UI 컴포넌트 수**: 총 16개 (Tab/Page: 10개, Lookup/Popup/기타: 6개)
- **서버 서비스 클래스 수**: **3개**
- **MyBatis 매퍼 XML 수**: **1개**
- **DB 테이블 수**: **0개**
