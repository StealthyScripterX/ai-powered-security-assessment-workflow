# D5 — Approval, RACI & Audit Trail Specification

**Status:** Draft, incorporated into one-go pack.
**Depends on:** D2, D3-Methodology, D4.

## 1. Purpose

Defines who may do what in the human approval workflow, the approval object's data model and immutability, and the audit trail's tamper-evidence mechanism.

## 2. RACI — Interim Model (OD-01 unresolved)

**Important:** D1's Open Decision OD-01 (single / risk-tiered / fixed multi-stage approval) is **not resolved**. Per the non-negotiable instruction not to invent approval tiers, the table below uses a single-tier interim model **explicitly marked as a placeholder**, not a decision. If the organization selects risk-tiered or fixed multi-stage, this table's "Final Approver" row splits into multiple rows and the Approval object's data model (§3) gains a `tier` field — flagged as a design point, not retrofitted silently.

| Activity | Requester | AI Agent | Security Reviewer | Environment Owner | Final Approver (interim, single-tier) | Compliance/Audit |
|---|---|---|---|---|---|---|
| Submit scope | R/A | — | — | — | — | — |
| Generate questionnaire | I | R/A | — | — | — | — |
| Answer questionnaire | R/A | — | — | — | — | — |
| Generate mapping/artifacts | I | R/A | C | — | — | — |
| Confirm/override mapping | I | I | R/A | — | — | — |
| Evidence validation (Not Provided→Verified/Rejected) | I | — | R/A | — | — | — |
| Environment readiness attestation | I | — | C | R/A | — | — |
| Decision engine run | I | R/A | I | I | I | — |
| Approval decision (Approve/Reject/Request More Info) | I | — | C | — | **R/A**, subject to system-enforced preconditions P1–P4 (§3a) | — |
| Audit trail read | — | — | — | — | — | R/A |

*(R = Responsible, A = Accountable, C = Consulted, I = Informed)*

## 3. Approval Object Data Model

```
POCApprovalRequest {
  id
  scope_submission_ref
  questionnaire_responses_ref
  control_mapping_ref            // includes confidence + review_status (D3-Methodology)
  evidence_state_summary_ref     // four-state distribution (D1 BR-005)
  environment_readiness_ref      // D4 sign-off object
  current_recommendation_ref: ref(Recommendation)  // points to the LATEST
                                  // Recommendation (D2 §4e) for this POC request;
                                  // superseded by a new ref whenever the engine
                                  // re-runs (D2 §4e) — never edited in place.
                                  // Historical Recommendation rows remain intact
                                  // and linked via their own input_version chain;
                                  // this pointer only tracks "current" for display
                                  // and for the P4 staleness check (§3a). No
                                  // separate ai_recommendation/rationale fields
                                  // are duplicated here — Recommendation (D2 §4e)
                                  // is the single source of truth.
  status: enum[Pending, Approved, Rejected, MoreInfoRequested]
  created_at
}

ApprovalDecision {
  poc_approval_request_id
  recommendation_ref: ref(Recommendation)  // D2 §4e — the exact immutable
                                            //   Recommendation this decision is
                                            //   acting on, including its
                                            //   input_version pointer
  approver_id: ref(User)          // server-derived from authenticated session,
                                   // never client-supplied (see "actor identity"
                                   // below); must hold Final Approver role; AI
                                   // identity structurally excluded
  decision: enum[Approved, Rejected, MoreInfoRequested]
  rationale: string               // mandatory, non-empty (D1 BR-012/BR-015)
  disagreement_rationale: string | null  // required specifically when decision
                                          // contradicts ai_recommendation's
                                          // directional implication (Finding 6.2);
                                          // see §3b for what counts as contradiction
  matched_ai_recommendation: boolean  // derived, for RSK-01 monitoring (D2 §7)
  recommendation_was_stale: boolean   // round 4 — true if recommendation_ref's
                                       // input_version was not current at the
                                       // moment this decision was committed;
                                       // see §3a for which decisions this can
                                       // be true for and what it means for each
  decided_at
  immutable: true                 // no update/delete after creation
}
```

**Structural enforcement (BR-010, D2 §6):** the AI agent's service identity holds no grant on `ApprovalDecision` writes. This is an access-control-layer fact, not a UI restriction — even a compromised or misbehaving AI process cannot write to this table.

**Actor identity enforcement (MINOR correction, round 3):** `approver_id` is never read from the request payload — it is derived server-side from the authenticated session or service-credential context making the call, exactly as D2 §6 and D4 §4 now state for their own actor fields. A client cannot submit a decision "as" another Approver.

## 3a. Server-Side Approval Preconditions (Finding 1 — CRITICAL fix)

**Problem this closes:** nothing in round 1 of this pack prevented a Final Approver from writing `decision = Approved` while a mandatory gate was unmet — the RACI table said the Approver is "Accountable" for the decision, but accountability for *making* a decision is not the same as the *system* refusing an impossible one. A human role's authority to decide does not include authority to decide around a structural prerequisite that D1 made non-negotiable (BR-018, BR-009a, and the blocker layer of BR-016). This section makes the refusal a server-side, transaction-level fact, not a UI validation someone could bypass by calling the API directly.

**Precondition checks, evaluated inside the same transaction that would write `ApprovalDecision`:**

| Check | Condition that must hold for `decision = Approved` to be accepted | Source |
|---|---|---|
| P1 | `EnvironmentReadinessSignOff.final_signoff_boolean = true`, **re-evaluated at commit time**, not read from a cached/stale value computed when the recommendation was generated | D4 §3 |
| P2 | No Layer 2 Mandatory Security Blocker (D2 §4b) is currently flagged for this `poc_approval_request_id` | D2 §4b |
| P3 | `recommendation_ref.outcome ≠ INSUFFICIENT_INFORMATION` | D1 BR-009a |
| P4 | `recommendation_ref.input_version` equals the **current** `AssessmentInputVersion` for this POC request — i.e., the `Recommendation` being acted on is not stale | D2 §4e |

**Decision-type scoping of P4 (round 4 clarification — resolves the D5/D2 §4e disagreement you flagged):** P1–P3 gate `Approved` only, as before. **P4 also gates `Approved` only** — it does not block `Rejected` or `MoreInfoRequested`. The reasoning: rejecting a request or asking for more information never grants testing authorization, so there is no safety reason to force a fresh engine run before allowing either — doing so would mean the system could trap a stale, unwanted request in limbo, unable even to be turned down until someone goes and re-runs an assessment nobody asked for. Instead:
- `Rejected` and `MoreInfoRequested` are **always permitted regardless of staleness** — "preserve the ability to reject a request safely" means rejection is never gated on freshness.
- To satisfy "no decision is silently based on stale information," every `ApprovalDecision` — including `Rejected` and `MoreInfoRequested` ones — records `recommendation_was_stale` (§3) as a plain fact: was `recommendation_ref.input_version` current at commit time, yes or no. A stale-but-safe decision is transparently logged as having been made against stale information, never hidden by simply not checking.
- `MoreInfoRequested` is the designed path back into the workflow: per D2 §4e's invalidating-change list (item 6, questionnaire changes), once the requester supplies the requested information, that submission itself creates a new `AssessmentInputVersion` — starting a new assessment cycle — and any subsequent decision attempt is checked against that new version, not the one that triggered the request.
- `Approved` remains the only decision P4 can block, consistent with P1–P3 only ever gating `Approved` as well.

**Concurrency safety for P4 (round 4 — closes a TOCTOU gap):** reading the current `AssessmentInputVersion.version` and writing the `ApprovalDecision` are two separate operations; without a concurrency guarantee, an invalidating change could land in the gap between them, after the version was read as "current" but before the decision commits — silently approving against information that became stale a moment earlier. This is prevented by requiring one of the following, chosen at implementation time but **mandatory in substance**: (a) the read of `AssessmentInputVersion.version` and the write of `ApprovalDecision` occur within a single transaction using `SERIALIZABLE` isolation (or the database's strictest available equivalent), so a concurrent write that would change the version forces this transaction to abort and retry rather than commit against data that moved; or (b) the `ApprovalDecision` write is conditioned on an explicit row/version lock or optimistic-concurrency check against `AssessmentInputVersion` (e.g., a `WHERE version = :expected_version` clause on the same transaction that the decision write depends on, failing the write if the version has since advanced) — equivalent in effect to (a), implemented without full serializable isolation if the platform doesn't offer it cheaply. Either way, the guarantee required is: **no `Approved` decision may ever commit against an `AssessmentInputVersion` that is no longer current by the time the decision write actually lands**, not merely by the time P4 was first checked.

**Enforcement:** if P1, P2, P3, or P4 fails, the write is **rejected by the data layer** (e.g., a database-level check constraint, a stored procedure, or an application-layer guard that runs inside the same transaction and is not reachable by any client-side path) — not merely flagged for review after the fact. If P4 specifically fails, the system does not just reject the attempt: it synchronously re-runs the decision engine against the current `AssessmentInputVersion` (per D2 §4e's re-run trigger rule) and returns the fresh `Recommendation` to the Approver, so the rejection carries the Approver forward rather than leaving them with a bare error and a now-useless stale reference. The rejected attempt itself generates an audit entry (who attempted it, which precondition failed, when) per §5 — a blocked attempt is itself audit-worthy, not a silent no-op.

**Decision options are gated by recommendation state**, as defense-in-depth beyond the engine's own output (recommendations can go stale between generation and decision — see D4 §5.2 Revocation and D2 §4e):
- `recommendation_ref.outcome = GO` → Approver may choose `Approved` or `Rejected` (P1–P4 are expected to already hold for `Approved`, and are re-checked regardless; `Rejected` is unconditional per the scoping rule above).
- `recommendation_ref.outcome = NO-GO` → Approver may choose `Rejected` or `MoreInfoRequested`, unconditionally; `Approved` is rejected by P2 unless the blocker has since been genuinely resolved (not merely reconsidered) and the recommendation re-run (which, per P4, produces a new `Recommendation` the Approver must then act on — not the original `NO-GO` one).
- `recommendation_ref.outcome = INSUFFICIENT_INFORMATION` → Approver may choose `MoreInfoRequested` or `Rejected`, unconditionally; `Approved` is rejected by P3 outright — there is no path to approving an assessment the engine itself said was inadequate.

## 3b. Formal Exception / Override Mechanism — NOT DEFINED (Finding 1)

Per your explicit instruction, no override path around P1–P4 is defined in this document, because doing so would mean inventing organizational policy about who may authorize bypassing a mandatory security prerequisite and under what circumstances. **The default is closed: no override mechanism exists.** If the organization later decides it wants a narrowly-scoped, heavily-audited emergency-override capability (e.g., for a genuine incident-response scenario where normal process cannot apply), that is **Open Decision OD-14**, and any such mechanism — including who may invoke it, what additional sign-off it requires, and what retrospective review is mandatory — must be specified in a future revision, not assumed from this gap.

## 4. Evidence Validation Workflow

- Only a Security Reviewer (or, pending **OD-07**, possibly also a Final Approver — unresolved, not decided here) may transition evidence from `Submitted – Pending Review` to `Verified – Human Validated` or `Rejected / Insufficient Evidence`.
- An uploaded file's arrival event and its validation event are **separate, both-logged** audit entries — upload never implies validation (D1 BR-005a).

## 5. Audit Trail Architecture (BR-013, BR-017, BR-019)

### 5.1 Append-Only Enforcement
- The audit store grants `INSERT`-only privilege to every application and service identity, including the AI agent's own identity. No role — including a platform administrator role used for routine operations — holds `UPDATE` or `DELETE` on this store. Any schema-level exception (e.g., a disaster-recovery procedure) must go through a separate, out-of-band process logged elsewhere, not through normal application access.

### 5.1a Durable Logging of Rejected Attempts and Audit-Store Failures (MINOR correction, round 3)

**Rejected/blocked attempts are audit events even though nothing changed.** A write rejected by P1–P4 (§3a), by the non-waivable-dimension rule (D4 §3), or by any other precondition in this pack did not produce a state transition — but the *attempt* is itself security-relevant information (who tried, what they tried, which precondition stopped it, when) and must be durably logged with the same rigor as a successful transition:
- The rejected-attempt audit entry is written **synchronously, before the rejection response is returned to the caller** — the caller does not receive "rejected" until the rejection itself is durably recorded.
- It participates in the same hash chain as every other entry (§5.2) — a rejected attempt is not a second-class, unverified log line.

**Audit-store failure during a rejected-attempt log (a gap BR-019 didn't explicitly cover, since BR-019 is phrased around successful transitions):** the same fail-closed principle is extended here. If the audit store cannot durably record the rejection, the system does not silently let the caller's request through as if nothing happened, and does not silently drop the attempt record — it returns a hard error (e.g., "unable to process request") distinct from an ordinary precondition rejection, so a caller cannot distinguish "my request was properly refused" from "the system is failing open" by looking at the response. **General rule, stated once here and applying throughout the pack:** every write path in this system — successful transition or rejected attempt — fails closed when the audit store is unavailable. No transition, approval, attestation, or disposition is ever considered to have happened without a durable audit record of it, and no attempt to perform one is ever silently discarded without one either.

### 5.2 Hash-Chaining

- **Algorithm (Finding 6.3):** SHA-256. This is a standard, uncontroversial technical choice (not an organizational policy decision) and is specified directly rather than left open.
- **Canonical serialization (Finding 6.3):** before hashing, `entry_content` is serialized using a fixed, deterministic encoding — field order fixed by schema (not insertion order), UTF-8, no non-significant whitespace, numbers in a fixed format (no locale-dependent formatting). Without this, two semantically-identical entries could serialize differently on different nodes/runs and produce different hashes, breaking verification for no real reason. The exact canonical form (e.g., a specific canonical-JSON profile) is an implementation detail to fix once at build time and never change without a migration plan — changing it retroactively would break every existing hash in the chain.
- `entry_hash = SHA-256(canonical_serialize(entry_content) || previous_entry_hash)`. Altering any historical entry's content changes its hash, which breaks the chain for every subsequent entry — detectable by recomputing the chain.
- `entry_content` includes: actor identity (including a distinct identity for the AI agent vs. human roles), action type, affected object ID, before/after state summary where applicable, and timestamp.

### 5.3 Atomic Transition/Audit Persistence (BR-019)
- Every workflow state transition (e.g., evidence validated, sign-off recorded, approval decided) and its corresponding audit entry are written within a single atomic operation (one database transaction, or an equivalent two-phase guarantee if the audit store is physically separate). If the audit write fails, the transition is rolled back — the system must never allow a transition to "succeed" silently without its audit record.
- **Concurrent audit writes (Finding 6.3):** because each entry's hash depends on the *previous* entry's hash, two concurrent writes racing to compute `previous_entry_hash` from the same prior entry would corrupt the chain. The store must serialize append order — either a single-writer append queue, or an atomically-assigned monotonic sequence number obtained via the database's own serialization primitive (e.g., a `SERIALIZABLE` transaction or a dedicated sequence) such that "what is the current last entry" is never read by two writers without one of them being forced to retry against the new tail. This is a concurrency-correctness requirement, not a policy choice, and is specified here rather than left open.
- **Trade-off flagged (RSK-08, carried from D1):** this means an audit-store outage blocks all workflow progress, not just audit visibility. This availability/integrity trade-off is accepted as a deliberate design choice consistent with BR-019, not an oversight — but it should be named explicitly to whoever signs off on production readiness.

### 5.4 Periodic Integrity Verification
- A verification job walks the hash chain and confirms no break exists. **Schedule and ownership are Open Decision OD-08** — not invented here. Recommended default (not a decision): daily, owned by the Platform Owner, with an alert to Compliance/Audit on failure. This is a recommendation for the organization to accept or override, not a specification.
- **Verification failure handling and recovery (Finding 6.3):** on detecting a break, the job records exactly which entry index first fails to verify (the break point, not just "chain is broken"), alerts Compliance/Audit and the Platform Owner immediately, and the affected range of entries is flagged `integrity_status = Disputed` for investigation. **Whether a detected break halts new workflow transitions (safety-first) or only raises an alert while the system keeps operating (availability-first) is Open Decision OD-21** — this document does not decide that trade-off, only that the detection and alerting must happen and must identify the exact break point, not just confirm "something is wrong somewhere."
- **Recovery:** entries before the break point remain trusted (the chain up to that point still verifies). Entries from the break point forward cannot be cryptographically trusted as unmodified and must be reconciled against independent records (e.g., application-level logs, backups) as a manual incident-response process — this document specifies that such a process must exist, not its operational detail, which is outside a requirements/architecture document's scope.

### 5.5 External Anchoring (Optional, OD-09)
- Periodically exporting a chain digest to storage outside the primary system's own write path is **not committed** for this phase. Noted as a credible post-MVP enhancement if a full-compromise threat model is in scope; not required for MVP per the lean roadmap.

## 6. Separation of Duties

- Compliance/Audit Reviewer identity has read-only grant on the audit store; it holds no write grant anywhere in the system.
- The AI agent's identity is excluded from: `ApprovalDecision` writes, evidence-state writes, and `EnvironmentReadinessAttestation`/`SignOff` writes (D4 §4). It may write: questionnaire content, mapping drafts, recommendation objects, and its own audit entries (as the acting identity on its own actions).

## 7. Mitigating Over-Reliance on AI Recommendations (carries D2 §7 into process)

- `ApprovalDecision.matched_ai_recommendation` (§3) is tracked per Approver over time. This is a monitoring/reporting hook; this document does not define a reporting cadence or escalation threshold — that is **Open Decision OD-12** (carried from D2), to be resolved by whoever owns the approval process operationally.
- **Mandatory disagreement rationale (Finding 6.2):** `matched_ai_recommendation = false` whenever the decision's directional implication differs from `recommendation_ref.outcome` — `Rejected` when the outcome was `GO`, or `Approved` when the outcome was anything other than `GO` (noting `Approved` against `NO-GO`/`INSUFFICIENT_INFORMATION` is already blocked by §3a P2/P3 except in the narrow case where P2's blocker was genuinely resolved between recommendation and decision, which per P4 requires a fresh `Recommendation` in any case). Whenever `matched_ai_recommendation = false`, `disagreement_rationale` (§3) is required and is validated as non-empty and distinct from `rationale` — the system rejects a disagreement rationale that is empty or an exact duplicate of the general rationale field, forcing the Approver to actually state what they're disagreeing with and why, rather than satisfying the field mechanically.

## 8. Open Decisions

| ID | Decision |
|---|---|
| OD-01 | Approval tier structure — this document uses a placeholder single-tier model only |
| OD-07 | Who may perform evidence validation — Security Reviewer only, or also Final Approver |
| OD-08 | Integrity-verification schedule/owner (default suggested: daily / Platform Owner) |
| OD-09 | Whether external chain anchoring is required this phase |
| OD-12 | Reporting cadence/escalation threshold for AI-recommendation-match monitoring |
| OD-14 *(new)* | Whether a formal, policy-gated emergency-override mechanism should exist at all for P1–P3 (§3b) — default is no such mechanism |
| OD-21 *(new)* | Whether a detected audit-chain integrity break halts new workflow transitions or only alerts (§5.4) |

**Note:** §3a/§3b (Finding 1) are not themselves open decisions — the precondition enforcement (P1–P4) and the closed-by-default override posture are specified, not deferred. Only *whether to later open* an override path (OD-14) is left to the organization.
