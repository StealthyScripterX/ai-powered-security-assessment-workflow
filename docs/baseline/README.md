# AI-Powered Security Assessment & POC Approval Workflow — Documentation Pack

## Documents, in dependency order

1. **[D1-Requirements.md](./D1-Requirements.md)** — APPROVED, FROZEN v1.0. The requirements baseline: business problem, stakeholders, scope, full business requirements (BR-001–BR-019), KPIs, assumptions, risks, and the authoritative list of Open Decisions.
2. **[D3-Control-Catalog.md](./D3-Control-Catalog.md)** — The static reference: 11 control domains, specific ISO/IEC 27001:2022 Annex A and NIST SP 800-53 Rev. 5 control identifiers, each tagged by Control Subject (Org/Target/TestEnv/Platform). Flagged UNVERIFIED pending validation against licensed standards text.
3. **[D2-AI-Governance.md](./D2-AI-Governance.md)** — The AI/human authority boundary: content-provenance tagging, questionnaire generation logic, the three-layer deterministic decision engine (Completeness → Blockers → Risk Scoring), prompt-injection resistance, and authorization-boundary enforcement.
4. **[D3-Methodology.md](./D3-Methodology.md)** — How specific answers get mapped to D3-Catalog controls: confidence scoring, reviewer overrides, conditional-domain triggers, and the (currently empty) organizational policy hooks that D2's Layer 2 blockers depend on.
5. **[D4-Environment-Readiness.md](./D4-Environment-Readiness.md)** — Security Test Environment readiness: isolation, access, test data, config baseline, logging, backup/rollback, decommissioning, and the Environment Owner sign-off data model that gates GO.
6. **[D5-Approval-Audit.md](./D5-Approval-Audit.md)** — Human approval RACI (interim single-tier, pending OD-01), the Approval object data model, evidence-validation workflow, and the append-only hash-chained atomic audit trail design.

## Workflow summary

```
Scope Submission → AI Scope Analysis → Questionnaire (11-15 Qs) →
Responses → AI Assessment Artifacts (assumptions/gaps marked) →
Control Mapping (ISO/NIST identifiers) → Evidence Classification
(4 states) → Environment Readiness + Owner Sign-off →
Decision Engine (Completeness → Blockers → Risk Score) →
GO / NO-GO / Insufficient Information (advisory) →
POC Approval Request → Human Approval (binding) →
Audit Trail Entry at every step (atomic, hash-chained)
```

## Non-negotiables preserved throughout this pack

- No pre-existing documentation required from the requester.
- AI never authorizes; only a human Approver does.
- AI never auto-verifies evidence; uploads start as "Submitted – Pending Review."
- Three outcomes only: GO / NO-GO / Insufficient Information — never forced.
- GO is structurally blocked without complete Environment Owner sign-off.
- Audit trail is append-only, hash-chained, atomic with every transition.

## Open Decisions index (consolidated across all documents)

This is the master list. No decision here is invented by this documentation pack — each is a specific question only the organization can answer.

| ID | Decision | Raised in | Status |
|---|---|---|---|
| OD-01 | Approval tier structure (single/risk-tiered/fixed multi-stage) | D1, D5 | Open — **blocking** |
| OD-02 | Long-term environment-readiness integration scope | D1, D4 | Open |
| OD-03 | Single-enterprise vs. multi-tenant | D1 | Open |
| OD-04 | No triage-time baseline exists | D1 | Open |
| OD-05 | Detailed evidence/blocker rule sets | D1 | **Reconciled** — addressed by OD-10 (completeness threshold), OD-11 (policy hooks), and OD-17 (evidence sufficiency criteria) below, not resolved on its own |
| OD-06 | Who holds "Environment Owner" | D1, D4 | Open — **blocking** |
| OD-07 | Who may validate evidence (and, per D3-Methodology §11, who validates sufficiency) | D1, D3-Methodology, D5 | Open — **blocking** |
| OD-08 | Audit integrity-verification schedule/owner | D1, D5 | Open (default suggested: daily / Platform Owner) |
| OD-09 | External audit-chain anchoring required? | D1, D5 | Open |
| OD-10 | Layer 1 Completeness threshold | D2 | Open — **blocking** |
| OD-11 | Policy-hook content (PH-01/02/03) | D2, D3-Methodology | Open (safe default exists) |
| OD-12 | AI-recommendation-match monitoring cadence/escalation | D2, D5 | Open |
| OD-14 | Whether a formal emergency-override mechanism for approval preconditions should exist at all | D5 | Open — default is **no** such mechanism |
| OD-15 | Layer 3 risk-factor weights (F1–F5) | D2 | Open — **blocking**, blocks Layer 3 implementation |
| OD-16 | Layer 3 risk-score thresholds/tiers | D2 | Open — **blocking**, blocks Layer 3 implementation |
| OD-17 | Per-control-family evidence sufficiency criteria | D3-Methodology | Open (safe default exists) |
| OD-18 | Extend the non-waivable exception dimension list beyond Isolation/Access Control? | D4 | Open |
| OD-19 | Escalation behavior when a remediation deadline passes unresolved | D4 | Open |
| OD-20 | Post-approval revocation handling (testing already underway) | D4 | Open |
| OD-21 | Does a detected audit-integrity break halt new transitions or only alert? | D5 | Open |

**Six Open Decisions are blocking** (OD-01, OD-06, OD-07, OD-10, OD-15, OD-16): the system cannot be operated, or cannot reach its first `GO`, until these are resolved. See `AUDIT-REPORT.md` §6 for the full verdict and rationale.

## Glossary

| Term | Meaning |
|---|---|
| POC | Proof-of-Concept security testing engagement this workflow governs intake and authorization for. |
| Provenance tag | One of four labels (`REQUESTER_FACT`, `AI_ASSERTION`, `AI_ASSUMPTION`, `MISSING_EVIDENCE`) marking the origin of every statement in the system (D2 §6). |
| Mapping review status | `Pending Review` / `Confirmed` / `Adjusted` / `Rejected` — a Security Reviewer's judgment on an AI-proposed control mapping, independent of provenance and evidence state (D3-Methodology §8.2). |
| Evidence state | `Not Provided` / `Submitted – Pending Review` / `Verified – Human Validated` / `Rejected / Insufficient Evidence` — the four-state model for submitted material (D1 BR-005). |
| AssessmentInputVersion | A monotonically-increasing version stamp over every assessment-relevant input for a POC request; used to detect staleness (D2 §8.5). |
| Recommendation | The engine's immutable, versioned output: one of `GO` / `NO-GO` / `INSUFFICIENT_INFORMATION`, advisory only (D2 §8.5). |
| Mandatory Security Blocker | A Layer 2 condition that forces `NO-GO` regardless of risk score (D2 §8.2). |
| Risk tier | `Low`/`Medium`/`High` metadata attached only to a `GO` outcome — never a fourth outcome (D2 §8.3). |
| Attestation | An Environment Owner's structured claim that one readiness dimension is ready, possibly with an exception (D4 §6). |
| Exception / Disposition | A documented, authorized judgment that an unresolved readiness issue is `Accepted`, `Rejected`, or `Deferred` (D4 §6). |
| Hash chain | The SHA-256, canonically-serialized, append-only linkage between audit entries that makes tampering detectable (D5 §10.3). |
| Open Decision (OD) | A question only the organization can answer; never invented or defaulted by this documentation pack. |

## What this pack does not contain

Code, architecture implementation, or a build of any kind — this remains a documentation-only deliverable, consistent with the project's documentation-first approach.

## Related documents

- `AUDIT-REPORT.md` — the internal historical audit record covering how this baseline was reviewed and hardened across five rounds. Retained for traceability; its findings are not re-stated as requirements in D1–D5, which now state the resulting rules directly in their final form.
- `PUBLICATION-QA-REPORT.md` — the quality-assurance report for this publication pass (formatting and structure only; no substantive content change).
