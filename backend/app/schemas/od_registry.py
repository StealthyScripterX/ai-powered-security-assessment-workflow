from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ODOut(BaseModel):
    id: str
    title: str
    purpose: str
    impact: str
    proposed_options: list[dict]
    is_blocking: bool
    current_status: str

    model_config = {"from_attributes": True}


class ODRecordOut(BaseModel):
    id: str
    od_id: str
    action: str
    value: dict | None
    rationale: str
    actor_id: str
    actor_role: str
    activated_policy_config_version: int | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ODProposeIn(BaseModel):
    value: dict
    rationale: str = Field(min_length=1)


class ODDecideIn(BaseModel):
    rationale: str = Field(min_length=1)
