"""Schema constraints and reset/seed (SPEC §7, §11; AC-12, AC-20, AC-33)."""

import sqlite3

import pytest

from cb import db, reset

EXPECTED_NONPROFITS = [
    ("np_bridge", "Community Bridge"),
    ("np_harbor", "Harbor Neighbors"),
]
EXPECTED_STAFF = [
    ("stf_bridge_cw", "np_bridge", "Casey Morgan", "CASE_WORKER"),
    ("stf_bridge_fin", "np_bridge", "Felix Ortega", "FINANCE"),
    ("stf_bridge_pm", "np_bridge", "Priya Shah", "PROGRAM_MANAGER"),
    ("stf_harbor_cw", "np_harbor", "Hana Lee", "CASE_WORKER"),
    ("stf_harbor_fin", "np_harbor", "Nadia Cole", "FINANCE"),
    ("stf_harbor_pm", "np_harbor", "Marcus Bell", "PROGRAM_MANAGER"),
]
EXPECTED_PARTICIPANTS = [
    ("par_bridge_001", "np_bridge", "Jordan Avery"),
    ("par_bridge_002", "np_bridge", "Sam Patel"),
    ("par_bridge_003", "np_bridge", "Riley Chen"),
    ("par_harbor_001", "np_harbor", "Taylor Brooks"),
    ("par_harbor_002", "np_harbor", "Morgan Diaz"),
]
EXPECTED_FUNDS = [
    ("fund_bridge_rent", "np_bridge", "Emergency Rent Relief", 1_000_000),
    ("fund_bridge_utility", "np_bridge", "Utility Assistance", 250_000),
    ("fund_harbor_general", "np_harbor", "General Emergency Assistance", 500_000),
]

NOW = "2026-11-18T09:00:00Z"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    path = tmp_path / "cb.sqlite3"
    monkeypatch.setenv("CB_DB_PATH", str(path))
    reset.main()
    return path


@pytest.fixture
def conn(db_path):
    c = db.connect()
    yield c
    c.close()


def _insert_request(
    c,
    request_id,
    *,
    nonprofit_id="np_bridge",
    participant_id="par_bridge_001",
    fund_id="fund_bridge_rent",
    created_by="stf_bridge_cw",
    decided_by=None,
    status="PENDING",
    amount_cents=30_000,
):
    c.execute(
        "INSERT INTO requests (id, nonprofit_id, participant_id, fund_id, purpose,"
        " description, amount_cents, status, created_by, created_at, decided_by,"
        " decided_at, rejection_reason)"
        " VALUES (?, ?, ?, ?, 'RENT', NULL, ?, ?, ?, ?, ?, ?, NULL)",
        (
            request_id,
            nonprofit_id,
            participant_id,
            fund_id,
            amount_cents,
            status,
            created_by,
            NOW,
            decided_by,
            NOW if decided_by else None,
        ),
    )


def _insert_payment(c, payment_id, request_id, *, amount_cents=30_000):
    c.execute(
        "INSERT INTO payments (id, request_id, nonprofit_id, amount_cents,"
        " recorded_by, recorded_at)"
        " VALUES (?, ?, 'np_bridge', ?, 'stf_bridge_fin', ?)",
        (payment_id, request_id, amount_cents, NOW),
    )


def _count(c, table):
    return c.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_ac12_second_payment_for_same_request_violates_unique(conn):
    _insert_request(conn, "req_ac12", status="PAID", decided_by="stf_bridge_pm")
    _insert_payment(conn, "pay_ac12_first", "req_ac12")
    assert _count(conn, "payments") == 1

    with pytest.raises(sqlite3.IntegrityError, match="UNIQUE"):
        _insert_payment(conn, "pay_ac12_second", "req_ac12")

    assert _count(conn, "payments") == 1


def test_ac20_request_cannot_reference_fund_of_other_nonprofit(conn):
    with pytest.raises(sqlite3.IntegrityError, match="FOREIGN KEY"):
        _insert_request(
            conn,
            "req_ac20",
            nonprofit_id="np_harbor",
            participant_id="par_harbor_001",
            fund_id="fund_bridge_rent",
            created_by="stf_harbor_cw",
        )
    assert _count(conn, "requests") == 0

    # Control: the same row with the harbor fund is accepted, so the failure
    # above comes from the cross-nonprofit fund reference.
    _insert_request(
        conn,
        "req_ac20",
        nonprofit_id="np_harbor",
        participant_id="par_harbor_001",
        fund_id="fund_harbor_general",
        created_by="stf_harbor_cw",
    )
    assert _count(conn, "requests") == 1


def test_ac33_reset_twice_restores_exact_seed(db_path):
    c = db.connect()
    try:
        _insert_request(c, "req_ac33_paid", status="PAID", decided_by="stf_bridge_pm")
        _insert_payment(c, "pay_ac33", "req_ac33_paid")
        _insert_request(c, "req_ac33_pending")
        assert _count(c, "requests") == 2
        assert _count(c, "payments") == 1
    finally:
        c.close()

    reset.main()
    reset.main()

    c = db.connect()
    try:
        assert c.execute("SELECT id, name FROM nonprofits ORDER BY id").fetchall() == EXPECTED_NONPROFITS
        assert (
            c.execute("SELECT id, nonprofit_id, name, role FROM staff ORDER BY id").fetchall()
            == EXPECTED_STAFF
        )
        assert (
            c.execute("SELECT id, nonprofit_id, display_name FROM participants ORDER BY id").fetchall()
            == EXPECTED_PARTICIPANTS
        )
        assert (
            c.execute("SELECT id, nonprofit_id, name, allocation_cents FROM funds ORDER BY id").fetchall()
            == EXPECTED_FUNDS
        )
        assert _count(c, "requests") == 0
        assert _count(c, "payments") == 0
    finally:
        c.close()
