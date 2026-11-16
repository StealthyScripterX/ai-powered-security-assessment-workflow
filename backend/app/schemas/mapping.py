from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MappingOut(BaseModel):
    id: str
    poc_request_id: str
    answer_id: str
    control_id: str
    provenance_tag: str
    confidence: str
    rationale: str
    review_status: str
    reject_reason: str | None
    supersedes_id: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class MappingReviewIn(BaseModel):
    action: str = Field(pattern="^(Confirm|Adjust|Reject)$")
    control_id: str | None = None
    confidence: str | None = None
    rationale: str | None = None
    reject_reason: str | None = None
