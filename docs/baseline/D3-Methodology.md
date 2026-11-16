# D3-Methodology — Answer-to-Control Mapping Methodology

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | D3-Methodology |
| Title | Answer-to-Control Mapping Methodology |
| Project | AI-Powered Security Assessment & POC Approval Workflow |
| Status | Draft — incorporated into documentation baseline |
| Depends on | D2, D3-Catalog |
| Feeds | D4, D5 |

## 2. Purpose

Defines how a requester's questionnaire answers and evidence get mapped to the specific ISO/NIST control identifiers in D3-Catalog, with confidence scoring, rationale, and a reviewer-override path — and hosts the organizational "policy hooks" that D2's decision engine depends on but does not itself define.

## 3. Scope

Covers the mapping process and record structure, confidence scoring, evidence linkage, the reviewer override mechanism, conditional-domain triggers, organizational policy hooks, per-control evidence requirements, and edge-case handling. Policy content (which conditions elevate to a Layer-2 blocker, what evidence counts as sufficient) is explicitly left for the organization to populate and is not invented here.

## 4. Definitions and Terminology

See the consolidated Glossary in `README.md`. This document defines `confidence`, `review_status`, and `EvidenceRequirement` specifically.

## 5. Roles and Responsibilities

| Role | Responsibility |
|---|---|
| AI Agent | Produces a mapping record per candidate control for each submitted answer; provenance always `AI_ASSERTION`. |
| Security Reviewer / GRC Analyst | Confirms, adjusts, or rejects each mapping record (§8); performs evidence-sufficiency judgment (**OD-07**, **OD-17**). |

## 6. Mapping Process

1. Each questionnaire answer is associated, at question-authoring time (D2 §7), with one or more candidate control identifiers from D3-Catalog.
2. When an answer is submitted, the AI agent produces a mapping record per candidate control: `{control_id, framework, answer_excerpt, provenance_tag, confidence, rationale, review_status}`.
3. **Assessment-relevant fields for versioning** (D2 §8.5, `mapping_hash`): `control_id`, `confidence`, `review_status`, and `rationale` are assessment-relevant — a change to any of them changes `mapping_hash` and stales existing recommendations. `framework` and `provenance_tag` are not assessment-relevant (fixed/constant). `answer_excerpt` is not separately assessment-relevant either — a change to the underlying answer is covered as a questionnaire change (D2 §8.5, item 6), which produces a new mapping record rather than mutating this field in place.
4. Every mapping record is `AI_ASSERTION` by provenance (D2 §6) — provenance never changes, even after review (see §8 below). Its separate `review_status` field starts at `Pending Review` and changes only through the mechanism in §8.

## 7. Confidence Scoring

`confidence` ∈ {High, Medium, Low}:

- **High** — the answer directly and unambiguously addresses the control's requirement (e.g., a specific named isolation mechanism for A.8.31/SC-7).
- **Medium** — the answer is relevant but partial, generic, or relies on an `AI_ASSUMPTION` to connect it to the control.
- **Low** — the answer is tangentially related; mapping is offered for reviewer judgment, not asserted as settled.

## 8. Evidence Linkage and Reviewer Override Mechanism

### 8.1 Evidence Linkage

Each control's "satisfaction" for this POC is a function of **both** the mapping confidence (§7) **and** the evidence state of whatever material supports it (D1 BR-005: Not Provided / Submitted–Pending Review / Verified–Human Validated / Rejected–Insufficient Evidence). A High-confidence mapping backed only by `Submitted–Pending Review` material is not equivalent to one backed by `Verified–Human Validated` material — the Risk Scoring layer (D2 §8.3) weights these differently, with Verified evidence reducing residual risk more than Pending evidence of the same confidence level.

### 8.2 Three Independent Axes

Provenance (D2 §6), mapping review status (this section), and evidence state (D1 BR-005) are three separate, independent axes and must never be merged:

| Axis | Lives on | Values | Set by |
|---|---|---|---|
| Provenance (D2 §6) | Every tagged statement | `REQUESTER_FACT` / `AI_ASSERTION` / `AI_ASSUMPTION` / `MISSING_EVIDENCE` | Origin-determined, immutable once set |
| Mapping `review_status` (this section) | Mapping records only | `Pending Review` / `Confirmed` / `Adjusted` / `Rejected` | Security Reviewer action |
| Evidence state (D1 BR-005) | Submitted material only | `Not Provided` / `Submitted – Pending Review` / `Verified – Human Validated` / `Rejected / Insufficient Evidence` | Security Reviewer action (separately, on the material, not the mapping) |

A mapping record's `provenance_tag` always remains `AI_ASSERTION` — the AI proposed it. Its `review_status` moves through the transitions below.

### 8.3 Reviewer Override Transitions

- A Security Reviewer/GRC Analyst may, for any mapping record: **Confirm** (`review_status → Confirmed`, no change to control_id/confidence), **Adjust** (`review_status → Adjusted`; control_id, confidence, or rationale may change), or **Reject** (`review_status → Rejected`; the mapping is excluded from scoring, with a required reason).
- Every transition is logged as a new record, not an edit-in-place — the original AI mapping and the Reviewer's action both persist, linked, so the audit trail (D5) shows what the AI proposed and what the human changed.
- A mapping with `review_status = Pending Review` may still feed Layer 3 risk scoring (D2 §8.3, factor F1) as an `AI_ASSERTION`-only input, but a `Confirmed` or `Adjusted` mapping is weighted more heavily than a `Pending Review` one of the same confidence level — mirroring, at the mapping-review axis, the same evidence-state-dominance principle D2 §8.3 applies to evidence. D2 §8.3's F1 definition states this same rule (Rejected excluded / Pending Review discounted / Confirmed-Adjusted full weight) as part of its own factor definition. Confidence and `review_status` remain two separate fields in both documents; the discount magnitude itself is **OD-15**.

## 9. Conditional-Domain Trigger Table

| Trigger signal (from scope text or an answer) | Conditional domain activated |
|---|---|
| Scope names a third-party vendor, contractor, or external service provider | Domain 9 (Third-Party/Cloud/Supply Chain) |
| Scope indicates the environment is hosted on a cloud provider | Domain 9 |
| Scope or an answer references personal data, customer data, or employee data | Domain 10 (Privacy & PII) |
| Scope indicates custom code or integration development is part of the POC | Domain 5's conditional controls (A.8.25 / SA-11) specifically, not the whole domain (already Mandatory) |

Each trigger detection is logged with the exact text/answer it relied on (D2 §7), so a Reviewer can audit why a domain was or wasn't activated.

## 10. Organizational Policy Hooks

This is the table D2 §8.2 (Layer 2) refers to for scope-conditional Mandatory Security Blockers. It is **intentionally left empty of invented content**:

| Policy hook ID | Condition | Elevates to Layer-2 blocker? | Owner | Status |
|---|---|---|---|---|
| PH-01 | RA-5 (vulnerability scan) evidence is `Not Provided` AND data sensitivity = High | **TBD** | GRC/Compliance | Open — see **OD-11** |
| PH-02 | A.8.24/SC-8/SC-28 (encryption) evidence is `Not Provided` AND data classified as Confidential or above | **TBD** | GRC/Compliance | Open — see **OD-11** |
| PH-03 | A.5.34/PT-2 (PII) triggered AND no lawful-basis evidence provided | **TBD** | Privacy/Legal | Open — see **OD-11** |

Until the organization resolves **OD-11**, these three conditions are treated **only** as Layer-3 risk-scoring inputs (weighted, not gating) — consistent with D1's position that none of RA-5, encryption, or PII presence may be an automatic blocker.

## 11. Evidence Requirements per Control

Each control a mapping references needs a defined answer to four questions before "satisfaction" can be evaluated at all. This structure is defined here; the organization-specific content (what counts as sufficient) is **not invented** — it is marked as a policy decision per control family.

```
EvidenceRequirement {
  control_id                      // from D3-Catalog
  expected_evidence_description   // what kind of material/attestation satisfies this
                                   // control for a POC context (e.g., "network
                                   // diagram or firewall rule export showing
                                   // segregation" for A.8.22)
  validator_role: Security Reviewer   // per OD-07 default; may extend to
                                       // Final Approver if OD-07 resolves that way
  sufficiency_criteria: TBD           // POLICY DECISION — not invented here.
                                       // Tracked per control family as it's defined.
  contradiction_handling: ref(§12, "Evidence contradicts claim")
}
```

- `expected_evidence_description` can and should be drafted per control as a documentation task (what *kind* of evidence is relevant) — this is descriptive, not a policy judgment call, and is a follow-on content task rather than invented wholesale here for all catalog controls.
- `sufficiency_criteria` (what makes evidence *enough*, as opposed to merely *relevant*) is a genuine organizational policy decision — e.g., whether a network diagram alone suffices for A.8.22, or whether a reviewer must also confirm against a live config export. This is **Open Decision OD-17**, scoped per control family, not resolved in this document.
- When evidence contradicts a requester's claim, §12's "Evidence contradicts claim" rule applies: confidence is forced to Low and the contradiction is logged — this governs *all* controls uniformly and does not wait on OD-17.

## 12. Edge Cases

- **Conflicting answers:** if two answers contradict each other (e.g., one says "no third parties," another names a vendor), the mapping engine flags `MISSING_EVIDENCE` with a contradiction note rather than silently picking one; this is a Layer 1 Completeness signal candidate (**OD-10** threshold applies).
- **Evidence contradicts claim:** if an uploaded attachment's content contradicts the requester's stated answer, the mapping confidence for the affected control is forced to Low regardless of what it would otherwise have been, and the contradiction is logged for Reviewer attention.
- **Partial answer across multiple controls:** a single answer may map to multiple controls at different confidence levels (e.g., one answer partially addresses both A.8.2 and AC-6) — this is expected and not an error state.

## 13. Dependencies and Related Documents

Depends on D2 (provenance model, decision engine) and D3-Catalog (control identifiers). Feeds D4 (readiness-dimension related controls) and D5 (mapping summary feeding the approval request object).

## 14. Assumptions and Constraints

Policy hooks (§10) and evidence sufficiency criteria (§11) remain empty of invented content until the organization fills them in.

## 15. Acceptance Criteria

- [ ] Every mapping record carries confidence, rationale, provenance (always `AI_ASSERTION`), and `review_status`.
- [ ] No mapping reaches `Confirmed`/`Adjusted` standing without an explicit Reviewer action (§8); `review_status` and evidence state are never conflated.
- [ ] Conditional-domain activation is always traceable to a specific trigger (§9).
- [ ] Policy hooks (§10) and evidence sufficiency criteria (§11) remain empty of invented content until the organization fills them in.

## 16. Open Decisions Arising From This Document

| ID | Decision | Impact | Recommended owner |
|---|---|---|---|
| OD-11 | Policy-hook content (PH-01/02/03) — carried from D2 | Blocks Layer-2 scope-conditional blockers | GRC/Compliance owner |
| OD-17 | Per-control-family evidence sufficiency criteria (§11) | Blocks a reviewer having a consistent bar for "sufficient" evidence; without it, sufficiency judgment is ad hoc per reviewer | GRC/Compliance owner |

## 17. References

D2 — AI Governance & Decision Boundary Specification. D3-Catalog — Security Control Catalog. D4 — Security Test Environment Readiness SOP. D5 — Approval, RACI & Audit Trail Specification. `README.md` for the consolidated Open Decisions index.

## 18. Revision History

| Version | Status | Notes |
|---|---|---|
| v1.0 | Draft, incorporated | Formatting revised for publication. The three-axis separation of provenance, mapping review status, and evidence state (§8.2) — previously described as a correction removing a since-discarded fifth provenance type — is now stated directly as the governing rule, with no change to its substance. |
