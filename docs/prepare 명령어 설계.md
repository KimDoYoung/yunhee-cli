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

## 7. 다음 할 일 (미구현, 우선순위 순)

1. **grounding 검증 패스를 `analyzer.py`에 연결.** `summarize_page()`가 만든 요약에서 mapperName/sqlId를 정규식/패턴으로 뽑아 `mapper_index`에 실제로 존재하는지 조회 → 없으면 그 사실을 qwen에게 다시 보여주고 "이 항목은 원본에 없다, 삭제하거나 고쳐라"로 재질의(재검증 루프). 로컬 모델이라 전기값만 들지 비용이 안 드니 반복 호출에 부담 없음.
2. **파일별 분할 요약(2단계 요약).** 지금은 7개 파일을 한 프롬프트에 우겨넣고 나머지 11개는 통째로 버리는데, 대신 mapper/server/Tab_ 파일 각각을 개별적으로 작게 요약(작은 컨텍스트 → 지시 순응도 높음, 4번 항목에서 이미 확인된 효과)한 뒤 마지막에 합치면 18개 파일을 전부 반영하면서 truncation도 사실상 없앨 수 있음.
3. **mapper_index staleness 체크** — ASIS 소스 변경 감지 후 자동/수동 재인덱싱.
4. (보류 중, 아직 근거 부족) chromadb 기반 legacy_scanner/chunker(Phase 1), tracker(Phase 4) — `docs/yunhee-cli-설계.md` 참고. framework-sprt에 실제 변환 예시가 쌓이기 전까지는 우선순위 낮음.

## 8. 관련 파일 위치 (요약)

| 파일 | 역할 |
|---|---|
| `src/yunhee/config.py` | `ASIS_SRC_DIR` (env: `YUNHEE_ASIS_SRC_DIR`) |
| `src/yunhee/tools/base.py` | `ToolResult` 공통 스키마 |
| `src/yunhee/tools/legacy_page.py` | 페이지 코드 → 파일 목록+내용 (예산/우선순위 적용) |
| `src/yunhee/context/analyzer.py` | qwen 요약 프롬프트 + 호출 |
| `src/yunhee/cli.py` (`_prepare`) | `prepare`/`prep` 커맨드, 캐시(`--force`/`--show`/`--delete`) |
| `tools/parse_mapper.py` | mapper XML → `data/db/yunhee.db`의 `mapper_index` (grounding용, 독립 실행 스크립트) |
| `tests/test_legacy_page.py` | `find_page_files` 순수 로직 테스트 |
