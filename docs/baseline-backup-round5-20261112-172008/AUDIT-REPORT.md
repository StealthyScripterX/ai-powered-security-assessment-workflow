# Consolidated Audit Report — Round 5 (Final)

**Scope:** D1 (frozen) through D5, after revisions responding to your fourth and final consolidation request (three targeted hash/versioning-coverage clarifications: scope versioning, mapping-hash field coverage, environment-hash field coverage). This is the final consolidated audit closing the documentation-first phase.
**Method:** targeted fix verification for each of the three round-5 items, a cross-document consistency pass (including a numbering/cross-reference check across every document that references D2 §4e's invalidating-changes list), a paper walk-through covering scope and mapping staleness scenarios, a full Open Decisions reconciliation, and a BR spot-recheck. Rounds 1–4 remain valid for what they covered; this report does not re-litigate them except where round 5's changes touch the same text.

## 1. Findings table (this round)

| Finding | Severity | Resolution |
|---|---|---|
| Scope versioning — scope submission changes not versioned | **MAJOR** | **Fixed.** D2 §4e's `AssessmentInputVersion` gained a `scope_hash` field and an explicit 8th invalidating-change item: creation, modification, replacement, or deletion of the scope submission (`scope_submission_ref`, D5 §3) now versions and stales existing recommendations. Before this fix, a requester could change the submitted scope after questions, mappings, and controls had already been generated against the old scope, with no mechanism forcing a fresh assessment — the same class of silent-staleness risk MAJOR-01 (round 3) closed for evidence/mapping/environment/questionnaire/policy state, just one input earlier in the pipeline than any of those. |
| Mapping hash coverage — `rationale` not covered; field-relevance undefined | **MAJOR** | **Fixed.** D3-Methodology's mapping record (`{control_id, framework, answer_excerpt, provenance_tag, confidence, rationale, review_status}`) has more fields than D2 §4e's `mapping_hash` previously named, and nothing stated which were assessment-relevant. Both documents now explicitly agree: `control_id`, `confidence`, `review_status`, and `rationale` are assessment-relevant (a Reviewer's `Adjust` action, per D3-Methodology §4, can change `rationale` alone); `framework` and `provenance_tag` are excluded as fixed/constant; `answer_excerpt` is excluded because an answer change is already covered via the questionnaire-change pathway, which produces a new mapping record rather than mutating this field. Before this fix, a Reviewer who adjusted only a mapping's stated rationale — without touching `control_id` or `confidence` — would have left existing recommendations un-stale despite a reviewer judgment the engine had not yet seen. |
| Environment hash coverage — `environment_readiness_hash` contents unenumerated | **MAJOR** | **Fixed.** The hash was previously defined only as "hash over D4 attestation/sign-off/exception state (incl. revocations)" — a description, not an enumeration. It now explicitly lists every covered field: `status`, `attestation_text`, every `ExceptionRecord` field (issue description, risk assessment, compensating controls, disposition, disposition rationale, remediation owner/deadline, expiry, revocation fields), supporting evidence references, and the resulting `final_signoff_boolean`. D4's `EnvironmentReadinessAttestation` gained an explicit `supporting_evidence` field so this enumeration has a concrete field to point at, rather than the hash definition referencing something the data model didn't yet name. |

**Self-found during this round's own consistency pass, not in your list:** D5 §3a's `MoreInfoRequested` narrative (added in round 4) cross-referenced D2 §4e's invalidating-change list as "item 5, questionnaire changes." Round 4 had already renumbered that list (inserting evidence-artifact changes as the new item 2), shifting questionnaire changes to item 6 — but this one cross-reference inside D5 was missed at the time and still said "item 5." Fixed in this round: corrected to "item 6." This is the same discipline round 3 applied to its self-found `POCApprovalRequest` inconsistency and round 4 applied to its D4 renumbering check — found during this round's own pass, not carried in from your list, and named rather than silently folded in.

## 2. Paper walk-through — scope and mapping staleness scenarios (verification)

| Scenario | Expected behavior | Result |
|---|---|---|
| Recommendation R1 (`GO`, input_version v1) exists; the requester later edits the scope submission's description of in-scope systems before the Approver acts | `scope_hash` changes → new `AssessmentInputVersion` v2 created → R1 is stale under the standard staleness test; an `Approved` attempt fails P4 and triggers a synchronous re-run against v2 | **Passes** |
| A Security Reviewer `Adjust`s a mapping, changing only its `rationale` field (control_id and confidence unchanged) | `mapping_hash` changes (per this round's expanded definition) → new `AssessmentInputVersion` created → existing recommendations go stale, even though no scoring-relevant field (`control_id`, `confidence`) moved | **Passes — this is the exact scenario the mapping-hash fix exists to catch; before this round, it would have silently NOT invalidated the recommendation** |
| An Environment Owner attaches a new supporting-evidence file to an `Attested` attestation, without changing its `status` | `environment_readiness_hash` changes (per this round's expanded definition, which explicitly includes `supporting_evidence`) → new `AssessmentInputVersion` created → existing recommendations go stale | **Passes — the gap this round's environment-hash fix exists to catch** |
| A requester deletes the scope submission entirely after a recommendation exists | Treated as an ordinary invalidating change per item 8 — existing recommendations go stale exactly as with any other change. Whether a POC request may *proceed* at all with no scope submission is a separate workflow-availability question, correctly left to D1/D5 and not resolved by the versioning rule itself (not a gap this round needed to close — scoped out explicitly in D2 §4e's item 8 note) | **Passes, with the scope boundary explicitly stated rather than left ambiguous** |
| Approver attempts `Approved`; `recommendation_ref.input_version` is current with respect to evidence, mapping, environment, questionnaire, and policy state, but the scope submission was modified after the recommendation was computed | P4 still catches this — `scope_hash` is one of the components of `AssessmentInputVersion`, so a scope-only change advances `version` exactly like any other change; P4's test (integer version comparison) requires no special-casing per hash component | **Passes — confirms the round-5 additions integrate into the existing single-version-number staleness test without requiring new precondition logic** |

## 3. Cross-document consistency (this round)

- D2 §4e's `scope_hash` ↔ D5 §3's `scope_submission_ref`: the new hash field is defined against the exact reference D5 already uses to identify the scope submission — no new, competing scope model introduced.
- D2 §4e's `mapping_hash` field-relevance statement ↔ D3-Methodology §2's mapping record field list: both documents now explicitly state the same four assessment-relevant fields and the same three excluded fields, each cross-referencing the other, rather than one asserting coverage the other's schema didn't support.
- D2 §4e's `environment_readiness_hash` enumeration ↔ D4 §3's `EnvironmentReadinessAttestation`/`ExceptionRecord` structs: every field named in the hash definition now exists in D4's data model (including the newly-added `supporting_evidence`), closing the gap where round 4's hash definitions could reference D4 fields in general terms without being traceable to a specific struct field.
- D2 §4e's invalidating-changes list, now at 8 items (unchanged in items 1–7 from round 4, new item 8 appended): checked against every external cross-reference in the pack — D4 §5.2 ("item 5") and D5 §3a ("item 6," corrected this round) both now point at the correct, current item.
- P1–P4, the `Approved`-only decision-type scoping, the TOCTOU concurrency-safety requirement, audit atomicity, and hash-chaining (all round 1–4 fixes) are unchanged by this round's edits — verified by confirming none of the three round-5 edits touched D5 §3a's precondition table, enforcement text, or concurrency-safety paragraph, D5 §5's audit-trail architecture, or D1 at all.
- No document references an Open Decision ID outside the README's master table; no new ID was introduced this round (see §5).

## 4. BR-001–BR-019 — spot recheck

No business requirement's *substance* changed this round. The three fixes extend the same staleness-protection coverage already established by MAJOR-01 (round 3) and the round-4 hash-coverage fix to two inputs — scope and the fuller mapping-record field set — that were previously under-specified, plus a long-overdue enumeration of what was already conceptually meant by "environment state." This is closing gaps in *what counts as a change*, not adding new obligations: BR-009a (exactly three outcomes), BR-016 (fixed layer order), BR-018 (GO cannot bypass gates), and BR-019 (atomic transition/audit persistence) are all unaffected in substance.

## 5. Updated Open Decisions Index

No new Open Decision IDs were created this round. The full master list is unchanged in membership from rounds 2–4; OD-05 remains reconciled rather than dropped:

| ID | Decision | Status |
|---|---|---|
| OD-01 | Approval tier structure | Open — **blocking** |
| OD-02 | Long-term environment-readiness integration scope | Open |
| OD-03 | Single-enterprise vs. multi-tenant | Open |
| OD-04 | No triage-time baseline exists | Open |
| OD-05 | Detailed evidence/blocker rule sets | Reconciled into OD-10/OD-11/OD-17 |
| OD-06 | Who holds "Environment Owner" | Open — **blocking** |
| OD-07 | Who may validate evidence (and sufficiency) | Open — **blocking** |
| OD-08 | Audit integrity-verification schedule/owner | Open |
| OD-09 | External audit-chain anchoring required? | Open |
| OD-10 | Layer 1 Completeness threshold | Open — **blocking** |
| OD-11 | Policy-hook content (PH-01/02/03) | Open (safe default exists) |
| OD-12 | AI-recommendation-match monitoring cadence | Open |
| OD-14 | Formal emergency-override mechanism — exist at all? | Open — default is no |
| OD-15 | Layer 3 risk-factor weights, including the F1 review-status discount | Open — **blocking** |
| OD-16 | Layer 3 risk-score thresholds/tiers | Open — **blocking** |
| OD-17 | Per-control-family evidence sufficiency criteria | Open (safe default exists) |
| OD-18 | Extend non-waivable exception dimension list? | Open |
| OD-19 | Remediation-deadline escalation behavior | Open |
| OD-20 | Post-approval revocation handling | Open |
| OD-21 | Integrity-break halt vs. alert-only | Open |

**Six remain blocking** (OD-01, OD-06, OD-07, OD-10, OD-15, OD-16) — identical in membership across all five rounds (one self-audit, four independent reviews). This round's fixes made the versioning/staleness machinery complete without touching which decisions are load-bearing.

## 6. Final Verdict

### NOT READY FOR IMPLEMENTATION

**Evidence for this verdict:**

- **Technical/structural completeness is now, as far as five rounds of review have been able to determine, closed.** Round 1 built the five-document structure and self-closed an exception-model gap. Round 2 closed a real authorization-bypass CRITICAL (a human Approver could write `Approved` while sign-off was incomplete or a blocker was unresolved) and built the Layer-3 risk-scoring framework. Round 3 closed a stale-data bypass (a recommendation could be approved after the facts it was based on had changed) and tightened actor-identity/audit-durability guarantees. Round 4 closed the remaining concurrency (TOCTOU) and partial-hash-coverage gaps in that same staleness mechanism, and resolved which decision types staleness protection should gate. Round 5 closed the last three coverage gaps in that mechanism — scope changes, the fuller mapping-record field set, and a fully enumerated environment-readiness hash — and fixed one self-found cross-reference regression from round 4. No round has found a new *structural* bypass since round 2; rounds 3–5 have progressively hardened the same staleness/versioning boundary rather than finding new categories of gap, which is itself evidence the structural work is substantively done.
- **What remains is exclusively organizational, not technical.** The same six Open Decisions (OD-01, OD-06, OD-07, OD-10, OD-15, OD-16) have been flagged as blocking since round 2 and have not changed across three further rounds of adversarial review. Each is a question only the organization can answer (who approves, who owns the environment, who validates evidence, what completeness threshold applies, what the risk weights and thresholds are) — none is a specification gap this documentation process can close by itself, and resolving them does not require reopening or rewriting any document in this pack.
- **No regression was found or introduced.** This round's cross-document consistency pass re-verified P1–P4, the `Approved`-only decision-type scoping, the TOCTOU concurrency-safety requirement, audit atomicity, and hash-chaining — all unchanged from round 4 — alongside confirming the three new fixes integrate into the existing single-version-number staleness test without new precondition logic.

**Recommended path to READY:** resolve OD-01, OD-06, OD-07, OD-10, OD-15, OD-16. At that point, the remaining fourteen Open Decisions either have a stated safe default (OD-11, OD-17) or are genuinely deferrable without blocking a build (OD-02, 03, 04, 08, 09, 12, 14, 18, 19, 20, 21) — plus the one build-time (not policy) implementation note carried forward since round 3 (propagating a policy/config change across in-flight POC requests), which belongs in the technical design, not in a further documentation round.

**This closes the documentation-first phase.** Five rounds of review (one self-audit, four independent reviews) have been applied to this pack; no further review round is anticipated absent a change in scope. The next step this pack points to is resolving the six blocking Open Decisions and beginning technical design — not further specification work on the documents themselves.
