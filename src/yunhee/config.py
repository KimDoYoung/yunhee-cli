import os
from pathlib import Path

from dotenv import load_dotenv

# config.py 기준 2단계 위 = yunhee-cli 프로젝트 루트 (설치 위치, .env.local이 있는 곳)
# WORK_DIR(작업 대상 프로젝트)과 구분하기 위해 YUNHEE_DIR로 명명한다.
YUNHEE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = YUNHEE_DIR / ".env.local"

# yunhee가 어느 디렉토리에서 실행됐는지 = 작업 대상 프로젝트 루트.
# grep/파일 검색 등 "작업 대상"을 다루는 tool들은 전부 이 값을 기준으로 동작해야 한다.
WORK_DIR = Path.cwd()

# `uv tool install --editable`로 어디서 실행하든 항상 이 프로젝트의 .env.local을 읽는다.
load_dotenv(ENV_FILE)

# OLLAMA_HOST는 Ollama 서버 자체의 bind address 환경변수와 이름이 겹치므로
# (예: OLLAMA_HOST=0.0.0.0) YUNHEE_ 접두사로 구분한다.
OLLAMA_HOST = os.getenv("YUNHEE_OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("YUNHEE_OLLAMA_MODEL", "qwen2.5-coder:14b")
EMBED_MODEL = os.getenv("YUNHEE_EMBED_MODEL", "bge-m3:latest")
# 요청마다 Ollama에 넘기는 컨텍스트 크기(토큰, 입력+출력 합계). 넘기지 않으면 Ollama 기본값(4096)이 적용되어
# 긴 프롬프트의 앞부분이 조용히 잘린다. qwen2.5-coder:14b는 16384에서 VRAM 약 13GB (16GB 제약 안).
NUM_CTX = int(os.getenv("YUNHEE_NUM_CTX", "16384"))

# docs/docker-compose.yml의 chromadb 서비스 참고
CHROMA_HOST = os.getenv("YUNHEE_CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("YUNHEE_CHROMA_PORT", "8000"))

# AssetERP 테스트/로컬 DB (읽기 전용 조회용, docs/yunhee-cli-설계.md 참고)
TEST_DB = os.getenv("TEST_DB")
LOCAL_DB = os.getenv("LOCAL_DB")
# `table`/`prepare`가 기본으로 읽을 스키마 스냅샷(`make-dbml <ENV>`로 생성)의 환경변수 이름
SCHEMA_ENV = os.getenv("YUNHEE_SCHEMA_ENV", "LOCAL_DB")

# ASIS(AssetERP, GWT/GXT) 소스 루트 - yunhee가 레거시 페이지/매퍼를 찾는 기준
ASIS_SRC_DIR = Path(os.getenv("YUNHEE_ASIS_SRC_DIR", "/home/kdy987/oms-data/src/Asset-ERP"))

import tomllib


def _find_yunhee_toml(start_dir: Path | None = None) -> tuple[Path | None, dict]:
    cur = (start_dir or Path.cwd()).resolve()
    for d in [cur, *cur.parents]:
        f = d / ".yunhee.toml"
        if f.is_file():
            try:
                return f, tomllib.loads(f.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                return f, {}
    return None, {}



TOML_FILE, TOML_CONFIG = _find_yunhee_toml()
_api_conf = TOML_CONFIG.get("api", {})

# API 스모크 테스트 기본 설정 (.yunhee.toml 우선, 없으면 .env.local)
API_BASE_URL = _api_conf.get("base") or os.getenv("YUNHEE_API_BASE_URL", "http://localhost:8082/AssetERP_1")
# YUNHEE_API_TENANT는 0.1.9까지 쓰던 이름 (호환)
API_DEFAULT_TENANT = (
    _api_conf.get("tenant") or os.getenv("YUNHEE_API_DEFAULT_TENANT") or os.getenv("YUNHEE_API_TENANT")
)
API_LOGIN_PATH = os.getenv("YUNHEE_API_LOGIN_PATH", "/api/auth/login")
TEST_ADMIN_USER = os.getenv("YUNHEE_TEST_ADMIN_USER", "admin")
TEST_ADMIN_PASS = os.getenv("YUNHEE_TEST_ADMIN_PASS", "1111")
TEST_COMPANY = os.getenv("YUNHEE_TEST_COMPANY")
API_TENANT_HOST = os.getenv("YUNHEE_API_TENANT_HOST", "{tenant}.localhost")


def _float_env(name: str, default: float) -> float:
    try:
        value = float(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


def resolve_api_tenant(tenant: str | None = None) -> str | None:
    """api·compare가 같이 쓰는 기본 테넌트 선택 순서.

    -t → .yunhee.toml [api] tenant → YUNHEE_API_DEFAULT_TENANT → YUNHEE_TEST_COMPANY
    """
    return tenant or API_DEFAULT_TENANT or TEST_COMPANY


# yunhee api 요청 타임아웃(초). 로그인 요청은 10초 고정.
API_TIMEOUT = _float_env("YUNHEE_API_TIMEOUT", 15.0)

# 로그 리더 (yunhee log) 기본 설정
_log_conf = TOML_CONFIG.get("log", {})
LOG_DOCKER = _log_conf.get("docker") if "docker" in _log_conf else os.getenv("YUNHEE_LOG_DOCKER", "t3600-tomcat")
LOG_DIR = _log_conf.get("dir") if "dir" in _log_conf else os.getenv("YUNHEE_LOG_DIR", "/home/kdy987/tmp/asseterp-data/logs")
LOG_APP = _log_conf.get("app") if "app" in _log_conf else os.getenv("YUNHEE_LOG_APP", "AssetERP-backend")
LOG_TZ = _log_conf.get("tz") if "tz" in _log_conf else os.getenv("YUNHEE_LOG_TZ", "")
LOG_CONTEXT = _log_conf.get("context") if "context" in _log_conf else os.getenv("YUNHEE_LOG_CONTEXT", "/AssetERP_1")
LOG_TRACE_HEADER = _log_conf.get("trace_header") if "trace_header" in _log_conf else os.getenv("YUNHEE_LOG_TRACE_HEADER", "X-Trace-Id")


def redact(url: str | None) -> str:
    """postgresql://user:password@host/db 형태에서 비밀번호를 가린다."""
    if not url:
        return "(not set)"
    if "://" not in url or "@" not in url:
        return url
    scheme, rest = url.split("://", 1)
    cred, host_part = rest.split("@", 1)
    user = cred.split(":", 1)[0]
    return f"{scheme}://{user}:***@{host_part}"


def summary() -> dict[str, str]:
    """/config 커맨드에서 보여줄 설정값 모음 (.env.local 기반)."""
    from yunhee.tools.as_is.drift import get_git_branch_sync_status

    return {
        "work-dir": str(WORK_DIR),
        "yunhee-dir": str(YUNHEE_DIR),
        "env-file": f"{ENV_FILE} ({'exists' if ENV_FILE.exists() else 'not found'})",
        "ollama-url": OLLAMA_HOST,
        "ollama-model": OLLAMA_MODEL,
        "embed-model": EMBED_MODEL,
        "num-ctx": str(NUM_CTX),
        "chroma-host": CHROMA_HOST,
        "chroma-port": str(CHROMA_PORT),
        "test-db": redact(TEST_DB),
        "local-db": redact(LOCAL_DB),
        "schema-env": SCHEMA_ENV,
        "asis-src": str(ASIS_SRC_DIR),
        "asis-branch": get_git_branch_sync_status(ASIS_SRC_DIR),
        "api-base": (
            f"{API_BASE_URL} (from {TOML_FILE.name})"
            if TOML_FILE and _api_conf.get("base")
            else f"{API_BASE_URL} (from .env.local)"
        ),
        "api-tenant": (
            f"{API_DEFAULT_TENANT} (from {TOML_FILE.name})"
            if TOML_FILE and _api_conf.get("tenant")
            else (API_DEFAULT_TENANT or (f"{TEST_COMPANY} (from YUNHEE_TEST_COMPANY)" if TEST_COMPANY else "(not set)"))
        ),
        "api-login-path": API_LOGIN_PATH,
        "api-tenant-host": API_TENANT_HOST,
        "api-timeout": f"{API_TIMEOUT:g}s",
        "test-admin-user": TEST_ADMIN_USER,
        "test-company": TEST_COMPANY or "(not set)",
    }


from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class ConfigItem:
    key: str  # 대표 환경변수명 또는 식별자
    aliases: list[str]  # 별칭 목록
    getter: Callable[[], Any]  # 현재 값 반환 함수
    description: str  # 설명
    secret: bool = False  # 완전 비밀번호 마스킹 대상 여부
    is_url: bool = False  # DB URL 비밀번호 마스킹 대상 여부

    def get_value(self, raw: bool = True) -> str:
        val = self.getter()
        if val is None:
            return ""
        s = str(val)
        if raw or not s:
            return s
        if self.secret:
            return "***"
        if self.is_url:
            return redact(s)
        return s


def _get_branch_status() -> str:
    try:
        from yunhee.tools.as_is.drift import get_git_branch_sync_status

        return get_git_branch_sync_status(ASIS_SRC_DIR)
    except Exception:  # noqa: BLE001
        return "(unknown)"


CONFIG_ITEMS: list[ConfigItem] = [
    ConfigItem(
        key="YUNHEE_ASIS_SRC_DIR",
        aliases=["ASIS_SRC_DIR", "asis-src", "asis_src", "asis"],
        getter=lambda: str(ASIS_SRC_DIR),
        description="AS-IS 레거시 소스 루트 디렉터리",
    ),
    ConfigItem(
        key="WORK_DIR",
        aliases=["work-dir", "work_dir", "target"],
        getter=lambda: str(WORK_DIR),
        description="현재 터미널 작업 디렉터리 (TOBE 타겟)",
    ),
    ConfigItem(
        key="YUNHEE_DIR",
        aliases=["yunhee-dir", "yunhee_dir", "home"],
        getter=lambda: str(YUNHEE_DIR),
        description="yunhee-cli 설치 디렉터리",
    ),
    ConfigItem(
        key="ENV_FILE",
        aliases=["env-file", "env_file"],
        getter=lambda: str(ENV_FILE),
        description="설정 파일 (.env.local) 경로",
    ),
    ConfigItem(
        key="LOCAL_DB",
        aliases=["local-db", "local_db"],
        getter=lambda: LOCAL_DB or "",
        description="로컬 PostgreSQL DB 접속 URL",
        is_url=True,
    ),
    ConfigItem(
        key="TEST_DB",
        aliases=["test-db", "test_db"],
        getter=lambda: TEST_DB or "",
        description="테스트 PostgreSQL DB 접속 URL",
        is_url=True,
    ),
    ConfigItem(
        key="YUNHEE_SCHEMA_ENV",
        aliases=["SCHEMA_ENV", "schema-env", "schema_env"],
        getter=lambda: SCHEMA_ENV,
        description="기본 스키마 스냅샷 환경변수 이름",
    ),
    ConfigItem(
        key="YUNHEE_OLLAMA_URL",
        aliases=["OLLAMA_URL", "OLLAMA_HOST", "ollama-url", "ollama_url"],
        getter=lambda: OLLAMA_HOST,
        description="Ollama 서버 URL",
    ),
    ConfigItem(
        key="YUNHEE_OLLAMA_MODEL",
        aliases=["OLLAMA_MODEL", "ollama-model", "ollama_model"],
        getter=lambda: OLLAMA_MODEL,
        description="추론/분석 LLM 모델명",
    ),
    ConfigItem(
        key="YUNHEE_EMBED_MODEL",
        aliases=["EMBED_MODEL", "embed-model", "embed_model"],
        getter=lambda: EMBED_MODEL,
        description="임베딩 모델명",
    ),
    ConfigItem(
        key="YUNHEE_NUM_CTX",
        aliases=["NUM_CTX", "num-ctx", "num_ctx"],
        getter=lambda: str(NUM_CTX),
        description="Ollama 컨텍스트 토큰 크기",
    ),
    ConfigItem(
        key="YUNHEE_CHROMA_HOST",
        aliases=["CHROMA_HOST", "chroma-host", "chroma_host"],
        getter=lambda: CHROMA_HOST,
        description="ChromaDB 호스트",
    ),
    ConfigItem(
        key="YUNHEE_CHROMA_PORT",
        aliases=["CHROMA_PORT", "chroma-port", "chroma_port"],
        getter=lambda: str(CHROMA_PORT),
        description="ChromaDB 포트",
    ),
    ConfigItem(
        key="YUNHEE_API_BASE_URL",
        aliases=["API_BASE_URL", "api-base", "api_base"],
        getter=lambda: API_BASE_URL,
        description="API Base URL",
    ),
    ConfigItem(
        key="YUNHEE_API_DEFAULT_TENANT",
        aliases=["YUNHEE_API_TENANT", "API_DEFAULT_TENANT", "API_TENANT", "api-tenant", "api_tenant"],
        getter=lambda: API_DEFAULT_TENANT or "",
        description="API 기본 테넌트",
    ),
    ConfigItem(
        key="YUNHEE_API_LOGIN_PATH",
        aliases=["API_LOGIN_PATH", "api-login-path", "api_login_path"],
        getter=lambda: API_LOGIN_PATH,
        description="API 로그인 엔드포인트 경로",
    ),
    ConfigItem(
        key="YUNHEE_TEST_ADMIN_USER",
        aliases=["TEST_ADMIN_USER", "test-admin-user", "test_admin_user"],
        getter=lambda: TEST_ADMIN_USER,
        description="API 테스트 관리자 계정",
    ),
    ConfigItem(
        key="YUNHEE_TEST_ADMIN_PASS",
        aliases=["TEST_ADMIN_PASS", "test-admin-pass", "test_admin_pass"],
        getter=lambda: TEST_ADMIN_PASS,
        description="API 테스트 관리자 비밀번호",
        secret=True,
    ),
    ConfigItem(
        key="YUNHEE_TEST_COMPANY",
        aliases=["TEST_COMPANY", "test-company", "test_company"],
        getter=lambda: TEST_COMPANY or "",
        description="API 테스트 회사 코드",
    ),
    ConfigItem(
        key="YUNHEE_API_TENANT_HOST",
        aliases=["API_TENANT_HOST", "api-tenant-host", "api_tenant_host"],
        getter=lambda: API_TENANT_HOST,
        description="API 테넌트 호스트 패턴",
    ),
    ConfigItem(
        key="YUNHEE_API_TIMEOUT",
        aliases=["API_TIMEOUT", "api-timeout", "api_timeout"],
        getter=lambda: f"{API_TIMEOUT:g}",
        description="API 요청 타임아웃(초)",
    ),
    ConfigItem(
        key="YUNHEE_ASIS_BRANCH",
        aliases=["ASIS_BRANCH", "asis-branch", "asis_branch"],
        getter=_get_branch_status,
        description="AS-IS 소스 git 브랜치 동기화 상태",
    ),
    ConfigItem(
        key="YUNHEE_LOG_DOCKER",
        aliases=["LOG_DOCKER", "log-docker", "log_docker"],
        getter=lambda: LOG_DOCKER,
        description="로그 Docker 컨테이너명",
    ),
    ConfigItem(
        key="YUNHEE_LOG_DIR",
        aliases=["LOG_DIR", "log-dir", "log_dir"],
        getter=lambda: LOG_DIR,
        description="로그 디렉터리 경로",
    ),
    ConfigItem(
        key="YUNHEE_LOG_APP",
        aliases=["LOG_APP", "log-app", "log_app"],
        getter=lambda: LOG_APP,
        description="로그 앱 이름",
    ),
    ConfigItem(
        key="YUNHEE_LOG_TZ",
        aliases=["LOG_TZ", "log-tz", "log_tz"],
        getter=lambda: LOG_TZ,
        description="로그 타임존",
    ),
    ConfigItem(
        key="YUNHEE_LOG_CONTEXT",
        aliases=["LOG_CONTEXT", "log-context", "log_context"],
        getter=lambda: LOG_CONTEXT,
        description="로그 컨텍스트 경로",
    ),
    ConfigItem(
        key="YUNHEE_LOG_TRACE_HEADER",
        aliases=["LOG_TRACE_HEADER", "log-trace-header", "log_trace_header"],
        getter=lambda: LOG_TRACE_HEADER,
        description="트레이스 헤더명",
    ),
]


def _normalize_key(key: str) -> str:
    return key.strip().lower().replace("-", "_")


def get_config_item(key: str) -> ConfigItem | None:
    norm = _normalize_key(key)
    # 1차: 완전 일치 (정규화된 key 또는 aliases)
    for item in CONFIG_ITEMS:
        if _normalize_key(item.key) == norm:
            return item
        if any(_normalize_key(a) == norm for a in item.aliases):
            return item

    # 2차: yunhee_ 접두사 유연 매칭 (yunhee_ 붙이거나 뗀 경우)
    norm_no_prefix = norm.removeprefix("yunhee_")

    for item in CONFIG_ITEMS:
        item_norm = _normalize_key(item.key)
        item_no_prefix = item_norm.removeprefix("yunhee_")
        if item_no_prefix == norm_no_prefix:
            return item
        for a in item.aliases:
            a_norm = _normalize_key(a)
            a_no_prefix = a_norm.removeprefix("yunhee_")
            if a_no_prefix == norm_no_prefix:
                return item

    return None


def get_config_value(key: str, raw: bool = True) -> str | None:
    """설정 키(환경변수명 또는 별칭)로 현재 설정값을 가져온다.

    1. 등록된 ConfigItem에서 찾음
    2. 없으면 os.environ에서 직접 검색 (대소문자 및 YUNHEE_ 접두사 fallback)
    3. 존재하지 않으면 None 반환
    """
    item = get_config_item(key)
    if item is not None:
        return item.get_value(raw=raw)

    # os.environ fallback
    candidates = [key, key.upper(), f"YUNHEE_{key.upper()}"]
    for c in candidates:
        if c in os.environ:
            return os.environ[c]
    return None


def get_config_items() -> list[ConfigItem]:
    """등록된 모든 설정 항목 목록을 반환한다."""
    return list(CONFIG_ITEMS)

