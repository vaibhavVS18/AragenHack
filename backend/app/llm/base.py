"""Provider-agnostic interface for the Explain step.

The agent depends on this interface, never on a concrete provider, so Gemini
can be swapped for Claude, Ollama or the offline mock by changing one env
variable.

Division of labour, which is the core design rule of this project:

* Classification is computed in ``mcp_server/tools.py``. It is deterministic
  and never involves a language model.
* Explanation is generated here. The model receives a result that has
  *already* been classified and is asked to describe what it means, never to
  decide what it is.

The prompt builder below encodes that rule explicitly, so any provider
implementing this interface inherits the same guarantee.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class LLMUnavailableError(RuntimeError):
    """The provider could not be reached or returned unusable output.

    Never fatal to a request: the agent catches this and returns
    classifications without explanations, because the clinically important
    half of the answer does not depend on the model.
    """


@dataclass(frozen=True)
class Explanation:
    """One result's generated prose."""

    explanation: str
    next_step: str


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You are a clinical decision-support assistant helping a healthcare provider \
interpret laboratory results.

The results below have ALREADY been classified by a deterministic rules engine \
that compared each value against published reference ranges. The severity of \
each result is a given fact. Do not re-classify, dispute, or second-guess it.

Your task is to explain each result and suggest a next step.

For each result write:
  - "explanation": 1-3 sentences on what this value means clinically. Name the \
condition it suggests where one is clearly indicated, and say why it matters. \
Address the provider, not the patient. Reference the actual value and how far \
it sits from the reference range.
  - "next_step": one concrete action. Match urgency to severity - critical \
results warrant immediate action, warnings warrant follow-up or repeat \
testing, normal results usually need no action beyond routine monitoring. \
Name the relevant specialty when a referral is appropriate.

Rules:
  - Be specific and clinically grounded. Avoid filler such as "consult your \
doctor" with no further detail.
  - Never state or imply a definitive diagnosis. Lab values suggest; they do \
not confirm.
  - Explain normal results too, briefly - confirming what is reassuring has \
clinical value.
  - Keep each field under 60 words.

Return ONLY a JSON array, one object per result, in the SAME ORDER as the \
input, each with exactly the keys "explanation" and "next_step". No prose \
outside the JSON.\
"""


def build_result_payload(result: dict[str, Any]) -> dict[str, Any]:
    """Reduce a classified result to the fields the model needs.

    Sending the whole dict would bury the relevant facts in bookkeeping. This
    keeps the prompt focused and the token count low.
    """
    payload: dict[str, Any] = {
        "test_name": result.get("test_name"),
        "value": result.get("value"),
        "unit": result.get("unit"),
        "severity": result.get("severity"),
        "measures": result.get("measures"),
        "specialty": result.get("specialty"),
    }

    reference = result.get("reference_range")
    if reference:
        payload["normal_range"] = f"{reference['low']}-{reference['high']} {reference['unit']}"
    if result.get("deviation_text"):
        payload["deviation"] = result["deviation_text"]
    if result.get("notes"):
        payload["note"] = result["notes"]

    return payload


def build_user_prompt(results: list[dict[str, Any]]) -> str:
    """Render the classified batch as the user turn of the prompt."""
    payloads = [build_result_payload(r) for r in results]
    return (
        f"Explain these {len(payloads)} classified lab results.\n\n"
        f"{json.dumps(payloads, indent=2)}\n\n"
        f"Return a JSON array of exactly {len(payloads)} objects, in the same order."
    )


def parse_explanations(raw: str, expected: int) -> list[Explanation]:
    """Parse a model response into explanations.

    Tolerates the usual deviations - markdown code fences, or a wrapper object
    around the array - because a rigid parser turns a cosmetic formatting
    difference into a failed request.

    Raises:
        LLMUnavailableError: if no array of the expected length can be found.
    """
    text = raw.strip()

    # Strip a ```json ... ``` fence if present.
    if text.startswith("```"):
        text = text.split("\n", 1)[-1] if "\n" in text else text
        text = text.rsplit("```", 1)[0].strip()

    # Fall back to the outermost bracketed array.
    if not text.startswith("["):
        start, end = text.find("["), text.rfind("]")
        if start != -1 and end > start:
            text = text[start:end + 1]

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LLMUnavailableError(
            f"Model returned unparseable JSON: {raw[:200]}"
        ) from exc

    if isinstance(data, dict):
        # Some models wrap the array, e.g. {"results": [...]}.
        for value in data.values():
            if isinstance(value, list):
                data = value
                break

    if not isinstance(data, list):
        raise LLMUnavailableError("Model response was not a JSON array.")

    if len(data) != expected:
        raise LLMUnavailableError(
            f"Model returned {len(data)} explanations for {expected} results."
        )

    return [
        Explanation(
            explanation=str(item.get("explanation", "")).strip(),
            next_step=str(item.get("next_step", "")).strip(),
        )
        for item in data
    ]


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """What the agent requires of an explanation provider."""

    #: Provider identifier reported in the API response metadata.
    name: str = "base"
    #: Specific model used, when the provider has one.
    model: str | None = None

    @abstractmethod
    async def explain(self, results: list[dict[str, Any]]) -> list[Explanation]:
        """Generate an explanation and next step for each classified result.

        Args:
            results: Classified results, already ordered by severity.

        Returns:
            One Explanation per input result, in the same order.

        Raises:
            LLMUnavailableError: if the provider fails. The agent degrades to
                classifications without explanations rather than failing.
        """
        raise NotImplementedError
