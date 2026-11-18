"""Error codes, AppError and tool result builders (SPEC §6.5, A-16)."""

import json
from typing import Any

import mcp_types as types
from pydantic import ValidationError

VALIDATION_ERROR = "VALIDATION_ERROR"
UNAUTHENTICATED = "UNAUTHENTICATED"
FORBIDDEN_ROLE = "FORBIDDEN_ROLE"
NOT_FOUND = "NOT_FOUND"
INVALID_TRANSITION = "INVALID_TRANSITION"
INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
INTERNAL_ERROR = "INTERNAL_ERROR"


class AppError(Exception):
    """An expected failure that becomes a §6.5 error result."""

    def __init__(self, code: str, message: str, details: dict[str, Any]):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


def not_found(entity: str, entity_id: str) -> AppError:
    # Same text for a missing record and another nonprofit's record (REQ-05).
    return AppError(NOT_FOUND, f"No {entity} with id {entity_id}.", {"entity": entity, "id": entity_id})


def forbidden_role(role: str, tool: str, allowed_roles: list[str]) -> AppError:
    return AppError(
        FORBIDDEN_ROLE,
        f"Role {role} may not call {tool}.",
        {"role": role, "tool": tool, "allowed_roles": allowed_roles},
    )


def success_result(body: dict[str, Any]) -> types.CallToolResult:
    # A-16: structuredContent plus the same JSON as text.
    content = [types.TextContent(type="text", text=json.dumps(body))]
    return types.CallToolResult(content=content, structured_content=body)


def error_result(code: str, message: str, details: dict[str, Any]) -> types.CallToolResult:
    # A-16: error JSON as text only.
    body = {"error": {"code": code, "message": message, "details": details}}
    return types.CallToolResult(content=[types.TextContent(type="text", text=json.dumps(body))], is_error=True)


def validation_error_result(exc: ValidationError) -> types.CallToolResult:
    fields = [{"field": ".".join(str(p) for p in e["loc"]), "issue": e["msg"]} for e in exc.errors()]
    return error_result(VALIDATION_ERROR, "Invalid tool input.", {"fields": fields})
