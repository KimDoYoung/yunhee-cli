import sqlite3
from pathlib import Path

# store/db.py 기준 4단계 위 = 프로젝트 루트 (src/yunhee/store -> src/yunhee -> src -> root)
DB_PATH = Path(__file__).resolve().parents[3] / "data" / "db" / "yunhee.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)
