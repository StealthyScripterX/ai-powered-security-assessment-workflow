"""The Deterministic Decision Engine -- a PURE function.

D2-AI-Governance.md section 8, architecture/TASD-v1.0.md section 14.
`evaluate()` has no I/O: no database read/write, no network call, no
model call, no wall-clock read. The caller (app/services/engine_orchestration.py)
assembles `EngineInput` from the database BEFORE calling this, and
persists `EngineOutput` AFTER -- this function touches neither.

Fixed order, BR-016: Layer 1 (Completeness) -> Layer 2 (Mandatory
Security Blockers) -> Layer 3 (Risk Scoring). A terminal layer stops
execution; later layers never run.

The engine REFUSES rather than guesses whenever a blocking Open Decision
(OD-10 for Layer 1 Rule 3, OD-15/OD-16 for all of Layer 3) is
unconfigured. `REFUSED` is NOT one of the three BR-009 outcomes and is
never persisted -- see app/models/engine_enums.py's docstring.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.models.engine_enums import EngineOutcome, RiskTier
from app.models.evidence import EvidenceState
from app.models.mapping import MappingConfidence, MappingReviewStatus

# --- F2 evidence-state severity floors, per confidence --------------------
# D2 section 8.3's qualitative ordering rule, implemented as literal
# numbers: Verified < Pending < NotProvided <= Rejected, for every
# confidence level. These are STRUCTURAL ordering constants, not Layer-3
# weights -- OD-15 still supplies the actual weight multiplier applied
# on top of this severity, via PolicyConfig.layer3_weights.
_EVIDENCE_SEVERITY_FLOOR = {
    EvidenceState.VERIFIED_HUMAN_VALIDATED: 1,
    EvidenceState.SUBMITTED_PENDING_REVIEW: 2,
    EvidenceState.NOT_PROVIDED: 3,
    EvidenceState.REJECTED_INSUFFICIENT_EVIDENCE: 3,  # >= NotProvided, never less severe
}
_CONFIDENCE_SEVERITY = {MappingConfidence.HIGH: 3, MappingConfidence.MEDIUM: 2, MappingConfidence.LOW: 1}


@dataclass
class EngineInput:
    poc_request_id: str
    input_version: int

    # Layer 1
    mandatory_domain_coverage: dict[str, bool] = field(default_factory=dict)
    environment_readiness_submitted: bool = False
    unusable_answer_count: int = 0
    total_answer_count: int = 0

    # Layer 2
    final_signoff_boolean: bool = False
    missing_evidence_on_always_required_controls: list[str] = field(default_factory=list)
    policy_hook_blockers_fired: list[str] = field(default_factory=list)

    # Layer 3 (per-control)
    mapping_confidence_by_control: dict[str, MappingConfidence | None] = field(default_factory=dict)
    mapping_review_status_by_control: dict[str, MappingReviewStatus | None] = field(default_factory=dict)
    evidence_state_by_control: dict[str, EvidenceState] = field(default_factory=dict)


@dataclass
class EngineOutput:
    outcome: EngineOutcome | None  # None means REFUSED
    decision_layer_attribution: int | None
    risk_tier: RiskTier | None
    rationale: list[str]
    refused: bool = False
    missing_config: list[str] = field(default_factory=list)


@dataclass
class PolicyConfigSnapshot:
    layer1_completeness_threshold: float | None
    layer2_policy_hooks: list[str]
    layer3_weights: dict | None
    layer3_thresholds: dict | None


def _evaluate_layer1(engine_input: EngineInput, config: PolicyConfigSnapshot) -> tuple[bool, list[str]]:
    gaps: list[str] = []
    for domain, covered in engine_input.mandatory_domain_coverage.items():
        if not covered:
            gaps.append(f"Mandatory domain unaddressed: {domain}")

    if not engine_input.environment_readiness_submitted:
        gaps.append("Environment Readiness: not started")

    if config.layer1_completeness_threshold is None:
        # OD-10 unconfigured: Rules 1-2 above still ran; Rule 3 cannot.
        # Modeled as "cannot confirm completeness," per BR-009a -- never
        # a silent pass.
        gaps.append("ENGINE REFUSAL: OD-10 completeness threshold not configured -- Rule 3 cannot evaluate")
        return True, gaps

    if engine_input.total_answer_count > 0:
        unusable_fraction = engine_input.unusable_answer_count / engine_input.total_answer_count
        if unusable_fraction > config.layer1_completeness_threshold:
            gaps.append(
                f"{engine_input.unusable_answer_count}/{engine_input.total_answer_count} unusable answers "
                f"exceeds configured threshold {config.layer1_completeness_threshold}"
            )

    return len(gaps) > 0, gaps


def _evaluate_layer2(engine_input: EngineInput, config: PolicyConfigSnapshot) -> tuple[bool, list[str]]:
    fired: list[str] = []

    # B-01: structural, always active, never configurable away.
    if not engine_input.final_signoff_boolean:
        fired.append("B-01")

    # B-02: structural, driven by whichever controls policy designates always-required.
    if engine_input.missing_evidence_on_always_required_controls:
        fired.append("B-02")

    # Scope-conditional blockers: ONLY those explicitly elevated by policy
    # (OD-11's safe default is an empty hook list -- nothing fires here
    # unless the organization has explicitly configured a hook).
    fired.extend(engine_input.policy_hook_blockers_fired)

    return len(fired) > 0, fired


def _evaluate_layer3(
    engine_input: EngineInput, config: PolicyConfigSnapshot
) -> tuple[bool, RiskTier | None, list[str], list[str]]:
    missing_config = []
    if config.layer3_weights is None:
        missing_config.append("OD-15: Layer 3 risk-factor weights not configured")
    if config.layer3_thresholds is None:
        missing_config.append("OD-16: Layer 3 risk-score thresholds not configured")
    if missing_config:
        return True, None, [], missing_config

    weights = config.layer3_weights
    thresholds = config.layer3_thresholds
    pending_discount = weights.get("f1_pending_review_discount", 0.5)

    per_control_severity: dict[str, float] = {}
    for control_id in engine_input.evidence_state_by_control:
        review_status = engine_input.mapping_review_status_by_control.get(control_id)
        confidence = engine_input.mapping_confidence_by_control.get(control_id)
        evidence_state = engine_input.evidence_state_by_control[control_id]

        if review_status == MappingReviewStatus.REJECTED:
            f1 = 0.0  # excluded from F1 entirely -- treated as if no mapping existed (D2 section 8.3)
        elif confidence is None:
            f1 = 0.0
        elif review_status == MappingReviewStatus.PENDING_REVIEW:
            f1 = _CONFIDENCE_SEVERITY[confidence] * pending_discount
        else:  # Confirmed or Adjusted
            f1 = _CONFIDENCE_SEVERITY[confidence] * 1.0

        evidence_severity = _EVIDENCE_SEVERITY_FLOOR[evidence_state]

        # Combination rule: evidence_severity is always the DOMINANT
        # term (D2 section 8.3's conflict-resolution rule -- a High-
        # confidence mapping backed by Rejected/NotProvided evidence must
        # still be treated as a gap, never "probably fine because the AI
        # was confident"). f1 contributes only a small, strictly
        # ADDITIVE offset (never a reduction, never large enough to move
        # a result across an evidence-severity tier boundary: f1's max
        # possible value is 3.0, scaled below by 0.1, so its max
        # contribution of 0.3 is smaller than the gap of >=1 between any
        # two evidence-severity floors). This single formula satisfies
        # BOTH structural invariants at once -- the evidence-state
        # ordering (Verified < Pending < NotProvided <= Rejected) and the
        # confidence-vs-evidence dominance rule -- without needing a
        # separate special-cased branch for "High confidence + bad
        # evidence" that could (and, before this fix, did -- see
        # tests/test_engine.py's dominance test) produce an inconsistent
        # severity scale against the ordinary case.
        per_control_severity[control_id] = evidence_severity + (f1 * 0.1)

    raw_score = sum(per_control_severity.values()) * weights.get("overall_multiplier", 1.0)
    max_possible = max(len(per_control_severity) * 6, 1)  # rough normalization ceiling
    risk_score = min(100.0, (raw_score / max_possible) * 100.0)

    low_max = thresholds.get("low_max", 33)
    medium_max = thresholds.get("medium_max", 66)
    if risk_score <= low_max:
        tier = RiskTier.LOW
    elif risk_score <= medium_max:
        tier = RiskTier.MEDIUM
    else:
        tier = RiskTier.HIGH

    residual = [
        f"{cid}: severity {sev:.1f}" for cid, sev in sorted(per_control_severity.items(), key=lambda kv: -kv[1])[:5]
    ]
    return False, tier, residual, []


def evaluate(engine_input: EngineInput, config: PolicyConfigSnapshot) -> EngineOutput:
    layer1_terminal, layer1_gaps = _evaluate_layer1(engine_input, config)
    if layer1_terminal:
        return EngineOutput(
            outcome=EngineOutcome.INSUFFICIENT_INFORMATION,
            decision_layer_attribution=1,
            risk_tier=None,
            rationale=layer1_gaps,
        )

    layer2_terminal, layer2_fired = _evaluate_layer2(engine_input, config)
    if layer2_terminal:
        return EngineOutput(
            outcome=EngineOutcome.NO_GO,
            decision_layer_attribution=2,
            risk_tier=None,
            rationale=layer2_fired,
        )

    layer3_refused, tier, residual, missing_config = _evaluate_layer3(engine_input, config)
    if layer3_refused:
        return EngineOutput(
            outcome=None,
            decision_layer_attribution=3,
            risk_tier=None,
            rationale=[],
            refused=True,
            missing_config=missing_config,
        )

    return EngineOutput(
        outcome=EngineOutcome.GO,
        decision_layer_attribution=3,
        risk_tier=tier,
        rationale=residual,
    )
