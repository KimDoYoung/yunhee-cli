# GEMINI.md

This file provides guidance to Gemini CLI, Google Antigravity, and other Gemini ecosystem agents when working with code in this repository.

## 프로젝트 개요

`yunhee`는 상용 vibe-coding 도구(Claude CLI, Antigravity CLI, Gemini CLI 등)의 **토큰 사용량을 절약**하기 위해 만드는 독자적인 로컬 agent CLI다. MCP 서버로 plug-in되는 형태가 아니라, 파일 읽기/검색/DB 조회 등 **실제 액션을 독립적으로 수행하는 CLI**를 지향한다. ("yunhee"는 절약 정신이 투철한 한국 여자의 대명사에서 따온 프로젝트명.)

- **로컬 모델 환경**: Ollama로 구동하며, `qwen2.5-coder:14b`(추론/분석)와 `bge-m3`(임베딩)을 사용한다. VRAM 16GB 제약으로 모델은 고정 1개만 사용하며, 모델 전환 기능은 의도적으로 제외했다.
- **실사용 배경**: legacy AssetERP(GWT 2.9/GXT 4.0.2/Java 8/PostgreSQL/MyBatis, 수백 page 규모 자산운용 SaaS ERP)의 ASIS 프레임워크를 TOBE 프레임워크(Spring Boot/React/MyBatis/PostgreSQL/Java 21)로 마이그레이션하는 vibe coding 작업에서, 페이지 변환마다 상용 AI CLI(gemini-cli, antigravity-cli, claude-cli)에 넘길 컨텍스트를 미리 압축·조립해 토큰 낭비(GXT 보일러플레이트 등)를 줄이는 것이 실질 목적이다.
- **설계 배경과 로드맵**: `docs/yunhee-cli-설계.md`, `docs/prepare 명령어 설계.md`, `docs/dbml-설계.md`에 상세히 기록되어 있다. 세션 작업 시작 시 참고할 것.

---

## 개발 명령어

이 프로젝트는 `uv` 기반 src layout이다. `./run.sh`를 실행하면 번호로 대화형 메뉴 선택이 가능하다 (1. run, 2. lint, 3. test, 4. install).

```bash
uv sync                          # 의존성 설치
uv run yunhee                    # REPL 진입 (서브커맨드 없이 실행 시 기본 동작)
uv run yunhee --version          # 버전 출력
uv run yunhee ask "질문"          # 단발성 질의
uv run yunhee vec "텍스트"        # bge-m3 임베딩 확인
uv run yunhee index "텍스트"      # chromadb에 텍스트 저장
uv run yunhee search "쿼리" -n 3  # 저장된 텍스트 중 유사 검색
uv run yunhee prepare <PageCode> # ASIS 페이지 요약 (prep과 동일). --force/--show/--delete/--two-stage/--no-grounding
uv run yunhee make-dbml LOCAL_DB # 환경변수의 PostgreSQL 스키마 → ./LOCAL_DB-dbml.md + data/schema/LOCAL_DB.json 스냅샷 (dbml과 동일). --output/-o, --schema(반복 가능)
uv run yunhee table act01_account_code 'sys0*'   # 스냅샷에서 해당 테이블만 DBML로 (stdout은 DBML만, 안내는 stderr)
uv run yunhee table --page ast01                 # 페이지 mapper가 참조하는 테이블 전부. --db로 스냅샷 선택
uv run yunhee run "mvn compile"                  # 외부 명령어 실행, 로그 격리 저장 및 Qwen 에러 요약 (exec과 동일)
uv run yunhee last-run                           # 가장 최근 실행 결과 및 요약 확인
uv run yunhee runs                               # 최근 실행 이력 테이블 출력
uv run yunhee agent-guide                        # 상용 AI 에이전트용 토큰 절약 지침서(Markdown) 출력

uv run tools/parse_mapper.py     # ASIS mapper XML → sqlite mapper_index 빌드 (prepare grounding 검증용)

uv run pytest                    # 테스트 실행
uv run ruff check .              # lint 검사

uv tool install --editable .     # yunhee를 전역 PATH에 editable로 설치 (다른 프로젝트 폴더에서 yunhee로 바로 실행하기 위함)
```

### 동작 전제
- **Ollama**: `YUNHEE_OLLAMA_URL`(기본 `http://localhost:11434`)에서 `qwen2.5-coder:14b`, `bge-m3:latest` 모델을 서빙 중이어야 `ask`/`chat`/`vec`/`index`/`search`/REPL이 동작한다.
- **ChromaDB**: `docs/docker-compose.yml`의 `chromadb` 서비스(docker, 8000 포트)로 구동 중이어야 한다. 로컬 파일 기반이 아닌 `chromadb.HttpClient`로 접속한다.
- **PostgreSQL / DBML**: `make-dbml`은 인자로 받은 이름의 환경변수(`.env.local`의 `LOCAL_DB`, `TEST_DB` 등)에 `postgresql://` URL이 있어야 한다 (`TEST_DB`는 사무실 내부망 전용).
- **ASIS 소스 및 mapper_index**: `prepare`는 `YUNHEE_ASIS_SRC_DIR`(ASIS 소스 루트)가 유효해야 동작한다. grounding 검증은 `tools/parse_mapper.py`로 `mapper_index`를 미리 빌드해 두어야 정상 작동한다 (인덱스가 없으면 조용히 skip하고 경고만 표시).

---

## 아키텍처 및 구현 레이어

### 1. 설정 및 프로젝트 관리
- `src/yunhee/config.py`: 설정의 단일 진입점.
  - 패키지 임포트 시점(`__init__.py`)에 `YUNHEE_DIR/.env.local`을 `load_dotenv()`로 로드.
  - **`YUNHEE_DIR` vs `WORK_DIR` 구분**:
    - `YUNHEE_DIR`: yunhee-cli 설치 경로(`.env.local` 위치, `__file__` 기준 고정).
    - `WORK_DIR`: 실행된 현재 작업 디렉토리(cwd, 작업 대상 프로젝트 루트).
    - `uv tool install --editable`로 설치해 다른 프로젝트 폴더(예: `framework-sprt`)에서 실행해도 설정과 작업 대상이 분리된다. 작업 대상을 다루는 tool은 반드시 `WORK_DIR`을 기준으로 동작해야 한다.
  - **`YUNHEE_OLLAMA_URL`**: 서버 바인드 변수(`OLLAMA_HOST=0.0.0.0`)와의 충돌을 피하기 위해 `YUNHEE_` 접두사를 사용.
  - **`NUM_CTX` (`YUNHEE_NUM_CTX`, 기본 16384)**: Ollama 요청 시 `options.num_ctx`로 전달. 넘기지 않으면 Ollama 기본값(4096)이 적용되어 긴 프롬프트 앞부분이 잘리므로 필수.
  - **`SCHEMA_ENV` (`YUNHEE_SCHEMA_ENV`, 기본 `LOCAL_DB`)**: 스키마 기본 스냅샷 이름.
  - **`ASIS_SRC_DIR` (`YUNHEE_ASIS_SRC_DIR`)**: ASIS 레거시 소스 루트.
  - `summary()`: `/config` 커맨드에서 비밀번호 마스킹 처리된 설정 반환.
- `src/yunhee/project.py`: 작업 대상 프로젝트(`WORK_DIR`) 등록/검사.
  - `WORK_DIR/.yunhee/project.json`에 `name`, `created_at`, `updated_at`, `yunhee_version` 저장.
  - `status()`로 `missing`, `outdated`, `ok` 판별 후 REPL 시작 시 `/init` 안내.
  - `current_version()`은 `importlib.metadata.version("yunhee")` 활용.

### 2. LLM / 스토어 / UI
- `src/yunhee/ollama_client.py`: Ollama HTTP API 래퍼.
  - `chat()` (단발성), `chat_stream()` (스트리밍 멀티턴), `embed()` (bge-m3 임베딩).
  - 요청마다 `num_ctx`를 명시하며, 응답의 `prompt_eval_count`가 `num_ctx`에 도달하면 토큰 잘림 경고 출력.
  - Ollama는 stateless이므로 멀티턴 대화는 전체 히스토리를 매번 전달 (REPL `/clear`의 필요 이유).
- `src/yunhee/store/vectorstore.py`: `chromadb.HttpClient` + `OllamaEmbeddingFunction` 연결 (`add_texts`, `search`).
- `src/yunhee/store/db.py`: SQLite 헬퍼. `data/db/yunhee.db`(`YUNHEE_DIR` 기준 로컬 파일)에 연결. 상위 디렉터리 자동 생성.
- `src/yunhee/ui/repl.py`: `prompt_toolkit` + `rich` 대화형 REPL.
  - 히스토리(`~/.yunhee_history`), 슬래시 커맨드(`/help`, `/exit`, `/clear`, `/config`, `/init`).
  - VRAM 제약으로 모델 고정이므로 `/model`은 미지원. 시작 배너에 버전 정보 표시.
- `src/yunhee/cli.py`: Typer 진입점.
  - 서브커맨드 없이 실행 시 REPL 실행. `--version` eager 콜백 지원.
  - `prepare` (`prep`): ASIS 페이지 요약 마크다운 생성 및 `WORK_DIR/.yunhee/prep/<page_code>.md` 캐싱. 연관 테이블 스키마(DBML) 섹션 부착.
  - `make-dbml` (`dbml`): 환경변수 이름 지정 PostgreSQL 카탈로그 추출 → DBML md 및 JSON 스냅샷 저장. 비밀번호 마스킹.
  - `table`: 스냅샷에서 지정한 테이블/glob/페이지 연관 테이블 DBML 출력.
  - `run` (`exec`): 외부 명령어 실행, 로그 격리 저장(`.yunhee/runs/<run_id>.log`) 및 로컬 Qwen 14B 에러 압축 리포트.
  - `last-run` / `runs`: 직전 실행 요약 확인 및 실행 이력 목록 테이블 표시.
- `src/yunhee/store/run_tracker.py`: SQLite `runs` 테이블에 실행 이력(명령어, exit code, 소요시간, 로그 경로, 요약 등) 저장 및 조회.

### 3. Tools 및 Context 레이어
- `src/yunhee/tools/base.py`: 모든 tool의 공통 반환 규격인 `ToolResult` (ok/data/error/truncated) 정의.
- `src/yunhee/tools/runner.py`: 외부 프로세스 실행 도구 (`subprocess.run`). 타임아웃, 원시 로그 영구 저장, 출력 미리보기 자르기(`truncated=True`), `ToolResult` 반환.
- `src/yunhee/context/run_analyzer.py`: 실행 결과 압축 요약. 성공 시 간결 헤더, 실패 시 로컬 Qwen 14B로 원인·관련 파일·핵심 에러 추출.
- `src/yunhee/tools/legacy_page.py`: ASIS 소스 수집.
  - GXT 파일명 접두사 규칙(`<page_code>_`) 기반 파일 수집 (`target/` 제외).
  - `validate_page_code()`로 경로 순회 방지 allowlist 검증.
  - 우선순위 정렬: mapper XML(0) → server/model(1) → `_Tab_` 메인(2) → 팝업(3).
  - 문자 수 예산 강제: 파일당 `PER_FILE_CHAR_LIMIT`(6,000자), 총합 `TOTAL_CHAR_LIMIT`(40,000자) 초과 시 `truncated=True`.
- `src/yunhee/tools/mapper_verify.py`: `mapper_index` 기반 환각 검증.
  - `extract_mapper_refs()`로 SQL ID 추출 및 `verify_mapper_refs()`로 실제 존재 여부 검증.
  - `check_staleness()`로 XML mtime과 인덱스 빌드 시각 비교.
- `src/yunhee/context/analyzer.py`: `summarize_page()` (로컬 Qwen 모델 기반 요약).
  - 기본 1단계 요약 및 `two_stage=True` (파일별 미니 요약 후 결합).
  - `grounding=True`: 존재하지 않는 mapper 참조를 찾아 재교정 요청.
- `src/yunhee/tools/pg_schema.py`: `fetch_schema()`.
  - `conn.read_only = True` 세션으로 카탈로그만 안전하게 조회 (테이블, 컬럼, PK/FK/인덱스, Enum, View, Procedure, Trigger 등).
- `src/yunhee/dbml.py`: `render_markdown()`. 순수 DBML 마크다운 렌더러 (DB 접속 없음).
- `src/yunhee/tools/schema_snapshot.py`: `data/schema/<ENV>.json` 스냅샷 로드/저장 및 `slice_tables()` (우선순위 기반 DBML 슬라이싱, 글자 수 예산 30,000자 제한).
- `src/yunhee/tools/page_schema.py`: `page_tables()` (mapper XML에서 참조 테이블 추출).
- `src/yunhee/context/schema_context.py`: `page_schema_section()` (prepare 결과에 붙일 연관 테이블 스키마 섹션 조립).
- `tools/parse_mapper.py`: ASIS MyBatis 매퍼 전체를 파싱해 SQLite `mapper_index` 생성 (독립 유틸리티).

---

## 핵심 설계 원칙

1. **Tools 레이어의 부수효과 격리**:
   - DB 조회, grep, 파일 탐색 등 외부 부수효과가 있는 모든 로직은 `src/yunhee/tools/` 하위에 독립 함수로 격리하고, 반드시 정형화된 `ToolResult(ok, data, error, truncated)`를 반환한다.
   - 상위 컨텍스트 조립기나 향후 추가될 Agent 루프는 이 `ToolResult`만 소비하며, 이 함수들은 향후 LLM Tool-Calling의 스키마로 직접 활용된다.
2. **Tools 레이어에서의 토큰/문자 수 예산 강제**:
   - 상위 레이어로 전달되기 전에 tools 단계에서 크기 제한(글자 수 컷오프)을 엄격히 강제한다. 이를 통해 상용 AI 어시스턴트에게 전달되는 컨텍스트 크기를 통제하고 토큰 낭비를 원천 차단한다.
3. **DB 쿼리 안전 가드**:
   - DB 접근은 읽기 전용(`read_only=True`) 세션 및 카탈로그 조회 위주로 수행하며, 임의 쿼리 실행 시 `SELECT` 전용 가드를 적용한다.
4. **오프라인 스키마 스냅샷 활용**:
   - 테스트 DB가 사무실 내부망에만 위치하므로, 실시간 커넥션에 의존하지 않고 오프라인 DBML/JSON 스냅샷(`make-dbml`)을 기반으로 동작하도록 설계한다.
5. **단일 SQLite DB 및 프로젝트 격리**:
   - 캐시나 상태 관리는 `data/db/yunhee.db` 하나의 파일에서 `project` 컬럼(프로젝트명)을 통해 다중 작업 대상을 구분·격리한다.

---

## 미구현 로드맵

- `tools/grep_source.py`, `tools/db_query.py` (SELECT 전용 가드 포함)
- `indexer/legacy_scanner.py`, `indexer/chunker.py` (레거시 소스 페이지 단위 청킹 및 해시 기반 증분 인덱싱)
- `context/assembler.py` (요약 + 검색 + 스키마 + 패턴 결합 최종 컨텍스트 조립)
- `store/patterns.py`, `store/tracker.py` (진행 상태 추적)
- **우선순위 로드맵**:
  1. 레거시 소스 인덱싱
  2. `yunhee prep <PageName>` 컨텍스트 압축·조립 (페이지 요약 단계까지 완료)
  3. `yunhee similar <PageName>` 패턴 재사용
  4. `yunhee status` / `yunhee next` 진행 상황 트래커
  5. 기계 판정 기반 루프 (`fix-build`, `check-sql`)

---

## 디렉터리 구조

- `src/yunhee/`: CLI 메인 소스 코드
  - `agent/`: 향후 agent loop 확장 모듈
  - `context/`: 컨텍스트 조립 및 프롬프트 생성 (`analyzer.py`, `schema_context.py`)
  - `store/`: ChromaDB 벡터스토어 및 SQLite 로컬 스토어
  - `tools/`: 독립 실행 도구 모음 (`legacy_page.py`, `pg_schema.py`, `schema_snapshot.py` 등)
  - `ui/`: REPL 대화형 인터페이스
  - `cli.py`, `config.py`, `dbml.py`, `ollama_client.py`, `project.py`
- `tests/`: pytest 테스트 코드 (`test_dbml.py`, `test_legacy_page.py`, `test_ollama_client.py`, `test_schema_snapshot.py`)
- `tools/`: 빌드/인덱싱용 유틸리티 스크립트 (`parse_mapper.py`)
- `data/`: 로컬 SQLite DB, 스키마 스냅샷 등 로컬 데이터 (git 제외)
- `docs/`: 상세 아키텍처 및 명령어 설계 문서, `docker-compose.yml`

---

## 주의사항

- **보안 및 자격 증명**: `.env.local`에는 실제 DB 계정 정보가 포함되어 있으므로 절대 git에 커밋하지 않는다 (`.gitignore`에 포함됨).
- **환경변수 규칙**: 새로운 환경변수 추가 시 반드시 `.env.local.sample`에도 설명과 함께 추가하며, 시스템 환경변수 충돌 방지를 위해 `YUNHEE_` 접두사를 사용한다.
- **경로 참조 원칙**:
  - `yunhee` 자체 리소스(설정, 로컬 SQLite DB, 스키마 스냅샷 등)는 `config.YUNHEE_DIR` 기준.
  - 마이그레이션 작업 대상 소스 파일이나 타겟 출력물은 반드시 `config.WORK_DIR` 기준.
  - ASIS 레거시 소스는 `config.ASIS_SRC_DIR` 기준.
