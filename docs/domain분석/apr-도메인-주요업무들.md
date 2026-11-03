# apr (전자결재 / 상신문서 관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `apr` (전자결재 / 상신문서 관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/apr/*`, `myApp/server/apr/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`apr##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`apr` 도메인은 **전자결재 / 상신문서 관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **APR-01** | **기타신청** | 기타신청 관련 화면 및 처리 모듈 | 4개 화면 |
| **APR-02** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 8개 화면 |
| **APR-03** | **메일관리** | 메일관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **APR-04** | **문서검색** | 문서검색 관련 화면 및 처리 모듈 | 3개 화면 |
| **APR-05** | **문서관리** | 문서관리 관련 화면 및 처리 모듈 | 3개 화면 |
| **APR-06** | **문서작성** | 문서작성 관련 화면 및 처리 모듈 | 1개 화면 |
| **APR-07** | **문서작성현황** | 문서작성현황 관련 화면 및 처리 모듈 | 2개 화면 |
| **APR-08** | **법인서류** | 법인서류 관련 화면 및 처리 모듈 | 9개 화면 |
| **APR-09** | **이익제공(수령)현황** | 이익제공(수령)현황 관련 화면 및 처리 모듈 | 1개 화면 |
| **APR-10** | **전자결재** | 전자결재 관련 화면 및 처리 모듈 | 9개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### APR-01. 기타신청
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **대외활동 신청서 작성** | `Apr01_Tab_ExternalBiz` | 1343 | 대외활동 신청서 작성 기능 처리 |
| 2 | **사무수탁사 확인서 작성** | `Apr01_Tab_OfficeWorkCert` | 1453 | 사무수탁사 확인서 작성 기능 처리 |
| 3 | **법인서류 및 날인 신청** | `Apr16_Tab_StampDocAppl` | 1330 | 법인서류 및 인감날인 신청 |
| 4 | **구)법인서류 및 날인 신청** | `Apr17_Tab_CorpDocApp` | 1510 | 구)법인서류 및 날인 신청 기능 처리 |

### APR-02. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 5 | **첨부파일 옵션설정** | `Apr03_Page_Relate` | - | 첨부파일 옵션설정 기능 처리 |
| 6 | **코드** | `Apr03_TabPage_Relate` | - | 코드 기능 처리 |
| 7 | **결재라인 설정** | `Apr06_Tab_ApprStepRule` | - | 결재라인 설정 기능 처리 |
| 8 | **사용여부** | `Apr09_Tab_ApprAgree` | - | 사용여부 기능 처리 |
| 9 | **조회구간** | `Apr11_Tab_AdvertBook` | - | 조회구간 기능 처리 |
| 10 | **검색** | `Apr13_Tab_PersonDcrAuth` | - | 검색 기능 처리 |
| 11 | **출력/다운로드** | `Apr19_Tab_OrgStampList` | - | 출력/다운로드 기능 처리 |
| 12 | **결재선 설정** | `Apr31_Page_ApprStepGroupMember` | - | 결재선 설정 기능 처리 |

### APR-03. 메일관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 13 | **(X)직책별 결재자 등록** | `Apr08_Tab_ApprRole` | 1027 | 직책별 결재자 등록 |

### APR-04. 문서검색
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 14 | **펀드별 문서검색** | `Apr01_Tab_FundDocument` | 1005 | 펀드별 문서검색 |
| 15 | **(X)종목별 문서검색** | `Apr01_Tab_ItemDocument` | 1137 | 종목별 문서검색 |
| 16 | **폐기문서 승인** | `Apr90_Tab_DisposalAppr` | 1490 | 폐기문서 승인 기능 처리 |

### APR-05. 문서관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 17 | **폐기문서 복구** | `Apr01_Tab_Restore` | 1098 | 폐기문서 복구 |
| 18 | **문서결재선 그룹관리** | `Apr30_Tab_ApprStepGroup` | 1282 | 문서결재선 그룹관리 |
| 19 | **폐기문서 승인(관리자)** | `Apr90_Tab_DisposalListAdmin` | 1253 | 폐기문서 승인 |

### APR-06. 문서작성
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 20 | **폐기문서 신청현황** | `Apr90_Tab_DisposalList` | 1443 | 폐기문서 신청현황 |

### APR-07. 문서작성현황
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 21 | **건별명세** | `Apr01_Tab_SubList` | 1011 | 건별명세 |
| 22 | **운영현황표** | `Apr01_Tab_TotalList` | 1010 | 운영현황표 |

### APR-08. 법인서류
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 23 | **법인등기부등본 관리(X)** | `Apr15_Tab_CcorCert` | 1291 | 법인등기부등본 관리 |
| 24 | **법인인감증명서 관리(X)** | `Apr15_Tab_StampCert` | 1194 | 인감증명서 관리 |
| 25 | **법인서류 매수관리** | `Apr16_Tab_StampDocManager` | 1328 | 법인인감증명서, 법인등기부등본 관리 |
| 26 | **인감날인본 업로드확인** | `Apr16_Tab_StampFileCheck` | 1350 | 인감날인본 사후업로드 확인 |
| 27 | **인감날인대장** | `Apr16_Tab_StampList` | 1329 | 전체 인감날인내역 조회 |
| 28 | **부서 인감날인대장** | `Apr16_Tab_StampListOrg` | 1484 | 부서(사용권한체크) 인감날인내역 조회 |
| 29 | **구)법인서류 매수관리** | `Apr17_Tab_CorpDoc` | 1507 | 구)법인서류 매수관리 기능 처리 |
| 30 | **구)인감날인본 업로드확인** | `Apr19_Tab_StampFileCheck` | 1509 | 구)인감날인본 업로드확인 기능 처리 |
| 31 | **구)인감날인대장** | `Apr19_Tab_StampList` | 1508 | 구)인감날인대장 기능 처리 |

### APR-09. 이익제공(수령)현황
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 32 | **이익제공 사전승인신청** | `Apr01_Tab_BizPriorApproval` | 1134 | 이익제공(수령) 사전승인 신청 |

### APR-10. 전자결재
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 33 | **결재내역 조회** | `Apr01_Tab_MyApproveList` | 1018 | 결재내역 조회 |
| 34 | **공람내역 조회** | `Apr01_Tab_MyAuthList` | 1428 | 공람내역 조회 |
| 35 | **참조내역 조회** | `Apr01_Tab_MyReferenceList` | 1093 | 참조내역 조회 |
| 36 | **상신내역 조회** | `Apr01_Tab_MyRequestList` | 1019 | 상신내역 조회 |
| 37 | **(X)인감대장** | `Apr01_Tab_StampSeq` | 1020 | 인감대장 |
| 38 | **대결자 지정** | `Apr07_Tab_AltAppr` | 1021 | 대결자 지정 |
| 39 | **대결자 지정(관리자)** | `Apr07_Tab_AltApprMgr` | 1022 | 대결자 지정(관리자) |
| 40 | **사용인감등록** | `Apr10_Tab_Stamp` | 1026 | 사용인감등록 |
| 41 | **추가 대표명의 등록** | `Apr15_Tab_ReprCorp` | 1506 | 추가 대표명의 등록 기능 처리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/apr/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Apr00_StampSeq` | Apr00_StampSeq 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Apr01_Appr` | Apr01_Appr 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Apr01_ApprTemp` | Apr01_ApprTemp 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Apr03_RelateFund` | Apr03_RelateFund 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Apr04_ApprStep` | Apr04_ApprStep 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Apr05_RelateDoc` | Apr05_RelateDoc 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Apr06_ApprStepRule` | Apr06_ApprStepRule 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Apr07_AltAppr` | Apr07_AltAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Apr08_ApprRole` | Apr08_ApprRole 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Apr09_ApprAgree` | Apr09_ApprAgree 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Apr10_ConvertHtml2PDF` | Apr10_ConvertHtml2PDF 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Apr10_PreviewStampPDF` | Apr10_PreviewStampPDF 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Apr10_Stamp` | Apr10_Stamp 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Apr10_StampPDF7` | Apr10_StampPDF7 비즈니스 로직 및 RPC 서비스 처리 |
| 15 | `Apr11_AdvertBook` | Apr11_AdvertBook 비즈니스 로직 및 RPC 서비스 처리 |
| 16 | `Apr12_RelateAdv` | Apr12_RelateAdv 비즈니스 로직 및 RPC 서비스 처리 |
| 17 | `Apr13_PersonAuth` | Apr13_PersonAuth 비즈니스 로직 및 RPC 서비스 처리 |
| 18 | `Apr14_RelateAst` | Apr14_RelateAst 비즈니스 로직 및 RPC 서비스 처리 |
| 19 | `Apr15_ReprCorp` | Apr15_ReprCorp 비즈니스 로직 및 RPC 서비스 처리 |
| 20 | `Apr16_StampDoc` | Apr16_StampDoc 비즈니스 로직 및 RPC 서비스 처리 |
| 21 | `Apr17_CorpDoc` | Apr17_CorpDoc 비즈니스 로직 및 RPC 서비스 처리 |
| 22 | `Apr18_RelateCorpDoc` | Apr18_RelateCorpDoc 비즈니스 로직 및 RPC 서비스 처리 |
| 23 | `Apr19_RelateStamp` | Apr19_RelateStamp 비즈니스 로직 및 RPC 서비스 처리 |
| 24 | `Apr20_RelateIcs` | Apr20_RelateIcs 비즈니스 로직 및 RPC 서비스 처리 |
| 25 | `Apr21_RelateAppr` | Apr21_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |
| 26 | `Apr22_RelateIcr` | Apr22_RelateIcr 비즈니스 로직 및 RPC 서비스 처리 |
| 27 | `Apr30_ApprStepGroup` | Apr30_ApprStepGroup 비즈니스 로직 및 RPC 서비스 처리 |
| 28 | `Apr31_ApprStepGroupMember` | Apr31_ApprStepGroupMember 비즈니스 로직 및 RPC 서비스 처리 |
| 29 | `Apr40_DownloadHistory` | Apr40_DownloadHistory 비즈니스 로직 및 RPC 서비스 처리 |
| 30 | `Apr41_OpenHistory` | Apr41_OpenHistory 비즈니스 로직 및 RPC 서비스 처리 |
| 31 | `Apr42_Comment` | Apr42_Comment 비즈니스 로직 및 RPC 서비스 처리 |
| 32 | `Apr50_Bookmark` | Apr50_Bookmark 비즈니스 로직 및 RPC 서비스 처리 |
| 33 | `Apr90_DisposalList` | Apr90_DisposalList 비즈니스 로직 및 RPC 서비스 처리 |
| 34 | `Apr91_DisposalHistory` | Apr91_DisposalHistory 비즈니스 로직 및 RPC 서비스 처리 |
| 35 | `Apr92_ApprModi` | Apr92_ApprModi 비즈니스 로직 및 RPC 서비스 처리 |
| 36 | `Apr99_ApprDel` | Apr99_ApprDel 비즈니스 로직 및 RPC 서비스 처리 |
| 37 | `AprServerFunction` | AprServerFunction 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/apr/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `apr00_stamp_seq.xml` | `apr00_stamp_seq` 테이블 관련 쿼리 매핑 |
| 2 | `apr01_appr.xml` | `apr01_appr` 테이블 관련 쿼리 매핑 |
| 3 | `apr01_appr_temp.xml` | `apr01_appr_temp` 테이블 관련 쿼리 매핑 |
| 4 | `apr03_relate_fund.xml` | `apr03_relate_fund` 테이블 관련 쿼리 매핑 |
| 5 | `apr04_appr_step.xml` | `apr04_appr_step` 테이블 관련 쿼리 매핑 |
| 6 | `apr05_relate_doc.xml` | `apr05_relate_doc` 테이블 관련 쿼리 매핑 |
| 7 | `apr06_appr_step_rule.xml` | `apr06_appr_step_rule` 테이블 관련 쿼리 매핑 |
| 8 | `apr07_alt_appr.xml` | `apr07_alt_appr` 테이블 관련 쿼리 매핑 |
| 9 | `apr08_appr_role.xml` | `apr08_appr_role` 테이블 관련 쿼리 매핑 |
| 10 | `apr09_appr_agree.xml` | `apr09_appr_agree` 테이블 관련 쿼리 매핑 |
| 11 | `apr10_stamp.xml` | `apr10_stamp` 테이블 관련 쿼리 매핑 |
| 12 | `apr11_advert_book.xml` | `apr11_advert_book` 테이블 관련 쿼리 매핑 |
| 13 | `apr12_relate_adv.xml` | `apr12_relate_adv` 테이블 관련 쿼리 매핑 |
| 14 | `apr13_person_auth.xml` | `apr13_person_auth` 테이블 관련 쿼리 매핑 |
| 15 | `apr14_relate_ast.xml` | `apr14_relate_ast` 테이블 관련 쿼리 매핑 |
| 16 | `apr15_repr_corp.xml` | `apr15_repr_corp` 테이블 관련 쿼리 매핑 |
| 17 | `apr16_stamp_doc.xml` | `apr16_stamp_doc` 테이블 관련 쿼리 매핑 |
| 18 | `apr17_corp_doc.xml` | `apr17_corp_doc` 테이블 관련 쿼리 매핑 |
| 19 | `apr18_relate_corp_doc.xml` | `apr18_relate_corp_doc` 테이블 관련 쿼리 매핑 |
| 20 | `apr19_relate_stamp.xml` | `apr19_relate_stamp` 테이블 관련 쿼리 매핑 |
| 21 | `apr20_relate_ics.xml` | `apr20_relate_ics` 테이블 관련 쿼리 매핑 |
| 22 | `apr21_relate_appr.xml` | `apr21_relate_appr` 테이블 관련 쿼리 매핑 |
| 23 | `apr22_relate_icr.xml` | `apr22_relate_icr` 테이블 관련 쿼리 매핑 |
| 24 | `apr30_appr_step_group.xml` | `apr30_appr_step_group` 테이블 관련 쿼리 매핑 |
| 25 | `apr31_appr_step_group_member.xml` | `apr31_appr_step_group_member` 테이블 관련 쿼리 매핑 |
| 26 | `apr40_download_history.xml` | `apr40_download_history` 테이블 관련 쿼리 매핑 |
| 27 | `apr41_open_history.xml` | `apr41_open_history` 테이블 관련 쿼리 매핑 |
| 28 | `apr42_comment.xml` | `apr42_comment` 테이블 관련 쿼리 매핑 |
| 29 | `apr50_bookmark.xml` | `apr50_bookmark` 테이블 관련 쿼리 매핑 |
| 30 | `apr90_disposal_list.xml` | `apr90_disposal_list` 테이블 관련 쿼리 매핑 |
| 31 | `apr91_disposal_history.xml` | `apr91_disposal_history` 테이블 관련 쿼리 매핑 |
| 32 | `apr92_appr_modi.xml` | `apr92_appr_modi` 테이블 관련 쿼리 매핑 |
| 33 | `apr99_appr_del.xml` | `apr99_appr_del` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `apr01_appr` | 전자결재상신내용 | 23 | `apr01_appr_id` |
| 2 | `apr01_appr_temp` | - | 24 | `apr01_appr_id` |
| 3 | `apr03_relate_fund` | 상신연관펀드맵핑 | 5 | `apr03_relate_fund_id` |
| 4 | `apr04_appr_step` | 결재단계정보 | 13 | `apr04_appr_step_id` |
| 5 | `apr05_relate_doc` | 연관문서 | 4 | `apr05_relate_doc_id` |
| 6 | `apr06_appr_step_rule` | 전자결재 결재자 설정정보 | 10 | `apr06_appr_step_rule_id` |
| 7 | `apr07_alt_appr` | 대결자지정 | 10 | `apr07_alt_appr_id` |
| 8 | `apr08_appr_role` | - | 7 | `apr08_appr_role_id` |
| 9 | `apr09_appr_agree` | - | 8 | `apr09_appr_agree_id` |
| 10 | `apr10_stamp` | 인장등록 | 14 | `apr10_stamp_id` |
| 11 | `apr11_advert_book` | 광고대장 | 8 | `apr11_advert_book_id` |
| 12 | `apr12_relate_adv` | 상신 연관계좌 매핑 | 3 | `apr12_relate_adv_id` |
| 13 | `apr12_relate_bond` | 상신 연관채권 매핑 | 3 | `apr12_relate_bond_id` |
| 14 | `apr13_person_auth` | 문서공람 | 3 | `apr13_person_auth_id` |
| 15 | `apr14_relate_ast` | 상신 연관종목 매핑 | 3 | `apr14_relate_ast_id` |
| 16 | `apr15_repr_corp` | 추가 대표명의 관리 | 9 | `apr15_repr_corp_id` |
| 17 | `apr15_stamp_cert` | 인감증명서(부수관리) - 사용X (apr17로 변경) | 12 | `apr15_stamp_cert_id` |
| 18 | `apr16_relate_stamp_cert` | 연관문서 연결 - 사용X | 3 | `apr16_relate_stamp_cert_id` |
| 19 | `apr16_stamp_doc` | 법인서류 및 날인신청 관리 | 21 | `apr16_stamp_doc_id` |
| 20 | `apr17_corp_doc` | 인감날인 및 법인서류 부수관리 - 사용X (apr16로 변경) | 15 | `apr17_corp_doc_id` |
| 21 | `apr18_relate_corp_doc` | 인감날인 및 법인서류 연결문서 - 사용X (apr16로 변경) | 3 | `apr18_relate_corp_doc_id` |
| 22 | `apr19_relate_stamp` | 인감날인 상세 - 사용X (apr16로 변경) | 9 | `apr19_relate_stamp_id` |
| 23 | `apr20_relate_ics` | 연관내부통제 | 10 | `apr20_relate_ics_id` |
| 24 | `apr21_relate_appr` | 상신 연관문서 매핑 | 3 | `apr21_relate_appr_id` |
| 25 | `apr22_relate_icr` | 연관내규 | 10 | `apr22_relate_icr_id` |
| 26 | `apr30_appr_step_group` | 결재선 지정그룹 | 4 | `apr30_appr_step_group_id` |
| 27 | `apr31_appr_step_group_member` | 결재선 지정그룹멤버 | 6 | `apr31_appr_step_group_member_id` |
| 28 | `apr40_download_history` | - | 5 | `apr40_download_history_id` |
| 29 | `apr41_open_history` | - | 6 | `apr41_open_history_id` |
| 30 | `apr42_comment` | 상신문서 댓글 | 7 | `apr42_comment_id` |
| 31 | `apr50_bookmark` | 상신문서 북마크 | 5 | `apr50_bookmark_id` |
| 32 | `apr90_disposal_list` | 폐기문서 신청 | 10 | `apr90_disposal_list_id` |
| 33 | `apr91_disposal_history` | 폐기문서 이력 | 6 | `apr91_disposal_history_id` |
| 34 | `apr92_appr_modi` | - | 15 | `apr92_appr_modi_id` |
| 35 | `apr99_appr_del` | - | 24 | `apr99_appr_del_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **41개**
- **UI 컴포넌트 수**: 총 109개 (Tab/Page: 38개, Lookup/Popup/기타: 71개)
- **서버 서비스 클래스 수**: **37개**
- **MyBatis 매퍼 XML 수**: **33개**
- **DB 테이블 수**: **35개**
