"""Tool discovery over a real MCP stdio connection (REQ-12, REQ-26; AC-40)."""

import re
from pathlib import Path

import anyio
import pytest
from mcp.shared.exceptions import MCPError
from mcp_types.jsonrpc import METHOD_NOT_FOUND

pytestmark = pytest.mark.anyio

READ_TOOLS = {"whoami", "list_participants", "list_funds", "get_funding_summary", "get_request", "list_requests"}
WRITE_TOOLS = {"create_request", "approve_request", "reject_request", "record_payment"}
SPEC = Path(__file__).resolve().parents[2] / "docs" / "SPEC.md"


def spec_descriptions() -> dict[str, str]:
    """Tool descriptions from the SPEC §8 table."""
    rows = re.findall(r'^\| `(\w+)` \| "(.*?)" \|', SPEC.read_text(encoding="utf-8"), re.M)
    return {name: text.replace('\\"', '"') for name, text in rows}


async def test_ac40_exactly_the_ten_spec_tools(seeded_db, mcp_session):
    with anyio.fail_after(30):
        async with mcp_session("stf_bridge_cw", seeded_db) as session:
            tools = (await session.list_tools()).tools

    names = [t.name for t in tools]
    assert len(names) == 10
    assert set(names) == READ_TOOLS | WRITE_TOOLS
    assert {t.name: t.description for t in tools} == spec_descriptions()
    # REQ-12: nothing edits or deletes a request.
    assert not [n for n in names if re.search(r"edit|update|delete|remove|cancel", n)]

    for tool in tools:
        assert tool.input_schema["type"] == "object", tool.name
        assert tool.input_schema["additionalProperties"] is False, tool.name
        assert tool.output_schema is not None, tool.name
        assert tool.output_schema["type"] == "object", tool.name
        read_only = bool(tool.annotations and tool.annotations.read_only_hint)
        assert read_only is (tool.name in READ_TOOLS), tool.name


async def test_ac40_no_resources_or_prompts(seeded_db, mcp_session):
    with anyio.fail_after(30):
        async with mcp_session("stf_bridge_cw", seeded_db) as session:
            capabilities = session.initialize_result.capabilities
            listings = {}
            for name, method in [("resources", session.list_resources), ("prompts", session.list_prompts)]:
                try:
                    listings[name] = getattr(await method(), name)
                except MCPError as exc:
                    listings[name] = exc.code

    assert capabilities.resources is None
    assert capabilities.prompts is None
    for name, listing in listings.items():
        assert listing in ([], METHOD_NOT_FOUND), (name, listing)
