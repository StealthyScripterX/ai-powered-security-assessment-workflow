"""User and role model.

Role set is exactly the six actors in architecture/TASD-v1.0.md section 6.1 /
docs/baseline/D1-Requirements.md section 7. Only Requester is exercised by this
Phase 1 vertical slice's endpoints, but the full role enum is modeled now
so the RBAC foundation does not need a breaking schema change when
Reviewer/Approver/Environment-Owner/Compliance/Platform-Owner endpoints
are added in later phases.

OIDC federation (TASD-v1.0.md section 8.3) is not wired up in this phase --
authentication here is a local username/password + JWT provider,
documented in IMPLEMENTATION-NOTES.md as a deliberate, declared stand-in,
not a silent architecture change. What matters for this phase's
non-negotiables is preserved regardless of the auth transport: role is
read from server-validated session state, never from client-supplied
request fields (app/security.py), matching D2 section 9.2 / D4 section 7 / D5
section 5 "actor identity is never a client-supplied field."
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserRole(str, enum.Enum):
    REQUESTER = "Requester"
    SECURITY_REVIEWER = "SecurityReviewer"
    ENVIRONMENT_OWNER = "EnvironmentOwner"
    FINAL_APPROVER = "FinalApprover"
    COMPLIANCE_AUDITOR = "ComplianceAuditor"
    PLATFORM_OWNER = "PlatformOwner"


def _uuid() -> str:
    return str(uuid.uuid4())


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
