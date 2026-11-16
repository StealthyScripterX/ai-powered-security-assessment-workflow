"""Organizational Decision Registry.

README.md's Open Decisions index names 21 questions only the
organization can answer; six are blocking (OD-01, OD-06, OD-07, OD-10,
OD-15, OD-16). This registry makes resolving them a tracked, auditable
governance workflow instead of an ad-hoc config edit:

  Open -> Proposed -> Approved -> [Activated, for OD-10/15/16 only]
                    -> Rejected

Every transition is a NEW `ODDecisionRecord` row, never an edit of a
previous one (same append-only discipline as `MappingRecord`'s Reviewer
transitions and `audit_entry`) -- the full history, including every
rejected or superseded proposal, is permanently visible. Nothing in
this module or its service/route layer ever moves a decision straight
to Approved without a human Propose-then-decide step recorded
separately (app/services/od_registry_service.py), and nothing activates
a policy value the registry itself invented -- see that module's
docstring.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ODStatus(str, enum.Enum):
    OPEN = "Open"
    PROPOSED = "Proposed"
    APPROVED = "Approved"
    REJECTED = "Rejected"


class ODAction(str, enum.Enum):
    PROPOSED = "Proposed"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    REVISED = "Revised"
    ACTIVATED = "Activated"


class OrganizationalDecision(Base):
    """Static reference row per tracked Open Decision. Seeded once
    (app/services/od_registry_seed.py) with the purpose/impact/options
    text drawn directly from the baseline documents -- never invented.
    `current_status` is a denormalized convenience field kept in sync by
    app/services/od_registry_service.py; the authoritative history is
    `ODDecisionRecord`.
    """

    __tablename__ = "organizational_decision"

    id: Mapped[str] = mapped_column(String(10), primary_key=True)  # "OD-01", "OD-10", ...
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    purpose: Mapped[str] = mapped_column(Text, nullable=False)
    impact: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_options: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    is_blocking: Mapped[bool] = mapped_column(nullable=False, default=False)
    current_status: Mapped[ODStatus] = mapped_column(Enum(ODStatus), nullable=False, default=ODStatus.OPEN)


def _uuid() -> str:
    return str(uuid.uuid4())


class ODDecisionRecord(Base):
    """Append-only history. One row per Propose/Approve/Reject/
    Revise/Activate action -- never updated or deleted, mirroring
    `audit_entry`'s immutability (and in fact every state-changing
    action here also writes a real `audit_entry` via
    app/services/audit_service.py, so the registry's own history is
    itself independently covered by the hash chain).
    """

    __tablename__ = "od_decision_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    od_id: Mapped[str] = mapped_column(String(10), ForeignKey("organizational_decision.id"), nullable=False)
    action: Mapped[ODAction] = mapped_column(Enum(ODAction), nullable=False)

    # The proposed or decided value -- shape is OD-specific (e.g.
    # {"layer1_completeness_threshold": 0.3} for OD-10,
    # {"weights": {...}} for OD-15, {"tier_model": "single"} for OD-01).
    # Null for Approved/Rejected rows that merely decide on the most
    # recent Proposed value rather than restating it.
    value: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)

    # Set only on an Activated row for OD-10/OD-15/OD-16 -- the exact
    # PolicyConfig.version this decision caused to be published.
    activated_policy_config_version: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("policy_config.version"), nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
