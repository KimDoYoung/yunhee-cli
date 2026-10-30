import json
from datetime import UTC, datetime
from importlib.metadata import version as pkg_version
from pathlib import Path

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
