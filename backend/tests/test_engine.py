"""Unit tests for the pure Decision Engine function
(app/services/engine.py) -- no database, no HTTP, same (input, config)
pair always produces the same output.
"""
from __future__ import annotations

from app.models.engine_enums import EngineOutcome, RiskTier
from app.models.evidence import EvidenceState
from app.models.mapping import MappingConfidence, MappingReviewStatus
from app.services.ai.questionnaire import MANDATORY_DOMAINS
from app.services.engine import EngineInput, PolicyConfigSnapshot, evaluate

UNCONFIGURED = PolicyConfigSnapshot(
    layer1_completeness_threshold=None, layer2_policy_hooks=[], layer3_weights=None, layer3_thresholds=None
)
CONFIGURED = PolicyConfigSnapshot(
    layer1_completeness_threshold=0.3,
    layer2_policy_hooks=[],
    layer3_weights={"f1_pending_review_discount": 0.5, "overall_multiplier": 1.0},
    layer3_thresholds={"low_max": 33, "medium_max": 66},
)


def _full_coverage() -> dict[str, bool]:
    return {d: True for d in MANDATORY_DOMAINS}


def test_missing_mandatory_domain_returns_insufficient_information_never_go_or_no_go():
    coverage = _full_coverage()
    coverage[MANDATORY_DOMAINS[0]] = False
    engine_input = EngineInput(
        poc_request_id="p1",
        input_version=1,
        mandatory_domain_coverage=coverage,
        environment_readiness_submitted=True,
        final_signoff_boolean=True,
    )
    output = evaluate(engine_input, CONFIGURED)
    assert output.outcome == EngineOutcome.INSUFFICIENT_INFORMATION
    assert output.decision_layer_attribution == 1
    assert output.risk_tier is None


def test_layer1_unconfigured_od10_refuses_only_when_rule3_would_matter():
    """OD-10 unconfigured: Rules 1-2 still run. A scope that fails ONLY
    on Rule 3 (which can't evaluate) gets terminal Insufficient
    Information via the refusal path, not a false pass.
    """
    engine_input = EngineInput(
        poc_request_id="p1",
        input_version=1,
        mandatory_domain_coverage=_full_coverage(),
        environment_readiness_submitted=True,
        final_signoff_boolean=True,
        unusable_answer_count=10,
        total_answer_count=11,
    )
    output = evaluate(engine_input, UNCONFIGURED)
    assert output.outcome == EngineOutcome.INSUFFICIENT_INFORMATION
    assert any("OD-10" in g for g in output.rationale)


def test_b01_blocks_go_even_with_zero_risk_inputs():
    """The hard gate (D2 section 8.4): GO is structurally unreachable
    while B-01 is true, regardless of how favorable Layer 3's inputs
    would be -- and Layer 3 never even runs (Layer 2 is terminal).
    """
    engine_input = EngineInput(
        poc_request_id="p1",
        input_version=1,
        mandatory_domain_coverage=_full_coverage(),
        environment_readiness_submitted=True,
        final_signoff_boolean=False,  # sign-off incomplete
        evidence_state_by_control={"AC-2": EvidenceState.VERIFIED_HUMAN_VALIDATED},
        mapping_confidence_by_control={"AC-2": MappingConfidence.HIGH},
        mapping_review_status_by_control={"AC-2": MappingReviewStatus.CONFIRMED},
    )
    output = evaluate(engine_input, CONFIGURED)
    assert output.outcome == EngineOutcome.NO_GO
    assert output.decision_layer_attribution == 2
    assert "B-01" in output.rationale


def test_layer3_refuses_without_weights_or_thresholds():
    """Layer 1 must have ALREADY passed (OD-10 configured, here) for
    execution to reach Layer 3 at all -- fixed order, BR-016.
    """
    layer1_ok_layer3_unconfigured = PolicyConfigSnapshot(
        layer1_completeness_threshold=0.3, layer2_policy_hooks=[], layer3_weights=None, layer3_thresholds=None
    )
    engine_input = EngineInput(
        poc_request_id="p1",
        input_version=1,
        mandatory_domain_coverage=_full_coverage(),
        environment_readiness_submitted=True,
        final_signoff_boolean=True,
    )
    output = evaluate(engine_input, layer1_ok_layer3_unconfigured)
    assert output.refused is True
    assert output.outcome is None
    assert output.decision_layer_attribution == 3
    assert any("OD-15" in m for m in output.missing_config)
    assert any("OD-16" in m for m in output.missing_config)


def test_go_with_risk_tier_when_fully_configured_and_clean():
    engine_input = EngineInput(
        poc_request_id="p1",
        input_version=1,
        mandatory_domain_coverage=_full_coverage(),
        environment_readiness_submitted=True,
        final_signoff_boolean=True,
        evidence_state_by_control={"AC-2": EvidenceState.VERIFIED_HUMAN_VALIDATED},
        mapping_confidence_by_control={"AC-2": MappingConfidence.HIGH},
        mapping_review_status_by_control={"AC-2": MappingReviewStatus.CONFIRMED},
    )
    output = evaluate(engine_input, CONFIGURED)
    assert output.outcome == EngineOutcome.GO
    assert output.risk_tier in (RiskTier.LOW, RiskTier.MEDIUM, RiskTier.HIGH)


def test_risk_tier_never_appears_on_nongo_outcomes():
    coverage = _full_coverage()
    coverage[MANDATORY_DOMAINS[0]] = False
    insufficient = evaluate(
        EngineInput(poc_request_id="p1", input_version=1, mandatory_domain_coverage=coverage, environment_readiness_submitted=True),
        CONFIGURED,
    )
    assert insufficient.risk_tier is None

    no_go = evaluate(
        EngineInput(
            poc_request_id="p1",
            input_version=1,
            mandatory_domain_coverage=_full_coverage(),
            environment_readiness_submitted=True,
            final_signoff_boolean=False,
        ),
        CONFIGURED,
    )
    assert no_go.risk_tier is None


def test_rejected_mapping_excluded_from_f1_entirely():
    """D2 section 8.3: a Rejected mapping contributes to the gap picture
    the same as if no mapping existed -- not scored as a weak positive.
    """
    base_kwargs = dict(
        poc_request_id="p1",
        input_version=1,
        mandatory_domain_coverage=_full_coverage(),
        environment_readiness_submitted=True,
        final_signoff_boolean=True,
    )
    rejected_input = EngineInput(
        **base_kwargs,
        evidence_state_by_control={"AC-2": EvidenceState.NOT_PROVIDED},
        mapping_confidence_by_control={"AC-2": MappingConfidence.HIGH},
        mapping_review_status_by_control={"AC-2": MappingReviewStatus.REJECTED},
    )
    no_mapping_input = EngineInput(
        **base_kwargs,
        evidence_state_by_control={"AC-2": EvidenceState.NOT_PROVIDED},
        mapping_confidence_by_control={"AC-2": None},
        mapping_review_status_by_control={"AC-2": None},
    )
    rejected_output = evaluate(rejected_input, CONFIGURED)
    no_mapping_output = evaluate(no_mapping_input, CONFIGURED)
    # Both should land in the same risk tier since Rejected contributes
    # nothing extra to F1 beyond evidence severity.
    assert rejected_output.risk_tier == no_mapping_output.risk_tier


def test_evidence_state_dominance_over_high_confidence():
    """D2 section 8.3's conflict-resolution rule: High confidence with
    Rejected/NotProvided evidence is still treated as a gap, not a pass.
    """
    base_kwargs = dict(
        poc_request_id="p1",
        input_version=1,
        mandatory_domain_coverage=_full_coverage(),
        environment_readiness_submitted=True,
        final_signoff_boolean=True,
    )
    high_confidence_no_evidence = EngineInput(
        **base_kwargs,
        evidence_state_by_control={"AC-2": EvidenceState.NOT_PROVIDED},
        mapping_confidence_by_control={"AC-2": MappingConfidence.HIGH},
        mapping_review_status_by_control={"AC-2": MappingReviewStatus.CONFIRMED},
    )
    high_confidence_verified = EngineInput(
        **base_kwargs,
        evidence_state_by_control={"AC-2": EvidenceState.VERIFIED_HUMAN_VALIDATED},
        mapping_confidence_by_control={"AC-2": MappingConfidence.HIGH},
        mapping_review_status_by_control={"AC-2": MappingReviewStatus.CONFIRMED},
    )
    gap_output = evaluate(high_confidence_no_evidence, CONFIGURED)
    clean_output = evaluate(high_confidence_verified, CONFIGURED)
    tier_order = {RiskTier.LOW: 0, RiskTier.MEDIUM: 1, RiskTier.HIGH: 2}
    assert tier_order[gap_output.risk_tier] >= tier_order[clean_output.risk_tier]


def test_deterministic_same_input_same_output():
    engine_input = EngineInput(
        poc_request_id="p1",
        input_version=1,
        mandatory_domain_coverage=_full_coverage(),
        environment_readiness_submitted=True,
        final_signoff_boolean=True,
        evidence_state_by_control={"AC-2": EvidenceState.VERIFIED_HUMAN_VALIDATED},
        mapping_confidence_by_control={"AC-2": MappingConfidence.HIGH},
        mapping_review_status_by_control={"AC-2": MappingReviewStatus.CONFIRMED},
    )
    out1 = evaluate(engine_input, CONFIGURED)
    out2 = evaluate(engine_input, CONFIGURED)
    assert out1.outcome == out2.outcome
    assert out1.risk_tier == out2.risk_tier
    assert out1.rationale == out2.rationale


def test_environment_readiness_not_started_is_completeness_failure():
    engine_input = EngineInput(
        poc_request_id="p1",
        input_version=1,
        mandatory_domain_coverage=_full_coverage(),
        environment_readiness_submitted=False,  # "not started" per D2 section 8.1
        final_signoff_boolean=False,
    )
    output = evaluate(engine_input, CONFIGURED)
    assert output.outcome == EngineOutcome.INSUFFICIENT_INFORMATION
    assert output.decision_layer_attribution == 1
