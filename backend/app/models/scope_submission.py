"""Scope submission -- BR-001: requesters submit scope with no
pre-existing security documentation required. architecture/TASD-v1.0.md
section 11.2.

Rows are immutable once written (a "change" is a new version row with
`superseded_by` set on the prior one, never an UPDATE of the content
fields) -- consistent with D2 section 8.5 item 8 treating any scope change as
an invalidating change that must be traceable, not silently overwritten.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class ScopeSubmission(Base):
    __tablename__ = "scope_submission"
    __table_args__ = (UniqueConstraint("poc_request_id", "version", name="uq_scope_poc_version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    poc_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("poc_request.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)

    project_description: Mapped[str] = mapped_column(Text, nullable=False)
    systems_in_scope: Mapped[str] = mapped_column(Text, nullable=False)
    business_justification: Mapped[str] = mapped_column(Text, nullable=False)
    intake_form_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    submitted_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    superseded_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
