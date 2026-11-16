"""Assembles EngineInput from the database, calls the pure
app.services.engine.evaluate(), and persists the result -- the only
place in the codebase that both touches the database AND calls the
engine. The engine function itself remains pure (app/services/engine.py).

D2-AI-Governance.md section 8's re-run trigger rule: the engine does not
eagerly re-run on every invalidating change. It runs on (a) an explicit
re-submission (this module's `run_engine`, called by a dedicated API
route) or (b) automatically inside the approval transaction on a P4
staleness failure (app/services/approval_service.py).
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ActorKind
from app.models.catalog import Control, ControlDomain
from app.models.engine import PolicyConfig, Recommendation
from app.models.engine_enums import EngineOutcome
from app.models.environment import EnvironmentReadinessAttestation
from app.models.evidence import ControlEvidenceState, EvidenceState
from app.models.mapping import MappingRecord
from app.models.poc_request import PocRequest
from app.models.questionnaire import AnswerUsability, QuestionnaireAnswer, QuestionnaireQuestion
from app.services import audit_service, environment_service
from app.services.ai.questionnaire import MANDATORY_DOMAINS
from app.services.engine import EngineInput, PolicyConfigSnapshot, evaluate


async def _get_active_policy(db: AsyncSession) -> PolicyConfigSnapshot:
    result = await db.execute(select(PolicyConfig).order_by(PolicyConfig.version.desc()).limit(1))
    config = result.scalar_one_or_none()
    if config is None:
        return PolicyConfigSnapshot(None, [], None, None)
    return PolicyConfigSnapshot(
        layer1_completeness_threshold=config.layer1_completeness_threshold,
        layer2_policy_hooks=config.layer2_policy_hooks or [],
        layer3_weights=config.layer3_weights,
        layer3_thresholds=config.layer3_thresholds,
    )


async def _assemble_engine_input(db: AsyncSession, poc_request: PocRequest) -> EngineInput:
    # Layer 1 inputs.
    questions = await db.execute(
        select(QuestionnaireQuestion).where(
            QuestionnaireQuestion.poc_request_id == poc_request.id,
            QuestionnaireQuestion.dropped_for_cap == False,  # noqa: E712
        )
    )
    questions_by_domain: dict[str, list[str]] = {}
    for q in questions.scalars().all():
        questions_by_domain.setdefault(q.domain_label, []).append(q.id)

    answers = await db.execute(
        select(QuestionnaireAnswer)
        .join(QuestionnaireQuestion, QuestionnaireAnswer.question_id == QuestionnaireQuestion.id)
        .where(QuestionnaireQuestion.poc_request_id == poc_request.id)
    )
    all_answers = answers.scalars().all()
    answered_question_ids = {a.question_id for a in all_answers}
    unusable_count = sum(1 for a in all_answers if a.usability != AnswerUsability.USABLE)

    mandatory_domain_coverage = {
        domain: any(qid in answered_question_ids for qid in questions_by_domain.get(domain, []))
        for domain in MANDATORY_DOMAINS
    }

    env_submitted_result = await db.execute(
        select(EnvironmentReadinessAttestation.poc_request_id)
        .where(EnvironmentReadinessAttestation.poc_request_id == poc_request.id)
        .limit(1)
    )
    environment_readiness_submitted = env_submitted_result.first() is not None

    # Layer 2 inputs.
    final_signoff = await environment_service.compute_final_signoff(db, poc_request_id=poc_request.id)

    # Layer 3 inputs: current (non-superseded) mapping per control, joined to evidence state.
    mapping_rows = await db.execute(select(MappingRecord).where(MappingRecord.poc_request_id == poc_request.id))
    all_mappings = list(mapping_rows.scalars().all())
    superseded_ids = {m.supersedes_id for m in all_mappings if m.supersedes_id}
    current_mappings = [m for m in all_mappings if m.id not in superseded_ids]

    confidence_by_control = {m.control_id: m.confidence for m in current_mappings}
    review_status_by_control = {m.control_id: m.review_status for m in current_mappings}

    evidence_rows = await db.execute(
        select(ControlEvidenceState).where(ControlEvidenceState.poc_request_id == poc_request.id)
    )
    evidence_by_control = {e.control_id: e.state for e in evidence_rows.scalars().all()}
    # Every mapped control that has no evidence row yet is implicitly Not Provided.
    for control_id in confidence_by_control:
        evidence_by_control.setdefault(control_id, EvidenceState.NOT_PROVIDED)

    return EngineInput(
        poc_request_id=poc_request.id,
        input_version=poc_request.current_input_version,
        mandatory_domain_coverage=mandatory_domain_coverage,
        environment_readiness_submitted=environment_readiness_submitted,
        unusable_answer_count=unusable_count,
        total_answer_count=len(all_answers),
        final_signoff_boolean=final_signoff,
        missing_evidence_on_always_required_controls=[],  # OD-11 safe default: no hooks elevated
        policy_hook_blockers_fired=[],
        mapping_confidence_by_control=confidence_by_control,
        mapping_review_status_by_control=review_status_by_control,
        evidence_state_by_control=evidence_by_control,
    )


class EngineRefusedError(RuntimeError):
    """Raised when the engine refuses to produce an outcome because a
    blocking Open Decision is unconfigured. Carries the exact missing
    configuration so the caller can surface it plainly -- never papered
    over with a default.
    """

    def __init__(self, missing_config: list[str]):
        self.missing_config = missing_config
        super().__init__("Decision engine refused: " + "; ".join(missing_config))


async def run_engine(db: AsyncSession, *, poc_request_id: str) -> Recommendation:
    result = await db.execute(select(PocRequest).where(PocRequest.id == poc_request_id))
    poc_request = result.scalar_one_or_none()
    if poc_request is None:
        raise ValueError(f"POC request {poc_request_id} not found.")

    engine_input = await _assemble_engine_input(db, poc_request)
    config = await _get_active_policy(db)
    output = evaluate(engine_input, config)

    if output.refused:
        await audit_service.record_event(
            db,
            actor_id=None,
            actor_kind=ActorKind.DECISION_ENGINE,
            action_type="engine_refused",
            affected_object_type="poc_request",
            affected_object_id=poc_request.id,
            after_state={"missing_config": output.missing_config},
        )
        await db.commit()
        raise EngineRefusedError(output.missing_config)

    recommendation = Recommendation(
        id=str(uuid.uuid4()),
        poc_request_id=poc_request.id,
        input_version=poc_request.current_input_version,
        outcome=output.outcome,
        risk_tier=output.risk_tier,
        rationale="; ".join(output.rationale) if output.rationale else "No residual findings flagged.",
        decision_layer_attribution=output.decision_layer_attribution,
    )
    db.add(recommendation)
    await db.flush()

    await audit_service.record_event(
        db,
        actor_id=None,
        actor_kind=ActorKind.DECISION_ENGINE,
        action_type="recommendation_produced",
        affected_object_type="recommendation",
        affected_object_id=recommendation.id,
        after_state={
            "outcome": output.outcome.value,
            "risk_tier": output.risk_tier.value if output.risk_tier else None,
            "decision_layer_attribution": output.decision_layer_attribution,
            "input_version": poc_request.current_input_version,
        },
    )
    await db.commit()
    return recommendation


async def get_current_recommendation(db: AsyncSession, *, poc_request_id: str) -> Recommendation | None:
    result = await db.execute(
        select(Recommendation)
        .where(Recommendation.poc_request_id == poc_request_id)
        .order_by(Recommendation.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()
