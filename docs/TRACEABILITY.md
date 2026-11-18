# Requirement Traceability

REQ and AC ids are defined in [SPEC.md](SPEC.md). Results come from the final `uv run pytest -v` run: 338 passed, 0 failed, 0 skipped (57.53 s), 2026-11-18. ✅ = covering tests pass · ☑ = checked manually · ❌ = failing · ⏭ = not run.

| REQ | Summary | Implementation | ACs · tests | Result |
|---|---|---|---|---|
| REQ-01 | Caller identity only from `CB_STAFF_ID`, resolved server-side | `cb/config.py`, `cb/identity.py`, `cb/server.py` (main) | AC-38, AC-31 · `e2e/test_skeleton.py`, `e2e/test_flow.py` | ✅ |
| REQ-02 | Refuse startup on missing/empty/unknown identity | `cb/server.py` (main) | AC-21, AC-22 · `e2e/test_startup.py` | ✅ |
| REQ-03 | Re-resolve identity per call → `UNAUTHENTICATED` | `cb/server.py` (`run_tool`) | AC-23 · `service/test_errors.py` | ✅ |
| REQ-04 | Role × tool matrix → `FORBIDDEN_ROLE` | `cb/permissions.py`, `cb/server.py` | AC-13, AC-14, AC-15 · `unit/test_permissions.py`, `service/test_create.py`, `service/test_decide.py`, `service/test_payment.py` | ✅ |
| REQ-05 | Nonprofit scoping; other nonprofit → `NOT_FOUND` | `cb/service.py` | AC-17, AC-18, AC-19, AC-35 · `service/test_isolation.py`, `service/test_decide.py`, `service/test_payment.py`, `service/test_reads.py` | ✅ |
| REQ-06 | Composite FKs block cross-nonprofit links | `cb/db.py` (DDL) | AC-19, AC-20 · `unit/test_schema.py`, `service/test_create.py` | ✅ |
| REQ-07 | No identity in inputs; unknown fields → `VALIDATION_ERROR` | `cb/models.py`, `cb/server.py` | AC-27 · `unit/test_models.py`, `service/test_create.py`, `e2e/test_skeleton.py` | ✅ |
| REQ-08 | Stored/submitted text never grants permissions | `cb/service.py`, `cb/permissions.py` | AC-28 · `service/test_create.py` | ✅ |
| REQ-09 | Case worker creates `PENDING` request | `cb/service.py` (`create_request`) | AC-01 · `service/test_create.py` | ✅ |
| REQ-10 | Only the three transitions; else `INVALID_TRANSITION` | `cb/service.py` (conditional UPDATEs) | AC-02, AC-08–AC-11 · `service/test_decide.py`, `service/test_payment.py` | ✅ |
| REQ-11 | Rejection reason 1–500 chars, stored trimmed | `cb/models.py`, `cb/service.py` | AC-04, AC-05 · `service/test_decide.py`, `unit/test_models.py` | ✅ |
| REQ-12 | No edit/delete operation for requests | `cb/server.py` (tool set) | AC-40 · `e2e/test_discovery.py` | ✅ |
| REQ-13 | Who/when recorded on decision and payment | `cb/service.py`, `cb/db.py` (CHECKs) | AC-02, AC-03, AC-04 · `service/test_decide.py`, `service/test_payment.py` | ✅ |
| REQ-14 | Purpose enum; OTHER requires description | `cb/models.py`, `cb/db.py` (CHECK) | AC-26 · `unit/test_models.py`, `service/test_create.py` | ✅ |
| REQ-15 | Amount string → `Decimal` → integer cents; no float | `cb/money.py`, `cb/models.py` | AC-24, AC-25 · `unit/test_money.py`, `unit/test_models.py`, `service/test_create.py` | ✅ |
| REQ-16 | committed / paid / available formula | `cb/service.py` | AC-01–AC-03 · `service/test_reads.py`, `service/test_decide.py`, `service/test_payment.py` | ✅ |
| REQ-17 | Create and reject leave balances unchanged | `cb/service.py` | AC-01, AC-04 · `service/test_create.py`, `service/test_decide.py` | ✅ |
| REQ-18 | Approve only if amount ≤ available (inclusive) | `cb/service.py` (`approve_request`) | AC-06, AC-07 · `service/test_decide.py` | ✅ |
| REQ-19 | Atomic approval across processes | `cb/service.py` (`approve_request`), `cb/db.py` (`BEGIN IMMEDIATE`) | AC-30 · `e2e/test_concurrency.py` (two processes × 10), negative control run once | ✅ |
| REQ-20 | One full payment per approved request | `cb/service.py` (`record_payment`), `cb/db.py` (UNIQUE) | AC-03, AC-10, AC-11, AC-12 · `service/test_payment.py`, `unit/test_schema.py` | ✅ |
| REQ-21 | Errors leave business state unchanged | `cb/db.py` (transaction helper), `cb/service.py` | Snapshot assertions in AC-05, 06, 08–11, 13–15, 18, 19, 23, 24, 26, 27 · `service/*` | ✅ |
| REQ-22 | `whoami` | `cb/service.py` | AC-16, AC-38 · `e2e/test_skeleton.py`, `service/test_reads.py` | ✅ |
| REQ-23 | `list_participants`, `list_funds` | `cb/service.py` | AC-16, AC-17 · `service/test_reads.py`, `service/test_isolation.py` | ✅ |
| REQ-24 | `get_request`, `list_requests` with filters | `cb/service.py` | AC-16, AC-39 · `service/test_reads.py` | ✅ |
| REQ-25 | `get_funding_summary` | `cb/service.py` | AC-01–AC-03, AC-16 · `service/test_reads.py` | ✅ |
| REQ-26 | 10 tools over stdio with input/output schemas; no resources/prompts | `cb/server.py`, `cb/models.py` | AC-31, AC-40 · `e2e/test_discovery.py`, `e2e/test_flow.py` | ✅ |
| REQ-27 | Error envelope; unexpected → `INTERNAL_ERROR` without internals | `cb/errors.py`, `cb/server.py` | AC-36 · `service/test_errors.py`, `e2e/test_skeleton.py` | ✅ |
| REQ-28 | Check order: validation → identity → role → ownership → rules | `cb/server.py` (pipeline), `cb/service.py` | AC-37 · `service/test_errors.py`, `service/test_create.py` | ✅ |
| REQ-29 | Logs on stderr; stdout only MCP | `cb/log.py`, `cb/server.py` | AC-29 · `e2e/test_skeleton.py`, `e2e/test_stdout.py` | ✅ |
| REQ-30 | Persistent local SQLite | `cb/db.py` | AC-34 · `e2e/test_flow.py` | ✅ |
| REQ-31 | Separate `cb-reset`; startup never seeds; missing DB → instruction | `cb/reset.py`, `cb/seed.py`, `cb/server.py` | AC-32, AC-33 · `e2e/test_startup.py`, `unit/test_schema.py` | ✅ |
| REQ-32 | Pinned Python and dependencies | `.python-version`, `pyproject.toml`, `uv.lock` | AC-41 · `uv sync --locked` (manual) | ☑ |
| REQ-33 | Reproducible MCP client demo | `scripts/demo.py` | AC-31 · `e2e/test_flow.py`, demo subprocess test, manual run | ✅ |
