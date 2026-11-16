"""Control mapping persistence and the Reviewer override state machine.

D3-Methodology section 8: every Reviewer action (Confirm/Adjust/Reject)
inserts a NEW `MappingRecord` row linked via `supersedes_id` -- never an
UPDATE of the AI's original row. Provenance stays `AI_ASSERTION` forever
(the AI proposed it); only `review_status` moves.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ActorKind
from app.models.catalog import Control, ControlDomain
from app.models.mapping import MappingConfidence, MappingRecord, MappingReviewStatus
from app.models.poc_request import PocRequest
from app.models.questionnaire import QuestionnaireAnswer, QuestionnaireQuestion
from app.services import audit_service, versioning
from app.services.ai.client import ModelClient
from app.services.ai.mapping import generate_mappings
from app.services.scope_service import get_poc_request_or_404


class MappingNotFoundError(RuntimeError):
    pass


async def _candidate_controls_for_domain(db: AsyncSession, domain_label: str) -> list[tuple[str, str]]:
    result = await db.execute(select(ControlDomain.id).where(ControlDomain.name == domain_label))
    domain_id = result.scalar_one_or_none()
    if domain_id is None:
        return []
    controls = await db.execute(select(Control.control_id, Control.title).where(Control.domain_id == domain_id))
    return list(controls.all())


async def generate_mappings_for_request(
    db: AsyncSession,
    *,
    poc_request_id: str,
    requester_id: str,
    client: ModelClient,
) -> list[MappingRecord]:
    """Fan out over every answered question for this POC request, drafting
    mapping records per answer against that question's domain's
    candidate controls (the closed set the AI may choose from).

    `requester_id` here is the ACTING user (logged for audit context
    where relevant), not necessarily the assessment's owning Requester --
    this endpoint is also reachable by SecurityReviewer, whose
    ownership-agnostic cross-cutting access the route
    (app/api/routes/mapping.py) already establishes; object-level
    ownership is enforced there for Requester callers specifically, not
    re-enforced here (see get_poc_request_or_404's docstring).
    """
    poc_request = await get_poc_request_or_404(db, poc_request_id)

    result = await db.execute(
        select(QuestionnaireAnswer, QuestionnaireQuestion)
        .join(QuestionnaireQuestion, QuestionnaireAnswer.question_id == QuestionnaireQuestion.id)
        .where(QuestionnaireQuestion.poc_request_id == poc_request_id)
    )
    rows = result.all()

    created: list[MappingRecord] = []
    for answer, question in rows:
        candidates = await _candidate_controls_for_domain(db, question.domain_label)
        if not candidates:
            continue
        proposals = await generate_mappings(client, answer_text=answer.answer_text, candidate_controls=candidates)
        for proposal in proposals:
            record = MappingRecord(
                poc_request_id=poc_request_id,
                answer_id=answer.id,
                control_id=proposal.control_id,
                provenance_tag="AI_ASSERTION",
                answer_excerpt=answer.answer_text[:500],
                confidence=MappingConfidence(proposal.confidence),
                rationale=proposal.rationale,
                review_status=MappingReviewStatus.PENDING_REVIEW,
                created_by=None,
            )
            db.add(record)
            created.append(record)
    await db.flush()

    if created:
        await versioning.bump_input_version(db, poc_request_id=poc_request.id)

    await audit_service.record_event(
        db,
        actor_id=None,
        actor_kind=ActorKind.AI_AGENT,
        action_type="mappings_generated",
        affected_object_type="poc_request",
        affected_object_id=poc_request.id,
        after_state={"mapping_count": len(created)},
    )
    await db.commit()
    return created


async def list_mappings(db: AsyncSession, *, poc_request_id: str) -> list[MappingRecord]:
    """"Current" view: a row that has been superseded by a later Reviewer
    action is excluded -- only the latest row per AI-origin/Reviewer-
    action chain is returned.
    """
    return _latest_per_chain(await _all_for_request(db, poc_request_id))


async def _all_for_request(db: AsyncSession, poc_request_id: str) -> list[MappingRecord]:
    result = await db.execute(
        select(MappingRecord).where(MappingRecord.poc_request_id == poc_request_id).order_by(MappingRecord.created_at)
    )
    return list(result.scalars().all())


def _latest_per_chain(rows: list[MappingRecord]) -> list[MappingRecord]:
    """Each Reviewer action creates a new row with supersedes_id pointing
    at the row it replaces. Return only the latest row per chain.
    """
    superseded_ids = {r.supersedes_id for r in rows if r.supersedes_id}
    return [r for r in rows if r.id not in superseded_ids]


async def review_mapping(
    db: AsyncSession,
    *,
    poc_request_id: str,
    mapping_id: str,
    reviewer_id: str,
    action: str,  # "Confirm" | "Adjust" | "Reject"
    control_id: str | None = None,
    confidence: str | None = None,
    rationale: str | None = None,
    reject_reason: str | None = None,
) -> MappingRecord:
    result = await db.execute(
        select(MappingRecord).where(MappingRecord.id == mapping_id, MappingRecord.poc_request_id == poc_request_id)
    )
    original = result.scalar_one_or_none()
    if original is None:
        raise MappingNotFoundError(f"Mapping {mapping_id} not found for this POC request.")

    if action == "Confirm":
        new_status = MappingReviewStatus.CONFIRMED
        new_control_id, new_confidence, new_rationale = original.control_id, original.confidence, original.rationale
    elif action == "Adjust":
        new_status = MappingReviewStatus.ADJUSTED
        new_control_id = control_id or original.control_id
        new_confidence = MappingConfidence(confidence) if confidence else original.confidence
        new_rationale = rationale or original.rationale
    elif action == "Reject":
        if not reject_reason or not reject_reason.strip():
            raise ValueError("A non-empty reject_reason is required to reject a mapping.")
        new_status = MappingReviewStatus.REJECTED
        new_control_id, new_confidence, new_rationale = original.control_id, original.confidence, original.rationale
    else:
        raise ValueError(f"Unknown review action: {action!r}")

    new_record = MappingRecord(
        poc_request_id=original.poc_request_id,
        answer_id=original.answer_id,
        control_id=new_control_id,
        provenance_tag="AI_ASSERTION",  # D3-Methodology section 8: provenance NEVER changes on review
        answer_excerpt=original.answer_excerpt,
        confidence=new_confidence,
        rationale=new_rationale,
        review_status=new_status,
        reject_reason=reject_reason if action == "Reject" else None,
        supersedes_id=original.id,
        created_by=reviewer_id,
    )
    db.add(new_record)
    await db.flush()

    # D2 section 8.5 invalidating change 4 (mapping-review changes).
    await versioning.bump_input_version(db, poc_request_id=original.poc_request_id)

    await audit_service.record_event(
        db,
        actor_id=reviewer_id,
        actor_kind=ActorKind.SECURITY_REVIEWER,
        action_type=f"mapping_review_{action.lower()}",
        affected_object_type="mapping_record",
        affected_object_id=new_record.id,
        before_state={"review_status": original.review_status.value, "control_id": original.control_id},
        after_state={"review_status": new_status.value, "control_id": new_control_id},
    )
    await db.commit()
    return new_record
