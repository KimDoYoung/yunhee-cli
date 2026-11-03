# scm (형상관리 / 시스템 개발의뢰(SR)) 도메인 주요 업무 리스트 및 분석표

> **문서 목적**: AssetERP의 `scm` (형상관리 / 시스템 개발의뢰(SR)) 도메인에 존재하는 주요 업무를 식별하고, 업무 영역별로 체계적으로 분류한 분석 리스트입니다.  
> **분석 대상 소스**: ASIS GXT 소스 (`myApp/client/vi/scm/*`, `myApp/server/scm/*`), MyBatis 매퍼 XML, PostgreSQL DB 스키마 (`scm##_*`), `sys06_menu`.

---

## 1. 업무 영역별 분류 요약

`scm` 도메인은 **형상관리 / 시스템 개발의뢰(SR)** 관련 비즈니스 로직을 수행하며, 다음과 같이 세부 업무 영역으로 구성됩니다.

| 영역 코드 | 업무 영역 | 주요 역할 및 설명 | 대상 화면 및 모듈 수 |
|:---:|:---|:---|:---:|
| **SCM-01** | **내부 컴포넌트/탭** | 내부 컴포넌트/탭 관련 화면 및 처리 모듈 | 1개 화면 |
| **SCM-02** | **배포관리** | 배포관리 관련 화면 및 처리 모듈 | 1개 화면 |
| **SCM-03** | **시스템 개발** | 시스템 개발 관련 화면 및 처리 모듈 | 4개 화면 |
| **SCM-04** | **프로그램 관리** | 프로그램 관리 관련 화면 및 처리 모듈 | 1개 화면 |

---

## 2. 세부 주요 업무 리스트 (전수 나열)

### SCM-01. 내부 컴포넌트/탭
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 1 | **배포처리** | `Scm13_Page_Deploy` | - | 배포처리 기능 처리 |

### SCM-02. 배포관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 2 | **배포처리** | `Scm13_Tab_Deploy` | 1266 | 프로그램 배포처리 |

### SCM-03. 시스템 개발
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 3 | **시스템 개발 관리** | `Scm01_Tab_DevMng` | 1262 | 시스템 개발 관리 (관리자용) |
| 4 | **시스템 개발 의뢰** | `Scm01_Tab_Sr` | 1261 | 시스템 개발 의뢰 |
| 5 | **시스템 개발** | `Scm10_Tab_Dev` | 1263 | 시스템 개발 (개발자용) |
| 6 | **시스템 QA/UAT** | `Scm11_Tab_DevTest` | 1264 | 시스템 품질검사 및 사용자 테스트 결과반영 test |

### SCM-04. 프로그램 관리
| 번호 | 업무명 | GXT 화면 컴포넌트 | 메뉴 번호 | 업무 설명 및 비고 |
|:---:|:---|:---|:---:|:---|
| 7 | **프로그램 관리** | `Scm30_Tab_Program` | 1265 | 프로그램 소스 및 버전관리 |

---

## 3. 관련 서버 모듈 및 매퍼 현황

### 서버 서비스 클래스 (`server/scm/`)
| 번호 | 서버 클래스 | 관련 역할 및 설명 |
|:---:|:---|:---|
| 1 | `Scm01_Sr` | Scm01_Sr 비즈니스 로직 및 RPC 서비스 처리 |
| 2 | `Scm02_SrApprStep` | Scm02_SrApprStep 비즈니스 로직 및 RPC 서비스 처리 |
| 3 | `Scm03_ExpectProgram` | Scm03_ExpectProgram 비즈니스 로직 및 RPC 서비스 처리 |
| 4 | `Scm10_Dev` | Scm10_Dev 비즈니스 로직 및 RPC 서비스 처리 |
| 5 | `Scm11_DevStep` | Scm11_DevStep 비즈니스 로직 및 RPC 서비스 처리 |
| 6 | `Scm12_DevStepRule` | Scm12_DevStepRule 비즈니스 로직 및 RPC 서비스 처리 |
| 7 | `Scm13_DevProgram` | Scm13_DevProgram 비즈니스 로직 및 RPC 서비스 처리 |
| 8 | `Scm30_Program` | Scm30_Program 비즈니스 로직 및 RPC 서비스 처리 |

### 관련 MyBatis 매퍼 XML (`server/scm/mapper/`)
| 번호 | 매퍼 파일 | 주요 SQL 처리 대상 |
|:---:|:---|:---|
| 1 | `scm01_sr.xml` | `scm01_sr` 테이블 관련 쿼리 매핑 |
| 2 | `scm02_sr_appr_step.xml` | `scm02_sr_appr_step` 테이블 관련 쿼리 매핑 |
| 3 | `scm03_expect_program.xml` | `scm03_expect_program` 테이블 관련 쿼리 매핑 |
| 4 | `scm10_dev.xml` | `scm10_dev` 테이블 관련 쿼리 매핑 |
| 5 | `scm11_dev_step.xml` | `scm11_dev_step` 테이블 관련 쿼리 매핑 |
| 6 | `scm12_dev_step_rule.xml` | `scm12_dev_step_rule` 테이블 관련 쿼리 매핑 |
| 7 | `scm13_dev_program.xml` | `scm13_dev_program` 테이블 관련 쿼리 매핑 |
| 8 | `scm30_program.xml` | `scm30_program` 테이블 관련 쿼리 매핑 |

### 관련 데이터베이스 테이블 (`LOCAL_DB`)
| 번호 | 테이블명 | 테이블 설명 (코멘트) | 컬럼 수 | PK |
|:---:|:---|:---|:---:|:---|
| 1 | `scm01_sr` | 시스템 개발의뢰 (SR) | 20 | `scm01_sr_id` |
| 2 | `scm02_sr_appr_step` | 시스템 개발의뢰 결재단계 정보 | 10 | `scm02_sr_appr_step_id` |
| 3 | `scm03_expect_program` | 예상프로그램 | 3 | `scm03_expect_program_id` |
| 4 | `scm10_dev` | 시스템 개발 | 7 | `scm10_dev_id` |
| 5 | `scm11_dev_step` | 개발단계 정보 | 10 | `scm11_dev_step_id` |
| 6 | `scm12_dev_step_rule` | 개발단계규칙 기본설정 | 3 | `scm12_dev_step_rule_id` |
| 7 | `scm13_dev_program` | 개발 프로그램 및 배포정보 | 10 | `scm13_dev_program_id` |
| 8 | `scm30_program` | 프로그램 | 11 | `scm30_program_id` |

---

## 4. 요약 통계

- **총 세부 업무 화면**: **7개**
- **UI 컴포넌트 수**: 총 41개 (Tab/Page: 7개, Lookup/Popup/기타: 34개)
- **서버 서비스 클래스 수**: **8개**
- **MyBatis 매퍼 XML 수**: **8개**
- **DB 테이블 수**: **8개**
