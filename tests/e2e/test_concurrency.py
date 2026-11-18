"""Concurrent approvals from two server processes never overspend (REQ-19; AC-30, SPEC §10)."""

import asyncio
import json

import anyio
import pytest

from cb import server

pytestmark = pytest.mark.anyio

F = "fund_bridge_rent"
DELAY_MS = "300"  # CB_TEST_TX_DELAY_MS: hold the write lock so the two approvals overlap


def create_request(amount):
    """Set-up through the in-process adapter (CB_DB_PATH points at the test database)."""
    result = server.run_tool(
        server.TOOLS["create_request"],
        "stf_bridge_cw",
        {"participant_id": "par_bridge_001", "fund_id": F, "purpose": "RENT", "amount": amount},
    )
    assert not result.is_error
    return result.structured_content["id"]


@pytest.mark.parametrize("iteration", range(10))
async def test_ac30_concurrent_approvals_never_overspend(seeded_db, mcp_session, iteration):
    r_a = create_request("6000.00")
    r_b = create_request("6000.00")

    with anyio.fail_after(60):
        async with (
            mcp_session("stf_bridge_pm", seeded_db, CB_TEST_TX_DELAY_MS=DELAY_MS) as pm_a,
            mcp_session("stf_bridge_pm", seeded_db, CB_TEST_TX_DELAY_MS=DELAY_MS) as pm_b,
        ):
            # Both sessions are initialized; send both approvals at the same time.
            result_a, result_b = await asyncio.gather(
                pm_a.call_tool("approve_request", {"request_id": r_a}),
                pm_b.call_tool("approve_request", {"request_id": r_b}),
            )
            results = {r_a: result_a, r_b: result_b}
            approved = [rid for rid, r in results.items() if not r.is_error]
            refused = [rid for rid, r in results.items() if r.is_error]

            assert len(approved) == 1, {rid: r.content[0].text for rid, r in results.items()}
            assert len(refused) == 1
            assert results[approved[0]].structured_content["status"] == "APPROVED"
            error = json.loads(results[refused[0]].content[0].text)["error"]
            assert error["code"] == "INSUFFICIENT_FUNDS"
            assert error["details"] == {
                "request_id": refused[0],
                "fund_id": F,
                "requested": "6000.00",
                "available": "4000.00",
            }

            still_pending = await pm_a.call_tool("get_request", {"request_id": refused[0]})
            assert still_pending.structured_content["status"] == "PENDING"
            summary = (await pm_b.call_tool("get_funding_summary", {"fund_id": F})).structured_content
            assert summary["funds"][0]["committed"] == "6000.00"
            assert summary["funds"][0]["paid"] == "0.00"
            assert summary["funds"][0]["available"] == "4000.00"
