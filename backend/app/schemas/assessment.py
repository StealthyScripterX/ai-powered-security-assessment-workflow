from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.engine import RecommendationOut
from app.schemas.environment import AttestationOut
from app.schemas.evidence import EvidenceStateOut
from app.schemas.mapping import MappingOut
from app.schemas.questionnaire import AnswerOut, QuestionOut
from app.schemas.scope import ScopeSubmissionOut


class AssessmentSummaryOut(BaseModel):
    """The single consolidated read-model behind the AI Assessment
    Workspace and every role's assessment-detail screen. Provenance,
    review_status, and evidence_state remain three distinct fields
    across the nested objects below -- never collapsed (D2-AI-Governance.md
    section 6).
    """

    poc_request_id: str
    status: str
    current_input_version: int
    scope: ScopeSubmissionOut | None
    questions: list[QuestionOut]
    answers: list[AnswerOut]
    mappings: list[MappingOut]
    evidence_states: list[EvidenceStateOut]
    environment_attestations: list[AttestationOut]
    final_signoff_boolean: bool
    recommendation: RecommendationOut | None


class QueueItemOut(BaseModel):
    id: str
    requester_id: str
    status: str
    current_input_version: int
    created_at: datetime

    model_config = {"from_attributes": True}
