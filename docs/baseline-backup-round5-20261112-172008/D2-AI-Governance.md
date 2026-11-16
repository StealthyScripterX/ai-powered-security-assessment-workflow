# D2 — AI Governance & Decision Boundary Specification

**Status:** Draft, incorporated into one-go pack.
**Depends on:** D1, D3-Catalog. **Feeds:** D3-Methodology, D4, D5.

## 1. Purpose

Defines the structural boundary between what the AI agent may do (analyze, question, map, score, recommend) and what only a human may do (validate evidence, authorize testing) — and the deterministic logic the AI's recommendation runs on, so that boundary is enforced by data-model and process design, not by convention.

## 2. Content Provenance Model (non-negotiable requirement)

Every piece of information in the system must be tagged with exactly one of four provenance types. This is the mechanism behind BR-008/BR-015 and the "distinguish facts, assertions, assumptions, missing evidence" requirement.

| Tag | Meaning | Who can set it |
|---|---|---|
| `REQUESTER_FACT` | Literal content the requester submitted (scope text, questionnaire answers, uploaded files) | Requester, verbatim |
| `AI_ASSERTION` | A conclusion the AI drew from requester facts (e.g., a control mapping) | AI agent |
| `AI_ASSUMPTION` | A gap the AI filled with a stated assumption because the requester didn't address it | AI agent, must carry a human-readable rationale string |
| `MISSING_EVIDENCE` | A data point the AI determined is required but absent — not filled, flagged | AI agent |

**Rule:** No artifact (gap analysis, mapping, readiness summary) may render without each constituent statement tagged. A rendering with an untagged statement is a defect, not a stylistic choice.

**Correction (consolidated audit, round 2):** this remains exactly four provenance types — a prior draft of D3-Methodology introduced a fifth (`HUMAN_VALIDATED_MAPPING`), which has been removed from that document. Provenance (this section) describes *where content originated*; whether a human has since reviewed an AI-origin mapping is tracked by a separate `review_status` field on the mapping record itself (D3-Methodology §4), and evidence state (D1 BR-005) is a third, independent axis again. These three axes — provenance, mapping review status, evidence state — must never be collapsed into one enum.

## 3. Questionnaire Generation Logic

- Question count: fixed at 11–15 (BR-002).
- Domain coverage: every **Mandatory** domain from D3-Catalog (1,2,3,4,5,6,7a,8,11) gets at least one question; **Conditional** domains (9,10) are included only if a prior answer or scope-text signal triggers them (e.g., scope text names a vendor → Domain 9 question is added; scope text references personal data → Domain 10 question is added).
- Trigger detection for Conditional domains is itself an `AI_ASSERTION` and must be logged with the triggering text/answer it relied on.
- If Mandatory domain coverage plus triggered Conditional domains would require more than 15 questions, the engine prioritizes Mandatory domains first, drops lowest-priority Conditional questions, and records which were dropped as `MISSING_EVIDENCE` candidates for completeness-check purposes (§4a) — it never silently expands past 15.
- If fewer than 11 meaningful questions can be generated (e.g., trivial scope), the shortfall itself is logged; the Completeness Check (§4a) is what determines whether this forces Insufficient Information — the questionnaire generator does not make that call itself.

## 4. Decision Engine — Fixed Three-Layer Order (BR-016)

The engine runs these layers **in order**; a layer that produces a terminal outcome stops execution — later layers do not run.

### 4a. Layer 1 — Completeness Check

**Purpose:** determine whether enough information exists to evaluate Layers 2–3 at all.

**Rule (deterministic):** Insufficient Information is returned if any of the following hold:
- Any Mandatory domain has zero answered questions with provenance `REQUESTER_FACT` (i.e., the requester left a mandatory domain entirely unaddressed), **or**
- The Environment Readiness module (D4) has not been submitted at all (not merely incomplete — "not started" is a completeness failure, not a blocker), **or**
- More than a defined threshold (TBD — Open Decision, see §7) of questions were answered with content too vague for the AI to generate even an `AI_ASSUMPTION` (i.e., answers that are blank, non-responsive, or contradictory to the point of being unusable).

**Output if triggered:** `Insufficient Information / Incomplete Assessment`, with an enumerated list of exactly which domains/questions are missing — not a generic message.

### 4b. Layer 2 — Mandatory Security Blockers

**Purpose:** enumerable, deterministic conditions that force NO-GO regardless of score. Reached only if Layer 1 passed.

**Fixed structural blockers (apply to every POC, per D1 BR-018):**
- B-01: `EnvironmentReadinessSignOff.final_signoff_boolean` (D4) is `false` — which, per D4's corrected model, is true whenever any dimension is `Not Started`/`In Progress`, **or** is `Attested-with-Exception` with a disposition other than `Accepted`, **or** is `Attested-with-Exception` on a non-waivable dimension (Isolation, Access Control — D4 §3) regardless of disposition. B-01 is re-evaluated at Approval-decision commit time, not only at recommendation-generation time (see D5 §Precondition Enforcement) — if sign-off is revoked after the recommendation was produced, B-01 fires at commit time even though the stale recommendation object said otherwise.
- B-02: A `MISSING_EVIDENCE` flag exists on a control the organization's documented policy (D3-Methodology, §policy hooks) designates as always-required regardless of scope (e.g., if policy says "isolation evidence is always required" — the *policy* decides this, not this document).

**Scope-conditional blockers (apply only when triggered, per documented policy — never invented here):**
- Any blocker beyond B-01/B-02 must be defined in D3-Methodology's policy hook table, driven by organizational policy, not asserted in this spec. This document does not enumerate PII-presence, encryption-absence, or scan-absence as blockers — per the correction that these are conditional on scope/sensitivity/policy, evaluated at Layer 3 as risk inputs unless a specific documented policy elevates one to a Layer-2 blocker.

**Output if triggered:** `NO-GO`, with the specific blocker ID(s) that fired.

### 4c. Layer 3 — Risk Scoring

**Status: scoring FRAMEWORK only — not implementation-ready.** This section fixes the required inputs, the shape of the calculation, and the qualitative rules that must hold, without inventing the specific weights or thresholds that turn it into an executable model. Per your instruction, those are organizational policy choices and are listed as Open Decisions (§8) rather than invented here. **The decision engine's Layer 3 cannot be built until OD-15 and OD-16 are resolved** — this is stated plainly rather than papered over with a plausible-looking default.

**Required risk factors (the complete input set — no other inputs are in scope for v1):**

| Factor | Source | Nature |
|---|---|---|
| F1 — Control-mapping confidence **AND review-status** distribution | D3-Methodology mapping records: `confidence` (High/Medium/Low) **and** `review_status` (Pending Review/Confirmed/Adjusted/Rejected), kept as the two independent fields D3-Methodology §4 defines | Categorical, per control, two sub-dimensions |
| F2 — Evidence-state distribution | D1 BR-005 four-state model, per control | Categorical, per control |
| F3 — Conditional-domain findings not elevated to a Layer-2 blocker | D3-Methodology §5/§6 | Count + severity tag |
| F4 — Accepted-disposition exceptions on waivable dimensions | D4 (corrected model) | Count, with the dimension and compensating controls attached |
| F5 — Data sensitivity tier | D1 §6 Data Sensitivity Summary, as instantiated per-POC | Categorical |

**F1 reconciliation (MAJOR-02 — D2 §4c ↔ D3-Methodology §4):** confidence and `review_status` are separate fields and must be scored as two distinct sub-factors of F1, never collapsed into one:
- A mapping with `review_status = Rejected` is **excluded from F1 entirely** — it contributes to the control's gap picture the same as if no mapping existed at all (consistent with D3-Methodology §4: "the mapping is excluded from scoring").
- A mapping with `review_status = Confirmed` or `Adjusted` contributes at full weight for its confidence level.
- A mapping with `review_status = Pending Review` contributes at a **discounted** weight relative to a `Confirmed`/`Adjusted` mapping of the same confidence — reflecting that no human has validated the AI's conclusion yet. The specific discount factor is not invented here; it is part of the same weight-setting exercise as every other Layer-3 weight, and is covered by **OD-15** rather than a new, separate decision.
- This sub-ordering (`Rejected` excluded < `Pending Review` discounted < `Confirmed`/`Adjusted` full weight) is a structural correctness rule, like the evidence-state ordering below — it must hold under whatever numeric weights OD-15 eventually sets.

**Weighting methodology:** each factor above must have an assigned weight before a numeric score can be computed. **No weight is specified in this document — OD-15.** The methodology requirement is that weights be externalized (configuration, not hardcoded in a model prompt or in application code), versioned, and auditable — i.e., whichever weights the organization sets, the engine must be able to show which weight version produced a given historical recommendation.

**Score calculation (shape, not parameters):** `risk_score = normalize(Σ weight(Fi) × severity(Fi))` over the factors present for a given POC, producing a value on a fixed scale (e.g., 0–100). The specific normalization function and scale are themselves part of OD-15.

**Risk thresholds:** the score must map to a small number of tiers (e.g., Low/Medium/High) that determine what the Approver sees and, per Open Decision OD-01, potentially which approval tier applies. **No threshold values are specified — OD-16.**

**Evidence-state treatment (qualitative rule, not a number):** for a given control, `Verified – Human Validated` evidence must reduce computed risk more than `Submitted – Pending Review` evidence of the same mapping confidence, which in turn must reduce risk more than `Not Provided`; `Rejected / Insufficient Evidence` must never reduce risk and must be treated at least as severely as `Not Provided` for that control. This ordering is a structural correctness rule the implementation must satisfy regardless of the exact weight values chosen under OD-15.

**Handling conflicting factors (qualitative rule):** when mapping confidence is High but the supporting evidence state is `Rejected` or `Not Provided`, evidence state dominates — the control is treated as a gap, not as "probably fine because the AI was confident." Confidence describes how well an answer maps to a control's *topic*; it says nothing about whether the control is actually *satisfied*, which is an evidence-state question. This ordering rule must hold under any weighting scheme chosen in OD-15; it is a logical-consistency requirement, not itself a policy choice.

**Output:** `GO`, with an attached `risk_tier` (e.g., Low/Medium/High per OD-16's thresholds) and flagged residual risk items for the Approver's attention. Risk Scoring never itself produces NO-GO — a scope that is merely "risky but not blocked" is a GO with flags, consistent with keeping GO/NO-GO decisions traceable to specific, named reasons rather than an opaque score.

**Risk tiers are metadata, not a fourth outcome (MINOR correction):** D1 BR-009 fixes the recommendation at exactly three outcomes — GO, NO-GO, Insufficient Information — and that remains exhaustive. `risk_tier` is a field attached *only* to a `GO` outcome, describing how much residual risk accompanies that GO; it is never itself returned as if it were a separate outcome, and it never appears on a `NO-GO` or `Insufficient Information` result, since those are determined entirely by Layers 1–2 and never reach Layer 3's scoring at all. A "High risk-tier GO" is still, structurally and for every downstream purpose (RACI, audit, approval gating), a `GO` — nothing in this pack treats it as a fourth state.

### 4d. Hard Gate Restated (BR-018)

Independent of Layer 3's numeric output: **GO is structurally unreachable while B-01 (sign-off incomplete) is true.** This is enforced as a precondition check wrapping the engine's output, not merely a high-weight scoring input — i.e., even a hypothetical zero-risk score cannot produce GO if sign-off is incomplete.

### 4e. Assessment Versioning & Recommendation Staleness (MAJOR-01)

**Problem this closes:** nothing before this round defined what happens when the inputs a recommendation was computed from change *after* the recommendation was produced but *before* an Approver acts on it. Without an explicit staleness rule, a GO issued against yesterday's evidence/sign-off state could be approved today against a different, unreviewed state — silently reintroducing the same class of bypass Finding 1 closed at the approval layer, just one step upstream of it.

**Versioning model:**

```
AssessmentInputVersion {
  poc_request_id
  version: integer                 // monotonically increasing per POC request
  scope_hash                       // round 5 — hash over the complete current
                                    //   content of the scope submission
                                    //   (`scope_submission_ref`, D5 §3) that
                                    //   initiated this POC request: every field
                                    //   the requester supplied (project
                                    //   description, systems/assets in scope,
                                    //   business justification, and any other
                                    //   intake-form field), as it currently
                                    //   stands. Changes on creation (the
                                    //   submission that starts the POC request
                                    //   establishes the first `version` and its
                                    //   initial `scope_hash`), on any later
                                    //   modification or replacement of the
                                    //   submitted content, and on deletion
                                    //   (a deleted scope leaves no valid basis
                                    //   for any existing `Recommendation`, so
                                    //   deletion invalidates exactly like any
                                    //   other change — see invalidating-change
                                    //   item 8 below).
  evidence_state_hash              // hash over, for every control: its current
                                    //   evidence state enum value AND the identity/
                                    //   content-digest of every evidence artifact
                                    //   currently attached to it (file reference,
                                    //   content hash, uploaded_at, uploaded_by).
                                    //   Covers upload, replacement, and deletion of
                                    //   an artifact even when the state enum itself
                                    //   does not change (e.g., replacing a Verified
                                    //   control's supporting file with a different
                                    //   file, while the state stays Verified) —
                                    //   the artifact-identity component changes and
                                    //   therefore so does this hash.
  mapping_hash                     // round 5 — hash over all mapping records'
                                    //   assessment-relevant fields: control_id,
                                    //   confidence, review_status, and rationale
                                    //   (rationale is included because D3-
                                    //   Methodology §4 allows a Reviewer's
                                    //   `Adjust` action to change it, and an
                                    //   adjustment that changes only the
                                    //   stated reasoning for a mapping, without
                                    //   also changing control_id or confidence,
                                    //   is still a reviewer judgment the engine
                                    //   has not yet seen). Also covers every
                                    //   evidence-control link (which evidence
                                    //   artifact is linked to which control_id),
                                    //   so relinking evidence to a different
                                    //   control, or unlinking it, changes this
                                    //   hash even if the mapping's own fields
                                    //   are untouched. Explicitly EXCLUDED:
                                    //   `framework` (fixed by which D3-Catalog
                                    //   entry the mapping targets — identifies
                                    //   the control, doesn't describe its
                                    //   assessment state) and `provenance_tag`
                                    //   (always `AI_ASSERTION`, per D2 §2 —
                                    //   constant for every mapping record, so
                                    //   including it could never change the
                                    //   hash and would only add noise).
                                    //   `answer_excerpt` is also excluded from
                                    //   this hash: it is a fixed snapshot of
                                    //   the questionnaire answer that produced
                                    //   the mapping, so if the underlying
                                    //   answer itself changes, that is
                                    //   invalidating change #6 (questionnaire
                                    //   changes, covered by
                                    //   `questionnaire_hash`) producing a new
                                    //   mapping record — not a mutation of
                                    //   this one's `answer_excerpt` in place.
  questionnaire_hash                // hash over questionnaire responses
  environment_readiness_hash        // round 5 — hash over the complete current
                                     //   state of every D4
                                     //   `EnvironmentReadinessAttestation` and
                                     //   its `ExceptionRecord` (where present)
                                     //   for this POC request: `status`,
                                     //   `attestation_text`, and, for every
                                     //   exception, `issue_description`,
                                     //   `risk_assessment`,
                                     //   `compensating_controls`,
                                     //   `disposition`,
                                     //   `disposition_rationale`,
                                     //   `remediation_owner`,
                                     //   `remediation_deadline`,
                                     //   `expiry_date`, and the
                                     //   `revoked`/`revoked_by`/`revoked_at`
                                     //   revocation fields (D4 §3) — plus any
                                     //   supporting evidence references
                                     //   attached to an attestation or
                                     //   exception (D4 §3, `supporting_
                                     //   evidence`), and the resulting
                                     //   `final_signoff_boolean` (D4 §3). Any
                                     //   change to any of these — a status
                                     //   change, an edited attestation or
                                     //   exception field, a supporting-
                                     //   evidence addition/removal, a
                                     //   disposition change, or a revocation —
                                     //   changes this hash, consistent with
                                     //   invalidating-change item 5.
  policy_config_version             // version identifier of the active policy
                                     //   hooks (D3-Methodology §6) and Layer-3
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
  risk_tier: enum[Low, Medium, High] | null    // GO-only metadata, §4c
  rationale
  decision_layer_attribution       // which layer (1/2/3) produced this outcome
  created_at
  immutable: true                  // never updated or deleted — see "history"
                                    //   rule below
}
```

**Invalidating changes (exhaustive list — any one of these creates a new `AssessmentInputVersion` with an incremented `version`, which by definition makes every existing `Recommendation` for that POC request stale):**

1. Evidence-state changes (any control's state moves between Not Provided / Submitted–Pending Review / Verified / Rejected).
2. Evidence-artifact changes (round 4 — made explicit: an evidence artifact is uploaded, replaced, or deleted for any control, *even when the state enum value in #1 does not itself change* — e.g., swapping one Verified control's supporting file for another file while it remains Verified. Covered by `evidence_state_hash`, per its definition above).
3. Mapping changes (a control_id, confidence, or rationale value on a mapping record changes — round 5: rationale added, per `mapping_hash`'s definition above — or an evidence artifact is linked to or unlinked from a control — round 4: made explicit in `mapping_hash`'s definition above).
4. Mapping-review changes (`review_status` moves between Pending Review / Confirmed / Adjusted / Rejected).
5. Environment attestation or revocation (any D4 `EnvironmentReadinessAttestation` field changes — `status`, `attestation_text`, or `supporting_evidence` — round 5: the latter two made explicit, per `environment_readiness_hash`'s definition above — any `ExceptionRecord` field changes, or any revocation per D4 §5.2).
6. Questionnaire changes (a new or amended answer is recorded — e.g., following a "Request More Information" cycle; this is the mechanism by which a `MoreInfoRequested` decision starts a new assessment cycle — see D5 §3a).
7. Policy/configuration changes (the active policy hooks, Layer-3 weights, or thresholds are updated — i.e., `policy_config_version` itself changes, even if nothing about this specific POC request changed).
8. Scope submission changes (round 5 — made explicit: the scope submission referenced by `scope_submission_ref` is created, modified, replaced, or deleted. Creation establishes the POC request's first `AssessmentInputVersion`; any later modification or replacement of the submitted scope content, or deletion of the submission itself, is assessment-relevant by definition — the scope is what every subsequent question, mapping, and control applicability determination was generated against, so a changed scope means the rest of the assessment may no longer describe what's actually being tested. Covered by `scope_hash`, per its definition above. A deleted scope submission leaves no valid basis for any existing `Recommendation` for that POC request; this is treated the same as any other invalidating change — i.e., it stales existing recommendations rather than requiring separate handling — but note that whether a POC request may *proceed* at all with no scope submission is a workflow-availability question for D1/D5, not something this versioning rule itself resolves.)

**Staleness test (consumed by D5 §3a as precondition P4):** a `Recommendation` is stale if `Recommendation.input_version.version` is not equal to the current (latest) `AssessmentInputVersion.version` for that `poc_request_id`. This is a simple integer comparison, not a re-derivation of the hashes — the hashes exist for audit/forensic verification (confirming *what* changed), not for the staleness check itself, which only needs to know *that* something changed.

**Decision-engine re-run trigger rule (round 4 — reconciled with D5 §3a's decision-type scoping):** the engine does not eagerly re-run in the background on every invalidating change — that would risk runaway re-computation. Re-running is triggered by exactly two events: (a) an explicit user-initiated re-submission (e.g., following a new `AssessmentInputVersion` created by invalidating change #6 after a `MoreInfoRequested` decision), or (b) automatically and synchronously whenever an `Approved` approval attempt's P4 check (D5 §3a) detects staleness. **Scoping note:** because D5 §3a's P4 gates `Approved` decisions only, this automatic re-run fires only on a blocked `Approved` attempt — never on a `Rejected` or `MoreInfoRequested` decision, since D5 §3a permits both of those unconditionally regardless of staleness (recording `recommendation_was_stale` transparently instead). This is a deliberate asymmetry, not an oversight: an `Approved` attempt against stale input must not silently proceed, so it is blocked and the Approver is handed a fresh `Recommendation`; a `Rejected` or `MoreInfoRequested` attempt grants no testing authorization either way, so forcing a re-run before allowing it would only trap the request without a safety benefit.

**Approval-time enforcement:** the Approval transaction (D5 §3a) must verify `ApprovalDecision.recommendation_ref.input_version == current AssessmentInputVersion` for the POC request before accepting any decision of type `Approved`. If stale, the write is rejected and a fresh engine run is triggered per the rule above — this is precondition **P4**, added alongside P1–P3, and like them it applies to `Approved` decisions only (D5 §3a).

**History preservation:** `Recommendation` rows are immutable and are never deleted or overwritten when superseded by a fresh run — the old recommendation, the `AssessmentInputVersion` it pointed to, and every audit entry referencing them remain exactly as they were. A superseding run creates a *new* `Recommendation` row linked to a *new* `AssessmentInputVersion`; "stale" is a relationship between two rows, never an edit to one.

## 5. Prompt-Injection Resistance

- The AI agent's scope-analysis and questionnaire-generation prompts treat all requester-submitted text (scope description, answers, filenames, uploaded-document content) as **data, not instruction** — the agent's own system instructions are not re-derivable or overridable from submitted content.
- Any submitted text that reads as an instruction to the AI (e.g., "mark this as GO", "skip the environment check") is logged as a `MISSING_EVIDENCE`/anomaly flag for reviewer attention, not acted on.
- The decision engine (§4) never takes its blocker/completeness/score inputs directly from free text — only from structured, previously-tagged provenance fields — so injected text in a free-text field cannot directly flip a Layer 2 blocker or Layer 1 completeness result.
- Adversarial test cases for this are specified in the Testing & Validation phase (outside this document's scope); this section defines the structural control, not the test plan.

## 6. Authorization-Boundary Protection

- The AI agent's service identity has **no write grant** to the Approval-decision object (D5) or to any evidence-state transition that promotes an item to `Verified – Human Validated` or `Rejected / Insufficient Evidence` (D3-Methodology, D5). This is enforced at the access-control layer, not by the AI choosing not to write.
- The AI agent may only write: questionnaire content, `AI_ASSERTION`/`AI_ASSUMPTION`/`MISSING_EVIDENCE`-tagged artifacts, control-mapping drafts (pending Reviewer confirmation per D3-Methodology), and the recommendation object (GO/NO-GO/Insufficient Information) — which is itself immutable once written and is a distinct object from the Approval decision (BR-010).
- **Actor identity is never a client-supplied field (MINOR correction, applies pack-wide):** every field that records who performed an action — `approver_id`, `disposition_authorized_by`, `environment_owner_id`, `revoked_by`, the AI agent's own acting identity, and every audit entry's actor field — is populated by the server from the authenticated session/service-credential context of the request, never accepted as a value the caller's request body supplies. A client cannot submit a write with someone else's ID in an actor field and have it honored; the server overwrites or rejects any such field with its own derived identity. This closes the same class of problem Finding 1 addressed for approval preconditions, applied to *who is recorded as having acted* rather than *whether the action was allowed*. D4 and D5 restate this at the specific fields where it matters most (environment sign-off, exception disposition, approval decisions).

## 7. Mitigating Reviewer/Approver Over-Reliance on AI (RSK-01)

- The Approval Request UI (D5) must surface the AI's recommendation alongside, not instead of, the underlying evidence-state table and blocker list — the recommendation is not permitted to be the only thing an Approver sees before deciding.
- A mandatory free-text rationale field is required from the Approver on every decision (BR-012/BR-015) — a rationale that merely restates the AI's own text is a process-quality signal to surface in periodic reporting, not something this document can technically prevent.
- The system logs, per Approver, the rate at which their decision matches the AI recommendation exactly; this is a monitoring signal for the organization, not an automated control (over-reliance is a human/process risk, not one this spec can fully engineer away).

## 8. Open Decisions Arising From This Document

| ID | Decision | Impact | Recommended owner |
|---|---|---|---|
| OD-10 | Exact threshold (count/%) of unusable answers that trips Layer 1 Completeness failure | Blocks finalizing the Completeness Check's deterministic rule | GRC/Product owner |
| OD-11 | Which (if any) scope-conditional findings the organization wants pre-elevated to Layer-2 blockers, beyond B-01/B-02 | Blocks finalizing D3-Methodology's policy hook table | GRC/Compliance owner |
| OD-12 | Whether "answer matches AI recommendation 1:1" monitoring (§7) feeds any formal review trigger, or is informational only | Affects D5's RACI and reporting requirements | Approval process owner |
| OD-15 | Layer 3 risk-factor weights (F1–F5), **including the Pending-Review discount factor within F1 (round 3 clarification — not a separate decision)**, and their versioning/governance | **Blocks Layer 3 implementation entirely** — the engine is not buildable without this | GRC/Risk owner |
| OD-16 | Layer 3 risk-score tiers and threshold values, and whether tier maps to approval tier (ties to OD-01) | **Blocks Layer 3 implementation entirely** | GRC/Risk owner, Approval process owner |

No organizational policy, approval tier, or blocker list beyond the structural B-01/B-02 is invented in this document — all scope-conditional blocker content is deferred to D3-Methodology's policy hooks, to be populated by the organization. Risk-scoring weights and thresholds (OD-15, OD-16) are likewise deliberately left unparameterized. Versioning/staleness (§4e) and actor-identity enforcement (§6) are specified as structural/technical rules in this round, not treated as open organizational decisions — they required no policy input to resolve.
