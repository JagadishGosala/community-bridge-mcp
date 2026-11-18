"""cb-server: MCP server over stdio (SPEC §8).

Built on the SDK's low-level Server rather than MCPServer (FastMCP's name in
mcp 2.x). The T3 spike showed MCPServer ignores unknown arguments and prefixes
every validation or tool error with "Error executing tool ...". The low-level
Server passes raw arguments to one call handler, so this module owns input
validation, the check order (§6.3) and the error body (§6.5).
"""

import json
import logging
import sqlite3
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp_types.jsonrpc import INVALID_PARAMS
from pydantic import BaseModel, ConfigDict, ValidationError

from cb import config, db, identity, log
from cb.identity import Caller

logger = logging.getLogger(__name__)


class WhoamiInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class WhoamiOutput(BaseModel):
    staff_id: str
    staff_name: str
    role: Literal["CASE_WORKER", "PROGRAM_MANAGER", "FINANCE"]
    nonprofit_id: str
    nonprofit_name: str


def whoami(conn: sqlite3.Connection, caller: Caller, args: WhoamiInput) -> WhoamiOutput:
    return WhoamiOutput(
        staff_id=caller.staff_id,
        staff_name=caller.staff_name,
        role=caller.role,
        nonprofit_id=caller.nonprofit_id,
        nonprofit_name=caller.nonprofit_name,
    )


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: Callable[[sqlite3.Connection, Caller, Any], BaseModel]
    read_only: bool

    def to_mcp(self) -> types.Tool:
        return types.Tool(
            name=self.name,
            description=self.description,
            input_schema=self.input_model.model_json_schema(),
            output_schema=self.output_model.model_json_schema(),
            annotations=types.ToolAnnotations(read_only_hint=True) if self.read_only else None,
        )


TOOLS = {
    spec.name: spec
    for spec in [
        ToolSpec(
            name="whoami",
            description="Return the staff member this server acts as, with their role and nonprofit. Read-only.",
            input_model=WhoamiInput,
            output_model=WhoamiOutput,
            handler=whoami,
            read_only=True,
        ),
    ]
}


def _text_result(body: dict[str, Any], *, is_error: bool) -> types.CallToolResult:
    # A-16: success carries structuredContent plus the same JSON as text;
    # errors carry the error JSON as text only.
    content = [types.TextContent(type="text", text=json.dumps(body))]
    if is_error:
        return types.CallToolResult(content=content, is_error=True)
    return types.CallToolResult(content=content, structured_content=body)


def _error(code: str, message: str, details: dict[str, Any]) -> types.CallToolResult:
    return _text_result({"error": {"code": code, "message": message, "details": details}}, is_error=True)


def _validation_error(exc: ValidationError) -> types.CallToolResult:
    fields = [{"field": ".".join(str(p) for p in e["loc"]), "issue": e["msg"]} for e in exc.errors()]
    return _error("VALIDATION_ERROR", "Invalid tool input.", {"fields": fields})


def run_tool(spec: ToolSpec, staff_id: str, arguments: dict[str, Any]) -> types.CallToolResult:
    """Run one tool call through the §6.3 check order. Blocking; one connection per call."""
    try:
        try:
            args = spec.input_model.model_validate(arguments)
        except ValidationError as exc:
            return _validation_error(exc)

        conn = db.connect()
        try:
            caller = identity.resolve(conn, staff_id)  # REQ-03: every call
            if caller is None:
                logger.warning("CB_STAFF_ID=%r no longer resolves; tool %s refused", staff_id, spec.name)
                return _error("UNAUTHENTICATED", "The configured staff identity no longer exists.", {})
            output = spec.handler(conn, caller, args)
        finally:
            conn.close()
        return _text_result(output.model_dump(mode="json"), is_error=False)
    except Exception as exc:
        error_id = uuid.uuid4().hex
        logger.exception("tool %s raised an unexpected exception; error_id=%s", spec.name, error_id)
        retryable = isinstance(exc, sqlite3.OperationalError) and exc.sqlite_errorname == "SQLITE_BUSY"
        return _error("INTERNAL_ERROR", "Internal error.", {"error_id": error_id, "retryable": retryable})


def build_server(staff_id: str) -> Server:
    async def list_tools(ctx: Any, params: types.PaginatedRequestParams | None) -> types.ListToolsResult:
        return types.ListToolsResult(tools=[spec.to_mcp() for spec in TOOLS.values()])

    async def call_tool(ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
        spec = TOOLS.get(params.name)
        if spec is None:
            raise MCPError(code=INVALID_PARAMS, message=f"Unknown tool: {params.name}")
        # Sync DB work runs on a worker thread so the event loop keeps serving stdio.
        return await anyio.to_thread.run_sync(run_tool, spec, staff_id, params.arguments or {})

    return Server("community-bridge-mcp", on_list_tools=list_tools, on_call_tool=call_tool)


async def _serve(server: Server) -> None:
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> int:
    """cb-server: check identity and database, then serve MCP over stdio."""
    log.setup()
    staff_id = config.staff_id()
    if not staff_id:
        logger.error("CB_STAFF_ID is not set. Set it to a staff id, e.g. CB_STAFF_ID=stf_bridge_cw.")
        return 1

    db_path = config.db_path()
    if not db_path.is_file():
        logger.error("Database not found at %s. Create it first with: uv run cb-reset", db_path.resolve())
        return 1

    conn = db.connect(db_path)
    try:
        caller = identity.resolve(conn, staff_id)
    finally:
        conn.close()
    if caller is None:
        logger.error("unknown identity: CB_STAFF_ID=%r does not match any staff member.", staff_id)
        return 1

    logger.info(
        "cb-server serving MCP over stdio as %s (%s, %s)", caller.staff_id, caller.role, caller.nonprofit_id
    )
    anyio.run(_serve, build_server(staff_id))
    return 0


if __name__ == "__main__":
    sys.exit(main())
