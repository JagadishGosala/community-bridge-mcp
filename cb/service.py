"""Business logic: one function per tool, (conn, caller, validated input) -> output model.

Every statement is parameterized and scoped to caller.nonprofit_id (REQ-05).
Balances are derived from request states, never stored (§6.2).
"""

import sqlite3
import time
import uuid
from datetime import UTC, datetime

from cb import config, db, errors, models
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

# SPEC §7, verbatim: status, ownership and availability re-checked in one statement (REQ-19).
_APPROVE = """
UPDATE requests
SET status = 'APPROVED', decided_by = :staff_id, decided_at = :now
WHERE id = :request_id
  AND nonprofit_id = :nonprofit_id
  AND status = 'PENDING'
  AND amount_cents <= (
    SELECT f.allocation_cents - COALESCE((
      SELECT SUM(r2.amount_cents) FROM requests r2
      WHERE r2.fund_id = f.id AND r2.nonprofit_id = f.nonprofit_id
        AND r2.status IN ('APPROVED', 'PAID')), 0)
    FROM funds f
    WHERE f.id = requests.fund_id AND f.nonprofit_id = requests.nonprofit_id)
"""

_REJECT = """
UPDATE requests
SET status = 'REJECTED', rejection_reason = :reason, decided_by = :staff_id, decided_at = :now
WHERE id = :request_id AND nonprofit_id = :nonprofit_id AND status = 'PENDING'
"""

_PAY = """
UPDATE requests
SET status = 'PAID'
WHERE id = :request_id AND nonprofit_id = :nonprofit_id AND status = 'APPROVED'
"""

_INSERT_PAYMENT = """
INSERT INTO payments (id, request_id, nonprofit_id, amount_cents, recorded_by, recorded_at)
SELECT :payment_id, id, nonprofit_id, amount_cents, :staff_id, :now
FROM requests WHERE id = :request_id AND nonprofit_id = :nonprofit_id
"""

# The only status each action may start from (§6.1).
_FROM_STATUS = {"APPROVE": "PENDING", "REJECT": "PENDING", "PAY": "APPROVED"}


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


def _invalid_transition(request_id: str, current_status: str, attempted: str) -> errors.AppError:
    return errors.AppError(
        errors.INVALID_TRANSITION,
        f"Cannot {attempted.lower()} a request whose status is {current_status}.",
        {"request_id": request_id, "current_status": current_status, "attempted": attempted},
    )


def _diagnose(conn: sqlite3.Connection, caller: Caller, request_id: str, attempted: str) -> tuple[str, int]:
    """Explain a conditional UPDATE that matched no row, inside the same transaction (§7).

    Raises NOT_FOUND or INVALID_TRANSITION; otherwise returns (fund_id, amount_cents).
    """
    row = conn.execute(
        "SELECT status, fund_id, amount_cents FROM requests WHERE id = ? AND nonprofit_id = ?",
        (request_id, caller.nonprofit_id),
    ).fetchone()
    if row is None:
        raise errors.not_found("request", request_id)
    status, fund_id, amount_cents = row
    if status != _FROM_STATUS[attempted]:
        raise _invalid_transition(request_id, status, attempted)
    return fund_id, amount_cents


def _available_cents(conn: sqlite3.Connection, caller: Caller, fund_id: str) -> int:
    """allocation − committed − paid (§6.2)."""
    _, _, allocation, committed, paid = conn.execute(
        _SELECT_SUMMARIES, {"nonprofit_id": caller.nonprofit_id, "fund_id": fund_id}
    ).fetchone()
    return allocation - committed - paid


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


def approve_request(
    conn: sqlite3.Connection, caller: Caller, args: models.ApproveRequestInput
) -> models.Request:
    """PENDING → APPROVED if amount ≤ available at commit time (REQ-18, REQ-19)."""
    params = {
        "request_id": args.request_id,
        "nonprofit_id": caller.nonprofit_id,
        "staff_id": caller.staff_id,
        "now": _now(),
    }
    with db.transaction(conn):
        approved = conn.execute(_APPROVE, params).rowcount == 1
        delay_ms = config.tx_delay_ms()
        if delay_ms:
            time.sleep(delay_ms / 1000)  # test-only: holds the write lock to force overlap (§10)
        if not approved:
            fund_id, amount_cents = _diagnose(conn, caller, args.request_id, "APPROVE")
            raise errors.AppError(
                errors.INSUFFICIENT_FUNDS,
                "The fund's available amount is less than the request amount.",
                {
                    "request_id": args.request_id,
                    "fund_id": fund_id,
                    "requested": format_cents(amount_cents),
                    "available": format_cents(_available_cents(conn, caller, fund_id)),
                },
            )
        return _fetch_request(conn, caller, args.request_id)


def reject_request(
    conn: sqlite3.Connection, caller: Caller, args: models.RejectRequestInput
) -> models.Request:
    """PENDING → REJECTED with a reason (REQ-11); funding unchanged (REQ-17)."""
    params = {
        "request_id": args.request_id,
        "nonprofit_id": caller.nonprofit_id,
        "staff_id": caller.staff_id,
        "reason": args.reason,
        "now": _now(),
    }
    with db.transaction(conn):
        if conn.execute(_REJECT, params).rowcount == 0:
            _diagnose(conn, caller, args.request_id, "REJECT")
            # Unreachable while _REJECT and _FROM_STATUS agree; never report success without a write.
            raise RuntimeError(f"reject_request matched no row for a PENDING request {args.request_id}")
        return _fetch_request(conn, caller, args.request_id)


def record_payment(
    conn: sqlite3.Connection, caller: Caller, args: models.RecordPaymentInput
) -> models.Request:
    """APPROVED → PAID with one payment for the full amount (REQ-20)."""
    params = {
        "request_id": args.request_id,
        "nonprofit_id": caller.nonprofit_id,
        "staff_id": caller.staff_id,
        "payment_id": "pay_" + uuid.uuid4().hex,
        "now": _now(),
    }
    with db.transaction(conn):
        if conn.execute(_PAY, params).rowcount == 0:
            _diagnose(conn, caller, args.request_id, "PAY")
            raise RuntimeError(f"record_payment matched no row for an APPROVED request {args.request_id}")
        try:
            conn.execute(_INSERT_PAYMENT, params)
        except sqlite3.IntegrityError as exc:
            if "payments.request_id" not in str(exc):
                raise
            # UNIQUE(payments.request_id) backstop: a payment already exists, so the request is paid.
            raise _invalid_transition(args.request_id, "PAID", "PAY") from exc
        return _fetch_request(conn, caller, args.request_id)
