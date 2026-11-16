from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Depends, HTTPException, status

from app.database import get_db
from app.models.engine import PolicyConfig, Recommendation
from app.models.user import UserRole
from app.schemas.engine import PolicyConfigIn, PolicyConfigOut, RecommendationOut
from app.security import CurrentUser, require_role
from app.services import approval_service, engine_orchestration

router = APIRouter(tags=["engine"])


@router.post("/api/poc-requests/{poc_request_id}/recommendation/recompute", response_model=RecommendationOut)
async def recompute_recommendation(
    poc_request_id: str,
    current: CurrentUser = Depends(require_role(UserRole.REQUESTER, UserRole.SECURITY_REVIEWER, UserRole.FINAL_APPROVER)),
    db: AsyncSession = Depends(get_db),
) -> Recommendation:
    """D2-AI-Governance.md section 8's re-run trigger rule, path (a):
    explicit user-initiated re-submission. Returns 503 with the exact
    missing Open Decision(s) if the engine refuses (OD-10/15/16
    unconfigured) -- never a fabricated outcome.
    """
    try:
        recommendation = await engine_orchestration.run_engine(db, poc_request_id=poc_request_id)
    except engine_orchestration.EngineRefusedError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "engine_refused", "missing_configuration": exc.missing_config},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    # BR-016/D1 step 10: once a non-refused recommendation exists, the
    # approval request is created (idempotently) so a Final Approver can act.
    await approval_service.ensure_approval_request(db, poc_request_id=poc_request_id)
    return recommendation


@router.get("/api/poc-requests/{poc_request_id}/recommendation", response_model=RecommendationOut)
async def get_recommendation(
    poc_request_id: str,
    current: CurrentUser = Depends(
        require_role(UserRole.REQUESTER, UserRole.SECURITY_REVIEWER, UserRole.FINAL_APPROVER, UserRole.COMPLIANCE_AUDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> Recommendation:
    recommendation = await engine_orchestration.get_current_recommendation(db, poc_request_id=poc_request_id)
    if recommendation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No recommendation exists yet.")
    return recommendation


@router.post("/api/admin/policy-config", response_model=PolicyConfigOut, status_code=status.HTTP_201_CREATED)
async def publish_policy_config(
    payload: PolicyConfigIn,
    current: CurrentUser = Depends(require_role(UserRole.PLATFORM_OWNER)),
    db: AsyncSession = Depends(get_db),
) -> PolicyConfig:
    """Where the organization's real OD-10/OD-15/OD-16/OD-01 answers get
    entered -- PlatformOwner only. Nothing in this codebase calls this
    endpoint automatically or seeds it with a plausible-looking default;
    it is published, or it stays NULL and the engine keeps refusing
    (D2-AI-Governance.md section 8.3's "no weight is specified... OD-15").
    """
    config = PolicyConfig(
        layer1_completeness_threshold=payload.layer1_completeness_threshold,
        layer2_policy_hooks=payload.layer2_policy_hooks,
        layer3_weights=payload.layer3_weights,
        layer3_thresholds=payload.layer3_thresholds,
        approval_tier_model=payload.approval_tier_model,
        published_by=current.user_id,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


@router.get("/api/admin/policy-config/current", response_model=PolicyConfigOut | None)
async def get_current_policy_config(
    current: CurrentUser = Depends(require_role(*list(UserRole))),
    db: AsyncSession = Depends(get_db),
) -> PolicyConfig | None:
    """Any authenticated role may read this -- transparency of which
    Open Decisions are configured vs. still NULL (TASD-v1.0.md section
    20.2: "returns NULL fields plainly, not omitted").
    """
    result = await db.execute(select(PolicyConfig).order_by(PolicyConfig.version.desc()).limit(1))
    return result.scalar_one_or_none()
