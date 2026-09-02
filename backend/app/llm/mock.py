"""Deterministic offline provider.

Runs the full pipeline with no API key and no network, which makes the app
demonstrable before a key exists and makes tests reproducible.

This is scaffolding, not a substitute for the real thing. The assignment
requires genuine LLM integration, and ``LLM_PROVIDER=gemini`` is what the
submitted demo uses. Text here is composed from the classification fields by
string templates - enough to check wiring and layout, but it is not a clinical
explanation and never claims to be.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .base import Explanation, LLMProvider

# Per severity: (headline verb, urgency, urgency reason).
_FRAMING = {
    "critical": (
        "is far outside the normal range and needs prompt medical attention",
        "urgent",
        "Values this far outside the normal range can affect how the body works and should be reviewed quickly.",
    ),
    "warning": (
        "is outside the normal range, though not severely",
        "soon",
        "A single out-of-range result often settles on its own, but it should be checked rather than ignored.",
    ),
    "normal": (
        "is within the normal range",
        "routine",
        "Nothing here needs action beyond your usual check-ups.",
    ),
    "unknown": (
        "could not be interpreted",
        "soon",
        "Without a reference range the value cannot be judged either way.",
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
        phrase, urgency, urgency_reason = _FRAMING.get(severity, _FRAMING["unknown"])

        test = result.get("test_name", "This test")
        value = result.get("value")
        unit = result.get("unit") or ""
        measures = result.get("measures") or "a substance measured in the blood"
        specialty = result.get("specialty", "your doctor")
        reference = result.get("reference_range")
        deviation = result.get("deviation_text")

        # --- what this result means ---
        parts = [f"Your {test.lower()} result is {value} {unit}.".replace("  ", " ")]
        if reference:
            parts.append(
                f"The normal range is {reference['low']} to {reference['high']} "
                f"{reference['unit']}."
            )
        if deviation and severity in {"critical", "warning"}:
            parts.append(f"That is {deviation}.")
        if severity == "unknown" and result.get("error"):
            parts.append(result["error"])
        elif severity == "normal":
            parts.append("No action is needed based on this result alone.")

        # --- causes and steps ---
        if severity in {"critical", "warning"}:
            causes = (
                "a temporary change such as illness, dehydration or medication",
                "an underlying condition that needs investigating",
                "natural variation between tests",
            )
            steps = (
                f"Contact {specialty} and share this result.",
                "Ask for a repeat test to confirm the reading.",
                "Mention any recent illness, new medication or changes in how you feel.",
            )
            questions = (
                f"Is this {test.lower()} result likely to be temporary?",
                "What would you like to check next, and how soon?",
            )
        elif severity == "unknown":
            causes = ("the test name or unit was not recognised",)
            steps = (
                "Check the test name, value and unit, then submit it again.",
                "If the test is correct, ask the laboratory for its reference range.",
            )
            questions = ()
        else:
            causes = ()
            steps = ("Keep to your usual testing schedule.",)
            questions = ()

        return Explanation(
            headline=f"Your {test.lower()} {phrase}.",
            what_it_measures=(
                f"{test} reflects {measures}. It is measured to check how well "
                "that part of the body is working."
            ),
            what_result_means=" ".join(parts),
            urgency=urgency,
            urgency_reason=urgency_reason,
            possible_causes=causes,
            next_steps=steps,
            questions_to_ask=questions,
        )
