from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.evidence import ControlEvidenceState, EvidenceArtifact
from app.models.user import UserRole
from app.schemas.evidence import EvidenceArtifactOut, EvidenceStateOut, EvidenceValidationIn
from app.security import CurrentUser, require_role
from app.services import evidence_service, scope_service

router = APIRouter(prefix="/api/poc-requests", tags=["evidence"])


@router.post(
    "/{poc_request_id}/evidence",
    response_model=EvidenceArtifactOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_evidence(
    poc_request_id: str,
    file: UploadFile = File(...),
    control_id: str | None = Form(None),
    current: CurrentUser = Depends(require_role(UserRole.REQUESTER, UserRole.SECURITY_REVIEWER)),
    db: AsyncSession = Depends(get_db),
) -> EvidenceArtifact:
    """BR-005a: always lands at 'Submitted - Pending Review'. Never
    auto-Verified -- there is no code path here that can set Verified or
    Rejected; see POST .../evidence/validate.
    """
    file_bytes = await file.read()
    try:
        artifact = await evidence_service.upload_evidence(
            db,
            poc_request_id=poc_request_id,
            requester_id=current.user_id,
            control_id=control_id,
            filename=file.filename or "unnamed",
            content_type=file.content_type or "application/octet-stream",
            file_bytes=file_bytes,
        )
    except scope_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except scope_service.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except evidence_service.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc

    # Synchronous stand-in for the async AV-scan worker queue
    # (architecture/TASD-v1.0.md section 8.14) -- see
    # evidence_service.run_scan's docstring for why this is a placeholder.
    await evidence_service.run_scan(db, artifact_id=artifact.id)
    refreshed = await db.execute(select(EvidenceArtifact).where(EvidenceArtifact.id == artifact.id))
    return refreshed.scalar_one()


@router.get("/{poc_request_id}/evidence-states", response_model=list[EvidenceStateOut])
async def list_evidence_states(
    poc_request_id: str,
    current: CurrentUser = Depends(
        require_role(UserRole.REQUESTER, UserRole.SECURITY_REVIEWER, UserRole.FINAL_APPROVER, UserRole.COMPLIANCE_AUDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[ControlEvidenceState]:
    """Always returns all four possible states across controls -- never
    collapses the four-state model into a simpler view (BR-005).
    """
    if current.role == UserRole.REQUESTER:
        try:
            await scope_service.get_poc_request_for_requester(db, poc_request_id, current.user_id)
        except scope_service.NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except scope_service.ForbiddenError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return await evidence_service.list_evidence_states(db, poc_request_id=poc_request_id)


@router.post("/{poc_request_id}/controls/{control_id}/evidence/validate", response_model=EvidenceStateOut)
async def validate_evidence(
    poc_request_id: str,
    control_id: str,
    payload: EvidenceValidationIn,
    current: CurrentUser = Depends(require_role(UserRole.SECURITY_REVIEWER)),
    db: AsyncSession = Depends(get_db),
) -> ControlEvidenceState:
    """The ONLY endpoint that can set 'Verified - Human Validated' or
    'Rejected - Insufficient Evidence'. SecurityReviewer only (OD-07's
    current default) -- never reachable by the AI actor, which holds no
    role that satisfies this dependency.
    """
    try:
        return await evidence_service.transition_evidence_state(
            db,
            poc_request_id=poc_request_id,
            control_id=control_id,
            new_state=payload.new_state,
            reviewer_id=current.user_id,
            rationale=payload.rationale,
        )
    except evidence_service.EvidenceNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except evidence_service.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
