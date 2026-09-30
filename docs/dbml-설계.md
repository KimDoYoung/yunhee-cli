# `make-dbml`(별칭 `dbml`) 명령어 설계

> `docs/yunhee-cli-설계.md`의 "스키마는 라이브 커넥션에 의존하지 않고 오프라인 캐시로 관리한다" 원칙을 구현한 결과 정리. 원래 계획의 `tools/schema_dump.py`(`pg_dump --schema-only` 스냅샷)를 이 명령이 대체한다.

## 1. 목적

AssetERP 페이지를 TOBE로 변환할 때 claude-cli/gemini-cli는 테이블 구조·컬럼 코멘트·함수 정의를 자주 참조해야 한다. 그런데 테스트 DB(`TEST_DB`)는 **사무실에서만 접근 가능**하고, 매번 DB에 붙어서 `\d` 결과를 에이전트에게 흘려보내는 건 토큰 낭비다. 그래서 스키마 전체를 **한 번 파일로 떠두고** 이후엔 그 파일(또는 그 일부)을 컨텍스트로 쓴다.

형식은 DBML(Database Markup Language)을 택했다.
- `CREATE TABLE` DDL보다 간결하다 (제약조건 문법·`COMMENT ON` 문 반복이 없음) → 토큰 절약.
- 한 줄에 컬럼 하나 + 한글 코멘트가 붙어서 LLM과 사람 모두 읽기 쉽다.
- dbdiagram.io에 그대로 붙여넣어 ERD로 볼 수 있다.

```
yunhee make-dbml LOCAL_DB                 # → ./LOCAL_DB-dbml.md
yunhee dbml TEST_DB --output=a.md         # → ./a.md
yunhee dbml LOCAL_DB --schema public      # 특정 스키마만 (여러 번 지정 가능)
```

## 2. 전체 흐름

```
yunhee make-dbml <ENV_NAME> [--output FILE] [--schema S ...]
        │
        ▼
cli.py : _make_dbml()
   - ENV_NAME 형식 검증 (^[A-Za-z_][A-Za-z0-9_]*$)
   - os.getenv(ENV_NAME) → 없거나 postgresql:// / postgres:// 가 아니면 오류 종료
        │
        ▼
tools/pg_schema.py : fetch_schema(dsn, schemas)
   - psycopg 접속 (connect_timeout=10) + conn.read_only = True
   - 시스템 카탈로그(pg_class, pg_attribute, pg_constraint, pg_index, pg_proc, ...)만 SELECT
   - 결과: ToolResult(ok, data={tables, refs, enums, views, routines, sequences, triggers, ...})
        │
        ▼
dbml.py : render_markdown(schema, source, source_url)
   - 헤더(생성 시각, 마스킹된 URL, DB/버전, 객체 개수)
   - ```dbml 블록 (Enum → Table → Ref)
   - ## Views / ## Materialized Views / ## Functions / ## Procedures  (```sql 정의문)
   - ## Sequences (표) / ## Triggers (```sql 블록)
        │
        ▼
--output (기본 WORK_DIR/<ENV_NAME>-dbml.md)에 저장, 객체 개수 출력
```

레이어 분리는 `prepare`와 같은 원칙: DB 접속(부수효과)은 `tools/`에, 렌더링은 DB 없이 dict만 받는 순수 함수로. 그래서 렌더러는 DB 없이 테스트할 수 있다 (`tests/test_dbml.py`).

## 3. 설계 결정

### 3-1. 인자는 URL이 아니라 "환경변수 이름"

`yunhee make-dbml LOCAL_DB`처럼 `.env.local`에 이미 있는 변수 이름을 받는다.
- 자격 증명이 셸 히스토리(`~/.yunhee_history`, fish history)에 남지 않는다.
- `LOCAL_DB`/`TEST_DB`를 바꿔가며 같은 명령을 쓸 수 있고, 기본 출력 파일명(`<ENV_NAME>-dbml.md`)에도 그 이름이 그대로 쓰인다.
- 화면·파일에 찍히는 URL은 전부 `config.redact()`로 비밀번호를 `***`로 가린다 (`/config`에서 쓰던 `_redact()`를 공개 함수로 바꿔 재사용).

### 3-2. 읽기 전용 세션

"DB 쿼리 tool은 SELECT만 허용" 원칙에 따라, 쿼리 문자열을 검사하는 대신 **세션 자체를 `read_only`로** 연다. 이 tool이 실행하는 SQL은 고정된 카탈로그 조회뿐이지만, 테스트 DB라도 쓰기가 원천적으로 불가능하게 해둔다.

### 3-3. DBML이 표현 못 하는 객체는 SQL 섹션으로

DBML 문법은 Table/컬럼/인덱스/Ref/Enum/Note만 지원한다. view·function·procedure·sequence·trigger는 표현할 방법이 없어서 다음 두 안 중 앞의 것을 택했다.

- (채택) ```` ```dbml ```` 블록 + 뒤쪽 마크다운 섹션에 ```` ```sql ```` 정의문 — dbml 블록만 떼서 dbdiagram.io에 붙일 수 있고, 함수 본문은 SQL 하이라이팅 그대로 읽힌다.
- (기각) 전부 dbml 안의 `Note` 블록 텍스트로 — 파싱은 되지만 가독성이 나쁘다.

정의문은 PostgreSQL이 재구성해주는 것을 그대로 쓴다: `pg_get_viewdef`, `pg_get_functiondef`, `pg_get_triggerdef`. view는 본문(SELECT)만 나오므로 `CREATE OR REPLACE VIEW ... AS` / `CREATE MATERIALIZED VIEW ... AS`를 앞에 붙인다.

### 3-4. DBML 렌더링 규칙

| 대상 | 렌더링 |
|---|---|
| 테이블/컬럼 이름 | 항상 `"schema"."table"`, `"col"` 큰따옴표 |
| 타입 | 항상 큰따옴표 (`"character varying(20)"`, `"timestamp with time zone"`, `"text[]"` — 공백·괄호가 있어도 파싱 안전) |
| 단일 PK / 단일 UNIQUE | 컬럼 설정 `[pk]`, `[unique]` (pk면 `not null`은 생략) |
| 복합 PK / 복합 UNIQUE | `indexes { ("a", "b") [pk] }`, `[unique, name: '...']` |
| identity, `nextval(...)` default (serial) | `[increment]` (nextval default 자체는 생략) |
| 일반 default | `` default: `expr` `` (항상 백틱 표현식) |
| generated column | default 대신 note에 `GENERATED ALWAYS AS (...) STORED` |
| 코멘트 | 컬럼 `note: '...'`, 테이블 `Note: '...'`. `'`는 `\'`로, 여러 줄이면 `'''...'''` |
| 일반 인덱스 | `(col, ...) [name: '...']`, 표현식 컬럼은 `` `lower(...)` `` |
| hash 인덱스 | `type: hash` |
| gin/gist 등 기타 인덱스, partial 인덱스 | `note: 'USING gin'`, `note: 'WHERE ...'` (DBML에 해당 문법 없음) |
| FK | `Ref "fk_name": "s"."t"."c" > "s"."t2"."c2" [delete: cascade, update: ...]`, 복합 FK는 `.("a", "b")` |
| 대상 테이블이 출력 범위 밖인 FK | `// Ref ...` 주석으로만 남김 (존재하지 않는 테이블을 가리키면 DBML 파싱 오류) |

PK·UNIQUE 제약조건이 만든 인덱스는 `pg_index`에서 제외하고 제약조건 쪽에서만 표현한다 (중복 방지). 출력 순서는 전부 이름순 고정이라 재생성해도 diff가 작다 (헤더의 생성 시각 한 줄만 바뀜).

### 3-5. 제외하는 것

- 시스템 스키마: `pg_catalog`, `information_schema`, `pg_toast*`, `pg_temp*`
- 파티션 자식 테이블 (`relispartition`) — 부모 테이블만 기록
- 확장(extension)이 소유한 객체 (`pg_depend.deptype = 'e'`) — pgcrypto 등의 함수 수백 개가 섞이는 걸 막음
- 내부 트리거 (`tgisinternal`, FK 구현용 트리거 등)
- aggregate/window 함수 (`prokind`가 `f`/`p`인 것만)

### 3-6. truncation 없음

"토큰 예산은 tools 레이어에서 강제" 원칙의 예외다. 이 명령의 결과물은 LLM에 바로 넘어가는 게 아니라 **스냅샷 파일**이기 때문에 전부 기록한다. 예산 관리는 이 파일을 소비하는 쪽(향후 `context/assembler.py` 등)이 페이지에 필요한 테이블만 골라내는 방식으로 해야 한다 (5번 참고).

## 4. 실제 검증 결과 (`LOCAL_DB`, 2026-09-30)

대상: `asseterpdb` (PostgreSQL 15.19, 로컬 docker `t3600_postgres`), 스키마 `public` 하나.

- 실행 시간 약 1.4초.
- 테이블 663, view 7, function 333, procedure 8, sequence 11, trigger 76. **FK·enum·materialized view는 0개** (적어도 로컬 DB에는 FK 제약조건이 하나도 없음 — `TEST_DB`도 같은지는 미확인).
- 테이블 663개 중 609개에 테이블 코멘트, 컬럼 코멘트 6,372개 — 한글 코멘트가 풍부해서 DBML이 사실상 "테이블 사전" 역할을 한다.
- 결과 파일 52,075줄 / 약 2.6M자. 섹션별 비중:

  | 섹션 | 줄 수 | 문자 수 | 비중 |
  |---|---:|---:|---:|
  | Functions | 38,369 | 2,017,576 | 77% |
  | DBML (테이블) | 12,189 | 509,884 | 20% |
  | Procedures | 973 | 51,354 | 2% |
  | Views | 441 | 22,627 | 1% |
  | Triggers | 80 | 11,174 | <1% |
  | Sequences | 16 | 1,111 | <1% |

  → **파일 크기는 함수 본문이 지배한다.** 통째로 LLM 컨텍스트에 넣을 크기가 아니다.

- DBML 문법 검증: dbml 블록 전체(12,184줄)를 공식 파서 `npx -p @dbml/cli dbml2sql --postgres`로 변환 성공. 단, 이 크기에서 파서가 **약 7분** 걸린다 (dbdiagram.io에 통째로 붙이면 느릴 수 있음).
- 이 DB에 없는 구문(FK Ref, 복합 FK, enum, 여러 줄 코멘트, 표현식/partial/hash 인덱스, generated column, 범위 밖 Ref 주석)은 가짜 데이터로 렌더링한 DBML을 같은 파서로 따로 검증함 — 전부 통과.
- 오류 경로: 없는 환경변수, 잘못된 이름(`a/b`), postgres URL이 아닌 값, 없는 스키마(`--schema nope`) → 전부 메시지 출력 후 exit 1, 비밀번호 비노출 확인.
- `TEST_DB`(사무실 DB)는 아직 실행해보지 않음.

## 5. 알려진 한계 / 남은 할 일

1. **파일이 너무 크다.** 다음 단계는 "페이지에 필요한 테이블만 뽑기"다. `mapper_index.tables`(`tools/parse_mapper.py`가 만든 mapper별 참조 테이블 목록)와 조합하면, `prepare <page_code>` 때 그 페이지 mapper가 쓰는 테이블의 DBML 블록만 잘라서 요약에 붙일 수 있다. 이를 위해선 `.md`를 다시 파싱하기보다 `fetch_schema()` 결과(dict)를 JSON이나 sqlite로도 같이 저장해두는 게 낫다.
2. **함수 본문 필터링 옵션.** 함수가 77%를 차지하므로 `--no-functions` 또는 시그니처만 기록하는 옵션을 고려.
3. **기록하지 않는 것:** CHECK 제약조건, domain/composite 타입, 권한(GRANT)·소유자, RLS policy, 시퀀스 현재값(`last_value`), 설치된 extension 목록. 필요해지면 추가.
4. **enum 컬럼 연결:** 타입을 항상 큰따옴표로 감싸기 때문에 dbdiagram.io에서 enum 컬럼과 `Enum` 정의가 시각적으로 연결되지 않는다 (현재 DB엔 enum이 없어서 보류).
5. **staleness:** 스냅샷이 언제 떠졌는지는 헤더의 생성 시각으로만 알 수 있다. `mapper_index`처럼 오래된 스냅샷을 경고하는 체크는 없음.
6. 사무실에서 `yunhee make-dbml TEST_DB` 실행 후 `LOCAL_DB` 결과와 차이 확인.

## 6. 관련 파일 위치 (요약)

| 파일 | 역할 |
|---|---|
| `src/yunhee/cli.py` (`_make_dbml`) | `make-dbml`/`dbml` 커맨드, 환경변수 이름 검증, `--output`/`--schema` |
| `src/yunhee/tools/pg_schema.py` | `fetch_schema()` — 읽기 전용 세션에서 카탈로그 조회 → dict |
| `src/yunhee/dbml.py` | `render_markdown()`, `counts()` — DBML + SQL 섹션 렌더링 (순수 함수) |
| `src/yunhee/config.py` | `redact()` — URL 비밀번호 마스킹 |
| `tests/test_dbml.py` | 렌더러 규칙 + CLI 오류 경로/기본 출력 파일명 (DB 불필요, `fetch_schema` monkeypatch) |
| `pyproject.toml` | `psycopg[binary]` 의존성 |
