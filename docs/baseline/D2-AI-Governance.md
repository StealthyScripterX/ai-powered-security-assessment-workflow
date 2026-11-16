# D2 — AI Governance & Decision Boundary Specification

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | D2 |
| Title | AI Governance & Decision Boundary Specification |
| Project | AI-Powered Security Assessment & POC Approval Workflow |
| Status | Draft — incorporated into documentation baseline |
| Depends on | D1, D3-Catalog |
| Feeds | D3-Methodology, D4, D5 |

## 2. Purpose

Defines the structural boundary between what the AI agent may do (analyze, question, map, score, recommend) and what only a human may do (validate evidence, authorize testing) — and the deterministic logic the AI's recommendation runs on — so that boundary is enforced by data-model and process design, not by convention.

## 3. Scope

Covers the content-provenance model, questionnaire generation logic, the three-layer deterministic decision engine, assessment versioning and recommendation staleness, prompt-injection resistance, and authorization-boundary enforcement. Organizational policy content (blocker rule sets, risk weights/thresholds, policy hooks) is explicitly out of scope and tracked as Open Decisions rather than invented here.

## 4. Definitions and Terminology

See the consolidated Glossary in `README.md`. Terms defined specifically by this document: `provenance_tag`, `AssessmentInputVersion`, `Recommendation`, Layer 1/2/3, Mandatory Security Blocker, risk tier.

## 5. Roles and Responsibilities

| Role | Responsibility under this document |
|---|---|
| AI Agent (system actor) | Generates provenance-tagged content, mapping drafts, and the immutable `Recommendation` object. Holds no authorization authority. |
| Security Reviewer / GRC Analyst | Confirms, adjusts, or rejects AI-proposed mappings (D3-Methodology §4). |
| Final Approver | Acts on a `Recommendation`; never produces one. |
| GRC/Product/Risk owners | Own the Open Decisions this document raises (§10). |

## 6. Content Provenance Model

Every piece of information in the system is tagged with exactly one of four provenance types. This is the mechanism behind BR-008/BR-015 and the requirement to distinguish facts, assertions, assumptions, and missing evidence.

| Tag | Meaning | Who can set it |
|---|---|---|
| `REQUESTER_FACT` | Literal content the requester submitted (scope text, questionnaire answers, uploaded files) | Requester, verbatim |
| `AI_ASSERTION` | A conclusion the AI drew from requester facts (e.g., a control mapping) | AI agent |
| `AI_ASSUMPTION` | A gap the AI filled with a stated assumption because the requester didn't address it | AI agent, must carry a human-readable rationale string |
| `MISSING_EVIDENCE` | A data point the AI determined is required but absent — not filled, flagged | AI agent |

**Rule:** No artifact (gap analysis, mapping, readiness summary) may render without each constituent statement tagged. A rendering with an untagged statement is a defect, not a stylistic choice.

**Three independent axes.** Provenance (this section), mapping review status (D3-Methodology §4), and evidence state (D1 BR-005) are three separate, independent fields and must never be collapsed into one enum. Provenance describes *where content originated*; whether a human has since reviewed an AI-origin mapping is tracked separately by that mapping's own `review_status` field; evidence state is a third, independent axis again.

## 7. Questionnaire Generation Logic

- Question count: fixed at 11–15 (BR-002).
- Domain coverage: every **Mandatory** domain from D3-Catalog (1, 2, 3, 4, 5, 6, 7a, 8, 11) gets at least one question; **Conditional** domains (9, 10) are included only if a prior answer or scope-text signal triggers them (e.g., scope text names a vendor → Domain 9 question is added; scope text references personal data → Domain 10 question is added).
- Trigger detection for Conditional domains is itself an `AI_ASSERTION` and must be logged with the triggering text/answer it relied on.
- If Mandatory domain coverage plus triggered Conditional domains would require more than 15 questions, the engine prioritizes Mandatory domains first, drops lowest-priority Conditional questions, and records which were dropped as `MISSING_EVIDENCE` candidates for completeness-check purposes (§8.1) — it never silently expands past 15.
- If fewer than 11 meaningful questions can be generated (e.g., trivial scope), the shortfall itself is logged; the Completeness Check (§8.1) is what determines whether this forces Insufficient Information — the questionnaire generator does not make that call itself.

## 8. Deterministic Decision Engine — Fixed Three-Layer Order (BR-016)

The engine runs these layers **in order**; a layer that produces a terminal outcome stops execution — later layers do not run.

### 8.1 Layer 1 — Completeness Check

**Purpose:** determine whether enough information exists to evaluate Layers 2–3 at all.

**Rule (deterministic):** `Insufficient Information` is returned if any of the following hold:
- Any Mandatory domain has zero answered questions with provenance `REQUESTER_FACT` (i.e., the requester left a mandatory domain entirely unaddressed), **or**
- The Environment Readiness module (D4) has not been submitted at all (not merely incomplete — "not started" is a completeness failure, not a blocker), **or**
- More than a defined threshold (Open Decision **OD-10**) of questions were answered with content too vague for the AI to generate even an `AI_ASSUMPTION` (i.e., answers that are blank, non-responsive, or contradictory to the point of being unusable).

**Output if triggered:** `Insufficient Information / Incomplete Assessment`, with an enumerated list of exactly which domains/questions are missing — not a generic message.

### 8.2 Layer 2 — Mandatory Security Blockers

**Purpose:** enumerable, deterministic conditions that force NO-GO regardless of score. Reached only if Layer 1 passed.

**Fixed structural blockers (apply to every POC, per D1 BR-018):**
- **B-01:** `EnvironmentReadinessSignOff.final_signoff_boolean` (D4) is `false` — which, per D4's model, is true whenever any dimension is `Not Started`/`In Progress`, **or** is `Attested-with-Exception` with a disposition other than `Accepted`, **or** is `Attested-with-Exception` on a non-waivable dimension (Isolation, Access Control — D4 §6) regardless of disposition. B-01 is re-evaluated at Approval-decision commit time, not only at recommendation-generation time (see D5 §Precondition Enforcement) — if sign-off is revoked after the recommendation was produced, B-01 fires at commit time even though the stale recommendation object said otherwise.
- **B-02:** A `MISSING_EVIDENCE` flag exists on a control the organization's documented policy (D3-Methodology, Policy Hooks §6) designates as always-required regardless of scope. The *policy* decides this, not this document.

**Scope-conditional blockers (apply only when triggered, per documented policy — never invented here):** any blocker beyond B-01/B-02 must be defined in D3-Methodology's policy hook table, driven by organizational policy. This document does not enumerate PII-presence, encryption-absence, or scan-absence as blockers; these are conditional on scope/sensitivity/policy and are evaluated at Layer 3 as risk inputs unless a specific documented policy elevates one to a Layer-2 blocker.

**Output if triggered:** `NO-GO`, with the specific blocker ID(s) that fired.

### 8.3 Layer 3 — Risk Scoring

**Status: scoring framework, not yet implementation-ready.** This section fixes the required inputs, the shape of the calculation, and the qualitative rules that must hold, without inventing the specific weights or thresholds that turn it into an executable model. Those are organizational policy choices, tracked as Open Decisions **OD-15** and **OD-16** (§10). **Layer 3 cannot be built until OD-15 and OD-16 are resolved.**

**Required risk factors (the complete input set — no other inputs are in scope for v1):**

| Factor | Source | Nature |
|---|---|---|
| F1 — Control-mapping confidence **and** review-status distribution | D3-Methodology mapping records: `confidence` (High/Medium/Low) **and** `review_status` (Pending Review/Confirmed/Adjusted/Rejected), kept as two independent fields | Categorical, per control, two sub-dimensions |
| F2 — Evidence-state distribution | D1 BR-005 four-state model, per control | Categorical, per control |
| F3 — Conditional-domain findings not elevated to a Layer-2 blocker | D3-Methodology §5/§6 | Count + severity tag |
| F4 — Accepted-disposition exceptions on waivable dimensions | D4 | Count, with the dimension and compensating controls attached |
| F5 — Data sensitivity tier | D1 §9 (Data Sensitivity Summary), as instantiated per-POC | Categorical |

**F1 — confidence and review-status reconciliation.** Confidence and `review_status` are separate fields and must be scored as two distinct sub-factors of F1, never collapsed into one:
- A mapping with `review_status = Rejected` is **excluded from F1 entirely** — it contributes to the control's gap picture the same as if no mapping existed at all (consistent with D3-Methodology §4: "the mapping is excluded from scoring").
- A mapping with `review_status = Confirmed` or `Adjusted` contributes at full weight for its confidence level.
- A mapping with `review_status = Pending Review` contributes at a **discounted** weight relative to a `Confirmed`/`Adjusted` mapping of the same confidence — reflecting that no human has validated the AI's conclusion yet. The specific discount factor is part of the same weight-setting exercise as every other Layer-3 weight (**OD-15**).
- This sub-ordering (`Rejected` excluded < `Pending Review` discounted < `Confirmed`/`Adjusted` full weight) is a structural correctness rule that must hold under whatever numeric weights OD-15 eventually sets.

**Weighting methodology:** each factor above must have an assigned weight before a numeric score can be computed. No weight is specified in this document (**OD-15**). Weights must be externalized (configuration, not hardcoded in a model prompt or in application code), versioned, and auditable — i.e., whichever weights the organization sets, the engine must be able to show which weight version produced a given historical recommendation.

**Score calculation (shape, not parameters):** `risk_score = normalize(Σ weight(Fi) × severity(Fi))` over the factors present for a given POC, producing a value on a fixed scale (e.g., 0–100). The specific normalization function and scale are themselves part of **OD-15**.

**Risk thresholds:** the score must map to a small number of tiers (e.g., Low/Medium/High) that determine what the Approver sees and, per **OD-01**, potentially which approval tier applies. No threshold values are specified (**OD-16**).

**Evidence-state treatment (qualitative rule, not a number):** for a given control, `Verified – Human Validated` evidence must reduce computed risk more than `Submitted – Pending Review` evidence of the same mapping confidence, which in turn must reduce risk more than `Not Provided`; `Rejected / Insufficient Evidence` must never reduce risk and must be treated at least as severely as `Not Provided` for that control. This ordering is a structural correctness rule the implementation must satisfy regardless of the exact weight values chosen under OD-15.

**Handling conflicting factors (qualitative rule):** when mapping confidence is High but the supporting evidence state is `Rejected` or `Not Provided`, evidence state dominates — the control is treated as a gap, not as "probably fine because the AI was confident." Confidence describes how well an answer maps to a control's *topic*; it says nothing about whether the control is actually *satisfied*, which is an evidence-state question. This ordering rule must hold under any weighting scheme chosen in OD-15; it is a logical-consistency requirement, not itself a policy choice.

**Output:** `GO`, with an attached `risk_tier` (e.g., Low/Medium/High per OD-16's thresholds) and flagged residual risk items for the Approver's attention. Risk Scoring never itself produces NO-GO — a scope that is merely "risky but not blocked" is a GO with flags, consistent with keeping GO/NO-GO decisions traceable to specific, named reasons rather than an opaque score.

**Risk tiers are metadata, not a fourth outcome.** D1 BR-009 fixes the recommendation at exactly three outcomes — GO, NO-GO, Insufficient Information — and that remains exhaustive. `risk_tier` is a field attached *only* to a `GO` outcome, describing how much residual risk accompanies that GO; it is never itself returned as if it were a separate outcome, and it never appears on a `NO-GO` or `Insufficient Information` result, since those are determined entirely by Layers 1–2 and never reach Layer 3's scoring at all. A "High risk-tier GO" is still, structurally and for every downstream purpose (RACI, audit, approval gating), a `GO`.

### 8.4 Hard Gate (BR-018)

Independent of Layer 3's numeric output: **GO is structurally unreachable while B-01 (sign-off incomplete) is true.** This is enforced as a precondition check wrapping the engine's output, not merely a high-weight scoring input — i.e., even a hypothetical zero-risk score cannot produce GO if sign-off is incomplete.

### 8.5 Assessment Versioning & Recommendation Staleness

**Problem addressed:** without an explicit staleness rule, a recommendation issued against one state of the inputs could be approved later against a different, unreviewed state — reintroducing a bypass at the approval layer.

**Versioning model:**

```
AssessmentInputVersion {
  poc_request_id
  version: integer                 // monotonically increasing per POC request

  scope_hash                       // hash over the complete current content of the
                                    //   scope submission (`scope_submission_ref`,
                                    //   D5 §3) that initiated this POC request:
                                    //   every field the requester supplied (project
                                    //   description, systems/assets in scope,
                                    //   business justification, and any other
                                    //   intake-form field), as it currently stands.
                                    //   Changes on creation (the submission that
                                    //   starts the POC request establishes the
                                    //   first `version` and its initial
                                    //   `scope_hash`), on any later modification or
                                    //   replacement of the submitted content, and
                                    //   on deletion (a deleted scope leaves no valid
                                    //   basis for any existing `Recommendation` —
                                    //   see invalidating-change item 8 below).

  evidence_state_hash              // hash over, for every control: its current
                                    //   evidence state enum value AND the identity/
                                    //   content-digest of every evidence artifact
                                    //   currently attached to it (file reference,
                                    //   content hash, uploaded_at, uploaded_by).
                                    //   Covers upload, replacement, and deletion of
                                    //   an artifact even when the state enum itself
                                    //   does not change (e.g., replacing a Verified
                                    //   control's supporting file with a different
                                    //   file, while the state stays Verified) — the
                                    //   artifact-identity component changes and
                                    //   therefore so does this hash.

  mapping_hash                     // hash over all mapping records' assessment-
                                    //   relevant fields: control_id, confidence,
                                    //   review_status, and rationale (rationale is
                                    //   included because D3-Methodology §4 allows a
                                    //   Reviewer's `Adjust` action to change it, and
                                    //   an adjustment that changes only the stated
                                    //   reasoning for a mapping, without also
                                    //   changing control_id or confidence, is still
                                    //   a reviewer judgment the engine has not yet
                                    //   seen). Also covers every evidence-control
                                    //   link (which evidence artifact is linked to
                                    //   which control_id), so relinking evidence to
                                    //   a different control, or unlinking it,
                                    //   changes this hash even if the mapping's own
                                    //   fields are untouched. Explicitly EXCLUDED:
                                    //   `framework` (fixed by which D3-Catalog entry
                                    //   the mapping targets — identifies the
                                    //   control, doesn't describe its assessment
                                    //   state) and `provenance_tag` (always
                                    //   `AI_ASSERTION` — constant for every mapping
                                    //   record, so including it could never change
                                    //   the hash and would only add noise).
                                    //   `answer_excerpt` is also excluded: it is a
                                    //   fixed snapshot of the questionnaire answer
                                    //   that produced the mapping, so if the
                                    //   underlying answer itself changes, that is
                                    //   invalidating change #6 (questionnaire
                                    //   changes, covered by `questionnaire_hash`)
                                    //   producing a new mapping record — not a
                                    //   mutation of this one's `answer_excerpt` in
                                    //   place.

  questionnaire_hash                // hash over questionnaire responses

  environment_readiness_hash        // hash over the complete current state of
                                     //   every D4 `EnvironmentReadinessAttestation`
                                     //   and its `ExceptionRecord` (where present)
                                     //   for this POC request: `status`,
                                     //   `attestation_text`, and, for every
                                     //   exception, `issue_description`,
                                     //   `risk_assessment`,
                                     //   `compensating_controls`, `disposition`,
                                     //   `disposition_rationale`,
                                     //   `remediation_owner`,
                                     //   `remediation_deadline`, `expiry_date`, and
                                     //   the `revoked`/`revoked_by`/`revoked_at`
                                     //   revocation fields (D4 §6) — plus any
                                     //   supporting evidence references attached to
                                     //   an attestation or exception (D4 §6,
                                     //   `supporting_evidence`), and the resulting
                                     //   `final_signoff_boolean` (D4 §6). Any change
                                     //   to any of these — a status change, an
                                     //   edited attestation or exception field, a
                                     //   supporting-evidence addition/removal, a
                                     //   disposition change, or a revocation —
                                     //   changes this hash, consistent with
                                     //   invalidating-change item 5.

  policy_config_version             // version identifier of the active policy
                                     //   hooks (D3-Methodology §9) and Layer-3
                                     //   weights/thresholds (OD-15/OD-16) at the
                                     //   time this version was computed
  computed_at
}

Recommendation {
  id
  poc_request_id
  input_version: ref(AssessmentInputVersion)   // immutable pointer — fixed at
                                                //   creation, never repointed
  outcome: enum[GO, NO-GO, INSUFFICIENT_INFORMATION]
  risk_tier: enum[Low, Medium, High] | null    // GO-only metadata, §8.3
  rationale
  decision_layer_attribution       // which layer (1/2/3) produced this outcome
  created_at
  immutable: true                  // never updated or deleted — see "history
                                    //   preservation" below
}
```

**Invalidating changes (exhaustive list — any one of these creates a new `AssessmentInputVersion` with an incremented `version`, which by definition makes every existing `Recommendation` for that POC request stale):**

1. Evidence-state changes (any control's state moves between Not Provided / Submitted–Pending Review / Verified / Rejected).
2. Evidence-artifact changes (an evidence artifact is uploaded, replaced, or deleted for any control, *even when the state enum value in #1 does not itself change* — e.g., swapping one Verified control's supporting file for another file while it remains Verified. Covered by `evidence_state_hash`, per its definition above).
3. Mapping changes (a `control_id`, `confidence`, or `rationale` value on a mapping record changes, or an evidence artifact is linked to or unlinked from a control — per `mapping_hash`'s definition above).
4. Mapping-review changes (`review_status` moves between Pending Review / Confirmed / Adjusted / Rejected).
5. Environment attestation or revocation (any D4 `EnvironmentReadinessAttestation` field changes — `status`, `attestation_text`, or `supporting_evidence` — any `ExceptionRecord` field changes, or any revocation per D4 §6).
6. Questionnaire changes (a new or amended answer is recorded — e.g., following a "Request More Information" cycle; this is the mechanism by which a `MoreInfoRequested` decision starts a new assessment cycle — see D5 §4).
7. Policy/configuration changes (the active policy hooks, Layer-3 weights, or thresholds are updated — i.e., `policy_config_version` itself changes, even if nothing about this specific POC request changed).
8. Scope submission changes (the scope submission referenced by `scope_submission_ref` is created, modified, replaced, or deleted. Creation establishes the POC request's first `AssessmentInputVersion`; any later modification or replacement of the submitted scope content, or deletion of the submission itself, is assessment-relevant by definition — the scope is what every subsequent question, mapping, and control applicability determination was generated against. Covered by `scope_hash`, per its definition above. A deleted scope submission leaves no valid basis for any existing `Recommendation` for that POC request; this is treated the same as any other invalidating change — it stales existing recommendations rather than requiring separate handling — but whether a POC request may *proceed* at all with no scope submission is a workflow-availability question for D1/D5, not resolved by this versioning rule itself).

**Staleness test (consumed by D5 §4 as precondition P4):** a `Recommendation` is stale if `Recommendation.input_version.version` is not equal to the current (latest) `AssessmentInputVersion.version` for that `poc_request_id`. This is a simple integer comparison, not a re-derivation of the hashes — the hashes exist for audit/forensic verification (confirming *what* changed), not for the staleness check itself, which only needs to know *that* something changed.

**Decision-engine re-run trigger rule:** the engine does not eagerly re-run in the background on every invalidating change. Re-running is triggered by exactly two events: (a) an explicit user-initiated re-submission (e.g., following a new `AssessmentInputVersion` created by invalidating change #6 after a `MoreInfoRequested` decision), or (b) automatically and synchronously whenever an `Approved` approval attempt's P4 check (D5 §4) detects staleness. Because D5 §4's P4 gates `Approved` decisions only, this automatic re-run fires only on a blocked `Approved` attempt — never on a `Rejected` or `MoreInfoRequested` decision, since D5 §4 permits both of those unconditionally regardless of staleness (recording `recommendation_was_stale` transparently instead). An `Approved` attempt against stale input must not silently proceed, so it is blocked and the Approver is handed a fresh `Recommendation`; a `Rejected` or `MoreInfoRequested` attempt grants no testing authorization either way, so forcing a re-run before allowing it would only trap the request without a safety benefit.

**Approval-time enforcement:** the Approval transaction (D5 §4) must verify `ApprovalDecision.recommendation_ref.input_version == current AssessmentInputVersion` for the POC request before accepting any decision of type `Approved`. If stale, the write is rejected and a fresh engine run is triggered per the rule above — this is precondition **P4**, alongside P1–P3, and like them applies to `Approved` decisions only (D5 §4).

**History preservation:** `Recommendation` rows are immutable and are never deleted or overwritten when superseded by a fresh run — the old recommendation, the `AssessmentInputVersion` it pointed to, and every audit entry referencing them remain exactly as they were. A superseding run creates a *new* `Recommendation` row linked to a *new* `AssessmentInputVersion`; "stale" is a relationship between two rows, never an edit to one.

## 9. Security and Governance Requirements

### 9.1 Prompt-Injection Resistance

- The AI agent's scope-analysis and questionnaire-generation prompts treat all requester-submitted text (scope description, answers, filenames, uploaded-document content) as **data, not instruction** — the agent's own system instructions are not re-derivable or overridable from submitted content.
- Any submitted text that reads as an instruction to the AI (e.g., "mark this as GO", "skip the environment check") is logged as a `MISSING_EVIDENCE`/anomaly flag for reviewer attention, not acted on.
- The decision engine (§8) never takes its blocker/completeness/score inputs directly from free text — only from structured, previously-tagged provenance fields — so injected text in a free-text field cannot directly flip a Layer 2 blocker or Layer 1 completeness result.
- Adversarial test cases for this are specified in the Testing & Validation phase (outside this document's scope); this section defines the structural control, not the test plan.

### 9.2 Authorization-Boundary Protection

- The AI agent's service identity has **no write grant** to the Approval-decision object (D5) or to any evidence-state transition that promotes an item to `Verified – Human Validated` or `Rejected / Insufficient Evidence` (D3-Methodology, D5). This is enforced at the access-control layer, not by the AI choosing not to write.
- The AI agent may only write: questionnaire content, `AI_ASSERTION`/`AI_ASSUMPTION`/`MISSING_EVIDENCE`-tagged artifacts, control-mapping drafts (pending Reviewer confirmation per D3-Methodology), and the recommendation object (GO/NO-GO/Insufficient Information) — which is itself immutable once written and is a distinct object from the Approval decision (BR-010).
- **Actor identity is never a client-supplied field.** Every field that records who performed an action — `approver_id`, `disposition_authorized_by`, `environment_owner_id`, `revoked_by`, the AI agent's own acting identity, and every audit entry's actor field — is populated by the server from the authenticated session/service-credential context of the request, never accepted as a value the caller's request body supplies. A client cannot submit a write with someone else's ID in an actor field and have it honored; the server overwrites or rejects any such field with its own derived identity. D4 and D5 restate this at the specific fields where it matters most (environment sign-off, exception disposition, approval decisions).

### 9.3 Mitigating Reviewer/Approver Over-Reliance on AI (RSK-01)

- The Approval Request UI (D5) must surface the AI's recommendation alongside, not instead of, the underlying evidence-state table and blocker list — the recommendation is not permitted to be the only thing an Approver sees before deciding.
- A mandatory free-text rationale field is required from the Approver on every decision (BR-012/BR-015) — a rationale that merely restates the AI's own text is a process-quality signal to surface in periodic reporting, not something this document can technically prevent.
- The system logs, per Approver, the rate at which their decision matches the AI recommendation exactly; this is a monitoring signal for the organization (**OD-12**), not an automated control (over-reliance is a human/process risk, not one this spec can fully engineer away).

## 10. Dependencies and Related Documents

Depends on D1 (requirements baseline) and D3-Catalog (control identifiers). Feeds D3-Methodology (mapping methodology and policy hooks), D4 (environment readiness, consumes B-01), and D5 (approval preconditions, consumes P4 staleness and actor-identity rules).

## 11. Assumptions and Constraints

No organizational policy, approval tier, or blocker list beyond the structural B-01/B-02 is invented in this document — all scope-conditional blocker content is deferred to D3-Methodology's policy hooks, to be populated by the organization. Risk-scoring weights and thresholds (OD-15, OD-16) are deliberately left unparameterized. Versioning/staleness (§8.5) and actor-identity enforcement (§9.2) are specified as structural/technical rules, not treated as open organizational decisions — they required no policy input to resolve.

## 12. Open Decisions Arising From This Document

| ID | Decision | Impact | Recommended owner |
|---|---|---|---|
| OD-10 | Exact threshold (count/%) of unusable answers that trips Layer 1 Completeness failure | Blocks finalizing the Completeness Check's deterministic rule | GRC/Product owner |
| OD-11 | Which (if any) scope-conditional findings the organization wants pre-elevated to Layer-2 blockers, beyond B-01/B-02 | Blocks finalizing D3-Methodology's policy hook table | GRC/Compliance owner |
| OD-12 | Whether "answer matches AI recommendation 1:1" monitoring (§9.3) feeds any formal review trigger, or is informational only | Affects D5's RACI and reporting requirements | Approval process owner |
| OD-15 | Layer 3 risk-factor weights (F1–F5), including the Pending-Review discount factor within F1, and their versioning/governance | **Blocks Layer 3 implementation entirely** | GRC/Risk owner |
| OD-16 | Layer 3 risk-score tiers and threshold values, and whether tier maps to approval tier (ties to OD-01) | **Blocks Layer 3 implementation entirely** | GRC/Risk owner, Approval process owner |

## 13. Acceptance Criteria

- [ ] Every rendered artifact tags each constituent statement with exactly one provenance type.
- [ ] Questionnaire generation never exceeds 15 or silently expands past it; Mandatory-domain coverage is always complete or explicitly logged as a gap.
- [ ] Decision engine layers execute in fixed order with short-circuit on terminal outcome.
- [ ] `risk_tier` never appears on a `NO-GO` or `Insufficient Information` outcome.
- [ ] A stale `Recommendation` cannot be the basis of an `Approved` decision (see D5 §4, P4).
- [ ] No actor-identity field is ever accepted from client input.

## 14. References

- D1 — Project Requirements Document
- D3-Control-Catalog — Security Control Catalog
- D3-Methodology — Answer-to-Control Mapping Methodology
- D4 — Security Test Environment Readiness SOP
- D5 — Approval, RACI & Audit Trail Specification
- `README.md` — consolidated Open Decisions index and glossary
- `AUDIT-REPORT.md` — internal historical audit record (not a specification source)

## 15. Revision History

| Version | Status | Notes |
|---|---|---|
| v1.0 | Draft, incorporated | Substantive content consolidated from the audited baseline; every structural fix previously described as a round-by-round correction (provenance-axis separation, the full `ExceptionRecord`-equivalent precondition closure now specified in D5, the Layer-3 risk-scoring framework, assessment versioning and staleness, scope/mapping/environment hash-coverage enumeration, and actor-identity server-derivation) is now stated directly in its final specification section (§6, §8, §9) rather than narrated as a correction history. A full account of what changed between review rounds and why is preserved in `AUDIT-REPORT.md`. |
