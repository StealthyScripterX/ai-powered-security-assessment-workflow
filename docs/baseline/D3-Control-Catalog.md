# D3-Catalog — Applicable Control Domains & Identifiers

## 1. Document Control

| Field | Value |
|---|---|
| Document ID | D3-Catalog |
| Title | Security Control Catalog |
| Project | AI-Powered Security Assessment & POC Approval Workflow |
| Status | Draft — incorporated into documentation baseline |
| Depends on | D1 |

## 2. Validation Notice — READ BEFORE USE

> **This entire catalog is flagged UNVERIFIED.** NIST baseline: **NIST SP 800-53, Revision 5**. ISO baseline: **ISO/IEC 27001:2022 Annex A**, as detailed in ISO/IEC 27002:2022. All identifiers and titles below are drawn from general knowledge of each standard's structure, **not a verbatim licensed copy**, and are **unverified against the authoritative texts**. This catalog requires review by a GRC/compliance owner with access to the official ISO and NIST publications before any control identifier here is treated as authoritative. No control ID, title, or ISO↔NIST pairing in this document has been validated against licensed standards text.

## 3. Purpose

Defines the static reference set of ISO/IEC 27001:2022 Annex A and NIST SP 800-53 Rev. 5 control identifiers organized by domain, tagged by Control Subject, for use by the questionnaire generator (D2 §7), the mapping methodology (D3-Methodology), and the environment readiness SOP (D4).

## 4. Scope

Covers eleven control domains (nine Mandatory-screening, two Conditional-screening). Does not itself determine blocker status for any individual control — see §5 for the governing clarification.

## 5. Clarifications

- **Mandatory** = the *domain* always receives question/screening coverage (BR-003). It does **not** mean every control in the domain is individually mandatory, and **no control in this catalog is, by itself, an automatic approval blocker**. Blocker determination belongs to D2's decision engine and D3-Methodology's rules, applied against scope, data sensitivity, and documented organizational policy.
- ISO Annex A and NIST 800-53 controls paired in the same domain row are a **thematic grouping for questionnaire design**, not a declared crosswalk or one-to-one equivalence.
- **Control Subject** tags: **Org** (organization governance), **Target** (POC target system), **TestEnv** (Security Test Environment), **Platform** (this workflow system's own architecture).

## 6. Control Domains

### 6.1 Domain 1 — Governance, Risk & Compliance *(Mandatory screening)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.5.1 | Policies for information security | Org | Not individually mandatory/blocking |
| ISO | A.5.8 | Information security in project management | Org | Not individually mandatory/blocking |
| ISO | A.5.31 | Legal, statutory, regulatory and contractual requirements | Target | Conditional — scope-triggered |
| NIST | RA-3 | Risk Assessment | Target | Not individually mandatory/blocking |
| NIST | CA-2 | Control Assessments | Target | Not individually mandatory/blocking |

### 6.2 Domain 2 — Data Classification & Test Data Handling *(Mandatory screening)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.5.12 | Classification of information | Target | Not individually mandatory/blocking |
| ISO | A.8.10 | Information deletion | TestEnv | Conditional — sensitivity/policy-based |
| ISO | A.8.11 | Data masking | TestEnv | Conditional — sensitivity/policy-based |
| ISO | A.8.33 | Test information | TestEnv | Not individually mandatory/blocking |
| NIST | MP-6 | Media Sanitization | TestEnv | Conditional — sensitivity/policy-based |

### 6.3 Domain 3 — Access Control & Identity Management *(Mandatory screening)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.5.15 | Access control | Org | Not individually mandatory/blocking |
| ISO | A.8.2 | Privileged access rights | TestEnv | Not individually mandatory/blocking |
| ISO | A.8.3 | Information access restriction | TestEnv | Not individually mandatory/blocking |
| ISO | A.8.5 | Secure authentication | TestEnv | Not individually mandatory/blocking |
| NIST | AC-2 | Account Management | TestEnv | Not individually mandatory/blocking |
| NIST | AC-6 | Least Privilege | TestEnv | Not individually mandatory/blocking |

### 6.4 Domain 4 — Test Environment Isolation & Segregation *(Mandatory screening — feeds D4 directly)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.8.31 | Separation of dev/test/production environments | TestEnv | Not individually mandatory/blocking (the workflow gate is sign-off completeness, BR-018 — not this control by name) |
| ISO | A.8.22 | Segregation of networks | TestEnv | Not individually mandatory/blocking |
| NIST | SC-7 | Boundary Protection | TestEnv | Not individually mandatory/blocking |
| NIST | CM-2 | Baseline Configuration | TestEnv | Not individually mandatory/blocking |

### 6.5 Domain 5 — Secure Development & Security Testing Practices *(Mandatory screening)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.8.29 | Security testing in development and acceptance | TestEnv | Not individually mandatory/blocking |
| ISO | A.8.34 | Protection of information systems during audit testing | TestEnv | Not individually mandatory/blocking |
| NIST | CA-8 | Penetration Testing | TestEnv | Not individually mandatory/blocking |
| ISO | A.8.25 | Secure development life cycle | Target | **Conditional at control level** — only when custom dev is in scope |
| NIST | SA-11 | Developer Testing and Evaluation | Target | **Conditional at control level** — only when custom dev is in scope |

### 6.6 Domain 6 — Vulnerability & Configuration Management *(Mandatory screening)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.8.8 | Management of technical vulnerabilities | TestEnv | Not individually mandatory/blocking |
| ISO | A.8.9 | Configuration management | TestEnv | Not individually mandatory/blocking |
| NIST | RA-5 | Vulnerability Monitoring and Scanning | TestEnv | **Conditional — scope/sensitivity/policy; never automatic** |
| NIST | SI-2 | Flaw Remediation | TestEnv | Not individually mandatory/blocking |

### 6.7 Domain 7a — Logging, Monitoring & Audit (POC/Test Environment) *(Mandatory screening)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.8.15 | Logging | TestEnv | Not individually mandatory/blocking |
| ISO | A.8.16 | Monitoring activities | TestEnv | Not individually mandatory/blocking |
| NIST | AU-2 | Event Logging | TestEnv | Not individually mandatory/blocking |

### 6.8 Domain 7b — Audit Architecture (Workflow Platform itself) *(not a questionnaire domain)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| NIST | AU-9 | Protection of Audit Information | **Platform** | Governs this system's own audit store (BR-017/BR-019); full specification lives in D5, not duplicated here |

### 6.9 Domain 8 — Cryptography & Network Protection *(Mandatory screening)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.8.24 | Use of cryptography | TestEnv | **Conditional — scope/sensitivity; not automatic for every POC** |
| NIST | SC-8 | Transmission Confidentiality and Integrity | TestEnv | Conditional — same basis |
| NIST | SC-28 | Protection of Information at Rest | TestEnv | Conditional — same basis |

### 6.10 Domain 9 — Third-Party, Cloud & Supply Chain *(Conditional screening — vendor/cloud triggered)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.5.19 | Information security in supplier relationships | Target | Conditional |
| ISO | A.5.23 | Information security for use of cloud services | Target | Conditional |
| NIST | SA-9 | External System Services | Target | Conditional |

### 6.11 Domain 10 — Privacy & PII Protection *(Conditional screening, high-weight when triggered)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.5.34 | Privacy and protection of PII | Target | **Conditional — PII presence; not an automatic blocker by itself** |
| NIST | PT-2 | Authority to Process PII | Target | Conditional — same basis |

### 6.12 Domain 11 — Incident Response & Contingency *(Mandatory screening)*

| Fw | ID | Title | Subject | Status |
|---|---|---|---|---|
| ISO | A.5.24 | Incident management planning and preparation | Org | Not individually mandatory/blocking |
| ISO | A.8.13 | Information backup | TestEnv | Not individually mandatory/blocking |
| NIST | IR-4 | Incident Handling | Org | Not individually mandatory/blocking |
| NIST | CP-9 | System Backup | TestEnv | Not individually mandatory/blocking |

## 7. Summary

9 Mandatory screening domains (1, 2, 3, 4, 5, 6, 7a, 8, 11); 2 Conditional screening domains (9, 10). Individually-conditional controls exist inside Mandatory domains (A.8.25/SA-11, RA-5, A.8.24/SC-8/SC-28, A.5.34/PT-2) — none are automatic blockers. AU-9 is the only Platform-subject control enumerated here; the rest of the platform's self-security controls belong to D5. No ISO↔NIST crosswalk is claimed anywhere in this document.

## 8. Dependencies and Related Documents

Depended on by D2 (questionnaire domain coverage), D3-Methodology (mapping target identifiers), and D4 (readiness-dimension control references).

## 9. Assumptions and Constraints

Per D1 ASM-03, the organization will designate the specific-identifier subset this catalog should ultimately reflect. Until then, this catalog's content is illustrative of structure and coverage, not a confirmed final list.

## 10. Open Decisions

None raised directly by this document. Its UNVERIFIED status (§2) is a validation task for a GRC/compliance owner, not an Open Decision requiring an organizational policy choice.

## 11. References

D1 — Project Requirements Document. `README.md` for the consolidated Open Decisions index.

## 12. Revision History

| Version | Status | Notes |
|---|---|---|
| v1.0 | Draft, incorporated | Formatting and structure revised for publication; no control identifier, title, domain assignment, or ISO↔NIST pairing was added, removed, or altered. The UNVERIFIED notice (§2) is preserved verbatim in substance and remains prominent. |
