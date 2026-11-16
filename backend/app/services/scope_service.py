"""Scope submission, questionnaire generation, and answer persistence --
the service layer behind the Phase 1 vertical slice's API routes.

Each public function here does exactly one state-changing thing and
writes its audit entry in the SAME session/transaction before the
caller commits (BR-019) -- see app/services/audit_service.py.
"""
from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ActorKind
from app.models.poc_request import PocRequest, PocRequestStatus
from app.models.questionnaire import AnswerUsability, QuestionnaireAnswer, QuestionnaireQuestion
from app.models.scope_submission import ScopeSubmission
from app.services import audit_service, versioning
from app.services.ai.client import ModelClient
from app.services.ai.questionnaire import QuestionnaireResult, generate_questionnaire


class NotFoundError(RuntimeError):
    pass


class ForbiddenError(RuntimeError):
    pass


def _classify_usability(answer_text: str) -> AnswerUsability:
    stripped = answer_text.strip()
    if not stripped:
        return AnswerUsability.BLANK
    # A short, low-content answer is flagged non-responsive; the exact
    # threshold is NOT invented here -- this is a crude placeholder for
    # D2 section 8.1 Rule 3's unusable-answer signal, which TASD-v1.0.md
    # section 14.7 correctly leaves unconfigured (OD-10) rather than
    # guessing a number. This classification only feeds the `usability`
    # column; no Completeness/blocker/risk decision is made from it in
    # this phase.
    if len(stripped) < 3:
        return AnswerUsability.NON_RESPONSIVE
    return AnswerUsability.USABLE


async def submit_scope(
    db: AsyncSession,
    *,
    requester_id: str,
    project_description: str,
    systems_in_scope: str,
    business_justification: str,
    intake_form_data: dict,
) -> tuple[PocRequest, ScopeSubmission]:
    """BR-001: creates a new PocRequest + its first ScopeSubmission
    version. Establishes input_version = 1 (D2 section 8.5: "creation of
    the scope submission establishes the request's first version").
    """
    poc_request = PocRequest(
        requester_id=requester_id,
        status=PocRequestStatus.IN_PROGRESS,
        current_input_version=1,
    )
    db.add(poc_request)
    await db.flush()

    scope = ScopeSubmission(
        poc_request_id=poc_request.id,
        version=1,
        project_description=project_description,
        systems_in_scope=systems_in_scope,
        business_justification=business_justification,
        intake_form_data=intake_form_data,
        submitted_by=requester_id,
    )
    db.add(scope)
    await db.flush()

    poc_request.current_scope_id = scope.id
    await db.flush()

    await audit_service.record_event(
        db,
        actor_id=requester_id,
        actor_kind=ActorKind.REQUESTER,
        action_type="scope_submitted",
        affected_object_type="poc_request",
        affected_object_id=poc_request.id,
        after_state={
            "status": poc_request.status.value,
            "scope_submission_id": scope.id,
            "input_version": poc_request.current_input_version,
        },
    )
    await db.commit()
    return poc_request, scope


async def get_poc_request_for_requester(db: AsyncSession, poc_request_id: str, requester_id: str) -> PocRequest:
    result = await db.execute(select(PocRequest).where(PocRequest.id == poc_request_id))
    poc_request = result.scalar_one_or_none()
    if poc_request is None:
        raise NotFoundError(f"POC request {poc_request_id} not found.")
    if poc_request.requester_id != requester_id:
        raise ForbiddenError("This POC request belongs to a different requester.")
    return poc_request


async def get_poc_request_or_404(db: AsyncSession, poc_request_id: str) -> PocRequest:
    """No ownership check -- for cross-cutting roles (SecurityReviewer,
    EnvironmentOwner, FinalApprover, ComplianceAuditor) that are
    expected to act on any assessment, not just their own. Routes are
    responsible for applying the Requester-only ownership check
    themselves when the caller's role is Requester (see
    app/api/routes/mapping.py's list_mappings for the established
    pattern).
    """
    result = await db.execute(select(PocRequest).where(PocRequest.id == poc_request_id))
    poc_request = result.scalar_one_or_none()
    if poc_request is None:
        raise NotFoundError(f"POC request {poc_request_id} not found.")
    return poc_request


async def generate_questionnaire_for_request(
    db: AsyncSession,
    *,
    poc_request_id: str,
    requester_id: str,
    client: ModelClient,
) -> tuple[list[QuestionnaireQuestion], QuestionnaireResult]:
    """Runs AI scope analysis, enforces BR-002/BR-003 server-side
    (app/services/ai/questionnaire.py), and persists exactly the
    surviving question set -- dropped-for-cap candidates are persisted
    too (with dropped_for_cap=True), never silently discarded (D2
    section 7).
    """
    poc_request = await get_poc_request_for_requester(db, poc_request_id, requester_id)
    scope_result = await db.execute(select(ScopeSubmission).where(ScopeSubmission.id == poc_request.current_scope_id))
    scope = scope_result.scalar_one()

    result = await generate_questionnaire(
        client,
        project_description=scope.project_description,
        systems_in_scope=scope.systems_in_scope,
        business_justification=scope.business_justification,
    )

    persisted: list[QuestionnaireQuestion] = []
    for gq in [*result.questions, *result.dropped_candidates]:
        row = QuestionnaireQuestion(
            poc_request_id=poc_request.id,
            input_version=poc_request.current_input_version,
            domain_label=gq.domain_label,
            is_mandatory_domain=gq.is_mandatory_domain,
            trigger_basis=gq.trigger_basis,
            question_text=gq.question_text,
            sequence=gq.sequence,
            dropped_for_cap=gq.dropped_for_cap,
        )
        db.add(row)
        persisted.append(row)
    await db.flush()

    await audit_service.record_event(
        db,
        actor_id=None,
        actor_kind=ActorKind.AI_AGENT,
        action_type="questionnaire_generated",
        affected_object_type="poc_request",
        affected_object_id=poc_request.id,
        after_state={
            "question_count": len(result.questions),
            "dropped_for_cap_count": len(result.dropped_candidates),
            "identified_gaps": result.identified_gaps,
            "identified_assumptions": result.identified_assumptions,
            "input_version": poc_request.current_input_version,
        },
    )
    await db.commit()
    return [q for q in persisted if not q.dropped_for_cap], result


async def submit_answers(
    db: AsyncSession,
    *,
    poc_request_id: str,
    requester_id: str,
    answers: list[tuple[str, str]],  # (question_id, answer_text)
) -> list[QuestionnaireAnswer]:
    """BR-008/D2 section 6: every answer row is persisted with provenance
    pinned to REQUESTER_FACT (enforced again by a CHECK constraint in
    app/models/questionnaire.py) and stamped with the POC request's
    CURRENT input_version at the moment of answering.
    """
    poc_request = await get_poc_request_for_requester(db, poc_request_id, requester_id)

    question_ids = [q_id for q_id, _ in answers]
    result = await db.execute(
        select(QuestionnaireQuestion).where(QuestionnaireQuestion.id.in_(question_ids))
    )
    questions_by_id = {q.id: q for q in result.scalars().all()}

    rows: list[QuestionnaireAnswer] = []
    for question_id, answer_text in answers:
        question = questions_by_id.get(question_id)
        if question is None or question.poc_request_id != poc_request.id:
            raise NotFoundError(f"Question {question_id} does not belong to this POC request.")
        row = QuestionnaireAnswer(
            question_id=question_id,
            input_version=poc_request.current_input_version,
            provenance_tag="REQUESTER_FACT",
            answer_text=answer_text,
            usability=_classify_usability(answer_text),
            answered_by=requester_id,
        )
        db.add(row)
        rows.append(row)
    await db.flush()

    # D2 section 8.5 invalidating change 6 (questionnaire changes).
    await versioning.bump_input_version(db, poc_request_id=poc_request.id)

    await audit_service.record_event(
        db,
        actor_id=requester_id,
        actor_kind=ActorKind.REQUESTER,
        action_type="answers_submitted",
        affected_object_type="poc_request",
        affected_object_id=poc_request.id,
        after_state={
            "answer_count": len(rows),
            "input_version": poc_request.current_input_version,
        },
    )
    await db.commit()
    return rows
