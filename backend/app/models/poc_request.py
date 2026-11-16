"""POC request -- the root object a scope submission, questionnaire,
mapping, evidence, environment readiness, recommendation, and approval
will all eventually hang off of (architecture/TASD-v1.0.md section 11.2).

Only the fields this Phase 1 slice actually uses are populated; the
columns anticipating later phases (current_input_version) are included
now because `scope_submission`/`questionnaire_answer` already need a
version number to stamp (TASD-v1.0.md section 11.8's invalidating-change
items 6 and 8), even though the full version-bump trigger machinery
(computing all five input-version hashes) is deferred to the phase that
builds the Decision Engine -- see IMPLEMENTATION-NOTES.md.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PocRequestStatus(str, enum.Enum):
    DRAFT = "Draft"
    IN_PROGRESS = "InProgress"
    PENDING_APPROVAL = "PendingApproval"
    APPROVED = "Approved"
    REJECTED = "Rejected"
    MORE_INFO_REQUESTED = "MoreInfoRequested"
    WITHDRAWN = "Withdrawn"


def _uuid() -> str:
    return str(uuid.uuid4())


class PocRequest(Base):
    __tablename__ = "poc_request"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    requester_id: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=False)
    status: Mapped[PocRequestStatus] = mapped_column(
        Enum(PocRequestStatus), nullable=False, default=PocRequestStatus.DRAFT
    )
    current_scope_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("scope_submission.id"), nullable=True
    )
    current_input_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
