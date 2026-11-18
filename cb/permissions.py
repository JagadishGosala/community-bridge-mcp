"""Role × tool matrix (SPEC §9). Checked in pipeline step 3, before any record lookup."""

ALL_ROLES = ("CASE_WORKER", "PROGRAM_MANAGER", "FINANCE")

ALLOWED_ROLES: dict[str, tuple[str, ...]] = {
    "whoami": ALL_ROLES,
    "list_participants": ALL_ROLES,
    "list_funds": ALL_ROLES,
    "get_funding_summary": ALL_ROLES,
    "get_request": ALL_ROLES,
    "list_requests": ALL_ROLES,
    "create_request": ("CASE_WORKER",),
    "approve_request": ("PROGRAM_MANAGER",),
    "reject_request": ("PROGRAM_MANAGER",),
    "record_payment": ("FINANCE",),
}


def is_allowed(role: str, tool: str) -> bool:
    return role in ALLOWED_ROLES.get(tool, ())
