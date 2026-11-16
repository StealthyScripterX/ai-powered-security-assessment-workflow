# architecture/ — Technical Architecture & System Design

## Purpose

This directory holds the Technical Architecture & System Design (TASD) deliverable for the AI-Powered Security Assessment & POC Approval Workflow project — the phase following the frozen Round 5 documentation baseline in `docs/baseline/`.

This is a **design-only** deliverable. It contains no application source code, no package installation, no API implementation. Its job is to translate the approved requirements and governance rules in `docs/baseline/` into a concrete, implementable system design: components, data model, workflow, AI architecture, decision-engine logic, security architecture, API shape, deployment topology, testing strategy, and a phased build roadmap.

## Document index

| File | Contents |
|---|---|
| [`TASD-v1.0.md`](./TASD-v1.0.md) | The full Technical Architecture & System Design document — 28 sections, 10 Mermaid diagrams, covering system context through glossary |
| [`OPEN-DECISIONS.md`](./OPEN-DECISIONS.md) | Concise summary of the six **blocking** Open Decisions (OD-01, OD-06, OD-07, OD-10, OD-15, OD-16) and the architectural areas each affects |
| `README.md` | This file |

## Version information

| Field | Value |
|---|---|
| Document version | v1.0 |
| Status | Draft, for stakeholder architecture review |
| Date | 2026-11-12 |
| Baseline consumed | `docs/baseline/` — D1, D2, D3-Catalog, D3-Methodology, D4, D5, README, Consolidated Audit Report (Round 5 Final), as they stood when this architecture was authored |

## Relationship to the frozen baseline

`docs/baseline/` is treated as frozen, authoritative source material throughout `TASD-v1.0.md`. **This architecture work does not modify any file in `docs/baseline/`.** Every normative statement in `TASD-v1.0.md` is tagged `[REQ]` (traced to a baseline requirement), `[ARCH]` (this document's own proposed design), `[ASM]` (an assumption requiring stakeholder confirmation), or `[OD-nn]` (an unresolved organizational decision carried from the baseline, not resolved here) — see `TASD-v1.0.md` §1.1 for the full legend and §5 for the section-by-section traceability matrix back to specific business requirements (BR-001–BR-019) and Round 5 audit findings.

This architecture does not reopen, re-litigate, or silently resolve any of the baseline's unresolved Open Decisions. It parameterizes the design so each decision can be supplied later as configuration (`policy_config`, role-mapping configuration, etc.) without a schema or architecture rewrite — see `OPEN-DECISIONS.md` and `TASD-v1.0.md` §24.

**Implementation readiness:** per the Round 5 audit's verdict (`docs/baseline/AUDIT-REPORT.md` §6), the project is **NOT READY FOR IMPLEMENTATION**, and this architecture does not change that verdict — the blocking gaps are organizational, not technical. See `TASD-v1.0.md` §27.1 for the precise, architecture-level restatement of what that means for what can and cannot be built today.
