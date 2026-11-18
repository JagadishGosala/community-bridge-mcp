"""cb-server: MCP server over stdio (SPEC §8).

Built on the SDK's low-level Server rather than MCPServer (FastMCP's name in
mcp 2.x). The T3 spike showed MCPServer ignores unknown arguments and prefixes
every validation or tool error with "Error executing tool ...". The low-level
Server passes raw arguments to one call handler, so this module owns input
validation, the check order (§6.3) and the error body (§6.5).
"""

import logging
import sqlite3
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.shared.exceptions import MCPError
from mcp_types.jsonrpc import INVALID_PARAMS
from pydantic import BaseModel, ValidationError

from cb import config, db, errors, identity, log, models, permissions, service
from cb.identity import Caller

logger = logging.getLogger(__name__)


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
            input_model=models.WhoamiInput,
            output_model=models.WhoamiOutput,
            handler=service.whoami,
            read_only=True,
        ),
        ToolSpec(
            name="list_participants",
            description="List participants of your nonprofit. Read-only.",
            input_model=models.ListParticipantsInput,
            output_model=models.ParticipantsOutput,
            handler=service.list_participants,
            read_only=True,
        ),
        ToolSpec(
            name="list_funds",
            description="List funds of your nonprofit with their fixed allocation in USD. Read-only.",
            input_model=models.ListFundsInput,
            output_model=models.FundsOutput,
            handler=service.list_funds,
            read_only=True,
        ),
        ToolSpec(
            name="get_funding_summary",
            description=(
                "Show allocation, committed, paid and available USD amounts for one fund, "
                "or for all funds of your nonprofit if fund_id is omitted. Read-only."
            ),
            input_model=models.GetFundingSummaryInput,
            output_model=models.FundingSummaryOutput,
            handler=service.get_funding_summary,
            read_only=True,
        ),
        ToolSpec(
            name="create_request",
            description=(
                "Create a PENDING assistance request for a participant against a fund. "
                'amount is a USD decimal string such as "300.00". '
                "Purpose OTHER requires a description. Does not reserve money. Requires CASE_WORKER."
            ),
            input_model=models.CreateRequestInput,
            output_model=models.Request,
            handler=service.create_request,
            read_only=False,
        ),
        ToolSpec(
            name="get_request",
            description="Get one request of your nonprofit by id, including payment details if paid. Read-only.",
            input_model=models.GetRequestInput,
            output_model=models.Request,
            handler=service.get_request,
            read_only=True,
        ),
        ToolSpec(
            name="list_requests",
            description="List requests of your nonprofit, optionally filtered by status and/or fund_id. Read-only.",
            input_model=models.ListRequestsInput,
            output_model=models.RequestsOutput,
            handler=service.list_requests,
            read_only=True,
        ),
    ]
}


def run_tool(spec: ToolSpec, staff_id: str, arguments: dict[str, Any]) -> types.CallToolResult:
    """Run one tool call through the §6.3 check order. Blocking; one connection per call.

    validation -> identity -> role -> service (ownership, business rules, write).
    """
    try:
        try:
            args = spec.input_model.model_validate(arguments)
        except ValidationError as exc:
            return errors.validation_error_result(exc)

        conn = db.connect()
        try:
            caller = identity.resolve(conn, staff_id)  # REQ-03: every call
            if caller is None:
                logger.warning("CB_STAFF_ID=%r no longer resolves; tool %s refused", staff_id, spec.name)
                return errors.error_result(
                    errors.UNAUTHENTICATED, "The configured staff identity no longer exists.", {}
                )
            if not permissions.is_allowed(caller.role, spec.name):
                raise errors.forbidden_role(caller.role, spec.name, list(permissions.ALLOWED_ROLES[spec.name]))
            output = spec.handler(conn, caller, args)
        finally:
            conn.close()
        return errors.success_result(output.model_dump(mode="json"))
    except errors.AppError as exc:
        logger.warning("tool %s refused: %s %s", spec.name, exc.code, exc.details)
        return errors.error_result(exc.code, exc.message, exc.details)
    except Exception as exc:
        error_id = uuid.uuid4().hex
        logger.exception("tool %s raised an unexpected exception; error_id=%s", spec.name, error_id)
        retryable = isinstance(exc, sqlite3.OperationalError) and exc.sqlite_errorname == "SQLITE_BUSY"
        return errors.error_result(
            errors.INTERNAL_ERROR, "Internal error.", {"error_id": error_id, "retryable": retryable}
        )


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
