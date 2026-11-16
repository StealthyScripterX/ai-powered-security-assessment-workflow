from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EvidenceArtifactOut(BaseModel):
    id: str
    poc_request_id: str
    control_id: str | None
    filename: str
    content_type: str
    size_bytes: int
    content_sha256: str
    scan_status: str
    uploaded_at: datetime

    model_config = {"from_attributes": True}


class EvidenceStateOut(BaseModel):
    poc_request_id: str
    control_id: str
    state: str
    validated_by: str | None
    validated_at: datetime | None
    validation_rationale: str | None

    model_config = {"from_attributes": True}


class EvidenceValidationIn(BaseModel):
    new_state: str = Field(pattern="^(Verified - Human Validated|Rejected - Insufficient Evidence)$")
    rationale: str = Field(min_length=1)
