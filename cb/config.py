import os
from pathlib import Path

DEFAULT_DB_PATH = "./data/cb.sqlite3"


def db_path() -> Path:
    """Database file path from CB_DB_PATH (A-13), read at call time."""
    return Path(os.environ.get("CB_DB_PATH") or DEFAULT_DB_PATH)
