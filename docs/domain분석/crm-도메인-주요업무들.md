# crm (영업활동(CRM) / 영업 Item 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `crm` (영업활동(CRM) / 영업 Item 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/crm/*`, `myApp/server/crm/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`crm##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`crm` 도메인은 **영업활동(CRM) / 영업 Item 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **CRM-01** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 5개 화면 |
| **CRM-02** | **업무활동** | 업무활동 관련 화면 및 처리 모듈 | 2개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### CRM-01. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **제목/내용** | `Crm02_Tab_Inspection` | - | 제목/내용 기능 처리 |
| 2 | **제목/내용** | `Crm02_Tab_InspectionManager` | - | 제목/내용 기능 처리 |
| 3 | **제목/내용** | `Crm05_Tab_CounselInfo_in` | - | 제목/내용 기능 처리 |
| 4 | **제목/내용** | `Crm05_Tab_CounselInfo_out` | - | 제목/내용 기능 처리 |
| 5 | **등록(복사)** | `Crm09_Tab_ContactPoint` | - | 등록(복사) 기능 처리 |

### CRM-02. 업무활동
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 6 | **(X)영업활동관리** | `Crm01_Tab_ItemTreeGrid` | 1062 | 영업활동관리 |
| 7 | **(X)거래처 및 업무활동 등록** | `Crm09_Tab_ContactPointTreeGrid` | 1063 | (X)거래처 및 업무활동 등록 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/crm/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Crm01_Item` | Crm01_Item 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Crm02_Inspection` | Crm02_Inspection 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Crm05_Counsel` | Crm05_Counsel 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Crm09_Contact` | Crm09_Contact 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Crm10_Comment` | Crm10_Comment 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Crm11_Count` | Crm11_Count 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Crm12_WorkDetail` | Crm12_WorkDetail 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Crm13_RelateFund` | Crm13_RelateFund 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Crm14_ShareDefault` | Crm14_ShareDefault 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Crm15_Share` | Crm15_Share 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/crm/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `crm01_item.xml` | `crm01_item` 테이블 관련 쿼리 매핑 |
| 2 | `crm02_inspection.xml` | `crm02_inspection` 테이블 관련 쿼리 매핑 |
| 3 | `crm05_counsel.xml` | `crm05_counsel` 테이블 관련 쿼리 매핑 |
| 4 | `crm09_contact.xml` | `crm09_contact` 테이블 관련 쿼리 매핑 |
| 5 | `crm10_cmnt.xml` | `crm10_cmnt` 테이블 관련 쿼리 매핑 |
| 6 | `crm11_count.xml` | `crm11_count` 테이블 관련 쿼리 매핑 |
| 7 | `crm12_work_detail.xml` | `crm12_work_detail` 테이블 관련 쿼리 매핑 |
| 8 | `crm13_relate_fund.xml` | `crm13_relate_fund` 테이블 관련 쿼리 매핑 |
| 9 | `crm14_share_default.xml` | `crm14_share_default` 테이블 관련 쿼리 매핑 |
| 10 | `crm15_share.xml` | `crm15_share` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `crm01_item` | - | 15 | `crm01_item_id` |
| 2 | `crm02_inspection` | - | 10 | `crm02_inspection_id` |
| 3 | `crm05_counsel` | - | 12 | `crm05_counsel_id` |
| 4 | `crm06_market` | - | 8 | `crm06_market_id` |
| 5 | `crm09_contact` | - | 15 | `crm09_contact_id` |
| 6 | `crm10_cmnt` | - | 5 | `crm10_cmnt_id` |
| 7 | `crm11_count` | - | 4 | `crm11_count_id` |
| 8 | `crm12_work_detail` | 업무활동상세 | 10 | `crm12_work_detail_id` |
| 9 | `crm13_relate_fund` | 업무활동상세 연결펀드 | 3 | `crm13_relate_fund_id` |
| 10 | `crm14_share_default` | 영업거래처 공유지정(업무활동내용 공유지정 Default Data) | 6 | `crm14_share_default_id` |
| 11 | `crm15_share` | 업무활동내용 공유지정 | 6 | `crm15_share_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **7개**
- **UI 컴포넌트 수**: 총 21개 (Tab/Page: 7개, Lookup/Popup/기타: 14개)
- **서버 서비스 클래스 수**: **10개**
- **MyBatis 매퍼 XML 수**: **10개**
- **DB 테이블 수**: **11개**
