"""Organizational Decision Dashboard API. PlatformOwner-only for every
write action (propose/approve/reject/revise/activate) -- the same role
that already owns `/api/admin/policy-config`
(app/api/routes/engine.py); reads are open to any authenticated role so
every dashboard can show which Open Decisions remain unresolved.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.od_registry import ODDecisionRecord, OrganizationalDecision
from app.models.user import UserRole
from app.schemas.od_registry import ODDecideIn, ODOut, ODProposeIn, ODRecordOut
from app.security import CurrentUser, require_role
from app.services import od_registry_service as svc

router = APIRouter(prefix="/api/organizational-decisions", tags=["organizational-decisions"])


def _handle_errors(exc: Exception):
    if isinstance(exc, svc.ODNotFoundError):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    if isinstance(exc, svc.ODValidationError):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    raise exc


@router.get("", response_model=list[ODOut])
async def list_decisions(
    current: CurrentUser = Depends(require_role(*UserRole)), db: AsyncSession = Depends(get_db)
) -> list[OrganizationalDecision]:
    return await svc.list_decisions(db)


@router.get("/{od_id}", response_model=ODOut)
async def get_decision(
    od_id: str, current: CurrentUser = Depends(require_role(*UserRole)), db: AsyncSession = Depends(get_db)
) -> OrganizationalDecision:
    try:
        return await svc.get_decision(db, od_id)
    except svc.ODNotFoundError as exc:
        _handle_errors(exc)


@router.get("/{od_id}/history", response_model=list[ODRecordOut])
async def get_history(
    od_id: str, current: CurrentUser = Depends(require_role(*UserRole)), db: AsyncSession = Depends(get_db)
) -> list[ODDecisionRecord]:
    return await svc.get_history(db, od_id)


@router.post("/{od_id}/propose", response_model=ODRecordOut)
async def propose(
    od_id: str,
    payload: ODProposeIn,
    current: CurrentUser = Depends(require_role(UserRole.PLATFORM_OWNER)),
    db: AsyncSession = Depends(get_db),
) -> ODDecisionRecord:
    try:
        return await svc.propose(
            db, od_id=od_id, value=payload.value, rationale=payload.rationale,
            actor_id=current.user_id, actor_role=current.role.value,
        )
    except (svc.ODNotFoundError, svc.ODValidationError) as exc:
        _handle_errors(exc)


@router.post("/{od_id}/approve", response_model=ODRecordOut)
async def approve(
    od_id: str,
    payload: ODDecideIn,
    current: CurrentUser = Depends(require_role(UserRole.PLATFORM_OWNER)),
    db: AsyncSession = Depends(get_db),
) -> ODDecisionRecord:
    try:
        return await svc.approve(
            db, od_id=od_id, rationale=payload.rationale, actor_id=current.user_id, actor_role=current.role.value
        )
    except (svc.ODNotFoundError, svc.ODValidationError) as exc:
        _handle_errors(exc)


@router.post("/{od_id}/reject", response_model=ODRecordOut)
async def reject(
    od_id: str,
    payload: ODDecideIn,
    current: CurrentUser = Depends(require_role(UserRole.PLATFORM_OWNER)),
    db: AsyncSession = Depends(get_db),
) -> ODDecisionRecord:
    try:
        return await svc.reject(
            db, od_id=od_id, rationale=payload.rationale, actor_id=current.user_id, actor_role=current.role.value
        )
    except (svc.ODNotFoundError, svc.ODValidationError) as exc:
        _handle_errors(exc)


@router.post("/{od_id}/revise", response_model=ODRecordOut)
async def revise(
    od_id: str,
    payload: ODProposeIn,
    current: CurrentUser = Depends(require_role(UserRole.PLATFORM_OWNER)),
    db: AsyncSession = Depends(get_db),
) -> ODDecisionRecord:
    try:
        return await svc.revise(
            db, od_id=od_id, value=payload.value, rationale=payload.rationale,
            actor_id=current.user_id, actor_role=current.role.value,
        )
    except (svc.ODNotFoundError, svc.ODValidationError) as exc:
        _handle_errors(exc)


@router.post("/{od_id}/activate", response_model=ODRecordOut)
async def activate(
    od_id: str,
    current: CurrentUser = Depends(require_role(UserRole.PLATFORM_OWNER)),
    db: AsyncSession = Depends(get_db),
) -> ODDecisionRecord:
    try:
        return await svc.activate(db, od_id=od_id, actor_id=current.user_id, actor_role=current.role.value)
    except (svc.ODNotFoundError, svc.ODValidationError) as exc:
        _handle_errors(exc)
