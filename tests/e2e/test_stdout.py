"""Stdout carries only JSON-RPC; logs go to stderr (REQ-29; AC-29 over the AC-31 flow)."""

import json
import sys
from contextlib import asynccontextmanager

import anyio
import pytest
from mcp_types.version import LATEST_HANDSHAKE_VERSION

pytestmark = pytest.mark.anyio

SERVER = [sys.executable, "-m", "cb.server"]
F = "fund_bridge_rent"


class RawServer:
    """A cb-server process driven with raw JSON-RPC lines; keeps every stdout line it prints."""

    def __init__(self, process):
        self.process = process
        self.buffer = b""
        self.stdout_lines: list[bytes] = []
        self.next_id = 1

    async def _send(self, message):
        await self.process.stdin.send(json.dumps(message).encode() + b"\n")

    async def notify(self, method):
        await self._send({"jsonrpc": "2.0", "method": method})

    async def request(self, method, params=None):
        request_id = self.next_id
        self.next_id += 1
        await self._send({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        while True:
            while b"\n" not in self.buffer:
                self.buffer += await self.process.stdout.receive()
            line, self.buffer = self.buffer.split(b"\n", 1)
            self.stdout_lines.append(line)
            try:
                message = json.loads(line)
            except ValueError:
                continue  # reported by the final stdout assertion
            if isinstance(message, dict) and message.get("id") == request_id:
                return message

    async def call_tool(self, name, arguments):
        return (await self.request("tools/call", {"name": name, "arguments": arguments}))["result"]

    async def finish(self):
        await self.process.stdin.aclose()
        await self.process.wait()
        try:
            while True:
                self.buffer += await self.process.stdout.receive()
        except anyio.EndOfStream:
            pass
        self.stdout_lines.extend(self.buffer.split(b"\n"))


@asynccontextmanager
async def raw_server(env, stderr_path, servers):
    with open(stderr_path, "wb") as errlog:
        process = await anyio.open_process(SERVER, env=env, stderr=errlog)
        async with process:
            server = RawServer(process)
            servers.append(server)
            init = await server.request(
                "initialize",
                {
                    "protocolVersion": LATEST_HANDSHAKE_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "stdout-test", "version": "0"},
                },
            )
            assert "result" in init
            await server.notify("notifications/initialized")
            yield server
            await server.finish()


async def test_ac29_stdout_is_only_jsonrpc_over_the_full_flow(seeded_db, server_env, tmp_path):
    servers: list[RawServer] = []
    stderr = {staff: tmp_path / f"{staff}.stderr.txt" for staff in ("stf_bridge_cw", "stf_bridge_pm", "stf_bridge_fin")}

    with anyio.fail_after(60):
        async with raw_server(server_env("stf_bridge_cw", seeded_db), stderr["stf_bridge_cw"], servers) as cw:
            tools = (await cw.request("tools/list"))["result"]["tools"]
            assert len(tools) == 10
            created = await cw.call_tool(
                "create_request", {"participant_id": "par_bridge_001", "fund_id": F, "purpose": "RENT", "amount": "300.00"}
            )
            assert created["isError"] is False
            request_id = created["structuredContent"]["id"]

        async with raw_server(server_env("stf_bridge_pm", seeded_db), stderr["stf_bridge_pm"], servers) as pm:
            assert (await pm.call_tool("approve_request", {"request_id": request_id}))["isError"] is False
            # The error call: approving again is an INVALID_TRANSITION tool error.
            again = await pm.call_tool("approve_request", {"request_id": request_id})
            assert again["isError"] is True
            assert json.loads(again["content"][0]["text"])["error"]["code"] == "INVALID_TRANSITION"

        async with raw_server(server_env("stf_bridge_fin", seeded_db), stderr["stf_bridge_fin"], servers) as fin:
            assert (await fin.call_tool("record_payment", {"request_id": request_id}))["isError"] is False
            summary = await fin.call_tool("get_funding_summary", {"fund_id": F})
            funds = summary["structuredContent"]["funds"][0]
            assert (funds["committed"], funds["paid"], funds["available"]) == ("0.00", "300.00", "9700.00")

    lines = [line for server in servers for line in server.stdout_lines if line.strip()]
    assert lines
    for line in lines:
        message = json.loads(line)
        assert isinstance(message, dict)
        assert message["jsonrpc"] == "2.0"
        assert "id" in message or "method" in message

    # Logger name is "__main__" under `python -m cb.server`, so match level and message only.
    def logged(staff, level, message):
        return any(f" {level} " in line and message in line for line in stderr[staff].read_text().splitlines())

    for staff in stderr:
        assert logged(staff, "INFO", f"cb-server serving MCP over stdio as {staff}")
    assert logged("stf_bridge_pm", "WARNING", "tool approve_request refused: INVALID_TRANSITION")
