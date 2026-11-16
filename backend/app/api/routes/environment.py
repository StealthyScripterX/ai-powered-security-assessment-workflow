from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.audit import ActorKind
from app.models.environment import EnvironmentReadinessAttestation, ExceptionRecord
from app.models.poc_request import PocRequest
from app.models.user import UserRole
from app.schemas.environment import AttestationIn, AttestationOut, ExceptionIn, SignoffOut
from app.security import CurrentUser, require_role
from app.services import environment_service

router = APIRouter(prefix="/api/poc-requests", tags=["environment"])


async def _requester_id_for(db: AsyncSession, poc_request_id: str) -> str:
    result = await db.execute(select(PocRequest.requester_id).where(PocRequest.id == poc_request_id))
    requester_id = result.scalar_one_or_none()
    if requester_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="POC request not found.")
    return requester_id


@router.get("/{poc_request_id}/environment-readiness", response_model=list[AttestationOut])
async def list_attestations(
    poc_request_id: str,
    current: CurrentUser = Depends(
        require_role(
            UserRole.ENVIRONMENT_OWNER, UserRole.SECURITY_REVIEWER, UserRole.FINAL_APPROVER, UserRole.COMPLIANCE_AUDITOR
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> list[EnvironmentReadinessAttestation]:
    return await environment_service.list_attestations(db, poc_request_id=poc_request_id)


@router.get("/{poc_request_id}/environment-readiness/signoff", response_model=SignoffOut)
async def get_signoff(
    poc_request_id: str,
    current: CurrentUser = Depends(
        require_role(
            UserRole.ENVIRONMENT_OWNER, UserRole.SECURITY_REVIEWER, UserRole.FINAL_APPROVER, UserRole.COMPLIANCE_AUDITOR
        )
    ),
    db: AsyncSession = Depends(get_db),
) -> SignoffOut:
    final = await environment_service.compute_final_signoff(db, poc_request_id=poc_request_id)
    return SignoffOut(poc_request_id=poc_request_id, final_signoff_boolean=final)


@router.put("/{poc_request_id}/environment-readiness/{dimension}", response_model=AttestationOut)
async def attest_dimension(
    poc_request_id: str,
    dimension: str,
    payload: AttestationIn,
    current: CurrentUser = Depends(require_role(UserRole.ENVIRONMENT_OWNER)),
    db: AsyncSession = Depends(get_db),
) -> EnvironmentReadinessAttestation:
    requester_id = await _requester_id_for(db, poc_request_id)
    try:
        return await environment_service.attest_dimension(
            db,
            poc_request_id=poc_request_id,
            dimension=dimension,
            status=payload.status,
            attestation_text=payload.attestation_text,
            environment_owner_id=current.user_id,
            requester_id_of_poc=requester_id,
            supporting_evidence_ids=payload.supporting_evidence_ids,
        )
    except (ValueError, environment_service.ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.post("/{poc_request_id}/environment-readiness/{dimension}/exception", response_model=dict)
async def dispose_exception(
    poc_request_id: str,
    dimension: str,
    payload: ExceptionIn,
    current: CurrentUser = Depends(require_role(UserRole.SECURITY_REVIEWER, UserRole.FINAL_APPROVER)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """D4-Environment-Readiness.md section 6: disposition is authorized
    by a Security Reviewer or Final Approver -- never the Environment
    Owner who raised the issue, never the AI.
    """
    try:
        record = await environment_service.dispose_exception(
            db,
            poc_request_id=poc_request_id,
            dimension=dimension,
            issue_description=payload.issue_description,
            risk_assessment=payload.risk_assessment,
            compensating_controls=payload.compensating_controls,
            disposition=payload.disposition,
            disposition_rationale=payload.disposition_rationale,
            authorized_by=current.user_id,
            environment_owner_id_for_dimension=payload.environment_owner_id_for_dimension,
            remediation_owner=payload.remediation_owner,
            remediation_deadline=payload.remediation_deadline,
            expiry_date=payload.expiry_date,
        )
    except environment_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except (ValueError, environment_service.ValidationError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    return {
        "id": record.id,
        "dimension": record.dimension.value,
        "disposition": record.disposition.value,
        "expiry_date": str(record.expiry_date),
    }


@router.post("/{poc_request_id}/environment-readiness/{dimension}/revoke", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_attestation(
    poc_request_id: str,
    dimension: str,
    current: CurrentUser = Depends(
        require_role(UserRole.SECURITY_REVIEWER, UserRole.FINAL_APPROVER, UserRole.ENVIRONMENT_OWNER)
    ),
    db: AsyncSession = Depends(get_db),
) -> None:
    actor_kind_map = {
        UserRole.SECURITY_REVIEWER: ActorKind.SECURITY_REVIEWER,
        UserRole.FINAL_APPROVER: ActorKind.FINAL_APPROVER,
        UserRole.ENVIRONMENT_OWNER: ActorKind.ENVIRONMENT_OWNER,
    }
    try:
        await environment_service.revoke_attestation(
            db,
            poc_request_id=poc_request_id,
            dimension=dimension,
            actor_id=current.user_id,
            actor_kind=actor_kind_map[current.role],
        )
    except environment_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
