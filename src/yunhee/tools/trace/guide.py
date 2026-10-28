"""trace-guide: 에이전트용 업무파악 워크플로우 지침 (`agent-guide`의 업무파악판).

명령 목록은 등록된 `trace-*` 명령에서 읽는다 (코드와 지침이 어긋나지 않게). 나머지는 에이전트가 따를 원칙과 순서다.
"""

from __future__ import annotations

from yunhee.tools.trace.render import TraceResult

GROUPS: list[tuple[str, list[str]]] = [
    ("탐색 — 어디서부터 볼까", ["trace-map", "trace-menu", "trace-screen"]),
    ("데이터 — 이 데이터는 누가 만들고 바꾸나", ["trace-table", "trace-column", "trace-code", "trace-state", "trace-crud"]),
    ("규칙 위치 — 조건이 걸린 곳은 어디인가", ["trace-flow", "trace-branch", "trace-dblogic"]),
    ("ASIS↔TOBE 대조 — 제대로 옮겨졌나", ["trace-pair", "trace-diff", "trace-gap"]),
    ("카탈로그 — 판정을 저장하고 문서로", ["trace-rule", "trace-term", "trace-doc", "trace-guide"]),
]


def registered_commands() -> dict[str, str]:
    """등록된 trace-* 명령 → 한 줄 설명 (명령 함수의 docstring 첫 줄)."""
    from yunhee.cli import app

    out: dict[str, str] = {}
    for c in app.registered_commands:
        if c.name and c.name.startswith("trace-"):
            doc = (c.help or (c.callback.__doc__ if c.callback else "") or "").strip().splitlines()
            out[c.name] = doc[0].strip() if doc else ""
    return out


def trace_guide() -> TraceResult:
    cmds = registered_commands()
    res = TraceResult(
        command="trace-guide",
        description="에이전트용 업무파악 워크플로우 지침 (agent-guide의 업무파악판)",
        side="both",
        options={"document": True},
    )
    s = res.facts

    s.append(
        "# yunhee trace-* 업무파악 지침 (에이전트용)\n\n"
        "`trace-*`는 ASIS(GWT/GXT)와 TOBE(React/Spring) 소스, 스키마 스냅샷, mapper SQL을 **결정적으로** 읽어 업무를 파악하게 돕는 조회 명령이다. "
        "LLM이 만든 요약이 아니라 소스에서 뽑은 사실과 그 근거 위치를 낸다. 해석·서술·판정은 당신(에이전트)의 몫이고, "
        "판정은 `trace-rule`에 근거와 함께 남겨 나중에 다시 확인할 수 있게 한다."
    )

    s.append(
        "## 1. 출력을 읽는 법\n\n"
        "모든 명령은 같은 세 블록을 낸다 (`--format json`이면 같은 키).\n\n"
        "| 블록 | 뜻 | 어떻게 쓰나 |\n|:---|:---|:---|\n"
        "| `## facts` | 소스에서 뽑은 사실 | 그대로 인용해도 된다. 해석은 덧붙이지 말고 구분해서 적는다 |\n"
        "| `## evidence` | 사실의 근거 위치 (`파일:줄`, mapper id, 스냅샷 시각) | 확인이 필요하면 `yunhee cat 파일:시작-끝`으로 그 줄만 읽는다 |\n"
        "| `## unresolved` | **모른다**는 신호: 해석하지 못한 호출, `${}` 치환, 파싱 실패, 없는 소스 | 비어 있지 않으면 그 부분은 사실로 쓰지 말고 소스를 직접 확인한다 |\n\n"
        "- `--max N`: facts·evidence를 N개로 줄인다 (unresolved는 절대 숨기지 않는다). 토큰이 부족하면 먼저 `--max`를 쓴다.\n"
        "- `--side asis|tobe|both`: 어느 쪽을 볼지 (기본 both). `--tobe`: TOBE 프로젝트 루트 또는 `frontend/src`. `--src-index`: ASIS 색인 위치.\n"
        "- 종료 코드: `0` 정상 · `1` 대상을 못 찾음, 또는 `trace-rule verify`에서 근거가 깨짐(MISSING·STALE) · `2` 사용법 오류, 대상이 모호함(후보가 출력됨).\n"
        "- \"대응 없음\"(ASIS에만 있음)과 \"추적하지 못함\"(근거 주석이 없음)은 다르다. 후자는 unresolved에 따로 나온다."
    )

    s.append(
        "## 2. 준비물\n\n"
        "1. ASIS 색인: `yunhee index-src` → `docs/as-is/src` (화면·서비스·SQL·메뉴). 없으면 `--src-index`로 위치를 준다.\n"
        "2. 스키마 스냅샷: `yunhee make-dbml <ENV>` (사무실에서 한 번). 없으면 컬럼·테이블·DB 함수를 다루는 명령이 제한된다.\n"
        "3. TOBE 소스: 작업 폴더가 TOBE 프로젝트가 아니면 `--tobe <루트>`.\n"
        "4. DB(선택): `trace-code`·`trace-term`·`--stats`만 읽기 전용으로 접속한다. 사무실 밖이면 건너뛰고 unresolved에 사유를 남긴다."
    )

    flow = [
        ("범위를 잡는다", "`trace-map` → `trace-menu \"<메뉴 경로>\"` → 화면 번호(`#1029`)나 클래스명을 정한다"),
        ("화면을 파악한다", "`trace-screen #1029` (필드·그리드·이벤트·서비스·테이블) → 하위 탭은 `--class <클래스>`"),
        ("규칙이 걸린 곳을 찾는다", "`trace-flow #1029 -e E3` (이벤트 하나의 끝까지) · `trace-branch #1029` / `trace-branch <mapper id>` (조건 지점 전체)"),
        ("데이터를 이해한다", "`trace-table`, `trace-column`, `trace-code <그룹>`, 상태 컬럼은 `trace-state <테이블.컬럼>`, 영향 범위는 `trace-crud`"),
        ("ASIS와 TOBE를 대조한다", "`trace-pair #1029` (짝과 근거) → `trace-diff #1029 [--sql|--branch|--ui]` (차이) → `trace-gap -d <영역>` (빠진 것)"),
        ("판정을 저장하고 검증한다", "`trace-rule add <대상> -v <판정> --note … -E <근거> …` → 이후 `trace-rule verify`로 근거가 살아 있는지 확인"),
        ("문서로 남긴다", "`trace-doc <영역>`으로 골격을 만들고 `<!-- 서술(에이전트): … -->` 자리를 채운다"),
    ]
    s.append("## 3. 워크플로우\n\n" + "\n".join(f"{i}. **{t}** — {d}" for i, (t, d) in enumerate(flow, 1)) + "\n\n```\ntrace-map → trace-menu → trace-screen #1029\n  → trace-flow #1029 -e E3\n  → trace-branch #1029\n  → trace-diff #1029 --branch\n  → trace-state FND_MST.STAT_CD\n  → trace-rule add … → trace-rule verify\n```")

    rows = []
    seen = set()
    for title, names in GROUPS:
        rows.append(f"**{title}**\n" + "\n".join(f"- `yunhee {n}` — {cmds.get(n, '(미등록)')}" for n in names))
        seen.update(names)
    extra = sorted(set(cmds) - seen)
    if extra:
        rows.append("**그 밖에**\n" + "\n".join(f"- `yunhee {n}` — {cmds[n]}" for n in extra))
    s.append(f"## 4. 명령 ({len(cmds)}개)\n\n" + "\n\n".join(rows))

    s.append(
        "## 5. 지켜야 할 원칙 (환각을 막는다)\n\n"
        "- **근거 없이 단정하지 않는다.** 사실은 facts에서 인용하고, 근거는 evidence의 위치를 적는다. unresolved에 있는 것은 사실로 쓰지 않는다.\n"
        "- **판정은 `trace-rule add`로 남긴다.** `add`는 근거로 적은 파일·줄·mapper 문장이 실제로 있는지 읽어 확인하고, 없으면 저장을 거부한다. 거부되면 위치를 잘못 안 것이다.\n"
        "- **저장한 규칙은 믿기 전에 `verify`한다.** `MOVED`(줄만 이동)는 안전하지만 `STALE`(내용이 바뀜)·`MISSING`은 규칙을 다시 확인해야 한다. 확인했다면 `verify R-NNN --accept`로 갱신한다.\n"
        "- **짝은 근거가 있는 것만 믿는다.** `trace-pair`/`trace-diff`의 짝은 TOBE 주석의 `AS-IS`와 같은 이름·테이블 조합을 근거로 짓고, \"약한 근거\"는 그렇게 표시된다.\n"
        "- **차이는 의도가 아니다.** `trace-diff`는 다른 점만 낸다. 의도적 변경인지 누락인지는 판정해 `trace-rule`에 사유와 함께 남긴다.\n"
        "- **개인정보를 옮겨 적지 않는다.** `trace-column --stats`는 코드성 컬럼(고유 값 30종 이하)의 값만 낸다. 그 밖의 값은 필요해도 직접 조회하지 않는다.\n"
        "- **읽기 전용이다.** 유일한 쓰기는 `trace-rule`이 로컬 sqlite(`data/db/yunhee.db`)에 판정을 저장하는 것이다."
    )

    s.append(
        "## 6. 알려진 한계\n\n"
        "- TOBE 호출 체인(TSX → api → 컨트롤러 → 서비스 → mapper)은 정규식으로 읽는다. 규약에서 벗어난 코드는 unresolved로 빠진다.\n"
        "- PostgreSQL 문법이 아닌 ASIS mapper(Tibero 계층 쿼리 등)는 정규식 추정으로 되돌리고 그렇다고 표시한다. `isTibero` 분기의 테이블은 제외된다.\n"
        "- 화면 분기(`trace-diff --branch`)는 Java와 React의 식이 달라 대응이 적게 나온다. 대응이 없다고 구현이 빠진 것은 아니다.\n"
        "- `UpdateDataModel`의 동적 쓰기는 어떤 컬럼에 무엇을 쓰는지 SQL로 알 수 없다 (서비스 목록만 낸다)."
    )

    res.evidence.append(f"명령 {len(cmds)}개는 등록된 trace-* 명령에서 읽음")
    return res
