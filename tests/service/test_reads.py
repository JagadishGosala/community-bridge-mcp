"""Read tools (REQ-16, REQ-22–REQ-25; AC-16, AC-35, AC-39)."""

import pytest

from cb import models, service
from cb.errors import AppError

F = "fund_bridge_rent"
U = "fund_bridge_utility"

BRIDGE_PARTICIPANTS = [
    {"id": "par_bridge_001", "display_name": "Jordan Avery"},
    {"id": "par_bridge_002", "display_name": "Sam Patel"},
    {"id": "par_bridge_003", "display_name": "Riley Chen"},
]
BRIDGE_FUNDS = [
    {"id": "fund_bridge_rent", "name": "Emergency Rent Relief", "allocation": "10000.00"},
    {"id": "fund_bridge_utility", "name": "Utility Assistance", "allocation": "2500.00"},
]
FRESH_RENT = {
    "fund_id": F,
    "fund_name": "Emergency Rent Relief",
    "allocation": "10000.00",
    "committed": "0.00",
    "paid": "0.00",
    "available": "10000.00",
}
FRESH_UTILITY = {
    "fund_id": U,
    "fund_name": "Utility Assistance",
    "allocation": "2500.00",
    "committed": "0.00",
    "paid": "0.00",
    "available": "2500.00",
}


def dump(output):
    return output.model_dump(mode="json")


def summary(conn, caller, fund_id=None):
    args = {} if fund_id is None else {"fund_id": fund_id}
    return dump(service.get_funding_summary(conn, caller, models.GetFundingSummaryInput.model_validate(args)))


def list_requests(conn, caller, **filters):
    return dump(service.list_requests(conn, caller, models.ListRequestsInput.model_validate(filters)))["requests"]


# --- AC-16: every role, every read tool, only np_bridge data -------------------------


@pytest.mark.parametrize("staff_id,role", [
    ("stf_bridge_cw", "CASE_WORKER"),
    ("stf_bridge_pm", "PROGRAM_MANAGER"),
    ("stf_bridge_fin", "FINANCE"),
])
def test_ac16_every_role_can_use_every_read_tool(call_tool, insert_request, staff_id, role):
    r = insert_request("PENDING")
    insert_request("PENDING", nonprofit_id="np_harbor")

    out = call_tool("whoami", staff_id)
    assert not out.is_error
    assert (out.body["staff_id"], out.body["role"], out.body["nonprofit_id"]) == (staff_id, role, "np_bridge")

    out = call_tool("list_participants", staff_id)
    assert out.body == {"participants": BRIDGE_PARTICIPANTS}

    out = call_tool("list_funds", staff_id)
    assert out.body == {"funds": BRIDGE_FUNDS}

    out = call_tool("get_funding_summary", staff_id)
    assert out.body == {"funds": [FRESH_RENT, FRESH_UTILITY]}

    out = call_tool("get_request", staff_id, {"request_id": r["id"]})
    assert out.body == r

    out = call_tool("list_requests", staff_id)
    assert out.body == {"requests": [r]}


# --- service-level reads ---------------------------------------------------------------


def test_list_participants_and_funds(conn, cw):
    assert dump(service.list_participants(conn, cw, models.ListParticipantsInput.model_validate({}))) == {
        "participants": BRIDGE_PARTICIPANTS
    }
    assert dump(service.list_funds(conn, cw, models.ListFundsInput.model_validate({}))) == {"funds": BRIDGE_FUNDS}


@pytest.mark.parametrize("status", ["PENDING", "APPROVED", "REJECTED", "PAID"])
def test_get_request_returns_full_request_in_every_status(conn, pm, insert_request, status):
    r = insert_request(status, amount_cents=12_345, purpose="OTHER", description="Bus pass for job interview")

    out = dump(service.get_request(conn, pm, models.GetRequestInput.model_validate({"request_id": r["id"]})))

    assert out == r
    if status == "PAID":
        assert out["payment"]["amount"] == "123.45"
        assert out["payment"]["recorded_by"] == "stf_bridge_fin"
    else:
        assert out["payment"] is None


def test_fresh_summary_for_one_fund_and_all_funds(conn, fin):
    assert summary(conn, fin, F) == {"funds": [FRESH_RENT]}
    assert summary(conn, fin) == {"funds": [FRESH_RENT, FRESH_UTILITY]}


# --- REQ-16 read side: committed / paid / available ------------------------------------


def test_req16_brief_example_approved(conn, cw, insert_request):
    insert_request("APPROVED", amount_cents=30_000)
    assert summary(conn, cw, F) == {
        "funds": [{**FRESH_RENT, "committed": "300.00", "paid": "0.00", "available": "9700.00"}]
    }


def test_req16_brief_example_paid(conn, cw, insert_request):
    insert_request("PAID", amount_cents=30_000)
    assert summary(conn, cw, F) == {
        "funds": [{**FRESH_RENT, "committed": "0.00", "paid": "300.00", "available": "9700.00"}]
    }


def test_req16_summary_counts_only_approved_and_paid_of_the_fund(conn, cw, insert_request):
    insert_request("PENDING", amount_cents=50_000)
    insert_request("APPROVED", amount_cents=30_000)
    insert_request("APPROVED", amount_cents=15_025)
    insert_request("PAID", amount_cents=100_000)
    insert_request("REJECTED", amount_cents=20_000)
    insert_request("APPROVED", amount_cents=7_000, fund_id=U)
    insert_request("APPROVED", amount_cents=99_999, nonprofit_id="np_harbor")
    insert_request("PAID", amount_cents=1_000, nonprofit_id="np_harbor")

    rent = {**FRESH_RENT, "committed": "450.25", "paid": "1000.00", "available": "8549.75"}
    utility = {**FRESH_UTILITY, "committed": "70.00", "paid": "0.00", "available": "2430.00"}
    assert summary(conn, cw, F) == {"funds": [rent]}
    assert summary(conn, cw) == {"funds": [rent, utility]}


# --- AC-35: nonexistent ids ------------------------------------------------------------


def test_ac35_get_request_nonexistent(conn, cw, call_tool):
    with pytest.raises(AppError) as exc:
        service.get_request(conn, cw, models.GetRequestInput.model_validate({"request_id": "req_doesnotexist"}))
    assert exc.value.code == "NOT_FOUND"
    assert exc.value.details == {"entity": "request", "id": "req_doesnotexist"}

    out = call_tool("get_request", "stf_bridge_cw", {"request_id": "req_doesnotexist"})
    assert out.code == "NOT_FOUND"
    assert out.details == {"entity": "request", "id": "req_doesnotexist"}


def test_ac35_summary_for_nonexistent_fund(conn, cw, call_tool):
    with pytest.raises(AppError) as exc:
        summary(conn, cw, "fund_nope")
    assert exc.value.code == "NOT_FOUND"
    assert exc.value.details == {"entity": "fund", "id": "fund_nope"}

    out = call_tool("get_funding_summary", "stf_bridge_cw", {"fund_id": "fund_nope"})
    assert out.code == "NOT_FOUND"
    assert out.details == {"entity": "fund", "id": "fund_nope"}


def test_ac35_approve_nonexistent(call_tool):
    out = call_tool("approve_request", "stf_bridge_pm", {"request_id": "req_doesnotexist"})
    assert out.code == "NOT_FOUND"
    assert out.details == {"entity": "request", "id": "req_doesnotexist"}


def test_list_requests_with_unknown_fund_is_not_found(conn, cw, call_tool):
    # §8: list_requests extra error NOT_FOUND (unknown fund_id).
    with pytest.raises(AppError) as exc:
        list_requests(conn, cw, fund_id="fund_nope")
    assert exc.value.code == "NOT_FOUND"
    assert exc.value.details == {"entity": "fund", "id": "fund_nope"}

    out = call_tool("list_requests", "stf_bridge_cw", {"fund_id": "fund_nope"})
    assert out.code == "NOT_FOUND"


# --- AC-39: list_requests filters and order ----------------------------------------------


def test_ac39_list_requests_filters(conn, pm, insert_request, call_tool):
    r1 = insert_request("PENDING")
    r2 = insert_request("APPROVED")
    r3 = insert_request("PENDING", fund_id=U)

    assert list_requests(conn, pm, status="PENDING") == [r1, r3]
    assert list_requests(conn, pm, fund_id=F) == [r1, r2]
    assert list_requests(conn, pm, status="PENDING", fund_id=F) == [r1]
    assert list_requests(conn, pm) == [r1, r2, r3]

    out = call_tool("list_requests", "stf_bridge_pm", {"status": "DONE"})
    assert out.code == "VALIDATION_ERROR"
    assert out.fields == ["status"]


def test_list_requests_ordered_by_created_at_then_id(conn, cw, insert_request):
    # A-14
    late_b = insert_request(request_id="req_b", created_at="2026-11-18T12:00:00Z")
    late_a = insert_request(request_id="req_a", created_at="2026-11-18T12:00:00Z")
    early_z = insert_request(request_id="req_z", created_at="2026-11-18T11:00:00Z")

    assert list_requests(conn, cw) == [early_z, late_a, late_b]
