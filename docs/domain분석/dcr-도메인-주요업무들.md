# dcr (문서분류 / 문서권한·양식 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `dcr` (문서분류 / 문서권한·양식 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/dcr/*`, `myApp/server/dcr/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`dcr##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`dcr` 도메인은 **문서분류 / 문서권한·양식 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **DCR-01** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 9개 화면 |
| **DCR-02** | **메일관리** | 메일관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **DCR-03** | **문서(전자결재)** | 문서(전자결재) 관련 화면 및 처리 모듈 | 2개 화면 |
| **DCR-04** | **문서검색** | 문서검색 관련 화면 및 처리 모듈 | 3개 화면 |
| **DCR-05** | **문서관리** | 문서관리 관련 화면 및 처리 모듈 | 2개 화면 |
| **DCR-06** | **문서권한관리** | 문서권한관리 관련 화면 및 처리 모듈 | 3개 화면 |
| **DCR-07** | **문서작성** | 문서작성 관련 화면 및 처리 모듈 | 2개 화면 |
| **DCR-08** | **전자결재** | 전자결재 관련 화면 및 처리 모듈 | 1개 화면 |
| **DCR-09** | **파일 및 양식관리** | 파일 및 양식관리 관련 화면 및 처리 모듈 | 1개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### DCR-01. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **검색** | `Dcr00_TabPage_GridFundPlan` | - | 검색 기능 처리 |
| 2 | **문서분류** | `Dcr00_TabPage_TreeFundPlan` | - | 문서분류 기능 처리 |
| 3 | **초기화** | `Dcr00_Tab_Download` | - | 초기화 기능 처리 |
| 4 | **구분코드** | `Dcr00_Tab_TreeFundPlan` | - | 구분코드 기능 처리 |
| 5 | **조직명** | `Dcr03_TabPage_DcrAuth` | - | 조직명 기능 처리 |
| 6 | **펼치기** | `Dcr03_TabPage_OrgAuth` | - | 펼치기 기능 처리 |
| 7 | **검색** | `Dcr04_TabPage_DocList` | - | 검색 기능 처리 |
| 8 | **사원별 권한현황** | `Dcr04_TabPage_EmpAuth` | - | 사원별 권한현황 기능 처리 |
| 9 | **회사명** | `Dcr30_TabPage_Company` | - | 회사명 기능 처리 |

### DCR-02. 메일관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 10 | **발신메일목록** | `Dcr10_Tab_MailHistory` | 1023 | 결재메일 목록 |

### DCR-03. 문서(전자결재)
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 11 | **문서분류** | `Dcr01_Tab_ClassTree` | 1110 | 문서분류 |
| 12 | **문서분류지정** | `Dcr30_Tab_LinkAdmin` | 1280 | 문서분류지정화면 |

### DCR-04. 문서검색
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 13 | **문서 다운로드** | `Dcr00_Tab_ApprList` | 1326 | 문서 다운로드 |
| 14 | **통합 문서검색** | `Dcr00_Tab_DocList` | 1006 | 통합 문서검색 |
| 15 | **문서별 첨부파일 검색** | `Dcr00_Tab_FileList` | 1224 | 문서별 첨부파일 검색 |

### DCR-05. 문서관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 16 | **문서이동** | `Dcr01_Tab_DcrClassModify` | 1004 | 상신된 문서 문서분류코드 변경 |
| 17 | **업무별 문서작성(관리자)** | `Dcr01_Tab_DcrManager` | 1003 | 문서작성 및 관리(관리자) |

### DCR-06. 문서권한관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 18 | **문서분류별 조직 맵핑** | `Dcr03_Tab_DcrAuth` | 1073 | 문서별 조직(부서) 맵핑 |
| 19 | **조직별 문서분류 맵핑** | `Dcr03_Tab_OrgAuth` | 1074 | 조직(부서)별 문서분류 맵핑 |
| 20 | **조회권한 예외사원 등록** | `Dcr04_Tab_EmpAuth` | 1491 | 조회권한 예외사원 등록 기능 처리 |

### DCR-07. 문서작성
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 21 | **업무별 문서작성** | `Dcr01_Tab_DcrUser` | 1002 | 문서관리 |
| 22 | **신규 문서작성** | `Dcr01_Tab_DcrWrite` | 1318 | 신규 문서작성 (문서분류 세부분류 관리시 사용가능) |

### DCR-08. 전자결재
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 23 | **발신메일 목록(관리자)** | `Dcr10_Tab_MailHistory_Manager` | 1024 | 발신메일 목록(관리자) |

### DCR-09. 파일 및 양식관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 24 | **문서양식등록** | `Dcr05_Tab_DocType` | 1007 | 문서양식등록 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/dcr/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Dcr00_DocList` | Dcr00_DocList 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Dcr01_ClassTree` | Dcr01_ClassTree 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Dcr03_OrgAuth` | Dcr03_OrgAuth 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Dcr04_EmpAuth` | Dcr04_EmpAuth 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Dcr05_DocType` | Dcr05_DocType 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Dcr06_RelateDocType` | Dcr06_RelateDocType 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Dcr07_ClassDetail` | Dcr07_ClassDetail 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Dcr08_OftenUse` | Dcr08_OftenUse 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Dcr10_MailHistory` | Dcr10_MailHistory 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Dcr10_MailSenderPDF` | Dcr10_MailSenderPDF 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Dcr11_MailFileHistory` | Dcr11_MailFileHistory 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Dcr20_RelateIcs` | Dcr20_RelateIcs 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Dcr21_RelateIcr` | Dcr21_RelateIcr 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Dcr30_Link` | Dcr30_Link 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Dcr40_StampAuth` | Dcr40_StampAuth 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/dcr/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `dcr00_doc_list.xml` | `dcr00_doc_list` 테이블 관련 쿼리 매핑 |
| 2 | `dcr01_class_tree.xml` | `dcr01_class_tree` 테이블 관련 쿼리 매핑 |
| 3 | `dcr03_org_auth.xml` | `dcr03_org_auth` 테이블 관련 쿼리 매핑 |
| 4 | `dcr04_emp_auth.xml` | `dcr04_emp_auth` 테이블 관련 쿼리 매핑 |
| 5 | `dcr05_doc_type.xml` | `dcr05_doc_type` 테이블 관련 쿼리 매핑 |
| 6 | `dcr06_relate_doc_Type.xml` | `dcr06_relate_doc_Type` 테이블 관련 쿼리 매핑 |
| 7 | `dcr07_class_detail.xml` | `dcr07_class_detail` 테이블 관련 쿼리 매핑 |
| 8 | `dcr08_often_use.xml` | `dcr08_often_use` 테이블 관련 쿼리 매핑 |
| 9 | `dcr10_mail_history.xml` | `dcr10_mail_history` 테이블 관련 쿼리 매핑 |
| 10 | `dcr11_mail_file_history.xml` | `dcr11_mail_file_history` 테이블 관련 쿼리 매핑 |
| 11 | `dcr20_relate_ics.xml` | `dcr20_relate_ics` 테이블 관련 쿼리 매핑 |
| 12 | `dcr21_relate_icr.xml` | `dcr21_relate_icr` 테이블 관련 쿼리 매핑 |
| 13 | `dcr30_link.xml` | `dcr30_link` 테이블 관련 쿼리 매핑 |
| 14 | `dcr40_stamp_auth.xml` | `dcr40_stamp_auth` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `dcr01_class_tree` | 문서분류 | 21 | `dcr01_class_tree_id` |
| 2 | `dcr03_org_auth` | 조직별 권한등록 | 6 | `dcr03_org_auth_id` |
| 3 | `dcr04_doc` | 문서 (사용안함!!) | 7 | `dcr04_doc_id` |
| 4 | `dcr04_emp_auth` | 사원별 권한등록 | 5 | `dcr04_emp_auth_id` |
| 5 | `dcr05_doc_type` | 문서양식 | 6 | `dcr05_doc_type_id` |
| 6 | `dcr06_relate_doc_type` | 연관 문서양식 | 6 | `dcr06_relate_doc_type_id` |
| 7 | `dcr07_class_detail` | 문서분류-세부분류 | 8 | `dcr07_class_detail_id` |
| 8 | `dcr08_often_use` | 문서분류-자주사용 | 7 | `dcr08_often_use_id` |
| 9 | `dcr10_mail_history` | 메일History | 13 | `dcr10_mail_history_id` |
| 10 | `dcr11_mail_file_history` | 메일첨부파일History | 3 | `dcr11_mail_file_history_id` |
| 11 | `dcr20_relate_ics` | 연관내부통제 | 5 | `dcr20_relate_ics_id` |
| 12 | `dcr21_relate_icr` | 연관내규 | 5 | `dcr21_relate_icr_id` |
| 13 | `dcr30_link` | 문서분류연결 | 6 | `dcr30_link_id` |
| 14 | `dcr40_stamp_auth` | 문서분류별 권한등록 | 5 | `dcr40_stamp_auth_id` |
| 15 | `dcr99_class_tree_del` | 문서분류 삭제이력 | 22 | `dcr99_class_tree_del_id` |
| 16 | `dcr99_class_tree_temp` | - | 17 | `dcr99_class_tree_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **24개**
- **UI 컴포넌트 수**: 총 54개 (Tab/Page: 24개, Lookup/Popup/기타: 30개)
- **서버 서비스 클래스 수**: **15개**
- **MyBatis 매퍼 XML 수**: **14개**
- **DB 테이블 수**: **16개**
