"""Control mapping: AI-drafted, human-reviewed. D3-Methodology section 6/8,
architecture/TASD-v1.0.md section 11.4.

Three independent axes, never merged (D2 section 6 / D3-Methodology
section 8.2): `provenance_tag` here is pinned to AI_ASSERTION (the AI
proposed it; this never changes even after review); `review_status` is
the Reviewer's judgment on the mapping; evidence state
(app/models/evidence.py) is tracked entirely separately on the control,
not on the mapping. Every Reviewer transition is a NEW row linked via
`supersedes_id`, never an edit-in-place.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MappingConfidence(str, enum.Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class MappingReviewStatus(str, enum.Enum):
    PENDING_REVIEW = "PendingReview"
    CONFIRMED = "Confirmed"
    ADJUSTED = "Adjusted"
    REJECTED = "Rejected"


def _uuid() -> str:
    return str(uuid.uuid4())


class MappingRecord(Base):
    __tablename__ = "mapping_record"
    __table_args__ = (
        # provenance_tag is a plain String column (not Enum), so its
        # literal value here is correct as-is. review_status IS an
        # Enum(MappingReviewStatus) column -- SQLAlchemy's Enum() type
        # stores the Python member NAME ("REJECTED"), not its .value
        # ("Rejected"); see app/models/environment.py's
        # ck_exception_non_waivable for the full explanation (confirmed
        # live against a real PostgreSQL 16 instance, where the .value
        # string made PostgreSQL refuse to CREATE this table at all).
        CheckConstraint("provenance_tag = 'AI_ASSERTION'", name="ck_mapping_provenance_fixed"),
        CheckConstraint(
            "review_status != 'REJECTED' OR reject_reason IS NOT NULL", name="ck_mapping_reject_reason_required"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    poc_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("poc_request.id"), nullable=False)
    answer_id: Mapped[str] = mapped_column(String(36), ForeignKey("questionnaire_answer.id"), nullable=False)
    control_id: Mapped[str] = mapped_column(String(20), ForeignKey("control.control_id"), nullable=False)

    # Pinned: AI proposed every mapping; this table may never hold anything else.
    provenance_tag: Mapped[str] = mapped_column(String(20), nullable=False, default="AI_ASSERTION")
    answer_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[MappingConfidence] = mapped_column(Enum(MappingConfidence), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    review_status: Mapped[MappingReviewStatus] = mapped_column(
        Enum(MappingReviewStatus), nullable=False, default=MappingReviewStatus.PENDING_REVIEW
    )
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    supersedes_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class MappingEvidenceLink(Base):
    __tablename__ = "mapping_evidence_link"

    mapping_record_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("mapping_record.id"), primary_key=True
    )
    evidence_artifact_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("evidence_artifact.id"), primary_key=True
    )
