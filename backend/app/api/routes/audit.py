"""Compliance Dashboard: read-only audit trail + hash-chain verification.

D5-Approval-Audit.md section 5.4 / architecture/TASD-v1.0.md section
18.4. `audit_reader`-equivalent access in this phase is enforced by
role (ComplianceAuditor, PlatformOwner), not yet by a separate database
role grant (see IMPLEMENTATION-NOTES.md) -- but the code-level
guarantee already holds: no route in this module, or anywhere else in
the codebase, writes to `audit_entry`.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, Query

from app.database import get_db
from app.models.audit import AuditEntry
from app.models.user import UserRole
from app.schemas.audit import AuditEntryOut, ChainVerificationOut
from app.security import CurrentUser, require_role
from app.services import audit_service

router = APIRouter(prefix="/api/audit-entries", tags=["audit"])


@router.get("", response_model=list[AuditEntryOut])
async def list_audit_entries(
    affected_object_id: str | None = Query(default=None),
    limit: int = Query(default=200, le=1000),
    current: CurrentUser = Depends(require_role(UserRole.COMPLIANCE_AUDITOR, UserRole.PLATFORM_OWNER)),
    db: AsyncSession = Depends(get_db),
) -> list[AuditEntry]:
    stmt = select(AuditEntry).order_by(AuditEntry.sequence_number.desc()).limit(limit)
    if affected_object_id:
        stmt = select(AuditEntry).where(AuditEntry.affected_object_id == affected_object_id).order_by(
            AuditEntry.sequence_number.desc()
        ).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.get("/verify", response_model=ChainVerificationOut)
async def verify_chain(
    current: CurrentUser = Depends(require_role(UserRole.COMPLIANCE_AUDITOR, UserRole.PLATFORM_OWNER)),
    db: AsyncSession = Depends(get_db),
) -> ChainVerificationOut:
    """D5-Approval-Audit.md section 5.4's `fn_verify_audit_chain`,
    triggered on demand -- recomputes the hash chain from genesis and
    reports the exact first broken sequence number, if any.
    """
    ok, break_point = await audit_service.verify_chain(db)
    count_result = await db.execute(select(AuditEntry))
    total = len(count_result.scalars().all())
    return ChainVerificationOut(ok=ok, first_broken_sequence_number=break_point, entries_checked=total)
