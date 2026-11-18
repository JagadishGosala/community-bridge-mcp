# Community Bridge: Emergency Assistance Funding

## Business Case

Community Bridge is a nonprofit helping participants with essential expenses such as rent, utilities and transportation.

The organization receives grant funding. Each fund has a fixed allocation, and staff need to understand how much money is committed, paid and available.

Today, assistance requests and payment updates are tracked in spreadsheets. Community Bridge wants these capabilities accessible through AI assistants and other MCP-compatible clients.

The organization needs a headless application supporting these activities:

- Case workers submit assistance requests for existing participants, including the purpose, amount and funding source.
- Program managers approve or reject pending requests.
- Finance staff record simulated payments against approved requests.
- Staff retrieve requests, statuses and funding summaries.

Approval reserves the full requested amount against the selected fund. Payment moves that amount from committed to paid expenditure without reducing available funding a second time.

For example, approving $300 against a $10,000 fund leaves $9,700 available. Paying that request leaves $300 paid, $0 committed and $9,700 available.

The application must prevent overspending, duplicate financial effects and unauthorized access. Staff must only access records belonging to their nonprofit.

This is a fictional exercise. No prior Bonterra product knowledge is required.

## Your Task

### 1. Create a specification before coding

The specification is a primary deliverable. It should be clear enough for another engineer or AI coding agent to implement without inventing important business behavior.

Translate the business case into a concise, implementation-ready specification covering:

- Requirements: Identify the users, workflows, goals, non-goals and assumptions. Assign requirement IDs.
- Business behavior: Define request states, permitted transitions, budget calculations, validation and retry behavior.
- Data model: Describe the entities, relationships, ownership and approach to exact monetary arithmetic.
- MCP interface: Define tool names, descriptions, input/output schemas, side effects and error behavior.
- Permissions: Explain how caller identity, staff roles and nonprofit boundaries are enforced.
- Acceptance criteria: Provide concrete examples with expected outcomes, including important failure cases.
- Implementation methodology: Break the work into ordered tasks with dependencies, completion criteria and verification gates. Explain how you would scope and review work delegated to an AI coding agent.
- Production security: Briefly explain how an HTTP-hosted MCP server would integrate with an existing OAuth authorization provider, validate access tokens and map callers to nonprofit membership and business permissions.
- Open questions: Identify information you would clarify with the business. Make and document reasonable assumptions so you can proceed.

Save the initial specification before implementation. Document significant subsequent changes and their reasons.

Your specification should guide both the implementation and the tests.

### 2. Implement a working version from your specification

Build a headless MCP server using your preferred language and a compatible MCP SDK.

Expose discoverable tools supporting participant and fund lookup, request creation, approval or rejection, simulated payment recording, request retrieval and funding summaries.

Provide:

- Validated inputs, defined output schemas and structured results.
- Persistent local storage.
- Synthetic seed data for two nonprofits, each with participants, funding and fixture staff identities.
- A repeatable setup/reset command that is separate from normal startup.
- Local stdio support and documented, pinned dependencies.

For this exercise:

- Requests start as Pending.
- Allowed transitions are Pending → Approved, Pending → Rejected and Approved → Paid.
- Submitting a request does not reserve money.
- Approving a request reserves the full amount, provided funding is sufficient.
- Rejecting a Pending request leaves funding unchanged.
- Payment is for the full approved amount and can succeed only once per request.
- Requests cannot be edited after submission.
- Amounts must be positive, using exact cent-level arithmetic in USD.
- Approval and budget reservation must be atomic so competing approvals cannot overspend a fund.
- Invalid or unauthorized actions must leave business state unchanged.

Use these permissions within each nonprofit:

- All three staff roles can read the exercise’s records and summaries.
- Case workers can create requests.
- Program managers can approve or reject requests.
- Finance staff can record payments.

Use trusted fixture identities selected through a launcher or environment configuration. Resolve each identity to its role and nonprofit on the server. Reject missing or unknown identities.

Tool arguments, prompts and stored text must not grant additional permissions.

Keep application logs separate from the MCP protocol output.

### 3. Verify the implementation against your specification

Add meaningful automated tests covering:

- Request-state transitions and funding calculations.
- Insufficient funding.
- Repeated approvals and payment retries.
- Role restrictions and cross-nonprofit access.
- Missing identity and invalid inputs.

Explain how competing approvals are handled and how you verified that protection.

Connect requirement IDs to the relevant implementation and tests. Report actual results, including failed or unrun checks.

Include at least one automated end-to-end test through MCP.

Provide a reproducible MCP client demonstration that discovers tools, creates a request, approves it, records payment and retrieves the final funding summary using the appropriate fixture identities.

### 4. Explain your AI-assisted approach

Use AI during the assignment.

Provide three brief examples covering:

- Requirements analysis or specification.
- Implementation planning or coding.
- Debugging or verification.

For each, include relevant context or prompt excerpts, the resulting suggestion or change, and the independent evidence you used to check it.

Include corrections where they occurred. Do not manufacture an AI mistake. Full chat histories are unnecessary.

## Time and Scope

Stop after three hours of active work, including specification, AI interaction, implementation and testing.

Submit completed work, actual time spent, known limitations and next priorities. Do not extend the time to add extra features.

Use synthetic data, one currency and simulated payments.

The following are outside scope:

- Frontend development; no UI is required or scored.
- Real banking or payment-provider integration.
- OAuth implementation or production identity infrastructure.
- Remote hosting or cloud deployment.
- A custom AI agent or hosted language-model integration.
- MCP resources and prompts.
- Participant intake and grant applications.
- Partial payments, cancellations, refunds and external payment failures.

An MCP client script can demonstrate the solution without calling a language model.

## Submission

Provide a private repository or archive containing:

- Initial specification, implementation plan and significant revisions.
- Working server, dependencies and seed/reset instructions.
- Tests and exact setup, run and test commands.
- MCP client configuration or demonstration script.
- Requirement-to-implementation-to-test mapping.
- Brief AI workflow evidence.
- Actual time spent, limitations and deferred work.

Keep written documentation to approximately three pages, excluding schemas, code and test output.

## Technical Follow-Up

The technical interview will use your submission.

Expect to explain your specification, trace a requirement through code and tests, investigate a failure case, and adapt the specification and implementation to a small requirement change.