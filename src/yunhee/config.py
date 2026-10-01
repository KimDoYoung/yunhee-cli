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

# API 스모크 테스트 기본 설정
API_BASE_URL = os.getenv("YUNHEE_API_BASE_URL", "http://localhost:8082/OMS")
API_LOGIN_PATH = os.getenv("YUNHEE_API_LOGIN_PATH", "/api/auth/login")
TEST_ADMIN_USER = os.getenv("YUNHEE_TEST_ADMIN_USER", "admin")
TEST_ADMIN_PASS = os.getenv("YUNHEE_TEST_ADMIN_PASS", "1111")
TEST_COMPANY = os.getenv("YUNHEE_TEST_COMPANY")
API_TENANT_HOST = os.getenv("YUNHEE_API_TENANT_HOST", "{tenant}.localhost")


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
        "api-base": API_BASE_URL,
        "api-login-path": API_LOGIN_PATH,
        "api-tenant-host": API_TENANT_HOST,
        "test-admin-user": TEST_ADMIN_USER,
        "test-company": TEST_COMPANY or "(not set)",
    }
