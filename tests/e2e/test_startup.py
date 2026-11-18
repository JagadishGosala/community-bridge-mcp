"""Startup failures before any MCP output (AC-21, AC-22, AC-32)."""

import subprocess
import sys

import pytest

SERVER = [sys.executable, "-m", "cb.server"]


def run_server(env):
    return subprocess.run(
        SERVER, env=env, stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=5
    )


@pytest.mark.parametrize("staff_id", [None, ""], ids=["unset", "empty"])
def test_ac21_missing_staff_id_refuses_to_start(seeded_db, server_env, staff_id):
    result = run_server(server_env(staff_id, seeded_db))

    assert result.returncode != 0
    assert "CB_STAFF_ID" in result.stderr
    assert result.stdout == ""


def test_ac22_unknown_staff_id_refuses_to_start(seeded_db, server_env):
    result = run_server(server_env("stf_nobody", seeded_db))

    assert result.returncode != 0
    assert "unknown identity" in result.stderr
    assert result.stdout == ""


def test_ac32_missing_database_refuses_to_start(tmp_path, server_env):
    db_path = tmp_path / "data" / "cb.sqlite3"

    result = run_server(server_env("stf_bridge_cw", db_path))

    assert result.returncode != 0
    assert "uv run cb-reset" in result.stderr
    assert result.stdout == ""
    assert not db_path.exists()
