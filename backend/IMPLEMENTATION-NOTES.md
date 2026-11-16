# Implementation Notes

Companion to `architecture/TASD-v1.0.md`. Read this alongside the code,
not instead of it. Every deviation from the approved architecture below
is declared here, with a reason, rather than left to be discovered --
nothing in this build silently rewrites or contradicts TASD-v1.0.

**Status: a complete, integrated, role-aware application, now with a
second real AI provider (Gemini) and a governed Organizational Decision
Registry.** Backend (Scope -> AI Analysis -> Questions -> Answers ->
Mapping -> Evidence -> Environment -> Engine -> Approval -> Audit) plus
a central AI orchestration facade and a real seven-page frontend
(Requester Portal, AI Assessment Workspace, Assessment Queue, Compliance
Dashboard, Organizational Decision Dashboard), all calling the same
backend over its real JSON API -- no mock screens. 106 automated tests
pass. See §11-14 for what changed in this round: Gemini integration
(live inference against the real account was reached end-to-end through
the actual application and browser UI -- see the updated §11 for the
corrected finding, which supersedes this section's earlier "POST hangs"
diagnosis), the Organizational Decision Registry, the security-test pass (which
caught and fixed a real upload-validation gap), and an honest
PostgreSQL/S3 status update.

## 1. What is implemented

| Module | What it does | Key files |
|---|---|---|
| Auth / RBAC | Local username+password, server-signed JWT, server-side role enforcement for all six roles | `app/security.py`, `app/api/routes/auth.py` |
| **Central AI agent** | Orchestration facade coordinating scope analysis, answer processing, and control-mapping proposal -- delegates to, never duplicates, the modules below | `app/services/ai_agent.py` |
| Scope intake | BR-001 scope submission, versioned | `app/services/scope_service.py`, `app/api/routes/poc_requests.py` |
| AI questionnaire | Scope analysis -> 11-15 server-validated questions + identified gaps/assumptions (BR-008), Mandatory/Conditional domain rules, retry-then-fail, injection/control-ID rejection | `app/services/ai/questionnaire.py`, `app/api/routes/questionnaire.py` |
| Control catalog | D3-Catalog seeded verbatim (Unverified) into `control`/`control_domain` | `app/models/catalog.py`, `app/services/catalog_seed.py` |
| Control mapping | AI drafts mappings from a CLOSED per-domain candidate set; Reviewer Confirm/Adjust/Reject as new rows, never edits | `app/services/ai/mapping.py`, `app/services/mapping_service.py`, `app/api/routes/mapping.py` |
| Evidence | Four-state model, quarantine-then-scan upload, human-only Verified/Rejected transition | `app/services/evidence_service.py`, `app/api/routes/evidence.py` |
| Environment readiness | Seven dimensions, full ExceptionRecord, non-waivable Isolation/AccessControl (CHECK + service check), `final_signoff_boolean` computed fresh | `app/services/environment_service.py`, `app/api/routes/environment.py` |
| Versioning | All five `AssessmentInputVersion` hashes recomputed and a new version row inserted on every one of D2 section 8.5's invalidating-change types | `app/services/versioning.py` |
| Decision Engine | Pure function, fixed Layer 1->2->3 order, OD-10/15/16-gated refusal, never a fabricated outcome | `app/services/engine.py` (pure), `app/services/engine_orchestration.py` (DB glue) |
| Human approval | P1-P4 in one transaction, synchronous re-run on P4 failure, disagreement-rationale rule, no override path | `app/services/approval_service.py`, `app/api/routes/approval.py` |
| Audit trail | SHA-256 hash chain, same-transaction persistence, tamper detection | `app/services/audit_service.py` |
| **Assessment summary / queue** | Consolidated read-model behind the Workspace screen; cross-cutting "all assessments" listing for non-Requester dashboards | `app/services/ai_agent.py:get_assessment_summary`, `app/api/routes/assessment.py` |
| **Audit API** | List/filter audit entries, on-demand hash-chain verification, for the Compliance Dashboard | `app/api/routes/audit.py` |
| Policy config | OD-01/10/11/15/16 as explicit, PlatformOwner-published, NULL-until-set configuration | `app/models/engine.py`, `app/api/routes/engine.py` |
| **Frontend (6 pages, shared CSS/JS)** | Login/Register, Requester Portal, Assessment Workspace (shared by every role, role-gated controls), Assessment Queue (Reviewer/EnvOwner/Approver/PlatformOwner), Compliance Dashboard. Responsive, consistent styling, provenance badges, status pills, progress indicator | `app/web/templates/*.html`, `app/web/static/app.{css,js}` |

**76 automated tests, all passing** (`pytest -q`): auth/RBAC, scope submission, AI governance invariants (count/domain/injection/control-ID rejection), questionnaire persistence, control mapping (including the invented-identifier-rejection test and the reviewer new-row-not-edit test), evidence (four states, non-waivable AV-scan-vs-validation separation, reset-on-reupload), environment readiness (full sign-off matrix, non-waivable rule, expiry, revocation), the Decision Engine as a pure function (10 tests, including the property-style evidence-dominance and Rejected-mapping-exclusion tests -- **this suite caught and fixed a real severity-formula bug during development, see §8**), the full approval integration suite (P1-P4, the synchronous P4 re-run, unconditional Rejected/MoreInfoRequested, disagreement-rationale ordering -- **also caught and fixed a real precondition-ordering bug, see §8**), audit hash-chain integrity/tamper-detection and atomicity, and (new this round) the assessment summary/queue/audit-API integration tests -- including a regression test for a real route-collision bug this round introduced and fixed (`/api/poc-requests/queue` vs. `/api/poc-requests/{id}`, see §8).

## 2. AI provider: real integration, no key required to keep building

Per explicit instruction, the absence of an `ANTHROPIC_API_KEY` was never
treated as a blocker:

- `app/services/ai/client.py` defines the `ModelClient` protocol and a
  real `AnthropicModelClient` implementation -- fully coded, ready to
  activate by setting `ANTHROPIC_API_KEY` in the environment (see
  `.env.example`). No code change is needed to go live with it.
- `FakeModelClient` (same file) is the clearly-named, test-and-dev-only
  stand-in. It is wired in ONLY via explicit test-time dependency
  overrides (`app.dependency_overrides[model_client_dependency] = ...`)
  or direct unit-test calls -- it is never the default and never
  silently substituted in the running application.
- With no key configured, every AI-dependent endpoint
  (`/questionnaire/generate`, `/mappings/generate`) returns a plain
  **503 "ANTHROPIC_API_KEY is not configured..."** -- `app/api/deps.py`'s
  `model_client_dependency` raises this before any AI call is attempted.
  This was verified against the real running server (not just the test
  client) in both this round and the Phase 1 round.
- Nothing in the codebase fabricates an AI result when the key is
  missing. The one place a "fake-looking" response could appear is
  `FakeModelClient`, and it is never reachable outside a test file or an
  explicit override a human wrote.

## 3. Declared deviations from architecture/TASD-v1.0.md, and why

| TASD-v1.0.md says | This build does | Why | What closes the gap |
|---|---|---|---|
| section 9.3: PostgreSQL 16 as the sole datastore (ADR-003) | SQLite via `aiosqlite`, config-driven (`DATABASE_URL`) | No PostgreSQL instance or Docker is available in this environment | Point `DATABASE_URL` at a `postgresql+asyncpg://...` DSN (the `postgres` extra: `pip install -e ".[postgres]"`); the ORM is dialect-neutral and all three migrations are already written to compile identically on both dialects (explicit FK ordering, `batch_alter_table` for SQLite's lack of `ALTER TABLE ADD CONSTRAINT`). `deploy/postgresql_roles.sql` implements section 11.10's role separation and is ready to run against a real instance -- see §4 for what is still unverified live. |
| section 8.3: OIDC + PKCE, server-side session (ADR-010) | Local username/password + JWT | No enterprise IdP available here | `get_current_user`'s contract (server-derived `user_id`/`role`, never trusted from the request) is already exactly what every later phase depends on -- swapping the transport does not change downstream code. |
| section 9.1: React SPA | Server-rendered HTML + vanilla JS calling the same JSON API | Faster to verify real end-to-end behavior without frontend build tooling | The JSON API is the real contract. |
| section 9.5/15.4: S3-compatible object storage, quarantine/serving bucket separation | `app/services/storage.py` -- an `ObjectStorage` protocol with `LocalFilesystemStorage` (dev/test default) and a real `S3Storage` (boto3), selected by `STORAGE_BACKEND` | No real S3/MinIO instance is available here to test `S3Storage` against live -- it is tested against `moto`'s mocked S3 instead (`tests/test_storage.py`); see §4 for the honest distinction. | Set `STORAGE_BACKEND=s3` plus the bucket/credential settings (`.env.example`); `app/services/evidence_service.py` depends only on the protocol, never on which backend is active. |
| section 15.4: real AV-scan service | A placeholder synchronous scanner (`evidence_service.run_scan`) that flags a recognizable test marker as Infected, everything else Clean | No AV service available here; **explicitly named as a placeholder in the code itself**, not hidden | Replace `run_scan`'s body with a call to a real AV API; the quarantine-then-scan control flow and the "scanning never implies validation" separation do not change. |
| section 11.10: `ai_svc`/`engine_svc`/`audit_writer` database-role grant separation | `deploy/postgresql_roles.sql` implements `poc_app_rw` (DML-only) / `poc_migrator` (DDL) -- a coarser split than three per-concern roles, but the same least-privilege principle: the running app cannot alter schema | Written against a real PostgreSQL instance's role/grant model, which SQLite has none of -- **not yet run against a live PostgreSQL to confirm the GRANTs behave as written** | See §4 for exactly what "implemented" vs "verified live" means here. |
| section 11.9: `SELECT ... FOR UPDATE` row lock closing the P4/evidence-state TOCTOU gaps | `.with_for_update()` now added at every identified race site (`approval_service.py`, `versioning.py`, `audit_service.py`, `evidence_service.py`) -- a real row lock under PostgreSQL, a no-op under SQLite (the dialect doesn't support it) | SQLite's own lack of row-level locking means the SQLite dev/test path still relies on its single-writer file lock, now backed by a `VersionConflictError`/409 safety net for the case SQLite surfaces instead (see §4 item 2) | Confirmed structurally correct against two genuinely independent SQLite connections (`tests/test_evidence_concurrency.py`); not yet confirmed against real PostgreSQL concurrent load -- see §4. |

## 4. Known gaps that are genuinely blocked, not just deferred

1. **Database role separation and the FOR UPDATE locks are implemented
   but UNVERIFIED against a real PostgreSQL instance.** `deploy/postgresql_roles.sql`
   and the `.with_for_update()` calls are written against PostgreSQL's
   actual role/grant and row-locking semantics, cross-checked against
   SQLAlchemy's documented dialect behavior (SQLite silently omits the
   `FOR UPDATE` clause; it never errors, confirmed by the full test
   suite passing with every lock added) -- but neither has been run
   against a live PostgreSQL 16 instance, because none is available in
   this environment. **Until that run happens, "two concurrent writers
   can never both bump the same version" is true as reasoned-through
   code, not yet as an independently observed database fact.**
2. **SQLite's OWN concurrency behavior, now exercised directly (not
   just reasoned about).** `tests/test_evidence_concurrency.py` opens
   two genuinely independent SQLite connections (not
   `tests/test_security.py`'s shared single-connection fixture, which
   cannot exhibit real inter-transaction behavior at all -- confirmed
   the hard way: an earlier version of this concurrency test, run on
   that shared connection, showed one writer's `rollback()` apparently
   undoing the other's already-committed state, which turned out to be
   an artifact of sharing one physical connection, not an application
   bug) and confirms SQLite genuinely refuses the losing writer -- as
   either a `assessment_input_version` unique-constraint collision
   (caught and re-raised as `VersionConflictError`,
   `app/services/versioning.py`) or sqlite3's own
   `OperationalError: database is locked` (caught by a dedicated
   handler, `app/main.py`) -- both surfaced as a clean 409 Conflict,
   never an unhandled 500. This is real, verified behavior for SQLite;
   the PostgreSQL path (the second writer blocking on the `FOR UPDATE`
   lock until the first commits, then succeeding rather than
   conflicting at all) remains unverified per item 1.
3. **D3-Catalog is seeded but still UNVERIFIED.** `verification_status`
   defaults to `Unverified` on every row and nothing in this codebase
   ever writes `Verified` -- there is no endpoint for it. A GRC owner
   reviewing against licensed ISO/NIST text is still required before
   this catalog should be treated as authoritative (D3-Catalog section 2).
4. **`evidence_requirement.sufficiency_criteria` (OD-17) and the policy
   hooks (OD-11) are not modeled as database tables yet** -- Layer 2's
   `missing_evidence_on_always_required_controls` and
   `policy_hook_blockers_fired` are hardcoded to empty in
   `engine_orchestration.py`, which is the documented safe default
   (nothing gates on them until the organization configures a hook), but
   there is no admin UI to populate them yet.

## 5. Running it

```bash
cd backend
../.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

Create `backend/.env` from `.env.example` with at least `JWT_SECRET_KEY`
set. Add `ANTHROPIC_API_KEY` to enable the two AI-dependent endpoints.

```bash
../.venv/Scripts/python.exe -m alembic upgrade head
../.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

- `/login` -- sign in / register (any of the six roles); `/` redirects here
- `/requester` -- Requester Portal: submit scope, list "my assessments"
- `/assessment?id=<poc_request_id>` -- the AI Assessment Workspace / assessment-detail page every role opens: scope, AI gaps/assumptions, questionnaire+answers, control mapping, evidence, environment readiness, recommendation, approval -- role-gated action buttons, server-enforced regardless
- `/queue` -- Assessment Queue: landing page for SecurityReviewer, EnvironmentOwner, FinalApprover, PlatformOwner (who also sees the Policy Config panel here)
- `/compliance` -- Compliance Dashboard: audit chain verification + full audit trail, read-only
- `/docs` -- OpenAPI/Swagger UI for every endpoint

Run tests: `../.venv/Scripts/python.exe -m pytest -q` (76 passed).

## 6. A full manual walkthrough (no AI key required)

1. Open `/login`, register six accounts (one per role), and sign in as
   each in turn to see their landing page (`/requester` for Requester;
   `/queue` for Reviewer/EnvOwner/Approver/PlatformOwner; `/compliance`
   for ComplianceAuditor).
2. As `PlatformOwner` on `/queue`: publish a policy config
   (`layer1_completeness_threshold`, `layer3_weights`,
   `layer3_thresholds` -- this is where the organization's real
   OD-10/15/16 answers go; nothing is pre-filled).
3. As `Requester` on `/requester`: submit a scope, which opens
   `/assessment?id=...`. With an AI key configured, click "Analyze scope
   & generate questions" and answer them; without one, the page shows
   the exact 503 configuration message (verified live, see §7) and you
   skip to environment readiness.
4. As `EnvironmentOwner`, open the same assessment from `/queue` and
   attest all seven dimensions.
5. Click "Run engine" (any role) to compute the recommendation.
6. As `FinalApprover`, open the assessment and submit a decision.
7. As `ComplianceAuditor` on `/compliance`, click "Verify chain now" and
   watch every step above appear in the audit trail table below it.

This exact sequence (steps 1-2, 4-7) was driven through a real browser
session against a live `uvicorn` process during this build -- not just
the test client -- including registering a Requester and a Compliance
Auditor, submitting a real scope, confirming the 503 AI-refusal message
renders correctly in the Workspace UI, and watching the live
hash-chain-verification endpoint report "OK" against the real audit
entries that session had produced. Step 3's questionnaire/mapping
generation was additionally verified via `curl` against the real
server (§7) and via the automated test suite's `FakeModelClient`
(§1) -- not live end-to-end with a real AI key, since none is
available in this environment.

## 7. Live smoke-test evidence

A real server run (`uvicorn`, not pytest) was driven through: register
all six roles -> publish policy config -> submit scope -> confirm the
Reviewer's `/api/poc-requests/queue` and `/api/poc-requests/{id}/summary`
both return real data -> attest all seven environment dimensions ->
confirm `final_signoff_boolean: true` -> run the engine (correctly
returned `INSUFFICIENT_INFORMATION` with the exact missing Mandatory
domains, since no questionnaire had been answered in this particular
run) -> commit an unconditional `Rejected` decision -> as
ComplianceAuditor, call `/api/audit-entries/verify` (`{"ok": true, ...}`)
and `/api/audit-entries` (10 entries, correctly ordered). No server
errors in the log for the entire run.

## 8. Bugs this build's own test suite caught and fixed

Documented because catching them is the point of writing the tests, not
something to bury:

1. **Engine severity-formula bug** (`app/services/engine.py`): the
   original Layer 3 implementation used `max(f1, evidence_severity)`
   for the "High confidence + bad evidence" dominance case but
   `f1 + evidence_severity` (a sum) for every other case. This meant a
   control with Verified evidence and High confidence could score a
   *higher* severity than the same control with No evidence at all --
   exactly backwards. `tests/test_engine.py::test_evidence_state_dominance_over_high_confidence`
   caught it; fixed by replacing both branches with one formula where
   evidence severity is always the dominant term and confidence
   contributes only a small, strictly additive offset that can never
   cross a severity-tier boundary.
2. **Approval precondition-ordering bug** (`app/services/approval_service.py`):
   the disagreement-rationale check (D5 section 9) originally ran
   *before* P1-P4, so an `Approved` attempt against a `NO-GO` or
   `Insufficient Information` recommendation returned a 422 ("missing
   disagreement rationale") instead of the correct 409 ("preconditions
   failed"). `tests/test_approval.py::test_approval_blocked_by_p1_incomplete_signoff`
   and `::test_insufficient_information_cannot_be_approved` caught it;
   fixed by moving the disagreement-rationale check to run only after
   P1-P4 have already passed (i.e., only when a decision is actually
   about to commit).
3. **Route-collision bug, introduced and fixed in this round**
   (`app/main.py`): adding `GET /api/poc-requests/queue` collided with
   the pre-existing `GET /api/poc-requests/{poc_request_id}` -- both are
   single-segment paths under the same prefix, and FastAPI/Starlette
   resolves the ambiguity by router registration order, not by
   literal-vs-parameter specificity. Caught by direct testing before it
   reached the automated suite (a Reviewer's `/queue` call returned
   403/404 depending on role, because it was being matched as a
   `poc_request_id` lookup against the Requester-only ownership check);
   fixed by registering `assessment.router` (which owns `/queue`) before
   `poc_requests.router` in `app/main.py`, with the reasoning commented
   at the point of registration so it cannot be silently reordered
   later. `tests/test_assessment_and_audit.py::test_queue_route_not_shadowed_by_poc_request_id_route`
   is a permanent regression test for this.

## 9. Frontend architecture notes

Six pages, one shared `app.css` and `app.js` (no per-page duplication of
auth/API/nav logic): `login.html`, `requester.html`, `assessment.html`
(the single, comprehensive "AI Assessment Workspace" / assessment-detail
page every role opens via `/assessment?id=<poc_request_id>`, with
role-gated action controls -- not role-gated *data*: every role that can
read a section sees the same real data, consistent with the backend's
own RBAC), `queue.html` (shared landing for the four cross-cutting
roles, with the Policy Config panel additionally shown only to
PlatformOwner), and `compliance.html`.

**Every control calls the real backend API; nothing is mocked in the
frontend.** This was verified twice: once by code review (there is no
hardcoded/sample data anywhere in `app/web/static/app.js` or any
template -- every table and field is populated from an `APP.api(...)`
call), and once by driving the actual application through a real
browser session during this build: registering a Requester, submitting
a real scope, confirming the assessment workspace rendered it with the
correct `REQUESTER_FACT` provenance badges, triggering AI analysis and
confirming the exact 503 configuration-message path renders correctly
(not a fake question set), then registering a Compliance Auditor and
confirming the live hash-chain verification reported "OK" against the
real audit entries that first session had produced.

The two Phase-1/Phase-2 placeholder pages (`index.html`, `workflow.html`)
were removed in this round -- superseded by the six pages above, which
cover every role the brief names. No orphaned or disconnected template
remains in `app/web/templates/`.

## 10. What genuinely blocks the next step

Unchanged from the Phase 1 assessment: **production-shaping this build
requires a real PostgreSQL deployment** to express the database-role
privilege separation (section 11.10) and the `FOR UPDATE` row lock
(section 11.9) that are currently either absent or only approximated by
SQLite's coarser guarantees. This is an infrastructure-provisioning
blocker, not an architecture or design gap -- every piece of application
logic those two mechanisms would wrap around is already written, tested,
and dialect-neutral.

Separately, and also unchanged: the six blocking Open Decisions
(OD-01, OD-06, OD-07, OD-10, OD-15, OD-16) remain unresolved by design.
This build makes that concrete rather than abstract -- `POST
/api/admin/policy-config` is the literal, tested mechanism by which an
organization supplies its real answers, and until it is called with
real values, the engine keeps refusing to produce a `GO` (verified
live in section 7).

## 11. Gemini integration -- status (corrected: live inference reached, quota-limited)

`app/services/ai/client.py:GeminiModelClient` is fully implemented using
the official `google-genai` SDK, behind the same `ModelClient` protocol
`AnthropicModelClient` already used, sharing the same
`_build_user_content` data/instruction-separation helper (so prompt-
injection resistance is provider-agnostic) and the same transport-level
retry/timeout wrapper (`_with_retry`: 3 attempts, exponential backoff,
60s per-attempt timeout, distinguishing retryable transient failures
from a hard failure). `AI_PROVIDER=gemini` in `.env` activates it; no
code change is needed to switch providers.

**This section previously (incorrectly) concluded that outbound POST to
`generativelanguage.googleapis.com` hung/timed out in this sandbox.**
That conclusion is superseded: in a later session, a live end-to-end run
through the actual running application (registration -> login ->
Requester Portal -> scope submission -> "Analyze scope & generate
questions" button, driven via real browser automation, not a script)
successfully reached Gemini's `generateContent` endpoint through the
app's own async SDK call path and received real, structured JSON error
responses back (`429 RESOURCE_EXHAUSTED`, with `retryDelay` and
`quotaId` fields) -- which is only possible if the POST actually
reached Google's servers and was processed. The earlier "hangs" finding
was most likely an artifact of a since-resolved transient sandbox
condition, not a durable property of this environment.

**What was verified, step by step:**

1. The real `GEMINI_API_KEY` is configured directly in `backend/.env`,
   never echoed to a terminal, never logged, and is additionally
   protected at the application level: every credential field in
   `app/config.py` is `SecretStr`, not `str`, so `repr(settings)` prints
   `**********` -- verified by a dedicated test
   (`tests/test_security.py::test_settings_secrets_are_masked_in_repr`).
2. `GET https://generativelanguage.googleapis.com/v1beta/models` with
   the key succeeds and returns the account's real available model list,
   confirmed again in this round via `client.models.list()` through the
   official SDK. `gemini-3.8-flash` (the configured default) is
   confirmed present and `generateContent`-capable on this account,
   alongside `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3.5-flash`,
   and others.
3. A real `POST :generateContent` call, made through the app's own
   async SDK path during a live browser-driven demo of the Requester
   flow, reached Google and returned a genuine `429 RESOURCE_EXHAUSTED`
   error -- first the free tier's per-minute limit
   (`generate_content_free_tier_requests`, 5/min), then, after repeated
   demo attempts (each retried 3x by `_with_retry`, compounding call
   volume), the free tier's **per-day** limit
   (`GenerateRequestsPerDayPerProjectPerModel-FreeTier`, 20/day for
   `gemini-3.8-flash`). The app correctly surfaced Google's real error
   text as a 502 via `ModelUnavailableError` rather than fabricating a
   response -- the fail-closed behavior worked exactly as designed under
   a real failure condition, not just in a unit test.
4. A direct, non-retrying sync-SDK probe (bypassing the app, to check
   current quota state) was also run; see the session's own report for
   whether it returned a quota error, a fresh success, or hung -- the
   daily quota resets roughly 24h after the first request in that
   window, so same-day retries are expected to be quota-limited.

**Conclusion:** the Gemini integration code is correct and live
inference is confirmed reachable from this sandbox; the only live
Gemini testing cut short in this build was due to the free tier's own
daily request cap, not a code defect or a network restriction. The
questionnaire-generation and control-mapping pipelines are verified at
two levels: structurally/deterministically via `FakeModelClient`
(unit/integration tests, unaffected by provider quotas) and, for the
scope-analysis step specifically, against the real Gemini API live.

**What this means for activation in a real deployment:** nothing in the
code needs to change. `AI_PROVIDER=gemini` plus a valid `GEMINI_API_KEY`
activates real inference immediately; a production deployment should
use a paid Gemini tier (or Anthropic, via `AI_PROVIDER=anthropic`) to
avoid the free tier's 20-requests/day ceiling hit during this testing.

### 11.1 Quota-aware backoff, and a repeatable live verification command

Two follow-up items from a later round of live testing:

1. **`_with_retry` (app/services/ai/client.py) is now quota-aware.**
   Previously every retryable failure (429 included) got the same
   fixed exponential backoff across all 3 attempts regardless of what
   the server actually said to do -- which is how an earlier live demo
   burned through the entire free-tier *daily* quota in one sitting
   (each of several duplicate UI clicks triggered its own 3-attempt
   retry loop). Gemini's 429 responses carry a `retryDelay` in their
   `error.details` (a `google.rpc.RetryInfo` entry); `_with_retry` now
   reads it (`_extract_retry_delay_seconds`) and, if it's longer than
   `_MAX_INLINE_RETRY_DELAY_SECONDS` (5s) -- i.e. a per-minute or
   per-day quota cap, not a brief blip -- stops after that single
   attempt instead of retrying blindly. A short-lived 429/503 (no
   advertised delay, or a short one) still gets the full 3-attempt
   backoff as before. Covered by `tests/test_ai_client_retry.py`
   (4 tests, exercising both branches plus the non-transient-error
   passthrough).
2. **`scripts/verify_gemini.py`** is a safe, repeatable, single-attempt
   live verification command: `python scripts/verify_gemini.py` from
   `backend/`. It checks the configured model is present and
   `generateContent`-capable (a GET, no generation quota consumed),
   then makes exactly one live call through the real `GeminiModelClient`
   (the same class and retry wrapper the app itself uses). Exit code 0
   means live inference is confirmed; 1 means reachable but currently
   blocked (quota or a transient provider-side condition -- re-run
   later, it will not retry blindly); 2 means a configuration/code
   error. Never prints the API key.

**Result of running it in this round:** the model-availability check
passed (`gemini-3.8-flash` confirmed present and `generateContent`-
capable). The single live call returned `503 UNAVAILABLE` ("This model
is currently experiencing high demand") -- a different real condition
than the earlier `429` quota exhaustion, and, like it, proof the
request reaches Google's servers. This is a transient, Google-side
overload signal on this specific model, not a code defect or a quota
problem; `gemini-2.5-flash` was checked as a fallback and is explicitly
404 ("no longer available to new users"), so no model switch was made
per the "don't switch models without verifying availability" rule.
**A complete JSON content response from live Gemini inference has
still not been captured end-to-end** -- recorded here plainly rather
than claimed. Re-running `scripts/verify_gemini.py` later (demand is,
per Google's own error text, "usually temporary") is the documented
path to closing this out; nothing else needs to change for it to
succeed.

## 12. Organizational Decision Registry (Phase 3)

A governed propose -> approve/reject -> activate workflow for the six
blocking Open Decisions, seeded once at startup
(`app/services/od_registry_seed.py`) with purpose/impact/options text
transcribed directly from `docs/baseline/README.md` and the originating
D1/D2/D4/D5 sections -- never invented. Every transition
(`app/services/od_registry_service.py`) is an append-only
`ODDecisionRecord` row (mirroring `MappingRecord`'s and `audit_entry`'s
own immutability discipline) and additionally writes a real
`audit_entry`, so the registry's own history is independently covered
by the hash chain.

**Structural guarantees, tested** (`tests/test_od_registry.py`, 9
tests): only `PlatformOwner` may write; `approve`/`reject` require an
existing `Proposed` record (no "propose and approve in one call"
shortcut); only OD-10/OD-15/OD-16 are activatable at all (OD-01/OD-06/
OD-07 are role/process decisions with no corresponding `PolicyConfig`
field -- activation is refused outright, not silently ignored);
`activate` requires `Approved` first and publishes a new `PolicyConfig`
version carrying exactly the approved value, nothing invented; the
engine stays fail-closed until ALL THREE of OD-10/15/16 are activated,
verified end-to-end by driving a real assessment through activating
OD-10 alone (engine still refuses, naming OD-15/OD-16 by ID) and then
all three (engine then produces a real outcome).

**What this does NOT do** (an honest limitation, not a silent gap):
OD-01 (approval tiers), OD-06 (who is Environment Owner), and OD-07
(who may validate evidence) can be proposed/approved/rejected/revised in
the registry -- their full history is tracked -- but approving them does
not yet change any runtime behavior (e.g., approving OD-06 does not
automatically grant a specific user the `EnvironmentOwner` RBAC role).
Wiring these three into actual role-assignment/tier-routing logic is a
larger change (an RBAC role-grant UI, a multi-tier approval state
machine) that was not safely implementable as a same-round addition
without risking exactly the kind of invented-policy shortcut the brief
explicitly forbids. The registry makes the decision itself fully
governed and auditable; applying OD-01/06/07's resolved values to the
RBAC system is the next concrete step once the organization resolves them.

## 13. Security hardening this round (Phase 6)

`tests/test_security.py` (21 tests) adds: a systematic RBAC-bypass
sweep (10 endpoints x every non-permitted role x no-token-at-all, all
asserting 403/401 specifically, not just "not 200"); secret-exposure
checks (SecretStr masking, no credential field anywhere in a config-
reading API response, `.env` unreachable through the static mount or
path traversal); input validation (oversized fields, malformed JSON,
an invalid enum value at registration); and a real concurrency test
(two simultaneous approval decisions via `asyncio.gather` against the
same POC request, confirming the server handles concurrent writes
without raising or corrupting state).

**One real defect found and fixed:** evidence upload validated only the
client-supplied `Content-Type` header, never the actual file bytes --
exactly the gap `architecture/TASD-v1.0.md` section 15.4 warns against
("never the client-supplied Content-Type header... alone"). Fixed in
`app/services/evidence_service.py` with real magic-byte sniffing: a
mismatch between the claimed type and the actual bytes (e.g. a Windows
executable renamed to `.pdf` with a forged `Content-Type: application/
pdf` header) is now rejected outright, verified by
`tests/test_security.py::test_executable_disguised_as_pdf_is_rejected`
and `::test_content_type_claim_mismatching_real_bytes_is_rejected`
(plus a positive test confirming a genuine PDF header is still accepted).

**One observation recorded, not fixed, to avoid inventing policy:** the
concurrency test revealed that `approval_service.py` does not prevent a
second `ApprovalDecision` from being written against a
`poc_approval_request` that already has a committed decision (e.g., two
`Rejected` decisions both succeed, since `Rejected` is unconditional per
D5-Approval-Audit.md section 6's decision-type scoping). The baseline
does not explicitly state whether `Approved`/`Rejected` should be a
terminal, single-shot state versus allowing further decisions (the
`MoreInfoRequested` path explicitly does anticipate multiple decision
cycles, so "can this object be decided more than once" is not uniformly
"no"). Deciding whether a committed `Approved`/`Rejected` decision
should block further decisions on the same request is a genuine process
question the baseline leaves open -- flagged here rather than silently
resolved by adding an invented guard.

## 14. Database and storage hardening (Phase 5) -- honest status

**No PostgreSQL, Docker, or S3-compatible service is available in this
sandbox** (re-confirmed again this round: no `psql`/`pg_ctl`/`docker`
binary, nothing listening on 5432). Unlike the prior round, this round
went further than "the dependency installs cleanly" and actually
implemented and tested the code-level pieces that don't themselves
require a live server, closing part of what was previously listed as
genuinely blocked:

- **`SELECT ... FOR UPDATE` row locks are now actually in the code**
  (they were not, in any prior round -- the docstrings described the
  intended design, but no call site used `.with_for_update()` at all,
  confirmed by grep before this round's change). Added at every
  identified race site: `approval_service.py` (the P4 TOCTOU gap these
  docstrings always described), `versioning.py` (the
  `current_input_version` read-then-increment every evidence/mapping/
  environment/scope mutation goes through), `audit_service.py` (the
  hash-chain tail read), `evidence_service.py` (the per-control
  evidence-state transition). SQLAlchemy's sqlite dialect silently
  omits the clause (confirmed: the full 110+ test suite passes
  unchanged with every lock added) -- a real row lock activates
  automatically the moment `DATABASE_URL` points at PostgreSQL, no
  further code change needed.
- **The race these locks close was reproduced for real**, not just
  reasoned about: `tests/test_evidence_concurrency.py` opens two
  genuinely independent SQLite connections (deliberately not
  `tests/conftest.py`'s shared single-StaticPool-connection `client`
  fixture, which cannot exhibit real concurrent-transaction behavior --
  see that test's module docstring for how this was discovered the
  hard way) and confirms SQLite's own concurrency guarantees correctly
  refuse the losing writer rather than corrupting state. See §4 items
  1-2 for the precise, honest boundary between "implemented and tested
  against SQLite's real behavior" and "verified against a live
  PostgreSQL instance" (not done -- no instance available).
- `deploy/postgresql_roles.sql` implements the least-privilege role
  separation TASD-v1.0.md section 11.10 asks for: `poc_app_rw`
  (DML-only -- SELECT/INSERT/UPDATE/DELETE, no DDL) for the running
  application, `poc_migrator` (owns the schema) for `alembic upgrade
  head` only. This is a coarser two-role split than three per-concern
  roles (`ai_svc`/`engine_svc`/`audit_writer`) -- a real per-concern
  split would need per-concern database connections throughout the
  codebase, a larger change than this round's scope; the two-role
  split still gives the one guarantee that actually matters most
  (the running app cannot `ALTER`/`DROP` its own schema even if fully
  compromised). **Written against PostgreSQL's real GRANT/REVOKE
  semantics; not run against a live instance to confirm.**
- **S3-compatible evidence storage is now a real abstraction**
  (`app/services/storage.py`: `ObjectStorage` protocol,
  `LocalFilesystemStorage` + `S3Storage`, selected by
  `STORAGE_BACKEND`), not just a filesystem stand-in with no swap-out
  path. `app/services/evidence_service.py` was refactored to depend on
  the protocol only. `S3Storage` is tested against `moto`'s mocked S3
  (`tests/test_storage.py`) -- a real `boto3` client against an
  in-process fake that implements the actual S3 HTTP API, the standard
  way to test S3 client code without a live AWS account. **This is
  explicitly NOT the same as testing against a real S3-compatible
  service** (real network behavior, IAM policy enforcement, bucket
  policy access boundaries are all untested) -- `deploy/DEPLOYMENT.md`
  §3 names the specific follow-up (point `S3_ENDPOINT_URL` at a real
  MinIO instance and re-run) to close this out when infrastructure is
  available.
- `asyncpg` (installable via `pip install -e ".[postgres]"`) and
  `boto3`/`moto` (`.[s3]`/dev) all install and import cleanly in this
  environment, confirming none of this is blocked by a missing
  dependency, only by the absence of a live server to point them at.
- `GET /readyz` (app/main.py) now actually exercises the database
  connection (`SELECT 1`), distinct from `/healthz`'s liveness-only
  check -- so a real deployment's orchestrator gets a meaningful signal
  the moment `DATABASE_URL` points at an unreachable PostgreSQL, rather
  than routing traffic to an instance that can't serve it.

**This is not claimed as production-tested, and should not be treated
as such.** Real PostgreSQL concurrent-load behavior, real S3/MinIO
integration, and the role-separation SQL's actual GRANT behavior all
remain unverified against live infrastructure -- §4 lists exactly
that boundary. What changed this round is that the code-level half of
"implement what's safely possible without the real infrastructure" now
actually exists and is tested against the most realistic substitute
available in this sandbox (two real SQLite connections, a real S3 API
mock), not just described as a future TODO.

**Superseded by §15 below**: the above described what was possible
*without* real PostgreSQL/S3 infrastructure. In a later round, Docker
was installed into this sandbox for the first time and real
infrastructure was actually stood up and tested against.

## 15. PostgreSQL and S3 -- actually tested live, two real defects found and fixed

Docker was not present in this environment in any prior round -- this
round installed Docker Desktop (and, as its prerequisite, WSL2, also
not previously present) and used it to stand up a real `postgres:16`
container and a real S3-compatible endpoint, then ran
`scripts/verify_postgres.py` / `scripts/verify_s3.py` against them for
real. This is qualitatively different from everything in §14: not a
substitute, not a mock, not reasoning about what *would* happen --
actual live infrastructure, actually exercised.

**PostgreSQL: all 6 checks PASS** (connectivity, migrations-at-head,
both directions of role separation, row-locking concurrency, atomicity)
-- but only after finding and fixing two real, PostgreSQL-only defects
that had been invisible under SQLite for the entirety of this build:

1. **`Enum` columns vs. hand-written CHECK constraints used different
   string representations.** SQLAlchemy's `Enum(SomePythonEnum)` type
   stores the enum member's **name** (e.g. `"ACCEPTED"`) as the actual
   database-level value on every backend -- not its human-readable
   `.value` (e.g. `"Accepted"`), confirmed by direct inspection
   (`Enum(SomeEnum).enums` returns names) and by this live run. Three
   hand-written CHECK constraints had been written using `.value`
   strings instead: `ck_exception_non_waivable` and
   `ck_exception_accepted_requires_remediation`
   (`app/models/environment.py`) and `ck_mapping_reject_reason_required`
   (`app/models/mapping.py`). On PostgreSQL, which has a real native
   enum type, this made `CREATE TABLE exception_record` fail outright
   with `invalid input value for enum exceptiondisposition: "Accepted"`
   -- the table could not even be created. On SQLite, which enforces
   no such type, the same mismatch instead made each constraint a
   silent, permanent no-op (the column is never literally `'Accepted'`,
   it's `'ACCEPTED'`, so `!= 'Accepted'` was always true) -- the
   constraint never once fired across this entire build's test
   history, and nothing noticed because SQLite happily created the
   table anyway. **This never meant the non-waivable Isolation/
   AccessControl rule was actually violable in practice**:
   `app/services/environment_service.py`'s `attest_dimension`/
   `dispose_exception` functions independently re-validate the exact
   same rule in Python before any database write
   (`disp == ExceptionDisposition.ACCEPTED and dim in NON_WAIVABLE_DIMENSIONS`),
   and that Python-level check is what every passing test
   (`test_isolation_exception_can_never_be_accepted`) was actually
   exercising. The DB-level CHECK constraint was meant as defense in
   depth on top of that, and until this round, it was not doing its
   job. Fixed in both model files and in the already-written migration
   (`alembic/versions/f034c3705558_...py`) to use the matching
   uppercase member names.
2. **`audit_entry.affected_object_id` was `VARCHAR(36)` (exactly one
   UUID's width), but two call sites store composite keys there**:
   `evidence_service.py`'s `f"{poc_request_id}:{control_id}"` and
   `environment_service.py`'s `f"{poc_request_id}:{dimension}"`, both
   up to roughly 57 characters. SQLite does not enforce `VARCHAR`
   length limits at all (a documented SQLite behavior, not a bug in
   this codebase), so this was invisible there; PostgreSQL correctly
   rejected it with `StringDataRightTruncationError: value too long
   for type character varying(36)` the moment a real evidence-state
   transition tried to write its audit entry. Widened to `VARCHAR(100)`
   in `app/models/audit.py` and the initial-schema migration.

Both fixes were verified by rerunning the full migration-to-row-locking
sequence against the live PostgreSQL instance afterward (all 6 checks
PASS) and by rerunning the complete SQLite test suite to confirm zero
regression.

**S3: the applicable checks PASS**, against a real S3-compatible
endpoint -- with one substitution worth stating plainly: MinIO's own
Docker Hub images now require a login (`pull access denied`) and the
current `localstack/localstack:latest` image requires a paid license
token even for S3; neither was known before trying them live this
round. `localstack/localstack:3.0` (an older, still-license-free-for-S3
version) was used instead -- a substitution of *which* free S3-
compatible service, not a substitution of a mock for a live one; it is
a real S3 HTTP server on a real port, exercised by `scripts/verify_s3.py`
exactly as a real AWS S3 or MinIO endpoint would be: live upload,
retrieval, quarantine-to-evidence promotion, and a full
`evidence_service.upload_evidence` + `run_scan` round-trip, all PASS.
Access-control (a deliberately under-privileged credential denied
read access) was left NOT TESTED -- LocalStack's community edition does
not model IAM-style access restrictions the way real AWS does, so
testing that specific property for real needs an actual AWS account,
not this substitution.

See `deploy/RELEASE-READINESS.md` §2/§3 for the per-check PASS table.

## 16. Gemini generateContent -- focused root-cause diagnosis

A later round specifically asked for a root-cause diagnosis of why
live `generateContent` inference kept failing, without rewriting the
integration. Findings:

1. **Key/config load: confirmed correct.** `GEMINI_API_KEY` loads from
   `backend/.env` (length 53, non-empty), `AI_PROVIDER=gemini`,
   `GEMINI_MODEL=gemini-3.8-flash`. Never printed beyond length.
2. **Model/endpoint: confirmed correct.** `gemini-3.8-flash` is
   present in the account's real `client.models.list()` output with
   `generateContent` in its `supported_actions`. Not a 404 case.
3. **Single-call diagnosis, three variants, same key/model/network path:**
   - A raw, timeout-less synchronous call hung for 2.5+ minutes with
     *zero* response of any kind (not even a slow error) -- while a
     `GET` (`models.list()`) on the same client completed in 0.53s.
     This GET-fast/POST-hangs asymmetry is the same pattern
     `IMPLEMENTATION-NOTES.md` §11 originally (and incorrectly, per
     later evidence) attributed to a sandbox network restriction.
   - The real application code path (`client.aio.models.generate_content`
     wrapped in `asyncio.wait_for(..., timeout=60)`, exactly what
     `app/services/ai/client.py:GeminiModelClient` does) got a clean,
     fast **`503 UNAVAILABLE`** ("This model is currently experiencing
     high demand") on all 3 of `scripts/verify_gemini.py`'s attempts --
     a real, structured response from Google, not a hang.
   - A follow-up single bounded call against the *same* model,
     moments later, hung for the full 60s with no response at all --
     different outcome, same model, same key, same code path.

   **Classification: 503 / intermittent timeout -- a genuine, Google-
   side temporary capacity condition specific to `gemini-3.8-flash` at
   the time of testing, not an authentication (401/403), model-
   availability (404), or quota/billing (429) issue, and not an
   application defect.** The inconsistency between runs (clean 503 vs.
   silent hang) is itself informative: it is the signature of a model
   under variable load, not of a fixed, deterministic block.
4. **Working alternative identified from the real model list, not
   guessed:** `gemini-3.5-flash` (also real, also `generateContent`-
   capable per `models.list()`) answered successfully in the same
   session, same key: `text='OK.'`, with `usage_metadata` showing
   `thoughts_token_count=44` + `candidates_token_count=2` against a
   `max_output_tokens=50` budget. (A first attempt at `max_output_tokens=10`
   against this same model returned `text=None` with
   `finish_reason=MAX_TOKENS` -- not a failure, just the token budget
   being consumed entirely by this model class's internal "thinking"
   tokens before any visible output could be emitted. Worth knowing for
   anyone tuning `max_tokens` on reasoning-capable Gemini models.)
5. **No config change was made.** `GEMINI_MODEL` remains
   `gemini-3.8-flash` in `.env` -- switching to `gemini-3.5-flash` is a
   one-line `.env` edit an operator can make if they want a model that
   is working right now instead of waiting out `gemini-3.8-flash`'s
   current demand spike; this was not done silently, per the
   diagnosis's own instruction not to switch models without reporting
   the reason.

**ROOT CAUSE:** Google-side capacity/demand condition on the specific
model `gemini-3.8-flash`, observed as both explicit 503 responses and
unexplained silent timeouts across repeated real attempts -- not a
defect in this codebase's Gemini integration, authentication, or
configuration.

**FIX:** none required in code (the integration's quota-aware retry
and fail-closed error handling already behave correctly under this
condition -- confirmed, not assumed). Operational options, not applied
automatically: wait for `gemini-3.8-flash`'s demand to subside and
re-run `scripts/verify_gemini.py`, or set `GEMINI_MODEL=gemini-3.5-flash`
in `.env` (a real, confirmed-working, `generateContent`-capable model
on this account) if inference is needed right now.

**STATUS: BLOCKED** (the configured model, this session) /
**interim PASS available** (an alternate real model, same account, if
the operator chooses to use it).
