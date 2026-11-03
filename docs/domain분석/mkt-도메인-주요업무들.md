# mkt (마케팅 (업무활동 관리)) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `mkt` (마케팅 (업무활동 관리)) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/mkt/*`, `myApp/server/mkt/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`mkt##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`mkt` 도메인은 **마케팅 (업무활동 관리)** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **MKT-01** | **업무활동** | 업무활동 관련 화면 및 처리 모듈 | 2개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### MKT-01. 업무활동
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **업무활동등록** | `Mkt01_Tab_TargetCompany` | 1405 | 업무활동등록 기능 처리 |
| 2 | **업무활동등록(관리자)** | `Mkt03_Tab_HistoryManager` | 1408 | 전체 업무활동내역 조회, 공유지정 기능 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/mkt/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Mkt01_TargetCompany` | Mkt01_TargetCompany 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Mkt02_Manager` | Mkt02_Manager 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Mkt03_History` | Mkt03_History 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Mkt04_RelateFund` | Mkt04_RelateFund 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Mkt05_Share` | Mkt05_Share 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Mkt06_Favorite` | Mkt06_Favorite 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/mkt/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `mkt01_target_company.xml` | `mkt01_target_company` 테이블 관련 쿼리 매핑 |
| 2 | `mkt02_manager.xml` | `mkt02_manager` 테이블 관련 쿼리 매핑 |
| 3 | `mkt03_history.xml` | `mkt03_history` 테이블 관련 쿼리 매핑 |
| 4 | `mkt04_relate_fund.xml` | `mkt04_relate_fund` 테이블 관련 쿼리 매핑 |
| 5 | `mkt05_share.xml` | `mkt05_share` 테이블 관련 쿼리 매핑 |
| 6 | `mkt06_favorite.xml` | `mkt06_favorite` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `mkt01_target_company` | 업무활동처 | 8 | `mkt01_target_company_id` |
| 2 | `mkt02_manager` | 업무활동처 담당자 | 10 | `mkt02_manager_id` |
| 3 | `mkt03_history` | 업무활동내역 | 10 | `mkt03_history_id` |
| 4 | `mkt04_relate_fund` | 업무활동내역 연결펀드 | 4 | `mkt04_relate_fund_id` |
| 5 | `mkt05_share` | 업무활동내역 공유지정 | 6 | `mkt05_share_id` |
| 6 | `mkt06_favorite` | 업무활동처 즐겨찾기 | 4 | `mkt06_favorite_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **2개**
- **UI 컴포넌트 수**: 총 14개 (Tab/Page: 2개, Lookup/Popup/기타: 12개)
- **서버 서비스 클래스 수**: **6개**
- **MyBatis 매퍼 XML 수**: **6개**
- **DB 테이블 수**: **6개**
