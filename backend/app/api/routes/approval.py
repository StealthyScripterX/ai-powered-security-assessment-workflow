from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.approval import PocApprovalRequest
from app.models.user import UserRole
from app.schemas.approval import ApprovalDecisionIn, ApprovalDecisionOut, ApprovalRequestOut
from app.security import CurrentUser, require_role
from app.services import approval_service

router = APIRouter(prefix="/api/poc-requests", tags=["approval"])


@router.get("/{poc_request_id}/approval-request", response_model=ApprovalRequestOut)
async def get_approval_request(
    poc_request_id: str,
    current: CurrentUser = Depends(
        require_role(UserRole.SECURITY_REVIEWER, UserRole.FINAL_APPROVER, UserRole.COMPLIANCE_AUDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> PocApprovalRequest:
    result = await db.execute(select(PocApprovalRequest).where(PocApprovalRequest.poc_request_id == poc_request_id))
    approval_request = result.scalar_one_or_none()
    if approval_request is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No approval request exists yet.")
    return approval_request


@router.post("/{poc_request_id}/approval-request/decisions", response_model=ApprovalDecisionOut)
async def decide(
    poc_request_id: str,
    payload: ApprovalDecisionIn,
    current: CurrentUser = Depends(require_role(UserRole.FINAL_APPROVER)),
    db: AsyncSession = Depends(get_db),
):
    """D5-Approval-Audit.md section 6: P1-P4 evaluated inside this one
    transaction. On a P4 failure, a 409 carries the fresh recommendation
    the server already re-ran -- never leaves the caller with a bare
    error and a now-useless stale reference.
    """
    try:
        decision_row, info = await approval_service.commit_approval_decision(
            db,
            poc_request_id=poc_request_id,
            approver_id=current.user_id,
            decision=payload.decision,
            rationale=payload.rationale,
            disagreement_rationale=payload.disagreement_rationale,
        )
    except approval_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except approval_service.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    if decision_row is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "approval_preconditions_failed",
                "failed_preconditions": info["failed_preconditions"],
                "fresh_recommendation": info.get("fresh_recommendation"),
            },
        )
    return decision_row
