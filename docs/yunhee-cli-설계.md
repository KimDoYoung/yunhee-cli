# yunhee-cli 설계 문서

> 이 문서는 지금까지 논의한 내용과 앞으로 구현할 것들을 정리한 참조용 문서입니다. `docs/`에 넣어두고 다음 세션에서 이어서 작업할 때 참고하세요.

## 1. 목적

- 실제 vibe coding 도구(Claude CLI, Antigravity CLI)를 보조해서 **토큰 사용량을 절약**하는 독자적인 로컬 agent CLI
- MCP 서버로 claude-cli에 plug-in되는 형태가 아니라, **독립적으로 실제 액션(파일 읽기/검색/DB 조회 등)을 수행하는 CLI**를 지향
- 로컬 모델: Ollama로 구동하는 `qwen2.5-coder:14b`(추론/분석), `bge-m3`(임베딩) — VRAM 16GB, 모델은 고정 1개만 사용 (모델 전환 기능은 불필요하다고 판단해 제외)

## 2. 사용 배경 — AssetERP 마이그레이션

- **레거시**: GWT 2.9, GXT 4.0.2, Java 8, PostgreSQL, MyBatis. 자산운용회사 대상 SaaS ERP, 수백 page 규모.
- **목표 스택**: Spring Boot, React, MyBatis, PostgreSQL, Java 21
- 작업 방식: Claude CLI, Antigravity CLI로 vibe coding
- yunhee-cli의 실질적 역할: 페이지 변환 작업마다 claude-cli/antigravity-cli에 넘기는 **컨텍스트를 미리 압축·조립**해서 토큰 낭비(GXT 보일러플레이트 등)를 줄이는 것

## 3. 접근 가능한 리소스

- AssetERP 전체 소스 (git clone, 로컬 디스크)
- PostgreSQL 테스트 DB — **사무실에서만 접근 가능, 집에서는 불가**
- → 스키마는 라이브 커넥션에 의존하지 않고 **오프라인 캐시**로 관리해야 함 (`pg_dump --schema-only` 스냅샷 + 주기적 재덤프)

## 4. 아키텍처 원칙

- DB 조회, grep, 파일 검색 등 **부수효과가 있는 실행은 전부 `tools/` 폴더에 독립 함수로 분리**하고, 상위 레이어(context 조립기, 나중의 agent loop)는 정형화된 결과(`ToolResult`: ok/data/error/truncated)만 소비한다.
- 이렇게 분리해두면 나중에 agent loop을 붙일 때 이 함수들이 그대로 tool-calling 스키마가 됨 (재작업 불필요).
- **토큰 예산 관리는 tools 레이어에서 강제** — grep/쿼리 결과를 여기서 자르면, 위쪽은 항상 절제된 크기만 다루게 됨. 이게 "토큰 절약"의 실질적 관문.
- DB 쿼리 tool은 `SELECT`만 허용하는 가드 필수 (테스트 DB라도 안전장치).

## 5. 현재까지 구현된 것 (스캐폴드 완료)

프로젝트: `~/work/yunhee-cli`, `uv` 기반 src layout.

- **`ollama_client.py`**: `chat()`, `chat_stream()`, `embed()` — qwen2.5-coder / bge-m3 연동 확인 완료 (curl, 파이썬 직접 호출 양쪽 다 검증)
- **`store/vectorstore.py`**: `chromadb.HttpClient(CHROMA_HOST, CHROMA_PORT)`(docker `chromadb` 서비스, `docs/docker-compose.yml`) + bge-m3 임베딩 함수, `add_texts()` / `search()` 동작 확인 완료 (관련 문서가 실제로 더 가까운 거리로 검색됨을 확인)
- **`ui/repl.py`**: claude-cli 스타일 대화형 REPL
  - `prompt_toolkit` 기반, 히스토리 파일 저장
  - 스트리밍 출력 (rich)
  - 슬래시 커맨드: `/help`, `/exit`(`/quit`), `/clear` (컨텍스트 리셋 — Ollama `/api/chat`이 stateless라 매 요청마다 전체 히스토리를 다시 보내야 하므로, 대화가 길어질 때 속도/품질 관리 목적으로 실제로 의미 있음)
  - `/`만 입력 시 `WordCompleter`로 커맨드 자동완성
  - `/model`은 VRAM 제약상 모델 고정이라 불필요 판단, 제외
- **`cli.py`**: typer app. `hello`, `ask`, `vec`, `index`, `search` 커맨드 + 서브커맨드 없이 실행하면 REPL 진입

## 6. 설계만 논의되고 아직 미구현

- `tools/base.py` — `ToolResult` 공통 스키마
- `tools/grep_source.py` — ripgrep wrapper, max_results로 truncate
- `tools/db_query.py` — read-only SELECT 전용, psycopg 사용
- `tools/schema_dump.py` — `pg_dump --schema-only` 스냅샷, staleness 체크(예: 30일)
- `indexer/legacy_scanner.py`, `chunker.py` — 레거시 소스를 페이지 단위(View+Presenter+Mapper+도메인)로 청킹, 파일 해시 기반 변경 감지로 재인덱싱 최소화
- `context/analyzer.py` — qwen으로 GXT 페이지 구조(필드/그리드/이벤트/호출 API) 요약
- `context/assembler.py` — 검색결과 + 요약 + 스키마 + 패턴을 최종 컨텍스트로 조립
- `store/patterns.py` — 변환 완료된 패턴 캐시 (sqlite)
- `store/tracker.py` — 페이지별 진행상황 (sqlite: page_name, status, complexity, last_touched)
- `store/session.py` — 대화 세션 저장/resume (우선순위 낮음, 보류)

## 7. 단계별 로드맵

| Phase | 내용 | 비고 |
|---|---|---|
| 1 | 레거시 소스 인덱싱 (`legacy_scanner`, `chunker`) | chromadb에 페이지 단위로 저장 |
| 2 | 컨텍스트 압축·조립 (`yunhee prep <PageName>`) | **핵심, ROI 가장 큼** — 원본 소스 대신 요약본만 claude-cli에 전달 |
| 3 | 변환 패턴 캐시 (`yunhee similar <PageName>`) | 비슷한 페이지 이미 변환된 패턴 재사용 |
| 4 | 진행상황 트래커 (`yunhee status`, `yunhee next`) | 수백 페이지 작업 상태 관리 |
| 5 | 판정자가 있는 루프 (`yunhee fix-build`, `yunhee check-sql`) | tool 실행 → 결과 판정 → 수정 → 재실행. 판정은 컴파일러/스키마 등 **기계가** 한다. 7.1 참고 |
| 6 (선택) | 범용 agent loop | 단순 CRUD 페이지는 로컬에서 초안 생성, claude/antigravity는 리뷰만. 1~5가 갖춰진 뒤 진행하는 게 신뢰도 높음 |

### 7.1 판정자가 있는 루프 (verifier loop)

**배경**: claude-cli가 토큰을 가장 많이 쓰는 구간은 첫 설계·첫 변환이 아니라 "빌드 → 에러 → 파일 다시 읽기 → 고치기 → 다시 빌드"를 반복하는 구간이다. 이 과정은 지능보다 끈기가 필요한 일이라, 토큰이 공짜인 로컬 모델이 몇 번이고 돌리기에 적합하다.

**핵심 원칙: 판정을 모델이 아니라 기계가 한다.** 판정자가 결정적이면 모델이 조금 부족해도 결국 수렴한다. 판정자가 모델 자신이면 14b는 5~10 스텝 안에 길을 잃는다.

| 루프 | 판정자 | 14b 적합성 |
|---|---|---|
| 컴파일 에러 수정 (`mvn compile`, `tsc`) | 컴파일러 | ✅ |
| lint/타입 에러 정리 | ruff, eslint, tsc | ✅ |
| MyBatis SQL ↔ 스키마 대조 (컬럼명·타입 불일치) | 스키마 스냅샷, `EXPLAIN` | ✅ yunhee만의 강점 |
| 테스트 실패 수정 | 테스트 러너 | △ 단순한 경우만 |
| `prep`용 탐색 (grep → 읽기 → 재grep) | 사람/Claude가 결과 검토 | ✅ 읽기 전용이라 안전 |
| GXT 페이지 전체 → React 변환 | 없음 (모델 자기 판단) | ❌ Claude 몫 |
| 설계 판단·구조 결정 | 없음 | ❌ |

**역할 분담**:

```
Claude  : 어려운 첫 변환 (prep으로 압축된 컨텍스트를 받아서)
yunhee  : 그 뒤의 반복 작업 → 컴파일/SQL/lint 에러를 루프로 정리
          → N회 안에 수렴하면 끝
          → 실패하면 "남은 에러 + 시도한 것"만 요약해서 Claude에게 넘김
Claude  : 리뷰, 또는 요약된 실패만 해결
```

yunhee가 실패해도 Claude에게는 압축된 실패 요약만 넘어가므로, 어느 경우든 토큰이 절약된다.

**14b로 성공하기 위한 설계 원칙**:

1. **범용 agent가 아니라 목적별 루프.** 루프 흐름(순서·분기)은 코드가 쥐고, 모델은 "다음 수정안"만 채운다. 행동 선택지가 좁을수록 작은 모델이 안정적이다.
2. **종료 조건은 코드가 결정.** 판정자 통과 / 최대 N회 / 같은 에러가 반복되면 중단.
3. **`num_ctx` 명시 지정.** 모델 최대 컨텍스트는 32k지만 Ollama 기본값은 훨씬 작아서, 지정하지 않으면 긴 입력이 조용히 잘린다. VRAM 16GB + Q4_K_M 14b 기준 16k 정도가 현실적. 히스토리를 매 턴 누적하지 말고 "현재 에러 + 현재 파일 조각"만 보낸다 — tools 레이어의 결과 truncate가 여기서 더 중요해진다.
4. **쓰기는 안전하게.** git worktree/브랜치에서만 수정하고, 끝나면 diff를 보여주고 사람이 승인한다.
5. **`ToolResult` 스키마 = tool-calling 스키마.** 4장 원칙대로 `tools/`를 먼저 만들어두면 루프는 그 위에 얹기만 하면 된다. (`qwen2.5-coder:14b`는 Ollama에서 `tools` capability 지원 확인됨)

**REPL과의 관계**: 이 방향에서 대화형 REPL이 처음으로 실질적 의미를 갖는다 — 루프 진행(tool 호출 → 결과 → 수정 diff)을 실시간으로 보면서 중간에 개입("그 파일 말고 이거 봐")하거나 diff를 승인하는 UI가 필요하기 때문. 그 전까지는 서브커맨드(파이프/배치 가능)를 주력으로 하고, REPL 슬래시 커맨드는 같은 함수를 호출하는 얇은 셸로만 유지한다.

## 8. 검토 후 기각/보류한 아이디어

- **MCP 서버 방식**: claude-cli에 plug-in되는 형태는 기각 — 독립적으로 액션을 취하는 CLI를 원함
- **`/model` 슬래시 커맨드**: VRAM 16GB로 모델 하나만 고정 사용이라 불필요, 제거
- **sqlite vs postgresql**: 패턴 캐시·진행상황 추적 등은 로컬 단일 사용자 용도라 sqlite로 충분. postgresql은 AssetERP 테스트 DB 읽기 전용 조회에만 사용
- **스키마 라이브 조회 의존**: 집에서 DB 접근이 안 되므로 기각, 오프라인 스냅샷 캐시 방식으로 결정

## 9. 다음 액션 후보 (미결정 — 다음 세션에서 하나 선택)

1. Phase 1 스캐폴딩부터 시작 (`legacy_scanner.py`)
2. 실제 AssetERP 페이지 1~2개로 Phase 2 `prep` 흐름을 손으로 흉내 내서 qwen 요약 품질부터 검증 (더 빨리 "진짜 토큰이 절약되는지" 확인 가능)
3. `tools/` 레이어(`grep_source`, `db_query`, `schema_dump`)부터 구현
4. 판정자 루프 수렴률 검증 — AssetERP 변환 결과의 실제 컴파일 에러 몇 개로, qwen에 "에러 + 해당 코드 조각"만 주고 3회 안에 고치는지 손으로 확인. 수렴률이 괜찮으면 `tools/` → `fix-build` 루프 순으로 진행 (7.1 참고)