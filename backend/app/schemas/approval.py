from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ApprovalDecisionIn(BaseModel):
    decision: str = Field(pattern="^(Approved|Rejected|MoreInfoRequested)$")
    rationale: str = Field(min_length=1)
    disagreement_rationale: str | None = None


class ApprovalDecisionOut(BaseModel):
    id: str
    poc_approval_request_id: str
    recommendation_id: str
    approver_id: str
    decision: str
    rationale: str
    disagreement_rationale: str | None
    matched_ai_recommendation: bool
    recommendation_was_stale: bool
    decided_at: datetime

    model_config = {"from_attributes": True}


class ApprovalRequestOut(BaseModel):
    id: str
    poc_request_id: str
    current_recommendation_id: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}
