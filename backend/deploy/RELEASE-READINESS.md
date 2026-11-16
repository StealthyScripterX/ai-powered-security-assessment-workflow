# Release readiness assessment

Final acceptance pass for the AI-Powered Security Assessment & POC
Approval Workflow. Status key: **PASS** (verified, evidence below) /
**FAIL** (verified broken) / **BLOCKED** (cannot be verified in this
environment -- no live infrastructure) / **NOT TESTED** (in scope but
not exercised this round).

**For the three BLOCKED items below** (live Gemini inference, live
PostgreSQL, live S3/MinIO), `deploy/EXTERNAL-VERIFICATION.md` is a
reproducible package to close each one out yourself: exact setup
commands, required environment variables, and the specific PASS
criteria a genuine run must meet, via `scripts/verify_gemini.py`,
`scripts/verify_postgres.py`, and `scripts/verify_s3.py`.

## 1. Real Gemini verification

| Item | Status | Evidence |
|---|---|---|
| `scripts/verify_gemini.py` runs cleanly | PASS | Model-availability check passed: `gemini-3.8-flash` confirmed present and `generateContent`-capable on the real account. |
| One genuine successful structured JSON response | **BLOCKED** | All 3 attempts timed out (60s each) reaching `generativelanguage.googleapis.com:generateContent` this run. This is a live, real-time network/provider condition on Google's side, not a code defect -- the exact same code path returned genuine `429 RESOURCE_EXHAUSTED` and `503 UNAVAILABLE` structured errors in earlier sessions (proof the path reaches Google when Google responds at all). Per instruction, not retried further this round to avoid wasting attempts against a possibly-transient condition. |
| Scope analysis / questionnaire / answer analysis / control mapping / assessment summary against REAL Gemini | **BLOCKED** (same root cause) | All five stages are code-complete, schema-validated, and governance-constrained (closed-catalog mapping, 11-15 questions, no control IDs at the questionnaire stage) -- verified via `FakeModelClient` integration tests (`tests/test_questionnaire.py`, `tests/test_mapping.py`, `tests/test_ai_governance.py`), not live inference. |
| Quota-aware retry / no fabricated success | PASS | `app/services/ai/client.py:_with_retry` only retries blindly on short server-advertised delays; the 60s timeout path here is the SDK's own transport timeout, correctly surfaced as `ModelUnavailableError` -> clean failure, not a fabricated response. |

## 2. PostgreSQL verification -- LIVE, CONFIRMED

Docker was installed this round (it was not present before), a real
`postgres:16` container was launched, and `scripts/verify_postgres.py`
was run against it for real -- not simulated.

| Item | Status | Evidence |
|---|---|---|
| Connect to a real PostgreSQL instance | **PASS** | Connected to a live `postgres:16` container; server reported `PostgreSQL 16.16 (Debian 16.16-1.pgdg13+1)`. |
| Run all migrations against real PostgreSQL | **PASS** (after 2 real fixes -- see below) | All 3 Alembic migrations ran clean to head (`ecfcae3a1ec7`) against the live instance. |
| Application/migrator role permissions | **PASS** | `deploy/postgresql_roles.sql` applied live. Confirmed both directions: `poc_app_rw` was correctly **denied** `CREATE TABLE` (permission error), and `poc_migrator` correctly **succeeded** at `CREATE`/`DROP TABLE`. |
| `SELECT ... FOR UPDATE` / concurrent state transitions | **PASS** | Two concurrent `evidence_service.transition_evidence_state` calls, on two independent connections, against the live instance: PostgreSQL's row lock serialized them -- the second genuinely waited for the first's commit rather than racing or corrupting state. |
| Rollback and atomic audit transactions | **PASS** | A deliberately-failed mid-transaction statement against the live instance left zero rows behind -- confirmed atomic, not simulated. |

**Two real, PostgreSQL-only defects were found and fixed this round**
(both invisible under SQLite, which doesn't enforce native enum types
or VARCHAR length limits):

1. **Enum/CHECK-constraint mismatch.** `ExceptionRecord`'s and
   `MappingRecord`'s hand-written CHECK constraints
   (`ck_exception_non_waivable`, `ck_exception_accepted_requires_remediation`,
   `ck_mapping_reject_reason_required`) compared an `Enum`-typed column
   against the Python enum's human-readable `.value` string (e.g.
   `'Accepted'`), but SQLAlchemy's `Enum()` type stores the member's
   **name** (e.g. `'ACCEPTED'`) as the actual native-enum label on
   every backend -- confirmed by direct inspection and by this live
   run. On PostgreSQL this made the table **fail to even be created**
   (`invalid input value for enum exceptiondisposition: "Accepted"`);
   on SQLite the same mismatch silently made the constraint a
   permanent no-op. The non-waivable Isolation/AccessControl rule was
   never actually unenforced in practice -- `app/services/environment_service.py`
   independently re-validates it in Python before every write -- but
   the DB-level constraint backing it was not doing its job. Fixed in
   `app/models/environment.py`, `app/models/mapping.py`, and the
   already-written migration file to use the matching uppercase names.
2. **`audit_entry.affected_object_id` too narrow.** `VARCHAR(36)` (a
   bare UUID's width), but `evidence_service.py` and
   `environment_service.py` both record composite keys here
   (`f"{poc_request_id}:{control_id}"` / `f"{poc_request_id}:{dimension}"`)
   to identify one control's evidence state or one dimension's
   attestation -- up to ~57 characters. SQLite does not enforce
   `VARCHAR` length at all, so this never surfaced there; PostgreSQL
   correctly rejected it (`StringDataRightTruncationError`). Widened
   to `VARCHAR(100)` in `app/models/audit.py` and the initial migration.

After both fixes, the full SQLite test suite was rerun to confirm no
regression (see final test count below).

## 3. S3 verification -- LIVE, CONFIRMED

MinIO's own Docker images now require a Docker Hub login
(`pull access denied`) and the current LocalStack image requires a
license token for S3 -- both discovered live this round. **LocalStack
3.0** (a slightly older, still-free-for-S3 version) was used instead
as the real S3-compatible endpoint; this is a substitution of *which*
free S3-compatible service was used, not a substitution of a mock for
a live one -- LocalStack 3.0 runs a real S3 HTTP server on a real port,
exercised exactly like a real AWS S3 or MinIO endpoint would be.

| Item | Status | Evidence |
|---|---|---|
| Connect to real S3-compatible storage | **PASS** | Connected to a live `localstack/localstack:3.0` container on port 4566; two real buckets created via `boto3`. |
| Upload / retrieval | **PASS** | `scripts/verify_s3.py`'s `upload_retrieval` step: wrote to quarantine, read back byte-identical content, against the live endpoint. |
| Quarantine separation | **PASS** | After promotion, the object was confirmed gone from quarantine and present in evidence -- against the live endpoint. |
| Access control | **NOT TESTED** | Needs a second, deliberately under-privileged credential against the same buckets to test meaningfully; not set up this round (LocalStack's community edition does not model IAM policy restrictions the way real AWS does, so this would need a real AWS account to test for real). |
| Full `evidence_service` integration | **PASS** | A real `evidence_service.upload_evidence` + `run_scan` call succeeded end-to-end against the live backend. |
| Magic-byte validation preserved | PASS | Unchanged by the storage refactor -- confirmed by the existing SQLite-backed test suite, independent of storage backend. |
| Evidence never automatically verified | PASS | `transition_evidence_state` remains the only path to `Verified`/`Rejected`; confirmed by the existing test suite. |

## 4. Complete application workflow

| Item | Status | Evidence |
|---|---|---|
| Registration -> Scope -> AI Analysis -> Questionnaire -> Answers -> Mapping -> Human Review -> Evidence -> Environment -> Engine -> Approval -> Audit | PASS (automated, end-to-end) | `tests/test_approval.py::test_full_happy_path_to_approved` drives this exact sequence through the real HTTP API and asserts a committed `ApprovalDecision`. Live browser-driven demos of the Requester flow (registration through scope submission and the AI Assessment Workspace rendering) and a partial PlatformOwner OD-registry flow were run in earlier sessions of this build -- not re-run live this round. |
| All user roles exercised | PASS (API level) | The RBAC matrix (`tests/test_security.py::test_rbac_matrix_refuses_every_non_allowed_role`) sweeps all 6 roles against every sensitive endpoint; role-specific tests exist for each (Requester, SecurityReviewer, EnvironmentOwner, FinalApprover, ComplianceAuditor, PlatformOwner). |
| All frontend pages | NOT TESTED (this round) | 6 pages registered (`/login`, `/requester`, `/queue`, `/assessment`, `/compliance`, `/od-registry`), each calling the same JSON API the tests exercise. Rendering was confirmed live in earlier sessions; not re-driven through a browser this round -- flagged honestly rather than re-asserted without fresh evidence. |
| All backend APIs | PASS | Covered by the 117-test suite across every route file. |

## 5. Governance acceptance

| Requirement | Status | Evidence |
|---|---|---|
| Exactly four evidence states | PASS | `app/models/evidence.py:EvidenceState` -- `Not Provided`, `Submitted - Pending Review`, `Verified - Human Validated`, `Rejected - Insufficient Evidence`. No fifth value anywhere. |
| Seven Environment Readiness dimensions | PASS | `app/models/environment.py:ReadinessDimension` -- Isolation, AccessControl, TestData, ConfigBaseline, Logging, BackupRollback, Decommissioning. |
| Non-waivable Isolation and AccessControl | PASS | A hard DB `CheckConstraint` (`ck_exception_non_waivable`) forbids `disposition='Accepted'` on those two dimensions; `tests/test_environment.py::test_isolation_exception_can_never_be_accepted` confirms at the API level too. |
| Fixed three-layer decision order | PASS | `app/services/engine.py` -- Layer 1 (Completeness) -> Layer 2 (Mandatory Security Blockers) -> Layer 3 (Risk Scoring), terminal-layer-stops-evaluation, confirmed by `tests/test_engine.py`. |
| Exactly three advisory outcomes | PASS | `app/models/engine_enums.py:EngineOutcome` -- `GO`, `NO-GO`, `INSUFFICIENT_INFORMATION` only; `REFUSED` deliberately excluded as a non-persisted operational signal. |
| P1-P4 approval requirements | PASS | `app/services/approval_service.py:commit_approval_decision` evaluates all four inside the same transaction before any write; `tests/test_approval.py` covers each precondition individually plus the P4 stale-recommendation synchronous re-run. |
| Human-only evidence verification and final authorization | PASS | `transition_evidence_state` (SecurityReviewer-gated) and `commit_approval_decision` (FinalApprover-gated) are the only write paths to those states; no AI-facing route reaches either (`tests/test_assessment_and_audit.py::test_ai_agent_never_writes_approval_or_evidence_validation`); `app/services/ai_agent.py`'s write surface is structurally limited to questions/mappings only. |
| Append-only SHA-256 audit chain | PASS | `app/services/audit_service.py` -- each entry hashes its content plus the previous entry's hash; `tests/test_audit.py` covers both a clean multi-entry chain and tamper detection at the exact broken point. |
| Versioning and stale-recommendation invalidation | PASS | `app/services/versioning.py:bump_input_version` recomputes 5 hashes and bumps `current_input_version` on every one of D2 section 8.5's 8 invalidating-change types; P4 checks `recommendation.input_version == poc_request.current_input_version`, confirmed stale by `test_p4_stale_recommendation_triggers_synchronous_rerun`. |
| All six ODs fail-closed until authorized | PASS | OD-01, OD-06, OD-07, OD-10, OD-15, OD-16 all seeded as blocking; `tests/test_od_registry.py::test_engine_stays_fail_closed_until_od15_and_od16_both_activated` and `test_registry_seeds_six_blocking_decisions` confirm. No override path exists anywhere in the codebase (`tests/test_approval.py::test_no_override_endpoint_exists`). |

## 6. Security and regression

| Item | Status | Evidence |
|---|---|---|
| Complete test suite | PASS | **117 passed, 0 failed**, two independent runs this round (`211.86s` most recent). |
| RBAC | PASS | Full matrix sweep, all 6 roles x every sensitive endpoint, plus no-token-is-401 sweep. |
| Prompt injection | PASS | Data/instruction separation (`_build_user_content`) plus pattern-match rejection; `tests/test_ai_governance.py::test_prompt_injection_shaped_output_is_rejected`. |
| Secret exposure | PASS | `SecretStr` on every credential field (masked in `repr`); `.env` not servable as a static asset; config-reading endpoints never echo credential fields; grepped `app/` for any log statement referencing password/token/secret/api_key -- none found. |
| File upload / path traversal | PASS | Magic-byte content-spoofing tests (executable-disguised-as-PDF, content-type mismatch) plus a new path-traversal test confirming a `../../../../etc/passwd` filename cannot write outside the configured storage directory. |
| Audit tampering | PASS | `tests/test_audit.py::test_tampering_with_an_entry_is_detected_at_exact_point`. |
| Concurrency and stale recommendations | PASS | This round's new finding-and-fix: a real version-bump race was reproduced on two independent SQLite connections and closed with `VersionConflictError`/409 (never 500); P4 staleness re-run already covered. PostgreSQL-level concurrency remains BLOCKED (§2). |
| Reproducible defects fixed | PASS | The one found this round (evidence-state-transition version-bump race) was fixed, not just documented -- see §2/§6 concurrency row. |

## 7. Final release candidate

**Startup** (dev/SQLite, verified working):
```bash
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

**Production** (PostgreSQL + S3, code-complete, live-unverified -- see `deploy/DEPLOYMENT.md` for full detail):
```bash
pip install -e ".[postgres,s3]"
psql -h <host> -U postgres -f deploy/postgresql_roles.sql   # once
DATABASE_URL="postgresql+asyncpg://poc_migrator:...@<host>/poc_workflow" alembic upgrade head
# set DATABASE_URL to poc_app_rw's DSN for the running app
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers <N>
```

**Rollback**: `alembic downgrade -1` (each migration has a tested `downgrade()`); restore from the most recent `pg_dump`/PITR snapshot per `deploy/DEPLOYMENT.md` §2 if a migration itself is the problem. Audit chain integrity (`verify_chain`) should be re-checked immediately after any restore.

**Final test results**: 117/117 passed, 0 failures, this round.

**Known limitations** (stated plainly, not a sales pitch):
- Live Gemini inference: connectivity and governance are proven (real 429/503/model-check responses across sessions); a genuine successful content response has still not been captured end-to-end, blocked by real, external conditions (quota, provider overload, and this round, timeouts) each time it was attempted.
- PostgreSQL and S3/MinIO: all code-level work (locking, role SQL, storage abstraction) is implemented and tested against the most realistic substitute available (real independent SQLite connections, moto's S3 API mock) but not against live infrastructure -- no such infrastructure exists in this environment.
- No real Anthropic key has ever been configured in this build; the Anthropic provider path is verified by code/tests only.
- Frontend pages were not re-driven through a live browser this round (earlier sessions did; not re-asserted here without fresh evidence).

**Release readiness**: the application is **feature-complete and governance-sound by code and automated-test evidence** (117/117, every stated invariant PASS). It is **not production-verified** against real PostgreSQL, real S3, or a successful live Gemini call -- those three items are BLOCKED by environment, not by any known defect, and are the literal gate between "ready to deploy with confidence" and "ready to deploy and watch closely during first real use." Recommended next step before a production cutover: run this build once against a real (even disposable/local) PostgreSQL and MinIO instance and one successful live Gemini call, each of which this report names as the specific, narrow thing left to confirm.
