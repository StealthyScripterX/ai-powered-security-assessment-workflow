"""Organizational Decision Registry service: propose, approve, reject,
revise, and (for OD-10/OD-15/OD-16 only) activate into `PolicyConfig`.

Governance rule enforced here, structurally: `approve`/`reject` always
require an existing `Proposed` record to act on -- there is no
"propose and approve in the same call" shortcut, so every resolved
decision has a visible two-step (at minimum) human trail: who proposed
what, and who separately approved or rejected it, each with their own
rationale and timestamp. `activate` additionally requires the record it
activates to already be `Approved` -- it is the only function that
writes to `PolicyConfig`, and it never invents a value: it publishes
exactly the `value` payload the Approved record carries. Nothing here
can move a decision to `Approved` on its own; nothing here can activate
a value that was never explicitly approved by a human.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import ActorKind
from app.models.engine import PolicyConfig
from app.models.od_registry import ODAction, ODDecisionRecord, ODStatus, OrganizationalDecision
from app.services import audit_service

_ACTIVATABLE = {"OD-10", "OD-15", "OD-16"}


class ODNotFoundError(RuntimeError):
    pass


class ODValidationError(RuntimeError):
    pass


async def list_decisions(db: AsyncSession) -> list[OrganizationalDecision]:
    result = await db.execute(select(OrganizationalDecision).order_by(OrganizationalDecision.id))
    return list(result.scalars().all())


async def get_decision(db: AsyncSession, od_id: str) -> OrganizationalDecision:
    result = await db.execute(select(OrganizationalDecision).where(OrganizationalDecision.id == od_id))
    decision = result.scalar_one_or_none()
    if decision is None:
        raise ODNotFoundError(f"Organizational Decision {od_id!r} not found.")
    return decision


async def get_history(db: AsyncSession, od_id: str) -> list[ODDecisionRecord]:
    result = await db.execute(
        select(ODDecisionRecord).where(ODDecisionRecord.od_id == od_id).order_by(ODDecisionRecord.created_at)
    )
    return list(result.scalars().all())


async def _latest_proposed(db: AsyncSession, od_id: str) -> ODDecisionRecord | None:
    result = await db.execute(
        select(ODDecisionRecord)
        .where(ODDecisionRecord.od_id == od_id, ODDecisionRecord.action == ODAction.PROPOSED)
        .order_by(ODDecisionRecord.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _latest_approved(db: AsyncSession, od_id: str) -> ODDecisionRecord | None:
    result = await db.execute(
        select(ODDecisionRecord)
        .where(ODDecisionRecord.od_id == od_id, ODDecisionRecord.action == ODAction.APPROVED)
        .order_by(ODDecisionRecord.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _require_nonempty(rationale: str, field_name: str = "rationale") -> None:
    if not rationale or not rationale.strip():
        raise ODValidationError(f"A non-empty {field_name} is required for every Organizational Decision action.")


async def propose(
    db: AsyncSession, *, od_id: str, value: dict, rationale: str, actor_id: str, actor_role: str
) -> ODDecisionRecord:
    """D1 section 12 / README.md: 'No decision here is invented by this
    documentation pack.' The same rule applies to this registry -- a
    Proposal is a human-authored value with a human-authored rationale;
    nothing here generates one.
    """
    decision = await get_decision(db, od_id)
    _require_nonempty(rationale)
    if not value:
        raise ODValidationError("A non-empty proposed value is required.")

    record = ODDecisionRecord(
        od_id=od_id, action=ODAction.PROPOSED, value=value, rationale=rationale, actor_id=actor_id, actor_role=actor_role
    )
    db.add(record)
    decision.current_status = ODStatus.PROPOSED
    await db.flush()

    await audit_service.record_event(
        db,
        actor_id=actor_id,
        actor_kind=ActorKind.PLATFORM_OWNER,
        action_type="od_proposed",
        affected_object_type="organizational_decision",
        affected_object_id=od_id,
        after_state={"value": value, "rationale": rationale},
    )
    await db.commit()
    return record


async def approve(
    db: AsyncSession, *, od_id: str, rationale: str, actor_id: str, actor_role: str
) -> ODDecisionRecord:
    decision = await get_decision(db, od_id)
    _require_nonempty(rationale)
    proposed = await _latest_proposed(db, od_id)
    if proposed is None or decision.current_status != ODStatus.PROPOSED:
        raise ODValidationError(f"{od_id} has no pending proposal to approve.")

    record = ODDecisionRecord(
        od_id=od_id,
        action=ODAction.APPROVED,
        value=proposed.value,
        rationale=rationale,
        actor_id=actor_id,
        actor_role=actor_role,
    )
    db.add(record)
    decision.current_status = ODStatus.APPROVED
    await db.flush()

    await audit_service.record_event(
        db,
        actor_id=actor_id,
        actor_kind=ActorKind.PLATFORM_OWNER,
        action_type="od_approved",
        affected_object_type="organizational_decision",
        affected_object_id=od_id,
        before_state={"proposed_value": proposed.value},
        after_state={"rationale": rationale},
    )
    await db.commit()
    return record


async def reject(db: AsyncSession, *, od_id: str, rationale: str, actor_id: str, actor_role: str) -> ODDecisionRecord:
    decision = await get_decision(db, od_id)
    _require_nonempty(rationale)
    proposed = await _latest_proposed(db, od_id)
    if proposed is None or decision.current_status != ODStatus.PROPOSED:
        raise ODValidationError(f"{od_id} has no pending proposal to reject.")

    record = ODDecisionRecord(
        od_id=od_id, action=ODAction.REJECTED, value=None, rationale=rationale, actor_id=actor_id, actor_role=actor_role
    )
    db.add(record)
    decision.current_status = ODStatus.REJECTED
    await db.flush()

    await audit_service.record_event(
        db,
        actor_id=actor_id,
        actor_kind=ActorKind.PLATFORM_OWNER,
        action_type="od_rejected",
        affected_object_type="organizational_decision",
        affected_object_id=od_id,
        before_state={"proposed_value": proposed.value},
        after_state={"rationale": rationale},
    )
    await db.commit()
    return record


async def revise(
    db: AsyncSession, *, od_id: str, value: dict, rationale: str, actor_id: str, actor_role: str
) -> ODDecisionRecord:
    """A Revise is only meaningful after Rejected (propose a different
    value) or after Approved-but-not-yet-activated (change course before
    it takes effect) -- it is implemented as exactly the same write as
    Propose (a new ODAction.REVISED row, status back to Proposed), kept
    as a distinct action type purely so the history reads honestly
    ("this was a revision of an earlier round," not "this is the first
    proposal").
    """
    decision = await get_decision(db, od_id)
    _require_nonempty(rationale)
    if decision.current_status not in (ODStatus.REJECTED, ODStatus.APPROVED, ODStatus.PROPOSED):
        raise ODValidationError(f"{od_id} has no prior proposal to revise.")
    if not value:
        raise ODValidationError("A non-empty proposed value is required.")

    record = ODDecisionRecord(
        od_id=od_id, action=ODAction.REVISED, value=value, rationale=rationale, actor_id=actor_id, actor_role=actor_role
    )
    db.add(record)
    decision.current_status = ODStatus.PROPOSED
    await db.flush()

    await audit_service.record_event(
        db,
        actor_id=actor_id,
        actor_kind=ActorKind.PLATFORM_OWNER,
        action_type="od_revised",
        affected_object_type="organizational_decision",
        affected_object_id=od_id,
        after_state={"value": value, "rationale": rationale},
    )
    await db.commit()
    return record


async def activate(db: AsyncSession, *, od_id: str, actor_id: str, actor_role: str) -> ODDecisionRecord:
    """Publishes a new `PolicyConfig` version carrying the Approved
    value, as a targeted update over the current active config (every
    other field carried forward unchanged) -- never a blanket reset of
    every Open Decision just because one was activated. Only OD-10,
    OD-15, and OD-16 are activatable: these are the only three that
    correspond to a `PolicyConfig` field at all (OD-01/OD-06/OD-07 are
    role/process decisions this codebase does not have a deeper runtime
    hook for yet -- see IMPLEMENTATION-NOTES.md).
    """
    if od_id not in _ACTIVATABLE:
        raise ODValidationError(
            f"{od_id} has no corresponding PolicyConfig field and cannot be activated via this endpoint "
            f"-- only {sorted(_ACTIVATABLE)} can."
        )
    decision = await get_decision(db, od_id)
    if decision.current_status != ODStatus.APPROVED:
        raise ODValidationError(f"{od_id} must be Approved before it can be activated (current: {decision.current_status.value}).")

    approved = await _latest_approved(db, od_id)
    if approved is None:
        raise ODValidationError(f"{od_id} has no Approved record to activate.")

    current_result = await db.execute(select(PolicyConfig).order_by(PolicyConfig.version.desc()).limit(1))
    current = current_result.scalar_one_or_none()

    new_config = PolicyConfig(
        layer1_completeness_threshold=(current.layer1_completeness_threshold if current else None),
        layer2_policy_hooks=(current.layer2_policy_hooks if current else []),
        layer3_weights=(current.layer3_weights if current else None),
        layer3_thresholds=(current.layer3_thresholds if current else None),
        approval_tier_model=(current.approval_tier_model if current else None),
        published_by=actor_id,
    )
    if od_id == "OD-10":
        new_config.layer1_completeness_threshold = approved.value.get("layer1_completeness_threshold")
    elif od_id == "OD-15":
        new_config.layer3_weights = approved.value.get("weights")
    elif od_id == "OD-16":
        new_config.layer3_thresholds = approved.value.get("thresholds")

    db.add(new_config)
    await db.flush()

    record = ODDecisionRecord(
        od_id=od_id,
        action=ODAction.ACTIVATED,
        value=approved.value,
        rationale=f"Activated into PolicyConfig version {new_config.version}.",
        actor_id=actor_id,
        actor_role=actor_role,
        activated_policy_config_version=new_config.version,
    )
    db.add(record)
    await db.flush()

    await audit_service.record_event(
        db,
        actor_id=actor_id,
        actor_kind=ActorKind.PLATFORM_OWNER,
        action_type="od_activated",
        affected_object_type="organizational_decision",
        affected_object_id=od_id,
        after_state={"policy_config_version": new_config.version, "value": approved.value},
    )
    await db.commit()
    return record
