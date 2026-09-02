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

Shape of the explanation
------------------------
The model returns a structured object rather than a paragraph. Free prose
tends to produce two dense clinical sentences that a non-specialist cannot act
on, and it cannot be laid out. Named fields force the model to answer the
questions a reader actually has - what is this test, what does my number mean,
why might it be off, what do I do, how soon - and let the UI render them as a
table.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

URGENCY_LEVELS = ("emergency", "urgent", "soon", "routine")


class LLMUnavailableError(RuntimeError):
    """The provider could not be reached or returned unusable output.

    Never fatal to a request: the agent catches this and returns
    classifications without explanations, because the clinically important
    half of the answer does not depend on the model.
    """


@dataclass(frozen=True)
class Explanation:
    """One result explained, in the fields a reader actually asks about."""

    headline: str
    what_it_measures: str
    what_result_means: str
    urgency: str
    urgency_reason: str
    possible_causes: tuple[str, ...] = field(default_factory=tuple)
    next_steps: tuple[str, ...] = field(default_factory=tuple)
    questions_to_ask: tuple[str, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """\
You explain laboratory results to the person whose results they are. Assume an \
intelligent adult with no medical training: someone who can follow a clear \
explanation but does not know what a reference range is, what an analyte does, \
or which specialist handles what.

Every result below has ALREADY been classified by a deterministic rules engine \
that compared the value against a reference range. The severity of each result \
is a given fact. Do not re-classify it, dispute it, hedge about it, or say a \
value "may be" abnormal when it has been measured as abnormal.

Return one JSON object per result with exactly these fields:

"headline"
    One sentence, maximum 20 words, in plain English, stating what this result \
shows. This is the only line some readers will read. Lead with the meaning, \
not the number. Good: "Your red blood cell count is slightly higher than \
normal." Bad: "Hemoglobin 17.8 g/dL, mildly elevated."

"what_it_measures"
    One or two sentences on what this test actually measures and why it is \
worth measuring, in everyday language. Explain the biology briefly. Do not \
mention this particular result here - this field is the same regardless of the \
value.

"what_result_means"
    Two to four sentences interpreting THIS value. State the number, the \
normal range, and how far outside it sits. Then explain what that difference \
means for the body in practical terms - what could be happening, and what the \
consequence of it is. If the result is normal, say plainly that it is normal \
and what that rules out. Define any medical term the moment you use it, in \
parentheses: "erythrocytosis (too many red blood cells)".

"possible_causes"
    An array of 2 to 4 short strings: the common reasons a result like this \
occurs, most likely first. Include benign and everyday causes where they are \
genuinely plausible - dehydration, recent illness, medication, diet - not only \
serious ones. Each entry is a short phrase, not a sentence. Empty array for a \
normal result.

"urgency"
    Exactly one of: "emergency", "urgent", "soon", "routine".
        emergency - needs medical attention today; a delay carries real risk
        urgent    - contact a doctor within a few days
        soon      - raise at the next appointment, or book one in a few weeks
        routine   - no action needed beyond normal check-ups
    Match this to the severity given. Critical results are "emergency" or \
"urgent". Normal results are "routine".

"urgency_reason"
    One short sentence saying why that urgency, in plain terms. What is the \
actual risk of waiting?

"next_steps"
    An array of 2 to 4 concrete actions, in the order to do them. Write them \
as instructions to the reader, starting with a verb. Be specific about WHO to \
contact and WHAT will likely happen: "Book an appointment with your GP and ask \
for a repeat test to confirm the reading" beats "Follow up with your doctor". \
Name the relevant specialty when a referral is genuinely likely. For a normal \
result, give the honest short answer: keep to routine testing.

"questions_to_ask"
    An array of 2 to 3 questions the reader could ask their doctor about this \
result. Make them specific to this test and this value, not generic. Empty \
array for a normal result.

Rules:
  - Plain language throughout. No jargon unless you define it in the same \
sentence.
  - Never give a definitive diagnosis. Lab values suggest and prompt \
investigation; they do not confirm.
  - Never tell the reader to ignore an abnormal result, and never alarm them \
about a normal one.
  - Do not invent numbers. Use only the values supplied.
  - Do not include a disclaimer about consulting a professional - the \
interface already carries one.

Return ONLY a JSON array, one object per result, in the SAME ORDER as the \
input. No prose outside the JSON.\
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
    if result.get("direction") in {"below", "above"}:
        payload["direction"] = result["direction"]
    if result.get("comparison") == "qualitative":
        payload["note"] = (
            "This is a qualitative result: it records whether something is "
            "present, not how much."
        )
    if result.get("notes"):
        payload["data_quality_note"] = result["notes"]
    if result.get("error"):
        payload["could_not_interpret"] = result["error"]

    return payload


def build_user_prompt(results: list[dict[str, Any]]) -> str:
    """Render the classified batch as the user turn of the prompt."""
    payloads = [build_result_payload(r) for r in results]
    return (
        f"Explain these {len(payloads)} classified lab results.\n\n"
        f"{json.dumps(payloads, indent=2)}\n\n"
        f"Return a JSON array of exactly {len(payloads)} objects, in the same order."
    )


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _as_tuple(value: Any, limit: int = 5) -> tuple[str, ...]:
    """Coerce a list-ish field into a tuple of non-empty strings."""
    if not value:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return ()
    return tuple(str(v).strip() for v in value[:limit] if str(v).strip())


def _urgency(value: Any, fallback: str = "routine") -> str:
    text = str(value or "").strip().lower()
    return text if text in URGENCY_LEVELS else fallback


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
            headline=str(item.get("headline", "")).strip(),
            what_it_measures=str(item.get("what_it_measures", "")).strip(),
            what_result_means=str(item.get("what_result_means", "")).strip(),
            urgency=_urgency(item.get("urgency")),
            urgency_reason=str(item.get("urgency_reason", "")).strip(),
            possible_causes=_as_tuple(item.get("possible_causes")),
            next_steps=_as_tuple(item.get("next_steps")),
            questions_to_ask=_as_tuple(item.get("questions_to_ask"), limit=3),
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
        """Generate a structured explanation for each classified result.

        Args:
            results: Classified results, already ordered by severity.

        Returns:
            One Explanation per input result, in the same order.

        Raises:
            LLMUnavailableError: if the provider fails. The agent degrades to
                classifications without explanations rather than failing.
        """
        raise NotImplementedError
