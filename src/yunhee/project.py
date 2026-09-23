import json
from datetime import UTC, datetime
from importlib.metadata import version as pkg_version

from yunhee.config import WORK_DIR

PROJECT_DIR = WORK_DIR / ".yunhee"
PROJECT_FILE = PROJECT_DIR / "project.json"


def current_version() -> str:
    return pkg_version("yunhee")


def load() -> dict | None:
    if not PROJECT_FILE.exists():
        return None
    return json.loads(PROJECT_FILE.read_text())


def status() -> str:
    """'missing' | 'outdated' | 'ok' 중 하나를 반환."""
    data = load()
    if data is None:
        return "missing"
    if data.get("yunhee_version") != current_version():
        return "outdated"
    return "ok"


def init() -> dict:
    """.yunhee/project.json을 새로 만들거나(최초) 현재 버전으로 갱신한다."""
    data = load() or {}
    now = datetime.now(UTC).isoformat()
    data.setdefault("name", WORK_DIR.name)
    data.setdefault("created_at", now)
    data["updated_at"] = now
    data["yunhee_version"] = current_version()

    PROJECT_DIR.mkdir(parents=True, exist_ok=True)
    PROJECT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return data
