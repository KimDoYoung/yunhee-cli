# 👩‍💻 yunhee AI 에이전트 종합 안내서 (도움말)

> **"저는 절약정신이 투철한 한국여자이고 이름은 'yunhee'입니다."**
> 
> `yunhee`는 상용 vibe-coding 도구(Claude CLI, Antigravity CLI, Gemini CLI 등)의 **토큰 사용량을 절약**하기 위해 만든 독자적인 로컬 agent CLI이자 정적 분석 도구 모음입니다.

---

## 1. yunhee의 정체성과 사명 (Identity & Mission)

### 1.1 범용 에이전트와의 차이점
`yunhee`는 `agy`(Antigravity), Claude CLI, Gemini CLI와 같은 일반 코딩 목적의 범용(General-purpose) 에이전트가 아닙니다.

수백 페이지 규모의 자산운용 SaaS ERP인 **AssetERP 시스템을 레거시(GWT 2.9 / GXT 4.0.2 / Java 8 / PostgreSQL)에서 현대적 프레임워크(Spring Boot / React 18 / Java 21 / MyBatis)로 안전하게 전환하고, 검증하고, 새로 생긴 프레임워크의 테스트 및 문서화 등에 특화된 전문 도메인 에이전트**입니다.

### 1.2 상용 AI와의 협업 구조 (토큰 절약 공작소)
```
┌────────────────────────────────────────────────────────┐
│           [yunhee] 전환 전문 로컬 도구 & 에이전트        │
│  - AssetERP 도메인 지식 & GXT/Spring 정적 분석기 내장    │
│  - DB 스냅샷, trace, compare, porting, outline 등 수행  │
│  - 수만 토큰의 레거시 잡음을 100~300 토큰의 팩트로 압축  │
└───────────────────────────┬────────────────────────────┘
                            │ 초압축 컨텍스트 전달 (토큰 절약)
                            ▼
┌────────────────────────────────────────────────────────┐
│       [agy / Claude CLI / Gemini CLI] 범용 코딩 에이전트 │
│  - 고성능 추론 능력을 바탕으로 실제 React/Spring 코드 작성│
│  - 리팩토링, 복잡한 비즈니스 로직 이식 및 에러 수정     │
└────────────────────────────────────────────────────────┘
```

---

## 2. 새 프로젝트 시작 가이드 (`mkdir project1` 시나리오)

새로운 마이그레이션 작업 폴더를 만들고 진입했을 때의 표준 동작 흐름입니다.

```bash
mkdir project1
cd project1
yunhee
```

### 2.1 `.yunhee` 폴더 부재 감지 및 안내
프로젝트 폴더에 `.yunhee/` 디렉터리가 없으면, REPL 시작 시 자동으로 등록 필요 상태(`missing`)를 감지하고 안내합니다:

```text
이 폴더는 아직 yunhee 프로젝트로 등록되지 않았습니다. /init 을 실행하여 프로젝트 설정 및 필요한 폴더를 생성하세요.
```

### 2.2 `/init` (또는 `yunhee init`) 실행 시 생성되는 필수 요소
REPL 대화창에서 `/init`을 입력하거나 터미널에서 `yunhee init`을 실행하면 작업 디렉터리에 다음 요소들이 자동으로 구성됩니다:

| 생성 파일 / 디렉터리 | 역할 및 설명 |
| :--- | :--- |
| **`.yunhee/project.json`** | 프로젝트 메타데이터 (프로젝트명, 생성/수정 일시, yunhee 버전) |
| **`.yunhee/mcp.json`** | 기본 MCP 도구 연동 설정 (`time`, `fetch` 서버 기본 등록) |
| **`.yunhee/memory.md`** | 에이전트의 영구 기억 헌법 (프로젝트별 특별 코딩 규칙 보관) |
| **`.yunhee/sessions/`** | 대화 세션 기록(`.md`, `.jsonl`) 보관 디렉터리 |
| **`.yunhee/runs/`** | `yunhee run` 외부 명령어 실행 로그 격리 보관 디렉터리 |
| **`.yunhee/.gitignore`** | 대화록(`sessions/`) 및 실행 로그(`runs/`)의 git 커밋 자동 차단 |

### 2.3 기초 데이터 및 색인 준비 (`data-setup.sh`)
새 프로젝트 디렉터리(`project1`)에서 `yunhee init` 완료 후, 필요한 DB 카탈로그 스냅샷(`make-dbml`, `index-db`) 및 소스 호출경로 색인(`index-src`, `tools/parse_mapper.py`)을 손쉽게 준비할 수 있도록 `yunhee-cli/data-setup.sh` 스크립트를 제공합니다.

```bash
# yunhee-cli 디렉터리에서 실행하거나 경로 지정 실행
~/work/yunhee-cli/data-setup.sh
```
* **대화형 메뉴**:
  - `1. 현재 상태`: 필수 환경변수 및 준비된 스냅샷/색인 현황 출력
  - `2. db 관련 조사된 자료들 삭제`: DBML, 스키마 JSON, `docs/as-is/db` 제거
  - `3. src 관련 조사된 자료들 삭제`: `menus.tsv`, `docs/as-is/src`, 매퍼 SQLite 캐시 초기화
  - `4. db 관련 자료들 준비`: `yunhee make-dbml` 및 `yunhee index-db` 자동 실행
  - `5. src 관련 자료들 준비`: `yunhee index-src --menus-from-db` 및 `tools/parse_mapper.py` 자동 실행
  - `6. 모든 자료들 삭제`: 2번 + 3번 전체 삭제
  - `7. 모든 자료들 재 설치`: 완전 삭제 후 4번 + 5번 신규 재구축
  - `99. 도움말` / `0. 종료`
* 비대화형 실행 지원: `./data-setup.sh 1` (상태), `./data-setup.sh 4` (DB 준비), `./data-setup.sh 5` (SRC 준비) 등

---

## 3. `.env.yunhee` 환경 설정 탐색 및 계층형(Cascading) 로딩

빈 디렉터리(`project1`)를 만들 때마다 매번 DB 접속 URL, 비밀번호, Ollama 설정, ASIS/TOBE 소스 경로를 복사-붙여넣기 할 필요가 없습니다. `yunhee`는 **전역 기본값 로드 ➔ 로컬 오버라이드**의 계층형 설정을 지원합니다.

### 3.1 탐색 우선순위

1. **1순위 (로컬 프로젝트 최우선)**:
   * `project1/.env.yunhee` (또는 `project1/.env.local`, `project1/.yunhee/.env.yunhee`)
2. **2순위 (상위 조상 디렉터리)**:
   * `project1`의 상위 부모 폴더를 거슬러 올라가며 탐색 (`.git` 저장소 루트까지)
3. **3순위 (사용자 홈 전역 설정)**:
   * `~/.yunhee/.env.yunhee` (또는 `~/.yunhee/.env.local`)
   * 개발자 PC 전체에서 공유할 공통 DB URL, Ollama, ASIS_SRC_DIR, TOBE_SRC_DIR을 저장하는 가장 권장되는 위치입니다.
4. **4순위 (yunhee 패키지 설치 위치)**:
   * `YUNHEE_DIR/.env.yunhee` (설치/개발 저장소의 기본 설정 fallback)

### 3.2 계층형 로딩 (Cascading) 동작 방식
* **1단계 (전역 로드)**: `~/.yunhee/.env.yunhee`를 먼저 로드하여 개발자 PC의 공통 설정을 확보합니다.
* **2단계 (로컬 오버라이드)**: `project1` 내에 `.env.yunhee`가 존재하면, 해당 파일에 정의된 항목만 기존 설정을 덮어씁니다(`load_dotenv(override=True)`).
* **효과**: 빈 프로젝트(`project1`)에 아무런 `.env.yunhee`가 없어도 전역 설정 덕분에 `yunhee table`, `yunhee outline`, `yunhee trace-*`, `yunhee page-style`이 즉시 100% 정상 작동합니다.

---

## 4. yunhee의 2가지 핵심 동작 모드

### 4.1 명령형 서브커맨드 방식 (CLI Tools)
* **호출**: `yunhee <command> [args...]`
* **주요 명령어**:
  * `outline <경로>`: 소스 코드 클래스/메서드 시그니처와 줄 번호 추출 (전체 코드 읽기 방지)
  * `table <테이블명>`: 오프라인 스키마 스냅샷에서 지정 테이블 DBML 추출
  * `cat <파일:줄범위>`: 지정 파일의 특정 줄 범위만 핀포인트 출력
  * `run "<명령>"`: 빌드/테스트 명령 실행, 성공 시 1줄 / 실패 시 에러 원문 압축 요약
  * `api <METHOD> <PATH>`: 자동 로그인 세션 기반 API 스모크 테스트 및 실행 SQL 요약
  * `compare <API> <SQL>`: TOBE API 결과와 AS-IS SQL 결과 행 수 및 화면 그리드 컬럼 커버리지 대조
  * `sql-check --tobe <매퍼>`: 대상 DB(`asseterpdb`)에서 매퍼 동적 SQL `psql EXPLAIN` 사전 검증
  * `page-style <화면>`: 9대 표준 화면 스타일(SID) 판별 및 머리 주석 검증
  * `trace-*`: 메뉴 트리, 화면, 테이블, 컬럼, 상태 전이 호출 체인 팩트시트 추출
* **사용 주체**: 터미널 개발자 직접 실행 또는 **상용 AI Agent(agy, Claude CLI)의 Tool-Calling 인터페이스**.

### 4.2 자체 대화형 에이전트 REPL 방식 (Autonomous Agent Harness)
* **호출**: 인자 없이 `yunhee` 단독 실행 (또는 `yunhee chat-cmd`)
* **특징**:
  * `you> ` 대화형 프롬프트 제공
  * 로컬 LLM(`qwen2.5-coder:14b`) 기반 자율 `AgentLoop` 가동
  * 파일 탐색/수정(`core_fs`), 안전 DB 조회(`run_sql`), 셸 실행(`run_command`) 등 자율 도구 호출
  * 세션 로깅(`.yunhee/sessions/<id>.md`) 및 기억 보관(`.yunhee/memory.md`)
* **자기소개 확인**:
  * REPL 대화창에서 `자기소개?` 또는 `/자기소개`, `/intro` 입력 시 즉시 정체성 마크다운 출력 (터미널에서는 `yunhee "자기소개?"` 또는 `yunhee intro` 실행).

---

## 5. REPL 슬래시 커맨드 요약표

| 슬래시 커맨드 | 설명 |
| :--- | :--- |
| `/help` | REPL 사용법 및 도움말 확인 |
| `/자기소개`, `/intro` | yunhee 에이전트 정체성 및 전문 영역 소개 (`자기소개?` 도 지원) |
| `/init` | 현재 작업 디렉터리를 yunhee 프로젝트로 등록 및 필수 폴더/파일 초기화 |
| `/config` | 현재 활성화된 설정값(Work Dir, TOBE/ASIS 경로, 브랜치, DB 등) 조회 |
| `/changelog` | 버전별 릴리즈 변경 이력 조회 |
| `/tools` | 에이전트가 호출 가능한 도구 목록 및 스키마 확인 |
| `/session` | 현재 세션 기록 마크다운/JSONL 파일 경로 확인 |
| `/memory` | 프로젝트 영구 기억 규칙 조회 (`/memory add <규칙>` 으로 추가) |
| `/knowledge <검색어>` | ChromaDB 지식 베이스(bge-m3) 즉시 검색 |
| `/out:pdf <화면>` | Gotenberg 엔진 기반 공식 마이그레이션 기술 명세서 PDF 발간 |
| `/clear` | 대화 맥락 초기화 |
| `/exit`, `/quit` | REPL 종료 (단축키: `Ctrl+D`) |
