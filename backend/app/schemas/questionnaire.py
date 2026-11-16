from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.models.questionnaire import AnswerUsability


class QuestionOut(BaseModel):
    id: str
    poc_request_id: str
    input_version: int
    domain_label: str
    is_mandatory_domain: bool
    trigger_basis: str | None
    question_text: str
    sequence: int

    model_config = {"from_attributes": True}


class AnswerIn(BaseModel):
    question_id: str
    answer_text: str = Field(max_length=20_000)


class AnswerSubmission(BaseModel):
    answers: list[AnswerIn]

    @field_validator("answers")
    @classmethod
    def _non_empty(cls, v: list[AnswerIn]) -> list[AnswerIn]:
        if not v:
            raise ValueError("At least one answer must be submitted.")
        return v


class ScopeAnalysisOut(BaseModel):
    """BR-008: the AI's full scope-analysis output -- not just the
    questions, but what it identified as a gap or an assumption while
    drafting them. Never authoritative; a human reviewer sees this
    alongside the raw scope text, never instead of it.
    """

    questions: list[QuestionOut]
    identified_gaps: list[str]
    identified_assumptions: list[str]
    dropped_candidate_count: int


class AnswerOut(BaseModel):
    id: str
    question_id: str
    input_version: int
    provenance_tag: str
    answer_text: str
    usability: AnswerUsability
    answered_at: datetime

    model_config = {"from_attributes": True}
