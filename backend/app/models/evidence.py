"""Evidence architecture: the four-state model (BR-005) and uploaded
artifacts. architecture/TASD-v1.0.md section 11.5 / section 15.

Non-negotiable encoded here: `ControlEvidenceState.state` has exactly
four values and defaults to `Not Provided`; there is no code path in
app/services/evidence_service.py that can set it to `Verified` or
`Rejected` except the human-only `transition_evidence_state` function,
which requires a SecurityReviewer role (OD-07's current default) and is
never callable by the AI actor.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class EvidenceState(str, enum.Enum):
    NOT_PROVIDED = "Not Provided"
    SUBMITTED_PENDING_REVIEW = "Submitted - Pending Review"
    VERIFIED_HUMAN_VALIDATED = "Verified - Human Validated"
    REJECTED_INSUFFICIENT_EVIDENCE = "Rejected - Insufficient Evidence"


class ScanStatus(str, enum.Enum):
    PENDING = "Pending"
    CLEAN = "Clean"
    INFECTED = "Infected"
    ERROR = "Error"


def _uuid() -> str:
    return str(uuid.uuid4())


class EvidenceArtifact(Base):
    __tablename__ = "evidence_artifact"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    poc_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("poc_request.id"), nullable=False)
    control_id: Mapped[str | None] = mapped_column(String(20), ForeignKey("control.control_id"), nullable=True)

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(200), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    scan_status: Mapped[ScanStatus] = mapped_column(Enum(ScanStatus), nullable=False, default=ScanStatus.PENDING)

    uploaded_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    superseded_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ControlEvidenceState(Base):
    __tablename__ = "control_evidence_state"
    __table_args__ = (PrimaryKeyConstraint("poc_request_id", "control_id"),)

    poc_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("poc_request.id"), nullable=False)
    control_id: Mapped[str] = mapped_column(String(20), ForeignKey("control.control_id"), nullable=False)
    state: Mapped[EvidenceState] = mapped_column(
        Enum(EvidenceState), nullable=False, default=EvidenceState.NOT_PROVIDED
    )
    validated_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    validation_rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
