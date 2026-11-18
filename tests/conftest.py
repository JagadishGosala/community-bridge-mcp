"""Shared fixtures for unit and service tests (SPEC §11 seed data, §12 conventions)."""

import itertools
import json
import uuid
from dataclasses import dataclass
from typing import Any

import pytest

from cb import db, reset, server
from cb.identity import Caller

# Per-nonprofit defaults used when inserting requests directly.
_NONPROFIT = {
    "np_bridge": {
        "participant_id": "par_bridge_001",
        "fund_id": "fund_bridge_rent",
        "cw": "stf_bridge_cw",
        "pm": "stf_bridge_pm",
        "fin": "stf_bridge_fin",
    },
    "np_harbor": {
        "participant_id": "par_harbor_001",
        "fund_id": "fund_harbor_general",
        "cw": "stf_harbor_cw",
        "pm": "stf_harbor_pm",
        "fin": "stf_harbor_fin",
    },
}


def money(cents: int) -> str:
    """Expected output form of a cents amount (A-10)."""
    return f"{cents // 100}.{cents % 100:02d}"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """Fresh cb-reset database per test; CB_DB_PATH points at it."""
    path = tmp_path / "cb.sqlite3"
    monkeypatch.setenv("CB_DB_PATH", str(path))
    reset.main()
    return path


@pytest.fixture
def conn(db_path):
    c = db.connect()
    yield c
    c.close()


@pytest.fixture
def cw():
    return Caller("stf_bridge_cw", "Casey Morgan", "CASE_WORKER", "np_bridge", "Community Bridge")


@pytest.fixture
def pm():
    return Caller("stf_bridge_pm", "Priya Shah", "PROGRAM_MANAGER", "np_bridge", "Community Bridge")


@pytest.fixture
def fin():
    return Caller("stf_bridge_fin", "Felix Ortega", "FINANCE", "np_bridge", "Community Bridge")


@pytest.fixture
def h_cw():
    return Caller("stf_harbor_cw", "Hana Lee", "CASE_WORKER", "np_harbor", "Harbor Neighbors")


@pytest.fixture
def h_pm():
    return Caller("stf_harbor_pm", "Marcus Bell", "PROGRAM_MANAGER", "np_harbor", "Harbor Neighbors")


@pytest.fixture
def h_fin():
    return Caller("stf_harbor_fin", "Nadia Cole", "FINANCE", "np_harbor", "Harbor Neighbors")


@pytest.fixture
def insert_request(conn):
    """Insert a request in any status with direct SQL; returns the expected §8 Request JSON.

    APPROVED/REJECTED/PAID rows are decided by the nonprofit's PM; PAID rows also get
    a payment recorded by its FIN. created_at increases by one second per insert unless given.
    """
    clock = itertools.count()

    def insert(
        status: str = "PENDING",
        *,
        amount_cents: int = 30_000,
        nonprofit_id: str = "np_bridge",
        participant_id: str | None = None,
        fund_id: str | None = None,
        purpose: str = "RENT",
        description: str | None = None,
        request_id: str | None = None,
        created_at: str | None = None,
    ) -> dict[str, Any]:
        defaults = _NONPROFIT[nonprofit_id]
        n = next(clock)
        request_id = request_id or "req_" + uuid.uuid4().hex
        participant_id = participant_id or defaults["participant_id"]
        fund_id = fund_id or defaults["fund_id"]
        created_at = created_at or f"2026-11-18T10:{n // 60:02d}:{n % 60:02d}Z"
        decided_by = None if status == "PENDING" else defaults["pm"]
        decided_at = None if status == "PENDING" else created_at
        rejection_reason = "Rejected in test setup" if status == "REJECTED" else None
        conn.execute(
            "INSERT INTO requests (id, nonprofit_id, participant_id, fund_id, purpose, description,"
            " amount_cents, status, created_by, created_at, decided_by, decided_at, rejection_reason)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request_id,
                nonprofit_id,
                participant_id,
                fund_id,
                purpose,
                description,
                amount_cents,
                status,
                defaults["cw"],
                created_at,
                decided_by,
                decided_at,
                rejection_reason,
            ),
        )
        payment = None
        if status == "PAID":
            payment_id = "pay_" + uuid.uuid4().hex
            conn.execute(
                "INSERT INTO payments (id, request_id, nonprofit_id, amount_cents, recorded_by, recorded_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (payment_id, request_id, nonprofit_id, amount_cents, defaults["fin"], created_at),
            )
            payment = {
                "id": payment_id,
                "amount": money(amount_cents),
                "recorded_by": defaults["fin"],
                "recorded_at": created_at,
            }
        return {
            "id": request_id,
            "participant_id": participant_id,
            "fund_id": fund_id,
            "purpose": purpose,
            "description": description,
            "amount": money(amount_cents),
            "status": status,
            "created_by": defaults["cw"],
            "created_at": created_at,
            "decided_by": decided_by,
            "decided_at": decided_at,
            "rejection_reason": rejection_reason,
            "payment": payment,
        }

    return insert


@pytest.fixture
def snapshot(conn):
    """State for "unchanged" assertions: all request rows, payments count, every fund's summary.

    The summary is computed here with §6.2 SQL, independently of cb.service.
    """

    def take() -> dict[str, Any]:
        requests = conn.execute("SELECT * FROM requests ORDER BY id").fetchall()
        payments = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
        funds = {
            fund_id: {
                "allocation": allocation,
                "committed": committed,
                "paid": paid,
                "available": allocation - committed - paid,
            }
            for fund_id, allocation, committed, paid in conn.execute(
                "SELECT f.id, f.allocation_cents,"
                " COALESCE(SUM(CASE WHEN r.status = 'APPROVED' THEN r.amount_cents END), 0),"
                " COALESCE(SUM(CASE WHEN r.status = 'PAID' THEN r.amount_cents END), 0)"
                " FROM funds f LEFT JOIN requests r"
                " ON r.fund_id = f.id AND r.nonprofit_id = f.nonprofit_id"
                " GROUP BY f.id ORDER BY f.id"
            )
        }
        return {"requests": requests, "payments": payments, "funds": funds}

    return take


@dataclass
class Outcome:
    """A tool call result run through the in-process adapter."""

    is_error: bool
    body: dict[str, Any]
    text: str

    @property
    def code(self) -> str:
        return self.body["error"]["code"]

    @property
    def details(self) -> dict[str, Any]:
        return self.body["error"]["details"]

    @property
    def fields(self) -> list[str]:
        return [f["field"] for f in self.details["fields"]]


@pytest.fixture
def call_tool(db_path):
    """Run a registered tool through cb.server.run_tool (the full §6.3 pipeline) as a staff id."""

    def call(tool: str, staff_id: str, arguments: dict[str, Any] | None = None) -> Outcome:
        result = server.run_tool(server.TOOLS[tool], staff_id, {} if arguments is None else arguments)
        assert len(result.content) == 1
        text = result.content[0].text
        body = json.loads(text)
        if result.is_error:
            # A-16 / §6.5: error JSON as text only, exactly {"error": {code, message, details}}.
            assert result.structured_content is None
            assert set(body) == {"error"}
            assert set(body["error"]) == {"code", "message", "details"}
        else:
            # A-16: structuredContent plus the same JSON as text.
            assert result.structured_content == body
        return Outcome(is_error=bool(result.is_error), body=body, text=text)

    return call
