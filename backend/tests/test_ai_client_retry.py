"""Transport-level retry behavior of app.services.ai.client._with_retry.

Covers the quota-aware short-circuit added after a live demo session
exhausted Gemini's free-tier daily quota by retrying 3x per call on top
of several duplicate UI clicks: a 429 whose server-advertised
retryDelay is long (a per-minute/per-day cap) must not be retried
blindly within the same call, while a short-lived 503/429 should still
get the full exponential-backoff retry treatment.
"""
from __future__ import annotations

import pytest

from app.services.ai.client import ModelUnavailableError, _with_retry


class _FakeAPIError(Exception):
    """Shaped like google.genai.errors.APIError: .code and a .details
    dict carrying a RetryInfo entry, the same place the real SDK puts
    the server's advertised retryDelay.
    """

    def __init__(self, code: int, retry_delay: str | None = None):
        self.code = code
        self.details = {"error": {"code": code, "details": ([{"retryDelay": retry_delay}] if retry_delay else [])}}
        super().__init__(f"{code} error")


async def test_long_quota_retry_delay_is_not_retried_inline():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        raise _FakeAPIError(429, retry_delay="61499.096890995s")  # Gemini's real per-day quota delay

    with pytest.raises(ModelUnavailableError, match="1 attempt"):
        await _with_retry(flaky, provider_name="Gemini")
    assert calls == 1


async def test_brief_rate_limit_without_long_retry_delay_is_retried():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        raise _FakeAPIError(503)  # no retryDelay info -- transient 503, retry as before

    with pytest.raises(ModelUnavailableError, match="3 attempt"):
        await _with_retry(flaky, provider_name="Gemini")
    assert calls == 3


async def test_short_retry_delay_still_retries_up_to_cap():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        raise _FakeAPIError(429, retry_delay="2s")  # well under the inline-retry cap

    with pytest.raises(ModelUnavailableError, match="3 attempt"):
        await _with_retry(flaky, provider_name="Gemini")
    assert calls == 3


async def test_non_transient_error_propagates_immediately_without_wrapping():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        raise _FakeAPIError(401)

    with pytest.raises(_FakeAPIError):
        await _with_retry(flaky, provider_name="Gemini")
    assert calls == 1
