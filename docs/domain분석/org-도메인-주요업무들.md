# org (조직 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `org` (조직 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/org/*`, `myApp/server/org/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`org##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`org` 도메인은 **조직 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **ORG-01** | **조직 및 사원관리** | 조직 및 사원관리 관련 화면 및 처리 모듈 | 1개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### ORG-01. 조직 및 사원관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **조직정보 등록** | `Org01_Tab_OrgCode` | 1028 | 조직정보 등록 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/org/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Org00_OrgInfo` | Org00_OrgInfo 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Org01_Code` | Org01_Code 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Org02_Info` | Org02_Info 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Org02_SearchOrgInfo` | Org02_SearchOrgInfo 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Org10_RoleStamp` | Org10_RoleStamp 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/org/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `org00_org_info.xml` | `org00_org_info` 테이블 관련 쿼리 매핑 |
| 2 | `org01_code.xml` | `org01_code` 테이블 관련 쿼리 매핑 |
| 3 | `org02_info.xml` | `org02_info` 테이블 관련 쿼리 매핑 |
| 4 | `org10_role_stamp.xml` | `org10_role_stamp` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `org01_code` | 조직코드 | 8 | `org01_code_id` |
| 2 | `org02_info` | 조직정보 | 14 | `org02_info_id` |
| 3 | `org10_role_stamp` | 인감권한 | 5 | `org10_role_stamp_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **1개**
- **UI 컴포넌트 수**: 총 12개 (Tab/Page: 1개, Lookup/Popup/기타: 11개)
- **서버 서비스 클래스 수**: **5개**
- **MyBatis 매퍼 XML 수**: **4개**
- **DB 테이블 수**: **3개**
