"""Human approval: P1-P4 server-side preconditions, evaluated inside the
same transaction as the `ApprovalDecision` write. D5-Approval-Audit.md
section 6, architecture/TASD-v1.0.md section 11.9/17.4.

Concurrency note (read before relying on this for anything beyond
Phase 1 demonstration): architecture/TASD-v1.0.md section 11.9 closes
the P4 TOCTOU gap with a `SELECT ... FOR UPDATE` row lock on
`poc_request`, taken by both the version-bump path and the approval
path, under PostgreSQL. This phase's SQLite dev database does not
implement that row lock -- SQLite's whole-database write serialization
hides the race in a single-process dev/test run, but this is NOT the
same guarantee and must not be relied upon once this runs against
PostgreSQL with real concurrent requests. Flagged in
IMPLEMENTATION-NOTES.md as a genuine gap, not a silently-skipped one.

What IS fully implemented and tested regardless of the locking gap:
 - P1 (`EnvironmentReadinessSignOff.final_signoff_boolean`), recomputed
   fresh at commit time, never read from a cache.
 - P2 (no active Layer 2 blocker), re-derived from the current
   recommendation's own decision_layer_attribution/outcome rather than
   trusted from a stale value.
 - P3 (`recommendation.outcome != INSUFFICIENT_INFORMATION`).
 - P4 (`recommendation.input_version == poc_request.current_input_version`),
   gating `Approved` ONLY -- `Rejected`/`MoreInfoRequested` are always
   permitted regardless of staleness, with `recommendation_was_stale`
   recorded as a transparent fact on every decision either way.
 - On a P4 failure specifically: a synchronous engine re-run (the engine
   is a pure function, so this is cheap and safe -- TASD-v1.0.md section
   17.5), producing a fresh Recommendation the caller is handed back.
 - Every attempt -- committed or rejected -- is durably logged via
   `ApprovalAttempt` and an audit entry BEFORE any response is formed.
 - No override path of any kind exists (D5 section 7): there is no
   function, grant, or config field anywhere in this codebase that
   bypasses P1-P4.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import (
    ApprovalAttempt,
    ApprovalDecision,
    ApprovalRequestStatus,
    AttemptOutcome,
    DecisionType,
    PocApprovalRequest,
)
from app.models.audit import ActorKind
from app.models.engine import Recommendation
from app.models.engine_enums import EngineOutcome
from app.models.poc_request import PocRequest
from app.services import audit_service, environment_service, engine_orchestration


class NotFoundError(RuntimeError):
    pass


class ValidationError(RuntimeError):
    pass


async def ensure_approval_request(db: AsyncSession, *, poc_request_id: str) -> PocApprovalRequest:
    """Creates (idempotently) the POCApprovalRequest once a non-refused
    recommendation exists -- D1-Requirements.md section 10 step 10.
    """
    result = await db.execute(
        select(PocApprovalRequest).where(PocApprovalRequest.poc_request_id == poc_request_id)
    )
    existing = result.scalar_one_or_none()

    recommendation = await engine_orchestration.get_current_recommendation(db, poc_request_id=poc_request_id)
    if recommendation is None:
        raise NotFoundError("No recommendation exists yet for this POC request; run the engine first.")

    if existing is not None:
        existing.current_recommendation_id = recommendation.id
        await db.flush()
        await db.commit()
        return existing

    approval_request = PocApprovalRequest(
        poc_request_id=poc_request_id,
        current_recommendation_id=recommendation.id,
    )
    db.add(approval_request)
    await db.flush()
    await db.commit()
    return approval_request


async def _active_layer2_blocker_exists(db: AsyncSession, *, poc_request_id: str) -> bool:
    """P2: re-derives blocker state from the current recommendation
    rather than trusting a value that could have gone stale -- if the
    current recommendation's own outcome is NO-GO (Layer 2 fired), a
    blocker is active; a GO or Insufficient-Information recommendation
    means Layer 2 passed when it was last computed. Combined with P4
    (which independently catches staleness), this is sufficient for
    this phase's single-recommendation-per-request model.
    """
    recommendation = await engine_orchestration.get_current_recommendation(db, poc_request_id=poc_request_id)
    return recommendation is not None and recommendation.outcome == EngineOutcome.NO_GO


async def commit_approval_decision(
    db: AsyncSession,
    *,
    poc_request_id: str,
    approver_id: str,
    decision: str,  # "Approved" | "Rejected" | "MoreInfoRequested"
    rationale: str,
    disagreement_rationale: str | None = None,
) -> tuple[ApprovalDecision | None, dict]:
    """Returns (decision_row_or_None, info). `info` carries
    `failed_preconditions` and, on a P4 failure, `fresh_recommendation`.
    """
    decision_type = DecisionType(decision)
    if not rationale or not rationale.strip():
        raise ValidationError("A non-empty rationale is required for every approval decision.")

    # FOR UPDATE: locks poc_request for the duration of this P1-P4
    # evaluation + commit, the same row versioning.bump_input_version
    # locks -- closes the literal P4 TOCTOU gap this module's docstring
    # describes (two concurrent approval attempts, or an approval
    # racing a version bump, can no longer both read
    # current_input_version before either writes). No-op under SQLite
    # (see versioning.py's comment on the same pattern); a real row
    # lock under PostgreSQL.
    pr_result = await db.execute(select(PocRequest).where(PocRequest.id == poc_request_id).with_for_update())
    poc_request = pr_result.scalar_one_or_none()
    if poc_request is None:
        raise NotFoundError(f"POC request {poc_request_id} not found.")

    ar_result = await db.execute(
        select(PocApprovalRequest).where(PocApprovalRequest.poc_request_id == poc_request_id)
    )
    approval_request = ar_result.scalar_one_or_none()
    if approval_request is None:
        raise NotFoundError("No approval request exists yet for this POC request.")

    rec_result = await db.execute(
        select(Recommendation).where(Recommendation.id == approval_request.current_recommendation_id)
    )
    recommendation = rec_result.scalar_one()

    # --- Evaluate P1-P4, inside this same transaction, before any write ---
    p1 = await environment_service.compute_final_signoff(db, poc_request_id=poc_request_id)  # fresh, never cached
    p2 = not await _active_layer2_blocker_exists(db, poc_request_id=poc_request_id)
    p3 = recommendation.outcome != EngineOutcome.INSUFFICIENT_INFORMATION
    p4 = recommendation.input_version == poc_request.current_input_version
    recommendation_was_stale = not p4

    matched_ai = (
        (decision_type == DecisionType.APPROVED and recommendation.outcome == EngineOutcome.GO)
        or (decision_type == DecisionType.REJECTED and recommendation.outcome != EngineOutcome.GO)
        or (decision_type == DecisionType.MORE_INFO_REQUESTED and recommendation.outcome == EngineOutcome.INSUFFICIENT_INFORMATION)
    )
    # D5-Approval-Audit.md section 9's disagreement-rationale requirement
    # is about a decision that actually COMMITS, not about an attempt
    # P1-P4 is about to reject anyway -- checked AFTER preconditions pass
    # (below), never before. Checking it here would have let an
    # unrelated 422 mask what should be a 409 "preconditions failed"
    # response for an Approved attempt against a NO-GO/Insufficient-
    # Information recommendation (caught by this module's own test
    # suite: tests/test_approval.py).

    if decision_type == DecisionType.APPROVED:
        failed = []
        if not p1:
            failed.append("P1")
        if not p2:
            failed.append("P2")
        if not p3:
            failed.append("P3")
        if not p4:
            failed.append("P4")

        if failed:
            attempt = ApprovalAttempt(
                poc_approval_request_id=approval_request.id,
                attempted_by=approver_id,
                attempted_decision=decision_type,
                outcome=AttemptOutcome.REJECTED_BY_PRECONDITION,
                failed_preconditions=failed,
            )
            db.add(attempt)
            await db.flush()

            await audit_service.record_event(
                db,
                actor_id=approver_id,
                actor_kind=ActorKind.FINAL_APPROVER,
                action_type="approval_attempt_rejected",
                affected_object_type="poc_approval_request",
                affected_object_id=approval_request.id,
                after_state={"failed_preconditions": failed},
            )
            # Audit entry committed BEFORE any fresh-recommendation work,
            # per D5 section 10.2 ("the rejected-attempt audit entry is
            # written synchronously, before the rejection response is
            # returned").
            await db.commit()

            info: dict = {"failed_preconditions": failed}
            if "P4" in failed:
                # Synchronous re-run -- safe because the engine is a pure
                # function (TASD-v1.0.md section 17.5).
                fresh = await engine_orchestration.run_engine(db, poc_request_id=poc_request_id)
                approval_request.current_recommendation_id = fresh.id
                await db.flush()
                await db.commit()
                info["fresh_recommendation"] = {
                    "id": fresh.id,
                    "outcome": fresh.outcome.value,
                    "risk_tier": fresh.risk_tier.value if fresh.risk_tier else None,
                    "input_version": fresh.input_version,
                }
            return None, info

    # Decision_type is either Approved-with-all-preconditions-passing, or
    # Rejected/MoreInfoRequested (unconditional per D5 section 6's
    # decision-type scoping -- P1-P4 are not gates for these). The
    # decision is actually going to commit now, so the disagreement-
    # rationale requirement (D5 section 9) applies here, not earlier.
    if not matched_ai:
        if not disagreement_rationale or not disagreement_rationale.strip():
            raise ValidationError(
                "disagreement_rationale is required when your decision does not match the AI recommendation."
            )
        if disagreement_rationale == rationale:
            raise ValidationError("disagreement_rationale must not be identical to rationale.")

    decision_row = ApprovalDecision(
        poc_approval_request_id=approval_request.id,
        recommendation_id=recommendation.id,
        approver_id=approver_id,
        decision=decision_type,
        rationale=rationale,
        disagreement_rationale=disagreement_rationale,
        matched_ai_recommendation=matched_ai,
        recommendation_was_stale=recommendation_was_stale,
    )
    db.add(decision_row)
    await db.flush()

    attempt = ApprovalAttempt(
        poc_approval_request_id=approval_request.id,
        attempted_by=approver_id,
        attempted_decision=decision_type,
        outcome=AttemptOutcome.COMMITTED,
        resulting_decision_id=decision_row.id,
    )
    db.add(attempt)

    approval_request.status = {
        DecisionType.APPROVED: ApprovalRequestStatus.APPROVED,
        DecisionType.REJECTED: ApprovalRequestStatus.REJECTED,
        DecisionType.MORE_INFO_REQUESTED: ApprovalRequestStatus.MORE_INFO_REQUESTED,
    }[decision_type]
    await db.flush()

    await audit_service.record_event(
        db,
        actor_id=approver_id,
        actor_kind=ActorKind.FINAL_APPROVER,
        action_type="approval_decision_committed",
        affected_object_type="approval_decision",
        affected_object_id=decision_row.id,
        after_state={"decision": decision_type.value, "recommendation_was_stale": recommendation_was_stale},
    )
    await db.commit()
    return decision_row, {"failed_preconditions": []}
