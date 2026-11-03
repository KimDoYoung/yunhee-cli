# com (공통 팝업 / 양식·첨부 연결) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `com` (공통 팝업 / 양식·첨부 연결) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/com/*`, `myApp/server/com/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`com##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`com` 도메인은 **공통 팝업 / 양식·첨부 연결** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|

---

## 2. 세부 주요 업무 리스트 (전수 나열)

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/com/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Com01_RelateAppr` | Com01_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Com10_FormMapping` | Com10_FormMapping 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Com11_FormMappingMulti` | Com11_FormMappingMulti 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Com50_Item` | Com50_Item 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/com/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `com01_relate_appr.xml` | `com01_relate_appr` 테이블 관련 쿼리 매핑 |
| 2 | `com10_form_mapping.xml` | `com10_form_mapping` 테이블 관련 쿼리 매핑 |
| 3 | `com11_form_mapping_multi.xml` | `com11_form_mapping_multi` 테이블 관련 쿼리 매핑 |
| 4 | `com50_item.xml` | `com50_item` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `com01_relate_appr` | 상신문서 연결(공통사용) | 4 | `com01_relate_appr_id` |
| 2 | `com10_form_mapping` | 문서양식관리(데이터맵핑문서) | 6 | `com10_form_mapping_id` |
| 3 | `com11_form_mapping_multi` | 상세코드별 문서분류연결코드 및 데이터맵핑양식관리 | 7 | `com11_form_mapping_multi_id` |
| 4 | `com50_item` | 종목정보(공통사용) | 5 | `com50_item_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **0개**
- **UI 컴포넌트 수**: 총 7개 (Tab/Page: 0개, Lookup/Popup/기타: 7개)
- **서버 서비스 클래스 수**: **4개**
- **MyBatis 매퍼 XML 수**: **4개**
- **DB 테이블 수**: **4개**
