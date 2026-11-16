# 🛡️ AI-Powered Security Assessment & POC Approval Workflow

A governance-first platform that lets an organization run security
assessments for Proof-of-Concept (POC) requests — from scope intake to
AI-assisted analysis, human evidence review, environment readiness, a
deterministic decision engine, and a final human-only approval — with
a tamper-evident audit trail backing every single step.

Built to answer one question honestly: **can an AI safely assist a
security review without ever being allowed to approve one?**

---

## 🎯 What this actually does

A **Requester** submits what they want to test (a new SaaS tool, a
vendor integration, a quick prototype). From there, the platform runs
the request through a full governance pipeline:

```
Scope Submission → AI Scope Analysis → Questionnaire (11-15 Qs)
→ Requester Answers → AI Control Mapping (ISO 27001 / NIST 800-53)
→ Human Evidence Review → Environment Readiness (7 dimensions)
→ 3-Layer Decision Engine → Human-Only Final Approval → Audit Trail
```

Six distinct roles (Requester, Security Reviewer, Environment Owner,
Final Approver, Compliance Auditor, Platform Owner) each see exactly
what their job needs — server-enforced, not just hidden in the UI.

## 🤖 Where AI fits in (and where it's deliberately locked out)

AI (Gemini or Anthropic, pick your provider) drafts:
- Scope gaps and assumptions
- A scoped questionnaire (always exactly 11–15 questions, governance
  domains enforced server-side, not just prompted for)
- Draft control mappings against a **closed catalog** — the model can
  never invent an ISO/NIST control ID that doesn't already exist in
  the system; any attempt is rejected, not silently corrected

AI **cannot**, by construction (not by prompt, by code path):
- Verify evidence
- Approve or reject a POC
- Override the decision engine
- Touch the audit trail directly
- Reach any endpoint gated to a human role

Every AI-authored field is tagged `AI_ASSUMPTION` / `MISSING_EVIDENCE`
/ `AI_ASSERTION` and shown *alongside* the raw human-submitted data —
never instead of it. Prompt-injection resistance is structural: the
model is sent requester text in a clearly separated "data" field,
never concatenated into its instructions.

## 🏛️ The governance engine

A fixed, 3-layer deterministic decision engine evaluates every
request, in strict order:

1. **Completeness** — is the intake actually complete?
2. **Mandatory Security Blockers** — any non-negotiable failure?
3. **Risk Scoring** — everything else, weighted

Output is always one of exactly three outcomes: `GO`, `NO-GO`, or
`INSUFFICIENT_INFORMATION`. No fourth option, ever.

Seven **Environment Readiness** dimensions must be attested before a
request can proceed — and two of them, **Isolation** and
**AccessControl**, are structurally non-waivable. There is no
exception path, no override flag, no admin bypass. It's enforced at
the database constraint level, not just in a form.

Every state transition writes an **append-only, SHA-256 hash-chained
audit entry** in the same transaction as the change itself — so a
failed audit write blocks the whole operation, and any tampering with
history is mathematically detectable, not just "logged."

## 🔒 Why this isn't just a CRUD app with an LLM bolted on

- **RBAC enforced server-side on every endpoint** — not UI-only. A
  full role × endpoint matrix is covered by automated tests.
- **Evidence has exactly four states** (`Not Provided` →
  `Submitted - Pending Review` → `Verified`/`Rejected`), and only a
  human Security Reviewer can ever move it past "pending." Uploads are
  magic-byte validated (not trusted by file extension or
  `Content-Type` header) and quarantined before being served.
- **Stale recommendations are caught, not trusted** — if the
  underlying data changes after a recommendation was computed, the
  system detects the staleness and recomputes before letting a human
  approve against outdated information.
- **Real concurrency bugs were found and fixed against a live
  PostgreSQL instance** during development — not just unit-tested
  against SQLite. See `backend/IMPLEMENTATION-NOTES.md` for the honest
  write-up, including two defects (an enum/CHECK-constraint mismatch
  and an undersized audit column) that SQLite's laxer type system had
  been silently hiding.

## 🧰 Tech stack

- **Backend**: FastAPI, SQLAlchemy 2.0 (async), Alembic migrations,
  PostgreSQL (prod) / SQLite (dev & tests)
- **AI providers**: Google Gemini and Anthropic Claude, swappable via
  one config value — zero code changes to switch
- **Object storage**: S3-compatible abstraction (real AWS S3, MinIO,
  or local filesystem for dev), quarantine/serving buckets kept
  structurally separate
- **Frontend**: server-rendered HTML + vanilla JS, calling the exact
  same JSON API a future SPA would
- **Auth**: JWT-based, bcrypt password hashing
- **Testing**: **117 automated tests**, including a dedicated security
  suite (RBAC matrix, prompt-injection resistance, secret-exposure
  checks, file-upload content-spoofing, audit tamper detection, and
  real concurrency races reproduced on independent connections)

## 🚀 Running it yourself

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env
# generate your own JWT secret:
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**You need your own AI key to actually run the AI features** — this
repo obviously doesn't ship one. Open `backend/.env`, pick a provider,
and drop your own key in:

```env
AI_PROVIDER=gemini          # or "anthropic"
GEMINI_API_KEY=your-own-key-here
# or
ANTHROPIC_API_KEY=your-own-key-here
```

No key configured? The app doesn't fake a response — the AI endpoints
return a clean `503` until you set one. Fail closed, not fail fake.

Then just start it:

```bash
uvicorn app.main:app --reload
```

Open `http://localhost:8000/login`, register an account (pick a
role), and you're in.

Run the test suite:

```bash
pytest
```

For PostgreSQL / S3 / production deployment, see
[`backend/deploy/DEPLOYMENT.md`](backend/deploy/DEPLOYMENT.md) and
[`backend/deploy/EXTERNAL-VERIFICATION.md`](backend/deploy/EXTERNAL-VERIFICATION.md).

## 📁 Project layout

```
backend/
  app/
    api/routes/     — one file per resource, RBAC on every route
    models/          — SQLAlchemy models (the actual source of truth)
    services/        — business logic; services/ai/ is the provider-agnostic AI layer
    services/engine.py — the deterministic 3-layer decision engine
  alembic/           — migrations (dialect-neutral: SQLite + PostgreSQL)
  tests/             — 117 tests, including tests/test_security.py
  scripts/           — live verify_{gemini,postgres,s3}.py scripts
  deploy/            — deployment docs, role-separation SQL, release notes
  IMPLEMENTATION-NOTES.md — the honest "here's what's real vs. deferred" log
architecture/        — the design doc (TASD) this build follows
docs/baseline/       — the original requirements/governance baseline
```

## 📜 License

No license file yet — treat as "all rights reserved" until one is
added. Open an issue if you want to use this and need that clarified.
