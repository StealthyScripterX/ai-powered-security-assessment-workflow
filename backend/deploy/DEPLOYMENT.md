# Production deployment

Concrete, run-these-commands guidance for deploying this application
against real PostgreSQL and (optionally) real S3-compatible storage.
No PostgreSQL/S3/Docker instance is available in the environment this
was written in, so none of this has been run against a live service --
see IMPLEMENTATION-NOTES.md for exactly what was and wasn't verified,
and don't take this file as a substitute for that honesty.

## 1. Secret management

Every credential (`JWT_SECRET_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
database password, `AWS_SECRET_ACCESS_KEY`) is read exclusively from
the process environment (`app/config.py`, `SecretStr` fields -- never
logged, never returned in an API response, masked as `**********` in
any repr). In production:

- Inject env vars from your platform's secret manager (AWS Secrets
  Manager / Parameter Store, GCP Secret Manager, Vault, Kubernetes
  Secrets) at container start -- never bake them into an image layer,
  never commit a production `.env`.
- Generate `JWT_SECRET_KEY` once per environment and never reuse the
  dev value: `python -c "import secrets; print(secrets.token_urlsafe(48))"`.
- Rotate the PostgreSQL `poc_app_rw`/`poc_migrator` passwords and both
  AI provider keys independently of application deploys.

## 2. Database (PostgreSQL)

```bash
# One-time, as a superuser (deploy/postgresql_roles.sql -- edit the two
# placeholder passwords first, or better, template them from your
# secret manager):
psql -h <host> -U postgres -f deploy/postgresql_roles.sql

# Migrations, run as poc_migrator (DDL role), NOT the app's own
# DATABASE_URL:
DATABASE_URL="postgresql+asyncpg://poc_migrator:<password>@<host>:5432/poc_workflow" \
  alembic upgrade head

# App startup connects as poc_app_rw (DML-only role):
DATABASE_URL="postgresql+asyncpg://poc_app_rw:<password>@<host>:5432/poc_workflow"
```

Install the `postgres` extra (`asyncpg`) alongside the app:
`pip install -e ".[postgres]"`.

Before trusting this in production, run `scripts/verify_postgres.py`
against the real instance once -- see `deploy/EXTERNAL-VERIFICATION.md`
§2 for exact setup commands and PASS criteria (connectivity,
migrations, role separation, row locking, atomicity).

### Backup and recovery

- **Continuous**: enable WAL archiving (`archive_mode = on`) to object
  storage (managed Postgres services -- RDS, Cloud SQL, etc -- do this
  for you; a self-managed instance needs `archive_command` configured).
- **Point-in-time restore**: `pg_basebackup` snapshot + replayed WAL,
  or your managed provider's PITR feature. Test the restore procedure
  *before* needing it -- a backup that has never been restored is not
  a verified backup, and this build has not had the chance to verify
  one against a real instance.
- **Logical backup for smaller/non-PITR needs**:
  `pg_dump --format=custom poc_workflow > backup.dump`, restore with
  `pg_restore --dbname=poc_workflow backup.dump`.
- The audit hash chain (`app/services/audit_service.py:verify_chain`)
  is the integrity check to run immediately after any restore --
  it recomputes every entry's hash from genesis and reports the first
  broken link, if any, confirming the restored chain is intact before
  resuming traffic.

## 3. Evidence storage (S3)

Set `STORAGE_BACKEND=s3`, `S3_QUARANTINE_BUCKET`, `S3_EVIDENCE_BUCKET`,
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` (or omit both and rely on
the AWS SDK's normal credential chain -- an attached IAM role is
preferred over static keys in any real deployment). Install the `s3`
extra: `pip install -e ".[s3]"`.

- Create the two buckets with **separate** IAM policies: the
  quarantine bucket should deny `s3:GetObject` to everything except
  the application's own scan-worker role -- nothing downstream of
  scanning should ever be able to read an unscanned file, enforced at
  the infrastructure level, not only by this codebase's logic.
  Enable versioning + a lifecycle rule to expire quarantine objects
  after a short window (scanned-and-promoted items should never
  linger there).
- The evidence (serving) bucket should block public access entirely;
  evidence is served through the application's own authenticated API,
  never a direct public URL.
- `app/services/storage.py:S3Storage` was tested against `moto`'s
  mocked S3 (`tests/test_storage.py`) -- a real boto3 client against an
  in-process fake implementing the actual S3 API, not a real AWS/MinIO
  instance. Before trusting this in production, run
  `scripts/verify_s3.py` against the real target once -- see
  `deploy/EXTERNAL-VERIFICATION.md` §3 for exact setup commands and
  PASS criteria.

## 4. Health, readiness, and logging

- `GET /healthz` -- liveness only (process is up). Use for your
  orchestrator's liveness probe.
- `GET /readyz` -- readiness: executes a real `SELECT 1` against the
  configured database and returns 503 if unreachable. Use for the
  readiness probe / load-balancer health check, not liveness -- a
  transient DB blip should take this instance out of rotation, not
  have the orchestrator kill-loop it.
- Every credential field is `SecretStr`; nothing in this codebase logs
  a raw credential, and `/readyz`'s failure path deliberately logs the
  DB exception server-side (which can embed the DSN) rather than
  returning it in the HTTP response body -- see `app/main.py`.
- Point your platform's log collector at stdout/stderr (uvicorn's
  default); no file-based logging is configured, so there is no local
  log file to accidentally leave world-readable with a stray key in it.

## 5. Startup

```bash
pip install -e ".[postgres,s3]"
alembic upgrade head        # as poc_migrator
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers <N>
```

Set `AI_PROVIDER` (`anthropic` or `gemini`) and its matching API key;
leaving the selected provider's key blank is a deliberate, tested
fail-closed 503 on the AI-facing endpoints (`app/api/deps.py`), never a
silent fallback.
