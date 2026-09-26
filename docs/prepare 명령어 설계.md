# `prepare`(별칭 `prep`) 명령어 설계

> `docs/yunhee-cli-설계.md`의 로드맵에서 "다음 액션 후보 2번"(Phase 2 prep 흐름을 실제 페이지로 검증)을 구현한 결과 정리. 다음 세션(집에서)에 이어서 작업할 때 여기부터 읽으면 됨.

## 1. 목적

claude-cli/gemini-cli가 AssetERP(ASIS, GWT/GXT) 페이지 하나를 Spring Boot/React(TOBE)로 변환할 때, 원본 소스(한 페이지당 십수 개 파일, 수천 줄의 GXT/MyBatis 보일러플레이트)를 직접 읽게 하는 대신 **로컬 qwen이 미리 압축한 요약 한 장**을 읽게 해서 토큰을 절약한다. 이게 이 프로젝트(`yunhee`)가 존재하는 이유를 처음으로 실제 증명하는 기능이다.

```
yunhee prepare ast01     # 정식 이름
yunhee prep ast01        # 완전히 동일한 별칭
```

## 2. 왜 chromadb 인덱싱(Phase 1) 없이 바로 이걸 만들었나

실제 AssetERP 소스(`/home/kdy987/oms-data/src/Asset-ERP`)를 조사해보니, **페이지 코드가 파일명 접두사로 그대로 인코딩**되어 있었다 (`Ast01_Tab_InfoManagement.java`, `ast01_class_tree.xml` 등, 대소문자만 다름). 즉 페이지 코드를 이미 알고 있으면 chromadb 의미검색 없이 `os.walk` + 파일명 prefix 매칭만으로 정확히 그 페이지의 파일들을 찾을 수 있다. chromadb 의미검색은 "어느 페이지가 이 로직을 담당하는지 모를 때"나 "비슷하게 변환된 페이지 찾기"에나 필요한데, TOBE 쪽(`framework-sprt`)에 아직 변환 완료 예시가 프론트엔드 1개뿐이라 지금은 필요 없다고 판단해 보류했다.

## 3. 전체 흐름

```
yunhee prepare <page_code>
        │
        ▼
tools/legacy_page.py : find_page_files(page_code)
   - ASIS_SRC_DIR 아래 재귀 탐색, target/ 제외
   - 파일명이 "<page_code>_"로 시작(대소문자 무시)하는 .java/.xml만
   - 예산 안에서 우선순위대로 채움: mapper XML → server 클래스 → Tab_(메인 화면) → 나머지(Edit_/Grid_/Lookup_/Move_ 팝업)
   - PER_FILE_CHAR_LIMIT(6000자)/TOTAL_CHAR_LIMIT(40000자) 넘으면 잘라내고 truncated=True
   - 결과: ToolResult(ok, data=[{path, content}, ...], truncated)
        │
        ▼
context/analyzer.py : summarize_page(page_code)
   - 위 파일들을 이어붙여 프롬프트 구성 (★ 지시사항은 코드 "뒤"에 배치 - 3번 참고)
   - ollama_client.chat()으로 qwen2.5-coder 호출
   - 화면개요/필드-그리드/이벤트-API호출/연관테이블/비즈니스로직 5개 섹션 마크다운 반환
        │
        ▼
cli.py : _prepare()
   - 캐시 경로: WORK_DIR/.yunhee/prep/<page_code>.md (project.PROJECT_DIR 재사용)
   - 캐시 있으면 그대로 출력 (qwen 재호출 없음)
   - --force: 캐시 무시하고 재생성
   - --show : 캐시만 출력, 없으면 에러 (생성 시도 안 함)
   - --delete: 캐시 삭제
```

## 4. 실제 검증 결과 (`ast01` 페이지 기준)

- 실측 파일 수: 18개(client 17개 + server 1개 + mapper 1개). 예산(40,000자) 안에는 보통 7개 정도(mapper+server+Tab_ 5개)가 들어감.
- **처음엔 지시사항을 소스 코드 "앞"에 뒀더니 qwen이 지시를 무시하고 관계없는 Java 코드를 이어쓰기(completion)해버렸다.** 지시사항을 소스 뒤로 옮기고 마크다운 헤더 형식(`## 화면 개요` 등)을 명시하니 정상적으로 요약을 따라 만들었다. → **로컬 코드 모델에게 긴 코드+지시를 같이 줄 때는 지시를 맨 뒤에 두는 게 중요**, 앞으로 프롬프트 만들 때 이 원칙 유지할 것.
- 캐시 재사용은 ~1초, `--force` 재생성(실제 qwen 호출)은 약 27초 걸림.

## 5. 알려진 문제: qwen의 mapperName/sqlId 환각

`ast01` 요약에서 qwen이 `mapperName: ast.Ast01_ClassTree`, `sqlId: insertRow/update/deleteRow` 같은 걸 만들어냈는데, 실제로는:
- 진짜 namespace는 `ast01_class_tree` (자바 클래스명 흉내가 아니라 mapper XML의 `namespace` 속성 그대로)
- 진짜 sql_id는 `insert`, `infoUpdate`, `modelUpdate`, `updateParentId` 등
- `ast.Ast02_DetailModel`은 완전 날조가 아니라 **다른 페이지(`ast02_detail`)의 진짜 mapper를 ast01 것처럼 잘못 갖다 붙인 것**이었다 (크로스오버 환각).

이걸 기계적으로 잡아내기 위해 검증용 인덱스를 만들어뒀다 (아래 6번). **아직 analyzer.py에 실제 검증 패스로 연결하지는 않았음 — 다음 할 일.**

## 6. `tools/parse_mapper.py` — mapper 인덱스 (grounding용, 구현 완료)

```bash
uv run tools/parse_mapper.py
```

- ASIS_SRC_DIR 아래 `mapper/*.xml`(944개)을 전부 파싱해서 `data/db/yunhee.db`의 `mapper_index` 테이블에 저장.
- 스키마: `mapper_index(mapper_name, sql_id, sql_type, tables, file_path)`, PK는 `(mapper_name, sql_id)`.
- `tables`는 SQL 텍스트에서 `from/join/into/update` 뒤에 오는 밑줄 포함 소문자 식별자를 정규식으로 뽑은 것(완벽하지 않은 휴리스틱, `<include>`로 재사용되는 공통 SQL 조각까지 재귀적으로 풀어내지는 않음).
- 실행 결과: SQL statement 3,294개, 파싱 실패 0건, 0.3초.
- 실제로 위 5번의 환각을 이 테이블로 대조해서 잡아낼 수 있음을 확인함 (`SELECT * FROM mapper_index WHERE mapper_name LIKE '%ast02%detail%'`로 크로스오버 환각 확인).
- ASIS 소스가 바뀌면(브랜치 갱신 등) 다시 실행해서 인덱스를 갱신해야 함 — 아직 staleness 체크(파일 mtime 등)는 없음.

## 7. 2차 구현 내용 (2026-09-26)

설계서 "다음 할 일" 1~3번 + 보안 취약점 수정을 구현함.

### 7-1. 보안: `page_code` 입력 검증

`validate_page_code(page_code)` (`tools/legacy_page.py`) — allowlist `[a-zA-Z0-9_-]+`로 검증.  
`../etc`, `ast01/../evil`, `ast01;drop` 등 path traversal·injection 패턴 전부 차단.  
`cli.py`의 `_prepare()`에서 캐시 경로 생성 전에 호출.

### 7-2. Model/VO 파일 tier 수정

`_priority()` 함수에서 `/model/` 경로 파일을 tier 3 → **tier 1**로 올림.  
`Ast01_ClassTreeModel.java`, `Ast01_ClassTreeModelProperties.java` 등 DTO/VO 클래스가  
40,000자 예산 내에서 server 클래스와 동급 우선순위로 담기게 됨.  
(Spring Boot 마이그레이션 시 Entity/DTO 구조 파악에 필수.)

변경 후 `ast01` 우선순위 실측:
```
tier 0  application/.../mapper/ast01_class_tree.xml
tier 1  application/.../model/Ast01_ClassTreeModel.java
tier 1  application/.../model/Ast01_ClassTreeModelProperties.java
tier 1  application/.../server/ast/Ast01_ClassTree.java
tier 2  application/.../Ast01_Tab_ClassTreeIntrinsic.java
...
```

### 7-3. Grounding 검증 패스 (`tools/mapper_verify.py` 신규 + `analyzer.py` 연결)

**`tools/mapper_verify.py`**:
- `extract_mapper_refs(summary)` — `namespace.sqlId` 패턴(`[a-z][a-z0-9]*(?:_[a-z0-9]+)+\.[a-zA-Z][a-zA-Z0-9_]*`)으로 요약 전체에서 쌍 추출.
- `verify_mapper_refs(refs)` — `mapper_index`에 없는 쌍을 반환. mapper_name은 있지만 sql_id가 없으면 실제 sql_id 목록도 함께 반환 (교정 힌트용). DB 없으면 빈 리스트 반환(graceful skip).
- `check_staleness()` — `mapper_index_meta.built_at`(float, epoch) vs ASIS mapper/*.xml 최신 mtime 비교. stale이면 `(True, 경고 메시지)` 반환.

**`analyzer.py`의 grounding 흐름**:
```
summarize_page() 호출
  → (단일 패스 or 2단계) qwen 요약 생성
  → extract_mapper_refs(summary) 로 (namespace, sql_id) 쌍 추출
  → verify_mapper_refs(refs) 로 DB 조회
  → invalid 존재 시 교정 프롬프트 구성 → qwen 재질의 (1회)
  → 교정된 요약 반환 + 메타에 "환각 감지 → 교정됨" 기록
```

교정 프롬프트 전략: 환각 항목 + 해당 mapper_name의 실제 sql_id 목록을 함께 제시해 qwen이 정확한 값으로 대체할 수 있게 함.

### 7-4. 2단계 요약 (`--two-stage`)

`find_all_page_files(page_code)` (`tools/legacy_page.py` 신규) — 총량 40,000자 제한 없이 전체 파일 반환. 파일별 6,000자 제한은 유지.

2단계 흐름:
1. 각 파일마다 `FILE_MINI_PROMPT_TEMPLATE`으로 mini-summary (3줄, mapper면 namespace·sql_id·테이블, Java면 클래스역할·메서드·호출 sqlId)
2. 모든 mini-summary를 `COMBINE_PROMPT_TEMPLATE`으로 최종 5섹션 요약으로 합산

`ast01` 기준: 단일 패스 8파일 → 2단계 **18파일** 전부 반영. truncation 없음.  
대신 qwen 호출 횟수 18+1=19회로 증가 → 시간 대폭 증가.

### 7-5. Staleness 체크 (`tools/parse_mapper.py` 수정)

`mapper_index_meta` 테이블 추가 (`key TEXT PK, built_at REAL`).  
`build_index()` 완료 시 `time.time()`을 `built_at` 키에 저장.  
이후 `check_staleness()`가 이 값과 ASIS 소스 mtime을 비교.

## 8. 사용법 (현재 기준)

```bash
# 기본 실행 (단일 패스 + grounding, 캐시 재사용)
yunhee prepare ast01
yunhee prep ast01

# 강제 재생성
yunhee prepare ast01 --force

# 2단계 요약 (전체 18파일, 느림 ~3-5분)
yunhee prepare ast01 --two-stage --force

# grounding 없이 빠르게
yunhee prepare ast01 --no-grounding --force

# 캐시 조회/삭제
yunhee prepare ast01 --show
yunhee prepare ast01 --delete

# mapper_index 빌드 (최초 1회, ASIS 소스 변경 시 재실행)
uv run tools/parse_mapper.py
```

**grounding 활성화 전제**: `mapper_index`가 없으면 grounding 패스는 자동 skip (경고 메시지 표시).  
ASIS 소스가 인덱싱 이후 변경됐으면 요약 메타에 재실행 권장 메시지 출력.

## 9. 남은 할 일

1. (보류 중, 아직 근거 부족) chromadb 기반 legacy_scanner/chunker(Phase 1), tracker(Phase 4) — `docs/yunhee-cli-설계.md` 참고. framework-sprt에 실제 변환 예시가 쌓이기 전까지는 우선순위 낮음.

## 10. 관련 파일 위치 (요약)

| 파일 | 역할 |
|---|---|
| `src/yunhee/config.py` | `ASIS_SRC_DIR` (env: `YUNHEE_ASIS_SRC_DIR`) |
| `src/yunhee/tools/base.py` | `ToolResult` 공통 스키마 |
| `src/yunhee/tools/legacy_page.py` | 페이지 코드 → 파일 목록+내용 (예산/우선순위/입력검증), `find_all_page_files` |
| `src/yunhee/tools/mapper_verify.py` | grounding 검증 (`extract_mapper_refs`, `verify_mapper_refs`), staleness 체크 |
| `src/yunhee/context/analyzer.py` | qwen 요약 (단일 패스 / 2단계), grounding 교정 루프 |
| `src/yunhee/cli.py` (`_prepare`) | `prepare`/`prep` 커맨드, 캐시(`--force`/`--show`/`--delete`/`--two-stage`/`--no-grounding`) |
| `tools/parse_mapper.py` | mapper XML → `mapper_index` + `mapper_index_meta`(staleness용 타임스탬프) |
| `tests/test_legacy_page.py` | `find_page_files` 순수 로직 테스트 |
