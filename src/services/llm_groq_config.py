"""
GROQ LLM Client — sync (legacy) and async (production) variants.

Retry policy (async):
  - Max 3 attempts
  - Retries on: 429 (rate limit), 5xx (server errors), timeouts
  - Backoff: 1s → 2s → 4s between attempts (exponential)
  - Raises LLMUnavailableError after all retries are exhausted
"""

import asyncio
import logging
import os
import time
import httpx
from typing import Optional

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.3-70b-versatile"
_MAX_RETRIES = 3
_RETRY_BACKOFF_BASE = 1  # seconds; doubles each retry (1 → 2 → 4)

# HTTP status codes that are safe to retry
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


# ---------------------------------------------------------------------------
# Custom exception — raised when all async retry attempts are exhausted.
# Callers should catch this and fall back to rule-based scoring.
# ---------------------------------------------------------------------------
class LLMUnavailableError(Exception):
    """Raised when the GROQ API is unreachable after all retry attempts."""
    pass


# ---------------------------------------------------------------------------
# ASYNC (production) — use this in all async FastAPI route handlers.
# Uses httpx.AsyncClient so the FastAPI event loop is never blocked.
# ---------------------------------------------------------------------------
async def chat_completion(
    prompt: str,
    system_prompt: str = None,
    model: str = None,
    temperature: float = 0.1,
    max_tokens: int = 4096,
    json_mode: bool = False,
) -> Optional[str]:
    """
    Send a chat completion request to GROQ API asynchronously with retry.

    Args:
        prompt: The user prompt
        system_prompt: Optional system prompt for role context
        model: Override the default model (defaults to _MODEL)
        temperature: 0.0–2.0; 0.1 for evaluation, 0.5+ for conversational
        max_tokens: Maximum tokens in response

    Returns:
        Response content string

    Raises:
        LLMUnavailableError: if all 3 retry attempts fail (rate-limit / server error / timeout)
        httpx.HTTPStatusError: immediately on non-retryable HTTP errors
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY not found in environment variables")
        raise LLMUnavailableError("GROQ_API_KEY not configured")

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model or _MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_error: Optional[Exception] = None

    for attempt in range(_MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(GROQ_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if attempt > 0:
                    logger.info(f"✅ GROQ async request succeeded on attempt {attempt + 1}")
                return content

        except httpx.HTTPStatusError as e:
            last_error = e
            status_code = e.response.status_code
            if status_code in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)  # 1s, 2s, 4s
                logger.warning(
                    f"⚠️ GROQ HTTP {status_code} on attempt {attempt + 1}/{_MAX_RETRIES}. "
                    f"Retrying in {wait}s…"
                )
                await asyncio.sleep(wait)
                continue
            # Non-retryable HTTP error — fail immediately
            logger.error(
                f"❌ GROQ API HTTP {status_code} (non-retryable): {e.response.text[:200]}"
            )
            raise

        except httpx.TimeoutException as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    f"⚠️ GROQ timeout on attempt {attempt + 1}/{_MAX_RETRIES}. "
                    f"Retrying in {wait}s…"
                )
                await asyncio.sleep(wait)
                continue
            logger.error(f"❌ GROQ API timed out after {_MAX_RETRIES} attempts")

        except Exception as e:
            logger.error(f"❌ Unexpected error calling GROQ API: {e}", exc_info=True)
            raise

    raise LLMUnavailableError(
        f"GROQ API unavailable after {_MAX_RETRIES} attempts. Last error: {last_error}"
    )


# ---------------------------------------------------------------------------
# SYNC (legacy) — kept for test_connection() and any sync callers.
# Do NOT use this inside async FastAPI route handlers — it blocks the event loop.
# ---------------------------------------------------------------------------
def chat_completion_sync(
    prompt: str,
    system_prompt: str = None,
    max_tokens: int = 4096,
    temperature: float = 0.1,
    json_mode: bool = False,
) -> Optional[str]:
    """
    Synchronous GROQ request with retry.  Preserved for backwards compatibility.
    Prefer chat_completion() (async) in all production async contexts.

    Returns:
        Response content string, or None if all attempts fail
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY not found in environment variables")
        return None

    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": _MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    last_error: Optional[Exception] = None

    for attempt in range(_MAX_RETRIES):
        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(GROQ_API_URL, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                if attempt > 0:
                    logger.info(f"✅ GROQ request succeeded on attempt {attempt + 1}")
                return content

        except httpx.HTTPStatusError as e:
            last_error = e
            status = e.response.status_code
            if status in _RETRYABLE_STATUS_CODES and attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    f"⚠️ GROQ HTTP {status} on attempt {attempt + 1}/{_MAX_RETRIES}. "
                    f"Retrying in {wait}s…"
                )
                time.sleep(wait)
                continue
            logger.error(
                f"❌ GROQ API HTTP {status} (non-retryable): {e.response.text[:200]}"
            )
            return None

        except httpx.TimeoutException as e:
            last_error = e
            if attempt < _MAX_RETRIES - 1:
                wait = _RETRY_BACKOFF_BASE * (2 ** attempt)
                logger.warning(
                    f"⚠️ GROQ timeout on attempt {attempt + 1}/{_MAX_RETRIES}. "
                    f"Retrying in {wait}s…"
                )
                time.sleep(wait)
                continue
            logger.error(f"❌ GROQ API timed out after {_MAX_RETRIES} attempts")
            return None

        except Exception as e:
            logger.error(f"❌ Unexpected error calling GROQ API: {e}", exc_info=True)
            return None

    logger.error(f"❌ All {_MAX_RETRIES} GROQ attempts failed. Last error: {last_error}")
    return None


def test_connection() -> bool:
    """Test if GROQ connection is working (uses sync client)."""
    try:
        result = chat_completion_sync("Say 'OK' if you can hear me.", max_tokens=10)
        return result is not None and "OK" in result.upper()
    except Exception as e:
        logger.error(f"Connection test failed: {e}")
        return False
