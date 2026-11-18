"""Identity re-resolution, unexpected exceptions and check order through the in-process adapter.

AC-23, AC-36, REQ-28 (AC-37 waits for approve_request in batch E).
"""

import dataclasses
import json
import logging

import pytest

from cb import server

VALID_CREATE = {
    "participant_id": "par_bridge_001",
    "fund_id": "fund_bridge_rent",
    "purpose": "RENT",
    "amount": "300.00",
}


@pytest.mark.parametrize(
    "tool,arguments",
    [("whoami", {}), ("list_funds", {}), ("get_funding_summary", {}), ("create_request", VALID_CREATE)],
    ids=["whoami", "list_funds", "get_funding_summary", "create_request"],
)
def test_ac23_deleted_staff_row_gives_unauthenticated(conn, call_tool, snapshot, tool, arguments):
    conn.execute("DELETE FROM staff WHERE id = 'stf_bridge_cw'")
    before = snapshot()

    out = call_tool(tool, "stf_bridge_cw", arguments)

    assert out.is_error
    assert out.code == "UNAUTHENTICATED"
    assert out.details == {}
    assert snapshot() == before


def test_req28_validation_runs_before_identity(conn, call_tool, snapshot):
    conn.execute("DELETE FROM staff WHERE id = 'stf_bridge_cw'")
    before = snapshot()

    out = call_tool("create_request", "stf_bridge_cw", {**VALID_CREATE, "amount": "abc"})

    assert out.code == "VALIDATION_ERROR"
    assert out.fields == ["amount"]
    assert snapshot() == before


def _raise_boom(conn, caller, args):
    raise RuntimeError("boom")


def _run_bad_sql(conn, caller, args):
    conn.execute("SELECT secret_column FROM no_such_table")


@pytest.mark.parametrize("handler", [_raise_boom, _run_bad_sql], ids=["runtime_error", "sql_error"])
def test_ac36_unexpected_exception_gives_internal_error_without_leaks(db_path, caplog, handler):
    spec = dataclasses.replace(server.TOOLS["list_funds"], handler=handler)

    with caplog.at_level(logging.ERROR):
        result = server.run_tool(spec, "stf_bridge_cw", {})

    assert result.is_error is True
    assert result.structured_content is None
    text = result.content[0].text
    body = json.loads(text)
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert set(body["error"]["details"]) == {"error_id", "retryable"}
    error_id = body["error"]["details"]["error_id"]
    assert isinstance(error_id, str) and error_id
    assert body["error"]["details"]["retryable"] is False
    for leaked in ["boom", "Traceback", "RuntimeError", "no_such_table", "secret_column", "SELECT", "sqlite"]:
        assert leaked not in text
    # The traceback goes to the (stderr) log together with the error_id.
    logged = [r for r in caplog.records if r.exc_info and error_id in r.getMessage()]
    assert logged


@pytest.mark.skip(reason="batch E")
def test_ac37_check_order_validation_then_role_then_ownership(call_tool, insert_request):
    r = insert_request("PENDING")
    r_h = insert_request("PENDING", nonprofit_id="np_harbor")

    out = call_tool("approve_request", "stf_bridge_cw", {})
    assert out.code == "VALIDATION_ERROR"
    assert out.fields == ["request_id"]

    out = call_tool("approve_request", "stf_bridge_cw", {"request_id": r_h["id"]})
    assert out.code == "FORBIDDEN_ROLE"

    out = call_tool("approve_request", "stf_harbor_pm", {"request_id": r["id"]})
    assert out.code == "NOT_FOUND"
    assert out.details == {"entity": "request", "id": r["id"]}
