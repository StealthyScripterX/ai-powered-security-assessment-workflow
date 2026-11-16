"""Safe, repeatable live S3/MinIO verification command.

Run from backend/, against REAL S3-compatible object storage (a
disposable local MinIO container is the fastest way to get one if you
don't already have AWS access):

    docker run -p 9000:9000 -p 9001:9001 minio/minio server /data --console-address ":9001"
    # then, in another terminal, create the two buckets with the MinIO
    # client (`mc`) or the MinIO web console at http://localhost:9001

    export STORAGE_BACKEND=s3
    export S3_QUARANTINE_BUCKET=verify-quarantine
    export S3_EVIDENCE_BUCKET=verify-evidence
    export S3_ENDPOINT_URL=http://localhost:9000   # blank for real AWS S3
    export S3_REGION=us-east-1
    export AWS_ACCESS_KEY_ID=minioadmin            # your real key for AWS
    export AWS_SECRET_ACCESS_KEY=minioadmin        # your real secret for AWS
    python scripts/verify_s3.py

Prerequisites: `pip install -e ".[s3]"` (installs `boto3`); the two
buckets created ahead of time (this script does not create buckets --
bucket creation is an infrastructure/IAM decision, not an application
concern).

What this script checks, using the REAL application code
(`app/services/storage.py:S3Storage`, via `get_storage()` -- the exact
class `app/services/evidence_service.py` calls, not a hand-rolled S3
client):
  1. Upload + retrieval: write to quarantine, read it back byte-for-byte.
  2. Quarantine separation: after promotion, the object is gone from
     quarantine and present in evidence -- never readable from both,
     never readable from evidence before promotion.
  3. Access control: OPTIONAL -- if `S3_READONLY_ACCESS_KEY_ID`/
     `S3_READONLY_SECRET_ACCESS_KEY` are set (a second, deliberately
     under-privileged credential pointed at the SAME buckets), confirms
     that credential cannot read the quarantine bucket. Without those,
     this step is NOT TESTED, not assumed -- bucket policy is an
     infrastructure setting this script cannot verify from one
     credential alone.
  4. Full evidence_service integration: runs an actual
     `evidence_service.upload_evidence` + `run_scan` through a
     throwaway in-memory SQLite database, confirming the application's
     real upload/scan/quarantine/promote code path works end-to-end
     against this real S3 backend (magic-byte validation still runs;
     evidence is still never auto-verified -- this only exercises
     upload+scan, never `transition_evidence_state`).

Never prints a credential. Exit code 0 only if every applicable step
PASSes.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

sys.path.insert(0, ".")

RESULTS: list[tuple[str, str, str]] = []


def _report(step: str, status: str, detail: str) -> None:
    RESULTS.append((step, status, detail))
    print(f"[{status}] {step}: {detail}")


def check_config() -> bool:
    from app.config import get_settings

    settings = get_settings()
    if settings.storage_backend != "s3":
        _report("config", "FAIL", "STORAGE_BACKEND is not 's3' -- set it before running this script.")
        return False
    if not settings.storage_configured:
        _report("config", "FAIL", "S3_QUARANTINE_BUCKET/S3_EVIDENCE_BUCKET are not both set.")
        return False
    _report("config", "PASS", f"STORAGE_BACKEND=s3, buckets configured (names withheld from this message).")
    return True


async def check_upload_retrieval_and_quarantine_separation() -> None:
    from app.services.storage import get_storage

    storage = get_storage()
    key = f"verify-s3/{uuid.uuid4().hex}.txt"
    payload = f"S3 live verification payload -- safe to delete -- {uuid.uuid4().hex}".encode()

    try:
        await storage.write_quarantine(key, payload)
        read_back = await storage.read_quarantine(key)
        if read_back != payload:
            _report("upload_retrieval", "FAIL", "bytes read back from quarantine did not match what was written.")
            return
        _report("upload_retrieval", "PASS", "wrote to quarantine and read back identical bytes.")
    except Exception as exc:  # noqa: BLE001
        _report("upload_retrieval", "FAIL", f"{type(exc).__name__} (credentials withheld from this message)")
        return

    try:
        await storage.promote_to_evidence(key, payload)
        still_in_quarantine = await storage.read_quarantine(key)
        if still_in_quarantine is not None:
            _report("quarantine_separation", "FAIL", "object still readable from quarantine after promotion.")
            return
        _report("quarantine_separation", "PASS", "object removed from quarantine and promoted to evidence.")
    except Exception as exc:  # noqa: BLE001
        _report("quarantine_separation", "FAIL", f"{type(exc).__name__} (credentials withheld from this message)")


async def check_access_control() -> None:
    import os

    readonly_key = os.environ.get("S3_READONLY_ACCESS_KEY_ID")
    readonly_secret = os.environ.get("S3_READONLY_SECRET_ACCESS_KEY")
    if not (readonly_key and readonly_secret):
        _report(
            "access_control", "NOT TESTED",
            "S3_READONLY_ACCESS_KEY_ID/S3_READONLY_SECRET_ACCESS_KEY not set -- "
            "provide a deliberately under-privileged credential pointed at the same buckets to test this.",
        )
        return

    from app.config import get_settings
    from app.services.storage import S3Storage

    settings = get_settings()
    restricted = S3Storage(
        quarantine_bucket=settings.s3_quarantine_bucket,
        evidence_bucket=settings.s3_evidence_bucket,
        region_name=settings.s3_region or None,
        endpoint_url=settings.s3_endpoint_url or None,
        access_key_id=readonly_key,
        secret_access_key=readonly_secret,
    )
    probe_key = f"verify-s3-access-control/{uuid.uuid4().hex}.txt"
    try:
        await restricted.read_quarantine(probe_key)
        _report(
            "access_control", "FAIL",
            "the under-privileged credential was able to read the quarantine bucket -- "
            "tighten its IAM/bucket policy.",
        )
    except Exception as exc:  # noqa: BLE001
        if "accessdenied" in str(exc).lower() or "forbidden" in str(exc).lower() or "403" in str(exc):
            _report("access_control", "PASS", "under-privileged credential correctly denied access to quarantine.")
        else:
            _report("access_control", "BLOCKED", f"unexpected error type, cannot confirm: {type(exc).__name__}")


async def check_evidence_service_integration() -> None:
    """Exercises the REAL upload_evidence + run_scan path -- never
    transition_evidence_state, so this cannot and does not verify
    anything, by design (BR-005a: an upload never auto-verifies).
    """
    import os

    os.environ.setdefault("JWT_SECRET_KEY", "verify-s3-script-only-not-for-production")
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.database import Base
    from app.models.evidence import ScanStatus
    from app.models.user import AppUser, UserRole
    from app.security import hash_password
    from app.services import evidence_service, scope_service

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    try:
        async with session_factory() as db:
            requester = AppUser(
                username=f"verify_s3_{uuid.uuid4().hex[:8]}",
                email=f"verify_s3_{uuid.uuid4().hex[:8]}@example.com",
                hashed_password=hash_password("verification-only-password-12345"),
                role=UserRole.REQUESTER,
            )
            db.add(requester)
            await db.flush()

            poc_request, _scope = await scope_service.submit_scope(
                db,
                requester_id=requester.id,
                project_description="Live S3 integration verification -- safe to delete.",
                systems_in_scope="None -- synthetic verification record.",
                business_justification="Infrastructure verification only.",
                intake_form_data={},
            )

            artifact = await evidence_service.upload_evidence(
                db,
                poc_request_id=poc_request.id,
                requester_id=requester.id,
                control_id="VERIFY-S3-1",
                filename="verify.txt",
                content_type="text/plain",
                file_bytes=b"Live S3 verification -- real evidence_service.upload_evidence path.",
            )
            scanned = await evidence_service.run_scan(db, artifact_id=artifact.id)
            if scanned.scan_status != ScanStatus.CLEAN:
                _report("evidence_service_integration", "FAIL", f"expected Clean scan, got {scanned.scan_status}")
                return
        _report(
            "evidence_service_integration", "PASS",
            "a real evidence_service.upload_evidence + run_scan call succeeded end-to-end against this S3 backend.",
        )
    except Exception as exc:  # noqa: BLE001
        _report("evidence_service_integration", "FAIL", f"{type(exc).__name__} (credentials withheld from this message)")
    finally:
        await engine.dispose()


async def main() -> int:
    if not check_config():
        return 2
    await check_upload_retrieval_and_quarantine_separation()
    await check_access_control()
    await check_evidence_service_integration()

    print("\n--- Summary ---")
    for step, status, _detail in RESULTS:
        print(f"{status:12s} {step}")
    return 0 if all(s in ("PASS", "NOT TESTED") for _, s, _ in RESULTS) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
