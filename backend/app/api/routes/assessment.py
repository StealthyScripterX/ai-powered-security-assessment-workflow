"""Cross-cutting read endpoints: the consolidated assessment summary
(the central AI agent's read-model, app/services/ai_agent.py) and the
assessment queue every non-Requester dashboard needs to see every
assessment, not just "mine."
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.poc_request import PocRequest
from app.models.user import UserRole
from app.schemas.assessment import AssessmentSummaryOut, QueueItemOut
from app.security import CurrentUser, require_role
from app.services import ai_agent, scope_service

router = APIRouter(prefix="/api/poc-requests", tags=["assessment"])

_CROSS_CUTTING_ROLES = (
    UserRole.SECURITY_REVIEWER,
    UserRole.ENVIRONMENT_OWNER,
    UserRole.FINAL_APPROVER,
    UserRole.COMPLIANCE_AUDITOR,
    UserRole.PLATFORM_OWNER,
)


@router.get("/queue", response_model=list[QueueItemOut])
async def list_queue(
    current: CurrentUser = Depends(require_role(*_CROSS_CUTTING_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> list[PocRequest]:
    """Every assessment, for the dashboards whose role is cross-cutting
    by nature (Reviewer, Environment Owner, Approver, Compliance,
    Platform Owner) -- a Requester uses GET /api/poc-requests instead,
    which is scoped to their own assessments only (T-04,
    architecture/TASD-v1.0.md section 19).
    """
    result = await db.execute(select(PocRequest).order_by(PocRequest.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{poc_request_id}/summary", response_model=AssessmentSummaryOut)
async def get_summary(
    poc_request_id: str,
    current: CurrentUser = Depends(require_role(*UserRole)),
    db: AsyncSession = Depends(get_db),
) -> AssessmentSummaryOut:
    if current.role == UserRole.REQUESTER:
        try:
            await scope_service.get_poc_request_for_requester(db, poc_request_id, current.user_id)
        except scope_service.NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except scope_service.ForbiddenError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    try:
        summary = await ai_agent.get_assessment_summary(db, poc_request_id=poc_request_id)
    except scope_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return AssessmentSummaryOut(
        poc_request_id=summary.poc_request_id,
        status=summary.status,
        current_input_version=summary.current_input_version,
        scope=summary.scope,
        questions=summary.questions,
        answers=summary.answers,
        mappings=summary.mappings,
        evidence_states=summary.evidence_states,
        environment_attestations=summary.environment_attestations,
        final_signoff_boolean=summary.final_signoff_boolean,
        recommendation=summary.recommendation,
    )
