# D4 — Security Test Environment Readiness SOP

**Status:** Draft, incorporated into one-go pack.
**Depends on:** D2, D3-Catalog, D3-Methodology.

## 1. Purpose

Defines what "ready" means for a Security Test Environment before a POC may proceed, and the structured sign-off mechanism that D2's decision engine treats as a hard precondition for GO (BR-018).

## 2. Readiness Dimensions

Each dimension below maps to D3-Catalog Domain 4 (Isolation), Domain 2 (Test Data), Domain 6 (Vulnerability/Config), Domain 7a (Logging), Domain 8 (Crypto, conditional), and Domain 11 (Backup/Recovery).

| Dimension | What is attested | Related controls (D3-Catalog) |
|---|---|---|
| Isolation | The environment is logically/physically separated from production; network segregation is in place | A.8.31, A.8.22, SC-7 |
| Access Control | Only named POC participants have access; privileged accounts are tracked | A.8.2, A.8.3, AC-2, AC-6 |
| Test Data Handling | Test data is classified; masking/sanitization applied where required by policy | A.8.33, A.8.11, MP-6 |
| Configuration Baseline | Environment build follows a known, documented baseline | A.8.9, CM-2 |
| Logging | Environment-level logging is active and will capture POC activity | A.8.15, AU-2 |
| Backup & Rollback | A backup exists prior to testing; a rollback procedure is defined and tested | A.8.13, CP-9 |
| Decommissioning Plan | A defined end-state exists for tearing down/reverting the environment after the POC | A.8.10 (deletion), A.8.13 (backup) |

Encryption (A.8.24/SC-8/SC-28) and vulnerability scanning (RA-5) are **not** listed as mandatory readiness dimensions here — per D1/D3-Methodology, their applicability is scope/sensitivity/policy-conditional (D3-Methodology §6, policy hooks PH-01/PH-02) and is evaluated in Risk Scoring (D2 §4c), not asserted as a universal readiness gate.

## 3. Sign-Off Data Model

**Correction (consolidated audit, round 2 — Finding 2):** round 1 of this audit added a `secondary_cosign_id` field and treated a co-signature as sufficient to let an exception count toward completeness. On further review, a second *signature* is not the same thing as a second *judgment that the risk is acceptable* — someone can co-sign without the exception being resolved, compensated for, or even fully understood. The model below replaces the bare co-sign with a full exception record: the unresolved issue, a risk assessment, compensating controls, an explicit disposition, a remediation owner/deadline, and an expiry — and names which dimensions can never be waived into a GO at all, regardless of disposition.

```
EnvironmentReadinessAttestation {
  poc_request_id
  dimension: enum[Isolation, AccessControl, TestData, ConfigBaseline,
                   Logging, BackupRollback, Decommissioning]
  status: enum[Not Started, In Progress, Attested, Attested-with-Exception]
  attestation_text: string         // structured, not free-form narrative only
  environment_owner_id: ref(User)
  timestamp
  supporting_evidence: EvidenceRef[]   // round 5 — made explicit: zero or more
                                        // references to files or artifacts the
                                        // Environment Owner attaches in support
                                        // of this attestation (e.g., a network
                                        // diagram evidencing Isolation, a config
                                        // export evidencing ConfigBaseline). May
                                        // be empty. Distinct from the POC's own
                                        // control evidence (D1 BR-005) — this is
                                        // evidence for the *environment's*
                                        // readiness claim, not for a specific
                                        // ISO/NIST control mapping.
  exception: ExceptionRecord | null   // required if status = Attested-with-Exception;
                                       // null for Attested or non-exception states
}

ExceptionRecord {
  issue_description: string           // the exact unresolved condition, specific
                                       // to this dimension — not a generic note
  risk_assessment: string             // what could go wrong as a result, in this
                                       // POC's specific context
  compensating_controls: string[]     // what is being done instead to reduce the
                                       // risk (may be empty if none exist — an
                                       // empty list is itself informative)
  disposition: enum[Accepted, Rejected, Deferred]
  disposition_authorized_by: ref(User)   // must be a Security Reviewer or Final
                                          // Approver; never the Environment Owner
                                          // (who raised the exception) and never
                                          // the AI agent
  disposition_rationale: string       // required; a bare "approved" is rejected
                                       // by validation, not merely discouraged
  remediation_owner: ref(User) | null     // required if disposition = Accepted
  remediation_deadline: date | null       // required if disposition = Accepted
  expiry_date: date                       // required for every exception, incl.
                                           // Rejected/Deferred — bounds how long a
                                           // disposition is valid before
                                           // revalidation is mandatory
  created_at
  revoked: boolean                        // see §5.1 (Revocation)
  revoked_by: ref(User) | null
  revoked_at: timestamp | null
}

EnvironmentReadinessSignOff {
  poc_request_id
  all_dimensions_status: derived
  environment_owner_id: ref(User)
  final_signoff_timestamp
  final_signoff_boolean          // see computation rule below
}
```

**Non-waivable dimensions:** `Isolation` and `Access Control` can never reach a disposition of `Accepted`. These two dimensions are structurally what BR-018's "mandatory prerequisite" exists to protect — an unisolated or uncontrolled-access environment is not a reduced-risk POC, it is a different, unapproved activity. An exception on either dimension may only be disposed `Rejected` or `Deferred`, both of which keep `final_signoff_boolean = false`. **This is enforced as a write-time validation rule, not merely a documented convention** — a `disposition_authorized_by` action attempting `Accepted` on `Isolation` or `AccessControl` is rejected by the data layer, mirroring how D5 §3a enforces P1–P3 at the approval step; the same "server-side, not just role-trust" principle applies here. **Open Decision OD-18:** whether the organization wants to extend this non-waivable list to any other dimension (e.g., Backup & Rollback) — the two listed here are the structural minimum derived directly from D1's non-negotiables, not a complete policy position.

**`final_signoff_boolean` computation rule (feeds D2 §4b, B-01):** `true` if and only if every dimension is either `Attested` outright, **or** `Attested-with-Exception` with `exception.disposition = Accepted` on a *waivable* dimension, `exception.revoked = false`, and `exception.expiry_date` not yet passed. Any dimension in `Not Started`/`In Progress`, any exception disposed `Rejected`/`Deferred`, any exception on a non-waivable dimension, any revoked exception, or any expired exception forces `final_signoff_boolean = false` — which correctly routes through Layer 2 Blocker B-01 (NO-GO) rather than through to Layer 3 scoring.

## 4. Who Attests

Per D1 Open Decision **OD-06**, the specific person/role holding "Environment Owner" is not yet named by the organization. This SOP requires that whoever holds the role:
- Is not the Requester (separation of duties — the person proposing the POC should not self-attest that its environment is ready).
- Is not the AI agent (structural — AI has no write access to this object, consistent with D2 §6).
- Has the technical standing to actually know the environment's isolation/access/config state (an administrative role with no technical visibility into the environment would make attestation meaningless).

**Actor identity enforcement (MINOR correction, round 3):** `environment_owner_id`, `disposition_authorized_by`, and `revoked_by` are never accepted as values supplied in a request payload — each is populated by the server from the authenticated identity making the call (D2 §6). An Environment Owner cannot submit an attestation on another user's behalf, and the role checks above (not the Requester, not the AI agent) are enforced against that server-derived identity, not a claimed one.

## 5. Rollback & Decommissioning Requirements

- A rollback point (backup or equivalent) must exist and be referenced in the `BackupRollback` dimension **before** testing begins, not created reactively after an incident.
- A decommissioning target date or trigger condition must be stated at sign-off time; the environment's existence beyond that point without a renewed attestation is itself a finding for the next audit-trail review cycle (mechanism: outside this SOP's scope — a scheduling/monitoring concern for the platform's operational design, not a documentation gap here).

### 5.1 Exception Expiry & Revalidation (Finding 2 / Finding 6.1)

- Every `ExceptionRecord.expiry_date` (§3) must be reached or exceeded for the exception to automatically stop counting toward sign-off — at that point `final_signoff_boolean` recomputes to `false` without requiring anyone to notice and manually intervene (this is a computed property, not a manually-maintained flag, to avoid relying on someone remembering to check).
- Before expiry, the `remediation_owner` (required on any `Accepted` disposition) is expected to resolve the underlying issue or request a new attestation cycle. What happens if the deadline passes with no remediation is an operational escalation question — **Open Decision OD-19** (e.g., auto-notify Compliance/Audit vs. auto-revoke) — not decided here.

### 5.2 Revocation

- A Security Reviewer, Final Approver, or the Environment Owner may revoke any `Attested` or `Attested-with-Exception` dimension at any time the underlying condition is known to have changed (e.g., an isolation control that was working is found to have failed) — never the AI agent, consistent with D2 §6.
- Revocation sets `revoked = true`, `revoked_by`, `revoked_at`, and immediately recomputes `final_signoff_boolean` to `false` for the POC request.
- **Defense in depth (ties to D5's precondition enforcement and D2 §4e versioning):** a revocation is itself an invalidating change under D2 §4e (item 5, round 4 renumbering) — it increments `AssessmentInputVersion.version`, which makes any existing `Recommendation` stale regardless of when the revocation happens relative to recommendation generation. Combined with D5 §3a's P1 and P4 checks at commit time, a revocation that occurs after a GO recommendation was produced — but before an Approver's decision is committed — is caught twice over: once by P1 (sign-off no longer complete) and once by P4 (recommendation now stale). **Open Decision OD-20:** what happens if revocation occurs *after* an Approval decision has already been committed and testing may have started (e.g., halt testing immediately vs. flag for urgent review) is an operational incident-response question, not resolved in this document — the versioning and precondition machinery only guarantees the *approval step itself* cannot be bypassed; it does not define post-approval incident handling.

## 6. Open Decisions Carried / Arising Here

| ID | Decision |
|---|---|
| OD-06 | Who formally holds "Environment Owner" (carried from D1) |
| OD-02 | Whether readiness verification moves beyond attestation to live integration (carried from D1) |
| OD-18 *(new)* | Whether to extend the non-waivable dimension list beyond Isolation/Access Control |
| OD-19 *(new)* | Escalation behavior when a remediation deadline passes unresolved |
| OD-20 *(new)* | Post-approval revocation handling (testing already underway) |

~~OD-13 (whether Attested-with-Exception needs a co-sign) — superseded during round 2 of the audit: a bare co-sign was found insufficient (Finding 2) and replaced by the full ExceptionRecord/disposition model in §3. No longer tracked as its own decision.~~
