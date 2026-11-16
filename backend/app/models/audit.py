"""Append-only, hash-chained audit entry.

architecture/TASD-v1.0.md section 18.1/18.2: SHA-256 over a canonically
serialized entry_content, chained to the previous entry's hash. Append
privilege is enforced at the application layer in this phase (no database
role/grant separation yet -- that requires the privileged-role model in
section 11.10, deferred to a later phase with a real multi-role deployment).
What IS enforced now, and is this phase's actual non-negotiable: every
state-changing write in app/services goes through
app.services.audit_service.record_event inside the SAME database
transaction as the state change it describes (BR-019) -- see
app/services/audit_service.py.
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ActorKind(str, enum.Enum):
    REQUESTER = "Requester"
    SECURITY_REVIEWER = "SecurityReviewer"
    ENVIRONMENT_OWNER = "EnvironmentOwner"
    FINAL_APPROVER = "FinalApprover"
    COMPLIANCE_AUDITOR = "ComplianceAuditor"
    PLATFORM_OWNER = "PlatformOwner"
    AI_AGENT = "AIAgent"
    DECISION_ENGINE = "DecisionEngine"
    SYSTEM = "System"


class AuditEntry(Base):
    __tablename__ = "audit_entry"

    # Integer (not BigInteger) is required for SQLite to alias this column
    # to its ROWID and actually auto-increment it; on PostgreSQL this
    # would become SERIAL/BIGSERIAL via a migration-time type override --
    # noted in IMPLEMENTATION-NOTES.md since architecture/TASD-v1.0.md
    # section 11.6 specifies BIGINT for this column.
    sequence_number: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    previous_entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    actor_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    actor_kind: Mapped[ActorKind] = mapped_column(Enum(ActorKind), nullable=False)

    action_type: Mapped[str] = mapped_column(String(100), nullable=False)
    affected_object_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # Not always a bare UUID -- app/services/evidence_service.py and
    # environment_service.py both record composite keys here
    # (f"{poc_request_id}:{control_id}" / f"{poc_request_id}:{dimension}")
    # to identify one control's evidence state or one dimension's
    # attestation within a request, since those are composite-PK
    # tables with no single id column of their own. 36 chars (a bare
    # UUID) was too narrow for that and silently truncated nothing on
    # SQLite (which does not enforce VARCHAR length at all) but raised
    # a real StringDataRightTruncationError on PostgreSQL, caught live
    # against a real PostgreSQL 16 instance. 100 covers a UUID plus the
    # longest composite suffix in use (a dimension name or control_id)
    # with headroom.
    affected_object_id: Mapped[str] = mapped_column(String(100), nullable=False)

    before_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    after_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
