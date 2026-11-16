"""Application configuration.

Secrets are read exclusively from the environment (via .env in local dev,
real process environment variables in any deployed environment). Nothing
here hardcodes a credential -- see .env.example for the variables this
reads and architecture/TASD-v1.0.md section 9.5 / section 21.3 for the
secrets-management design this is a local-dev stand-in for.

Every credential field is `SecretStr`, not `str` -- Pydantic masks it as
`**********` in `repr()`/`str()`/logging/tracebacks by default, so an
accidental `print(settings)`, an unhandled-exception log, or a FastAPI
debug page can never leak a key. Call `.get_secret_value()` only at the
one point a credential is actually used (the provider client
constructors in app/services/ai/client.py) -- never store the unwrapped
value in a variable that outlives that call, never log it, never
include it in an API response.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"

    database_url: str = "sqlite+aiosqlite:///./poc_workflow.db"

    jwt_secret_key: SecretStr = SecretStr("")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    # Provider selection -- "anthropic" (default) or "gemini". Both
    # providers' credentials may be present at once (e.g. in a dev
    # environment that has both keys); only AI_PROVIDER decides which
    # one is actually instantiated at call time
    # (app/services/ai/factory.py). Switching providers is a config
    # change, never a code change.
    ai_provider: str = "anthropic"

    anthropic_api_key: SecretStr = SecretStr("")
    anthropic_model: str = "claude-sonnet-4-5-20250929"

    gemini_api_key: SecretStr = SecretStr("")
    gemini_model: str = "gemini-3.8-flash"

    # Evidence object storage. "local" (default) -- a local-filesystem
    # stand-in, this build's dev/test default -- or "s3" for real
    # S3-compatible storage (architecture/TASD-v1.0.md section 9.5/15.4),
    # selected via app/services/storage.py:get_storage(). Switching
    # backends is a config change, never a code change (same pattern as
    # AI_PROVIDER). quarantine_dir/evidence_dir are only used by the
    # "local" backend; overridden to a temp directory by the test suite
    # (tests/conftest.py) so test runs never write into the real working
    # directory.
    storage_backend: str = "local"
    quarantine_dir: str = "var/quarantine"
    evidence_dir: str = "var/evidence"

    s3_quarantine_bucket: str = ""
    s3_evidence_bucket: str = ""
    s3_region: str = ""
    # Non-AWS S3-compatible endpoints (e.g. MinIO); blank uses real AWS S3.
    s3_endpoint_url: str = ""
    aws_access_key_id: SecretStr = SecretStr("")
    aws_secret_access_key: SecretStr = SecretStr("")

    @property
    def storage_configured(self) -> bool:
        """Whether the CURRENTLY SELECTED storage backend has what it
        needs -- the same "explicit unconfigured state, never silently
        degrade" rule app/services/ai/client.py's ModelNotConfiguredError
        applies to the AI provider.
        """
        if self.storage_backend == "s3":
            return bool(self.s3_quarantine_bucket and self.s3_evidence_bucket)
        return True  # "local" always has a usable default directory pair

    @property
    def ai_configured(self) -> bool:
        """Whether the CURRENTLY SELECTED provider (ai_provider) has a
        credential set -- not whether any provider anywhere has one.
        """
        if self.ai_provider == "gemini":
            return bool(self.gemini_api_key.get_secret_value())
        return bool(self.anthropic_api_key.get_secret_value())

    @property
    def auth_configured(self) -> bool:
        return bool(self.jwt_secret_key.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
