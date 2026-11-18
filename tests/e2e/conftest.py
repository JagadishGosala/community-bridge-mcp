import os

import pytest

from cb import reset


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def seeded_db(tmp_path, monkeypatch):
    """Fresh cb-reset database in tmp_path."""
    path = tmp_path / "cb.sqlite3"
    monkeypatch.setenv("CB_DB_PATH", str(path))
    reset.main()
    return path


@pytest.fixture
def server_env():
    """Full environment for a server process; a reduced env breaks Python on Windows."""

    def make(staff_id, db_path):
        env = {**os.environ, "CB_DB_PATH": str(db_path)}
        if staff_id is None:
            env.pop("CB_STAFF_ID", None)
        else:
            env["CB_STAFF_ID"] = staff_id
        return env

    return make
