# sms (SMS / 알림 발송관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `sms` (SMS / 알림 발송관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/sms/*`, `myApp/server/sms/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`sms##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`sms` 도메인은 **SMS / 알림 발송관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **SMS-01** | **고객관리** | 고객관리 관련 화면 및 처리 모듈 | 2개 화면 |
| **SMS-02** | **기타** | 기타 관련 화면 및 처리 모듈 | 1개 화면 |
| **SMS-03** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 4개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### SMS-01. 고객관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **고객별 문자사용량** | `Sms02_Tab_TotalCount` | 1305 | 고객별 문자사용량 |
| 2 | **고객별 문자발송** | `Sms03_Tab_SendAdmin` | 1367 | 고객별 문자발송 |

### SMS-02. 기타
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **사원별 문자발송** | `Sms03_Tab_GroupSend` | 1186 | 사원별 문자발송 |

### SMS-03. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 4 | **사용연도** | `Sms02_TabPage_Detail` | - | 사용연도 기능 처리 |
| 5 | **Sms02_Tab_History** | `Sms02_Tab_History` | - | Sms02_Tab_History 기능 처리 |
| 6 | **발송** | `Sms03_Page_UserList` | - | 발송 기능 처리 |
| 7 | **기타고객사 추가** | `Sms03_Page_UserListAdmin` | - | 기타고객사 추가 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/sms/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Sms02_History` | Sms02_History 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Sms03_GroupSend` | Sms03_GroupSend 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Sms04_GroupSendHistory` | Sms04_GroupSendHistory 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Sms10_AlarmHistory` | Sms10_AlarmHistory 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/sms/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `sms02_history.xml` | `sms02_history` 테이블 관련 쿼리 매핑 |
| 2 | `sms03_group_send.xml` | `sms03_group_send` 테이블 관련 쿼리 매핑 |
| 3 | `sms04_group_send_history.xml` | `sms04_group_send_history` 테이블 관련 쿼리 매핑 |
| 4 | `sms10_alarm_history.xml` | `sms10_alarm_history` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `sms02_history` | SMS발신기록 | 5 | `sms02_history_id` |
| 2 | `sms03_group_send` | 단체문자 | 7 | `sms03_group_send_id` |
| 3 | `sms04_group_send_history` | 단체문자 SMS발신기록 | 8 | `sms04_group_send_history_id` |
| 4 | `sms10_alarm_history` | 알림기록 | 6 | `sms10_alarm_history_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **7개**
- **UI 컴포넌트 수**: 총 12개 (Tab/Page: 7개, Lookup/Popup/기타: 5개)
- **서버 서비스 클래스 수**: **4개**
- **MyBatis 매퍼 XML 수**: **4개**
- **DB 테이블 수**: **4개**
