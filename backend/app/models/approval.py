"""Human approval objects. D5-Approval-Audit.md section 5/6,
architecture/TASD-v1.0.md section 11.6/17.

P1-P4 (D5 section 6) are enforced in app/services/approval_service.py's
single commit transaction, never spread across multiple writes a caller
could interleave with something else -- see that module's docstring for
the exact precondition-evaluation order and the TOCTOU note (this phase's
SQLite dev database does not yet implement the FOR UPDATE row lock
TASD-v1.0.md section 11.9 specifies for PostgreSQL; flagged in
IMPLEMENTATION-NOTES.md, not silently skipped).
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, CheckConstraint, DateTime, Enum, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ApprovalRequestStatus(str, enum.Enum):
    PENDING = "Pending"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    MORE_INFO_REQUESTED = "MoreInfoRequested"


class DecisionType(str, enum.Enum):
    APPROVED = "Approved"
    REJECTED = "Rejected"
    MORE_INFO_REQUESTED = "MoreInfoRequested"


class AttemptOutcome(str, enum.Enum):
    COMMITTED = "Committed"
    REJECTED_BY_PRECONDITION = "RejectedByPrecondition"
    REJECTED_BY_AUDIT_FAILURE = "RejectedByAuditFailure"


def _uuid() -> str:
    return str(uuid.uuid4())


class PocApprovalRequest(Base):
    __tablename__ = "poc_approval_request"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    poc_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("poc_request.id"), nullable=False, unique=True)
    current_recommendation_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("recommendation.id"), nullable=False
    )
    status: Mapped[ApprovalRequestStatus] = mapped_column(
        Enum(ApprovalRequestStatus), nullable=False, default=ApprovalRequestStatus.PENDING
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class ApprovalDecision(Base):
    __tablename__ = "approval_decision"
    __table_args__ = (
        CheckConstraint("length(trim(rationale)) > 0", name="ck_decision_rationale_nonempty"),
        CheckConstraint(
            "matched_ai_recommendation = true OR (disagreement_rationale IS NOT NULL "
            "AND length(trim(disagreement_rationale)) > 0 AND disagreement_rationale != rationale)",
            name="ck_disagreement_rationale_required",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    poc_approval_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("poc_approval_request.id"), nullable=False
    )
    recommendation_id: Mapped[str] = mapped_column(String(36), ForeignKey("recommendation.id"), nullable=False)
    approver_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=False)
    decision: Mapped[DecisionType] = mapped_column(Enum(DecisionType), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    disagreement_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_ai_recommendation: Mapped[bool] = mapped_column(Boolean, nullable=False)
    recommendation_was_stale: Mapped[bool] = mapped_column(Boolean, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # Immutable by convention (no UPDATE path exists in
    # app/services/approval_service.py) -- see Recommendation's docstring
    # for the same caveat re: a real database-role grant.


class ApprovalAttempt(Base):
    __tablename__ = "approval_attempt"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    poc_approval_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("poc_approval_request.id"), nullable=False
    )
    attempted_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=False)
    attempted_decision: Mapped[DecisionType] = mapped_column(Enum(DecisionType), nullable=False)
    outcome: Mapped[AttemptOutcome] = mapped_column(Enum(AttemptOutcome), nullable=False)
    failed_preconditions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    resulting_decision_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("approval_decision.id"), nullable=True
    )
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
