# bbs (게시판 / 공지사항 / 사규) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `bbs` (게시판 / 공지사항 / 사규) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/bbs/*`, `myApp/server/bbs/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`bbs##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`bbs` 도메인은 **게시판 / 공지사항 / 사규** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **BBS-01** | **게시판** | 게시판 관련 화면 및 처리 모듈 | 1개 화면 |
| **BBS-02** | **경영정보** | 경영정보 관련 화면 및 처리 모듈 | 1개 화면 |
| **BBS-03** | **공지사항** | 공지사항 관련 화면 및 처리 모듈 | 3개 화면 |
| **BBS-04** | **기타신청** | 기타신청 관련 화면 및 처리 모듈 | 2개 화면 |
| **BBS-05** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 5개 화면 |
| **BBS-06** | **법규정보** | 법규정보 관련 화면 및 처리 모듈 | 1개 화면 |
| **BBS-07** | **신청서관리** | 신청서관리 관련 화면 및 처리 모듈 | 2개 화면 |
| **BBS-08** | **업무활동** | 업무활동 관련 화면 및 처리 모듈 | 1개 화면 |
| **BBS-09** | **회사규정** | 회사규정 관련 화면 및 처리 모듈 | 2개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### BBS-01. 게시판
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **게시판** | `Bbs30_Tab_ClassTree` | 1379 | insert menu |

### BBS-02. 경영정보
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 2 | **경영공지** | `Bbs02_Tab_NoticeViewMgt` | 1259 | 경영정보 공지사항 |

### BBS-03. 공지사항
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **KFS공지등록** | `Bbs02_Tab_NoticeAdmin` | 1246 | 시스템/법규/경영 공지사항 |
| 4 | **사내공지등록** | `Bbs02_Tab_NoticeManager` | 1064 | 공지사항(관리자) |
| 5 | **공지사항** | `Bbs02_Tab_NoticeView` | 1065 | 공지사항 |

### BBS-04. 기타신청
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 6 | **기타신청서 작성** | `Bbs11_Tab_Application` | 1331 | 재직증명서, 경력증명서, 퇴직증명서, 징계내역확인서, 갑근세원천징수확인서 등 신청 |
| 7 | **화환 신청** | `Bbs20_Tab_FloralRequest` | 1363 | 화환 신청 기능 처리 |

### BBS-05. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 8 | **구분** | `Bbs01_Tab_Board` | - | 구분 기능 처리 |
| 9 | **구분** | `Bbs01_Tab_BoardManager` | - | 구분 기능 처리 |
| 10 | **등 록** | `Bbs07_TapPage_Comment` | - | 등 록 기능 처리 |
| 11 | **등 록** | `Bbs32_TapPage_Comment` | - | 등 록 기능 처리 |
| 12 | **제목찾기** | `Page_Board` | - | 제목찾기 기능 처리 |

### BBS-06. 법규정보
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 13 | **법규공지** | `Bbs02_Tab_NoticeViewLaw` | 1258 | 법규정보 공지사항 |

### BBS-07. 신청서관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 14 | **기타신청서 확인** | `Bbs11_Tab_ApplicationMng` | 1332 | 재직증명서, 경력증명서, 퇴직증명서, 징계내역확인서, 갑근세원천징수확인서 등 신청내역 확인 |
| 15 | **화환신청 확인** | `Bbs20_Tab_FloralRequestMng` | 1362 | 화환신청 확인 기능 처리 |

### BBS-08. 업무활동
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 16 | **업무공유** | `Bbs10_Tab_BizShare` | 1254 | 업무공유 |

### BBS-09. 회사규정
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 17 | **회사규정** | `Bbs15_Tab_CompanyRule` | 1344 | 회사규정 조회 |
| 18 | **회사규정(관리자)** | `Bbs15_Tab_CompanyRuleManager` | 1345 | 회사규정 등록/수정/삭제 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/bbs/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Bbs01_Board` | Bbs01_Board 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Bbs02_Notice` | Bbs02_Notice 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Bbs03_Target` | Bbs03_Target 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Bbs04_TargetCompany` | Bbs04_TargetCompany 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Bbs05_History` | Bbs05_History 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Bbs07_Comment` | Bbs07_Comment 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Bbs09_NoticeHistory` | Bbs09_NoticeHistory 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Bbs10_BizShare` | Bbs10_BizShare 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Bbs11_Application` | Bbs11_Application 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Bbs12_ApplicationForm` | Bbs12_ApplicationForm 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Bbs15_CompanyRule` | Bbs15_CompanyRule 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Bbs20_FloralRequest` | Bbs20_FloralRequest 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Bbs21_FloralRequestShare` | Bbs21_FloralRequestShare 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Bbs22_FloralMessage` | Bbs22_FloralMessage 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Bbs30_ClassTree` | Bbs30_ClassTree 비즈니스 로직 및 RPC 서비스 처리 |
| 16 | `Bbs31_Content` | Bbs31_Content 비즈니스 로직 및 RPC 서비스 처리 |
| 17 | `Bbs32_Comment` | Bbs32_Comment 비즈니스 로직 및 RPC 서비스 처리 |
| 18 | `Bbs33_Role` | Bbs33_Role 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/bbs/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `bbs01_board.xml` | `bbs01_board` 테이블 관련 쿼리 매핑 |
| 2 | `bbs02_notice.xml` | `bbs02_notice` 테이블 관련 쿼리 매핑 |
| 3 | `bbs03_target.xml` | `bbs03_target` 테이블 관련 쿼리 매핑 |
| 4 | `bbs04_target_company.xml` | `bbs04_target_company` 테이블 관련 쿼리 매핑 |
| 5 | `bbs05_history.xml` | `bbs05_history` 테이블 관련 쿼리 매핑 |
| 6 | `bbs07_comment.xml` | `bbs07_comment` 테이블 관련 쿼리 매핑 |
| 7 | `bbs09_notice_history.xml` | `bbs09_notice_history` 테이블 관련 쿼리 매핑 |
| 8 | `bbs10_biz_share.xml` | `bbs10_biz_share` 테이블 관련 쿼리 매핑 |
| 9 | `bbs11_application.xml` | `bbs11_application` 테이블 관련 쿼리 매핑 |
| 10 | `bbs12_application_form.xml` | `bbs12_application_form` 테이블 관련 쿼리 매핑 |
| 11 | `bbs15_company_rule.xml` | `bbs15_company_rule` 테이블 관련 쿼리 매핑 |
| 12 | `bbs20_floral_request.xml` | `bbs20_floral_request` 테이블 관련 쿼리 매핑 |
| 13 | `bbs21_floral_request_share.xml` | `bbs21_floral_request_share` 테이블 관련 쿼리 매핑 |
| 14 | `bbs22_floral_message.xml` | `bbs22_floral_message` 테이블 관련 쿼리 매핑 |
| 15 | `bbs30_class_tree.xml` | `bbs30_class_tree` 테이블 관련 쿼리 매핑 |
| 16 | `bbs31_content.xml` | `bbs31_content` 테이블 관련 쿼리 매핑 |
| 17 | `bbs32_comment.xml` | `bbs32_comment` 테이블 관련 쿼리 매핑 |
| 18 | `bbs33_role.xml` | `bbs33_role` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `bbs01_board` | 공지사항자료 | 8 | `bbs01_board_id` |
| 2 | `bbs02_notice` | 공지사항 | 20 | `bbs02_notice_id` |
| 3 | `bbs03_target` | 개별공지대상 | 4 | `bbs03_target_id` |
| 4 | `bbs04_target_company` | 개별공지대상 | 4 | `bbs04_target_company_id` |
| 5 | `bbs05_history` | 공지사항 History | 4 | `bbs05_history_id` |
| 6 | `bbs06_notice_no` | 공지번호 관리 | 4 | `bbs06_notice_no_id` |
| 7 | `bbs07_comment` | 공지사항 댓글 | 7 | `bbs07_comment_id` |
| 8 | `bbs08_notice_law_record` | 법규/경영공지 DML기록 | 21 | `bbs08_notice_law_record_id` |
| 9 | `bbs09_notice_history` | 공지사항 History | 7 | `bbs09_notice_history_id` |
| 10 | `bbs10_biz_share` | 업무공유 | 8 | `bbs10_biz_share_id` |
| 11 | `bbs11_application` | 요청서 작성 | 11 | `bbs11_application_id` |
| 12 | `bbs12_application_form` | 요청서 양식 | 6 | `bbs12_application_form_id` |
| 13 | `bbs15_company_rule` | 회사규정 | 16 | `bbs15_company_rule_id` |
| 14 | `bbs20_floral_request` | 화환신청 | 25 | `bbs20_floral_request_id` |
| 15 | `bbs21_floral_request_share` | 화환신청 공유지정 | 5 | `bbs21_floral_request_share_id` |
| 16 | `bbs22_floral_message` | 화환신청 문구 관리 | 4 | `bbs22_floral_message_id` |
| 17 | `bbs30_class_tree` | 게시판분류 | 9 | `bbs30_class_tree_id` |
| 18 | `bbs31_content` | 게시판내용 | 10 | `bbs31_content_id` |
| 19 | `bbs32_comment` | 게시판 댓글 | 7 | `bbs32_comment_id` |
| 20 | `bbs33_role` | 게시판분류권한 | 6 | `bbs33_role_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **18개**
- **UI 컴포넌트 수**: 총 57개 (Tab/Page: 18개, Lookup/Popup/기타: 39개)
- **서버 서비스 클래스 수**: **18개**
- **MyBatis 매퍼 XML 수**: **18개**
- **DB 테이블 수**: **20개**
