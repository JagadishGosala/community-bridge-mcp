"""record_payment (REQ-10, REQ-13, REQ-16, REQ-20, REQ-21).

AC-03, AC-10, AC-11; record_payment parts of AC-13, AC-14, AC-18; payment object per §8.
"""

import re

import pytest

from cb import models, service

P = "par_bridge_001"
F = "fund_bridge_rent"
MISSING_REQUEST = "req_" + "f" * 32
PAYMENT_ID = re.compile(r"^pay_[0-9a-f]{32}$")  # A-08
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")  # A-09


def pay(call_tool, staff_id, request_id):
    return call_tool("record_payment", staff_id, {"request_id": request_id})


def rent_balances(call_tool):
    s = call_tool("get_funding_summary", "stf_bridge_fin", {"fund_id": F}).body["funds"][0]
    return s["committed"], s["paid"], s["available"]


def payment_rows(conn):
    return conn.execute("SELECT id, request_id, nonprofit_id, amount_cents, recorded_by, recorded_at FROM payments").fetchall()


# --- AC-01 -> AC-02 -> AC-03: full lifecycle ------------------------------------------------------


def test_ac03_payment_after_create_and_approve(conn, call_tool):
    created = call_tool(
        "create_request", "stf_bridge_cw", {"participant_id": P, "fund_id": F, "purpose": "RENT", "amount": "300.00"}
    ).body
    approved = call_tool("approve_request", "stf_bridge_pm", {"request_id": created["id"]}).body
    assert rent_balances(call_tool) == ("300.00", "0.00", "9700.00")

    out = pay(call_tool, "stf_bridge_fin", created["id"])

    assert not out.is_error
    assert out.body["status"] == "PAID"
    payment = out.body["payment"]
    assert set(payment) == {"id", "amount", "recorded_by", "recorded_at"}
    assert PAYMENT_ID.match(payment["id"])
    assert payment["amount"] == "300.00"
    assert payment["recorded_by"] == "stf_bridge_fin"
    assert TIMESTAMP.match(payment["recorded_at"])
    # The approval audit fields stay as recorded by the PM (REQ-13).
    assert out.body["decided_by"] == "stf_bridge_pm"
    assert out.body["decided_at"] == approved["decided_at"]
    assert out.body["amount"] == created["amount"]

    assert rent_balances(call_tool) == ("0.00", "300.00", "9700.00")
    rows = payment_rows(conn)
    assert len(rows) == 1
    assert rows[0] == (payment["id"], created["id"], "np_bridge", 30_000, "stf_bridge_fin", payment["recorded_at"])
    # §8: get_request returns the same Request including the payment.
    assert call_tool("get_request", "stf_bridge_fin", {"request_id": created["id"]}).body == out.body


def test_payment_moves_exact_amount_from_committed_to_paid(call_tool, insert_request):
    # REQ-20: exactly the request amount; available unchanged by payment.
    insert_request("APPROVED", amount_cents=50_000)
    r = insert_request("APPROVED", amount_cents=12_345)
    assert rent_balances(call_tool) == ("623.45", "0.00", "9376.55")

    out = pay(call_tool, "stf_bridge_fin", r["id"])

    assert out.body["payment"]["amount"] == "123.45"
    assert rent_balances(call_tool) == ("500.00", "123.45", "9376.55")


def test_record_payment_at_service_level(conn, fin, insert_request):
    r = insert_request("APPROVED", amount_cents=30_000)

    out = service.record_payment(conn, fin, models.RecordPaymentInput.model_validate({"request_id": r["id"]}))

    assert out.status == "PAID"
    assert out.payment is not None
    assert (out.payment.amount, out.payment.recorded_by) == ("300.00", "stf_bridge_fin")
    assert conn.execute("SELECT status FROM requests WHERE id = ?", (r["id"],)).fetchone()[0] == "PAID"
    assert len(payment_rows(conn)) == 1


# --- AC-10 / AC-11: invalid transitions -------------------------------------------------------------


def test_ac10_second_payment_is_invalid_transition(conn, call_tool, insert_request, snapshot):
    r = insert_request("PAID", amount_cents=30_000)
    before = snapshot()

    out = pay(call_tool, "stf_bridge_fin", r["id"])

    assert out.code == "INVALID_TRANSITION"
    assert out.details == {"request_id": r["id"], "current_status": "PAID", "attempted": "PAY"}
    assert snapshot() == before
    assert len(payment_rows(conn)) == 1
    assert rent_balances(call_tool) == ("0.00", "300.00", "9700.00")


@pytest.mark.parametrize("status", ["PENDING", "REJECTED"])
def test_ac11_payment_of_unapproved_request_is_invalid_transition(conn, call_tool, insert_request, snapshot, status):
    r = insert_request(status)
    before = snapshot()

    out = pay(call_tool, "stf_bridge_fin", r["id"])

    assert out.code == "INVALID_TRANSITION"
    assert out.details == {"request_id": r["id"], "current_status": status, "attempted": "PAY"}
    assert snapshot() == before
    assert len(payment_rows(conn)) == 0


# --- AC-13 / AC-14: roles ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "staff_id,role",
    [("stf_bridge_cw", "CASE_WORKER"), ("stf_bridge_pm", "PROGRAM_MANAGER")],
    ids=["ac13_cw", "ac14_pm"],
)
def test_ac13_ac14_only_finance_records_payment(conn, call_tool, insert_request, snapshot, staff_id, role):
    s = insert_request("APPROVED")
    before = snapshot()

    out = pay(call_tool, staff_id, s["id"])

    assert out.code == "FORBIDDEN_ROLE"
    assert out.details == {"role": role, "tool": "record_payment", "allowed_roles": ["FINANCE"]}
    assert snapshot() == before
    assert len(payment_rows(conn)) == 0


# --- AC-18: other nonprofit ---------------------------------------------------------------------------


def test_ac18_other_nonprofit_payment_is_not_found(conn, call_tool, insert_request, snapshot):
    s = insert_request("APPROVED")
    before = snapshot()

    out = pay(call_tool, "stf_harbor_fin", s["id"])
    missing = pay(call_tool, "stf_harbor_fin", MISSING_REQUEST)

    assert out.code == "NOT_FOUND"
    assert out.details == {"entity": "request", "id": s["id"]}
    assert out.text.replace(s["id"], MISSING_REQUEST) == missing.text
    assert snapshot() == before
    assert len(payment_rows(conn)) == 0
