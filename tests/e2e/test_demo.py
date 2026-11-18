"""scripts/demo.py runs the AC-31 flow and exits 0 (REQ-33)."""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "data"


def data_dir_state():
    if not DATA_DIR.exists():
        return None
    return sorted((p.name, p.stat().st_size, p.stat().st_mtime_ns) for p in DATA_DIR.iterdir())


def test_demo_script_runs_the_flow_and_exits_zero(tmp_path):
    before = data_dir_state()
    decoy_db = tmp_path / "must_not_be_created.sqlite3"
    env = {**os.environ, "CB_DB_PATH": str(decoy_db)}
    env.pop("CB_STAFF_ID", None)

    result = subprocess.run(
        [sys.executable, str(REPO / "scripts" / "demo.py")],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    for step in ("Step 1: discovered 10 tools", "Step 2:", "Step 3:", "Step 4:"):
        assert step in result.stdout
    final = json.loads(result.stdout.split("=== Final funding summary", 1)[1])
    assert final == {
        "funds": [
            {
                "fund_id": "fund_bridge_rent",
                "fund_name": "Emergency Rent Relief",
                "allocation": "10000.00",
                "committed": "0.00",
                "paid": "300.00",
                "available": "9700.00",
            }
        ]
    }
    # The demo uses its own temporary database: neither CB_DB_PATH nor ./data is touched.
    assert not decoy_db.exists()
    assert data_dir_state() == before
