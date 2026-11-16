"""The central AI orchestration layer.

This module is a FACADE, not a reimplementation: every operation here
delegates to the existing, already-tested service modules
(scope_service, mapping_service, engine_orchestration,
evidence_service, environment_service). Its job is to give the rest of
the application -- and in particular the "AI Assessment Workspace"
frontend screen -- ONE coherent entry point for "where is this
assessment's AI-driven lifecycle at," rather than scattering that
question across five service modules' call sites.

Structural guarantee, restated here because this is the module a future
reader is most likely to reach for when tempted to add a shortcut: the
AI agent's write surface is EXACTLY the union of what
app.services.ai.questionnaire and app.services.ai.mapping already write
(questionnaire_question rows and mapping_record rows, both via their
existing service functions) -- this facade adds NO new write path and
in particular never touches `control_evidence_state`,
`environment_readiness_attestation`, `exception_record`,
`approval_decision`, or `recommendation`. Those remain exclusively
human- or engine-owned, exactly as app/services/evidence_service.py,
environment_service.py, approval_service.py, and engine.py already
enforce. This module cannot "override the deterministic decision
engine" because it never calls app.services.engine at all -- reading a
recommendation (via engine_orchestration.get_current_recommendation) is
the only interaction it has with the engine, and that is read-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.engine import Recommendation
from app.models.environment import EnvironmentReadinessAttestation
from app.models.evidence import ControlEvidenceState
from app.models.mapping import MappingRecord
from app.models.poc_request import PocRequest
from app.models.questionnaire import QuestionnaireAnswer, QuestionnaireQuestion
from app.models.scope_submission import ScopeSubmission
from app.services import engine_orchestration, environment_service, evidence_service, mapping_service, scope_service
from app.services.ai.client import ModelClient
from app.services.ai.questionnaire import QuestionnaireResult


@dataclass
class ScopeAnalysisResult:
    """BR-008: what the AI found when it analyzed the submitted scope --
    gaps, assumptions, and the resulting question set. Nothing here is
    authoritative; it is the draft a human reviewer evaluates alongside
    the raw scope text, never instead of it (D2-AI-Governance.md section
    9.3 / architecture/TASD-v1.0.md section 17.3).
    """

    questions: list[QuestionnaireQuestion]
    identified_gaps: list[str]
    identified_assumptions: list[str]
    dropped_candidate_count: int


async def analyze_scope(
    db: AsyncSession, *, poc_request_id: str, requester_id: str, client: ModelClient
) -> ScopeAnalysisResult:
    """Step 1 of the agent's lifecycle: scope analysis -> 11-15
    questions. Delegates entirely to
    app.services.scope_service.generate_questionnaire_for_request, which
    already enforces BR-002/BR-003 server-side
    (app/services/ai/questionnaire.py) -- this function adds no new
    validation, only exposes the result in the shape the workspace
    screen and the central agent's callers want.
    """
    questions, result = await scope_service.generate_questionnaire_for_request(
        db, poc_request_id=poc_request_id, requester_id=requester_id, client=client
    )
    return ScopeAnalysisResult(
        questions=questions,
        identified_gaps=result.identified_gaps,
        identified_assumptions=result.identified_assumptions,
        dropped_candidate_count=len(result.dropped_candidates),
    )


@dataclass
class AnswerProcessingResult:
    """BR-008's second half: once answers are in, what is still
    unanswered or flagged unusable (contradictory/blank/non-responsive).
    This is descriptive -- it does NOT decide Layer 1 Completeness
    (that is the Decision Engine's job, app/services/engine.py Rule 3,
    gated on OD-10); it only surfaces the same `usability` classification
    already persisted by scope_service.submit_answers so a reviewer (or
    the workspace UI) can see it without re-deriving it.
    """

    answered_count: int
    unanswered_question_ids: list[str]
    unusable_answer_ids: list[str]


async def process_answers(db: AsyncSession, *, poc_request_id: str) -> AnswerProcessingResult:
    """Step 2: after app.services.scope_service.submit_answers has
    already persisted the answers (with provenance and version, per
    D2-AI-Governance.md section 6/8.5), this reads back which questions
    remain unanswered and which answers were classified unusable --
    read-only, no new writes.
    """
    from app.models.questionnaire import AnswerUsability

    questions = await db.execute(
        select(QuestionnaireQuestion).where(
            QuestionnaireQuestion.poc_request_id == poc_request_id,
            QuestionnaireQuestion.dropped_for_cap == False,  # noqa: E712
        )
    )
    all_questions = {q.id: q for q in questions.scalars().all()}

    answers = await db.execute(
        select(QuestionnaireAnswer)
        .join(QuestionnaireQuestion, QuestionnaireAnswer.question_id == QuestionnaireQuestion.id)
        .where(QuestionnaireQuestion.poc_request_id == poc_request_id)
    )
    all_answers = list(answers.scalars().all())
    answered_ids = {a.question_id for a in all_answers}

    return AnswerProcessingResult(
        answered_count=len(all_answers),
        unanswered_question_ids=[qid for qid in all_questions if qid not in answered_ids],
        unusable_answer_ids=[a.id for a in all_answers if a.usability != AnswerUsability.USABLE],
    )


async def propose_control_mappings(
    db: AsyncSession, *, poc_request_id: str, requester_id: str, client: ModelClient
) -> list[MappingRecord]:
    """Step 3: delegates entirely to
    app.services.mapping_service.generate_mappings_for_request, which
    already enforces the closed-catalog constraint
    (app/services/ai/mapping.py: "never invent ISO/NIST control
    mappings") -- no new validation added here.
    """
    return await mapping_service.generate_mappings_for_request(
        db, poc_request_id=poc_request_id, requester_id=requester_id, client=client
    )


@dataclass
class AssessmentSummary:
    """The consolidated read-model behind the 'AI Assessment Workspace'
    and every role's assessment-detail screen. Every field is read-only,
    assembled fresh from the existing tables -- this is a VIEW, not a
    new source of truth. The `provenance`/`review_status`/`evidence_state`
    three-axis separation (D2-AI-Governance.md section 6 /
    D3-Methodology.md section 8.2) is preserved: this dataclass carries
    all three as distinct fields on each item, never collapsed into one
    status string, matching the same contract
    app/api/routes/mapping.py's MappingOut and
    app/api/routes/evidence.py's EvidenceStateOut already expose over
    HTTP (this is the same data, assembled together for convenience).
    """

    poc_request_id: str
    status: str
    current_input_version: int
    scope: ScopeSubmission | None
    questions: list[QuestionnaireQuestion]
    answers: list[QuestionnaireAnswer]
    mappings: list[MappingRecord]
    evidence_states: list[ControlEvidenceState]
    environment_attestations: list[EnvironmentReadinessAttestation]
    final_signoff_boolean: bool
    recommendation: Recommendation | None
    identified_gaps: list[str] = field(default_factory=list)
    identified_assumptions: list[str] = field(default_factory=list)


async def get_assessment_summary(db: AsyncSession, *, poc_request_id: str) -> AssessmentSummary:
    """Assembles the full current state of one assessment from every
    existing module -- the single call the frontend's assessment-detail
    page makes instead of six separate round trips. Read-only; changes
    nothing.
    """
    pr_result = await db.execute(select(PocRequest).where(PocRequest.id == poc_request_id))
    poc_request = pr_result.scalar_one_or_none()
    if poc_request is None:
        raise scope_service.NotFoundError(f"POC request {poc_request_id} not found.")

    scope = None
    if poc_request.current_scope_id:
        scope_result = await db.execute(select(ScopeSubmission).where(ScopeSubmission.id == poc_request.current_scope_id))
        scope = scope_result.scalar_one_or_none()

    questions_result = await db.execute(
        select(QuestionnaireQuestion)
        .where(QuestionnaireQuestion.poc_request_id == poc_request_id, QuestionnaireQuestion.dropped_for_cap == False)  # noqa: E712
        .order_by(QuestionnaireQuestion.sequence)
    )
    questions = list(questions_result.scalars().all())

    answers_result = await db.execute(
        select(QuestionnaireAnswer)
        .join(QuestionnaireQuestion, QuestionnaireAnswer.question_id == QuestionnaireQuestion.id)
        .where(QuestionnaireQuestion.poc_request_id == poc_request_id)
    )
    answers = list(answers_result.scalars().all())

    mappings = await mapping_service.list_mappings(db, poc_request_id=poc_request_id)
    evidence_states = await evidence_service.list_evidence_states(db, poc_request_id=poc_request_id)
    attestations = await environment_service.list_attestations(db, poc_request_id=poc_request_id)
    final_signoff = await environment_service.compute_final_signoff(db, poc_request_id=poc_request_id)
    recommendation = await engine_orchestration.get_current_recommendation(db, poc_request_id=poc_request_id)

    return AssessmentSummary(
        poc_request_id=poc_request_id,
        status=poc_request.status.value,
        current_input_version=poc_request.current_input_version,
        scope=scope,
        questions=questions,
        answers=answers,
        mappings=mappings,
        evidence_states=evidence_states,
        environment_attestations=attestations,
        final_signoff_boolean=final_signoff,
        recommendation=recommendation,
    )
