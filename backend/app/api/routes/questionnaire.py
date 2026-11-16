from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import model_client_dependency
from app.database import get_db
from app.models.questionnaire import QuestionnaireAnswer, QuestionnaireQuestion
from app.models.user import UserRole
from app.schemas.questionnaire import AnswerOut, AnswerSubmission, QuestionOut, ScopeAnalysisOut
from app.security import CurrentUser, require_role
from app.services import ai_agent, scope_service
from app.services.ai.client import ModelClient, ModelUnavailableError
from app.services.ai.questionnaire import QuestionnaireGenerationError

router = APIRouter(prefix="/api/poc-requests", tags=["questionnaire"])


@router.post("/{poc_request_id}/questionnaire/generate", response_model=ScopeAnalysisOut)
async def generate_questionnaire(
    poc_request_id: str,
    current: CurrentUser = Depends(require_role(UserRole.REQUESTER)),
    db: AsyncSession = Depends(get_db),
    client: ModelClient = Depends(model_client_dependency),
) -> ScopeAnalysisOut:
    """AI scope analysis -> 11-15 questions (BR-002/BR-003), server-validated.

    Routed through the central AI agent facade
    (app/services/ai_agent.py:analyze_scope), which itself delegates to
    app.services.scope_service -- no logic is duplicated here or there.
    Returns the identified gaps/assumptions alongside the questions
    (BR-008) -- the "AI Assessment Workspace" screen's source for them.

    Returns 503 if no AI provider is configured -- an explicit refusal,
    never a fabricated or default question set (same "unconfigured, not
    invented" rule architecture/TASD-v1.0.md section 14.7 applies to the
    Decision Engine's Open Decisions).
    """
    try:
        result = await ai_agent.analyze_scope(
            db, poc_request_id=poc_request_id, requester_id=current.user_id, client=client
        )
    except scope_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except scope_service.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except QuestionnaireGenerationError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc
    except ModelUnavailableError as exc:
        # Transport-level failure (timeout/rate-limit/5xx) after retries
        # -- distinct from "not configured" (503 via model_client_dependency)
        # and from "responded, but invalidly" (502 above). Never silently
        # substitutes a fake result.
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return ScopeAnalysisOut(
        questions=result.questions,
        identified_gaps=result.identified_gaps,
        identified_assumptions=result.identified_assumptions,
        dropped_candidate_count=result.dropped_candidate_count,
    )


@router.get("/{poc_request_id}/questionnaire", response_model=list[QuestionOut])
async def list_questionnaire(
    poc_request_id: str,
    current: CurrentUser = Depends(
        require_role(UserRole.REQUESTER, UserRole.SECURITY_REVIEWER, UserRole.FINAL_APPROVER, UserRole.COMPLIANCE_AUDITOR)
    ),
    db: AsyncSession = Depends(get_db),
) -> list[QuestionnaireQuestion]:
    if current.role == UserRole.REQUESTER:
        try:
            await scope_service.get_poc_request_for_requester(db, poc_request_id, current.user_id)
        except scope_service.NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except scope_service.ForbiddenError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    result = await db.execute(
        select(QuestionnaireQuestion)
        .where(
            QuestionnaireQuestion.poc_request_id == poc_request_id,
            QuestionnaireQuestion.dropped_for_cap == False,  # noqa: E712
        )
        .order_by(QuestionnaireQuestion.sequence)
    )
    return list(result.scalars().all())


@router.post("/{poc_request_id}/answers", response_model=list[AnswerOut], status_code=status.HTTP_201_CREATED)
async def submit_answers(
    poc_request_id: str,
    payload: AnswerSubmission,
    current: CurrentUser = Depends(require_role(UserRole.REQUESTER)),
    db: AsyncSession = Depends(get_db),
) -> list[QuestionnaireAnswer]:
    try:
        rows = await scope_service.submit_answers(
            db,
            poc_request_id=poc_request_id,
            requester_id=current.user_id,
            answers=[(a.question_id, a.answer_text) for a in payload.answers],
        )
    except scope_service.NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except scope_service.ForbiddenError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return rows
