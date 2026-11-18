"""approve_request / reject_request (REQ-10, REQ-11, REQ-13, REQ-16–REQ-19, REQ-21).

AC-02, AC-04–AC-09; approve/reject parts of AC-13, AC-15, AC-18.
"""

import re

import pytest

from cb import models, service

P = "par_bridge_001"
F = "fund_bridge_rent"
U = "fund_bridge_utility"
MISSING_REQUEST = "req_" + "f" * 32
TIMESTAMP = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$")  # A-09
REASON = "Duplicate of earlier request"


def approve(call_tool, staff_id, request_id):
    return call_tool("approve_request", staff_id, {"request_id": request_id})


def reject(call_tool, staff_id, request_id, reason=REASON):
    return call_tool("reject_request", staff_id, {"request_id": request_id, "reason": reason})


def rent_summary(call_tool):
    return call_tool("get_funding_summary", "stf_bridge_pm", {"fund_id": F}).body["funds"][0]


def balances(summary):
    return summary["committed"], summary["paid"], summary["available"]


# --- AC-02: approve ----------------------------------------------------------------------


def test_ac02_approve_reserves_amount(call_tool):
    created = call_tool(
        "create_request", "stf_bridge_cw", {"participant_id": P, "fund_id": F, "purpose": "RENT", "amount": "300.00"}
    ).body

    out = approve(call_tool, "stf_bridge_pm", created["id"])

    assert not out.is_error
    assert out.body["status"] == "APPROVED"
    assert out.body["decided_by"] == "stf_bridge_pm"
    assert TIMESTAMP.match(out.body["decided_at"])
    assert out.body["rejection_reason"] is None
    assert out.body["payment"] is None
    # Fields fixed at creation are untouched (REQ-12).
    for field in ("id", "participant_id", "fund_id", "purpose", "description", "amount", "created_by", "created_at"):
        assert out.body[field] == created[field]
    assert call_tool("get_request", "stf_bridge_pm", {"request_id": created["id"]}).body == out.body
    assert balances(rent_summary(call_tool)) == ("300.00", "0.00", "9700.00")


def test_approve_at_service_level(conn, pm, insert_request):
    r = insert_request("PENDING", amount_cents=30_000)

    out = service.approve_request(conn, pm, models.ApproveRequestInput.model_validate({"request_id": r["id"]}))

    assert out.status == "APPROVED"
    assert out.decided_by == "stf_bridge_pm"
    row = conn.execute("SELECT status, decided_by, decided_at FROM requests WHERE id = ?", (r["id"],)).fetchone()
    assert row[:2] == ("APPROVED", "stf_bridge_pm")
    assert TIMESTAMP.match(row[2])


# --- AC-04 / AC-05: reject ------------------------------------------------------------------


def test_ac04_reject_stores_reason_and_leaves_funding(call_tool, insert_request, snapshot):
    r = insert_request("PENDING", amount_cents=30_000)
    before = snapshot()

    out = reject(call_tool, "stf_bridge_pm", r["id"])

    assert not out.is_error
    assert out.body["status"] == "REJECTED"
    assert out.body["rejection_reason"] == REASON
    assert out.body["decided_by"] == "stf_bridge_pm"
    assert TIMESTAMP.match(out.body["decided_at"])
    assert out.body["payment"] is None
    assert snapshot()["funds"] == before["funds"]
    assert snapshot()["payments"] == 0
    assert balances(rent_summary(call_tool)) == ("0.00", "0.00", "10000.00")


def test_reject_stores_trimmed_reason(conn, call_tool, insert_request):
    r = insert_request("PENDING")

    out = reject(call_tool, "stf_bridge_pm", r["id"], reason="   Duplicate of earlier request  ")

    assert out.body["rejection_reason"] == REASON
    assert conn.execute("SELECT rejection_reason FROM requests WHERE id = ?", (r["id"],)).fetchone()[0] == REASON


def test_reject_at_service_level(conn, pm, insert_request):
    r = insert_request("PENDING")

    out = service.reject_request(
        conn, pm, models.RejectRequestInput.model_validate({"request_id": r["id"], "reason": REASON})
    )

    assert (out.status, out.rejection_reason, out.decided_by) == ("REJECTED", REASON, "stf_bridge_pm")
    assert conn.execute(
        "SELECT status, rejection_reason, decided_by FROM requests WHERE id = ?", (r["id"],)
    ).fetchone() == ("REJECTED", REASON, "stf_bridge_pm")


@pytest.mark.parametrize("reason", [None, "", "   ", "x" * 501], ids=["missing", "empty", "blank", "501_chars"])
def test_ac05_invalid_reason_is_validation_error(call_tool, insert_request, snapshot, reason):
    r = insert_request("PENDING")
    before = snapshot()
    arguments = {"request_id": r["id"]} if reason is None else {"request_id": r["id"], "reason": reason}

    out = call_tool("reject_request", "stf_bridge_pm", arguments)

    assert out.code == "VALIDATION_ERROR"
    assert out.fields == ["reason"]
    assert snapshot() == before


# --- AC-06 / AC-07: availability ---------------------------------------------------------------


def test_ac06_approval_above_available_is_insufficient_funds(call_tool, insert_request, snapshot):
    insert_request("APPROVED", amount_cents=600_000)
    r2 = insert_request("PENDING", amount_cents=400_001)
    before = snapshot()

    out = approve(call_tool, "stf_bridge_pm", r2["id"])

    assert out.code == "INSUFFICIENT_FUNDS"
    assert out.details == {"request_id": r2["id"], "fund_id": F, "requested": "4000.01", "available": "4000.00"}
    assert snapshot() == before
    assert call_tool("get_request", "stf_bridge_pm", {"request_id": r2["id"]}).body["status"] == "PENDING"
    assert balances(rent_summary(call_tool)) == ("6000.00", "0.00", "4000.00")


def test_ac07_approval_of_exact_available_then_one_cent_more(call_tool, insert_request, snapshot):
    insert_request("APPROVED", amount_cents=600_000)
    r3 = insert_request("PENDING", amount_cents=400_000)

    out = approve(call_tool, "stf_bridge_pm", r3["id"])

    assert out.body["status"] == "APPROVED"
    assert balances(rent_summary(call_tool)) == ("10000.00", "0.00", "0.00")

    cent = insert_request("PENDING", amount_cents=1)
    before = snapshot()

    out = approve(call_tool, "stf_bridge_pm", cent["id"])

    assert out.code == "INSUFFICIENT_FUNDS"
    assert out.details == {"request_id": cent["id"], "fund_id": F, "requested": "0.01", "available": "0.00"}
    assert snapshot() == before


def test_paid_amounts_count_against_available(call_tool, insert_request, snapshot):
    # §6.2 / §7: available = allocation − committed − paid.
    insert_request("PAID", amount_cents=600_000)
    r = insert_request("PENDING", amount_cents=400_001)
    before = snapshot()

    out = approve(call_tool, "stf_bridge_pm", r["id"])

    assert out.code == "INSUFFICIENT_FUNDS"
    assert out.details == {"request_id": r["id"], "fund_id": F, "requested": "4000.01", "available": "4000.00"}
    assert snapshot() == before


def test_availability_counts_only_the_requests_fund(call_tool, insert_request):
    # Approved money on another fund, another nonprofit, or in PENDING/REJECTED requests does not count.
    insert_request("APPROVED", amount_cents=250_000, fund_id=U)
    insert_request("APPROVED", amount_cents=500_000, nonprofit_id="np_harbor")
    insert_request("PENDING", amount_cents=900_000)
    insert_request("REJECTED", amount_cents=900_000)
    r = insert_request("PENDING", amount_cents=1_000_000)

    out = approve(call_tool, "stf_bridge_pm", r["id"])

    assert out.body["status"] == "APPROVED"
    assert balances(rent_summary(call_tool)) == ("10000.00", "0.00", "0.00")


# --- AC-08 / AC-09: invalid transitions -------------------------------------------------------


def test_ac08_second_approval_is_invalid_transition(call_tool, insert_request, snapshot):
    r = insert_request("APPROVED", amount_cents=30_000)
    before = snapshot()

    out = approve(call_tool, "stf_bridge_pm", r["id"])

    assert out.code == "INVALID_TRANSITION"
    assert out.details == {"request_id": r["id"], "current_status": "APPROVED", "attempted": "APPROVE"}
    assert snapshot() == before
    assert balances(rent_summary(call_tool)) == ("300.00", "0.00", "9700.00")


@pytest.mark.parametrize(
    "action,status",
    [
        ("approve", "REJECTED"),
        ("approve", "PAID"),
        ("reject", "REJECTED"),
        ("reject", "PAID"),
        ("reject", "APPROVED"),
    ],
)
def test_ac09_decision_on_non_pending_request_is_invalid_transition(
    call_tool, insert_request, snapshot, action, status
):
    r = insert_request(status)
    before = snapshot()

    if action == "approve":
        out = approve(call_tool, "stf_bridge_pm", r["id"])
    else:
        out = reject(call_tool, "stf_bridge_pm", r["id"])

    assert out.code == "INVALID_TRANSITION"
    assert out.details == {
        "request_id": r["id"],
        "current_status": status,
        "attempted": "APPROVE" if action == "approve" else "REJECT",
    }
    assert snapshot() == before


def test_transition_is_checked_before_availability(call_tool, insert_request, snapshot):
    # §6.3 step 5: INVALID_TRANSITION wins over INSUFFICIENT_FUNDS on a full fund.
    r = insert_request("APPROVED", amount_cents=600_000)
    insert_request("APPROVED", amount_cents=400_000)
    before = snapshot()

    out = approve(call_tool, "stf_bridge_pm", r["id"])

    assert out.code == "INVALID_TRANSITION"
    assert out.details["current_status"] == "APPROVED"
    assert snapshot() == before


# --- AC-13 / AC-15: roles -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "staff_id,role", [("stf_bridge_cw", "CASE_WORKER"), ("stf_bridge_fin", "FINANCE")], ids=["ac13_cw", "ac15_fin"]
)
@pytest.mark.parametrize("action", ["approve", "reject"])
def test_ac13_ac15_only_program_manager_decides(call_tool, insert_request, snapshot, staff_id, role, action):
    r = insert_request("PENDING")
    before = snapshot()

    if action == "approve":
        out = approve(call_tool, staff_id, r["id"])
    else:
        out = reject(call_tool, staff_id, r["id"])

    tool = f"{action}_request"
    assert out.code == "FORBIDDEN_ROLE"
    assert out.details == {"role": role, "tool": tool, "allowed_roles": ["PROGRAM_MANAGER"]}
    assert snapshot() == before


# --- AC-18: other nonprofit ------------------------------------------------------------------------


@pytest.mark.parametrize("action", ["approve", "reject"])
def test_ac18_other_nonprofit_decision_is_not_found(call_tool, insert_request, snapshot, action):
    r = insert_request("PENDING")
    before = snapshot()

    if action == "approve":
        out = approve(call_tool, "stf_harbor_pm", r["id"])
        missing = approve(call_tool, "stf_harbor_pm", MISSING_REQUEST)
    else:
        out = reject(call_tool, "stf_harbor_pm", r["id"])
        missing = reject(call_tool, "stf_harbor_pm", MISSING_REQUEST)

    assert out.code == "NOT_FOUND"
    assert out.details == {"entity": "request", "id": r["id"]}
    # Same response as for a nonexistent id (REQ-05).
    assert out.text.replace(r["id"], MISSING_REQUEST) == missing.text
    assert snapshot() == before


def test_reject_nonexistent_is_not_found(call_tool, snapshot):
    before = snapshot()

    out = reject(call_tool, "stf_bridge_pm", "req_doesnotexist")

    assert out.code == "NOT_FOUND"
    assert out.details == {"entity": "request", "id": "req_doesnotexist"}
    assert snapshot() == before
