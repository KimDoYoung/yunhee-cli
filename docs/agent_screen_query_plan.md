# Local LLM Agent 자율 Python 코드 생성·실행 기반 화면 탐색 구현 계획

## Goal Description
사용자가 `TOBE/ASIS` 구분이나 `frontend/backend` 위치, 출력 항목(`파일명, 메뉴명, 화면번호 알려줘`)을 일일이 지정하지 않고 아래처럼 **짧고 자연스럽게 질문**하더라도:
- *"제목이 '계정과목'인 모달 찾아줘"*
- *"grid의 column 중 체크박스이면서 제목이 한글 3글자인 화면 찾아줘"*
- *"act01_account_code 테이블을 삭제하는 화면 찾아줘"*

에이전트(`qwen2.5-coder:14b`)가:
1. **기본적으로 TOBE를 대상**으로 삼고 (사용자가 'AS-IS/원본'을 명시한 경우만 AS-IS 탐색),
2. **질문 맥락에 따라 Frontend(TSX/UI)와 Backend(Controller/Service/Mapper)를 스스로 판단·연결**하여 Python 스크립트를 작성·실행(`execute_python`)한 뒤,
3. 별도 지시가 없어도 항상 **`[화면번호(#번호), 메뉴명(경로), 파일명(경로), 일치 상세]`**를 기본 표 양식으로 보여주는 기능을 구현합니다.

```mermaid
sequenceDiagram
    actor User as 사용자
    participant Loop as AgentLoop (Qwen2.5-Coder:14B)
    participant PyTool as execute_python 도구
    participant Catalog as screen_catalog (TOBE 기본, FE+BE 통합)

    User->>Loop: "제목이 '계정과목'인 모달 찾아줘"
    Note over Loop: 1. 기본값 = TOBE 자동 적용<br/>2. '모달/그리드/버튼' → FE, 'API/테이블/SQL' → BE 자동 판단<br/>3. Python 검색 스크립트 생성
    Loop->>PyTool: execute_python(code="...")
    PyTool->>Catalog: iter_screens() 실행 (기본 side="tobe")<br/>FE(pages, lookup) ↔ BE(controller, service, mapper) ↔ 메뉴(#번호) 자동 매핑
    Catalog-->>PyTool: STDOUT (#1001 | 회계관리 > ... > 계정과목관리 | Act01_Lookup_AccountTree.tsx | ...)
    PyTool-->>Loop: 실행 결과 반환
    Loop->>User: 기본 포맷(화면번호, 메뉴명, 파일명, 상세내역) 마크다운 표 출력
```

---

## 핵심 UX 원칙 (사용자 무지칭 자동화)

> [!IMPORTANT]
> **1. 기본 타겟은 항상 `TOBE` (`side="tobe"` 기본값)**
> - 사용자가 `"TOBE에서"`라고 말하지 않아도 무조건 TOBE 소스를 기본 검색합니다.
> - 사용자가 `"AS-IS에서"`, `"구버전에서"`, `"원본에서"`라고 명시할 때만 `side="asis"` 또는 `"both"`로 동작합니다.
>
> **2. `frontend` / `backend` 무지칭 자동 탐색 (FE ↔ BE 통합 카탈로그)**
> - 사용자는 찾고자 하는 대상이 프론트엔드에 있는지 백엔드에 있는지 몰라도 됩니다.
> - `ScreenRecord` 객체 하나에 **프론트엔드 정보**(모달, 그리드 컬럼, 버튼, TSX 경로)와 **백엔드 연결 정보**(호출 API URL, Controller/Service 메서드, MyBatis SQL ID, 참조 DB 테이블)가 함께 묶여 있어 에이전트가 한 번에 조회합니다.
>
> **3. 결과 출력 시 `[화면번호, 메뉴명, 파일명]` 기본 출력**
> - 사용자가 *"파일명, 메뉴명, 화면번호 알려줘"*라고 덧붙이지 않아도, 화면/컴포넌트 탐색 결과는 언제나 **`#화면번호 | 메뉴명(경로) | 파일명 | 일치 조건`**을 기본 컬럼으로 출력합니다.

---

## Proposed Changes

### 1. Agent 코드 실행기 (`execute_python`) 추가

#### [MODIFY] [core_exec.py](file:///home/kdy987/work/yunhee-cli/src/yunhee/agent/tools/core_exec.py)
- `execute_python(code: str, description: str = "", timeout_seconds: int = 30) -> str` 함수를 추가합니다.
- 마크다운 코드 펜스(` ```python ... ``` `) 자동 제거 및 `WORK_DIR/.yunhee/scratch/agent_script_<timestamp>.py` 저장.
- `PYTHONPATH`에 `yunhee-cli`의 `src` 경로를 자동 주입하여 어느 폴더에서 실행하든 `yunhee.tools.trace.screen_catalog`를 import 가능하게 합니다.
- 에러 발생 시 Traceback을 `STDERR`로 반환하여 Qwen 14B가 즉시 코드를 수정해 재실행(Self-healing)할 수 있게 합니다.

#### [MODIFY] [registry.py](file:///home/kdy987/work/yunhee-cli/src/yunhee/agent/registry.py)
- `create_default_registry()`에 `execute_python` 도구를 등록합니다.

---

### 2. TOBE 기본 & FE+BE 통합 화면 카탈로그 (`screen_catalog.py`)

#### [MODIFY] [tobe.py](file:///home/kdy987/work/yunhee-cli/src/yunhee/tools/trace/tobe.py)
- `GridCol` 데이터클래스를 도입하여 컬럼 타입(`boolean`, `booleanYn2`, `text`, `date` 등), 필드명, 라벨, 너비를 보존합니다.
- 기존 코드(`diff.py`, `term.py`, `column.py`)와의 호환성을 위해 `(field, label)` 2-튜플을 상속합니다.

#### [NEW] [screen_catalog.py](file:///home/kdy987/work/yunhee-cli/src/yunhee/tools/trace/screen_catalog.py)
- **`iter_screens(side: str = "tobe") -> list[ScreenRecord]`**: 기본값을 `"tobe"`로 설정합니다.
- 각 `ScreenRecord`는 Frontend와 Backend, 메뉴 정보를 하나로 묶어 제공합니다:
  - **메뉴/식별 정보 (자동 역추적)**:
    - `name`: 컴포넌트/화면명 (예: `Act01_Lookup_AccountTree`)
    - `file`: 파일 경로 (예: `frontend/src/pages/act/Act01_Lookup_AccountTree.tsx`)
    - `menu_no`: 화면번호 (예: `'1001'`, 팝업/모달인 경우 이를 import해서 여는 상위 `_Tab_` 화면을 역추적하여 자동 부여)
    - `menu_path`: 메뉴 경로 (예: `'회계관리 > 기본정보 > 계정과목관리'`)
    - `opening_tabs`: 상위 `_Tab_` 화면 클래스 목록
  - **Frontend UI 정보**:
    - `modals`: `[ModalInfo(kind='LookupModal'|'Modal'|'confirm', title='계정과목', line=95)]`
    - `grid_cols`: `[GridCol('fssYn', '금감원', col_type='boolean', width=50), ...]`
    - `buttons`: 버튼 라벨 목록
    - `text`: TSX 원본 소스 텍스트
  - **Backend 연계 정보 (`TobeIndex` 연동)**:
    - `apis`: 호출하는 API 목록 (예: `['GET /api/v1/act/account-codes']`)
    - `backend_files`: 연결된 Controller / Service / Mapper XML 파일 경로 목록
    - `sql_ids`: 연결된 MyBatis SQL ID 목록
  - **기본 포맷 헬퍼 (`s.format_hit(detail: str)`)**:
    - `print(s.format_hit(f"모달 제목: {m.title}"))` 한 줄만 호출하면 자동으로 `#1001 | 회계관리 > 기본정보 > 계정과목관리 | Act01_Lookup_AccountTree (frontend/src/pages/act/Act01_Lookup_AccountTree.tsx) | 모달 제목: 계정과목` 문자열을 생성합니다.

---

### 3. 에이전트 시스템 프롬프트 고도화

#### [MODIFY] [loop.py](file:///home/kdy987/work/yunhee-cli/src/yunhee/agent/loop.py)
- `DEFAULT_SYSTEM_PROMPT`에 다음 규칙을 명시합니다:
  1. **기본 타겟**: 사용자가 'AS-IS'나 '원본'을 명시하지 않으면 **항상 TOBE(`iter_screens()` 기본값)**를 검색한다.
  2. **FE/BE 자동 판단**: 모달·그리드·버튼·입력창 등 UI 조건은 `s.modals`, `s.grid_cols`, `s.buttons`, `s.text`에서 찾고, API·SQL·백엔드 조건은 `s.apis`, `s.sql_ids`, `s.backend_files` 또는 백엔드 디렉터리에서 자동으로 찾는다.
  3. **표준 출력 양식**: 사용자가 별도로 요구하지 않아도 화면/컴포넌트 검색 결과는 반드시 **`[화면번호(#), 메뉴명(경로), 파일명(경로), 일치 상세]`** 마크다운 표로 정리해 답변한다.

---

### 4. CLI 진입점 확장 (`yunhee agent` / `yunhee ask -a` 및 `yunhee trace-grid`)

#### [MODIFY] [cli.py](file:///home/kdy987/work/yunhee-cli/src/yunhee/cli.py)
- `yunhee agent "<질문>"` (및 `yunhee ask -a "<질문>"`) 명령어를 추가하여 아래와 같이 간단히 질문할 수 있도록 지원합니다:
  ```bash
  uv run yunhee agent "제목이 '계정과목'인 모달 찾아줘"
  uv run yunhee agent "그리드 컬럼 중 체크박스이면서 제목이 한글 3글자인 화면 찾아줘"
  ```

#### [NEW] [grid_search.py](file:///home/kdy987/work/yunhee-cli/src/yunhee/tools/trace/grid_search.py) & [MODIFY] [__init__.py](file:///home/kdy987/work/yunhee-cli/src/yunhee/tools/trace/__init__.py)
- LLM을 거치지 않는 결정적 CLI 명령어 `yunhee trace-grid`도 기본값 `side="tobe"`로 함께 등록합니다.

#### [MODIFY] [trace.md](file:///home/kdy987/work/yunhee-cli/docs/help/trace.md)
- `trace-grid` 및 `agent` 검색 사용법을 문서화합니다.

---

## Verification Plan

### Automated Tests
1. **단위 테스트 (`tests/test_screen_catalog_and_agent_exec.py`)**:
   - `iter_screens()` 호출 시 인자 생략해도 기본 `side="tobe"`로 동작하는지 검증
   - `s.format_hit(...)` 호출 시 `#화면번호 | 메뉴명 | 파일경로 | 상세내역`이 누락 없이 출력되는지 검증
   - 팝업(`LookupModal`, `Modal`)에서 상위 `_Tab_` 화면의 메뉴 번호(`#1001` 등)가 자동 역추적되는지 검증
   - `execute_python` 도구의 정상 실행 및 에러 반환 검증
   ```bash
   uv run pytest tests/test_screen_catalog_and_agent_exec.py -v
   uv run ruff check .
   ```

### Manual Verification
1. **짧은 자연어 질의 테스트 1 (모달 검색)**:
   ```bash
   uv run yunhee agent "제목이 '계정과목'인 모달 찾아줘"
   ```
2. **짧은 자연어 질의 테스트 2 (그리드 조건 검색)**:
   ```bash
   uv run yunhee agent "grid의 column 중 체크박스이면서 제목이 한글 3글자인 화면 찾아줘"
   ```
   - 두 경우 모두 `TOBE`나 `frontend`, `파일명/메뉴명/화면번호`를 언급하지 않았음에도 자동으로 TOBE에서 찾아내어 화면번호(`#`), 메뉴명, 파일명을 표로 출력하는지 확인합니다.
