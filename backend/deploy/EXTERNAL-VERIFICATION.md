# External verification package

A reproducible, run-it-yourself package for the live infrastructure
checks `deploy/RELEASE-READINESS.md` tracks. **PostgreSQL and S3 have
since been run live** (Docker was installed into this environment and
used to stand up a real `postgres:16` container and a real
`localstack:3.0` S3-compatible endpoint -- see
`IMPLEMENTATION-NOTES.md` §15 for the two real defects that run found
and fixed); **Gemini structured inference remains BLOCKED** (real
timeouts/quota each time it was attempted). Each section below gives
exact setup commands, required environment variables, prerequisites,
and the specific PASS criteria a genuine run must meet -- useful both
as a record of what was actually done and to re-run any of the three
again later (a different Postgres/S3 target, a fresh Gemini attempt).

**No external service is treated as verified until one of these
scripts has actually been run against it and reported PASS.** A mock
(moto's simulated S3, for instance) is not a substitute for this and
is never described as one anywhere in this codebase.

**Secrets**: every command below keeps credentials in your own shell
environment or a local `.env` you create and never commit. None of the
three scripts print a credential, DSN, or access key under any
circumstance -- confirmed by reading their source
(`scripts/verify_postgres.py`, `scripts/verify_s3.py`,
`scripts/verify_gemini.py`) and by deliberately triggering their error
paths with throwaway fake credentials during development.

---

## 1. Gemini structured inference

**Prerequisites**: a `GEMINI_API_KEY` with quota available right now
(the free tier's 20-requests/day cap and per-minute rate limit are
real; if you've been testing today, wait for the reset window Google's
own error message reports).

**Setup**:
```bash
# backend/.env (or your shell environment) -- NOT committed:
AI_PROVIDER=gemini
GEMINI_API_KEY=<your real key>
GEMINI_MODEL=gemini-3.8-flash
```

**Run**:
```bash
cd backend
python scripts/verify_gemini.py
```

**PASS criteria**: exit code `0` and a line reading
`[2/2] SUCCESS -- live Gemini inference confirmed. Response: {...}`
with an actual parsed JSON object in it. Exit code `1`
(`BLOCKED (transient/quota)`) means a real condition from Google, not
a failure of this criterion -- re-run later; exit code `2` means a
configuration/code problem to fix first.

**Do not** interpret a `429`/`503`/timeout as success, and do not loop
retrying it rapidly -- the script already makes exactly one inline
attempt (through the app's own quota-aware retry wrapper) per run, by
design.

**Once PASS is captured**, optionally extend coverage to the other
four AI stages (questionnaire generation exactly 11-15 questions,
answer analysis, catalog-constrained control mapping, assessment
summary) the same way the original live demo did: register a
Requester account through the running app (`uvicorn app.main:app`),
submit a scope through `/requester`, and click "Analyze scope &
generate questions" on the resulting `/assessment?id=...` page -- the
same real endpoint `scripts/verify_gemini.py` exercises directly.

---

## 2. PostgreSQL: migrations, roles, locking, concurrency

**Prerequisites**: a real PostgreSQL 16 instance you can create roles
and databases on. Fastest path if you have Docker:
```bash
docker run -d --name verify-pg -e POSTGRES_PASSWORD=postgres -p 5432:5432 postgres:16
```
(Any other real Postgres -- a local install, a disposable cloud
instance -- works identically; this is the one step this package
cannot do for you, since it requires a server to exist somewhere.)

**Setup**:
```bash
cd backend
pip install -e ".[postgres]"

# Edit the two placeholder passwords in deploy/postgresql_roles.sql first.
psql -h localhost -U postgres -f deploy/postgresql_roles.sql

export DATABASE_URL="postgresql+asyncpg://poc_app_rw:<app_password>@localhost:5432/poc_workflow"
export MIGRATOR_DATABASE_URL="postgresql+asyncpg://poc_migrator:<migrator_password>@localhost:5432/poc_workflow"

# Run migrations as the migrator role (never as the app role):
DATABASE_URL="postgresql+asyncpg://poc_migrator:<migrator_password>@localhost:5432/poc_workflow" alembic upgrade head
```

**Run**:
```bash
python scripts/verify_postgres.py
```

**PASS criteria** (printed per-step, plus a final summary table):

| Step | PASS means |
|---|---|
| `connectivity` | connects and prints the server version |
| `migrations` | `alembic_version` exists and is non-empty |
| `role_separation(app=DDL)` | the app role's `CREATE TABLE` attempt is correctly **denied** (a PASS here is a denial, not a success) |
| `role_separation(migrator=DDL)` | the migrator role's `CREATE`/`DROP TABLE` succeeds (only runs if `MIGRATOR_DATABASE_URL` is set) |
| `row_locking` | exactly one of two concurrent evidence-state transitions commits and the other gets a clean conflict refusal, OR both commit sequentially without error -- never both failing, never a corrupted/third state |
| `atomicity` | a deliberately-failed transaction leaves zero rows behind -- confirms real commit/rollback atomicity on PostgreSQL, the same guarantee already tested on SQLite |

Script exit code `0` only if every step is `PASS` or `NOT TESTED`
(the migrator-role check is `NOT TESTED`, not failed, if you choose
not to set `MIGRATOR_DATABASE_URL`).

**Cleanup**: the script's seeded verification rows (a throwaway
Requester/SecurityReviewer user and one PocRequest) are harmless test
data -- drop and recreate the database, or just leave the `poc_workflow`
database for repeated runs; nothing it creates needs manual cleanup.

---

## 3. S3 / MinIO: upload, retrieval, quarantine, access control

**Prerequisites**: a real S3-compatible endpoint.

**MinIO's official Docker Hub image now requires a Docker Hub login**
(`docker run ... minio/minio` fails with `pull access denied` as of
this writing -- confirmed live, not assumed), and the current
`localstack/localstack:latest` image requires a paid license token
even for S3 (`License activation failed`, also confirmed live). The
path that actually worked, verified live this round:

```bash
docker run -d --name verify-localstack -p 4566:4566 -e SERVICES=s3 localstack/localstack:3.0
```
(`3.0` is an older LocalStack release that still runs S3 without a
license token. If MinIO's login requirement has since changed, or you
have Docker Hub credentials, `docker login` then the `minio/minio`
command from this file's git history works identically -- the app
code doesn't care which S3-compatible backend it talks to.)

Then create the two buckets (LocalStack has no web console by default;
use `boto3` or the `aws` CLI pointed at `--endpoint-url http://localhost:4566`):
```bash
python -c "
import boto3
c = boto3.client('s3', endpoint_url='http://localhost:4566', region_name='us-east-1', aws_access_key_id='test', aws_secret_access_key='test')
c.create_bucket(Bucket='verify-quarantine')
c.create_bucket(Bucket='verify-evidence')
"
```

**Setup**:
```bash
cd backend
pip install -e ".[s3]"

export STORAGE_BACKEND=s3
export S3_QUARANTINE_BUCKET=verify-quarantine
export S3_EVIDENCE_BUCKET=verify-evidence
export S3_ENDPOINT_URL=http://localhost:4566   # blank for real AWS S3; :9000 for MinIO
export S3_REGION=us-east-1
export AWS_ACCESS_KEY_ID=test                  # LocalStack accepts any value; your real key for AWS/MinIO
export AWS_SECRET_ACCESS_KEY=test              # same
```

**Run**:
```bash
python scripts/verify_s3.py
```

**PASS criteria**:

| Step | PASS means |
|---|---|
| `config` | `STORAGE_BACKEND=s3` and both buckets configured |
| `upload_retrieval` | bytes written to quarantine read back identical |
| `quarantine_separation` | after promotion, the object is gone from quarantine (never readable from both buckets at once) |
| `access_control` | **optional** -- only runs if you set `S3_READONLY_ACCESS_KEY_ID`/`S3_READONLY_SECRET_ACCESS_KEY` to a second, deliberately under-privileged credential against the same buckets; PASS means that credential is denied read access to quarantine. Without it, this step reports `NOT TESTED`, not assumed. |
| `evidence_service_integration` | a real `evidence_service.upload_evidence` + `run_scan` call (the app's actual code, not a hand-rolled S3 client) succeeds end-to-end against this backend |

Script exit code `0` only if every step is `PASS` or `NOT TESTED`.

This script's own logic was exercised against `moto`'s mocked S3 during
development (confirmed all 4 applicable checks PASS there) -- that
confirms the script is correct, **not** that live S3/MinIO has been
verified. Only a run against the real endpoint above satisfies that.

---

## 4. Browser-based smoke-test checklist (all frontend roles)

Start the app first: `uvicorn app.main:app --reload`, then open
`http://localhost:8000/login` in a browser for each role below. Each
role needs its own registered account (the "Create an account" card
on the login page; pick the matching role from the dropdown).

### Requester
1. Register + log in. Land on `/requester`.
2. Submit a scope (project description, systems in scope, business
   justification) -> a new assessment appears in "My assessments" and
   opens `/assessment?id=<id>`.
3. On the assessment page, confirm the scope fields are tagged
   `REQUESTER_FACT` and the stepper shows Scope -> Questions -> Answers
   -> Mapping -> Evidence -> Environment -> Recommendation -> Approval.
4. Click "Analyze scope & generate questions" -- expect either a real
   AI-generated question set (if Gemini/Anthropic is configured and
   available) or a clear 503/502 error, never a silently blank result.
5. Upload an evidence file against a control -- expect it to land as
   `Submitted - Pending Review`, never auto-Verified.

### SecurityReviewer
1. Register + log in. Land on `/queue` -- confirm the Requester's
   assessment from above is listed.
2. Open it, go to the Evidence step, Verify or Reject the uploaded
   evidence -- confirm a rationale is required to Reject.
3. Go to the Mapping step, Confirm/Adjust/Reject an AI-proposed
   mapping (if one exists) -- confirm Confirm/Adjust creates a new row
   rather than editing the AI's original.

### EnvironmentOwner
1. Register + log in. Open the same assessment via `/queue`.
2. Attest each of the 7 dimensions (Isolation, AccessControl, TestData,
   ConfigBaseline, Logging, BackupRollback, Decommissioning).
3. Confirm Isolation and AccessControl have NO "accept exception"
   option anywhere in the UI (they are structurally non-waivable).
4. Confirm the overall sign-off only shows true once every dimension
   is Attested (or has a non-Isolation/AccessControl exception
   accepted with a remediation owner and deadline).

### FinalApprover
1. Register + log in. Open the assessment once a recommendation exists
   (requires the Decision Engine to have run -- needs OD-10/OD-15/OD-16
   configured via the PlatformOwner first, see below).
2. Confirm the Approval step shows the engine's GO/NO-GO/
   Insufficient-Information recommendation and its rationale.
3. Attempt to Approve against a NO-GO/Insufficient-Information
   recommendation -- confirm a disagreement rationale is required and
   must differ from the main rationale.
4. Confirm there is no "override" button or hidden admin path anywhere
   that bypasses this.

### ComplianceAuditor
1. Register + log in. Open `/compliance`.
2. Confirm the audit trail list loads and "Verify chain" reports a
   clean hash chain.
3. Confirm this role cannot reach any write action (Verify evidence,
   Approve, attest environment) -- only read-only screens.

### PlatformOwner
1. Register + log in. Open `/od-registry`.
2. Confirm all six Open Decisions (OD-01, OD-06, OD-07, OD-10, OD-15,
   OD-16) are listed and, on a fresh database, in an unauthorized/
   blocking state.
3. Propose and Approve a value for OD-10 (or OD-15/OD-16) -- confirm
   the Decision Engine's behavior changes only after Activation, never
   after Propose or Approve alone.
4. Confirm no action anywhere lets a non-PlatformOwner reach this page
   or its endpoints (expect a 403/redirect for other roles).

**Record, for each role**: pass/fail per step above, and the exact
browser console/network error text for anything that didn't behave as
described -- that is the evidence this checklist produces.
