"""Questionnaire question/answer models.

Governance invariants encoded here:
 - `provenance_tag` on `QuestionnaireAnswer` is pinned to the single legal
   value REQUESTER_FACT (D2 section 6 / architecture/TASD-v1.0.md section 11.4)
   -- this table may never hold an AI-authored row. The AI writes
   `QuestionnaireQuestion` rows only.
 - Question count (11-15, BR-002) is enforced in the service layer
   (app/services/scope_service.py) against the AI's actual output, never
   assumed from what was requested.
 - `trigger_basis` is required (non-null) only for a Conditional-domain
   question, matching D2 section 7 / D3-Methodology section 9's requirement
   that a Conditional-domain activation always be traceable to the exact
   triggering text.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AnswerUsability(str, enum.Enum):
    USABLE = "Usable"
    BLANK = "Blank"
    NON_RESPONSIVE = "NonResponsive"
    CONTRADICTORY = "Contradictory"


def _uuid() -> str:
    return str(uuid.uuid4())


class QuestionnaireQuestion(Base):
    __tablename__ = "questionnaire_question"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    poc_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("poc_request.id"), nullable=False)
    input_version: Mapped[int] = mapped_column(Integer, nullable=False)

    domain_label: Mapped[str] = mapped_column(String(255), nullable=False)
    is_mandatory_domain: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    trigger_basis: Mapped[str | None] = mapped_column(Text, nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    sequence: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    dropped_for_cap: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class QuestionnaireAnswer(Base):
    __tablename__ = "questionnaire_answer"
    __table_args__ = (
        CheckConstraint("provenance_tag = 'REQUESTER_FACT'", name="ck_answer_provenance_fixed"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    question_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("questionnaire_question.id"), nullable=False
    )
    input_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Pinned: this table may NEVER hold an AI-authored row (D2 section 6).
    provenance_tag: Mapped[str] = mapped_column(String(20), nullable=False, default="REQUESTER_FACT")

    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    usability: Mapped[AnswerUsability] = mapped_column(Enum(AnswerUsability), nullable=False)

    answered_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=False)
    answered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
