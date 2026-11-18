"""Nonprofit boundary on reads (REQ-05; AC-17)."""

import pytest

from cb import models, service
from cb.errors import AppError

F = "fund_bridge_rent"
MISSING_REQUEST = "req_" + "f" * 32
MISSING_FUND = "fund_nope"

HARBOR_PARTICIPANTS = [
    {"id": "par_harbor_001", "display_name": "Taylor Brooks"},
    {"id": "par_harbor_002", "display_name": "Morgan Diaz"},
]
HARBOR_FUNDS = [{"id": "fund_harbor_general", "name": "General Emergency Assistance", "allocation": "5000.00"}]


def test_ac17_other_nonprofit_request_is_not_found_like_a_missing_one(call_tool, insert_request):
    r = insert_request("PENDING")

    out = call_tool("get_request", "stf_harbor_cw", {"request_id": r["id"]})
    missing = call_tool("get_request", "stf_harbor_cw", {"request_id": MISSING_REQUEST})

    assert out.code == "NOT_FOUND"
    assert out.details == {"entity": "request", "id": r["id"]}
    assert out.text.replace(r["id"], MISSING_REQUEST) == missing.text


def test_ac17_other_nonprofit_fund_summary_is_not_found_like_a_missing_one(call_tool):
    out = call_tool("get_funding_summary", "stf_harbor_cw", {"fund_id": F})
    missing = call_tool("get_funding_summary", "stf_harbor_cw", {"fund_id": MISSING_FUND})

    assert out.code == "NOT_FOUND"
    assert out.details == {"entity": "fund", "id": F}
    assert out.text.replace(F, MISSING_FUND) == missing.text


def test_ac17_list_requests_filtered_by_other_nonprofit_fund_is_not_found(call_tool, insert_request):
    insert_request("PENDING")

    out = call_tool("list_requests", "stf_harbor_cw", {"fund_id": F})
    missing = call_tool("list_requests", "stf_harbor_cw", {"fund_id": MISSING_FUND})

    assert out.code == "NOT_FOUND"
    assert out.details == {"entity": "fund", "id": F}
    assert out.text.replace(F, MISSING_FUND) == missing.text


def test_ac17_lists_contain_only_own_nonprofit_records(call_tool, insert_request):
    insert_request("PENDING")
    insert_request("APPROVED")
    h = insert_request("PENDING", nonprofit_id="np_harbor")

    assert call_tool("list_requests", "stf_harbor_cw").body == {"requests": [h]}
    assert call_tool("list_participants", "stf_harbor_cw").body == {"participants": HARBOR_PARTICIPANTS}
    assert call_tool("list_funds", "stf_harbor_cw").body == {"funds": HARBOR_FUNDS}
    assert call_tool("get_funding_summary", "stf_harbor_cw").body == {
        "funds": [
            {
                "fund_id": "fund_harbor_general",
                "fund_name": "General Emergency Assistance",
                "allocation": "5000.00",
                "committed": "0.00",
                "paid": "0.00",
                "available": "5000.00",
            }
        ]
    }


def test_service_get_request_of_other_nonprofit_raises_not_found(conn, h_cw, insert_request):
    r = insert_request("PAID")

    with pytest.raises(AppError) as exc:
        service.get_request(conn, h_cw, models.GetRequestInput.model_validate({"request_id": r["id"]}))

    assert exc.value.code == "NOT_FOUND"
    assert exc.value.details == {"entity": "request", "id": r["id"]}


def test_service_reads_for_bridge_exclude_harbor_records(conn, cw, insert_request):
    r = insert_request("APPROVED")
    insert_request("APPROVED", nonprofit_id="np_harbor")

    out = service.list_requests(conn, cw, models.ListRequestsInput.model_validate({}))

    assert out.model_dump(mode="json") == {"requests": [r]}
