"""A hard boundary around what the assistant will answer.

The system prompt already tells the model to decline medical questions. That
is not sufficient. Asked "am I going to be ok?", a 3B model with reference
ranges in its context answered "yes, if your calcium is within the normal
range you are likely to be in good health" - a personal medical judgement,
produced despite an explicit instruction not to.

Instructions are a request. This is a gate: a question that reads as personal
medical advice is refused in code, before any model sees it. Deterministic,
testable, and it cannot be talked around by phrasing.

It is intentionally narrow. "What does critical mean?" and "what is the normal
range for potassium?" are questions about the application and must still be
answered - only questions about *the reader's own health or treatment* are
turned away.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REFUSAL = (
    "I can only explain how this application works - how results are graded, "
    "what the reference ranges are, and how to use the app. I can't tell you "
    "what a result means for your health, whether you're unwell, or what to "
    "do about it. That needs a doctor who can see your full picture.\n\n"
    "If a result here is marked Critical, treat that as a reason to contact a "
    "doctor promptly rather than to read further."
)

# Personal framing: the question is about the reader, not the software.
_PERSONAL = (
    r"\bam i\b", r"\bdo i have\b", r"\bhave i got\b", r"\bwill i\b",
    r"\bam i going to\b", r"\bmy health\b", r"\bcure\b",
    r"\bshould i take\b", r"\bshould i be (?:worried|concerned|scared)\b",
    r"\bwhat should i do about my\b", r"\bis it safe for me\b",
    r"\bdo i need (?:medication|treatment|surgery|a doctor)\b",
    r"\bhow long (?:do i|have i)\b", r"\bwhat is wrong with me\b",
    r"\bdiagnos(?:e|is) me\b", r"\bam i (?:ok|okay|fine|dying|sick|ill)\b",
)

# Clinical asks that are out of scope however they are phrased.
_CLINICAL = (
    r"\bwhat (?:medication|medicine|drug|dose|dosage)\b",
    r"\bshould (?:i|he|she|they) (?:stop|start) taking\b",
    r"\bhow do i (?:treat|cure|fix) \b",
    r"\btreatment for\b", r"\bprescri(?:be|ption)\b",
    r"\bwhat (?:disease|condition|illness) (?:do|does)\b",
    r"\bdiet plan\b", r"\bhome remed(?:y|ies)\b",
    # Procedure questions. "Tell me how to test for glucose" produced an
    # answer about drawing blood from a vein - invented, because nothing in
    # the corpus describes phlebotomy. This app reads results that already
    # exist; it does not perform tests.
    r"\bhow (?:is|are|do you) .{0,24}(?:blood|sample|specimen) (?:drawn|taken|collected)\b",
    r"\bwhere can i (?:get|have|do) \b",
    r"\bhow do i get (?:tested|a test|my blood)\b",
    r"\bget tested\b",
    r"\b(?:fasting|prepare) (?:for|before) (?:a |the )?(?:blood )?test\b",
)

# These override the patterns above: they are about the software even when
# phrased personally. "Can I trust this?" is a question about the app.
_ABOUT_THE_APP = (
    r"\bthis app\b", r"\bthe app\b", r"\bapplication\b", r"\bwebsite\b",
    r"\bhow does (?:it|this|the app)\b", r"\bwhat does (?:critical|warning|normal)\b",
    r"\breference range\b", r"\bupload\b", r"\bcsv\b", r"\bpdf\b", r"\breport\b",
    r"\bmcp\b", r"\bclassif\w*\b", r"\bthreshold\b",
)

_PERSONAL_RE = tuple(re.compile(p, re.I) for p in _PERSONAL)
_CLINICAL_RE = tuple(re.compile(p, re.I) for p in _CLINICAL)
_APP_RE = tuple(re.compile(p, re.I) for p in _ABOUT_THE_APP)


@dataclass(frozen=True)
class ScopeCheck:
    """Whether a question may be answered."""

    allowed: bool
    reason: str = ""


def check_scope(question: str) -> ScopeCheck:
    """Decide whether a question is about the application or about health.

    Returns ``allowed=False`` for questions seeking a personal medical
    judgement, diagnosis or treatment.
    """
    text = re.sub(r"\s+", " ", question.lower()).strip()

    # A clear reference to the software wins: "how does this app decide if I
    # am at risk" is a question about the classifier.
    if any(pattern.search(text) for pattern in _APP_RE):
        return ScopeCheck(allowed=True)

    if any(pattern.search(text) for pattern in _CLINICAL_RE):
        return ScopeCheck(allowed=False, reason="clinical")

    if any(pattern.search(text) for pattern in _PERSONAL_RE):
        return ScopeCheck(allowed=False, reason="personal")

    return ScopeCheck(allowed=True)
