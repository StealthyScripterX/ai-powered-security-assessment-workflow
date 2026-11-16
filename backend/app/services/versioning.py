"""AssessmentInputVersion bumping -- D2-AI-Governance.md section 8.5,
architecture/TASD-v1.0.md section 11.8.

`bump_input_version` recomputes ALL FIVE hashes from current database
state and inserts a new `AssessmentInputVersion` row every time it is
called (a conservative, always-bump policy rather than a diff-detecting
one -- correct, if not the most efficient; see IMPLEMENTATION-NOTES.md).
It is called at the end of every service-layer function that performs
one of D2 section 8.5's eight invalidating-change types: scope changes
(scope_service), evidence/mapping/mapping-review changes
(evidence_service, mapping_service), environment attestation/exception/
revocation changes (environment_service), and questionnaire changes
(scope_service's submit_answers).

The staleness test itself (consumed by approval_service as P4) is a
PLAIN INTEGER COMPARISON against `poc_request.current_input_version` --
these hashes exist for forensic "what changed" answers, never for the
staleness check itself (D2 section 8.5, explicit on this point).
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engine import AssessmentInputVersion, PolicyConfig
from app.models.environment import EnvironmentReadinessAttestation, ExceptionRecord
from app.models.evidence import ControlEvidenceState, EvidenceArtifact
from app.models.mapping import MappingEvidenceLink, MappingRecord
from app.models.poc_request import PocRequest
from app.models.questionnaire import QuestionnaireAnswer, QuestionnaireQuestion
from app.models.scope_submission import ScopeSubmission


class VersionConflictError(RuntimeError):
    """Two concurrent writers both tried to bump current_input_version
    for the same POC request at the same instant -- an optimistic-
    concurrency conflict, not data corruption: the losing writer's
    ENTIRE transaction is rolled back here (every change the request
    made, not just this insert), so the database is left exactly as
    the winning writer left it -- the same atomicity guarantee
    app/services/audit_service.py's module docstring describes for a
    failed audit write blocking its transition.

    On PostgreSQL this is prevented outright by the `with_for_update()`
    lock on `poc_request` below: the second writer's SELECT blocks
    until the first writer commits, then reads the now-current version
    and never collides. It can still occur under this phase's SQLite
    dev database, which has no row-level locking at all (`with_for_update()`
    is a silent no-op there -- see the comment at its call site). The
    route layer (app/main.py's exception handler) turns this into an
    HTTP 409 Conflict, never an unhandled 500.
    """


def _hash_json(value: Any) -> str:
    serialized = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


async def _scope_hash(db: AsyncSession, poc_request: PocRequest) -> str:
    if poc_request.current_scope_id is None:
        return _hash_json(None)
    result = await db.execute(select(ScopeSubmission).where(ScopeSubmission.id == poc_request.current_scope_id))
    scope = result.scalar_one()
    return _hash_json(
        {
            "project_description": scope.project_description,
            "systems_in_scope": scope.systems_in_scope,
            "business_justification": scope.business_justification,
            "intake_form_data": scope.intake_form_data,
        }
    )


async def _evidence_state_hash(db: AsyncSession, poc_request_id: str) -> str:
    states = await db.execute(
        select(ControlEvidenceState).where(ControlEvidenceState.poc_request_id == poc_request_id)
    )
    artifacts = await db.execute(
        select(EvidenceArtifact).where(
            EvidenceArtifact.poc_request_id == poc_request_id, EvidenceArtifact.deleted_at.is_(None)
        )
    )
    return _hash_json(
        {
            "states": sorted(
                [{"control_id": s.control_id, "state": s.state.value} for s in states.scalars().all()],
                key=lambda d: d["control_id"],
            ),
            "artifacts": sorted(
                [
                    {"id": a.id, "control_id": a.control_id, "sha256": a.content_sha256, "uploaded_at": str(a.uploaded_at)}
                    for a in artifacts.scalars().all()
                ],
                key=lambda d: d["id"],
            ),
        }
    )


async def _mapping_hash(db: AsyncSession, poc_request_id: str) -> str:
    """Covers control_id, confidence, review_status, rationale (D2 section
    8.5 Round 5 fix) plus every evidence-control link. Excludes
    framework, provenance_tag (fixed/constant), and answer_excerpt
    (covered via the questionnaire pathway instead).
    """
    mappings = await db.execute(select(MappingRecord).where(MappingRecord.poc_request_id == poc_request_id))
    links = await db.execute(
        select(MappingEvidenceLink)
        .join(MappingRecord, MappingEvidenceLink.mapping_record_id == MappingRecord.id)
        .where(MappingRecord.poc_request_id == poc_request_id)
    )
    return _hash_json(
        {
            "mappings": sorted(
                [
                    {
                        "id": m.id,
                        "control_id": m.control_id,
                        "confidence": m.confidence.value,
                        "review_status": m.review_status.value,
                        "rationale": m.rationale,
                    }
                    for m in mappings.scalars().all()
                ],
                key=lambda d: d["id"],
            ),
            "links": sorted(
                [{"mapping_id": l.mapping_record_id, "evidence_id": l.evidence_artifact_id} for l in links.scalars().all()],
                key=lambda d: (d["mapping_id"], d["evidence_id"]),
            ),
        }
    )


async def _questionnaire_hash(db: AsyncSession, poc_request_id: str) -> str:
    answers = await db.execute(
        select(QuestionnaireAnswer)
        .join(QuestionnaireQuestion, QuestionnaireAnswer.question_id == QuestionnaireQuestion.id)
        .where(QuestionnaireQuestion.poc_request_id == poc_request_id)
    )
    return _hash_json(
        sorted(
            [{"id": a.id, "answer_text": a.answer_text} for a in answers.scalars().all()],
            key=lambda d: d["id"],
        )
    )


async def _environment_readiness_hash(db: AsyncSession, poc_request_id: str) -> str:
    attestations = await db.execute(
        select(EnvironmentReadinessAttestation).where(
            EnvironmentReadinessAttestation.poc_request_id == poc_request_id
        )
    )
    exceptions = await db.execute(
        select(ExceptionRecord).where(ExceptionRecord.poc_request_id == poc_request_id)
    )
    from app.services.environment_service import compute_final_signoff

    final_signoff = await compute_final_signoff(db, poc_request_id=poc_request_id)
    return _hash_json(
        {
            "attestations": sorted(
                [
                    {"dimension": a.dimension.value, "status": a.status.value, "text": a.attestation_text}
                    for a in attestations.scalars().all()
                ],
                key=lambda d: d["dimension"],
            ),
            "exceptions": sorted(
                [
                    {
                        "id": e.id,
                        "dimension": e.dimension.value,
                        "disposition": e.disposition.value,
                        "disposition_rationale": e.disposition_rationale,
                        "remediation_owner": e.remediation_owner,
                        "remediation_deadline": str(e.remediation_deadline),
                        "expiry_date": str(e.expiry_date),
                        "revoked": e.revoked,
                        "revoked_by": e.revoked_by,
                    }
                    for e in exceptions.scalars().all()
                ],
                key=lambda d: d["id"],
            ),
            "final_signoff_boolean": final_signoff,
        }
    )


async def bump_input_version(db: AsyncSession, *, poc_request_id: str) -> int:
    """Recomputes all five hashes and inserts a new AssessmentInputVersion.
    Returns the new version number. Caller is responsible for committing
    (this flushes but does not commit, consistent with every other
    service function's audit-then-commit pattern).
    """
    # FOR UPDATE: this read-then-increment of current_input_version is
    # exactly the TOCTOU shape architecture/TASD-v1.0.md section 11.9
    # calls out -- locks the row against a concurrent bump (or a
    # concurrent approval-decision read of the same row, see
    # app/services/approval_service.py) so two overlapping writers can
    # never both compute the same `new_version`. SQLAlchemy's sqlite
    # dialect silently omits the FOR UPDATE clause (no row-level locking
    # concept there), so this is a no-op under the dev/test SQLite
    # database and a real row lock once this runs against PostgreSQL --
    # same code path, no branch on dialect.
    result = await db.execute(select(PocRequest).where(PocRequest.id == poc_request_id).with_for_update())
    poc_request = result.scalar_one()

    policy_result = await db.execute(select(PolicyConfig).order_by(PolicyConfig.version.desc()).limit(1))
    active_policy = policy_result.scalar_one_or_none()

    new_version = poc_request.current_input_version + 1
    row = AssessmentInputVersion(
        poc_request_id=poc_request_id,
        version=new_version,
        scope_hash=await _scope_hash(db, poc_request),
        evidence_state_hash=await _evidence_state_hash(db, poc_request_id),
        mapping_hash=await _mapping_hash(db, poc_request_id),
        questionnaire_hash=await _questionnaire_hash(db, poc_request_id),
        environment_readiness_hash=await _environment_readiness_hash(db, poc_request_id),
        policy_config_version=active_policy.version if active_policy else None,
    )
    db.add(row)
    poc_request.current_input_version = new_version
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise VersionConflictError(
            f"Concurrent update conflict on POC request {poc_request_id}; retry the request."
        ) from exc
    return new_version
