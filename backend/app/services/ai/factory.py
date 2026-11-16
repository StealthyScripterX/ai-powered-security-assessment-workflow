from __future__ import annotations

from app.config import get_settings
from app.services.ai.client import (
    AnthropicModelClient,
    GeminiModelClient,
    ModelClient,
    ModelNotConfiguredError,
)


def get_model_client() -> ModelClient:
    """Instantiates the provider selected by AI_PROVIDER (app/config.py).
    Credentials are unwrapped from SecretStr only here, at the one point
    they are actually used, and passed straight into the provider SDK
    client constructor -- never stored in a plain variable that outlives
    this call, never logged, never returned to any caller.
    """
    settings = get_settings()
    if not settings.ai_configured:
        provider_env_var = "GEMINI_API_KEY" if settings.ai_provider == "gemini" else "ANTHROPIC_API_KEY"
        raise ModelNotConfiguredError(
            f"AI_PROVIDER is set to {settings.ai_provider!r} but {provider_env_var} is not configured on "
            f"this server. Set it in the environment (see .env.example) to enable AI scope analysis and "
            f"questionnaire generation."
        )

    if settings.ai_provider == "gemini":
        return GeminiModelClient(api_key=settings.gemini_api_key.get_secret_value(), model=settings.gemini_model)
    return AnthropicModelClient(api_key=settings.anthropic_api_key.get_secret_value(), model=settings.anthropic_model)
