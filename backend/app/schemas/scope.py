from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ScopeSubmissionCreate(BaseModel):
    """BR-001: no pre-existing security documentation is required --
    these three free-text fields plus an open intake_form_data bag are
    the entire intake surface.
    """

    project_description: str = Field(min_length=1, max_length=20_000)
    systems_in_scope: str = Field(min_length=1, max_length=20_000)
    business_justification: str = Field(min_length=1, max_length=20_000)
    intake_form_data: dict = Field(default_factory=dict)


class ScopeSubmissionOut(BaseModel):
    id: str
    poc_request_id: str
    version: int
    project_description: str
    systems_in_scope: str
    business_justification: str
    intake_form_data: dict
    submitted_at: datetime

    model_config = {"from_attributes": True}


class PocRequestOut(BaseModel):
    id: str
    requester_id: str
    status: str
    current_input_version: int
    created_at: datetime

    model_config = {"from_attributes": True}
