# act (회계 / 계정관리) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `act` (회계 / 계정관리) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/act/*`, `myApp/server/act/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`act##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`act` 도메인은 **회계 / 계정관리** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **ACT-01** | **결산** | 결산 관련 화면 및 처리 모듈 | 1개 화면 |
| **ACT-02** | **관리회계** | 관리회계 관련 화면 및 처리 모듈 | 6개 화면 |
| **ACT-03** | **사업비관리** | 사업비관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **ACT-04** | **예금관리** | 예금관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **ACT-05** | **재무제표** | 재무제표 관련 화면 및 처리 모듈 | 3개 화면 |
| **ACT-06** | **전표입력** | 전표입력 관련 화면 및 처리 모듈 | 2개 화면 |
| **ACT-07** | **특수회계처리(외화)** | 특수회계처리(외화) 관련 화면 및 처리 모듈 | 1개 화면 |
| **ACT-08** | **회계장부** | 회계장부 관련 화면 및 처리 모듈 | 4개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### ACT-01. 결산
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **회계마감** | `Act04_Tab_Close` | 1195 | 계정원장,자산원장의 정리 및 대사작업, 마감작업 |

### ACT-02. 관리회계
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 2 | **결산회기관리** | `Act09_Tab_AccountNum` | 1206 | 결산회기관리 |
| 3 | **대표계정 관리** | `Act10_Tab_ReprAccount` | 1147 | 대표계정코드 관리 |
| 4 | **계정코드 관리** | `Act01_Tab_AccountCode` | 1114 | 계정코드 관리 기능 처리 |
| 5 | **거래유형별 분개맵핑** | `Act11_Tab_TrJournalMap` | 1168 | 거래별 분개맵핑 |
| 6 | **실계정맵핑** | `Act13_Tab_RealAccountMap` | 1169 | 실계정맵핑 |
| 7 | **마감검증 체크항목** | `Act15_Tab_CloseCheck` | 1368 | 마감검증 체크항목 기능 처리 |

### ACT-03. 사업비관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 8 | **급여/카드 회계처리** | `Act02_Tab_CreateJournalBiz` | 1180 | 업무단(급여, 법카사용, 최저보수)에서 발생한 회계처리 |

### ACT-04. 예금관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 9 | **일일자금관리** | `Act02_Tab_DepositIoList` | 1470 | 일일자금관리 기능 처리 |

### ACT-05. 재무제표
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 10 | **재무상태표** | `Act04_Tab_ReportBS` | 1179 | 재무상태표 |
| 11 | **금감원보고용 재무제표** | `Act04_Tab_ReportFSS` | 1225 | 금감원보고용 재무제표 |
| 12 | **손익계산서** | `Act04_Tab_ReportPL` | 1178 | 손익계산서 |

### ACT-06. 전표입력
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 13 | **전표입력** | `Act02_Tab_CreateJournal` | 1148 | 분개 생성 |
| 14 | **전표승인처리** | `Act02_Tab_JournalFix` | 1207 | 전표승인처리 |

### ACT-07. 특수회계처리(외화)
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 15 | **전표입력(외화)** | `Act02_Tab_CreateForJournal` | 1176 | 정정분개(외화) |

### ACT-08. 회계장부
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 16 | **분개장(외화)** | `Act02_Tab_ForJournal` | 1177 | 분개장(외화) |
| 17 | **분개장** | `Act02_Tab_Journal` | 1149 | 분개장 |
| 18 | **계정별원장** | `Act02_Tab_JournalSub` | 1150 | 계정보조부 |
| 19 | **계정과목집계표** | `Act04_Tab_GenLedger` | 1151 | 계정원장 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/act/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Act01_AccountCode` | Act01_AccountCode 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Act02_Journal` | Act02_Journal 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Act03_JournalDtl` | Act03_JournalDtl 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Act04_GenLedger` | Act04_GenLedger 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Act06_JournalTmp` | Act06_JournalTmp 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Act08_JournalUpload` | Act08_JournalUpload 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Act09_AccountNum` | Act09_AccountNum 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Act10_ReprAccount` | Act10_ReprAccount 비즈니스 로직 및 RPC 서비스 처리 |
| 9 | `Act11_TrMap` | Act11_TrMap 비즈니스 로직 및 RPC 서비스 처리 |
| 10 | `Act12_JournalMap` | Act12_JournalMap 비즈니스 로직 및 RPC 서비스 처리 |
| 11 | `Act13_RealAccountMap` | Act13_RealAccountMap 비즈니스 로직 및 RPC 서비스 처리 |
| 12 | `Act14_Link` | Act14_Link 비즈니스 로직 및 RPC 서비스 처리 |
| 13 | `Act15_CloseCheck` | Act15_CloseCheck 비즈니스 로직 및 RPC 서비스 처리 |
| 14 | `Act80_RelateAppr` | Act80_RelateAppr 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/act/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `act01_account_code.xml` | `act01_account_code` 테이블 관련 쿼리 매핑 |
| 2 | `act02_journal.xml` | `act02_journal` 테이블 관련 쿼리 매핑 |
| 3 | `act03_journal_dtl.xml` | `act03_journal_dtl` 테이블 관련 쿼리 매핑 |
| 4 | `act04_gen_ledger.xml` | `act04_gen_ledger` 테이블 관련 쿼리 매핑 |
| 5 | `act06_journal_tmp.xml` | `act06_journal_tmp` 테이블 관련 쿼리 매핑 |
| 6 | `act08_journal_upload.xml` | `act08_journal_upload` 테이블 관련 쿼리 매핑 |
| 7 | `act09_account_num.xml` | `act09_account_num` 테이블 관련 쿼리 매핑 |
| 8 | `act10_repr_account.xml` | `act10_repr_account` 테이블 관련 쿼리 매핑 |
| 9 | `act11_tr_map.xml` | `act11_tr_map` 테이블 관련 쿼리 매핑 |
| 10 | `act12_journal_map.xml` | `act12_journal_map` 테이블 관련 쿼리 매핑 |
| 11 | `act13_real_account_map.xml` | `act13_real_account_map` 테이블 관련 쿼리 매핑 |
| 12 | `act14_link.xml` | `act14_link` 테이블 관련 쿼리 매핑 |
| 13 | `act15_close_check.xml` | `act15_close_check` 테이블 관련 쿼리 매핑 |
| 14 | `act80_relate_appr.xml` | `act80_relate_appr` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `act01_account_code` | 계정코드 | 17 | `act01_account_code_id` |
| 2 | `act01_account_code_fss` | - | 12 | `act01_account_code_fss_id` |
| 3 | `act02_journal` | 분개장 | 17 | `act02_journal_id` |
| 4 | `act03_journal_dtl` | 분개장-분개상세 | 13 | `act03_journal_dtl_id` |
| 5 | `act04_gen_ledger` | 계정원장 | 12 | `act04_gen_ledger_id` |
| 6 | `act05_gen_ledger_close` | 계정원장(결산마감)-월말기준 | 13 | `act05_gen_ledger_close_id` |
| 7 | `act06_journal_tmp` | 임시분개장 | 11 | `act06_journal_tmp_id` |
| 8 | `act07_gen_ledger_closetmp` | 계정원장(가결산-결산전 재무제표 조회용)-월말기준 | 13 | `act07_gen_ledger_closetmp_id` |
| 9 | `act08_journal_upload` | 분개장-업로드자료 | 12 | `act08_journal_upload_id` |
| 10 | `act09_account_num` | 결산회기관리 | 6 | `act09_account_num_id` |
| 11 | `act10_repr_account` | 대표계정코드 | 7 | `act10_repr_account_id` |
| 12 | `act11_tr_map` | 거래맵핑 | 8 | `act11_tr_map_id` |
| 13 | `act12_journal_map` | 분개맵핑 | 10 | `act12_journal_map_id` |
| 14 | `act13_real_account_map` | 실계정맵핑 | 6 | `act13_real_account_map_id` |
| 15 | `act14_link` | 이익제공 계정코드 연결 | 5 | `act14_link_id` |
| 16 | `act15_close_check` | 마감검증 체크항목별 사용여부 | 15 | `act15_close_check_id` |
| 17 | `act80_relate_appr` | 상신문서 연결 | 4 | `act80_relate_appr_id` |
| 18 | `act90_journal_back` | 분개장(백업) | 20 | `act90_journal_back_id` |
| 19 | `act91_journal_dtl_back` | 분개장 상세(백업) | 16 | `act91_journal_dtl_back_id` |
| 20 | `act92_journal_tmp_back` | 분개장 임시(백업) | 14 | `act92_journal_tmp_back_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **19개**
- **UI 컴포넌트 수**: 총 52개 (Tab/Page: 19개, Lookup/Popup/기타: 33개)
- **서버 서비스 클래스 수**: **14개**
- **MyBatis 매퍼 XML 수**: **14개**
- **DB 테이블 수**: **20개**
