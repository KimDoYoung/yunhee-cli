# sch (업무일정 / 법규점검·공모주 일정) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `sch` (업무일정 / 법규점검·공모주 일정) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/sch/*`, `myApp/server/sch/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`sch##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`sch` 도메인은 **업무일정 / 법규점검·공모주 일정** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **SCH-01** | **(X)02. 체크리스트** | (X)02. 체크리스트 관련 화면 및 처리 모듈 | 1개 화면 |
| **SCH-02** | **고유자산 거래처리** | 고유자산 거래처리 관련 화면 및 처리 모듈 | 1개 화면 |
| **SCH-03** | **공모주청약** | 공모주청약 관련 화면 및 처리 모듈 | 1개 화면 |
| **SCH-04** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 11개 화면 |
| **SCH-05** | **법규관리** | 법규관리 관련 화면 및 처리 모듈 | 2개 화면 |
| **SCH-06** | **법규정보** | 법규정보 관련 화면 및 처리 모듈 | 1개 화면 |
| **SCH-07** | **법규통제 현황(사용X)** | 법규통제 현황(사용X) 관련 화면 및 처리 모듈 | 1개 화면 |
| **SCH-08** | **업무일정** | 업무일정 관련 화면 및 처리 모듈 | 5개 화면 |
| **SCH-09** | **업무일정 체크** | 업무일정 체크 관련 화면 및 처리 모듈 | 2개 화면 |
| **SCH-10** | **자산&경영** | 자산&경영 관련 화면 및 처리 모듈 | 1개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### SCH-01. (X)02. 체크리스트
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **(X)체크리스트 생성** | `Sch20_Tab_AddChecklist` | 1441 | 체크리스트 생성 |

### SCH-02. 고유자산 거래처리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 2 | **공모주일정** | `Sch10_Tab_Ipo2` | 1296 | 공모주 일정조회 |

### SCH-03. 공모주청약
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **공모주 일정조회** | `Sch10_Tab_Ipo` | 1223 | 공모주 일정조회 |

### SCH-04. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 4 | **부서추가** | `Sch02_Page_Share` | - | 부서추가 기능 처리 |
| 5 | **03** | `Sch03_TabPage_Cycle01` | - | 03 기능 처리 |
| 6 | **04** | `Sch03_TabPage_Cycle02` | - | 04 기능 처리 |
| 7 | **05** | `Sch03_TabPage_Cycle03` | - | 05 기능 처리 |
| 8 | **07** | `Sch03_TabPage_Cycle04` | - | 07 기능 처리 |
| 9 | **08** | `Sch03_TabPage_Cycle05` | - | 08 기능 처리 |
| 10 | **09** | `Sch03_TabPage_Cycle06` | - | 09 기능 처리 |
| 11 | **10** | `Sch03_TabPage_Short99` | - | 10 기능 처리 |
| 12 | **법규명** | `Sch05_Page_RelateIcs` | - | 법규명 기능 처리 |
| 13 | **작성자그룹 관리** | `Sch21_Page_AddChecklistContent` | - | 작성자그룹 관리 기능 처리 |
| 14 | **구분** | `Sch22_Page_AddWriteGroup` | - | 구분 기능 처리 |

### SCH-05. 법규관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 15 | **법규 담당자 변경(일회성)** | `Sch04_Tab_BizReClass` | 1015 | 내부통제 업무담당자 변경 |
| 16 | **법규보고 점검(관리자)** | `Sch04_Tab_IcsListManager` | 1340 | 법규보고 발생내역(관리자) |

### SCH-06. 법규정보
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 17 | **법규보고 점검** | `Sch04_Tab_IcsList` | 1337 | 법규보고 발생내역 |

### SCH-07. 법규통제 현황(사용X)
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 18 | **법규통제 상세내역** | `Sch04_Tab_CheckList` | 1017 | 내부통제 체크리스트 |

### SCH-08. 업무일정
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 19 | **업무일정 등록** | `Sch01_Tab_Info` | 1042 | 스케줄 관리 |
| 20 | **기간별 업무일정 조회** | `Sch01_Tab_List` | 1226 | 기간별 업무일정 조회 기능 처리 |
| 21 | **부서별 업무일정 조회** | `Sch01_Tab_ListOrg` | 1357 | 부서별 스케줄 조회 (기간조회) |
| 22 | **(X)기간별 스케줄 조회** | `Sch04_Tab_List` | 1440 | 나의 기간별 스케줄 조회 |
| 23 | **업무일정 처리** | `Sch04_Tab_ToDoList` | 1043 | 특정일의 스케줄 조회 및 처리여부 저장 |

### SCH-09. 업무일정 체크
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 24 | **데일리 체크리스트(상신)** | `Sch04_Tab_DailyCheckList` | 1308 | 나의 스케줄 + 공모주(공유지정자) |
| 25 | **업무일정 체크내역** | `Sch04_Tab_DailyCheckListStatus` | 1356 | 기간별 나의 체크리스트 현황 |

### SCH-10. 자산&경영
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 26 | **공모주 일정등록** | `Sch10_Tab_IpoAdmin` | 1293 | 공모주 일정등록 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/sch/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Sch01_Info` | Sch01_Info 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Sch02_Share` | Sch02_Share 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Sch03_Deadline` | Sch03_Deadline 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Sch04_List` | Sch04_List 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Sch05_RelateIcs` | Sch05_RelateIcs 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Sch06_Alarm` | Sch06_Alarm 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Sch08_Class` | Sch08_Class 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Sch10_Ipo` | Sch10_Ipo 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Sch11_IpoCompany` | Sch11_IpoCompany 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Sch12_IpoCorp` | Sch12_IpoCorp 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Sch14_IpoMismatch` | Sch14_IpoMismatch 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Sch15_IpoItemMatching` | Sch15_IpoItemMatching 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Sch20_Checklist` | Sch20_Checklist 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Sch21_ChecklistContent` | Sch21_ChecklistContent 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Sch22_WriteGroup` | Sch22_WriteGroup 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/sch/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `sch01_info.xml` | `sch01_info` 테이블 관련 쿼리 매핑 |
| 2 | `sch02_share.xml` | `sch02_share` 테이블 관련 쿼리 매핑 |
| 3 | `sch03_deadline.xml` | `sch03_deadline` 테이블 관련 쿼리 매핑 |
| 4 | `sch04_list.xml` | `sch04_list` 테이블 관련 쿼리 매핑 |
| 5 | `sch05_relate_ics.xml` | `sch05_relate_ics` 테이블 관련 쿼리 매핑 |
| 6 | `sch06_alarm.xml` | `sch06_alarm` 테이블 관련 쿼리 매핑 |
| 7 | `sch07_alarm_record.xml` | `sch07_alarm_record` 테이블 관련 쿼리 매핑 |
| 8 | `sch08_class.xml` | `sch08_class` 테이블 관련 쿼리 매핑 |
| 9 | `sch10_ipo.xml` | `sch10_ipo` 테이블 관련 쿼리 매핑 |
| 10 | `sch11_ipo_company.xml` | `sch11_ipo_company` 테이블 관련 쿼리 매핑 |
| 11 | `sch12_ipo_corp.xml` | `sch12_ipo_corp` 테이블 관련 쿼리 매핑 |
| 12 | `sch13_ipo_crawling.xml` | `sch13_ipo_crawling` 테이블 관련 쿼리 매핑 |
| 13 | `sch14_ipo_mismatch.xml` | `sch14_ipo_mismatch` 테이블 관련 쿼리 매핑 |
| 14 | `sch15_ipo_item_matching.xml` | `sch15_ipo_item_matching` 테이블 관련 쿼리 매핑 |
| 15 | `sch20_checklist.xml` | `sch20_checklist` 테이블 관련 쿼리 매핑 |
| 16 | `sch21_checklist_content.xml` | `sch21_checklist_content` 테이블 관련 쿼리 매핑 |
| 17 | `sch22_write_group.xml` | `sch22_write_group` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `sch01_info` | 스케줄 정보 | 12 | `sch01_info_id` |
| 2 | `sch02_share` | 스케줄 공유 | 8 | `sch02_share_id` |
| 3 | `sch03_deadline` | 스케줄 기한 | 23 | `sch03_deadline_id` |
| 4 | `sch03_deadline_100_old` | - | 14 | `-` |
| 5 | `sch03_deadline_20211230` | - | 14 | `-` |
| 6 | `sch03_deadline_new` | 스케줄 기한 | 21 | `sch03_deadline_id` |
| 7 | `sch04_list` | 스케줄 확인 | 19 | `sch04_list_id` |
| 8 | `sch05_relate_ics` | 연관내부통제 | 4 | `sch05_relate_ics_id` |
| 9 | `sch06_alarm` | 알람설정 | 13 | `sch06_alarm_id` |
| 10 | `sch07_alarm_record` | 알람이력 | 11 | `sch07_alarm_record_id` |
| 11 | `sch08_class` | 스케줄분류(사용자별) | 6 | `sch08_class_id` |
| 12 | `sch09_deadline_day` | 스케줄 일자 | 3 | `sch09_deadline_day_id` |
| 13 | `sch10_ipo` | 공모주 일정 | 17 | `sch10_ipo_id` |
| 14 | `sch11_ipo_company` | 고객사별 공모주일정 | 11 | `sch11_ipo_company_id` |
| 15 | `sch12_ipo_corp` | 공모주청약 주간사 정보 | 5 | `sch12_ipo_corp_id` |
| 16 | `sch13_ipo_crawling` | 공모주 일정 크롤링데이터 | 37 | `sch13_ipo_crawling_id` |
| 17 | `sch14_ipo_mismatch` | 공모주일정 미일치내역 | 9 | `sch14_ipo_mismatch_id` |
| 18 | `sch15_ipo_item_matching` | IPO 종목코드 매칭 | 4 | `sch15_ipo_item_matching_id` |
| 19 | `sch20_checklist` | 체크리스트 | 7 | `sch20_checklist_id` |
| 20 | `sch21_checklist_content` | 체크리스트 내용 | 7 | `sch21_checklist_content_id` |
| 21 | `sch22_write_group` | 체크리스트 작성자그룹 | 3 | `sch22_write_group_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **26개**
- **UI 컴포넌트 수**: 총 59개 (Tab/Page: 26개, Lookup/Popup/기타: 33개)
- **서버 서비스 클래스 수**: **15개**
- **MyBatis 매퍼 XML 수**: **17개**
- **DB 테이블 수**: **21개**
