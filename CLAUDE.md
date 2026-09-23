# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 프로젝트 개요

`yunhee-cli`는 상용 vibe-coding 도구(Claude CLI, Antigravity CLI)의 **토큰 사용량을 절약**하기 위해 만드는 독자적인 로컬 agent CLI다. MCP 서버로 claude-cli에 plug-in되는 형태가 아니라, 파일 읽기/검색/DB 조회 등 **실제 액션을 독립적으로 수행하는 CLI**를 지향한다.

- 로컬 모델은 Ollama로 구동: `qwen2.5-coder:14b`(추론/분석), `bge-m3`(임베딩). VRAM 16GB 제약으로 모델은 고정 1개만 사용하며, 모델 전환 기능은 의도적으로 제외했다.
- 실사용 배경: legacy AssetERP(GWT 2.9/GXT 4.0.2/Java 8/PostgreSQL/MyBatis, 수백 page 규모 자산운용 SaaS ERP)를 Spring Boot/React/MyBatis/PostgreSQL/Java 21로 마이그레이션하는 vibe coding 작업에서, 페이지 변환마다 claude-cli/antigravity-cli에 넘길 컨텍스트를 미리 압축·조립해 토큰 낭비(GXT 보일러플레이트 등)를 줄이는 것이 실질 목적이다.
- 설계 배경과 로드맵 전체는 `docs/yunhee-cli-설계.md`에 있다. 세션 시작 시 먼저 읽을 것 — 지금까지 논의된 결정과 기각된 아이디어가 정리되어 있다.

## 개발 명령어

이 프로젝트는 `uv` 기반 src layout이다.

```bash
uv sync                          # 의존성 설치
uv run yunhee                    # REPL 진입 (서브커맨드 없이 실행 시 기본 동작)
uv run yunhee ask "질문"          # 단발성 질의 (기본 모델: qwen2.5-coder:14b)
uv run yunhee vec "텍스트"        # bge-m3 임베딩 확인
uv run yunhee index "텍스트"      # chromadb에 텍스트 저장
uv run yunhee search "쿼리" -n 3  # 저장된 텍스트 중 유사 검색

uv run pytest                    # 테스트 실행 (tests/ 디렉토리는 아직 비어있음)
uv run ruff check .              # lint
```

Ollama가 `http://localhost:11434`에서 `qwen2.5-coder:14b`, `bge-m3:latest` 모델을 서빙 중이어야 `ask`/`chat`/`vec`/`index`/`search`/REPL이 동작한다.

## 아키텍처

### 현재 구현된 레이어 (스캐폴드 완료)

- `src/yunhee/ollama_client.py` — Ollama HTTP API 래퍼. `chat()`(단발성), `chat_stream()`(멀티턴, 토큰 단위 yield), `embed()`(bge-m3 임베딩). Ollama `/api/chat`은 stateless이므로 멀티턴 대화는 매 요청마다 전체 히스토리를 다시 보내야 한다 — REPL의 `/clear`가 실질적 의미를 갖는 이유.
- `src/yunhee/store/vectorstore.py` — chromadb `PersistentClient`(`data/chroma/`에 저장) + `OllamaEmbeddingFunction`(내부적으로 `ollama_client.embed()` 호출)로 bge-m3 임베딩을 연결. `add_texts()` / `search()` 제공.
- `src/yunhee/ui/repl.py` — claude-cli 스타일 대화형 REPL. `prompt_toolkit`(히스토리 파일 `~/.yunhee_history`, 슬래시 커맨드 자동완성) + `rich`(스트리밍 출력). 지원 커맨드: `/help`, `/exit`(`/quit`), `/clear`. `/model`은 VRAM 제약상 모델 고정이라 의도적으로 제외.
- `src/yunhee/cli.py` — typer app 진입점(`yunhee` 스크립트). 서브커맨드 없이 실행하면 바로 REPL 진입.

### 설계 원칙 (미구현 레이어에도 적용)

- **부수효과가 있는 실행(DB 조회, grep, 파일 검색 등)은 전부 `tools/` 폴더에 독립 함수로 분리**하고, 상위 레이어(컨텍스트 조립기, 이후의 agent loop)는 정형화된 결과(`ToolResult`: ok/data/error/truncated)만 소비한다. 이렇게 분리해두면 나중에 agent loop을 붙일 때 이 함수들이 그대로 tool-calling 스키마가 된다.
- **토큰 예산 관리는 tools 레이어에서 강제한다.** grep/쿼리 결과를 이 레이어에서 자르면 위쪽 레이어는 항상 절제된 크기만 다루게 된다 — 이것이 "토큰 절약"의 실질적 관문이다.
- DB 쿼리 tool은 `SELECT`만 허용하는 가드가 필수다 (테스트 DB라도 안전장치로).
- PostgreSQL 테스트 DB는 **사무실에서만 접근 가능**하므로, 스키마는 라이브 커넥션에 의존하지 않고 `pg_dump --schema-only` 스냅샷 기반 **오프라인 캐시**로 관리한다.
- 패턴 캐시·진행상황 추적 등 로컬 단일 사용자용 저장소는 sqlite를 쓴다. PostgreSQL은 AssetERP 테스트 DB 읽기 전용 조회에만 사용한다.

### 아직 설계만 되고 미구현인 것

- `tools/base.py`(`ToolResult` 공통 스키마), `tools/grep_source.py`, `tools/db_query.py`, `tools/schema_dump.py`
- `indexer/legacy_scanner.py`, `indexer/chunker.py` — 레거시 소스를 페이지 단위(View+Presenter+Mapper+도메인)로 청킹, 파일 해시 기반 변경 감지로 재인덱싱 최소화
- `context/analyzer.py`, `context/assembler.py` — qwen으로 GXT 페이지 구조 요약 후 검색결과+요약+스키마+패턴을 최종 컨텍스트로 조립
- `store/patterns.py`, `store/tracker.py`(sqlite: page_name, status, complexity, last_touched)

로드맵 우선순위(가장 ROI 큰 것부터): 레거시 소스 인덱싱 → `yunhee prep <PageName>` 컨텍스트 압축·조립(핵심) → `yunhee similar <PageName>` 패턴 재사용 → `yunhee status`/`yunhee next` 진행상황 트래커 → (선택) agent loop.

## 주의사항

- `.env.local`, `tools/.env.local`에 DB 접속 정보(자격 증명 포함)가 있다. 커밋하지 말 것 (`.gitignore`에서 `.env*` 제외 처리됨).
- `tests/`는 현재 비어있다.
