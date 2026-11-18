"""Walking skeleton over a real MCP stdio connection (AC-38, partial AC-29)."""

import json
import sys
from contextlib import asynccontextmanager

import anyio
import pytest
from mcp import ClientSession, StdioServerParameters, stdio_client
from mcp_types.version import LATEST_HANDSHAKE_VERSION

pytestmark = pytest.mark.anyio

SERVER = [sys.executable, "-m", "cb.server"]

SEED_STAFF = [
    ("stf_bridge_cw", "Casey Morgan", "CASE_WORKER", "np_bridge", "Community Bridge"),
    ("stf_bridge_pm", "Priya Shah", "PROGRAM_MANAGER", "np_bridge", "Community Bridge"),
    ("stf_bridge_fin", "Felix Ortega", "FINANCE", "np_bridge", "Community Bridge"),
    ("stf_harbor_cw", "Hana Lee", "CASE_WORKER", "np_harbor", "Harbor Neighbors"),
    ("stf_harbor_pm", "Marcus Bell", "PROGRAM_MANAGER", "np_harbor", "Harbor Neighbors"),
    ("stf_harbor_fin", "Nadia Cole", "FINANCE", "np_harbor", "Harbor Neighbors"),
]


@asynccontextmanager
async def mcp_session(env, errlog):
    params = StdioServerParameters(command=SERVER[0], args=SERVER[1:], env=env)
    async with stdio_client(params, errlog=errlog) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        yield session


@pytest.mark.parametrize(
    "staff_id,staff_name,role,nonprofit_id,nonprofit_name", SEED_STAFF, ids=[s[0] for s in SEED_STAFF]
)
async def test_ac38_whoami_as_each_seed_identity(
    seeded_db, server_env, tmp_path, staff_id, staff_name, role, nonprofit_id, nonprofit_name
):
    expected = {
        "staff_id": staff_id,
        "staff_name": staff_name,
        "role": role,
        "nonprofit_id": nonprofit_id,
        "nonprofit_name": nonprofit_name,
    }
    with open(tmp_path / "stderr.txt", "w") as errlog:
        with anyio.fail_after(30):
            async with mcp_session(server_env(staff_id, seeded_db), errlog) as session:
                result = await session.call_tool("whoami", {})

    assert result.is_error is False
    assert result.structured_content == expected
    assert len(result.content) == 1
    assert json.loads(result.content[0].text) == expected


async def test_whoami_schemas_are_flat_and_closed(seeded_db, server_env, tmp_path):
    with open(tmp_path / "stderr.txt", "w") as errlog:
        with anyio.fail_after(30):
            async with mcp_session(server_env("stf_bridge_cw", seeded_db), errlog) as session:
                tools = {t.name: t for t in (await session.list_tools()).tools}

    whoami = tools["whoami"]
    assert whoami.input_schema["type"] == "object"
    assert whoami.input_schema["properties"] == {}
    assert whoami.input_schema["additionalProperties"] is False
    assert whoami.output_schema is not None
    assert set(whoami.output_schema["properties"]) == {
        "staff_id",
        "staff_name",
        "role",
        "nonprofit_id",
        "nonprofit_name",
    }


async def test_whoami_unknown_field_returns_validation_error_body(seeded_db, server_env, tmp_path):
    with open(tmp_path / "stderr.txt", "w") as errlog:
        with anyio.fail_after(30):
            async with mcp_session(server_env("stf_bridge_cw", seeded_db), errlog) as session:
                result = await session.call_tool("whoami", {"role": "PROGRAM_MANAGER"})

    assert result.is_error is True
    assert result.structured_content is None
    assert len(result.content) == 1
    # The whole text must parse as the §6.5 body: no prefix, no extra text.
    body = json.loads(result.content[0].text)
    assert set(body) == {"error"}
    assert set(body["error"]) == {"code", "message", "details"}
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert isinstance(body["error"]["message"], str) and body["error"]["message"]
    assert [f["field"] for f in body["error"]["details"]["fields"]] == ["role"]


async def test_stdout_carries_only_jsonrpc(seeded_db, server_env, tmp_path):
    """Partial AC-29: raw stdout is JSON-RPC 2.0 only; logs go to stderr."""
    stderr_path = tmp_path / "stderr.txt"
    stdout_lines: list[bytes] = []
    buffer = b""

    async def send(proc, message):
        await proc.stdin.send(json.dumps(message).encode() + b"\n")

    async def response(proc, request_id):
        nonlocal buffer
        while True:
            while b"\n" not in buffer:
                buffer += await proc.stdout.receive()
            line, buffer = buffer.split(b"\n", 1)
            stdout_lines.append(line)
            message = json.loads(line)
            if message.get("id") == request_id:
                return message

    with open(stderr_path, "wb") as errlog:
        with anyio.fail_after(30):
            proc = await anyio.open_process(SERVER, env=server_env("stf_bridge_cw", seeded_db), stderr=errlog)
            async with proc:
                await send(proc, {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": LATEST_HANDSHAKE_VERSION,
                        "capabilities": {},
                        "clientInfo": {"name": "stdout-test", "version": "0"},
                    },
                })
                init = await response(proc, 1)
                await send(proc, {"jsonrpc": "2.0", "method": "notifications/initialized"})
                await send(proc, {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": "whoami", "arguments": {}},
                })
                ok = await response(proc, 2)
                await send(proc, {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "whoami", "arguments": {"role": "PROGRAM_MANAGER"}},
                })
                bad = await response(proc, 3)
                await proc.stdin.aclose()
                await proc.wait()
                try:
                    while True:
                        buffer += await proc.stdout.receive()
                except anyio.EndOfStream:
                    pass
                stdout_lines.extend(buffer.split(b"\n"))

    assert "result" in init
    assert ok["result"]["isError"] is False
    assert bad["result"]["isError"] is True
    for line in stdout_lines:
        if line.strip():
            message = json.loads(line)
            assert message["jsonrpc"] == "2.0"
    assert stderr_path.read_text().strip() != ""
