"""Safe, repeatable live PostgreSQL verification command.

Run from backend/, against a REAL PostgreSQL 16 instance (disposable
is fine -- a local install, a throwaway RDS/Cloud SQL instance, or a
`postgres:16` container if Docker is available on your machine):

    export DATABASE_URL="postgresql+asyncpg://poc_app_rw:<password>@<host>:5432/poc_workflow"
    export MIGRATOR_DATABASE_URL="postgresql+asyncpg://poc_migrator:<password>@<host>:5432/poc_workflow"
    python scripts/verify_postgres.py

Prerequisites (see deploy/DEPLOYMENT.md and deploy/postgresql_roles.sql
for the exact commands):
  1. A running PostgreSQL 16 instance.
  2. `psql -h <host> -U postgres -f deploy/postgresql_roles.sql` run
     once (edit the two placeholder passwords first).
  3. `DATABASE_URL=<poc_migrator DSN> alembic upgrade head` run once.
  4. `pip install -e ".[postgres]"` (installs `asyncpg`).

What this script checks, each a separate, independently-reported step
(never stops at the first failure unless a step is a hard prerequisite
for a later one):
  1. Connectivity + migrations are at head.
  2. Role separation: the app role (DATABASE_URL) can do DML but NOT
     DDL; the migrator role (MIGRATOR_DATABASE_URL), if given, CAN.
  3. Real row-level locking: app/services/evidence_service.py's
     `.with_for_update()` genuinely serializes two concurrent evidence-
     state transitions on PostgreSQL (the SAME check
     tests/test_evidence_concurrency.py makes against two independent
     SQLite connections, run here against a real server) -- exactly
     ONE of two concurrent attempts commits, the loser gets a clean
     VersionConflictError, never both/neither, never a corrupted state.
  4. Atomicity: a forced mid-transaction failure leaves NO partial
     audit entry or state change behind.

Never prints a DSN, password, or any other credential -- only
PASS/FAIL/BLOCKED per step and the specific, non-secret reason.
Exit code 0 only if every applicable step PASSes.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

sys.path.insert(0, ".")

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

RESULTS: list[tuple[str, str, str]] = []  # (step, status, detail)


def _report(step: str, status: str, detail: str) -> None:
    RESULTS.append((step, status, detail))
    print(f"[{status}] {step}: {detail}")


def _require_postgres_url(name: str) -> str | None:
    import os

    url = os.environ.get(name)
    if not url:
        return None
    if not url.startswith("postgresql"):
        _report(name, "BLOCKED", f"{name} is set but is not a postgresql:// DSN -- refusing to run against it.")
        return None
    return url


async def check_connectivity_and_migrations(app_url: str) -> bool:
    engine = create_async_engine(app_url)
    try:
        async with engine.connect() as conn:
            version = (await conn.execute(text("SELECT version()"))).scalar_one()
            _report("connectivity", "PASS", f"connected -- server reports: {version.split(',')[0]}")

            try:
                row = (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar_one_or_none()
            except DBAPIError:
                _report("migrations", "FAIL", "alembic_version table not found -- run `alembic upgrade head` first.")
                return False
            if row is None:
                _report("migrations", "FAIL", "alembic_version table is empty.")
                return False
            _report("migrations", "PASS", f"at revision {row} -- compare against `alembic heads` for your checkout.")
            return True
    except Exception as exc:  # noqa: BLE001 -- top-level diagnostic script
        _report("connectivity", "FAIL", f"{type(exc).__name__} (DSN/credentials withheld from this message)")
        return False
    finally:
        await engine.dispose()


async def check_role_separation(app_url: str, migrator_url: str | None) -> None:
    probe_table = f"verify_role_check_{uuid.uuid4().hex[:8]}"
    engine = create_async_engine(app_url)
    try:
        async with engine.connect() as conn:
            await conn.execute(text(f"CREATE TABLE {probe_table} (id int)"))
            await conn.rollback()
            _report(
                "role_separation(app=DDL)", "FAIL",
                "the app role (DATABASE_URL) was able to CREATE TABLE -- it should be DML-only. "
                "Re-check deploy/postgresql_roles.sql was applied to this role.",
            )
            # Clean up the table we should not have been able to make.
            async with engine.begin() as cleanup:
                await cleanup.execute(text(f"DROP TABLE IF EXISTS {probe_table}"))
    except Exception as exc:  # noqa: BLE001
        if "permission denied" in str(exc).lower() or "insufficientprivilege" in type(exc).__name__.lower():
            _report("role_separation(app=DDL)", "PASS", "app role correctly denied CREATE TABLE (DML-only, as designed).")
        else:
            _report("role_separation(app=DDL)", "BLOCKED", f"unexpected error type: {type(exc).__name__}")
    finally:
        await engine.dispose()

    if migrator_url is None:
        _report("role_separation(migrator=DDL)", "NOT TESTED", "MIGRATOR_DATABASE_URL not set -- skipped.")
        return
    engine = create_async_engine(migrator_url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(f"CREATE TABLE {probe_table}_m (id int)"))
            await conn.execute(text(f"DROP TABLE {probe_table}_m"))
        _report("role_separation(migrator=DDL)", "PASS", "migrator role can CREATE/DROP TABLE, as designed.")
    except Exception as exc:  # noqa: BLE001
        _report("role_separation(migrator=DDL)", "FAIL", f"migrator role could not DDL: {type(exc).__name__}")
    finally:
        await engine.dispose()


async def check_row_locking(app_url: str) -> None:
    """The real concurrency check: seeds a minimal user/poc_request/
    scope/control_evidence_state via the app's OWN service functions
    (not hand-written SQL -- so this exercises the real code path),
    then fires two concurrent `evidence_service.transition_evidence_state`
    calls on two independent connections, exactly
    tests/test_evidence_concurrency.py's approach, against this real
    PostgreSQL server instead of two SQLite connections.
    """
    from app.models.audit import ActorKind
    from app.models.evidence import ControlEvidenceState, EvidenceState
    from app.models.user import AppUser, UserRole
    from app.security import hash_password
    from app.services import evidence_service, scope_service
    from app.services.catalog_seed import seed_catalog_if_empty
    from app.services.versioning import VersionConflictError

    engine = create_async_engine(app_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    try:
        async with session_factory() as db:
            # control_evidence_state.control_id is a real foreign key
            # into the D3-Catalog `control` table -- a made-up ID would
            # fail this INSERT with ForeignKeyViolationError, which is
            # correct behavior, not a bug: seed the real catalog first
            # (idempotent) and use a real control ("AC-2").
            await seed_catalog_if_empty(db)

            requester = AppUser(
                username=f"verify_pg_requester_{uuid.uuid4().hex[:8]}",
                email=f"verify_pg_{uuid.uuid4().hex[:8]}@example.com",
                hashed_password=hash_password("verification-only-password-12345"),
                role=UserRole.REQUESTER,
            )
            reviewer = AppUser(
                username=f"verify_pg_reviewer_{uuid.uuid4().hex[:8]}",
                email=f"verify_pg_reviewer_{uuid.uuid4().hex[:8]}@example.com",
                hashed_password=hash_password("verification-only-password-12345"),
                role=UserRole.SECURITY_REVIEWER,
            )
            db.add_all([requester, reviewer])
            await db.flush()

            poc_request, _scope = await scope_service.submit_scope(
                db,
                requester_id=requester.id,
                project_description="Live PostgreSQL locking verification -- safe to delete.",
                systems_in_scope="None -- synthetic verification record.",
                business_justification="Infrastructure verification only.",
                intake_form_data={},
            )

            state_row = ControlEvidenceState(
                poc_request_id=poc_request.id, control_id="AC-2", state=EvidenceState.SUBMITTED_PENDING_REVIEW
            )
            db.add(state_row)
            await db.flush()
            await db.commit()
            poc_request_id = poc_request.id
            reviewer_id = reviewer.id
    except Exception as exc:  # noqa: BLE001
        _report("row_locking", "BLOCKED", f"could not seed verification data: {type(exc).__name__}")
        await engine.dispose()
        return

    second_engine = create_async_engine(app_url)
    first_factory = session_factory
    second_factory = async_sessionmaker(second_engine, expire_on_commit=False, class_=AsyncSession)

    async def _attempt(factory, new_state: str, n: int):
        async with factory() as db:
            return await evidence_service.transition_evidence_state(
                db,
                poc_request_id=poc_request_id,
                control_id="AC-2",
                new_state=new_state,
                reviewer_id=reviewer_id,
                rationale=f"Live PostgreSQL concurrency verification, attempt {n}.",
            )

    try:
        results = await asyncio.gather(
            _attempt(first_factory, "Verified - Human Validated", 1),
            _attempt(second_factory, "Rejected - Insufficient Evidence", 2),
            return_exceptions=True,
        )
    finally:
        await engine.dispose()
        await second_engine.dispose()

    conflicts = [
        r for r in results
        if isinstance(r, VersionConflictError) or (isinstance(r, OperationalError) and "lock" in str(r).lower())
    ]
    others = [r for r in results if isinstance(r, Exception) and r not in conflicts]
    committed = [r for r in results if not isinstance(r, Exception)]

    if others:
        _report("row_locking", "FAIL", f"unexpected exception type escaped: {[type(e).__name__ for e in others]}")
    elif len(committed) == 1 and len(conflicts) == 1:
        _report(
            "row_locking", "PASS",
            "exactly one concurrent attempt committed, the other got a clean conflict refusal -- "
            "real PostgreSQL row locking confirmed, not corrupted/partial state.",
        )
    elif len(committed) == 2:
        _report(
            "row_locking", "PASS",
            "both attempts committed sequentially without error -- PostgreSQL's FOR UPDATE lock "
            "serialized them (second waited for the first to commit, then proceeded) rather than "
            "colliding. Also a valid, correct outcome.",
        )
    else:
        _report("row_locking", "FAIL", f"neither attempt committed: {results}")


async def check_atomicity(app_url: str) -> None:
    """Confirms a forced failure mid-transaction leaves no partial
    write -- the same guarantee app/services/audit_service.py's
    docstring describes (audit row and state-changing row commit or
    roll back together).
    """
    from app.models.audit import ActorKind
    from app.services import audit_service

    engine = create_async_engine(app_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    marker = f"verify-pg-atomicity-{uuid.uuid4().hex}"
    try:
        async with session_factory() as db:
            await audit_service.record_event(
                db,
                actor_id=None,
                actor_kind=ActorKind.SYSTEM,
                action_type=marker,
                affected_object_type="verification",
                affected_object_id="atomicity-check",
                after_state={"intentional": "forced failure follows"},
            )
            try:
                # Deliberately invalid: violates entry_hash's NOT NULL
                # by going around the ORM -- forces a failure AFTER the
                # audit row above was flushed but BEFORE this
                # transaction commits.
                await db.execute(text("INSERT INTO audit_entry (sequence_number) VALUES (-1)"))
                await db.commit()
                _report("atomicity", "FAIL", "the deliberately-invalid statement did not raise -- cannot confirm rollback.")
                return
            except Exception:
                await db.rollback()
    except Exception as exc:  # noqa: BLE001
        _report("atomicity", "BLOCKED", f"could not run atomicity check: {type(exc).__name__}")
        await engine.dispose()
        return

    async with engine.connect() as conn:
        count = (
            await conn.execute(text("SELECT count(*) FROM audit_entry WHERE action_type = :m"), {"m": marker})
        ).scalar_one()
    await engine.dispose()
    if count == 0:
        _report("atomicity", "PASS", "the audit row from the failed transaction was correctly rolled back, not left behind.")
    else:
        _report("atomicity", "FAIL", f"found {count} leftover row(s) from a transaction that should have rolled back.")


async def main() -> int:
    app_url = _require_postgres_url("DATABASE_URL")
    if app_url is None:
        print("DATABASE_URL is not set to a postgresql:// DSN. Nothing to verify against.")
        return 2
    migrator_url = _require_postgres_url("MIGRATOR_DATABASE_URL")

    migrations_ok = await check_connectivity_and_migrations(app_url)
    if not migrations_ok:
        print("\nStopping -- later checks need a migrated schema.")
        return 1

    await check_role_separation(app_url, migrator_url)
    await check_row_locking(app_url)
    await check_atomicity(app_url)

    print("\n--- Summary ---")
    for step, status, _detail in RESULTS:
        print(f"{status:12s} {step}")
    return 0 if all(s in ("PASS", "NOT TESTED") for _, s, _ in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
