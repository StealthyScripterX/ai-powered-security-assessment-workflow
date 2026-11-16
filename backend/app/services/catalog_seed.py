"""Seed data transcribed verbatim from docs/baseline/D3-Control-Catalog.md
section 6 (control domains and identifiers). Every row is seeded with
verification_status = Unverified, matching that document's section 2
notice -- nothing here claims catalog validation has occurred.

This is NOT a substitute for the GRC validation task
architecture/TASD-v1.0.md section 25 Phase 0 names; it exists so
`mapping_record.control_id` (Phase 2) has real rows to foreign-key
against. See backend/IMPLEMENTATION-NOTES.md.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.catalog import Control, ControlDomain, ControlSubject, Framework, ScreeningType

_DOMAINS: list[tuple[str, str, ScreeningType, int]] = [
    ("1", "Governance, Risk & Compliance", ScreeningType.MANDATORY, 1),
    ("2", "Data Classification & Test Data Handling", ScreeningType.MANDATORY, 2),
    ("3", "Access Control & Identity Management", ScreeningType.MANDATORY, 3),
    ("4", "Test Environment Isolation & Segregation", ScreeningType.MANDATORY, 4),
    ("5", "Secure Development & Security Testing Practices", ScreeningType.MANDATORY, 5),
    ("6", "Vulnerability & Configuration Management", ScreeningType.MANDATORY, 6),
    ("7a", "Logging, Monitoring & Audit (POC/Test Environment)", ScreeningType.MANDATORY, 7),
    ("7b", "Audit Architecture (Workflow Platform itself)", ScreeningType.NOT_QUESTIONNAIRE, 8),
    ("8", "Cryptography & Network Protection", ScreeningType.MANDATORY, 9),
    ("9", "Third-Party, Cloud & Supply Chain", ScreeningType.CONDITIONAL, 10),
    ("10", "Privacy & PII Protection", ScreeningType.CONDITIONAL, 11),
    ("11", "Incident Response & Contingency", ScreeningType.MANDATORY, 12),
]

# (control_id, framework, title, domain_id, subject, status_note)
_CONTROLS: list[tuple[str, Framework, str, str, ControlSubject, str]] = [
    ("A.5.1", Framework.ISO27001_2022, "Policies for information security", "1", ControlSubject.ORG, "Not individually mandatory/blocking"),
    ("A.5.8", Framework.ISO27001_2022, "Information security in project management", "1", ControlSubject.ORG, "Not individually mandatory/blocking"),
    ("A.5.31", Framework.ISO27001_2022, "Legal, statutory, regulatory and contractual requirements", "1", ControlSubject.TARGET, "Conditional - scope-triggered"),
    ("RA-3", Framework.NIST_SP_800_53_R5, "Risk Assessment", "1", ControlSubject.TARGET, "Not individually mandatory/blocking"),
    ("CA-2", Framework.NIST_SP_800_53_R5, "Control Assessments", "1", ControlSubject.TARGET, "Not individually mandatory/blocking"),

    ("A.5.12", Framework.ISO27001_2022, "Classification of information", "2", ControlSubject.TARGET, "Not individually mandatory/blocking"),
    ("A.8.10", Framework.ISO27001_2022, "Information deletion", "2", ControlSubject.TEST_ENV, "Conditional - sensitivity/policy-based"),
    ("A.8.11", Framework.ISO27001_2022, "Data masking", "2", ControlSubject.TEST_ENV, "Conditional - sensitivity/policy-based"),
    ("A.8.33", Framework.ISO27001_2022, "Test information", "2", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("MP-6", Framework.NIST_SP_800_53_R5, "Media Sanitization", "2", ControlSubject.TEST_ENV, "Conditional - sensitivity/policy-based"),

    ("A.5.15", Framework.ISO27001_2022, "Access control", "3", ControlSubject.ORG, "Not individually mandatory/blocking"),
    ("A.8.2", Framework.ISO27001_2022, "Privileged access rights", "3", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("A.8.3", Framework.ISO27001_2022, "Information access restriction", "3", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("A.8.5", Framework.ISO27001_2022, "Secure authentication", "3", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("AC-2", Framework.NIST_SP_800_53_R5, "Account Management", "3", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("AC-6", Framework.NIST_SP_800_53_R5, "Least Privilege", "3", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),

    ("A.8.31", Framework.ISO27001_2022, "Separation of dev/test/production environments", "4", ControlSubject.TEST_ENV, "Not individually mandatory/blocking (workflow gate is sign-off completeness, BR-018)"),
    ("A.8.22", Framework.ISO27001_2022, "Segregation of networks", "4", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("SC-7", Framework.NIST_SP_800_53_R5, "Boundary Protection", "4", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("CM-2", Framework.NIST_SP_800_53_R5, "Baseline Configuration", "4", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),

    ("A.8.29", Framework.ISO27001_2022, "Security testing in development and acceptance", "5", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("A.8.34", Framework.ISO27001_2022, "Protection of information systems during audit testing", "5", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("CA-8", Framework.NIST_SP_800_53_R5, "Penetration Testing", "5", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("A.8.25", Framework.ISO27001_2022, "Secure development life cycle", "5", ControlSubject.TARGET, "Conditional at control level - only when custom dev is in scope"),
    ("SA-11", Framework.NIST_SP_800_53_R5, "Developer Testing and Evaluation", "5", ControlSubject.TARGET, "Conditional at control level - only when custom dev is in scope"),

    ("A.8.8", Framework.ISO27001_2022, "Management of technical vulnerabilities", "6", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("A.8.9", Framework.ISO27001_2022, "Configuration management", "6", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("RA-5", Framework.NIST_SP_800_53_R5, "Vulnerability Monitoring and Scanning", "6", ControlSubject.TEST_ENV, "Conditional - scope/sensitivity/policy; never automatic"),
    ("SI-2", Framework.NIST_SP_800_53_R5, "Flaw Remediation", "6", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),

    ("A.8.15", Framework.ISO27001_2022, "Logging", "7a", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("A.8.16", Framework.ISO27001_2022, "Monitoring activities", "7a", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("AU-2", Framework.NIST_SP_800_53_R5, "Event Logging", "7a", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),

    ("AU-9", Framework.NIST_SP_800_53_R5, "Protection of Audit Information", "7b", ControlSubject.PLATFORM, "Governs this system's own audit store (BR-017/BR-019)"),

    ("A.8.24", Framework.ISO27001_2022, "Use of cryptography", "8", ControlSubject.TEST_ENV, "Conditional - scope/sensitivity; not automatic for every POC"),
    ("SC-8", Framework.NIST_SP_800_53_R5, "Transmission Confidentiality and Integrity", "8", ControlSubject.TEST_ENV, "Conditional - same basis"),
    ("SC-28", Framework.NIST_SP_800_53_R5, "Protection of Information at Rest", "8", ControlSubject.TEST_ENV, "Conditional - same basis"),

    ("A.5.19", Framework.ISO27001_2022, "Information security in supplier relationships", "9", ControlSubject.TARGET, "Conditional"),
    ("A.5.23", Framework.ISO27001_2022, "Information security for use of cloud services", "9", ControlSubject.TARGET, "Conditional"),
    ("SA-9", Framework.NIST_SP_800_53_R5, "External System Services", "9", ControlSubject.TARGET, "Conditional"),

    ("A.5.34", Framework.ISO27001_2022, "Privacy and protection of PII", "10", ControlSubject.TARGET, "Conditional - PII presence; not an automatic blocker by itself"),
    ("PT-2", Framework.NIST_SP_800_53_R5, "Authority to Process PII", "10", ControlSubject.TARGET, "Conditional - same basis"),

    ("A.5.24", Framework.ISO27001_2022, "Incident management planning and preparation", "11", ControlSubject.ORG, "Not individually mandatory/blocking"),
    ("A.8.13", Framework.ISO27001_2022, "Information backup", "11", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
    ("IR-4", Framework.NIST_SP_800_53_R5, "Incident Handling", "11", ControlSubject.ORG, "Not individually mandatory/blocking"),
    ("CP-9", Framework.NIST_SP_800_53_R5, "System Backup", "11", ControlSubject.TEST_ENV, "Not individually mandatory/blocking"),
]


async def seed_catalog_if_empty(db: AsyncSession) -> None:
    existing = await db.execute(select(ControlDomain.id).limit(1))
    if existing.first() is not None:
        return  # already seeded

    for domain_id, name, screening, sequence in _DOMAINS:
        db.add(ControlDomain(id=domain_id, name=name, screening=screening, sequence=sequence))
    await db.flush()

    for control_id, framework, title, domain_id, subject, status_note in _CONTROLS:
        db.add(
            Control(
                control_id=control_id,
                framework=framework,
                title=title,
                domain_id=domain_id,
                subject=subject,
                status_note=status_note,
            )
        )
    await db.commit()
