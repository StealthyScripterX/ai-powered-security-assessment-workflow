from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.poc_request import PocRequest
from app.models.scope_submission import ScopeSubmission
from app.models.user import UserRole
from app.schemas.scope import PocRequestOut, ScopeSubmissionCreate, ScopeSubmissionOut
from app.security import CurrentUser, require_role
from app.services import scope_service

router = APIRouter(prefix="/api/poc-requests", tags=["poc-requests"])


@router.post("", response_model=ScopeSubmissionOut, status_code=status.HTTP_201_CREATED)
async def create_poc_request(
    payload: ScopeSubmissionCreate,
    current: CurrentUser = Depends(require_role(UserRole.REQUESTER)),
    db: AsyncSession = Depends(get_db),
) -> ScopeSubmission:
    """BR-001: submit a scope with no pre-existing security documentation."""
    _poc_request, scope = await scope_service.submit_scope(
        db,
        requester_id=current.user_id,
        project_description=payload.project_description,
        systems_in_scope=payload.systems_in_scope,
        business_justification=payload.business_justification,
        intake_form_data=payload.intake_form_data,
    )
    return scope


@router.get("", response_model=list[PocRequestOut])
async def list_my_poc_requests(
    current: CurrentUser = Depends(require_role(UserRole.REQUESTER)),
    db: AsyncSession = Depends(get_db),
) -> list[PocRequest]:
    result = await db.execute(
        select(PocRequest).where(PocRequest.requester_id == current.user_id).order_by(PocRequest.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{poc_request_id}", response_model=PocRequestOut)
async def get_poc_request(
    poc_request_id: str,
    current: CurrentUser = Depends(require_role(UserRole.REQUESTER)),
    db: AsyncSession = Depends(get_db),
) -> PocRequest:
    result = await db.execute(select(PocRequest).where(PocRequest.id == poc_request_id))
    poc_request = result.scalar_one_or_none()
    if poc_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POC request not found.")
    # Object-level authorization: server-checked ownership, not a
    # client-supplied filter (T-04 in architecture/TASD-v1.0.md section 19).
    if poc_request.requester_id != current.user_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your POC request.")
    return poc_request
