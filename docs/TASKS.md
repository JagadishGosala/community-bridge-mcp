# Community Bridge MCP — Phase 1 Implementation Plan

Spec: [SPEC.md](SPEC.md) · Mapping: [TRACEABILITY.md](TRACEABILITY.md) · Time box: ~3 h total (spec, build, tests).

## Planned package layout

```text
pyproject.toml          # deps + console scripts: cb-server, cb-reset
uv.lock, .python-version
cb/
  __init__.py
  config.py             # CB_DB_PATH, CB_STAFF_ID, CB_TEST_TX_DELAY_MS
  log.py                # stderr-only logging setup
  db.py                 # connect (mode=rw, pragmas, isolation_level=None), DDL, tx helper
  seed.py               # §11 seed rows
  reset.py              # cb-reset entry point
  identity.py           # resolve staff id -> Caller(staff_id, role, nonprofit_id)
  permissions.py        # role × tool matrix
  money.py              # parse_amount(str) -> int cents, format_cents(int) -> str
  models.py             # Pydantic input models (extra=forbid, strict) + output models
  errors.py             # error codes, AppError, envelope builder
  service.py            # business logic: functions(conn, caller, input) -> output | AppError
  server.py             # FastMCP app, tool registration, check-order pipeline, cb-server main
tests/
  conftest.py           # fresh seeded DB per test, caller fixtures, MCP client helper
  unit/                 # test_money.py, test_models.py, test_schema.py, test_permissions.py
  service/              # test_create.py, test_decide.py, test_payment.py, test_reads.py,
                        # test_isolation.py, test_identity.py, test_errors.py
  e2e/                  # test_skeleton.py, test_startup.py, test_discovery.py,
                        # test_flow.py, test_stdout.py, test_concurrency.py
scripts/demo.py         # MCP client demo (no LLM)
docs/                   # Brief, SPEC, TASKS, TRACEABILITY, AI_LOG_RAW, README material
```

`service.py` holds all business behavior and is tested directly (fast). `server.py` is a thin adapter, tested through a real SDK stdio client.

## Tasks

| ID | Task | Depends on | Done when | Verification gate |
|---|---|---|---|---|
| T0 | Review and commit `SPEC.md`, `TASKS.md` and `TRACEABILITY.md` before any code | — | Commit exists containing only docs | Human read-through: every brief "must" maps to a REQ and an AC |
| T1 | Scaffold: `uv init`, Python 3.12 pin, deps (`mcp`, `pydantic`, `pytest`, `pytest-asyncio` or `anyio`), console scripts, empty `cb/` and `tests/` | T0 | `uv sync --locked` and `uv run pytest` succeed (0 tests) | AC-41 |
| T2 | Schema + reset/seed, **test-first**: `db.py`, `seed.py`, `reset.py` | T1 | `uv run cb-reset` creates the §11 DB; constraint tests pass | AC-12, AC-20, AC-33 (`tests/unit/test_schema.py`) |
| T3 | **Walking skeleton:** `config.py`, `log.py`, `identity.py`, `server.py` with only `whoami` over stdio; startup failures. Spike: confirm (a) whether FastMCP rejects or ignores unknown fields; (b) whether a raised exception's text gets a prefix such as "Error executing tool …" (if so, return a `CallToolResult(isError=True)` directly so the error body is pure JSON per REQ-27); (c) that tools use flat parameters (a single Pydantic model parameter would nest the input schema and break §8); (d) whether sync tools run on worker threads (open a connection per call either way) | T2 | An SDK stdio client test launches `cb-server` as each seed identity and gets the correct `whoami`; bad startups exit non-zero | AC-21, AC-22, AC-32, AC-38; partial AC-29 (`tests/e2e/test_skeleton.py`, `test_startup.py`) |
| T4 | Money + input models, **test-first**: `money.py`, `models.py` | T1 | All invalid/valid amount, purpose, description, reason and extra-field cases pass at unit level | AC-24, AC-25, AC-26, AC-27 (unit) |
| T5 | Errors + permissions + check-order pipeline, **test-first**: `errors.py`, `permissions.py`, pipeline in `server.py` | T3, T4 | Pipeline runs validation → identity → role → service; exceptions → `INTERNAL_ERROR` with `error_id` | AC-23, AC-36, AC-37 (`tests/service/test_identity.py`, `test_errors.py`, `tests/unit/test_permissions.py`) |
| T6 | Read tools, **test-first**: `list_participants`, `list_funds`, `get_request`, `list_requests`, `get_funding_summary` in `service.py` | T2, T5 | Reads return only caller-nonprofit data; balances follow §6.2 | AC-16, AC-17, AC-35, AC-39 (`tests/service/test_reads.py`, `test_isolation.py`) |
| T7 | `create_request`, **test-first** | T6 | Creates `PENDING`; no balance change; cross-nonprofit refs → `NOT_FOUND` | AC-01, AC-19, AC-24–AC-28, create parts of AC-14/15 (`tests/service/test_create.py`) |
| T8 | `approve_request` / `reject_request`, **test-first**, using the §7 conditional UPDATE inside `BEGIN IMMEDIATE` | T7 | All transition, funding and role cases pass; failures leave state unchanged | AC-02, AC-04–AC-09, AC-13, AC-15, AC-18 (`tests/service/test_decide.py`) |
| T9 | `record_payment`, **test-first** | T8 | One payment per request; retry and PENDING/REJECTED → `INVALID_TRANSITION` | AC-03, AC-10, AC-11, AC-14 (`tests/service/test_payment.py`) |
| T10 | Register all 10 tools in `server.py` with descriptions, schemas and `readOnlyHint` | T9 | `list_tools` matches §8; no resources/prompts | AC-40 (`tests/e2e/test_discovery.py`) |
| T11 | Concurrency test: two `cb-server` processes, `CB_TEST_TX_DELAY_MS`, 10 iterations; run the negative control once and record the result | T10 | Exactly one approval wins in every iteration; negative control fails as expected | AC-30 (`tests/e2e/test_concurrency.py`) |
| T12 | End-to-end flow test + `scripts/demo.py` (identity switched per step by relaunching the server); stdout cleanliness; restart persistence | T10 | `uv run python scripts/demo.py` exits 0 and prints the final summary | AC-29, AC-31, AC-34 (`tests/e2e/test_flow.py`, `test_stdout.py`) |
| T13 | Docs: README (setup, reset, run, test, client config), fill TRACEABILITY Result column from the actual `uv run pytest -v` output (including failures and unrun checks), AI workflow examples, time spent, limitations, next priorities, SPEC revisions | T11, T12 | Every REQ row has a result; known gaps listed | Full suite run recorded verbatim; reviewer can reproduce from README alone |

Tasks T4 and T2–T3 can run in parallel. Everything else is sequential.

### Execution batches

To fit the time box, tasks are delegated in six risk-based batches instead of one prompt per task. Low-risk, mechanical tasks are combined; uncertain or money-critical work gets its own batch. Tests-first, review gates, per-batch commits and logging are unchanged.

| Batch | Tasks | Prompts |
|---|---|---|
| A | T1 + T2 (scaffold, schema, reset/seed) | 1 |
| B | T3 (walking skeleton + FastMCP spike) | 1 |
| C | T4 + T5 (money, models, errors, permissions, check-order pipeline) | 2 (tests, then code) |
| D | T6 + T7 (reads, create_request) | 2 (tests, then code) |
| E | T8 + T9 (approve, reject, record_payment) | 2 (tests, then code) |
| F | T10 + T11 + T12 (tool registration, concurrency, e2e flow + demo) | 1–2 |
| — | T13 (docs) | done by me with AI assistance |

## Cut order if time runs short

Cut from the top first:

1. `list_requests` filters (keep an unfiltered list) and AC-39.
2. Tool annotations (`readOnlyHint`).
3. Concurrency iterations 10 → 3. Keep the negative control as a manual note if it doesn't fit.
4. `STRICT` tables (CHECKs and FKs stay).
5. Unit tests that duplicate service-level coverage (e.g. separate `test_models.py` cases already exercised through `create_request`).
6. AC-23 (identity revoked mid-session). Keep the per-call re-resolution code.
7. Polish of `scripts/demo.py` output formatting.

**Never cut:** T0 spec commit before code; tenant isolation (scoped queries + composite FKs) and AC-17–AC-20; role matrix and AC-13–AC-15; the conditional atomic approval and AC-30; one payment per request (AC-10, AC-12); integer-cent money and invalid-amount tests (AC-24); state unchanged on error; missing/unknown identity and missing DB startup failures; stdout cleanliness; the end-to-end MCP test and demo (AC-31); `cb-reset`; pinned deps; traceability with honest results and limitations.

## Delegating to an AI coding agent

- **One batch per prompt (see Execution batches).** The prompt names the task ids and quotes the relevant SPEC sections and REQ/AC ids. It lists the files the agent may create or change and says "do not add tools, fields, states or rules not in SPEC.md; if something is unclear, stop and ask."
- **Tests first, owned by me.** For business-logic tasks I write or review the failing tests against the ACs before asking for implementation. The agent may not weaken, delete or skip a test to make it pass; any test change must be called out separately with a reason.
- **Review the diff, not the summary.** Checklist: no `float` near money; every SQL statement parameterized and filtered by `nonprofit_id`; mutations only inside `BEGIN IMMEDIATE`; no `print` or stdout writes in server code; errors only through the §6.5 envelope; no new dependencies without a lockfile update.
- **Independent evidence.** I run `uv run pytest` myself (and the demo for T12) instead of accepting "tests pass" claims, and record the actual output.
- **Spec changes are explicit.** If implementation shows the spec is wrong or incomplete, update SPEC.md §15 Revisions with the reason before or with the code change. Each task's interaction is logged in `docs/AI_LOG_RAW.md`.
