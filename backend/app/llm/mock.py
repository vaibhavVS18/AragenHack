"""Deterministic offline provider.

Runs the full pipeline with no API key and no network, which makes the app
demonstrable before a key exists and makes tests reproducible.

This is scaffolding, not a substitute for the real thing. The assignment
requires genuine LLM integration, and ``LLM_PROVIDER=gemini`` is what the
submitted demo uses. Text here is composed from the classification fields by
string templates - useful for checking wiring and layout, but it is not a
clinical explanation and never claims to be.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .base import Explanation, LLMProvider

# Phrasing per severity: (opening clause, action verb).
_SEVERITY_FRAMING = {
    "critical": (
        "This result is markedly outside the reference range and is "
        "considered a critical value.",
        "Escalate immediately",
    ),
    "warning": (
        "This result falls outside the reference range but is not in the "
        "critical band.",
        "Arrange follow-up",
    ),
    "normal": (
        "This result sits within the expected reference range.",
        "No action required",
    ),
    "unknown": (
        "This result could not be interpreted against a reference range.",
        "Verify the submitted data",
    ),
}


class MockProvider(LLMProvider):
    """Composes explanations from the classification, without a model."""

    name = "mock"
    model = None

    def __init__(self, latency_seconds: float = 0.0) -> None:
        # Optional delay so loading states can be exercised in the UI.
        self._latency = latency_seconds

    async def explain(self, results: list[dict[str, Any]]) -> list[Explanation]:
        if self._latency:
            await asyncio.sleep(self._latency)
        return [self._explain_one(result) for result in results]

    @staticmethod
    def _explain_one(result: dict[str, Any]) -> Explanation:
        severity = result.get("severity", "unknown")
        opening, verb = _SEVERITY_FRAMING.get(
            severity, _SEVERITY_FRAMING["unknown"]
        )

        test = result.get("test_name", "This test")
        value = result.get("value")
        unit = result.get("unit") or ""
        measures = result.get("measures")
        specialty = result.get("specialty", "internal medicine")
        deviation = result.get("deviation_text")

        # --- explanation ---
        parts = [f"{test} measured {value} {unit}.".replace("  ", " ")]
        if measures:
            parts.append(f"This test reflects {measures}.")
        parts.append(opening)
        if deviation and severity in {"critical", "warning"}:
            parts.append(f"The value is {deviation}.")
        if severity == "unknown" and result.get("error"):
            parts.append(result["error"])

        # --- next step ---
        if severity == "critical":
            next_step = (
                f"{verb}: confirm with a repeat sample and contact "
                f"{specialty} for urgent review."
            )
        elif severity == "warning":
            next_step = (
                f"{verb}: repeat the test to confirm the trend and consider a "
                f"{specialty} referral if it persists."
            )
        elif severity == "normal":
            next_step = f"{verb}. Continue routine monitoring."
        else:
            next_step = (
                f"{verb}: check the test name, value and unit, then resubmit."
            )

        return Explanation(
            explanation=" ".join(parts),
            next_step=next_step,
        )
