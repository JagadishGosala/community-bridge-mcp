"""End-to-end flow over real MCP stdio sessions, one server process per identity (AC-31, AC-34)."""

import anyio
import pytest

pytestmark = pytest.mark.anyio

F = "fund_bridge_rent"
CREATE = {"participant_id": "par_bridge_001", "fund_id": F, "purpose": "RENT", "amount": "300.00"}


def ok(result):
    assert not result.is_error, result.content[0].text
    return result.structured_content


async def test_ac31_create_approve_pay_across_three_identities(seeded_db, mcp_session):
    with anyio.fail_after(60):
        async with mcp_session("stf_bridge_cw", seeded_db) as cw:
            tools = (await cw.list_tools()).tools
            assert len(tools) == 10
            assert all(t.input_schema and t.output_schema for t in tools)
            assert ok(await cw.call_tool("whoami", {}))["role"] == "CASE_WORKER"
            created = ok(await cw.call_tool("create_request", CREATE))
            assert (created["status"], created["amount"], created["created_by"]) == (
                "PENDING",
                "300.00",
                "stf_bridge_cw",
            )

        async with mcp_session("stf_bridge_pm", seeded_db) as pm:
            assert ok(await pm.call_tool("whoami", {}))["role"] == "PROGRAM_MANAGER"
            approved = ok(await pm.call_tool("approve_request", {"request_id": created["id"]}))
            assert (approved["status"], approved["decided_by"]) == ("APPROVED", "stf_bridge_pm")

        async with mcp_session("stf_bridge_fin", seeded_db) as fin:
            assert ok(await fin.call_tool("whoami", {}))["role"] == "FINANCE"
            paid = ok(await fin.call_tool("record_payment", {"request_id": created["id"]}))
            assert paid["status"] == "PAID"
            assert (paid["payment"]["amount"], paid["payment"]["recorded_by"]) == ("300.00", "stf_bridge_fin")
            final = ok(await fin.call_tool("get_request", {"request_id": created["id"]}))
            summary = ok(await fin.call_tool("get_funding_summary", {"fund_id": F}))

    assert final == paid
    assert summary == {
        "funds": [
            {
                "fund_id": F,
                "fund_name": "Emergency Rent Relief",
                "allocation": "10000.00",
                "committed": "0.00",
                "paid": "300.00",
                "available": "9700.00",
            }
        ]
    }


async def test_ac34_request_survives_server_restart(seeded_db, mcp_session):
    with anyio.fail_after(60):
        async with mcp_session("stf_bridge_cw", seeded_db) as first:
            created = ok(await first.call_tool("create_request", CREATE))
        # The first server process has exited; a new one reads the same SQLite file.
        async with mcp_session("stf_bridge_cw", seeded_db) as second:
            again = ok(await second.call_tool("get_request", {"request_id": created["id"]}))

    assert again == created
