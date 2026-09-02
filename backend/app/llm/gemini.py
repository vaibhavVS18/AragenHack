"""Google Gemini provider - batched, structured clinical explanations.

One request covers a whole batch of results. Calling per result would multiply
latency and rate-limit pressure by the number of rows while producing no better
output, since each explanation is independent of the others.

Reliability measures, in order of importance:

* **Structured output.** The model is given a response schema and asked for
  ``application/json``, so the reply is machine-readable by construction rather
  than by prompt-begging.
* **Order is the contract.** Explanation *n* belongs to result *n*. A mismatch
  in length is treated as failure rather than silently realigned, because
  attaching the wrong advice to the wrong test is the worst bug this app could
  have.
* **Bounded retries.** Transient errors (rate limits, timeouts) are retried
  with backoff; authentication and quota errors are not, since retrying those
  only wastes the user's time.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from google import genai
from google.genai import types

from .base import (
    SYSTEM_PROMPT,
    Explanation,
    LLMProvider,
    LLMUnavailableError,
    build_user_prompt,
    parse_explanations,
)

logger = logging.getLogger(__name__)

# Low but non-zero: clinical language should be consistent between runs, while
# still reading naturally rather than templated.
TEMPERATURE = 0.3

MAX_ATTEMPTS = 3
BACKOFF_SECONDS = (1.0, 3.0)

# Substrings identifying errors that will not improve on retry. A retired or
# misspelled model name is as permanent as a bad key: retrying it only delays
# the fallback to classifications-without-explanations.
PERMANENT_ERROR_MARKERS = (
    "api key not valid",
    "api_key_invalid",
    "invalid api key",
    "permission denied",
    "permission_denied",
    "unauthenticated",
    "unauthorized",
    "billing",
    "quota exceeded",
    "not_found",
    "no longer available",
    "is not found",
)

# The shape every response must take: an array of objects, one per result.
RESPONSE_SCHEMA = types.Schema(
    type=types.Type.ARRAY,
    items=types.Schema(
        type=types.Type.OBJECT,
        required=["explanation", "next_step"],
        properties={
            "explanation": types.Schema(
                type=types.Type.STRING,
                description=(
                    "1-3 sentences on what this result means clinically, "
                    "referencing the value and its distance from the "
                    "reference range."
                ),
            ),
            "next_step": types.Schema(
                type=types.Type.STRING,
                description=(
                    "One concrete action, with urgency matching the severity."
                ),
            ),
        },
    ),
)


class GeminiProvider(LLMProvider):
    """Generates explanations with the Gemini API."""

    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-3.5-flash-lite") -> None:
        if not api_key or not api_key.strip():
            raise LLMUnavailableError("GEMINI_API_KEY is empty.")

        self.model = model
        self._client = genai.Client(api_key=api_key.strip())

    async def explain(self, results: list[dict[str, Any]]) -> list[Explanation]:
        """Generate an explanation and next step for each classified result."""
        if not results:
            return []

        prompt = build_user_prompt(results)
        raw = await self._generate_with_retries(prompt)
        return parse_explanations(raw, expected=len(results))

    # -- request -----------------------------------------------------------

    async def _generate_with_retries(self, prompt: str) -> str:
        """Call the API, retrying only errors that might succeed later."""
        last_error: Exception | None = None

        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                return await self._generate(prompt)
            except LLMUnavailableError:
                raise                      # already classified as permanent
            except Exception as exc:
                last_error = exc
                if _is_permanent(exc):
                    raise LLMUnavailableError(
                        f"Gemini rejected the request: {exc}"
                    ) from exc

                if attempt < MAX_ATTEMPTS:
                    delay = BACKOFF_SECONDS[attempt - 1]
                    logger.warning(
                        "Gemini attempt %d/%d failed (%s); retrying in %.0fs",
                        attempt, MAX_ATTEMPTS, exc, delay,
                    )
                    await asyncio.sleep(delay)

        raise LLMUnavailableError(
            f"Gemini failed after {MAX_ATTEMPTS} attempts: {last_error}"
        )

    async def _generate(self, prompt: str) -> str:
        """One API call, returning the raw response text."""
        response = await self._client.aio.models.generate_content(
            model=self.model,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                response_mime_type="application/json",
                response_schema=RESPONSE_SCHEMA,
                temperature=TEMPERATURE,
            ),
        )

        text = getattr(response, "text", None)
        if not text or not text.strip():
            # Usually a safety block or an empty candidate list. Surfacing the
            # reason is more useful than a generic parse failure downstream.
            reason = _blocked_reason(response)
            raise LLMUnavailableError(
                f"Gemini returned no text{f' ({reason})' if reason else ''}."
            )
        return text


def _is_permanent(exc: Exception) -> bool:
    """True for errors that retrying cannot fix."""
    message = str(exc).lower()
    return any(marker in message for marker in PERMANENT_ERROR_MARKERS)


def _blocked_reason(response: Any) -> str | None:
    """Extract why a response came back empty, when the SDK says."""
    feedback = getattr(response, "prompt_feedback", None)
    if feedback and getattr(feedback, "block_reason", None):
        return f"blocked: {feedback.block_reason}"

    candidates = getattr(response, "candidates", None) or []
    if candidates and getattr(candidates[0], "finish_reason", None):
        return f"finish_reason: {candidates[0].finish_reason}"

    return None
