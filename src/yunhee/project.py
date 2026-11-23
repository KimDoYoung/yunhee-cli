import json
import re
from datetime import UTC, datetime
from importlib.metadata import version as pkg_version
from pathlib import Path

from yunhee import config
from yunhee.config import WORK_DIR

PROJECT_DIR = WORK_DIR / ".yunhee"
PROJECT_FILE = PROJECT_DIR / "project.json"
MCP_FILE = PROJECT_DIR / "mcp.json"

DEFAULT_MCP_CONFIG = {
    "mcpServers": {
        "time": {
            "command": "uvx",
            "args": ["mcp-server-time"],
        },
        "fetch": {
            "command": "uvx",
            "args": ["mcp-server-fetch"],
        },
    }
}


def find_project_root(start_dir: Path | None = None) -> Path:
    """프로젝트 루트를 위로 올라가며 찾는다.

    우선순위:
    1. .yunhee.toml, .env.local, CLAUDE.md, .yunhee/project.json 가 있는 디렉터리
    2. .yunhee/runs 가 있는 디렉터리 중 가장 바깥(최상위) 디렉터리
    3. .git 이 있는 디렉터리
    """
    curr = (start_dir or Path.cwd()).resolve()
    parents = [curr, *curr.parents]

    # 1. 명시적 프로젝트 설정/표지 파일 우선
    for p in parents:
        if (p / ".yunhee.toml").is_file():
            return p
        if (p / ".env.yunhee").is_file() or (p / ".env.local").is_file():
            return p
        if (p / "CLAUDE.md").is_file():
            return p
        if (p / ".yunhee" / "project.json").is_file():
            return p

    # 2. .yunhee/runs 가 있는 디렉터리 중 가장 바깥(최상위) 디렉터리
    outermost_yunhee = None
    for p in reversed(parents):
        if (p / ".yunhee" / "runs").is_dir():
            outermost_yunhee = p
            break
    if outermost_yunhee:
        return outermost_yunhee

    # 3. .git 확인
    for p in parents:
        if (p / ".git").is_dir() or (p / ".git").is_file():
            return p

    return curr


def current_version() -> str:
    return pkg_version("yunhee")


def load(root: Path | None = None) -> dict | None:
    pfile = (root / ".yunhee" / "project.json") if root else PROJECT_FILE
    if not pfile.exists():
        return None
    return json.loads(pfile.read_text(encoding="utf-8"))


def status(root: Path | None = None) -> str:
    """'missing' | 'outdated' | 'ok' 중 하나를 반환."""
    data = load(root)
    if data is None:
        return "missing"
    if data.get("yunhee_version") != current_version():
        return "outdated"
    return "ok"


def init(root: Path | None = None) -> dict:
    """.yunhee 디렉터리 및 필수 파일(project.json, mcp.json, memory.md, sessions/, runs/, .gitignore)을 초기화/갱신한다."""
    effective_root = root or Path.cwd()
    pdir = effective_root / ".yunhee"
    pfile = pdir / "project.json"
    mfile = pdir / "mcp.json"
    mem_file = pdir / "memory.md"
    git_ignore = pdir / ".gitignore"
    sessions_dir = pdir / "sessions"
    runs_dir = pdir / "runs"

    data = load(effective_root) or {}
    now = datetime.now(UTC).isoformat()
    data.setdefault("name", effective_root.name)
    data.setdefault("created_at", now)
    data["updated_at"] = now
    data["yunhee_version"] = current_version()
    data["project_dir"] = str(pdir)

    pdir.mkdir(parents=True, exist_ok=True)
    pfile.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 1. .yunhee/mcp.json 기본 생성 (미존재 시)
    if not mfile.exists():
        mfile.write_text(
            json.dumps(DEFAULT_MCP_CONFIG, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        data["mcp_created"] = True
    else:
        data["mcp_created"] = False

    # 2. .yunhee/memory.md 기본 생성 (미존재 시)
    if not mem_file.exists():
        mem_template = (
            "# 프로젝트 규칙 및 특이사항\n\n"
            "- 여기에 기록된 규칙은 에이전트 대화 시 시스템 프롬프트에 자동으로 주입됩니다.\n"
            "- REPL에서 `/memory add <규칙>` 으로 손쉽게 추가할 수 있습니다.\n"
        )
        mem_file.write_text(mem_template, encoding="utf-8")
        data["memory_created"] = True
    else:
        data["memory_created"] = False

    # 3. .yunhee/sessions/ 및 .yunhee/runs/ 디렉터리 생성
    sessions_dir.mkdir(parents=True, exist_ok=True)
    runs_dir.mkdir(parents=True, exist_ok=True)

    # 4. .yunhee/.gitignore 기본 생성 (미존재 시)
    if not git_ignore.exists():
        git_ignore_content = (
            "# yunhee 세션 대화록 및 실행 로그 ignore\n"
            "sessions/\n"
            "runs/\n"
            ".env*\n"
        )
        git_ignore.write_text(git_ignore_content, encoding="utf-8")
        data["gitignore_created"] = True
    else:
        data["gitignore_created"] = False

    return data


GLOBAL_ENV_TEMPLATE = """\
# yunhee 전역 기본 설정 파일 (~/.yunhee/.env.yunhee)
# 프로젝트별 오버라이드가 필요하면 해당 프로젝트 루트에 .env.yunhee 를 두면 됩니다.

# (선택) yunhee 전역 데이터 디렉터리 (미지정 시 개발 환경은 레포 루트, 설치본은 ~/.yunhee)
# YUNHEE_DIR="$HOME/.yunhee"

# AssetERP 단일 데이터베이스 접속 URL (읽기 전용 조회용, PostgreSQL)
YUNHEE_DB="postgresql://user:password@localhost:5432/asseterpdb"
# 기본 DB 이름 (미지정 시 YUNHEE_DB URL의 DB명 사용)
# YUNHEE_DB_NAME="asseterpdb"

# yunhee table / prepare / get_db_definition이 읽을 스키마 스냅샷 이름 (기본값: YUNHEE_DB)
YUNHEE_SCHEMA_ENV="YUNHEE_DB"

# 로그 조회 (yunhee log)
# YUNHEE_LOG_DOCKER="your-tomcat-container"
# YUNHEE_LOG_DIR="/path/to/app/logs"
YUNHEE_LOG_APP="AssetERP-backend"
# YUNHEE_LOG_CONTEXT="/AssetERP"
# YUNHEE_LOG_ACCESS_LOGGER="kr.co.kfs.asseterp.access"

# Ollama - qwen2.5-coder(추론/분석), bge-m3(임베딩)
YUNHEE_OLLAMA_URL="http://localhost:11434"
YUNHEE_OLLAMA_MODEL="qwen2.5-coder:14b"
YUNHEE_EMBED_MODEL="bge-m3:latest"
YUNHEE_NUM_CTX="16384"

# ChromaDB (docker, docs/docker-compose.yml 참고)
YUNHEE_CHROMA_HOST="localhost"
YUNHEE_CHROMA_PORT="8000"

# Gotenberg PDF 변환 (docker, docs/docker-compose.yml 참고)
# YUNHEE_GOTENBERG_URL="http://localhost:3000"

# ASIS(AssetERP, GWT/GXT) 소스 루트 - yunhee가 레거시 페이지/매퍼를 찾는 기준
YUNHEE_ASIS_SRC_DIR="/path/to/Asset-ERP"
# YUNHEE_SRC_INDEX_DIR="/path/to/project/docs/as-is/src"

# TOBE(Spring Boot/React) 소스 루트 (미지정 시 현재 작업 디렉터리 WORK_DIR)
# YUNHEE_TOBE_SRC_DIR="/path/to/AssetERP"
# YUNHEE_JAVA_BASE_PACKAGE="kr.co.kfs.asseterp"

# API 스모크 테스트 (yunhee api)
YUNHEE_API_BASE_URL="http://localhost:8082/AssetERP"
YUNHEE_API_LOGIN_PATH="/api/auth/login"
YUNHEE_API_DEFAULT_TENANT="admin"
YUNHEE_TEST_ADMIN_USER="admin"
YUNHEE_TEST_ADMIN_PASS="password"
YUNHEE_TEST_COMPANY="admin"
YUNHEE_API_TENANT_HOST="{tenant}.localhost"
YUNHEE_API_TIMEOUT=15
YUNHEE_TEST_USER="user"
YUNHEE_TEST_PASS="password"

# 화면 자동 캡처 (yunhee screen-capture, 미지정 시 YUNHEE_API_BASE_URL 사용)
YUNHEE_CAPTURE_URL="http://localhost:8082/AssetERP"
YUNHEE_CAPTURE_OUT_DIR=".yunhee/screen-capture"
"""

_PASS_LINE_RE = re.compile(r"^(\s*[A-Z0-9_]*PASS(?:WORD)?\s*=\s*)(.+)$")
_URL_CRED_RE = re.compile(r"([a-zA-Z][a-zA-Z0-9+.-]*://[^:/\s\"']+:)([^@\s\"']+)(@)")


def redact_env_content(text: str) -> str:
    """기존 .env.yunhee 출력 시 비밀번호·DB 접속 비밀번호를 마스킹한다."""
    out: list[str] = []
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("#") or not stripped:
            out.append(line)
            continue
        m = _PASS_LINE_RE.match(line)
        if m:
            out.append(f'{m.group(1)}"***"')
            continue
        out.append(_URL_CRED_RE.sub(r"\1***\3", line))
    return "\n".join(out) + ("\n" if text.endswith("\n") else "")


def _load_global_env_template() -> str:
    sample = config.YUNHEE_DIR / ".env.yunhee.sample"
    if sample.is_file():
        return sample.read_text(encoding="utf-8")
    return GLOBAL_ENV_TEMPLATE


def init_global(home: Path | None = None, force: bool = False) -> dict:
    """~/.yunhee 디렉터리와 ~/.yunhee/.env.yunhee 전역 설정 파일을 초기화한다."""
    home_dir = (home or Path.home()) / ".yunhee"
    env_file = home_dir / ".env.yunhee"
    home_dir.mkdir(parents=True, exist_ok=True)

    existed = env_file.is_file()
    if existed and not force:
        content = env_file.read_text(encoding="utf-8")
        return {
            "yunhee_dir": str(home_dir),
            "env_file": str(env_file),
            "created": False,
            "overwritten": False,
            "content": content,
        }

    content = _load_global_env_template()
    env_file.write_text(content, encoding="utf-8")
    return {
        "yunhee_dir": str(home_dir),
        "env_file": str(env_file),
        "created": True,
        "overwritten": existed and force,
        "content": content,
    }
