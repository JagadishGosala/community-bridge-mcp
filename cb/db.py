import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from cb import config

# SPEC §7, verbatim.
SCHEMA = """
CREATE TABLE nonprofits (
  id   TEXT PRIMARY KEY,
  name TEXT NOT NULL
) STRICT;

CREATE TABLE staff (
  id           TEXT PRIMARY KEY,
  nonprofit_id TEXT NOT NULL REFERENCES nonprofits(id),
  name         TEXT NOT NULL,
  role         TEXT NOT NULL CHECK (role IN ('CASE_WORKER','PROGRAM_MANAGER','FINANCE')),
  UNIQUE (id, nonprofit_id)
) STRICT;

CREATE TABLE participants (
  id           TEXT PRIMARY KEY,
  nonprofit_id TEXT NOT NULL REFERENCES nonprofits(id),
  display_name TEXT NOT NULL,
  UNIQUE (id, nonprofit_id)
) STRICT;

CREATE TABLE funds (
  id               TEXT PRIMARY KEY,
  nonprofit_id     TEXT NOT NULL REFERENCES nonprofits(id),
  name             TEXT NOT NULL,
  allocation_cents INTEGER NOT NULL CHECK (allocation_cents >= 0),
  UNIQUE (id, nonprofit_id)
) STRICT;

CREATE TABLE requests (
  id               TEXT PRIMARY KEY,
  nonprofit_id     TEXT NOT NULL,
  participant_id   TEXT NOT NULL,
  fund_id          TEXT NOT NULL,
  purpose          TEXT NOT NULL CHECK (purpose IN ('RENT','UTILITIES','TRANSPORTATION','OTHER')),
  description      TEXT CHECK (description IS NULL OR length(description) BETWEEN 1 AND 500),
  amount_cents     INTEGER NOT NULL CHECK (amount_cents BETWEEN 1 AND 100000000),
  status           TEXT NOT NULL CHECK (status IN ('PENDING','APPROVED','REJECTED','PAID')),
  created_by       TEXT NOT NULL,
  created_at       TEXT NOT NULL,
  decided_by       TEXT,
  decided_at       TEXT,
  rejection_reason TEXT CHECK (rejection_reason IS NULL OR length(rejection_reason) BETWEEN 1 AND 500),
  UNIQUE (id, nonprofit_id),
  FOREIGN KEY (participant_id, nonprofit_id) REFERENCES participants(id, nonprofit_id),
  FOREIGN KEY (fund_id, nonprofit_id)        REFERENCES funds(id, nonprofit_id),
  FOREIGN KEY (created_by, nonprofit_id)     REFERENCES staff(id, nonprofit_id),
  FOREIGN KEY (decided_by, nonprofit_id)     REFERENCES staff(id, nonprofit_id),
  CHECK (purpose <> 'OTHER' OR description IS NOT NULL),
  CHECK ((status = 'REJECTED') = (rejection_reason IS NOT NULL)),
  CHECK ((status = 'PENDING') = (decided_by IS NULL))
) STRICT;
CREATE INDEX ix_requests_fund_status ON requests (nonprofit_id, fund_id, status);

CREATE TABLE payments (
  id           TEXT PRIMARY KEY,
  request_id   TEXT NOT NULL UNIQUE,
  nonprofit_id TEXT NOT NULL,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  recorded_by  TEXT NOT NULL,
  recorded_at  TEXT NOT NULL,
  FOREIGN KEY (request_id, nonprofit_id)  REFERENCES requests(id, nonprofit_id),
  FOREIGN KEY (recorded_by, nonprofit_id) REFERENCES staff(id, nonprofit_id)
) STRICT;
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open an existing database (A-17: mode=rw, never auto-created)."""
    if path is None:
        path = config.db_path()
    uri = Path(path).resolve().as_uri() + "?mode=rw"
    conn = sqlite3.connect(uri, uri=True, isolation_level=None)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """BEGIN IMMEDIATE; COMMIT on success, ROLLBACK on any exception."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def create_schema(conn: sqlite3.Connection) -> None:
    # Statements are run one by one instead of with executescript(), which
    # would COMMIT an open transaction first.
    for statement in SCHEMA.split(";"):
        if statement.strip():
            conn.execute(statement)
