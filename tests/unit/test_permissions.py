"""Role × tool matrix (SPEC §9, REQ-04)."""

import pytest

from cb import permissions

READ_TOOLS = {"whoami", "list_participants", "list_funds", "get_funding_summary", "get_request", "list_requests"}
ALL_TOOLS = READ_TOOLS | {"create_request", "approve_request", "reject_request", "record_payment"}

EXPECTED = {
    "CASE_WORKER": READ_TOOLS | {"create_request"},
    "PROGRAM_MANAGER": READ_TOOLS | {"approve_request", "reject_request"},
    "FINANCE": READ_TOOLS | {"record_payment"},
}


@pytest.mark.parametrize("tool", sorted(ALL_TOOLS))
@pytest.mark.parametrize("role", sorted(EXPECTED))
def test_matrix(role, tool):
    assert permissions.is_allowed(role, tool) is (tool in EXPECTED[role])


def test_matrix_covers_exactly_the_ten_tools():
    assert set(permissions.ALLOWED_ROLES) == ALL_TOOLS


@pytest.mark.parametrize("tool", sorted(ALL_TOOLS))
def test_allowed_roles_per_tool(tool):
    assert set(permissions.ALLOWED_ROLES[tool]) == {role for role, tools in EXPECTED.items() if tool in tools}


def test_unknown_role_is_not_allowed():
    assert permissions.is_allowed("ADMIN", "whoami") is False
