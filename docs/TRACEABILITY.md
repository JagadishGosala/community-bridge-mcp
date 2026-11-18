# Requirement Traceability

REQ ids and ACs are defined in [SPEC.md](SPEC.md). Planned files follow the layout in [TASKS.md](TASKS.md). The Result column is filled in from actual test runs in T13.

| REQ | Summary | Planned implementation file | ACs / tests | Result |
|---|---|---|---|---|
| REQ-01 | Caller identity only from `CB_STAFF_ID`, resolved server-side | `cb/identity.py`, `cb/config.py` | AC-31, AC-38 · `tests/e2e/test_skeleton.py`, `tests/e2e/test_flow.py` | |
| REQ-02 | Refuse startup on missing/empty/unknown identity | `cb/server.py` (main), `cb/identity.py` | AC-21, AC-22 · `tests/e2e/test_startup.py` | |
| REQ-03 | Re-resolve identity per call; `UNAUTHENTICATED` | `cb/server.py` (pipeline), `cb/identity.py` | AC-23 · `tests/service/test_identity.py` | |
| REQ-04 | Role × tool matrix; `FORBIDDEN_ROLE` | `cb/permissions.py`, `cb/server.py` | AC-13, AC-14, AC-15, AC-16 · `tests/unit/test_permissions.py`, `tests/service/test_decide.py`, `tests/service/test_payment.py`, `tests/service/test_create.py` | |
| REQ-05 | Nonprofit scoping; cross-nonprofit → `NOT_FOUND` | `cb/service.py` | AC-17, AC-18, AC-19, AC-35 · `tests/service/test_isolation.py`, `tests/service/test_reads.py` | |
| REQ-06 | DB-level composite FKs prevent cross-nonprofit links | `cb/db.py` (DDL) | AC-19, AC-20 · `tests/unit/test_schema.py` | |
| REQ-07 | No identity in inputs; unknown fields → `VALIDATION_ERROR` | `cb/models.py`, `cb/server.py` | AC-27 · `tests/unit/test_models.py`, `tests/e2e/test_flow.py` | |
| REQ-08 | Stored/submitted text never grants permissions | `cb/service.py`, `cb/permissions.py` | AC-28 · `tests/service/test_create.py` | |
| REQ-09 | Case worker creates `PENDING` request | `cb/service.py` | AC-01 · `tests/service/test_create.py` | |
| REQ-10 | Only the three allowed transitions; else `INVALID_TRANSITION` | `cb/service.py` | AC-02, AC-08, AC-09, AC-10, AC-11 · `tests/service/test_decide.py`, `tests/service/test_payment.py` | |
| REQ-11 | Rejection reason 1–500 chars, stored | `cb/models.py`, `cb/service.py` | AC-04, AC-05 · `tests/service/test_decide.py` | |
| REQ-12 | No edit/delete operation for requests | `cb/server.py` (tool set) | AC-40 · `tests/e2e/test_discovery.py` | |
| REQ-13 | Who/when recorded on decision and payment | `cb/service.py`, `cb/db.py` | AC-02, AC-03, AC-04 · `tests/service/test_decide.py`, `tests/service/test_payment.py` | |
| REQ-14 | Purpose enum; OTHER requires description | `cb/models.py`, `cb/db.py` (CHECK) | AC-26 · `tests/unit/test_models.py`, `tests/service/test_create.py` | |
| REQ-15 | Amount string regex + range, Decimal → integer cents, no float | `cb/money.py`, `cb/models.py` | AC-24, AC-25 · `tests/unit/test_money.py`, `tests/service/test_create.py` | |
| REQ-16 | committed / paid / available formula | `cb/service.py` | AC-01, AC-02, AC-03 · `tests/service/test_reads.py`, `tests/service/test_payment.py` | |
| REQ-17 | Create and reject do not change balances | `cb/service.py` | AC-01, AC-04 · `tests/service/test_create.py`, `tests/service/test_decide.py` | |
| REQ-18 | Approve only if amount ≤ available (inclusive) | `cb/service.py` (conditional UPDATE) | AC-06, AC-07 · `tests/service/test_decide.py` | |
| REQ-19 | Atomic approval; concurrent approvals cannot overspend | `cb/service.py`, `cb/db.py` (BEGIN IMMEDIATE) | AC-30 · `tests/e2e/test_concurrency.py` | |
| REQ-20 | One full payment per approved request | `cb/service.py`, `cb/db.py` (UNIQUE) | AC-03, AC-10, AC-11, AC-12 · `tests/service/test_payment.py`, `tests/unit/test_schema.py` | |
| REQ-21 | Errors leave business state unchanged | `cb/service.py`, `cb/db.py` (tx helper) | AC-05, AC-06, AC-08–AC-11, AC-13–AC-15, AC-18, AC-19, AC-23, AC-24, AC-26, AC-27 · `tests/service/*` | |
| REQ-22 | `whoami` | `cb/service.py`, `cb/server.py` | AC-16, AC-38 · `tests/e2e/test_skeleton.py` | |
| REQ-23 | `list_participants`, `list_funds` | `cb/service.py` | AC-16, AC-17 · `tests/service/test_reads.py` | |
| REQ-24 | `get_request`, `list_requests` with filters | `cb/service.py` | AC-16, AC-39 · `tests/service/test_reads.py` | |
| REQ-25 | `get_funding_summary` | `cb/service.py` | AC-01–AC-03, AC-16 · `tests/service/test_reads.py` | |
| REQ-26 | 10 tools over stdio with input/output schemas; no resources/prompts | `cb/server.py`, `cb/models.py` | AC-31, AC-40 · `tests/e2e/test_discovery.py`, `tests/e2e/test_flow.py` | |
| REQ-27 | Error envelope; unexpected → `INTERNAL_ERROR` without internals | `cb/errors.py`, `cb/server.py` | AC-36 · `tests/service/test_errors.py` | |
| REQ-28 | Check order: validation → identity → role → ownership → rules → write | `cb/server.py` (pipeline), `cb/service.py` | AC-37 · `tests/service/test_errors.py` | |
| REQ-29 | Logs to stderr only; stdout is MCP only | `cb/log.py`, `cb/server.py` | AC-29 · `tests/e2e/test_stdout.py` | |
| REQ-30 | Persistent local SQLite | `cb/db.py` | AC-34 · `tests/e2e/test_flow.py` | |
| REQ-31 | `cb-reset` separate; startup never seeds; missing DB → exit with instruction | `cb/reset.py`, `cb/seed.py`, `cb/db.py` | AC-32, AC-33 · `tests/e2e/test_startup.py`, `tests/unit/test_schema.py` | |
| REQ-32 | Pinned Python and dependencies | `.python-version`, `pyproject.toml`, `uv.lock` | AC-41 · manual `uv sync --locked` | |
| REQ-33 | Reproducible MCP client demo | `scripts/demo.py` | AC-31 · `tests/e2e/test_flow.py`, manual demo run | |
