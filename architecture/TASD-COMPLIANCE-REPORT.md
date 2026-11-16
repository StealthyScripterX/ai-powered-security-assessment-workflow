# TASD-v1.0 Documentation Compliance Review

**Review type:** Originally review-only (§1 below records the as-found findings exactly as they were discovered). **Update:** Finding Ma-01 (the pack-wide stale cross-reference defect) has since been corrected in `TASD-v1.0.md` at the user's request — see §7. `D1-Requirements.md`, `D2-AI-Governance.md`, `D3-Control-Catalog.md`, `D3-Methodology.md`, `D4-Environment-Readiness.md`, `D5-Approval-Audit.md`, `README.md`, and `AUDIT-REPORT.md` were read in full for the review and were never modified.

**Reviewed:** `architecture/TASD-v1.0.md` (28 sections, 10 Mermaid diagrams), `architecture/README.md`, `architecture/OPEN-DECISIONS.md`.

**Against:** `docs/baseline/D1-Requirements.md`, `D2-AI-Governance.md`, `D3-Control-Catalog.md`, `D3-Methodology.md`, `D4-Environment-Readiness.md`, `D5-Approval-Audit.md`, `README.md`, `AUDIT-REPORT.md` — **current on-disk content**, i.e. the professionalized/restructured versions produced by the documentation-cleanup pass that ran in this same session, after most of `TASD-v1.0.md` was drafted against the pre-cleanup section numbering.

## 1. Executive Summary

**Substantively, TASD-v1.0 is a faithful, rigorous implementation of the D1–D5 baseline.** Every provision checked — the three-axis provenance/review-status/evidence-state separation, the three-layer engine with fixed order and short-circuit, the full `AssessmentInputVersion`/`Recommendation` versioning model with all eight invalidating-change items, P1–P4 with the TOCTOU closure, the non-waivable Isolation/AccessControl rule, SHA-256 hash-chaining with atomic persistence and fail-closed behavior, and the structural AI/human authority boundary — is implemented correctly and in most cases implemented *more* precisely than the baseline's own prose (e.g., turning "weights are TBD" into a `NULL`-gated engine refusal rather than a silent default). No genuine contradiction of a business requirement, data model, or approval precondition was found.

**One systemic, non-substantive defect was found:** the documentation-cleanup pass that produced the current `docs/baseline/` files renumbered nearly every section in D2, D3-Catalog, D3-Methodology, D4, and D5. `TASD-v1.0.md` was drafted against the pre-cleanup numbering (e.g., "D2 §4e", "D5 §3a", "D4 §3", "D3-Methodology §6a") and its roughly 150 cross-references into those four documents are now stale — they point at section numbers that have moved. The *content* each citation describes is still correctly represented; only the *pointer* is wrong. D1 citations are unaffected because TASD cites D1 almost exclusively by stable requirement ID (`BR-005`, `ASM-02`, `RSK-08`, `OD-06`) rather than by section number.

This was reported as the review's one **Major** finding (§3) and has since been **fixed** — see §7. No **Critical** finding was identified — nothing in TASD weakens, bypasses, or silently resolves a baseline invariant or an Open Decision.

## 2. Traceability Matrix

| Requirement / Source | Architecture Section | Status | Finding |
|---|---|---|---|
| BR-001 (no pre-existing documentation required) | TASD §12.1 step 1 | COMPLIANT | `scope_submission` has no required attachment field |
| BR-002 (11–15 questions) | TASD §13.4 stage 4, §22.1 T-AI-03 | COMPLIANT | Hard-bound server-side re-validation, not trusted from AI output alone |
| BR-003 (Mandatory-domain coverage) | TASD §13.4, §14.4 Layer 1 Rule 1 | COMPLIANT | — |
| BR-004 (specific identifiers, not families) | TASD §11.4 `mapping_record.control_id` FK, §13.5 closed-vocabulary constraint | COMPLIANT | AI-proposed identifiers outside the catalog are rejected, not coerced |
| BR-005 (four evidence states) | TASD §11.5 `control_evidence_state.state` enum | COMPLIANT | Exactly four values, no fifth |
| BR-005a (never auto-Verified) | TASD §15.2, §15.3, §11.10 (`ai_svc` has no grant) | COMPLIANT | Enforced at the database-grant level, not application convention |
| BR-006 (blocker/score separation) | TASD §14.4/§14.5 (B-01/B-02 disjoint from F1–F5) | COMPLIANT | — |
| BR-007 (readiness per D4 SOP) | TASD §16 in full | COMPLIANT | All seven dimensions carried exactly |
| BR-008 (assumptions/gaps marked) | TASD §13.1, §13.5 rationale requirement | COMPLIANT | — |
| BR-009 (exactly three outcomes, advisory) | TASD §11.6 `recommendation.outcome` enum, §14.6 | COMPLIANT | `REFUSED` explicitly kept out of the persisted enum (§14.6) — correct treatment of a fourth *operational* signal as distinct from a fourth *recommendation outcome* |
| BR-009a (never forced GO/NO-GO when inadequate) | TASD §14.4 Layer 1, §14.7 | COMPLIANT | Extended correctly: "policy not configured" is also modeled as inability to confirm adequacy, not a default pass |
| BR-010 (recommendation ≠ authorization) | TASD §11.6 (`recommendation` vs. `approval_decision` as distinct tables), §11.10 | COMPLIANT | — |
| BR-011 (approval request composition) | TASD §17.3 | COMPLIANT | — |
| BR-012 (sole human Approver) | TASD §17.2, §11.10 | COMPLIANT | — |
| BR-013 (audit entry per transition) | TASD §12.1 (DB writes column), §22.8 coverage-completeness meta-test | COMPLIANT | — |
| BR-014 (audit read-only for Compliance) | TASD §11.10 `audit_reader` role | COMPLIANT | — |
| BR-015 (AI vs. human content distinguished) | TASD §11.4 `provenance_tag`, §18.1 `actor_kind` | COMPLIANT | — |
| BR-016 (fixed layer order, deterministic) | TASD §14.1, §14.2 | COMPLIANT | Pure-function design is a stronger implementation of "deterministic" than the baseline requires, not a weaker one |
| BR-017 (append-only, hash-chained, tamper-evident, verified) | TASD §18.1–§18.4 | COMPLIANT | — |
| BR-018 (GO impossible without complete sign-off / unresolved blocker) | TASD §14.4 (B-01 unconditional), §17.4 (P1/P2 recomputed at commit) | COMPLIANT | — |
| BR-019 (atomic transition + audit, failed audit blocks transition) | TASD §18.3, §18.6 | COMPLIANT | — |
| D2 §6 four provenance types, no fifth | TASD §11.4 (three separate `provenance_tag` enum columns, each constrained to its one legal value) | COMPLIANT | — |
| D2 §6 three independent axes never merged | TASD §15.1 (contract test T-EV-05 fails the build on any merge) | COMPLIANT | Enforced as a testable contract, not only a convention |
| D2 §8 Layer 1/2/3 fixed order, short-circuit | TASD §14.2 | COMPLIANT | — |
| D2 §8.2 B-01/B-02 structural, not configurable away | TASD §14.4 ("no `config` field that turns B-01 off") | COMPLIANT | — |
| D2 §8.3 F1 confidence/review-status reconciliation | TASD §14.5 | COMPLIANT | Rejected-excluded / Pending-discounted / Confirmed-Adjusted-full-weight ordering implemented literally |
| D2 §8.3 evidence-state dominance over confidence | TASD §14.5, property-tested at §22.1 T-ENG-08/09 | COMPLIANT | Verified as a property across the full Cartesian product, not example-based only |
| D2 §8.3 risk tier is GO-only metadata | TASD §11.6 `CHECK (risk_tier IS NULL OR outcome = 'GO')` | COMPLIANT | — |
| D2 §8.5 AssessmentInputVersion, 5 hashes, 8 invalidating changes | TASD §11.6–§11.8 | COMPLIANT | Every hash's field coverage (including the Round-5 `rationale`, `supporting_evidence`, `scope_hash` fixes) is reproduced exactly |
| D2 §8.5 staleness test is an integer comparison, not hash re-derivation | TASD §11.6 comment, §17.4 P4 | COMPLIANT | — |
| D2 §9.1 prompt-injection: data not instruction | TASD §13.7 (type-level guarantee: `PromptPayload.requester_data` is the only path) | COMPLIANT | Stronger than the baseline's own framing — a type-system guarantee rather than a coding discipline |
| D2 §9.2 actor identity always server-derived | TASD §8.3, §11.10 (every actor field, pack-wide) | COMPLIANT | — |
| D3-Catalog §2 UNVERIFIED notice | TASD §6.4, §11.3 `verification_status` column, Phase 0 (§25) gate | COMPLIANT | Carried into the data model and the UI contract, not just restated in prose |
| D3-Catalog §5 no control is individually an automatic blocker | TASD §11.3 `applicability` enum has no "automatic blocker" value | PARTIALLY COMPLIANT | See Finding M-02 below — the three-value `applicability` enum is TASD's own interpretation of D3-Catalog's free-text per-row status column; it does not misstate the no-automatic-blocker rule, but it is an architectural abstraction the baseline itself does not define, and should be confirmed against the full ~34-row catalog during Phase 0's GRC validation rather than assumed correct for every row |
| D3-Methodology §8.2 three independent axes (same rule as D2 §6, restated) | TASD §15.1 | COMPLIANT | — |
| D3-Methodology §8.3 Confirm/Adjust/Reject, new row per transition | TASD §11.4 `mapping_record.supersedes_id`, never edit-in-place | COMPLIANT | — |
| D3-Methodology §9 conditional-domain triggers logged | TASD §11.4 `trigger_basis` column, `CHECK` forbidding it on Mandatory domains | COMPLIANT | — |
| D3-Methodology §10 policy hooks, empty until OD-11 | TASD §11.7 `layer2_policy_hooks` default `[]` | COMPLIANT | Matches the baseline's own stated interim behavior (hooks are risk-scoring-only, never gating, until OD-11), not an invented default |
| D3-Methodology §11 EvidenceRequirement structure; sufficiency is OD-17 | TASD §15.6 | PARTIALLY COMPLIANT | See Finding M-03 below — TASD's claim that `sufficiency_criteria = NULL` means "the Reviewer's judgment is the only bar... exactly as the baseline's safe default describes" slightly overstates what D3-Methodology itself says; the baseline leaves the interim behavior for OD-17 unstated (unlike OD-11, which explicitly describes its own interim rule). TASD's inferred behavior is reasonable and harmless, but it is TASD's inference, not a baseline restatement |
| D3-Methodology §12 contradiction forces confidence to Low | TASD §15.7 | COMPLIANT | — |
| D4 §5 seven readiness dimensions | TASD §16.1, §11.5 enum | COMPLIANT | Exact enum match, no dimension added/renamed |
| D4 §6 full ExceptionRecord, not bare co-sign | TASD §11.5 `exception_record` table | COMPLIANT | — |
| D4 §6 Isolation/AccessControl never `Accepted` | TASD §11.5 `CHECK` constraint, §16.4 defense-in-depth assertion | COMPLIANT | Enforced at the data layer, matching the baseline's explicit "not merely documented convention" requirement |
| D4 §6 `final_signoff_boolean` computed, not manually maintained | TASD §16.4 `fn_final_signoff`, called fresh at every B-01/P1 read | COMPLIANT | Same function used by both callers — no drift risk between two independent re-implementations |
| D4 §7 actor identity server-derived; not Requester, not AI | TASD §16.2 | COMPLIANT | — |
| D4 §8.3 revocation is itself an invalidating change, "caught twice over" | TASD §16.5, §22.4 T-CONC-03 | COMPLIANT | — |
| D5 §4 RACI, single-tier placeholder (OD-01) | TASD §17.1, `policy_config.approval_tier_model` reserved | COMPLIANT | — |
| D5 §6 P1–P4, all four evaluated in the same transaction | TASD §11.9, §17.4 | COMPLIANT | — |
| D5 §6 P4 decision-type scoping (Approved only; Rejected/MoreInfoRequested unconditional) | TASD §11.9 pseudocode, §22.6 T-APR-03 | COMPLIANT | — |
| D5 §6 TOCTOU concurrency closure | TASD §11.9, ADR-011 | COMPLIANT | Explicit choice of lock+`REPEATABLE READ` over `SERIALIZABLE`, both permitted by the baseline; recorded as a decision with alternatives, per the brief's ADR requirement |
| D5 §6 rejected attempt is itself audit-worthy, synchronous, before response | TASD §11.9, §17.6 | COMPLIANT | — |
| D5 §7 no override mechanism; default closed (OD-14) | TASD §17.7 | COMPLIANT | No bypass function, grant, or config field exists anywhere in the schema or API surface |
| D5 §9 mandatory, non-duplicate disagreement rationale | TASD §11.6 `CHECK` constraint | COMPLIANT | — |
| D5 §10.1–§10.6 hash chain, canonical serialization, atomicity, verification, recovery, external anchoring hook | TASD §18.1–§18.8 | COMPLIANT | — |
| D5 §10.2 fail-closed on audit-store failure, every write path | TASD §18.6, T-AUD-10 | COMPLIANT | — |
| D5 §10.4 single-writer serialization of the chain tail | TASD §18.2 `audit_chain_tail FOR UPDATE` | COMPLIANT | — |
| Brief §6 invariant: "hash chaining alone does not make a database tamper-proof" | TASD §18.10 | COMPLIANT | Stated explicitly, with the exact residual-risk boundary (SQL-interface tampering defended; host/physical-storage access not) named rather than glossed over |
| Six blocking Open Decisions (OD-01, OD-06, OD-07, OD-10, OD-15, OD-16) kept unresolved | TASD §2.4, §14.7, §24, `OPEN-DECISIONS.md` | COMPLIANT | None invented or defaulted; each is `NULL`-gated configuration with an explicit refusal behavior where it blocks engine output |
| All 21 Open Decisions (full README index) carried | TASD §24 | COMPLIANT | One-to-one with the README table; OD-05's "reconciled" status also correctly carried as non-blocking |
| Cross-document section citations (D2, D3-Catalog, D3-Methodology, D4, D5) | TASD, pack-wide | **COMPLIANT (fixed — see §7)** | Was NON-COMPLIANT on citation accuracy only (never on substance); corrected — see Finding Ma-01 |

## 3. Findings

### Finding Ma-01 (Major): Pack-wide stale section cross-references into D2, D3-Catalog, D3-Methodology, D4, D5 — **FIXED**

> **Outcome: fixed.** Every citation below was corrected in `TASD-v1.0.md` by a scripted, context-aware pass (full old→new mapping applied via collision-safe placeholder substitution, verified afterward by an automated scan confirming zero old-numbered citations remain outside the new mapping's valid range, plus a structural check confirming all 28 sections and all 10 Mermaid diagrams are still intact post-edit). No prose, schema, or diagram content was changed — only the bracketed section pointers. Details below are kept as the as-found record of what was wrong before the fix.

**Nature:** Not a contradiction of content. Every rule TASD describes at a given citation is still the correct rule — the citation's *target section number* has simply moved, because the baseline's documentation-cleanup pass (which ran after most of TASD was drafted) renumbered D2, D3-Catalog, D3-Methodology, D4, and D5 throughout. D1 is unaffected: TASD cites D1 almost exclusively by stable ID (`BR-nnn`, `ASM-nn`, `RSK-nn`, `CON-nn`, `OD-nn`), which the cleanup pass did not change.

**Representative mapping (not exhaustive — illustrative of the pattern, which recurs roughly 150 times across the document):**

| TASD's citation | What it describes | Current correct section |
|---|---|---|
| D2 §2 | Four provenance types | D2 §6 |
| D2 §3 | Questionnaire generation logic | D2 §7 |
| D2 §4 / §4a / §4b / §4c / §4d / §4e | Decision engine, Layers 1–3, hard gate, versioning | D2 §8 / §8.1 / §8.2 / §8.3 / §8.4 / §8.5 |
| D2 §5 | Prompt-injection resistance | D2 §9.1 |
| D2 §6 | Authorization-boundary protection | D2 §9.2 |
| D2 §7 | Over-reliance mitigation | D2 §9.3 |
| D3-Catalog §0 | UNVERIFIED validation notice | D3-Catalog §2 |
| D3-Catalog §1 | Mandatory/blocker clarifications | D3-Catalog §5 |
| D3-Methodology §2 / §2.1 / §2.4 | Mapping process, record structure, provenance | D3-Methodology §6 |
| D3-Methodology §4 | Reviewer override mechanism, three-axis table | D3-Methodology §8 / §8.2 / §8.3 |
| D3-Methodology §5 | Conditional-domain trigger table | D3-Methodology §9 |
| D3-Methodology §6 | Organizational policy hooks | D3-Methodology §10 |
| D3-Methodology §6a | EvidenceRequirement structure | D3-Methodology §11 |
| D3-Methodology §7 | Edge cases | D3-Methodology §12 |
| D4 §2 | Readiness dimensions | D4 §5 |
| D4 §3 | Sign-off data model, non-waivable rule | D4 §6 |
| D4 §4 | Who attests | D4 §7 |
| D4 §5.1 / §5.2 | Expiry/revalidation, revocation | D4 §8.2 / §8.3 |
| D5 §2 | RACI | D5 §4 |
| D5 §3 | Approval object data model | D5 §5 |
| D5 §3a | P1–P4 preconditions | D5 §6 |
| D5 §3b | No-override posture | D5 §7 |
| D5 §4 | Evidence validation workflow | D5 §8 |
| D5 §5 / §5.1 / §5.1a / §5.2 / §5.3 / §5.4 / §5.5 | Audit architecture (append-only, durable logging, hash chain, atomicity, verification, external anchoring) | D5 §10 / §10.1 / §10.2 / §10.3 / §10.4 / §10.5 / §10.6 |
| D5 §6 | Separation of duties | D5 §11 |
| D5 §7 | Over-reliance / disagreement rationale | D5 §9 |

**Why this matters enough to report as Major rather than cosmetic:** a reviewer, auditor, or future engineer who opens D5 and looks for "§3a" to verify TASD's P1–P4 claim will not find it — they will find §6 instead, with no forwarding note. At the volume of cross-referencing this document does (it is one of TASD's core strengths, and also therefore the surface area of this defect), a stale citation is not a typo in one place; it is a navigational failure wherever it occurs. Left uncorrected, it would erode confidence in a document that is otherwise unusually careful about tracing every claim to its source.

**Why it is not Critical:** nothing in TASD's own normative content — its schemas, pseudocode, constraints, grants, or stated rules — is wrong. The defect is entirely in the pointer, not the payload. No `[REQ]`-tagged claim in TASD misstates what the baseline requires.

**Distinguishing this from a deliberate placeholder:** this is not a case of TASD leaving something open pending an Open Decision (which TASD does correctly and extensively, e.g. §14.7, §24). It is a sequencing artifact between two pieces of work in this session — TASD was substantially drafted before the baseline cleanup pass renumbered its sections. It requires no design judgment to fix, only a mechanical find-and-replace against the mapping above (and its full extension through every remaining citation in the document).

**Correction applied:** a targeted pass over `TASD-v1.0.md` updated every `D2 §…`, `D3-Catalog §…`, `D3-Methodology §…`, `D4 §…`, and `D5 §…` citation to the current section number, using the mapping tables above as the key. No prose, schema, or diagram content was rewritten — only the bracketed/inline section references. D1 citations required no change (none were stale).

### Finding M-02 (Minor): D3-Catalog `applicability` enum is TASD's own abstraction, not a baseline-defined taxonomy

**Nature:** D3-Catalog §5/§6 (current numbering) expresses each control's conditionality as free-text in a `Status` column ("Not individually mandatory/blocking", "Conditional — scope-triggered", "Conditional — sensitivity/policy-based", "Conditional at control level — only when custom dev is in scope", etc.). TASD §11.3 collapses this into a three-value enum (`AlwaysInDomain`, `ConditionalByScope`, `ConditionalBySensitivityPolicy`). The collapse is reasonable and does not misstate the no-automatic-blocker rule, but it is TASD's own interpretive step — D3-Catalog itself does not define this as a closed taxonomy, and at least one case (A.8.25/SA-11, "conditional at control level — only when custom dev is in scope") sits awkwardly between `ConditionalByScope` and a fourth category D3-Catalog's prose implies but TASD's enum does not name separately.

**Why Minor, not Major:** no business rule depends on this classification being exactly right at the architecture-review stage — D2's Layer 2 does not read `applicability` as a blocker signal (only B-01/B-02 and explicit policy hooks are), so a slightly imprecise categorization here does not create a path to an incorrect `GO`/`NO-GO`. It matters for data-entry correctness once the catalog is seeded, which is exactly when Phase 0's GRC validation (§25, §6.4) is scheduled to happen.

**Proposed correction:** no change to TASD is required now. Flag this enum's values for explicit confirmation as part of Phase 0's D3-Catalog validation task, alongside verifying the identifiers themselves.

### Finding M-03 (Minor): §15.6's "exactly as the baseline's safe default describes" overstates what D3-Methodology says about OD-17's interim state

**Nature:** D3-Methodology §10 (policy hooks, OD-11) explicitly states the interim behavior while unresolved ("treated only as Layer-3 risk-scoring inputs... not gating"). D3-Methodology §11 (evidence sufficiency, OD-17) states only that `sufficiency_criteria` is a policy decision "not invented here" — it does not itself describe an interim behavior the way §10 does for OD-11. TASD §15.6 asserts that `sufficiency_criteria = NULL` meaning "Reviewer judgment alone is the bar" is "exactly as the baseline's safe default describes" — but the baseline does not describe this; TASD infers it.

**Why Minor:** the inference itself is sound and operationally necessary (a `NULL` sufficiency criterion has to mean *something*, and "the Reviewer decides" is the only coherent reading), and it introduces no risk — it does not let an AI-origin judgment substitute for a human one, and it does not weaken any gate. It is flagged only because the review method asks to distinguish a baseline restatement from an architectural inference, and this sentence blurs that line in its own wording.

**Proposed correction:** reword TASD §15.6's closing clause from "exactly as the baseline's safe default describes" to "a reasonable reading of the baseline's deliberately unresolved position, pending OD-17" — a wording-only change, no schema or behavior change.

## 4. Missing Architecture Sections

**None.** All seven areas named in the review brief's §2 — business requirements, AI/human boundary, D3-Catalog verification status, mapping/evidence-review concepts, the seven environment-readiness dimensions and non-waivable rule, D5's P1–P4/transaction safety/audit atomicity, and trust boundaries/database/workflow/engine/security/ADRs/roadmap — are present and substantively covered in `TASD-v1.0.md`. The brief's required ten Mermaid diagrams (system context, high-level architecture, component interaction, database ERD, end-to-end sequence, state machine, approval sequence, audit hash chain, trust boundaries, deployment) are all present (TASD §6.2, §7.2, §8.18, §11.13, §12.2, §12.3, §17.9, §18.0, §10.2, §21.7) and were spot-checked for syntactic validity during this review (balanced subgraph/end pairs, no unescaped special characters in node labels).

## 5. Decisions Requiring Organizational Input

Unchanged from the baseline. This review confirms TASD neither resolves nor silently defaults any of the 21 Open Decisions in `README.md`'s index, and in particular preserves all six blocking decisions exactly as named:

| ID | Decision | TASD's accommodation (not a resolution) |
|---|---|---|
| OD-01 | Approval tier structure | `policy_config.approval_tier_model` reserved `NULL`; single-tier placeholder active |
| OD-06 | Environment Owner role | Role-claim check only; no named individual |
| OD-07 | Evidence validator role | `validator_role` enum extension point; Security-Reviewer-only today |
| OD-10 | Layer 1 completeness threshold | `NULL`-gated; Rule 3 refuses rather than defaults |
| OD-15 | Layer 3 risk weights | `NULL`-gated; Layer 3 cannot run at all until set |
| OD-16 | Layer 3 risk thresholds | `NULL`-gated alongside OD-15 |

The remaining fifteen Open Decisions (OD-02, 03, 04, 05 [reconciled], 08, 09, 11, 12, 14, 17, 18, 19, 20, 21) are likewise carried without modification, each with the safe default or extension point the baseline itself specifies or implies — see TASD §24's full table for the one-to-one mapping.

## 6. Final Recommendation

### **ARCHITECTURE BASELINE ACCEPTABLE, BLOCKED BY ORGANIZATIONAL DECISIONS**

**Basis for this recommendation:** with Ma-01 now corrected (§7), the one defect that would otherwise have warranted "ARCHITECTURE REVISION REQUIRED" no longer exists. Nothing in TASD's actual architecture — its schemas, constraints, grants, transaction design, or engine logic — ever required revision on compliance grounds; the defect was confined to stale section pointers, not substance. M-02 and M-03 remain open as Minor, low-risk items (an interpretive data-modeling choice to confirm during Phase 0's catalog validation, and a wording overstatement with no behavioral consequence) and do not on their own justify withholding acceptance.

The architecture is therefore acceptable as a design. Its implementation — specifically Layer 3 of the decision engine, and the Final Approver/Environment Owner/evidence-validator roles — remains correctly gated on the same six Open Decisions (OD-01, OD-06, OD-07, OD-10, OD-15, OD-16) the Round 5 audit identified as blocking, exactly as `TASD-v1.0.md` §27.1 and `AUDIT-REPORT.md` §6 already state. This recommendation does not imply TASD overstates its own readiness: §27.1's explicit "this document claims architectural completeness and internal consistency; it does not claim the system is ready to build end-to-end today" is itself accurate and is not contradicted by anything in this review.

## 7. Correction Record

| Finding | Action taken | Verification |
|---|---|---|
| Ma-01 | Scripted, placeholder-safe mapping applied to every `D2/D3-Catalog/D3-Methodology/D4/D5 §…` citation in `TASD-v1.0.md`, per the old→new tables in §3 | Automated post-fix scan confirmed zero citations remain pointing at a pre-cleanup section number outside the current documents' valid range; `grep -c '^## [0-9]'` confirmed all 28 top-level sections intact; Mermaid fence count (10 `mermaid` blocks, 66 total code fences) unchanged; file ends correctly at "*End of TASD v1.0.*" |
| M-02 | Not corrected — recommended for confirmation during Phase 0's D3-Catalog GRC validation, not a TASD text change | — |
| M-03 | Not corrected — a one-sentence wording clarification in §15.6 remains open if the organization wants it tightened before wide circulation; no behavioral or schema impact either way | — |
