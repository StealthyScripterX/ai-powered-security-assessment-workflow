"""Evidence upload, scanning, and the human-only four-state transition.

BR-005a / architecture/TASD-v1.0.md section 15.3: an upload ALWAYS lands
at `Submitted - Pending Review`, never `Verified` or `Rejected` --
`fn_transition_evidence_state`'s equivalent here
(`transition_evidence_state`) is the ONLY function that can move a
control to `Verified` or `Rejected`, and it requires a SecurityReviewer
(or FinalApprover, per OD-07's extension point) actor. No AI-kind actor
can reach this function -- there is no AI-facing route for it at all
(app/api/routes/evidence.py never wires it to anything but the
SecurityReviewer-gated endpoint).

Object storage: architecture/TASD-v1.0.md section 9.5 specifies
S3-compatible object storage with quarantine/serving bucket separation.
`app/services/storage.py` provides that behind an `ObjectStorage`
protocol -- a local-filesystem implementation (this build's dev/test
default) and a real S3-compatible implementation, selected by
`STORAGE_BACKEND` (app/config.py). This module depends only on the
protocol, never on which backend is active -- same quarantine-then-scan
flow, same content hashing, same "never served until Clean," regardless
of backend. See IMPLEMENTATION-NOTES.md.
"""
from __future__ import annotations

import hashlib
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ActorKind
from app.models.evidence import ControlEvidenceState, EvidenceArtifact, EvidenceState, ScanStatus
from app.services import audit_service, versioning
from app.services.scope_service import get_poc_request_for_requester
from app.services.storage import get_storage

MAX_UPLOAD_BYTES = 25 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "text/plain",
    "text/csv",
    "image/png",
    "image/jpeg",
    "application/json",
    "application/zip",
}

# A deliberately recognizable, standard test string (same idea as the
# industry-standard EICAR test file) so automated tests can exercise the
# Infected path deterministically without needing a real AV engine.
# PLACEHOLDER ONLY -- see docstring and IMPLEMENTATION-NOTES.md: a real
# deployment replaces `run_scan` with a call to an actual AV service
# (architecture/TASD-v1.0.md section 15.4), never ships this pattern.
_FAKE_MALWARE_MARKER = re.compile(rb"EICAR-FAKE-TEST-MARKER")

# Magic-byte signatures for the binary types in ALLOWED_CONTENT_TYPES.
# architecture/TASD-v1.0.md section 15.4: "enforced server-side against
# the actual decoded content type (magic-byte sniffing), never the
# client-supplied Content-Type header or file extension alone." A
# mismatch between what the client CLAIMED (`content_type` parameter)
# and what the bytes ACTUALLY are is rejected outright -- this is a
# content-spoofing defense (e.g. an executable renamed to "evidence.pdf"
# with a forged Content-Type header), not merely a formality.
_MAGIC_BYTES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF-",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "application/zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}
# Known-dangerous executable/script signatures that must never be
# accepted regardless of the claimed content type (covers the text/*
# and application/json types above, which have no single magic number
# of their own to positively match against).
_DANGEROUS_SIGNATURES: tuple[bytes, ...] = (
    b"MZ",  # Windows PE executable
    b"\x7fELF",  # Linux ELF executable
    b"#!/",  # shebang script
    b"\xca\xfe\xba\xbe",  # Mach-O / Java class (fat binary magic)
)


def _sniff_content_type_mismatch(claimed_content_type: str, file_bytes: bytes) -> str | None:
    """Returns an error string if the bytes don't match what was
    claimed, else None. Never trusts the claim alone for the types that
    have a real magic number; for the plain-text types, only rejects
    bytes that look like a disguised executable/script.
    """
    header = file_bytes[:16]
    if any(header.startswith(sig) for sig in _DANGEROUS_SIGNATURES):
        return "File content matches a known executable/script signature, regardless of the declared content type."

    expected_signatures = _MAGIC_BYTES.get(claimed_content_type)
    if expected_signatures is not None and not any(header.startswith(sig) for sig in expected_signatures):
        return (
            f"File content does not match the declared content type {claimed_content_type!r} "
            f"(magic-byte check failed)."
        )
    return None


class EvidenceNotFoundError(RuntimeError):
    pass


class ValidationError(RuntimeError):
    pass


def _storage_key(poc_request_id: str, artifact_id: str, filename: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)[-100:]
    return f"{poc_request_id}/{artifact_id}_{safe_name}"


async def upload_evidence(
    db: AsyncSession,
    *,
    poc_request_id: str,
    requester_id: str,
    control_id: str | None,
    filename: str,
    content_type: str,
    file_bytes: bytes,
) -> EvidenceArtifact:
    poc_request = await get_poc_request_for_requester(db, poc_request_id, requester_id)

    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(f"Content type {content_type!r} is not permitted.")
    if len(file_bytes) == 0 or len(file_bytes) > MAX_UPLOAD_BYTES:
        raise ValidationError(f"File size must be between 1 byte and {MAX_UPLOAD_BYTES} bytes.")

    mismatch = _sniff_content_type_mismatch(content_type, file_bytes)
    if mismatch is not None:
        raise ValidationError(mismatch)

    import uuid

    artifact_id = str(uuid.uuid4())
    storage_key = _storage_key(poc_request.id, artifact_id, filename)
    content_hash = hashlib.sha256(file_bytes).hexdigest()

    await get_storage().write_quarantine(storage_key, file_bytes)

    artifact = EvidenceArtifact(
        id=artifact_id,
        poc_request_id=poc_request.id,
        control_id=control_id,
        filename=filename,
        content_type=content_type,
        size_bytes=len(file_bytes),
        storage_key=storage_key,
        content_sha256=content_hash,
        scan_status=ScanStatus.PENDING,
        uploaded_by=requester_id,
    )
    db.add(artifact)
    await db.flush()

    if control_id:
        # BR-005a: ALWAYS lands here, never Verified/Rejected. A new
        # upload against a previously Verified/Rejected control resets
        # validation state -- a human must re-look at the new bytes.
        existing = await db.execute(
            select(ControlEvidenceState).where(
                ControlEvidenceState.poc_request_id == poc_request.id,
                ControlEvidenceState.control_id == control_id,
            )
        )
        state_row = existing.scalar_one_or_none()
        if state_row is None:
            state_row = ControlEvidenceState(poc_request_id=poc_request.id, control_id=control_id)
            db.add(state_row)
        state_row.state = EvidenceState.SUBMITTED_PENDING_REVIEW
        state_row.validated_by = None
        state_row.validated_at = None
        state_row.validation_rationale = None
        await db.flush()

        # D2 section 8.5 invalidating change 2 (evidence-artifact changes).
        await versioning.bump_input_version(db, poc_request_id=poc_request.id)

    await audit_service.record_event(
        db,
        actor_id=requester_id,
        actor_kind=ActorKind.REQUESTER,
        action_type="evidence_uploaded",
        affected_object_type="evidence_artifact",
        affected_object_id=artifact.id,
        after_state={"control_id": control_id, "scan_status": ScanStatus.PENDING.value, "sha256": content_hash},
    )
    await db.commit()
    return artifact


async def run_scan(db: AsyncSession, *, artifact_id: str) -> EvidenceArtifact:
    """Stands in for the asynchronous AV-scan worker
    (architecture/TASD-v1.0.md section 8.14 `worker-ops`). An Infected
    result deletes the quarantined bytes; a Clean result moves the file
    to the serving directory. Either way, this NEVER changes
    `ControlEvidenceState.state` -- scanning gates whether the artifact
    is retrievable, not whether a human has validated it (TASD-v1.0.md
    section 15.3).
    """
    result = await db.execute(select(EvidenceArtifact).where(EvidenceArtifact.id == artifact_id))
    artifact = result.scalar_one_or_none()
    if artifact is None:
        raise EvidenceNotFoundError(f"Evidence artifact {artifact_id} not found.")

    storage = get_storage()
    data = await storage.read_quarantine(artifact.storage_key) or b""

    if _FAKE_MALWARE_MARKER.search(data):
        artifact.scan_status = ScanStatus.INFECTED
        await storage.delete_quarantine(artifact.storage_key)
    else:
        artifact.scan_status = ScanStatus.CLEAN
        await storage.promote_to_evidence(artifact.storage_key, data)

    await audit_service.record_event(
        db,
        actor_id=None,
        actor_kind=ActorKind.SYSTEM,
        action_type="evidence_scanned",
        affected_object_type="evidence_artifact",
        affected_object_id=artifact.id,
        after_state={"scan_status": artifact.scan_status.value},
    )
    await db.commit()
    return artifact


async def transition_evidence_state(
    db: AsyncSession,
    *,
    poc_request_id: str,
    control_id: str,
    new_state: str,  # "Verified - Human Validated" | "Rejected - Insufficient Evidence"
    reviewer_id: str,
    rationale: str,
) -> ControlEvidenceState:
    """The ONLY path that can set Verified/Rejected -- requires a
    SecurityReviewer-role caller (enforced by the route's RBAC
    dependency, app/api/routes/evidence.py), never reachable by the AI
    actor at all.
    """
    target = EvidenceState(new_state)
    if target not in (EvidenceState.VERIFIED_HUMAN_VALIDATED, EvidenceState.REJECTED_INSUFFICIENT_EVIDENCE):
        raise ValidationError(
            "This function may only set 'Verified - Human Validated' or "
            "'Rejected - Insufficient Evidence'; use the upload path for other states."
        )
    if not rationale or not rationale.strip():
        raise ValidationError("A non-empty rationale is required to validate or reject evidence.")

    # FOR UPDATE: locks this control's evidence-state row for the
    # duration of the transition so two concurrent reviewer decisions on
    # the same control (e.g. one Verify, one Reject racing each other)
    # can never both read the pre-transition state and both believe
    # they are the one making the change. No-op under SQLite; a real
    # row lock under PostgreSQL, same code path as the other FOR UPDATE
    # sites in this codebase (approval_service.py, versioning.py,
    # audit_service.py).
    result = await db.execute(
        select(ControlEvidenceState)
        .where(ControlEvidenceState.poc_request_id == poc_request_id, ControlEvidenceState.control_id == control_id)
        .with_for_update()
    )
    state_row = result.scalar_one_or_none()
    if state_row is None:
        raise EvidenceNotFoundError(f"No evidence state exists yet for control {control_id!r} on this POC request.")

    before = state_row.state.value
    state_row.state = target
    state_row.validated_by = reviewer_id
    state_row.validation_rationale = rationale
    from datetime import datetime, timezone

    state_row.validated_at = datetime.now(timezone.utc)
    await db.flush()

    # D2 section 8.5 invalidating change 1 (evidence-state changes).
    await versioning.bump_input_version(db, poc_request_id=poc_request_id)

    await audit_service.record_event(
        db,
        actor_id=reviewer_id,
        actor_kind=ActorKind.SECURITY_REVIEWER,
        action_type="evidence_state_transition",
        affected_object_type="control_evidence_state",
        affected_object_id=f"{poc_request_id}:{control_id}",
        before_state={"state": before},
        after_state={"state": target.value},
    )
    await db.commit()
    return state_row


async def list_evidence_states(db: AsyncSession, *, poc_request_id: str) -> list[ControlEvidenceState]:
    result = await db.execute(
        select(ControlEvidenceState).where(ControlEvidenceState.poc_request_id == poc_request_id)
    )
    return list(result.scalars().all())
