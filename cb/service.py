"""Business logic: one function per tool, (conn, caller, validated input) -> output model.

Every statement is parameterized and scoped to caller.nonprofit_id (REQ-05).
Balances are derived from request states, never stored (§6.2).
"""

import sqlite3
import uuid
from datetime import UTC, datetime

from cb import db, errors, models
from cb.identity import Caller
from cb.money import format_cents

_EXISTS = {
    "participant": "SELECT 1 FROM participants WHERE id = ? AND nonprofit_id = ?",
    "fund": "SELECT 1 FROM funds WHERE id = ? AND nonprofit_id = ?",
}

_SELECT_REQUESTS = """
SELECT r.id, r.participant_id, r.fund_id, r.purpose, r.description, r.amount_cents, r.status,
       r.created_by, r.created_at, r.decided_by, r.decided_at, r.rejection_reason,
       p.id, p.amount_cents, p.recorded_by, p.recorded_at
FROM requests r
LEFT JOIN payments p ON p.request_id = r.id AND p.nonprofit_id = r.nonprofit_id
WHERE r.nonprofit_id = :nonprofit_id
"""

_SELECT_SUMMARIES = """
SELECT f.id, f.name, f.allocation_cents,
       COALESCE(SUM(CASE WHEN r.status = 'APPROVED' THEN r.amount_cents END), 0),
       COALESCE(SUM(CASE WHEN r.status = 'PAID' THEN r.amount_cents END), 0)
FROM funds f
LEFT JOIN requests r ON r.fund_id = f.id AND r.nonprofit_id = :nonprofit_id
WHERE f.nonprofit_id = :nonprofit_id AND (:fund_id IS NULL OR f.id = :fund_id)
GROUP BY f.id
ORDER BY f.id
"""


def _now() -> str:
    """UTC ISO-8601 with a Z suffix (A-09)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _require(conn: sqlite3.Connection, caller: Caller, entity: str, entity_id: str) -> None:
    if conn.execute(_EXISTS[entity], (entity_id, caller.nonprofit_id)).fetchone() is None:
        raise errors.not_found(entity, entity_id)


def _request_from_row(row: tuple) -> models.Request:
    (rid, participant_id, fund_id, purpose, description, amount_cents, status,
     created_by, created_at, decided_by, decided_at, rejection_reason,
     pay_id, pay_cents, recorded_by, recorded_at) = row
    payment = None
    if pay_id is not None:
        payment = models.Payment(
            id=pay_id, amount=format_cents(pay_cents), recorded_by=recorded_by, recorded_at=recorded_at
        )
    return models.Request(
        id=rid,
        participant_id=participant_id,
        fund_id=fund_id,
        purpose=purpose,
        description=description,
        amount=format_cents(amount_cents),
        status=status,
        created_by=created_by,
        created_at=created_at,
        decided_by=decided_by,
        decided_at=decided_at,
        rejection_reason=rejection_reason,
        payment=payment,
    )


def _fetch_request(conn: sqlite3.Connection, caller: Caller, request_id: str) -> models.Request:
    row = conn.execute(
        _SELECT_REQUESTS + " AND r.id = :request_id",
        {"nonprofit_id": caller.nonprofit_id, "request_id": request_id},
    ).fetchone()
    if row is None:
        raise errors.not_found("request", request_id)
    return _request_from_row(row)


# --- reads ---------------------------------------------------------------------------


def whoami(conn: sqlite3.Connection, caller: Caller, args: models.WhoamiInput) -> models.WhoamiOutput:
    return models.WhoamiOutput(
        staff_id=caller.staff_id,
        staff_name=caller.staff_name,
        role=caller.role,
        nonprofit_id=caller.nonprofit_id,
        nonprofit_name=caller.nonprofit_name,
    )


def list_participants(
    conn: sqlite3.Connection, caller: Caller, args: models.ListParticipantsInput
) -> models.ParticipantsOutput:
    rows = conn.execute(
        "SELECT id, display_name FROM participants WHERE nonprofit_id = ? ORDER BY id", (caller.nonprofit_id,)
    )
    return models.ParticipantsOutput(
        participants=[models.Participant(id=pid, display_name=name) for pid, name in rows]
    )


def list_funds(conn: sqlite3.Connection, caller: Caller, args: models.ListFundsInput) -> models.FundsOutput:
    rows = conn.execute(
        "SELECT id, name, allocation_cents FROM funds WHERE nonprofit_id = ? ORDER BY id", (caller.nonprofit_id,)
    )
    return models.FundsOutput(
        funds=[models.Fund(id=fid, name=name, allocation=format_cents(cents)) for fid, name, cents in rows]
    )


def get_funding_summary(
    conn: sqlite3.Connection, caller: Caller, args: models.GetFundingSummaryInput
) -> models.FundingSummaryOutput:
    rows = conn.execute(
        _SELECT_SUMMARIES, {"nonprofit_id": caller.nonprofit_id, "fund_id": args.fund_id}
    ).fetchall()
    if args.fund_id is not None and not rows:
        raise errors.not_found("fund", args.fund_id)
    return models.FundingSummaryOutput(
        funds=[
            models.FundSummary(
                fund_id=fid,
                fund_name=name,
                allocation=format_cents(allocation),
                committed=format_cents(committed),
                paid=format_cents(paid),
                available=format_cents(allocation - committed - paid),
            )
            for fid, name, allocation, committed, paid in rows
        ]
    )


def get_request(conn: sqlite3.Connection, caller: Caller, args: models.GetRequestInput) -> models.Request:
    return _fetch_request(conn, caller, args.request_id)


def list_requests(
    conn: sqlite3.Connection, caller: Caller, args: models.ListRequestsInput
) -> models.RequestsOutput:
    if args.fund_id is not None:
        _require(conn, caller, "fund", args.fund_id)
    rows = conn.execute(
        _SELECT_REQUESTS
        + " AND (:status IS NULL OR r.status = :status)"
        + " AND (:fund_id IS NULL OR r.fund_id = :fund_id)"
        + " ORDER BY r.created_at, r.id",
        {"nonprofit_id": caller.nonprofit_id, "status": args.status, "fund_id": args.fund_id},
    )
    return models.RequestsOutput(requests=[_request_from_row(row) for row in rows])


# --- writes --------------------------------------------------------------------------


def create_request(
    conn: sqlite3.Connection, caller: Caller, args: models.CreateRequestInput
) -> models.Request:
    """Insert a PENDING request (REQ-09). No availability check (A-04); balances unchanged (REQ-17)."""
    request_id = "req_" + uuid.uuid4().hex
    with db.transaction(conn):
        _require(conn, caller, "participant", args.participant_id)
        _require(conn, caller, "fund", args.fund_id)
        conn.execute(
            "INSERT INTO requests (id, nonprofit_id, participant_id, fund_id, purpose, description,"
            " amount_cents, status, created_by, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)",
            (
                request_id,
                caller.nonprofit_id,
                args.participant_id,
                args.fund_id,
                args.purpose,
                args.description,
                args.amount_cents,
                caller.staff_id,
                _now(),
            ),
        )
        return _fetch_request(conn, caller, request_id)
