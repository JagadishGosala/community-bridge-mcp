import os
from pathlib import Path

DEFAULT_DB_PATH = "./data/cb.sqlite3"


def db_path() -> Path:
    """Database file path from CB_DB_PATH (A-13), read at call time."""
    return Path(os.environ.get("CB_DB_PATH") or DEFAULT_DB_PATH)


def staff_id() -> str:
    """The identity this server acts as, from CB_STAFF_ID (REQ-01); "" if unset."""
    return os.environ.get("CB_STAFF_ID", "")


def tx_delay_ms() -> int:
    """Test-only CB_TEST_TX_DELAY_MS (SPEC §10); 0 unless set to a positive integer."""
    value = os.environ.get("CB_TEST_TX_DELAY_MS", "")
    return int(value) if value.isdigit() else 0
