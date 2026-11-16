"""Safe, repeatable live Gemini verification command.

Run from backend/:

    python scripts/verify_gemini.py

What it does, and no more:
  1. Lists the account's available models (a GET call -- does not
     consume generateContent quota) and confirms the configured
     GEMINI_MODEL is present and generateContent-capable.
  2. Makes exactly ONE generateContent call, through the real
     GeminiModelClient (the same provider class and retry/backoff
     wrapper the application itself uses) -- never a bare loop of
     requests, and never retried blindly if the account is already
     quota-exhausted: app.services.ai.client._with_retry now stops
     after a single attempt when the server's own advertised
     retryDelay is long (see client.py), so running this script
     repeatedly while quota-exhausted does not burn further quota.

Never prints the API key. Exit codes: 0 = live inference confirmed,
1 = reachable but currently blocked (quota/rate-limit/overload --
re-run later), 2 = configuration or code-level error.
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.services.ai.client import (  # noqa: E402
    GeminiModelClient,
    ModelNotConfiguredError,
    ModelResponseError,
    ModelUnavailableError,
    PromptPayload,
)


def _check_model_available(client_api_key: str, model_name: str) -> bool:
    from google import genai

    client = genai.Client(api_key=client_api_key)
    for m in client.models.list():
        if m.name == f"models/{model_name}" and "generateContent" in (m.supported_actions or []):
            print(f"[1/2] Model check: {model_name!r} is present and generateContent-capable. OK.")
            return True
    print(f"[1/2] Model check: {model_name!r} was NOT found as generateContent-capable on this account.")
    return False


async def _single_live_call(api_key: str, model_name: str) -> dict:
    client = GeminiModelClient(api_key=api_key, model=model_name)
    payload = PromptPayload(
        system_instructions="Reply only with valid JSON matching the requested shape. No prose, no markdown fences.",
        task_instructions='Return exactly this JSON object: {"status": "ok", "source": "gemini_live_probe"}',
        requester_data={},
    )
    return await client.complete_json(payload, max_tokens=50)


def main() -> int:
    settings = get_settings()
    if settings.ai_provider != "gemini":
        print(f"AI_PROVIDER is {settings.ai_provider!r}, not 'gemini' -- set AI_PROVIDER=gemini in .env to use this script.")
        return 2
    api_key = settings.gemini_api_key.get_secret_value()
    if not api_key:
        print("GEMINI_API_KEY is not configured.")
        return 2

    try:
        if not _check_model_available(api_key, settings.gemini_model):
            return 2
    except Exception as exc:  # noqa: BLE001 -- top-level diagnostic script
        print(f"[1/2] Model check failed: {type(exc).__name__}: {exc}")
        return 2

    print(f"[2/2] Making exactly one live generateContent call against {settings.gemini_model!r}...")
    try:
        result = asyncio.run(_single_live_call(api_key, settings.gemini_model))
    except ModelNotConfiguredError as exc:
        print(f"[2/2] Not configured: {exc}")
        return 2
    except ModelUnavailableError as exc:
        print(f"[2/2] BLOCKED (transient/quota) -- this is a real condition from Google, not a code defect: {exc}")
        print("      Re-run this script later; it will not retry blindly against an exhausted quota.")
        return 1
    except ModelResponseError as exc:
        print(f"[2/2] Reached Gemini but the response was not valid JSON: {exc}")
        return 2

    print(f"[2/2] SUCCESS -- live Gemini inference confirmed. Response: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
