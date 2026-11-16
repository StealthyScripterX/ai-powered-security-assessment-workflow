"""Seed data for the Organizational Decision Registry -- purpose,
impact, and proposed-options text transcribed directly from
docs/baseline/README.md's Open Decisions index and the originating D1/
D2/D4/D5 sections, not invented here. The six BLOCKING decisions
(README.md: "identical in membership across all five audit rounds").

`proposed_options` are the architecture's own documented possibilities
(e.g. TASD-v1.0.md section 24's OD-01 note that a tiered model would
split the RACI "Final Approver" row) -- they are OFFERED to the
decision-maker, never auto-selected. Nothing in this file or its caller
(app/services/catalog_seed.py's sibling, run once at startup) ever sets
`current_status` to anything but `Open`.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.od_registry import ODStatus, OrganizationalDecision

_DECISIONS: list[dict] = [
    {
        "id": "OD-01",
        "title": "Approval tier structure",
        "purpose": (
            "D5-Approval-Audit.md section 4 uses a single-tier interim RACI model, explicitly marked as "
            "a placeholder. Resolving this decides whether every POC goes through one Final Approver, or "
            "whether higher-risk POCs require a tiered/multi-stage approval chain."
        ),
        "impact": (
            "Blocks finalizing the approval RACI and the ApprovalDecision data model's tier field "
            "(architecture/TASD-v1.0.md section 17.1). Until resolved, policy_config.approval_tier_model "
            "stays NULL and the single-tier model remains active."
        ),
        "proposed_options": [
            {"label": "single_tier", "description": "One Final Approver role decides every POC, regardless of risk tier.", "implications": "Simplest; matches the current placeholder model exactly."},
            {"label": "risk_tiered", "description": "Approval authority scales with the engine's risk_tier (Low/Medium/High) once Layer 3 is configured (OD-15/OD-16).", "implications": "Requires OD-15/OD-16 resolved first; adds a dependency between three Open Decisions."},
            {"label": "fixed_multi_stage", "description": "Every POC requires sign-off from more than one Approver role regardless of risk.", "implications": "Simpler than risk-tiering but slower for every request, including low-risk ones."},
        ],
        "is_blocking": True,
    },
    {
        "id": "OD-06",
        "title": "Who holds the Environment Owner role",
        "purpose": (
            "D4-Environment-Readiness.md section 7 requires the Environment Owner to not be the Requester "
            "and to have real technical visibility into the environment, but does not name who that is."
        ),
        "impact": (
            "Blocks meaningfully operating environment-readiness sign-off -- the platform enforces the "
            "separation-of-duties RULE (RBAC role check) regardless, but the organization has not yet "
            "said which real individuals/teams should be granted the EnvironmentOwner role."
        ),
        "proposed_options": [
            {"label": "infra_team", "description": "Infrastructure/Platform engineering team owns environment attestation for all POCs.", "implications": "Centralized, consistent; may become a bottleneck at higher volume."},
            {"label": "per_project_owner", "description": "Each POC's hosting team designates its own Environment Owner at intake time.", "implications": "Scales better; requires a mechanism to verify the designee's technical standing per D4 section 7."},
        ],
        "is_blocking": True,
    },
    {
        "id": "OD-07",
        "title": "Who may validate evidence (and judge sufficiency)",
        "purpose": (
            "D5-Approval-Audit.md section 8 names Security Reviewer as the default evidence validator, "
            "pending whether Final Approver should also be eligible; D3-Methodology.md section 11's "
            "evidence_requirement.validator_role field already supports both values."
        ),
        "impact": (
            "Blocks extending evidence validation beyond the current Security-Reviewer-only default "
            "(architecture/TASD-v1.0.md section 15.2) -- not a gap in what the platform enforces today, "
            "only in whether the organization wants a second eligible role."
        ),
        "proposed_options": [
            {"label": "reviewer_only", "description": "Only SecurityReviewer may transition evidence to Verified/Rejected (current default).", "implications": "No change needed -- this is already how the system behaves."},
            {"label": "reviewer_or_approver", "description": "FinalApprover may also validate evidence directly.", "implications": "Faster for small teams; blurs the separation between evidence validation and authorization that BR-010/D2 section 9.2 establish for the AI boundary (though not for human roles)."},
        ],
        "is_blocking": True,
    },
    {
        "id": "OD-10",
        "title": "Layer 1 Completeness threshold",
        "purpose": (
            "D2-AI-Governance.md section 8.1 Rule 3: the fraction of unusable (blank/non-responsive/"
            "contradictory) answers that trips Insufficient Information. No threshold is specified in "
            "the baseline -- inventing one here would be exactly the 'plausible-looking default presented "
            "as specification' the architecture explicitly refuses to do."
        ),
        "impact": (
            "BLOCKS Layer 1 Rule 3 from ever evaluating (architecture/TASD-v1.0.md section 14.7): the "
            "engine returns Insufficient Information for every assessment via the engine-refusal path "
            "until this is set, even when the requester answered every question usably."
        ),
        "proposed_options": [
            {"label": "conservative_10pct", "description": "0.10 -- more than 1 in 10 unusable answers trips Insufficient Information.", "implications": "Strict; may route many borderline-quality submissions to Insufficient Information."},
            {"label": "moderate_30pct", "description": "0.30 -- more than 3 in 10 unusable answers trips it.", "implications": "A common starting point; the organization's own risk tolerance should ultimately set this."},
        ],
        "is_blocking": True,
    },
    {
        "id": "OD-15",
        "title": "Layer 3 risk-factor weights (F1-F5)",
        "purpose": (
            "D2-AI-Governance.md section 8.3: the numeric weight for each risk factor (mapping confidence/"
            "review-status, evidence state, conditional-domain findings, accepted exceptions, data "
            "sensitivity), including the Pending-Review discount within F1. Explicitly not specified -- "
            "'no weight is specified in this document.'"
        ),
        "impact": (
            "BLOCKS Layer 3 implementation ENTIRELY (architecture/TASD-v1.0.md section 14.7): no `GO` "
            "recommendation can ever be issued, under any circumstance, until this AND OD-16 are both set."
        ),
        "proposed_options": [
            {"label": "equal_weighting", "description": "Weight every factor equally (F1=F2=F3=F4=F5), Pending-Review discount 0.5.", "implications": "Simple starting point; does not reflect that evidence state (F2) is usually considered more load-bearing than data sensitivity (F5) alone."},
            {"label": "evidence_weighted", "description": "Weight F2 (evidence state) and F1 (mapping confidence/review-status) higher than F3-F5.", "implications": "Matches D2 section 8.3's own qualitative emphasis on evidence-state dominance; still requires the organization to pick exact numbers."},
        ],
        "is_blocking": True,
    },
    {
        "id": "OD-16",
        "title": "Layer 3 risk-score thresholds/tiers",
        "purpose": (
            "D2-AI-Governance.md section 8.3: the cut points that turn a normalized risk score into "
            "Low/Medium/High. Explicitly not specified -- 'no threshold values are specified.'"
        ),
        "impact": (
            "BLOCKS Layer 3 implementation ENTIRELY, alongside OD-15 -- weights alone cannot produce a "
            "tier without cut points. Also ties to OD-01 if the organization resolves toward risk-tiered "
            "approval."
        ),
        "proposed_options": [
            {"label": "thirds", "description": "Low 0-33, Medium 34-66, High 67-100 (even thirds of the normalized score).", "implications": "Simple, symmetric starting point."},
            {"label": "conservative_high_bar", "description": "Low 0-20, Medium 21-50, High 51-100 (High tier reachable at a lower score).", "implications": "Flags more assessments as High risk for extra scrutiny; fewer false negatives, more Approver review load."},
        ],
        "is_blocking": True,
    },
]


async def seed_od_registry_if_empty(db: AsyncSession) -> None:
    existing = await db.execute(select(OrganizationalDecision.id).limit(1))
    if existing.first() is not None:
        return

    for entry in _DECISIONS:
        db.add(
            OrganizationalDecision(
                id=entry["id"],
                title=entry["title"],
                purpose=entry["purpose"],
                impact=entry["impact"],
                proposed_options=entry["proposed_options"],
                is_blocking=entry["is_blocking"],
                current_status=ODStatus.OPEN,
            )
        )
    await db.commit()
