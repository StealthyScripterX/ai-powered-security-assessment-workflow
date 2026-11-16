"""Shared FastAPI dependencies that need to be override-able in tests
(e.g. swapping the real Anthropic-backed model client for
app.services.ai.client.FakeModelClient without a network dependency).
"""
from __future__ import annotations

from fastapi import HTTPException, status

from app.services.ai.client import ModelClient, ModelNotConfiguredError
from app.services.ai.factory import get_model_client


async def model_client_dependency() -> ModelClient:
    try:
        return get_model_client()
    except ModelNotConfiguredError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
