# `yunhee screen-capture` 설계 및 구현 계획서

TOBE(Spring Boot + React)로 변환된 화면들의 시각적·기능적 품질(레이아웃, 그리드 데이터 바인딩, 탭 전환, 팝업/Lookup 오픈, 콘솔/네트워크 에러)을 자동으로 검수하기 위한 **`yunhee screen-capture`** 명령어를 구현합니다.

---

## 1. 명령어 인터페이스 (CLI UX)

```bash
# 기본 사용법 (위치 인자 login=... 및 옵션 --login 모두 지원)
uv run yunhee screen-capture <screen-id> login=kfstest/104/1111

# 옵션 지정 예시
uv run yunhee screen-capture 1018 login=kfstest/104/1111 \
  --url http://localhost:8082/AssetERP \
  --out .yunhee/screen-capture

# 클래스명으로 호출 (메뉴번호 자동 역추적 또는 FlexLayout 직접 오픈)
uv run yunhee screen-capture Fnd01_Tab_FundSearch --login kfstest/104/1111
```

### 인자 및 옵션 규격

| 인자 / 옵션 | 기본값 | 설명 |
| :--- | :--- | :--- |
| `<screen-id>` | (필수) | 화면번호(예: `1018`, `1051`) 또는 화면 클래스명(예: `Fnd01_Tab_FundSearch`, `Sys01_Tab_Company`) |
| `login=...` / `--login`, `-l` | `.env.local` 기본 계정 (`kfstest/104/1111` 등) | `<company>/<user>/<password>` 형식 (예: `login=kfstest/104/1111`). 비밀번호 생략 시(`kfstest/104`) DB(`emp01_person`)에서 자동 조회 |
| `--url` | `http://localhost:8082/AssetERP` | 접속할 TOBE 프론트엔드(또는 통합 서버) 기본 URL (`YUNHEE_CAPTURE_URL` 환경변수 호환) |
| `--out`, `-o` | `.yunhee/screen-capture` | 캡처 루트 폴더. 실제 파일은 **`<out>/<화면폴더>/`** 하위에 격리 저장 |
| `--title` | 자동 탐색 | 겸직선택(`Emp04_Lookup_AddTitleList`) 시 특정 부서명/직책명/사원ID를 강제 지정하고 싶을 때 사용 (미지정 시 대상 화면 권한이 있는 겸직을 자동 선택) |
| `--no-popups` | `False` | 팝업/모달 클릭 순회를 생략하고 본 화면(초기/조회/행선택/탭)만 빠르게 캡처 |
| `--headed` | `False` | 디버깅용 브라우저 창 표시 여부 (기본은 Headless Chromium) |
| `--viewport` | `1920x1080` | 브라우저 해상도 지정 |

---

## 2. 저장 폴더 및 파일 구조 (`--out` 하위 화면별 격리)

화면 수가 많아져도 섞이지 않도록 `--out` 아래에 **`<화면식별자>` 하위 폴더**를 생성합니다.
- 메뉴번호와 클래스명이 모두 확인되면 `<menuNo>_<classNm>` 또는 요청한 `<screen-id>`로 폴더를 생성합니다 (예: `.yunhee/screen-capture/1018_Apr01_Tab_MyApproveList/` 또는 `.yunhee/screen-capture/1018/`).

```text
.yunhee/screen-capture/
└── 1018_Apr01_Tab_MyApproveList/
    ├── 01_initial.png              # 화면 최초 오픈 상태
    ├── 02_searched.png             # [조회] 버튼 클릭 및 API 응답 완료 후 상태
    ├── 03_row_selected.png         # 그리드 첫 번째 행 선택 후 (우측/하단 폼·탭 바인딩 확인)
    ├── 04_tab_01_기본정보.png       # 화면 내 서브 탭이 있는 경우 각 탭 전환 캡처
    ├── 05_popup_01_신규등록.png     # [신규]/[등록] 등 모달 오픈 캡처
    ├── 06_lookup_01_사원찾기.png    # 돋보기(Lookup) 트리거 클릭 모달 캡처
    └── report.json                 # 실행 메타데이터, 캡처 목록, 콘솔 에러, 실패한 API(4xx/5xx) 기록
```

---

## 3. 전체 실행 파이프라인 아키텍처

1. **CLI 실행 및 로그인 정보 파싱**
   - `login=kfstest/104/1111` → `company="kfstest"`, `user="104"`, `password="1111"` 분리
   - 테넌트 서브도메인 URL 변환: `http://localhost:8082/AssetERP` → `http://kfstest.localhost:8082/AssetERP`
2. **사전 API/메타 탐색 (`httpx`)**
   - 로그인 및 겸직 목록(`GET /api/v1/emp/add-titles/login-list`) 확인
   - 각 겸직별 메뉴(`GET /api/v1/sys/menus`)를 대조해 요청한 `<screen-id>`(화면번호 또는 클래스명)를 보유한 겸직(`addPersonId`)을 자동 판별
3. **Playwright 브라우저 기동 & 로그인 통과**
   - `LoginPage` 로그인 수행 (또는 세션 주입)
   - 비밀번호 변경 권고 모달("N일 남았습니다. 지금 변경하시겠습니까?") 발생 시 `[아니오]` 자동 클릭
4. **겸직선택 Gate (`Emp04_Lookup_AddTitleList`) 통과**
   - `'로그인 선택'` 모달이 뜨면 2단계에서 찾은 대상 화면 권한 보유 겸직 행을 선택하고 `[확인]` 클릭
   - 로그인 직후 뜨는 출퇴근 기록 창(`Att02_Lookup_Commute`)이 있으면 자동 닫기
5. **대상 화면 오픈 (2중 전략)**
   - **① TopBar 검색창 Enter**: 상단바 `화면번호/메뉴명 (Enter)` 입력창에 화면번호(`menuNo`)를 입력하고 `Enter`로 탭 오픈
   - **② FlexLayout Deeplink 주입 (Fallback)**: 메뉴에 안 걸려 있는 화면(`screens.ts`에는 등록된 클래스)인 경우 `localStorage`의 `asseterp_settings.flexlayout_model`에 탭 노드를 직접 주입해 100% 오픈
6. **단계별 자동 인터랙션 & 캡처 (Safety Filter 적용)**
   - `01_initial.png`: 화면 최초 오픈 직후
   - `02_searched.png`: `[조회]`/`[검색]` 버튼 클릭 및 네트워크 유휴 대기 후
   - `03_row_selected.png`: AG Grid 첫 번째 행 클릭 후 (상세 폼/서브 그리드 바인딩 확인)
   - `04_tab_*.png`: 화면 내부 `.ant-tabs-tab` 순회 클릭
   - `05_popup_*.png` / `06_lookup_*.png`:
     - **클릭 허용**: 돋보기 Lookup 아이콘, `등록`/`신규`/`추가`/`수정`/`상세`/`변경`/`이력`/`설정`/`찾기`/`선택`/`보기` 등 팝업 오픈 버튼
     - **클릭 금지(블랙리스트)**: `저장`, `삭제`, `취소`, `확정`, `승인`, `반려`, `마감`, `엑셀`, `다운로드`, `업로드`, `발송`, `출력`, `인쇄`, `초기화`, `생성`, `복사`
     - 모달(`.ant-modal-content:visible`)이 열리면 캡처 후 `[닫기]` 또는 `ESC`로 닫고 다음 버튼으로 진행
7. **품질 리포트 생성**
   - 이미지 파일들과 `report.json` 저장, 터미널에 캡처된 파일 목록 및 콘솔 에러 / 실패한 API(4xx/5xx) 요약 출력

---

## 4. 변경 및 추가될 파일 목록

1. `pyproject.toml`: `playwright` 의존성 추가 (`uv add playwright && uv run playwright install chromium`)
2. `src/yunhee/config.py`: `CAPTURE_BASE_URL` (`YUNHEE_CAPTURE_URL`, 기본 `http://localhost:8082/AssetERP`) 및 `CAPTURE_OUT_DIR` (`.yunhee/screen-capture`) 설정 추가
3. `src/yunhee/tools/screen_capture.py` **(신규)**: 로그인/겸직 탐색 및 Playwright 캡처 엔진 구현
4. `src/yunhee/cli.py`: `yunhee screen-capture` 서브커맨드 등록
5. `tests/test_screen_capture.py` **(신규)**: 단위 테스트 작성
6. `docs/help/`: 도움말 문서 업데이트
