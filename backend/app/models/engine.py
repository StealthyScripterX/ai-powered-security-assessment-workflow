"""Policy configuration + assessment versioning + recommendation.

architecture/TASD-v1.0.md section 11.6/11.7/11.8, D2-AI-Governance.md
section 8. `PolicyConfig`'s OD-gated columns (layer1_completeness_threshold,
layer3_weights, layer3_thresholds) default to NULL and NOTHING in this
codebase ever writes a non-NULL value to them automatically -- they can
only be set by an explicit POST to /api/admin/policy-config (PlatformOwner
only), which is exactly where the organization's real OD-10/15/16
answers would be entered. Until that happens, app/services/engine.py
refuses to produce a GO (or any outcome at all past Layer 1 Rule 3) --
see that module's docstring.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, CheckConstraint, DateTime, Enum, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.engine_enums import EngineOutcome, RiskTier


class PolicyConfig(Base):
    __tablename__ = "policy_config"

    version: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # OD-10. NULL until the organization sets it -- Layer 1 Rule 3
    # (unusable-answer-fraction) cannot evaluate while NULL.
    layer1_completeness_threshold: Mapped[float | None] = mapped_column(nullable=True)

    # OD-11. Empty list is the documented safe default (D3-Methodology
    # section 10): scope-conditional hooks are risk-scoring-only, never
    # gating, until the organization elevates one explicitly.
    layer2_policy_hooks: Mapped[list] = mapped_column(JSON, nullable=False, default=list)

    # OD-15 / OD-16. NULL means Layer 3 cannot run AT ALL -- no default
    # weight or threshold is ever substituted.
    layer3_weights: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    layer3_thresholds: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # OD-01. NULL = single-tier placeholder model (D5 section 4) is active.
    approval_tier_model: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    published_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=False)
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class AssessmentInputVersion(Base):
    __tablename__ = "assessment_input_version"
    __table_args__ = (
        CheckConstraint("version >= 1", name="ck_input_version_positive"),
    )

    poc_request_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("poc_request.id"), primary_key=True
    )
    version: Mapped[int] = mapped_column(Integer, primary_key=True)

    scope_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_state_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    mapping_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    questionnaire_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    environment_readiness_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    policy_config_version: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("policy_config.version"), nullable=True
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class Recommendation(Base):
    __tablename__ = "recommendation"
    __table_args__ = (
        CheckConstraint("risk_tier IS NULL OR outcome = 'GO'", name="ck_risk_tier_go_only"),
        CheckConstraint("decision_layer_attribution IN (1, 2, 3)", name="ck_decision_layer_valid"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    poc_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("poc_request.id"), nullable=False)
    input_version: Mapped[int] = mapped_column(Integer, nullable=False)

    outcome: Mapped[EngineOutcome] = mapped_column(Enum(EngineOutcome), nullable=False)
    risk_tier: Mapped[RiskTier | None] = mapped_column(Enum(RiskTier), nullable=True)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decision_layer_attribution: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    engine_version: Mapped[str] = mapped_column(String(50), nullable=False, default="phase1-v0.1")
    policy_config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    # No UPDATE/DELETE grant exists at the database-role level in this
    # single-role dev setup (see IMPLEMENTATION-NOTES.md); immutability
    # is enforced today by convention (no service function ever updates
    # a Recommendation row) rather than by a grant.
