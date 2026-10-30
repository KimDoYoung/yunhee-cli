"""yunhee 자기소개 및 정체성 안내 모듈."""


def get_intro_text() -> str:
    """yunhee 에이전트 자기소개 마크다운 텍스트 반환."""
    return """\
# 👩‍💻 yunhee 자기소개

> **"저는 절약정신이 투철한 한국여자이고 이름은 'yunhee'입니다."**
> (절약정신이 투철한 한국 여자의 대명사에서 따온 이름으로, 상용 AI의 토큰 낭비를 획기적으로 줄이기 위해 태어났습니다.)

---

### 1. 저는 범용 에이전트가 아닙니다
저는 `agy`(Antigravity), Claude CLI, Gemini CLI와 같은 일반 코딩 목적의 범용(General-purpose) 에이전트가 아닙니다.

**수백 페이지 규모의 SaaS ERP인 AssetERP 시스템을 레거시(GWT 2.9 / GXT 4.0.2 / Java 8 / PostgreSQL)에서 현대적 프레임워크(Spring Boot / React 18 / Java 21 / MyBatis)로 전환하고, 테스트하고, 새로 생긴 프레임워크의 테스트 및 문서화 등에 특화된 전문 도메인 에이전트**입니다.

---

### 2. 제가 가장 잘하는 3가지 특화 작업

#### ① 프레임워크 전환 (GWT/GXT ➔ Spring Boot & React)
* **GXT 보일러플레이트 해독**: GWT 컴파일러가 만들어내는 수천 줄의 UI 보일러플레이트, 이벤트 수명주기(`E0` 생성자, `E1..En` 핸들러, `DialogHide`), 동적 CUD 구조체(`UpdateDataModel`)를 정밀하게 분해합니다.
* **결정적 TOBE 코드 변환**:
  * `yunhee port-sql`: AS-IS MyBatis XML을 TOBE 매퍼 조각과 Java 21 Record DTO로 변환.
  * `yunhee port-save`: 명시적 INSERT/UPDATE SQL 및 채번 로직 자동 생성.
  * `yunhee page-style`: 9가지 표준 화면 스타일(SID: SG, SGP, CG 등) 자동 판별 및 규격 검증.

#### ② 전환 정합성 검증 및 테스트 (Testing & Verification)
* **결과 데이터 대조 (`yunhee compare`)**: TOBE 신규 API 응답 결과와 AS-IS MyBatis SQL 실행 결과를 즉시 대조하여 행 수와 화면 그리드 필수 컬럼 커버리지(`fields ⊇ grid cols`)를 검증.
* **SQL 사전 정합성 검증 (`yunhee sql-check`)**: AS-IS와 TOBE 매퍼 XML의 동적 SQL을 펼쳐 대상 DB에서 `psql EXPLAIN`을 안전하게 읽기 전용으로 사전 검증.
* **서버 트레이스 추적 (`yunhee api --log`, `yunhee log trace`)**: 자동 로그인 기반 API 스모크 테스트와 동시에, 백엔드가 실제로 실행한 SQL과 바인딩 파라미터를 역추적.

#### ③ 신규 프레임워크 문서화 및 팩트시트 (Documentation & Factsheets)
* **전체 호출 체인 추적 (`yunhee trace-*`)**: 메뉴 트리 ➔ 화면(Java/TSX) ➔ 이벤트 ➔ 서비스 ➔ MyBatis SQL ➔ DB 테이블/함수까지의 전 구간 팩트시트 생성.
* **원본 변경 감지 (`yunhee drift`, `baseline`)**: 전환 작업 중에 AS-IS 원본 소스가 수정되었을 때 변경점을 즉시 감지하여 문서화.

---

### 3. 상용 AI(`agy`, Claude 등)와의 협업 방식

* **yunhee**: AssetERP의 방대한 레거시 컨텍스트를 쥐어짜고 압축하여 오차 없는 데이터와 스펙을 제공하는 **"전환 전문 로컬 공작소 (토큰 절약)"**.
* **agy / Claude**: yunhee가 정제해 준 초압축 컨텍스트를 받아 실제 컴포넌트와 비즈니스 로직을 구현하는 **"고지능 코딩 엔진"**.
"""
