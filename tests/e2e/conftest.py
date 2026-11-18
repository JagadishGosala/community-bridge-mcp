import itertools
import os
import sys
from contextlib import asynccontextmanager

import pytest
from mcp import ClientSession, StdioServerParameters, stdio_client

from cb import reset

SERVER = [sys.executable, "-m", "cb.server"]


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


@pytest.fixture
def mcp_session(server_env, tmp_path):
    """Open an initialized SDK stdio session to a new cb-server process acting as staff_id.

    Extra keyword arguments are added to the server environment. Each process's stderr
    goes to its own file in tmp_path.
    """
    counter = itertools.count()

    @asynccontextmanager
    async def session(staff_id, db_path, **extra_env):
        env = {**server_env(staff_id, db_path), **extra_env}
        params = StdioServerParameters(command=SERVER[0], args=SERVER[1:], env=env)
        with open(tmp_path / f"server-{next(counter)}-{staff_id}.stderr.txt", "w") as errlog:
            async with stdio_client(params, errlog=errlog) as (read, write), ClientSession(read, write) as s:
                await s.initialize()
                yield s

    return session
