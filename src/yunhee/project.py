import json
from datetime import UTC, datetime
from importlib.metadata import version as pkg_version
from pathlib import Path

from yunhee.config import WORK_DIR

PROJECT_DIR = WORK_DIR / ".yunhee"
PROJECT_FILE = PROJECT_DIR / "project.json"


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
        if (p / ".env.local").is_file():
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
    """.yunhee/project.json을 새로 만들거나(최초) 현재 버전으로 갱신한다."""
    effective_root = root or WORK_DIR
    pdir = effective_root / ".yunhee"
    pfile = pdir / "project.json"
    data = load(effective_root) or {}
    now = datetime.now(UTC).isoformat()
    data.setdefault("name", effective_root.name)
    data.setdefault("created_at", now)
    data["updated_at"] = now
    data["yunhee_version"] = current_version()

    pdir.mkdir(parents=True, exist_ok=True)
    pfile.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return data
