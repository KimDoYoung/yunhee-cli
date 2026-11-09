# `yunhee agent` 사용법 가이드 (`yunhee-agent-사용법.md`)

`yunhee` 에이전트 모드는 로컬 LLM(`qwen2.5-coder:14b`)과 임베딩 모델(`bge-m3`), 그리고 사전 학습된 **TOBE 카탈로그 스냅샷(`.yunhee/tobe_catalog.json`) + ChromaDB 벡터 스토어(`yunhee_tobe_kb`)**를 결합하여 상용 AI 토큰 소모 없이 TOBE/AS-IS 코드베이스와 DB를 자율 탐색·분석하는 로컬 에이전트입니다.

---

## 1. 진입 및 실행 방법 (2가지 모드)

> **실행 위치 무관**: `yunhee-cli` 폴더에서 실행하든 작업 대상 프로젝트(`AssetERP`) 폴더에서 실행하든 `.env.local`의 `YUNHEE_TOBE_SRC_DIR`을 자동으로 참조하므로 **어느 폴더에서 실행해도 100% 동일하게 동작**합니다.

### ① 대화형 REPL 모드 (`yunhee`)
서브커맨드 없이 `yunhee`만 입력하면 멀티턴 대화와 슬래시(`/`) 명령어를 사용할 수 있는 대화형 프롬프트(`you> `)로 진입합니다.
```bash
yunhee
```

### ② 단발성 CLI 에이전트 모드 (`yunhee agent` / `yunhee ask -a`)
터미널에서 한 줄 명령으로 에이전트에게 질문하고 즉시 마크다운 표/답변을 출력받습니다.
```bash
yunhee agent "1002 화면의 파일명은?"
yunhee agent "'법규분류 수정' 타이틀을 갖는 모달을 찾아줘"
yunhee ask -a "grid의 column 중 체크박스이면서 제목이 한글 3글자인 화면 찾아줘"
```

---

## 2. TOBE 사전 학습 및 관리 명령어 (`rag-*`)

에이전트가 TOBE 전체 화면(1,355개+), 메뉴번호(`#1001`~), 모달, 그리드 컬럼, 버튼, API, 백엔드 파일을 0.1초 만에 파악할 수 있도록 학습시키는 명령어입니다.

| 명령어 | 주요 옵션 | 설명 |
| :--- | :--- | :--- |
| **`yunhee rag-index`** | `--no-vector`<br>`--reset`<br>`--reset-all` | **[기본: 증분 학습]** TOBE 소스를 스캔해 `.yunhee/tobe_catalog.json`과 `docs/to-be/`를 갱신하고, 변경/추가된 화면만 ChromaDB(`yunhee_tobe_kb`)에 임베딩(`upsert`)하며 삭제된 파일 벡터는 자동 제거(`delete`)합니다.<br>- `--no-vector`: 임베딩 없이 JSON 스냅샷과 마크다운만 고속 갱신 (~6초) |
| **`yunhee rag-status`** | `--json` | **[학습 상태 점검]** 마지막 학습 시각, 인덱싱된 화면/벡터 건수, 마지막 학습 이후 수정·추가·삭제된 TOBE 파일(`Stale`) 건수를 확인합니다. |
| **`yunhee rag-search "<질의>"`** | `-n <개수>`<br>`--json` | **[학습 카드 직접 조회]** 화면번호(`1002`), 메뉴명, 컴포넌트명 또는 키워드로 에이전트가 소환할 학습 카드를 즉시 확인합니다. |
| **`yunhee rag-reset`** | `--all`<br>`--no-reindex` | **[완전 초기화 후 재학습]** ChromaDB `yunhee_tobe_kb` 컬렉션과 스냅샷을 완전히 삭제한 뒤 처음부터 다시 학습합니다 (`--all` 지정 시 수동 노하우 컬렉션 `yunhee_knowledge`까지 초기화). |

---

## 3. `yunhee agent` 안에서 줄 수 있는 자연어 명령어·질문 유형

별도로 `"TOBE에서"`, `"프론트엔드/백엔드"`, `"화면번호와 메뉴명을 알려줘"`라고 지정하지 않아도, **기본적으로 TOBE 전체(FE+BE+메뉴번호 통합)**를 대상으로 탐색하며 결과는 **`[화면번호(#), 메뉴명, 컴포넌트명, 파일 경로, 일치 상세]`** 마크다운 표로 정리해 줍니다.

### 3.1 화면번호 · 메뉴명 · 컴포넌트 단건 조회 (즉시 응답)
질문에 4자리 화면번호(`1002`), 메뉴명, 컴포넌트명, API URL, 테이블명이 포함되면 **하이브리드 Prefetch RAG**가 학습 카드를 즉시 주입하거나 `lookup_tobe` 도구를 호출하여 1~2초 내에 답변합니다.

```text
you> 1002 화면의 파일명은?
you> 1029 화면에서 호출하는 API와 연결된 백엔드(Controller, Service, Mapper) 파일을 알려줘.
you> 업무별 문서작성 화면의 하위 컴포넌트와 참조하는 DB 테이블은?
you> Ics01_Edit_ClassTree 모달을 여는 상위 탭 화면과 화면번호를 알려줘.
you> /api/v1/ics/class-tree API를 호출하는 화면은 어디야?
```

### 3.2 모달 · 그리드 컬럼 · 검색바 · 버튼 복합 조건 탐색 (`execute_python`)
정규식, 글자 수, 컬럼 타입, 개수 등 복합 조건을 자연어로 질문하면 에이전트가 스스로 Python 스크립트(`from yunhee.tools.trace.screen_catalog import iter_screens`)를 작성·실행(0.25초)하여 조건에 맞는 모든 화면을 찾아 표로 보여줍니다.

- **모달(Modal / LookupModal / EditModal) 조건 검색** *(부모 화면에서 `titleName` 등으로 동적 전달하는 모달 타이틀까지 포함)*:
  ```text
  you> '법규분류 수정' 타이틀을 갖는 모달을 찾아줘.
  you> 제목이 '계정과목'인 모달을 찾아줘.
  you> 모달 창이 2개 이상 있는 화면을 찾아줘.
  ```
- **그리드 컬럼(`grid_cols`) 타입 · 라벨 · 글자수 · 폭 조건 검색**:
  ```text
  you> grid의 column 중 체크박스이면서 제목이 한글 3글자인 화면 찾아줘.
  you> 그리드 컬럼 제목에 '수수료'가 들어가고 타입이 숫자인 화면 찾아줘.
  you> 그리드 컬럼 개수가 15개 이상인 화면 목록을 알려줘.
  ```
- **조회 조건(`SearchBar`) · 버튼(`buttons`) · 페이지 스타일(`page_style`) 검색**:
  ```text
  you> 조회 조건(SearchBar)에 '펀드'가 들어가는 화면을 찾아줘.
  you> 버튼 중에 '상위등록'과 '하위등록'이 있는 화면을 찾아줘.
  you> 페이지 스타일이 SGP인 화면들을 찾아줘.
  ```
- **AS-IS 원본 기준 검색이 필요할 때**:
  - 질문에 `"AS-IS에서"` 또는 `"원본에서"`라고 명시하면 `iter_screens(side="asis")`로 전환하여 탐색합니다.

### 3.3 DB 스키마(DDL) · 스토어드 함수 소스 · 안전 SQL 실행 (`run_sql`, `get_db_definition`)
에이전트가 PostgreSQL 스키마 스냅샷 및 읽기 전용 세션을 통해 DB 구조와 데이터를 직접 확인합니다.

```text
you> sys01_company 테이블의 DDL 스키마를 보여줘.
you> f_ast_class_tree_nm DB 함수의 본체 소스코드를 보여줘.
you> sys01_company 테이블에서 최근 5건만 SELECT 해줘.
you> ics01로 시작하는 테이블 목록과 건수를 확인해줘.
```

### 3.4 파일 열람 · 코드 검색 · 서버 에러 분석 (`read_file`, `grep_search`, `read_recent_errors`)
```text
you> frontend/src/pages/dcr/Dcr01_Tab_DcrUser.tsx 파일의 1줄부터 80줄까지 읽어줘.
you> frontend/src/pages/ics 폴더에 어떤 파일들이 있는지 목록을 보여줘.
you> 최근 서버 로그에서 발생한 에러(WARN/ERROR)들을 요약해줘.
```

### 3.5 규칙(L1) 및 노하우(L2) 장기 기억 저장 (`save_rule`, `save_knowledge`)
```text
you> "모든 TOBE DTO는 Java 21 Record로 작성한다"는 규칙을 프로젝트 메모리에 저장해줘.
you> "SysRoleMapper 삭제 시 sys04_user_role을 먼저 삭제해야 외래키 에러가 나지 않는다"는 노하우를 지식 베이스에 저장해줘.
you> 이전에 저장한 외래키 삭제 관련 노하우를 검색해줘.
```

---

## 4. 대화형 REPL(`yunhee`) 전용 슬래시(`/`) 명령어

`yunhee` 대화형 프롬프트(`you> `)에서는 자연어 질문 외에도 아래 슬래시 명령어를 사용할 수 있습니다.

### 4.1 내장 슬래시 명령어
| 슬래시 명령어 | 설명 |
| :--- | :--- |
| `/help` | 사용 가능한 슬래시 명령어 및 단축키 도움말 출력 |
| `/자기소개` (`/intro`) | `yunhee` 에이전트 소개 및 보유 능력 안내 |
| `/tools` | 에이전트가 내부적으로 호출할 수 있는 전체 도구(18종) 스키마 목록 표시 |
| `/config` | 현재 설정(`WORK_DIR`, `TOBE_SRC_DIR`, `ASIS_SRC_DIR`, DB, Ollama 등) 조회 |
| `/changelog` | 버전별 변경 이력 조회 |
| `/init` | 현재 폴더를 `yunhee` 프로젝트로 등록/갱신 (`.yunhee/project.json`) |
| `/memory` | `.yunhee/memory.md` 핵심 규칙 조회 (`/memory add <규칙>`으로 즉시 추가) |
| `/knowledge <검색어>` | ChromaDB에 저장된 수동 노하우(`yunhee_knowledge`) 즉시 검색 |
| `/session` | 현재 대화 세션의 마크다운/JSONL 로그 파일 경로 확인 |
| `/out <화면코드>` | 지정 화면의 마이그레이션 종합 마크다운 명세서 자동 생성 |
| `/out:pdf <화면코드>` | 지정 화면의 기술 명세서를 Gotenberg 기반 PDF로 발간 |
| `/out:pdf session` | 현재까지의 에이전트 대화 기록 전체를 PDF 문서로 발간 |
| `/clear` | 멀티턴 대화 히스토리 초기화 (컨텍스트 토큰 비우기) |
| `/exit` (`/quit`) | REPL 종료 (`Ctrl+D`와 동일, 추론 중단은 `ESC` 더블탭) |

### 4.2 하이브리드 슬래시 명령어 (실행 결과를 대화 맥락에 자동 주입)
대화 도중 아래 명령어를 `/`로 실행하면, **CLI 실행 결과를 화면에 보여줌과 동시에 현재 에이전트 대화 컨텍스트에 자동 첨부**하므로 이어서 바로 후속 질문을 할 수 있습니다.

- `/rag-index` : TOBE 프로젝트 증분 학습 실행 후 결과를 대화에 주입
- `/rag-status` : 현재 TOBE RAG 학습 상태 및 미반영 파일 점검
- `/rag-search <질의>` : 특정 화면번호/메뉴/키워드 학습 카드를 조회해 대화 맥락에 주입
- `/rag-reset` : TOBE RAG 초기화 후 재학습
- `/screen-desc <화면번호들> [--format=md|json]` : 쉼표(`,`)·공백(` `)으로 구분한 복수의 화면번호(예: `1002,1029, 1085`)와 관련된 모든 정보(메뉴명·파일명·팝업·하위 컴포넌트·그리드·버튼·API·SQL·테이블·ASIS)를 조회해 대화에 주입
- `/table <테이블명>` : DBML 테이블 스키마를 조회해 현재 대화에 주입
- `/outline <파일경로>` : Java/TSX/XML 클래스·메서드 시그니처를 추출해 대화에 주입
- `/sql "<SELECT문>"` : 읽기 전용 SQL 실행 결과를 대화에 주입
- `/log errors` (또는 `/log tail`, `/log trace <id>`) : 서버 로그 분석 결과를 대화에 주입
- `/api GET /api/v1/...` : API 스모크 테스트 결과를 대화에 주입
- `/events <ASIS화면.java>` : AS-IS 화면 이벤트/Grid Spec/버튼 추출 결과를 대화에 주입
- `/analysis <하위명령>` : `analysis screen`, `analysis sql`, `analysis callers` 등의 결과를 대화에 주입
- `/run "<셸명령>"` : 빌드/테스트 등 외부 명령 실행 결과를 대화에 주입

---

## 5. `execute_python`에서 활용되는 `ScreenRecord` 주요 속성 참고

에이전트가 `execute_python`으로 복합 조건 스크립트를 작성할 때 사용하는 `iter_screens()`의 각 `ScreenRecord`(`s`) 객체는 다음 속성을 가집니다:

| 속성 / 메서드 | 타입 | 설명 및 예시 |
| :--- | :--- | :--- |
| `s.menu_no` | `str` | 4자리 화면(메뉴) 번호 (예: `'1002'`, `'1029'`, 없으면 `''`) |
| `s.menu_path` | `str` | 전체 메뉴 경로 (예: `'문서작성 > 01. 문서작성 > 업무별 문서작성'`) |
| `s.menu_name` | `str` | 말단 메뉴명 (예: `'업무별 문서작성'`) |
| `s.name` | `str` | 화면/컴포넌트 이름 (예: `'Dcr01_Tab_DcrUser'`, `'Ics01_Edit_ClassTree'`) |
| `s.role` | `str` | 역할 분류 (`'Tab'`, `'TabPage'`, `'Grid'`, `'Lookup'`, `'Edit'`, `'Popup'`, `'Move'`) |
| `s.page_style` | `str` | 페이지/모달 스타일 SID (예: `'SG'`, `'SGP'`, `'TG'`, `'MF'`) |
| `s.file` | `str` | 프론트엔드 상대 경로 (예: `'frontend/src/pages/dcr/Dcr01_Tab_DcrUser.tsx'`) |
| `s.opening_tabs` | `list[str]` | 팝업/하위 컴포넌트를 여는 상위 `_Tab_` 화면 목록 |
| `s.child_components` | `list[str]` | 이 화면이 import하여 사용하는 하위 컴포넌트/모달 목록 |
| `s.search_fields` | `list[str]` | 조회바(`SearchBar.Field`) 라벨 목록 |
| `s.modals` | `list[ModalInfo]` | 모달 목록 (`m.kind`, `m.title`, `m.line`) — 부모 전달 동적 타이틀 포함 |
| `s.grid_cols` | `list[GridCol]` | 그리드 컬럼 목록 (`c.col_type`, `c.field`, `c.label`, `c.width`) |
| `s.buttons` | `list[str]` | 화면 내 버튼 라벨 목록 |
| `s.apis` | `list[str]` | 호출하는 HTTP API 목록 (예: `['GET /api/v1/dcr/...']`) |
| `s.backend_files` | `list[str]` | 연결된 백엔드 `Controller`, `Service`, `Mapper.xml` 파일 경로 목록 |
| `s.sql_ids` | `list[str]` | 연결된 MyBatis SQL ID 목록 |
| `s.tables` | `list[str]` | 매퍼 XML이 참조하는 DB 테이블 목록 |
| `s.text` (`s.raw_text`) | `str` | 파일 전체 소스 텍스트 (스냅샷 로드 시 필요할 때만 지연 읽기) |
| `s.format_hit(detail)` | `str` | `#화면번호 \| 메뉴명 \| 컴포넌트명 \| 파일경로 \| 일치상세` 표준 행 문자열 반환 |
