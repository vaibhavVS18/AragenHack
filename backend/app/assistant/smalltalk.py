"""Greetings and pleasantries, answered without a model.

"hi" is not a question about the application, but a vector search cannot tell.
Embedded, it landed 0.487 from the corpus entry titled "Can you tell me if I am
ill, or what to take?" - comfortably above the 0.35 retrieval floor - and the
model answered *that* question instead of the greeting:

    hi
    > No, I can't tell you if you are ill or what to take. This application only
    > explains how to use the interface and analyze lab results.

A refusal to a question nobody asked. The cause is not the floor: a greeting
carries almost no lexical signal, so its embedding sits near the centre of the
space and everything scores about 0.5. Raising the threshold enough to exclude
"hi" would exclude real questions too.

So small talk never reaches retrieval. It is matched here, on the exact
normalised string, and answered from a fixed reply. That also makes the first
thing most people type instant and free, instead of a five-second round trip to
a language model that gets it wrong.

Matching is deliberately narrow. Exact whole-string equality, not substring:
"hi" must not fire on "high", and "ok" must not fire on "ok so how does the
potassium threshold work". Anything not recognised here falls through to the
normal path, which is the safe direction to be wrong in - a real question
handled as small talk would be far worse than a greeting handled as a question.
"""

from __future__ import annotations

import re

# Whole strings, already normalised. Spelling variants are listed rather than
# fuzzy-matched: the set is small, and a fuzzy match here would eventually
# swallow a real question.
GREETINGS = frozenset({
    "hi", "hii", "hiii", "hey", "heyy", "helo", "hello", "hallo", "yo",
    "hi there", "hey there", "hello there", "hiya",
    "good morning", "good afternoon", "good evening", "gm",
    "namaste", "hola", "greetings",
})

THANKS = frozenset({
    "thanks", "thank you", "thankyou", "thx", "ty", "thanks a lot",
    "thank you so much", "thanks so much", "cheers", "much appreciated",
    "appreciate it", "nice", "great", "cool", "awesome", "perfect",
})

FAREWELLS = frozenset({
    "bye", "byee", "goodbye", "good bye", "see you", "see ya", "cya",
    "later", "good night", "gn",
})

# Acknowledgements: nothing was asked, so nothing should be answered.
ACKS = frozenset({"ok", "okay", "k", "kk", "right", "i see", "got it", "sure", "yes", "no"})

CAPABILITY = frozenset({
    "who are you", "what are you", "what can you do", "what do you do",
    "help", "what can i ask", "what can i ask you", "what is this",
    "how can you help", "how can you help me",
})

_PUNCTUATION = re.compile(r"[^\w\s]+")
_SPACES = re.compile(r"\s+")


def _normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace.

    So "Hi!", "hi ", and "HI." are all one key, and the sets stay readable.
    """
    return _SPACES.sub(" ", _PUNCTUATION.sub("", text.lower())).strip()


def small_talk(question: str, *, report: bool = False) -> str | None:
    """Return a fixed reply for small talk, or None to answer normally.

    Args:
        question: What the reader typed.
        report: Whether their own results are attached. Only changes what the
            reply offers to do next - there is no point inviting someone to ask
            "which is most urgent?" when there are no results on screen.
    """
    text = _normalise(question)
    if not text:
        return None

    if text in GREETINGS or text in CAPABILITY:
        # What the reader can do, not how the internals fit together. Someone
        # who has just typed "hi" has not yet decided to care about MCP or
        # about the classification rules - they want to know what this thing is
        # for and where to start. The tour is deliberately in the order they
        # would do it: enter, read, download, ask.
        if report:
            return (
                "Hello. Your results are attached, so ask me about them - "
                "which one is most urgent, why a result was flagged, how far a "
                "value sits outside its range, or what order to deal with them "
                "in. What they mean for your health is a question for a "
                "doctor.\n\n"
                "You can also download the whole thing as a PDF report from "
                "the button above."
            )
        return (
            "Hello. Here is what you can do with this app:\n\n"
            "• Test your results - type them into the Analyze page, or upload "
            "a CSV. Each value is checked against its reference range and "
            "graded Normal, Warning or Critical.\n"
            "• Read what it means - every result gets a plain-language "
            "explanation and a suggested next step.\n"
            "• Get a report - download the whole panel as a PDF to take to a "
            "doctor.\n"
            "• Ask about your results - once you have analyzed something, "
            "press \"Ask about your report\" and I will answer from your own "
            "numbers.\n\n"
            "No results yet? Press \"Load sample\" on the Analyze page for a "
            "quick run. What would you like to know?"
        )

    if text in THANKS:
        return "You're welcome. Ask me anything else you need."

    if text in FAREWELLS:
        return "Goodbye. The panel is here whenever you need it."

    if text in ACKS:
        return "Anything else you would like to know?"

    return None


__all__ = ["small_talk"]
