import sqlite3

from yunhee import config

DB_PATH = config.YUNHEE_DIR / "data" / "db" / "yunhee.db"


def get_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(DB_PATH)
