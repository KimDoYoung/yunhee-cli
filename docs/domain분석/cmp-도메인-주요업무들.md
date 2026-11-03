# cmp (회사별 공용 관리 / 광고심사) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `cmp` (회사별 공용 관리 / 광고심사) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/cmp/*`, `myApp/server/cmp/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`cmp##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`cmp` 도메인은 **회사별 공용 관리 / 광고심사** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **CMP-01** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 2개 화면 |
| **CMP-02** | **메일관리** | 메일관리 관련 화면 및 처리 모듈 | 1개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### CMP-01. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **검증** | `Cmp10_Edit_Tab_MailBook` | - | 검증 기능 처리 |
| 2 | **사원정보** | `Cmp10_Tab_MailBookList` | - | 사원정보 기능 처리 |

### CMP-02. 메일관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **공용메일 관리** | `Cmp10_Tab_MailBook` | 1212 | 공용메일 관리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/cmp/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Cmp10_MailBook` | Cmp10_MailBook 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Cmp11_MailRole` | Cmp11_MailRole 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/cmp/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `cmp10_mail_book.xml` | `cmp10_mail_book` 테이블 관련 쿼리 매핑 |
| 2 | `cmp11_mail_role.xml` | `cmp11_mail_role` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `cmp01_advertise` | 광고심사 | 8 | `cmp01_advertise_id` |
| 2 | `cmp02_inner_item` | - | 10 | `cmp02_inner_item_id` |
| 3 | `cmp03_item_check` | - | 5 | `cmp03_item_check_id` |
| 4 | `cmp04_person_check` | - | 9 | `cmp04_person_check_id` |
| 5 | `cmp10_mail_book` | 공용메일(회사별) | 5 | `cmp10_mail_book_id` |
| 6 | `cmp11_account` | - | 12 | `cmp11_account_id` |
| 7 | `cmp11_mail_role` | 공용메일 권한 | 4 | `cmp11_mail_role_id` |
| 8 | `cmp12_account_master` | - | 9 | `cmp12_account_master_id` |
| 9 | `cmp13_account_trans` | - | 11 | `cmp13_account_trans_id` |
| 10 | `cmp99_jongmok` | - | 6 | `cmp99_jm_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **3개**
- **UI 컴포넌트 수**: 총 5개 (Tab/Page: 3개, Lookup/Popup/기타: 2개)
- **서버 서비스 클래스 수**: **2개**
- **MyBatis 매퍼 XML 수**: **2개**
- **DB 테이블 수**: **10개**
