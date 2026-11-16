from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RecommendationOut(BaseModel):
    id: str
    poc_request_id: str
    input_version: int
    outcome: str
    risk_tier: str | None
    rationale: str
    decision_layer_attribution: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PolicyConfigIn(BaseModel):
    layer1_completeness_threshold: float | None = None
    layer2_policy_hooks: list[str] = []
    layer3_weights: dict | None = None
    layer3_thresholds: dict | None = None
    approval_tier_model: dict | None = None


class PolicyConfigOut(BaseModel):
    version: int
    layer1_completeness_threshold: float | None
    layer2_policy_hooks: list[str]
    layer3_weights: dict | None
    layer3_thresholds: dict | None
    approval_tier_model: dict | None
    published_at: datetime

    model_config = {"from_attributes": True}
