# D1 — Project Requirements Document

**Status:** APPROVED AND FROZEN (v1.0)
**Project:** AI-Powered Security Assessment & POC Approval Workflow

> This document is preserved unchanged from its approved baseline. No content below was altered during the one-go documentation run. If a contradiction with D2–D5 was found during drafting, it is reported in `AUDIT-REPORT.md`, not silently patched here.

## 1. Project Overview

The organization requires a governed intake and evaluation mechanism for Proof-of-Concept (POC) and pilot security testing requests. Requesters often have no pre-existing security documentation and no security background, so the system itself generates the assessment artifacts from what they submit — explicitly marking every assumption it makes and every piece of evidence that is missing, rather than silently filling gaps.

An AI agent analyzes the submitted scope, generates 11–15 scope-specific questions, maps responses to specific ISO/IEC 27001:2022 Annex A and NIST SP 800-53 Rev. 5 control identifiers, evaluates Security Test Environment readiness against a dedicated SOP, and produces one of three outcomes — **GO**, **NO-GO**, or **Insufficient Information / Incomplete Assessment** — using a documented, deterministic decision engine. This recommendation is advisory only. A human Approver holds sole authority to authorize testing. Every transition is recorded atomically with its audit event in an append-only, cryptographically chained audit trail.

## 2. Business Problem

- **BP-01:** Requesters often lack the security background to know what information a reviewer needs, and often have no formal security documentation.
- **BP-02:** Manual control mapping is slow and inconsistent across reviewers.
- **BP-03:** Security Test Environment readiness is often assumed rather than verified.
- **BP-04:** Approval decisions and rationale are not consistently or durably documented.
- **BP-05:** No standardized distinction exists between a claim, submitted material, and human-validated evidence.

## 3. Objectives

| ID | Objective |
|---|---|
| OBJ-01 | Reduce time/effort to triage a POC security request. |
| OBJ-02 | Standardize mapping to specific ISO/NIST control identifiers. |
| OBJ-03 | Make evidence state (validated vs. claimed vs. absent) explicit everywhere. |
| OBJ-04 | Preserve human authority over all authorization decisions. |
| OBJ-05 | Produce a complete, tamper-evident audit trail. |
| OBJ-06 | Make Security Test Environment readiness an explicit, unbypassable gate. |
| OBJ-07 | Ensure the AI never forces GO/NO-GO when information is inadequate; use a deterministic decision engine. |

## 4. Stakeholders

| Role | Responsibility | Decision Authority |
|---|---|---|
| Requester | Submits scope, answers questionnaire, supplies material | None |
| AI Agent (system actor) | Generates questions, mapping, artifacts, recommendation | **No authorization authority** |
| Security Reviewer / GRC Analyst | Validates mapping; performs "Human Validated" evidence sign-off | Recommends; cannot authorize |
| Final Approver *(tier structure — OD-01)* | Reviews and issues binding decision | **Sole authorization authority** |
| Environment Owner *(role assignment — OD-06)* | Signs off on environment readiness | Sign-off required; not an authorization role |
| Compliance / Audit Reviewer | Reads audit trail | Read-only |
| System/Platform Owner | Owns the tool | Administrative only |

## 5. Scope and Exclusions

**In scope:** no-documentation-required intake; AI questionnaire (11–15 Qs); AI-generated assessment artifacts with assumptions/gaps marked; specific ISO/NIST control-identifier mapping; four-state evidence model; SOP-based environment readiness; three-outcome deterministic recommendation; human approval workflow; append-only hash-chained atomic audit trail.

**Out of scope (this phase):** live CMDB/scanner integration (OD-02); AI authorization of any kind; auto-verification of uploads; code/architecture/build; multi-tenant productization (OD-03); external cryptographic anchoring of the audit chain (OD-09).

## 6. Data Sensitivity Summary

| Data category | Sensitivity |
|---|---|
| Submitted scope text | Internal/Confidential |
| Questionnaire responses | Internal/Confidential |
| Uploaded material | Confidential; never auto-verified |
| Control mapping & gap analysis | Confidential |
| Approval decisions & rationale | Internal/Confidential, retained for audit |
| Audit trail | Confidential, restricted write access |

## 7. End-to-End Business Workflow

```
1.  Scope Submission
2.  AI Scope Analysis
3.  Dynamic Questionnaire Generation (11-15 Qs, informed by control catalog)
4.  Questionnaire Response Collection
5.  AI generates assessment artifacts (assumptions/gaps marked)
6.  ISO 27001:2022 / NIST 800-53 Control Mapping (specific identifiers)
7.  Security Assessment — four-state evidence classification
8.  Security Test Environment Readiness Assessment (SOP + Environment Owner sign-off)
9.  Decision Engine, fixed order:
    a. Completeness Check -> Insufficient Information if inadequate
    b. Mandatory Security Blockers (incl. incomplete sign-off) -> NO-GO if tripped
    c. Risk Scoring -> GO or risk-tiered outcome, only if (a) and (b) pass
10. POC Approval Request Creation
11. Human Approval Workflow (Approve / Reject / Request More Information)
12. Audit Trail Entry at every transition, atomic with the transition itself
```

## 8. Business Requirements

| ID | Requirement |
|---|---|
| BR-001 | Submit scope without pre-existing security documentation. |
| BR-002 | Generate 11–15 scope-specific questions. |
| BR-003 | Ensure mandatory-domain coverage; exclude irrelevant questions. |
| BR-004 | Map to specific ISO Annex A / NIST 800-53 Rev.5 control identifiers, not families. |
| BR-005 | Four evidence states: Not Provided / Submitted–Pending Review / Verified–Human Validated / Rejected–Insufficient Evidence. |
| BR-005a | Uploads default to Submitted–Pending Review; never auto-Verified. |
| BR-006 | Evidence/blocker rules defined separately from, and not auto-inflating, risk score. |
| BR-007 | Environment readiness assessed per SOP (D4), incl. mandatory Environment Owner sign-off. |
| BR-008 | AI generates assessment artifacts from submitted info, marking assumptions/missing evidence. |
| BR-009 | Exactly three outcomes: GO / NO-GO / Insufficient Information — advisory only. |
| BR-009a | AI never forced into GO/NO-GO when information is inadequate. |
| BR-010 | AI recommendation never constitutes authorization. |
| BR-011 | POC Approval Request contains scope, responses, mapping, evidence states, recommendation. |
| BR-012 | Only a designated human Approver may issue a binding decision. |
| BR-013 | Audit entry for every workflow transition. |
| BR-014 | Audit trail readable by Compliance/Audit without workflow action authority. |
| BR-015 | AI-generated vs. human-authored content distinguished everywhere. |
| BR-016 | Decision engine: fixed order Completeness -> Blockers -> Risk Scoring; deterministic, documented, not open-ended model judgment. |
| BR-017 | Audit trail: append-only, hash-chained, tamper-evident; periodic integrity verification (owner/schedule — OD-08). |
| BR-018 | GO structurally unreachable unless Environment Owner sign-off complete AND no Mandatory Security Blocker unresolved. |
| BR-019 | Workflow transition and its audit event persist atomically; failed audit write blocks the transition. |

## 9. Success Criteria and KPIs

Time-to-recommendation reduction (baseline TBD, OD-04); mapping consistency across similar scopes; 100% human-reviewed "Verified" items; 100% approval decisions with rationale; 100% audit completeness/atomicity; 0% GO issued with incomplete sign-off or unresolved blocker; 100% decision-layer attribution logged.

## 10. Assumptions and Dependencies

ASM-01: readiness assessed via questionnaire/attachment only this phase.
ASM-02: single-enterprise volume (tens–low hundreds/year).
ASM-03: org will designate a specific-identifier control catalog subset.

**Document dependency chain:**
`D1 → D3-Catalog → D2 → D3-Methodology → D4 (depends on D3-Catalog AND D3-Methodology) → D5`

## 11. Constraints and Risks

CON-01: AI never authorizes, enforced structurally. CON-02: fixed 11–15 questions; genuine inadequacy routes to Insufficient Information.
RSK-01 reviewer over-reliance on AI; RSK-02 overconfident mapping; RSK-03 scope/answer manipulation; RSK-04 blocker-rule correctness now load-bearing for GO-gating; RSK-05 system itself is a sensitive-data target; RSK-06 AI artifacts mistaken for authoritative docs; RSK-07 infrequent integrity verification; RSK-08 atomic persistence availability trade-off.

## 12. Open Decisions

| ID | Decision |
|---|---|
| OD-01 | Approval tier structure (single / risk-tiered / fixed multi-stage) |
| OD-02 | Long-term environment-readiness integration scope |
| OD-03 | Single-enterprise vs. future multi-tenant |
| OD-04 | No current triage-time baseline |
| OD-05 | Detailed evidence/blocker rule sets (deferred to D2/D3-Methodology) |
| OD-06 | Who holds "Environment Owner" |
| OD-07 | Who is authorized to perform "Verified – Human Validated" sign-off |
| OD-08 | Audit integrity-verification schedule/owner |
| OD-09 | Whether external cryptographic anchoring is required this phase |
