# Community Bridge MCP — Emergency Assistance Funding (Phase 1)

A headless MCP server (stdio) that lets nonprofit staff submit, approve or reject, and pay emergency-assistance requests against grant funds. It keeps each fund's committed, paid and available amounts exact to the cent, prevents overspending and duplicate payments, and enforces roles and nonprofit boundaries.

**Stack:** Python 3.12, official `mcp` SDK 2.3 (low-level `Server`), Pydantic v2, SQLite (stdlib `sqlite3`), pytest, uv.

**Documents:** [Specification](docs/SPEC.md) (v1.0 committed before any code; revisions in §15) · [Implementation plan](docs/TASKS.md) · [Requirement → code → test mapping](docs/TRACEABILITY.md) · [AI workflow](docs/AI_LOG.md)

## Setup and commands

Requires [uv](https://docs.astral.sh/uv/). uv installs the pinned Python (`.python-version`) and the locked dependencies (`uv.lock`).

```bash
uv sync --locked                     # install exact pinned dependencies
uv run cb-reset                      # create ./data/cb.sqlite3 with schema + seed data (separate from startup)
CB_STAFF_ID=stf_bridge_cw uv run cb-server   # serve MCP over stdio as a fixture identity
uv run pytest -v                     # full test suite (unit, service, end-to-end, concurrency)
uv run python scripts/demo.py        # MCP client demo: discover → create → approve → pay → summary
```

PowerShell: `$env:CB_STAFF_ID="stf_bridge_cw"; uv run cb-server`.

| Variable | Meaning |
|---|---|
| `CB_STAFF_ID` | Required. Fixture identity the server acts as; resolved server-side to role and nonprofit. Missing or unknown → the server refuses to start. |
| `CB_DB_PATH` | SQLite file, default `./data/cb.sqlite3`. `cb-reset` and `cb-server` use the same value. |
| `CB_TEST_TX_DELAY_MS` | Test-only. Holds the approval transaction open to force overlap in the concurrency test. Ignored when unset. |

Logs go to stderr only; stdout carries only MCP JSON-RPC.

## Fixture identities (seed data)

| Nonprofit | Case worker | Program manager | Finance | Funds |
|---|---|---|---|---|
| Community Bridge (`np_bridge`) | `stf_bridge_cw` | `stf_bridge_pm` | `stf_bridge_fin` | `fund_bridge_rent` $10,000.00 · `fund_bridge_utility` $2,500.00 |
| Harbor Neighbors (`np_harbor`) | `stf_harbor_cw` | `stf_harbor_pm` | `stf_harbor_fin` | `fund_harbor_general` $5,000.00 |

## MCP client configuration

One server entry per identity (identity is fixed per process):

```json
{
  "mcpServers": {
    "community-bridge-case-worker": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/community-bridge-mcp", "run", "cb-server"],
      "env": { "CB_STAFF_ID": "stf_bridge_cw", "CB_DB_PATH": "/absolute/path/to/community-bridge-mcp/data/cb.sqlite3" }
    }
  }
}
```

Tools: `whoami`, `list_participants`, `list_funds`, `get_funding_summary`, `get_request`, `list_requests`, `create_request`, `approve_request`, `reject_request`, `record_payment` (schemas and errors in SPEC §8).

## Key design decisions

- **Balances are derived, not stored.** committed = Σ APPROVED, paid = Σ PAID, available = allocation − committed − paid, computed from request rows, so they cannot drift.
- **Money is integer cents.** Amounts arrive as decimal strings (`"300.00"`), are checked against a strict pattern and parsed with `Decimal`; floats are never used. JSON numbers are rejected.
- **Nonprofit isolation at two layers.** Every query is scoped by the caller's `nonprofit_id`, and composite foreign keys stop a request, decision or payment from linking records of another nonprofit even if application code is wrong. Other nonprofits' records return `NOT_FOUND`, identical to a nonexistent id.
- **Identity comes only from the launcher.** `CB_STAFF_ID` is resolved at startup and again on every call. No tool accepts a role, nonprofit or staff field, and unknown input fields are rejected.
- **Low-level MCP `Server`.** A spike showed the SDK's high-level server silently drops unknown arguments and prefixes error text, which conflicts with the spec, so one adapter validates raw arguments and returns pure-JSON error bodies (SPEC revision 1.2).

## How competing approvals are handled

Approval runs inside `BEGIN IMMEDIATE`, which takes SQLite's single write lock before any balance is read, and is a single conditional `UPDATE` that approves only if the request is still `PENDING`, belongs to the caller's nonprofit, and the fund's available amount covers it. A second approver waits for the lock and then re-evaluates against committed data, so two approvals can never both fit. Payment uses the same pattern, with `UNIQUE(payments.request_id)` as a backstop.

**Verified by** `tests/e2e/test_concurrency.py` (AC-30): two separate `cb-server` processes approve two $6,000 requests on the $10,000 fund at the same time, with the transaction held open (300 ms) so the approvals overlap; 10 iterations, each with exactly one approval, the other `INSUFFICIENT_FUNDS`, and available = 4,000.00. **Negative control** (run once, not kept): with approval swapped for a naive read-then-write version, the unchanged test failed: both $6,000 requests were approved, committing $12,000 against the $10,000 fund.

## Test results (actual)

```
338 passed in 57.53s
```

Platform: Windows, Python 3.12.14, mcp 2.3.0. No failed or skipped tests. Checked manually rather than by automated test: AC-41 (`uv sync --locked`). The AC-30 negative control was run once and is not part of the suite.

## Time spent

| Phase | Time |
|---|---|
| Specification (agent draft, independent review, fixes, commit) | <<~40 min>> |
| Implementation and tests, batches A–F | <<~1 h 50 min>> |
| Documentation | <<~20 min>> |
| **Total** | <<~2 h 50 min>> |

## Known limitations

- No idempotency keys: retrying `create_request` creates a second request (Q-07); approval and payment retries fail safely with `INVALID_TRANSITION`.
- SQLite allows one writer at a time; a lock wait over 5 s returns `INTERNAL_ERROR` with `retryable: true`.
- One identity per server process; switching identity means relaunching (A-12).
- Lists are unpaginated (A-14).
- Developed and tested on Windows only; not yet run on Linux or macOS.
- Decision and payment timestamps are tested for format, not for ordering.
- The duplicate-payment backstop (reachable only with corrupted data) reports `current_status: "PAID"`.
- Every expected error (role refused, not found, …) is logged at WARNING; a judgement call on Q-11.
- Written documentation runs somewhat over the suggested three pages, mostly SPEC acceptance criteria.

## Next priorities

1. Idempotency keys on mutating tools.
2. Streamable HTTP transport with the OAuth resource-server integration in SPEC §13.
3. Run CI on Linux and macOS.
4. Pagination for list tools, and an append-only audit log of status changes (Q-09).
