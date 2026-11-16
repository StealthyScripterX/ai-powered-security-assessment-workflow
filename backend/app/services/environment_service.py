"""Environment readiness: attestation, exception disposition, revocation,
and the `final_signoff_boolean` computation.

D4-Environment-Readiness.md section 6/7/8, architecture/TASD-v1.0.md
section 16. `compute_final_signoff` is called FRESH every time -- never
cached -- so an exception's expiry passing, or a revocation, takes
effect the instant it is next checked (D4 section 8.2: "recomputes to
false without requiring anyone to notice").
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ActorKind
from app.models.environment import (
    NON_WAIVABLE_DIMENSIONS,
    AttestationStatus,
    EnvironmentReadinessAttestation,
    ExceptionDisposition,
    ExceptionRecord,
    ReadinessDimension,
)
from app.services import audit_service, versioning

ALL_DIMENSIONS = list(ReadinessDimension)


class ValidationError(RuntimeError):
    pass


class NotFoundError(RuntimeError):
    pass


async def attest_dimension(
    db: AsyncSession,
    *,
    poc_request_id: str,
    dimension: str,
    status: str,
    attestation_text: str | None,
    environment_owner_id: str,
    requester_id_of_poc: str,
    supporting_evidence_ids: list[str] | None = None,
) -> EnvironmentReadinessAttestation:
    """D4 section 7: the attester must not be the Requester for this POC
    (separation of duties) and -- structurally, not checked here because
    there is no AI-facing route for this function at all -- never the AI
    agent.
    """
    if environment_owner_id == requester_id_of_poc:
        raise ValidationError("The Requester for this POC request cannot self-attest environment readiness.")

    dim = ReadinessDimension(dimension)
    att_status = AttestationStatus(status)

    result = await db.execute(
        select(EnvironmentReadinessAttestation).where(
            EnvironmentReadinessAttestation.poc_request_id == poc_request_id,
            EnvironmentReadinessAttestation.dimension == dim,
        )
    )
    row = result.scalar_one_or_none()
    before = row.status.value if row else "Not Started"
    if row is None:
        row = EnvironmentReadinessAttestation(poc_request_id=poc_request_id, dimension=dim)
        db.add(row)

    row.status = att_status
    row.attestation_text = attestation_text
    row.environment_owner_id = environment_owner_id
    row.supporting_evidence_ids = supporting_evidence_ids or []
    row.attested_at = datetime.now(timezone.utc)
    await db.flush()

    # D2 section 8.5 invalidating change 5 (environment attestation/revocation).
    await versioning.bump_input_version(db, poc_request_id=poc_request_id)

    await audit_service.record_event(
        db,
        actor_id=environment_owner_id,
        actor_kind=ActorKind.ENVIRONMENT_OWNER,
        action_type="environment_attested",
        affected_object_type="environment_readiness_attestation",
        affected_object_id=f"{poc_request_id}:{dim.value}",
        before_state={"status": before},
        after_state={"status": att_status.value},
    )
    await db.commit()
    return row


async def dispose_exception(
    db: AsyncSession,
    *,
    poc_request_id: str,
    dimension: str,
    issue_description: str,
    risk_assessment: str,
    compensating_controls: list[str],
    disposition: str,
    disposition_rationale: str,
    authorized_by: str,
    environment_owner_id_for_dimension: str | None,
    remediation_owner: str | None = None,
    remediation_deadline: date | None = None,
    expiry_date: date | None = None,
) -> ExceptionRecord:
    """D4 section 6: `disposition_authorized_by` must never be the
    Environment Owner who raised the exception, and never the AI agent
    (no AI-facing route exists). The non-waivable rule (Isolation /
    AccessControl can never be Accepted) is enforced twice: by the
    database CHECK constraint on `exception_record`
    (app/models/environment.py) AND by this explicit check, matching
    TASD-v1.0.md section 16.3's "belt is the CHECK, suspenders is the
    REQUIRE" pattern.
    """
    dim = ReadinessDimension(dimension)
    disp = ExceptionDisposition(disposition)

    if authorized_by == environment_owner_id_for_dimension:
        raise ValidationError(
            "The person disposing an exception must not be the Environment Owner who raised it."
        )
    if not disposition_rationale or not disposition_rationale.strip():
        raise ValidationError("A non-empty disposition_rationale is required.")
    if disp == ExceptionDisposition.ACCEPTED and dim in NON_WAIVABLE_DIMENSIONS:
        raise ValidationError(
            f"{dim.value} is a non-waivable dimension and can never be disposed 'Accepted' "
            "(D4-Environment-Readiness.md section 6)."
        )
    if disp == ExceptionDisposition.ACCEPTED and (remediation_owner is None or remediation_deadline is None):
        raise ValidationError("remediation_owner and remediation_deadline are required when disposition=Accepted.")
    if expiry_date is None:
        raise ValidationError("expiry_date is required for every exception, including Rejected/Deferred.")

    record = ExceptionRecord(
        poc_request_id=poc_request_id,
        dimension=dim,
        issue_description=issue_description,
        risk_assessment=risk_assessment,
        compensating_controls=compensating_controls,
        disposition=disp,
        disposition_authorized_by=authorized_by,
        disposition_rationale=disposition_rationale,
        remediation_owner=remediation_owner,
        remediation_deadline=remediation_deadline,
        expiry_date=expiry_date,
    )
    db.add(record)

    # Reflect on the attestation row so compute_final_signoff can find it.
    att_result = await db.execute(
        select(EnvironmentReadinessAttestation).where(
            EnvironmentReadinessAttestation.poc_request_id == poc_request_id,
            EnvironmentReadinessAttestation.dimension == dim,
        )
    )
    attestation = att_result.scalar_one_or_none()
    if attestation is None:
        raise NotFoundError(f"No attestation exists yet for dimension {dim.value!r} on this POC request.")
    attestation.status = AttestationStatus.ATTESTED_WITH_EXCEPTION
    await db.flush()

    await versioning.bump_input_version(db, poc_request_id=poc_request_id)

    await audit_service.record_event(
        db,
        actor_id=authorized_by,
        actor_kind=ActorKind.SECURITY_REVIEWER,
        action_type="exception_disposed",
        affected_object_type="exception_record",
        affected_object_id=record.id,
        after_state={"dimension": dim.value, "disposition": disp.value},
    )
    await db.commit()
    return record


async def revoke_attestation(
    db: AsyncSession, *, poc_request_id: str, dimension: str, actor_id: str, actor_kind: ActorKind
) -> None:
    """D4 section 8.3: Security Reviewer, Final Approver, or the
    Environment Owner may revoke at any time -- never the AI (no
    AI-facing route exists for this function).
    """
    dim = ReadinessDimension(dimension)

    exc_result = await db.execute(
        select(ExceptionRecord)
        .where(
            ExceptionRecord.poc_request_id == poc_request_id,
            ExceptionRecord.dimension == dim,
            ExceptionRecord.revoked.is_(False),
        )
        .order_by(ExceptionRecord.created_at.desc())
        .limit(1)
    )
    exception = exc_result.scalar_one_or_none()

    if exception is not None:
        exception.revoked = True
        exception.revoked_by = actor_id
        exception.revoked_at = datetime.now(timezone.utc)
    else:
        att_result = await db.execute(
            select(EnvironmentReadinessAttestation).where(
                EnvironmentReadinessAttestation.poc_request_id == poc_request_id,
                EnvironmentReadinessAttestation.dimension == dim,
            )
        )
        attestation = att_result.scalar_one_or_none()
        if attestation is None:
            raise NotFoundError(f"No attestation exists for dimension {dim.value!r} on this POC request.")
        # An Attested (no-exception) dimension that's revoked reverts to
        # In Progress, not Not Started -- the prior attestation attempt
        # is a fact that happened, not erased (D4 section 8.3).
        attestation.status = AttestationStatus.IN_PROGRESS
    await db.flush()

    # D4 section 8.3: a revocation IS itself an invalidating change --
    # catches a revoked sign-off twice over, here and via P1's fresh
    # recompute at approval-commit time (TASD-v1.0.md section 16.5).
    await versioning.bump_input_version(db, poc_request_id=poc_request_id)

    await audit_service.record_event(
        db,
        actor_id=actor_id,
        actor_kind=actor_kind,
        action_type="attestation_revoked",
        affected_object_type="environment_readiness_attestation",
        affected_object_id=f"{poc_request_id}:{dim.value}",
        after_state={"dimension": dim.value},
    )
    await db.commit()


async def compute_final_signoff(db: AsyncSession, *, poc_request_id: str) -> bool:
    """D4 section 6's computation rule, feeding B-01 (Layer 2) and P1
    (approval). Called fresh every time -- never cached.
    """
    result = await db.execute(
        select(EnvironmentReadinessAttestation).where(
            EnvironmentReadinessAttestation.poc_request_id == poc_request_id
        )
    )
    attestations = {a.dimension: a for a in result.scalars().all()}

    for dim in ALL_DIMENSIONS:
        attestation = attestations.get(dim)
        if attestation is None or attestation.status in (AttestationStatus.NOT_STARTED, AttestationStatus.IN_PROGRESS):
            return False
        if attestation.status == AttestationStatus.ATTESTED:
            continue
        if attestation.status == AttestationStatus.ATTESTED_WITH_EXCEPTION:
            exc_result = await db.execute(
                select(ExceptionRecord)
                .where(
                    ExceptionRecord.poc_request_id == poc_request_id,
                    ExceptionRecord.dimension == dim,
                    ExceptionRecord.revoked.is_(False),
                )
                .order_by(ExceptionRecord.created_at.desc())
                .limit(1)
            )
            exception = exc_result.scalar_one_or_none()
            if exception is None:
                return False
            if exception.disposition != ExceptionDisposition.ACCEPTED:
                return False
            if dim in NON_WAIVABLE_DIMENSIONS:
                return False  # unreachable given the CHECK constraint; defense in depth
            if exception.revoked:
                return False
            if exception.expiry_date < date.today():
                return False
    return True


async def list_attestations(db: AsyncSession, *, poc_request_id: str) -> list[EnvironmentReadinessAttestation]:
    result = await db.execute(
        select(EnvironmentReadinessAttestation).where(
            EnvironmentReadinessAttestation.poc_request_id == poc_request_id
        )
    )
    return list(result.scalars().all())
