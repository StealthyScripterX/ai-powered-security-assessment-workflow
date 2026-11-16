# AI-Powered Security Assessment & POC Approval Workflow — Documentation Pack

## Round 2 corrections (independent review findings)

A second, independent review of the first pack found one CRITICAL and five MAJOR issues the original consolidated audit missed. All are addressed in this version:

1. **CRITICAL, fixed:** D5 now enforces server-side preconditions (§3a) so a Final Approver cannot write an `Approved` decision while environment sign-off is incomplete, a Mandatory Security Blocker is unresolved, or the recommendation is Insufficient Information — closed at the transaction level, not just by role convention.
2. **MAJOR, fixed:** D4's exception model replaced a bare co-signature with a full exception record (issue, risk assessment, compensating controls, disposition, remediation owner/deadline, expiry) and named Isolation/Access Control as never-waivable.
3. **MAJOR, addressed as far as possible without inventing policy:** D2's Layer 3 risk-scoring model is now a complete framework (required factors, calculation shape, evidence-dominance and conflict-resolution rules) with weights and thresholds explicitly left as Open Decisions (OD-15, OD-16) rather than implied.
4. **MAJOR, fixed:** the fifth provenance type introduced in D3-Methodology was removed; provenance stays at the four types D2 defines, with mapping review status and evidence state kept as separate, independent fields.
5. **MAJOR, addressed:** D3-Methodology now defines the structure of per-control evidence requirements (§6a), with sufficiency criteria correctly left as a policy decision (OD-17).
6. **Additional fixes:** D4 gained exception expiry/remediation tracking and a revocation mechanism; D5 requires a distinct disagreement rationale when an Approver's decision contradicts the AI recommendation, and now specifies the hash algorithm (SHA-256), canonical serialization, concurrent-write ordering, and integrity-failure handling/recovery for the audit trail.

## Round 3 corrections (second independent review)

A second independent review found two MAJOR issues round 2 missed, plus four MINOR items. All addressed without introducing any new numbered Open Decisions — every fix below is structural/technical, not a new organizational policy question:

1. **MAJOR-01, fixed:** D2 §4e adds an explicit `AssessmentInputVersion`/`Recommendation` versioning model. Six invalidating change types (evidence, mapping, mapping-review, environment attestation/revocation, questionnaire, policy/config) are enumerated; a new precondition **P4** in D5 §3a rejects any approval attempt against a stale recommendation and triggers a synchronous fresh engine run. Recommendations are immutable and never overwritten — superseding runs create new rows.
2. **MAJOR-02, fixed:** D2 §4c's F1 now explicitly reconciles with D3-Methodology §4 — `Rejected` mappings are excluded from scoring, `Pending Review` mappings are discounted relative to `Confirmed`/`Adjusted` ones, and the discount magnitude is folded into the existing OD-15 (no new decision invented).
3. **MINOR, fixed:** risk tiers are explicitly confirmed as metadata on a `GO` outcome, not a fourth outcome (D2 §4c).
4. **MINOR, fixed:** rejected/blocked approval attempts and audit-store failures now have an explicit durable-logging and fail-closed rule (D5 §5.1a), closing a gap BR-019's original phrasing (written around successful transitions) didn't quite cover.
5. **MINOR, fixed:** actor-identity fields (`approver_id`, `environment_owner_id`, `disposition_authorized_by`, `revoked_by`, and audit-entry actors) are now explicitly stated to be server-derived from authenticated context, never client-supplied (D2 §6, D4 §4, D5 §3).
6. **MINOR, fixed:** the decision-engine re-run trigger rule is now explicit — lazy, on-demand (explicit resubmission, or automatically on a P4 staleness detection), not an eager background process (D2 §4e).

## Round 4 corrections (third independent review)

A third independent review found three final targeted clarifications, all closed by structural/technical specification without introducing any new numbered Open Decisions:

1. **Concurrency safety, fixed:** D5 §3a's precondition P4 (recommendation freshness) read the current `AssessmentInputVersion` and wrote the `ApprovalDecision` as two separate operations, leaving a TOCTOU gap in which an invalidating change could land between the check and the commit. D5 §3a now mandates that the two occur as a single unit protected by either `SERIALIZABLE` transaction isolation or an explicit row/version lock (optimistic-concurrency check against `AssessmentInputVersion.version`) — equivalent mechanisms, either mandatory in substance, so no `Approved` decision can ever commit against a version that stopped being current before the write landed.
2. **Assessment hash coverage, fixed:** D2 §4e's `evidence_state_hash` and `mapping_hash` definitions were silent on whether an evidence artifact's own upload, replacement, or deletion — or a change to which control an evidence artifact is linked to — would register as a change if the evidence-state enum and mapping fields themselves stayed put. Both hash definitions are now explicit: `evidence_state_hash` covers each control's state value *and* the identity/content-digest of every artifact currently attached to it; `mapping_hash` covers each mapping's fields *and* every evidence-control link. The invalidating-changes list (D2 §4e) gained an explicit item for evidence-artifact changes, renumbering the list (D4 §5.2's cross-reference to "item 4" was updated to the new numbering).
3. **Decision-type clarification, fixed:** D5 §3a and D2 §4e previously implied, without quite saying, that staleness (P4) might gate every approval action. Both documents now explicitly agree: **P4 gates `Approved` decisions only.** `Rejected` and `MoreInfoRequested` are always permitted regardless of staleness — rejecting a request or asking for more information grants no testing authorization, so gating either on freshness would only trap an unwanted stale request rather than protect anything. Every `ApprovalDecision` (including `Rejected`/`MoreInfoRequested` ones) now records `recommendation_was_stale` as a transparent fact rather than silently omitting the check. `MoreInfoRequested` is confirmed as the path that starts a new assessment cycle: the requester's new answer is invalidating-change item 6 (questionnaire changes), which creates a fresh `AssessmentInputVersion` that any later decision is checked against.

## Round 5 corrections (final consolidation)

A final consolidated correction closes three remaining gaps in the staleness/versioning model, all closed by structural/technical specification without introducing any new numbered Open Decisions:

1. **Scope versioning, fixed:** D2 §4e gained a `scope_hash` field on `AssessmentInputVersion` and an explicit 8th invalidating-change item: creation, modification, replacement, or deletion of the scope submission (`scope_submission_ref`) that initiated the POC request now versions and stales existing recommendations, consistent with every other assessment-relevant change. Creation of the scope submission establishes the request's first version.
2. **Mapping hash coverage, fixed:** D3-Methodology's mapping record carries more fields (`answer_excerpt`, `provenance_tag`, `rationale`) than D2 §4e's `mapping_hash` previously named. Both documents now explicitly agree on which fields are assessment-relevant (`control_id`, `confidence`, `review_status`, `rationale`) and which are not (`framework` and `provenance_tag` are fixed/constant; `answer_excerpt` changes are already covered via the questionnaire-change pathway, which produces a new mapping record rather than mutating this field). `mapping_hash` now covers `rationale` in addition to the fields already covered in round 4.
3. **Environment hash coverage, fixed:** D2 §4e's `environment_readiness_hash` previously said only "attestation/sign-off/exception state" without enumerating it. It now explicitly lists every field it covers: `status`, `attestation_text`, every `ExceptionRecord` field (issue description, risk assessment, compensating controls, disposition, disposition rationale, remediation owner/deadline, expiry, revocation fields), supporting evidence references, and the resulting `final_signoff_boolean`. D4's `EnvironmentReadinessAttestation` gained an explicit `supporting_evidence` field (previously referenced only implicitly) so the hash definition has something concrete to point at.

**Self-found and fixed during this round's consistency pass, not in your list:** D5 §3a's `MoreInfoRequested` discussion (added in round 4) cited D2 §4e's invalidating-change list as "item 5, questionnaire changes" — but round 4's own renumbering (inserting evidence-artifact changes as item 2) had already shifted questionnaire changes to item 6, and this one cross-reference was missed at the time. Corrected to "item 6" in this round, the same way round 3 logged its own self-found `POCApprovalRequest` inconsistency and round 4 logged its D4 renumbering check.

## Documents, in dependency order

1. **[D1-project-requirements.md](./D1-project-requirements.md)** — APPROVED, FROZEN v1.0. The requirements baseline: business problem, stakeholders, scope, full business requirements (BR-001–BR-019), KPIs, assumptions, risks, and the authoritative list of Open Decisions.
2. **[D3-catalog.md](./D3-catalog.md)** — The static reference: 11 control domains, specific ISO/IEC 27001:2022 Annex A and NIST SP 800-53 Rev. 5 control identifiers, each tagged by Control Subject (Org/Target/TestEnv/Platform). Flagged UNVERIFIED pending validation against licensed standards text.
3. **[D2-ai-governance-decision-boundary.md](./D2-ai-governance-decision-boundary.md)** — The AI/human authority boundary: content-provenance tagging, questionnaire generation logic, the three-layer deterministic decision engine (Completeness → Blockers → Risk Scoring), prompt-injection resistance, and authorization-boundary enforcement.
4. **[D3-methodology.md](./D3-methodology.md)** — How specific answers get mapped to D3-Catalog controls: confidence scoring, reviewer overrides, conditional-domain triggers, and the (currently empty) organizational policy hooks that D2's Layer 2 blockers depend on.
5. **[D4-environment-readiness-sop.md](./D4-environment-readiness-sop.md)** — Security Test Environment readiness: isolation, access, test data, config baseline, logging, backup/rollback, decommissioning, and the Environment Owner sign-off data model that gates GO.
6. **[D5-approval-raci-audit-trail.md](./D5-approval-raci-audit-trail.md)** — Human approval RACI (interim single-tier, pending OD-01), the Approval object data model, evidence-validation workflow, and the append-only hash-chained atomic audit trail design.

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

## Open Decisions index (consolidated across all documents, through round 5 — final)

This is the master list. No decision here is invented by this documentation pack — each is a specific question only the organization can answer. `OD-05` (originally in D1) is **reconciled, not dropped**: round 1 of this audit set it aside as "superseded" without saying by what; round 2 corrects that by naming exactly which later decisions subsume it.

| ID | Decision | Raised in | Status |
|---|---|---|---|
| OD-01 | Approval tier structure (single/risk-tiered/fixed multi-stage) | D1, D5 | Open |
| OD-02 | Long-term environment-readiness integration scope | D1, D4 | Open |
| OD-03 | Single-enterprise vs. multi-tenant | D1 | Open |
| OD-04 | No triage-time baseline exists | D1 | Open |
| OD-05 | Detailed evidence/blocker rule sets | D1 | **Reconciled** — addressed by OD-10 (completeness threshold), OD-11 (policy hooks), and OD-17 (evidence sufficiency criteria) below, not resolved on its own |
| OD-06 | Who holds "Environment Owner" | D1, D4 | Open |
| OD-07 | Who may validate evidence (and, per D3-Methodology §6a, who validates sufficiency) | D1, D3-Methodology, D5 | Open |
| OD-08 | Audit integrity-verification schedule/owner | D1, D5 | Open (default suggested: daily / Platform Owner) |
| OD-09 | External audit-chain anchoring required? | D1, D5 | Open |
| OD-10 | Layer 1 Completeness threshold | D2 | Open |
| OD-11 | Policy-hook content (PH-01/02/03) | D2, D3-Methodology | Open |
| OD-12 | AI-recommendation-match monitoring cadence/escalation | D2, D5 | Open |
| OD-14 | Whether a formal emergency-override mechanism for approval preconditions should exist at all | D5 | Open — default is **no** such mechanism |
| OD-15 | Layer 3 risk-factor weights (F1–F5) | D2 | Open — **blocks Layer 3 implementation** |
| OD-16 | Layer 3 risk-score thresholds/tiers | D2 | Open — **blocks Layer 3 implementation** |
| OD-17 | Per-control-family evidence sufficiency criteria | D3-Methodology | Open |
| OD-18 | Extend the non-waivable exception dimension list beyond Isolation/Access Control? | D4 | Open |
| OD-19 | Escalation behavior when a remediation deadline passes unresolved | D4 | Open |
| OD-20 | Post-approval revocation handling (testing already underway) | D4 | Open |
| OD-21 | Does a detected audit-integrity break halt new transitions or only alert? | D5 | Open |

See `AUDIT-REPORT.md` for the full round-5 (final) findings, what was fixed vs. left open, and the final readiness verdict.

## What this pack does not contain

Code, architecture implementation, or a build of any kind — this remains a documentation-only deliverable, consistent with the project's documentation-first approach.
