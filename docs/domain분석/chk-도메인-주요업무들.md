# chk (일일점검내역 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `chk` (일일점검내역 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/chk/*`, `myApp/server/chk/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`chk##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`chk` 도메인은 **일일점검내역 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **CHK-01** | **내부통제** | 내부통제 관련 화면 및 처리 모듈 | 2개 화면 |
| **CHK-02** | **펀드회계 일일점검** | 펀드회계 일일점검 관련 화면 및 처리 모듈 | 4개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### CHK-01. 내부통제
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **일일점검내역 분류(관리자)** | `Chk01_Tab_ClassTree` | 1244 | 일일점검내역 분류관리(관리자) |
| 2 | **일일점검내역 관리(관리자)** | `Chk02_Tab_DailyListAdmin` | 1245 | 일일점검내역 체크리스트(관리자) |

### CHK-02. 펀드회계 일일점검
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **일일점검내역 관리** | `Chk02_Tab_DailyList` | 1240 | 일일점검내역 관리 |
| 4 | **일일점검내역 확인** | `Chk03_Tab_DailyListConfirm` | 1242 | 일일점검내역 확인 |
| 5 | **일일점검내역** | `Chk03_Tab_DailyListStatus` | 1243 | 일일점검내역 |
| 6 | **일일점검내역 작성** | `Chk03_Tab_DailyListWrite` | 1241 | 일일점검내역 작성 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/chk/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Chk01_ClassTree` | Chk01_ClassTree 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Chk02_DailyList` | Chk02_DailyList 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Chk03_DailyListWrite` | Chk03_DailyListWrite 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/chk/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `chk01_class_tree.xml` | `chk01_class_tree` 테이블 관련 쿼리 매핑 |
| 2 | `chk02_daily_list.xml` | `chk02_daily_list` 테이블 관련 쿼리 매핑 |
| 3 | `chk03_daily_list_write.xml` | `chk03_daily_list_write` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `chk01_class_tree` | 체크리스트분류 | 8 | `chk01_class_tree_id` |
| 2 | `chk02_daily_list` | 일일점검항목관리 | 11 | `chk02_daily_list_id` |
| 3 | `chk03_daily_list_write` | 일일점검표 작성 | 12 | `chk03_daily_list_write_id` |
| 4 | `chk50_act_notice` | 관리회계체크알림 | 10 | `chk50_act_notice_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **6개**
- **UI 컴포넌트 수**: 총 12개 (Tab/Page: 6개, Lookup/Popup/기타: 6개)
- **서버 서비스 클래스 수**: **3개**
- **MyBatis 매퍼 XML 수**: **3개**
- **DB 테이블 수**: **4개**
