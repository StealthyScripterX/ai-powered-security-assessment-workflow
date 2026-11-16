"""Environment Readiness: D4-Environment-Readiness.md section 5/6,
architecture/TASD-v1.0.md section 11.5/16.

Non-negotiable encoded as a hard data-layer CHECK, not a documented
convention: `disposition = 'Accepted'` is structurally forbidden on the
Isolation and AccessControl dimensions (D4 section 6's non-waivable
rule). `final_signoff_boolean` is never a stored column -- it is always
computed fresh by app/services/environment_service.py:compute_final_signoff,
exactly as D4 section 6 / TASD-v1.0.md section 16.4 require, so an
expired or revoked exception takes effect the instant it is checked,
with no stale cached value to forget to invalidate.
"""
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    PrimaryKeyConstraint,
    String,
    Text,
)
from sqlalchemy.ext.mutable import MutableList
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.database import Base


class ReadinessDimension(str, enum.Enum):
    ISOLATION = "Isolation"
    ACCESS_CONTROL = "AccessControl"
    TEST_DATA = "TestData"
    CONFIG_BASELINE = "ConfigBaseline"
    LOGGING = "Logging"
    BACKUP_ROLLBACK = "BackupRollback"
    DECOMMISSIONING = "Decommissioning"


NON_WAIVABLE_DIMENSIONS = {ReadinessDimension.ISOLATION, ReadinessDimension.ACCESS_CONTROL}


class AttestationStatus(str, enum.Enum):
    NOT_STARTED = "Not Started"
    IN_PROGRESS = "In Progress"
    ATTESTED = "Attested"
    ATTESTED_WITH_EXCEPTION = "Attested-with-Exception"


class ExceptionDisposition(str, enum.Enum):
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    DEFERRED = "Deferred"


def _uuid() -> str:
    return str(uuid.uuid4())


class EnvironmentReadinessAttestation(Base):
    __tablename__ = "environment_readiness_attestation"
    __table_args__ = (PrimaryKeyConstraint("poc_request_id", "dimension"),)

    poc_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("poc_request.id"), nullable=False)
    dimension: Mapped[ReadinessDimension] = mapped_column(Enum(ReadinessDimension), nullable=False)
    status: Mapped[AttestationStatus] = mapped_column(
        Enum(AttestationStatus), nullable=False, default=AttestationStatus.NOT_STARTED
    )
    attestation_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    environment_owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=True)
    supporting_evidence_ids: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), nullable=False, default=list)
    attested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExceptionRecord(Base):
    __tablename__ = "exception_record"
    __table_args__ = (
        # NOTE on the literal strings below: SQLAlchemy's Enum() type
        # uses the Python enum MEMBER NAME (e.g. "ACCEPTED"), not its
        # .value (e.g. "Accepted"), as the string actually stored and
        # as the native PostgreSQL enum type's labels -- confirmed live
        # against a real PostgreSQL 16 instance (this CHECK constraint
        # originally used the human-readable .value strings, which
        # made PostgreSQL refuse to even CREATE this table with
        # "invalid input value for enum exceptiondisposition: 'Accepted'",
        # since the DB-side enum type only has ACCEPTED/REJECTED/DEFERRED
        # as valid labels). On SQLite the same mismatch silently made
        # this constraint a permanent no-op (disposition is never
        # literally stored as 'Accepted', so `!= 'Accepted'` was always
        # true) -- the non-waivable rule only held in practice because
        # app/services/environment_service.py separately re-validates it
        # in Python before any write. Fixed here to use the names that
        # actually match what the Enum column stores.
        CheckConstraint(
            "disposition != 'ACCEPTED' OR dimension NOT IN ('ISOLATION', 'ACCESS_CONTROL')",
            name="ck_exception_non_waivable",
        ),
        CheckConstraint(
            "disposition != 'ACCEPTED' OR (remediation_owner IS NOT NULL AND remediation_deadline IS NOT NULL)",
            name="ck_exception_accepted_requires_remediation",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    poc_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("poc_request.id"), nullable=False)
    dimension: Mapped[ReadinessDimension] = mapped_column(Enum(ReadinessDimension), nullable=False)

    issue_description: Mapped[str] = mapped_column(Text, nullable=False)
    risk_assessment: Mapped[str] = mapped_column(Text, nullable=False)
    compensating_controls: Mapped[list] = mapped_column(MutableList.as_mutable(JSON), nullable=False, default=list)
    disposition: Mapped[ExceptionDisposition] = mapped_column(Enum(ExceptionDisposition), nullable=False)
    disposition_authorized_by: Mapped[str] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=False)
    disposition_rationale: Mapped[str] = mapped_column(Text, nullable=False)
    remediation_owner: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=True)
    remediation_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    expiry_date: Mapped[date] = mapped_column(Date, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revoked_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("app_user.id"), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
