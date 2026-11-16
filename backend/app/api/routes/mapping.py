from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import model_client_dependency
from app.database import get_db
from app.models.mapping import MappingRecord
from app.models.user import UserRole
from app.schemas.mapping import MappingOut, MappingReviewIn
from app.security import CurrentUser, require_role
from app.services import ai_agent, mapping_service, scope_service
from app.services.ai.client import ModelClient, ModelUnavailableError
from app.services.ai.mapping import MappingGenerationError

router = APIRouter(prefix="/api/poc-requests", tags=["mapping"])


@router.post("/{poc_request_id}/mappings/generate", response_model=list[MappingOut])
async def generate_mappings(
    poc_request_id: str,
    current: CurrentUser = Depends(require_role(UserRole.REQUESTER, UserRole.SECURITY_REVIEWER)),
    db: AsyncSession = Depends(get_db),
    client: ModelClient = Depends(model_client_dependency),
) -> list[MappingRecord]:
    """D3-Methodology section 6: drafts control mapping records per
    answered question, choosing only from the closed candidate-control
    set for that question's domain. Never invents a control identifier
    outside the catalog (app/services/ai/mapping.py enforces this).

    Reachable by the Requester (as part of their own assessment flow) or
    a SecurityReviewer (to retrigger mapping on any assessment in their
    queue) -- object-level ownership is checked here for a Requester
    caller only; SecurityReviewer's cross-cutting access is expected.
    """
    try:
        if current.role == UserRole.REQUESTER:
            await scope_service.get_poc_request_for_requester(db, poc_request_id, current.user_id)
        return await ai_agent.propose_control_mappings(
            db, poc_request_id=poc_request_id, requester_id=current.user_id, client=client
        )
    except scope_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except scope_service.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except MappingGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ModelUnavailableError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc


@router.get("/{poc_request_id}/mappings", response_model=list[MappingOut])
async def list_mappings(
    poc_request_id: str,
    current: CurrentUser = Depends(
        require_role(UserRole.REQUESTER, UserRole.SECURITY_REVIEWER, UserRole.FINAL_APPROVER, UserRole.COMPLIANCE_AUDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[MappingRecord]:
    if current.role == UserRole.REQUESTER:
        # Object-level authorization: a Requester sees only their own
        # POC request's mappings (T-04, architecture/TASD-v1.0.md section 19).
        try:
            await scope_service.get_poc_request_for_requester(db, poc_request_id, current.user_id)
        except scope_service.NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except scope_service.ForbiddenError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return await mapping_service.list_mappings(db, poc_request_id=poc_request_id)


@router.post("/{poc_request_id}/mappings/{mapping_id}/review", response_model=MappingOut)
async def review_mapping(
    poc_request_id: str,
    mapping_id: str,
    payload: MappingReviewIn,
    current: CurrentUser = Depends(require_role(UserRole.SECURITY_REVIEWER)),
    db: AsyncSession = Depends(get_db),
) -> MappingRecord:
    """D3-Methodology section 8: Confirm/Adjust/Reject -- SecurityReviewer
    only. Every transition is a new row (app/services/mapping_service.py),
    never an edit of the AI's original.
    """
    try:
        return await mapping_service.review_mapping(
            db,
            poc_request_id=poc_request_id,
            mapping_id=mapping_id,
            reviewer_id=current.user_id,
            action=payload.action,
            control_id=payload.control_id,
            confidence=payload.confidence,
            rationale=payload.rationale,
            reject_reason=payload.reject_reason,
        )
    except mapping_service.MappingNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
