"""Community Bridge MCP demo: a scripted MCP client over stdio, no LLM (REQ-33, AC-31).

Run with:  uv run python scripts/demo.py

It resets a throwaway database in a temp directory (./data is not touched), then:
  1. as stf_bridge_cw (CASE_WORKER): discovers the tools and creates a 300.00 request
  2. as stf_bridge_pm (PROGRAM_MANAGER): approves it
  3. as stf_bridge_fin (FINANCE): records the payment and reads the funding summary
Each identity is a separate cb-server process, selected with CB_STAFF_ID.
Demo output goes to stdout; server logs go to stderr. Exit code 0 on success.
"""

import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters, stdio_client

from cb import reset

FUND = "fund_bridge_rent"


class DemoError(Exception):
    pass


def show(title, data):
    print(f"\n=== {title}")
    print(json.dumps(data, indent=2))


@asynccontextmanager
async def session_as(staff_id, db_path):
    """Start a cb-server process acting as staff_id and open an initialized MCP session to it."""
    env = {**os.environ, "CB_STAFF_ID": staff_id, "CB_DB_PATH": str(db_path)}
    params = StdioServerParameters(command=sys.executable, args=["-m", "cb.server"], env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        me = await call(session, "whoami", {})
        print(f"\n--- connected as {me['staff_id']} ({me['role']}, {me['nonprofit_id']})")
        yield session


async def call(session, tool, arguments):
    result = await session.call_tool(tool, arguments)
    body = json.loads(result.content[0].text)
    if result.is_error:
        raise DemoError(f"{tool} failed: {json.dumps(body)}")
    return body


async def run(db_path):
    async with session_as("stf_bridge_cw", db_path) as cw:
        tools = (await cw.list_tools()).tools
        show(f"Step 1: discovered {len(tools)} tools", [t.name for t in tools])
        request = await call(
            cw,
            "create_request",
            {"participant_id": "par_bridge_001", "fund_id": FUND, "purpose": "RENT", "amount": "300.00"},
        )
        show("Step 2: create_request 300.00 (CASE_WORKER)", request)

    async with session_as("stf_bridge_pm", db_path) as pm:
        show("Step 3: approve_request (PROGRAM_MANAGER)", await call(pm, "approve_request", {"request_id": request["id"]}))
        show("Funding after approval", await call(pm, "get_funding_summary", {"fund_id": FUND}))

    async with session_as("stf_bridge_fin", db_path) as fin:
        show("Step 4: record_payment (FINANCE)", await call(fin, "record_payment", {"request_id": request["id"]}))
        summary = await call(fin, "get_funding_summary", {"fund_id": FUND})

    show("Final funding summary", summary)


def main() -> int:
    failure = None
    with tempfile.TemporaryDirectory(prefix="cb-demo-", ignore_cleanup_errors=True) as tmp:
        db_path = Path(tmp) / "cb.sqlite3"
        os.environ["CB_DB_PATH"] = str(db_path)
        reset.main()
        try:
            anyio.run(run, db_path)
        except* DemoError as group:
            failure = group.exceptions[0]
    if failure is not None:
        print(f"demo failed: {failure}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
