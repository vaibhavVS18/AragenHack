"""The assistant: retrieve, then answer from what was retrieved.

Flow for one question:

    detect tone -> embed question -> search index -> build prompt -> generate

Two rules shape the whole thing.

**Grounded only.** The model answers from retrieved chunks and is told to say
so when they do not cover the question. An assistant that improvises about a
clinical tool is worse than one that admits a gap.

**Application scope only.** It explains how this system works - thresholds,
severities, MCP, CSV handling. It does not answer medical questions. A local
4B model dispensing unsourced clinical advice is precisely the failure this
application is built to avoid, so the refusal is in the prompt and enforced by
what is in the corpus.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..config import Settings
from .corpus import build_corpus
from .embeddings import (
    EmbeddingUnavailable,
    _model_present,
    get_embedding_provider,
    ollama_available,
)
from .scope import REFUSAL, check_scope
from .sentiment import Tone, detect_tone
from .smalltalk import small_talk
from .store import Match, VectorStore

logger = logging.getLogger(__name__)

INDEX_PATH = Path(__file__).resolve().parent.parent.parent / ".assistant_index"

# A local model on CPU is not fast; the widget shows progress rather than
# timing out early.
CHAT_TIMEOUT = httpx.Timeout(120.0, connect=5.0)

# How much of each retrieved chunk reaches the prompt. Prompt length is what
# costs time on CPU: trimming 5 chunks of 1400 chars to 3 of 700 cut a typical
# answer from about seven seconds to under three.
PROMPT_CHUNK_CHARS = 700

# Answers are meant to be two or three short paragraphs; a larger budget only
# gives the model room to ramble, and every token is generated serially.
MAX_ANSWER_TOKENS = 260

# Keep the model resident between questions. Reloading it on each request adds
# seconds to the first answer after any pause.
KEEP_ALIVE = "10m"

SYSTEM_PROMPT = """\
You are the built-in assistant for Aragen AI, a clinical lab results \
analyzer. You answer questions about how this application works.

Answer ONLY from the CONTEXT below. If the context does not contain the \
answer, say so plainly and suggest where in the app to look. Never invent a \
threshold, a number, or a behaviour that is not in the context.

You do NOT give medical advice. If asked whether a person is ill, what \
condition they have, what treatment to take, or anything about their health \
beyond what this application computes, say that you can only explain how the \
application works and that medical questions belong with a doctor. Explaining \
what a severity level means, or what a reference range is, IS in scope - \
diagnosing or advising is not.

Be concise: two or three short paragraphs at most, fewer if the question is \
simple. Use plain language.

Write the answer and nothing else. Do not narrate your process, do not think \
out loud, and do not refer to "the context", "section [1]" or "the documents". \
Never begin with phrases like "Looking at", "Let me", "I need to" or "The user \
is asking". Start immediately with the answer itself.\
"""


# The system prompt for questions about one particular set of results.
#
# Deliberately standalone, and deliberately not built on SYSTEM_PROMPT. The two
# were merged at first - the report was appended to the documentation prompt
# and retrieval ran as usual - and the retrieved passages won. Asked "why is it
# critical?" about a real panel, the assistant returned a textbook definition of
# criticality drawn from three documentation chunks, and never looked at the
# reader's value at all.
#
# There is nothing to retrieve here. The report is the entire ground, so the
# prompt says so and never mentions context, sources or documents.
#
# The line about what may not be said is the whole safety of the feature:
# restating what the application already computed is explaining; going beyond it
# is diagnosing, and a small local model reading real lab values is exactly
# where that would happen if it were left implicit.
REPORT_SYSTEM = """\
You are the built-in assistant for Aragen AI, a clinical lab results analyzer. \
The reader is looking at their own results, shown below, and is asking you \
about them.

Answer from THEIR RESULTS. Name the specific test and quote its value and its \
range. Never answer with a general definition when a specific result is being \
asked about, and never refer to "the results" in the abstract when you can name \
the test.

What you may do: say which result is most urgent and why, restate the \
comparison that produced a severity, explain how far a value sits from its \
range, say what order to deal with them in, and repeat the next step that was \
already generated for a result.

What you must NOT do: add any clinical judgement that is not already in the \
results. Do not say whether the reader is ill, name a condition they might \
have, predict an outcome, suggest a treatment or a medication, or interpret \
several results together as a pattern. If asked for any of that, say it needs a \
doctor who can see their full picture.

Quote the numbers exactly as given. Never estimate, round differently, or infer \
a value that is not present. If the results do not contain what is being asked \
for, say that plainly.

Be concise: two or three short sentences unless more is genuinely needed. Use \
plain language.

Write the answer and nothing else. Do not narrate your process and do not think \
out loud. Never begin with "Looking at", "Let me", "I need to" or "The user is \
asking". Start immediately with the answer.\
"""


# Reasoning models sometimes narrate before answering even when thinking is
# disabled. Belt and braces: strip an explicit <think> block, and drop a
# leading paragraph that is clearly the model talking to itself.
_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.S | re.I)
# A leaked opening line looks like: 'Hmm, the user is asking about X.'
# Matched with plain string logic rather than a regex - it is easier to
# read, and only ever removes a first line that is unambiguously the model
# talking to itself.
_META_STARTERS = ("hmm", "okay", "ok", "alright", "right", "so", "first")
_META_MARKERS = (
    "the user", "user is asking", "i need to", "i should", "let me",
    "i will", "i'll",
)


def _strip_reasoning(text: str) -> str:
    """Remove chain-of-thought that leaked into the answer.

    Reasoning models sometimes narrate before answering even with thinking
    disabled. Two passes: an explicit <think> block, then a first line that
    is clearly the model addressing itself rather than the reader.
    """
    text = _THINK_BLOCK.sub("", text).strip()
    lines = text.split(chr(10))
    if len(lines) > 1:
        first = lines[0].strip().lower()
        if first.startswith(_META_STARTERS) and any(
            marker in first for marker in _META_MARKERS
        ):
            return chr(10).join(lines[1:]).strip()

    return text


class AssistantUnavailable(RuntimeError):
    """No usable embedding or chat backend."""


@dataclass(frozen=True)
class Source:
    """A chunk that informed an answer, for showing provenance."""

    title: str
    source: str
    score: float


@dataclass(frozen=True)
class Answer:
    """One answered question."""

    answer: str
    sources: list[Source]
    tone: str
    engine: str
    grounded: bool


class AssistantService:
    """Owns the index and answers questions against it.

    The index is built once, lazily, on the first question, and reused after.
    Building it embeds the whole corpus, which takes several seconds locally -
    doing it at startup would delay every boot for a feature most requests
    never touch.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._store: VectorStore | None = None
        self._provider: Any = None
        # Concurrent first questions would otherwise each build the index.
        self._lock = asyncio.Lock()

    # -- index -------------------------------------------------------------

    @property
    def is_indexed(self) -> bool:
        """Whether the index is already built and in memory.

        Lets the route skip fetching the reference catalogue over MCP. That
        catalogue is only used to *build* the index; once built it is ignored,
        so every question after the first was paying about 1.5 seconds for a
        round trip whose result went straight in the bin.
        """
        return self._store is not None

    async def _ensure_index(self, catalogue: dict[str, Any] | None) -> VectorStore:
        if self._store is not None:
            return self._store

        async with self._lock:
            if self._store is not None:  # built while waiting for the lock
                return self._store

            try:
                self._provider = await get_embedding_provider(self._settings)
            except EmbeddingUnavailable as exc:
                raise AssistantUnavailable(str(exc)) from exc

            cached = VectorStore.load(INDEX_PATH, self._provider.signature)
            if cached is not None:
                logger.info("Assistant index loaded (%d chunks)", len(cached.chunks))
                self._store = cached
                return cached

            chunks = build_corpus(catalogue)
            logger.info("Building assistant index over %d chunks…", len(chunks))

            vectors = await self._provider.embed([c.for_embedding() for c in chunks])
            store = VectorStore.build(chunks, vectors, self._provider.signature)
            store.save(INDEX_PATH)

            logger.info("Assistant index built with %s", self._provider.signature)
            self._store = store
            return store

    async def rebuild(self, catalogue: dict[str, Any] | None = None) -> int:
        """Discard and rebuild the index. Returns the chunk count."""
        self._store = None
        store = await self._ensure_index(catalogue)
        return len(store.chunks)

    # -- answering ---------------------------------------------------------

    async def ask(self, question: str,
                  catalogue: dict[str, Any] | None = None,
                  history: list[tuple[str, str]] | None = None) -> Answer:
        """Answer a question about the application.

        Questions about a reader's own results do not come here - they go to
        :meth:`ask_about_report`, which retrieves nothing. Serving both from
        one path meant the documentation competed with the reader's results and
        won: "why is it critical?" about a real panel came back as a textbook
        definition assembled from three doc chunks.

        ``history`` is the recent conversation as ``(role, text)`` pairs,
        oldest first, supplied by the client on every request. The server holds
        no session: a conversation that lives only in the caller's own state
        cannot be handed to the wrong reader, and there is nothing to expire.

        Raises:
            AssistantUnavailable: if no backend can be reached.
        """
        history = list(history or [])
        tone = detect_tone(question)

        # Before the scope guard and before retrieval. A greeting has almost no
        # lexical signal, so it retrieves whatever sits nearest the centre of
        # the embedding space - which for "hi" was the entry on whether the app
        # can tell you if you are ill, and the model answered that instead.
        chat = small_talk(question)
        if chat:
            return Answer(
                answer=chat,
                sources=[],
                tone=tone.label,
                engine="small-talk",
                grounded=True,
            )

        # Checked before anything else. The prompt already asks the model to
        # decline medical questions and the model complied with the user
        # instead - "am I going to be ok?" came back as a personal health
        # judgement. A gate in code cannot be talked around, and it answers
        # instantly rather than after a generation.
        scope = check_scope(question)
        if not scope.allowed:
            return Answer(
                answer=REFUSAL,
                sources=[],
                tone=tone.label,
                engine="scope-guard",
                grounded=True,
            )

        store = await self._ensure_index(catalogue)

        # A follow-up is a bad search query on its own. "what about the second
        # one?" shares no words with anything in the corpus. It is anchored to
        # the question that opened the conversation rather than to the message
        # immediately before it: the previous turn is often itself a follow-up
        # ("say that again in simpler words"), and chaining one vague query
        # onto another drifts further from the subject with every turn.
        opening = next((text for role, text in history if role == "user"), None)
        retrieval_query = (
            f"{opening} {question}" if opening and len(question) < 80 else question
        )

        query_vector = (await self._provider.embed([retrieval_query]))[0]
        matches = store.search(
            query_vector,
            top_k=self._settings.assistant_top_k,
            min_score=self._settings.assistant_min_score,
        )

        if not matches:
            # Refuse rather than let the model fill the gap from its own
            # weights: an ungrounded answer about a clinical tool is the one
            # thing this assistant must not produce.
            return Answer(
                answer=(
                    "I do not have anything on that. I can explain how results "
                    "are classified, what the reference ranges are, how the MCP "
                    "tools work, or how to upload a CSV — try asking about one "
                    "of those."
                ),
                sources=[],
                tone=tone.label,
                engine="none",
                grounded=False,
            )

        system, user = self._build_prompt(question, matches, tone)
        text, engine = await self._generate(system, user, history)

        return Answer(
            answer=text,
            sources=[
                Source(title=m.chunk.title, source=m.chunk.source,
                       score=round(m.score, 3))
                for m in matches
            ],
            tone=tone.label,
            engine=engine,
            grounded=True,
        )

    @staticmethod
    def _build_prompt(question: str, matches: list[Match], tone: Tone,
                      ) -> tuple[str, str]:
        """Return ``(system, user)``.

        Split rather than concatenated so the chat endpoint can put each in
        its proper role. Instructions placed in a user turn are followed far
        less reliably than the same instructions in a system turn.
        """
        context = "\n\n".join(
            f"[{i + 1}] {m.chunk.title}\n{m.chunk.text}"
            for i, m in enumerate(matches)
        )
        system = f"{SYSTEM_PROMPT}\n\nTONE GUIDANCE: {tone.directive}"
        user = f"CONTEXT:\n{context}\n\nQUESTION: {question}"
        return system, user

    # -- answering about one report ---------------------------------------

    async def ask_about_report(
        self,
        question: str,
        report: str,
        history: list[tuple[str, str]] | None = None,
    ) -> Answer:
        """Answer a question about one particular set of results.

        No retrieval, no index, no embedding call. The reader's results are the
        entire ground, and the corpus has nothing to add that would not compete
        with them - which is precisely what went wrong when this shared the
        retrieval path: three documentation chunks outvoted the one thing the
        question was actually about.

        Dropping the embedding also takes roughly 700ms off every answer, which
        is most of the gap between this feeling like a chat and feeling like a
        search.

        Args:
            question: What the reader asked.
            report: The digest of the results they are looking at.
            history: Earlier turns of *this* report's conversation, oldest
                first. The caller drops these when a new analysis replaces the
                report, so answers can never mix two panels.

        Raises:
            AssistantUnavailable: if no backend can be reached.
        """
        history = list(history or [])
        tone = detect_tone(question)

        chat = small_talk(question, report=True)
        if chat:
            return Answer(
                answer=chat,
                sources=[],
                tone=tone.label,
                engine="small-talk",
                grounded=True,
            )

        # The same gate as the documentation assistant, for the same reason,
        # and it matters more here: the model is holding real values, so a
        # question like "am I going to be ok?" has everything it needs to
        # answer badly.
        scope = check_scope(question)
        if not scope.allowed:
            return Answer(
                answer=REFUSAL,
                sources=[],
                tone=tone.label,
                engine="scope-guard",
                grounded=True,
            )

        system = (
            f"{REPORT_SYSTEM}\n\nTONE GUIDANCE: {tone.directive}\n\n"
            f"THE READER'S RESULTS:\n{report}"
        )
        text, engine = await self._generate(system, f"QUESTION: {question}", history)

        # No sources: the answer is grounded in the reader's own results, which
        # are already on the screen beside it. Citing the report back to the
        # person looking at it would be noise.
        return Answer(
            answer=text,
            sources=[],
            tone=tone.label,
            engine=engine,
            grounded=True,
        )

    # -- generation --------------------------------------------------------

    async def _generate(self, system: str, user: str,
                        history: list[tuple[str, str]] | None = None) -> tuple[str, str]:
        """Generate with the local Ollama model. No fallback.

        Local only, deliberately. A hosted fallback looks like resilience and
        is not: the corpus is embedded by nomic-embed-text into a 768-dimension
        space, and Gemini embeds into 3072, so the moment the embedding backend
        changes the existing index is unusable and has to be rebuilt from
        scratch mid-question. Falling back also moves the reader's own lab
        values off their machine without telling them, which is the opposite of
        what running a local model was for.

        So when Ollama is not there, the assistant says so and says what to
        start. An honest refusal is worth more than an answer from somewhere the
        reader did not choose.

        Raises:
            AssistantUnavailable: with the specific reason and its fix.
        """
        history = list(history or [])
        model = self._settings.ollama_chat_model
        reachable, models = await ollama_available(self._settings.ollama_base_url)

        # Three different causes, three different fixes. Collapsing them into
        # one "assistant unavailable" leaves the reader guessing which.
        if not reachable:
            raise AssistantUnavailable(
                "Not connected to the local Ollama model. Start Ollama, then "
                f"make sure the model is installed: ollama pull {model}"
            )

        if not _model_present(models, model):
            raise AssistantUnavailable(
                f"Ollama is running but the model {model} is not installed. "
                f"Run: ollama pull {model}"
            )

        try:
            return await self._generate_ollama(system, user, history), f"ollama:{model}"
        except Exception as exc:
            logger.warning("Ollama generation failed: %s", exc)
            raise AssistantUnavailable(
                f"The local model {model} could not answer: {exc}"
            ) from exc

    async def _generate_ollama(self, system: str, question: str,
                               history: list[tuple[str, str]] | None = None) -> str:
        """Generate through Ollama's chat endpoint.

        Chat rather than /api/generate: Qwen3 is a reasoning model, and only
        the chat endpoint keeps its thinking in a separate field. Through
        /api/generate the reasoning arrived as part of the answer, so replies
        opened with "Hmm, the user is asking...".
        """
        async with httpx.AsyncClient(timeout=CHAT_TIMEOUT) as client:
            response = await client.post(
                f"{self._settings.ollama_base_url.rstrip('/')}/api/chat",
                json={
                    "model": self._settings.ollama_chat_model,
                    # Earlier turns go in as real messages rather than being
                    # pasted into the prompt: the model already knows how to
                    # read a conversation, and a transcript flattened into one
                    # user turn gets answered as though the reader wrote it.
                    "messages": [
                        {"role": "system", "content": system},
                        *(
                            {"role": role, "content": text}
                            for role, text in (history or [])
                        ),
                        {"role": "user", "content": question},
                    ],
                    "stream": False,
                    # Nothing here needs deliberation; the answer is already
                    # in the retrieved context, and thinking is pure latency.
                    "think": False,
                    "keep_alive": KEEP_ALIVE,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": MAX_ANSWER_TOKENS,
                    },
                },
            )
            response.raise_for_status()

        text = (response.json().get("message", {}).get("content") or "").strip()
        if not text:
            raise RuntimeError("Ollama returned an empty response.")
        return _strip_reasoning(text)

    # -- status ------------------------------------------------------------

    async def status(self) -> dict[str, Any]:
        """What the widget needs to know before offering itself."""
        reachable, models = await ollama_available(self._settings.ollama_base_url)

        embed_ready = reachable and _model_present(
            models, self._settings.ollama_embed_model)
        chat_ready = reachable and _model_present(
            models, self._settings.ollama_chat_model)

        return {
            "available": bool(embed_ready and chat_ready),
            "indexed": self._store is not None,
            "chunks": len(self._store.chunks) if self._store else 0,
            "ollama": {
                "reachable": reachable,
                "chat_model": self._settings.ollama_chat_model,
                "chat_model_ready": reachable and _model_present(
                    models, self._settings.ollama_chat_model),
                "embed_model": self._settings.ollama_embed_model,
                "embed_model_ready": reachable and _model_present(
                    models, self._settings.ollama_embed_model),
            },
        }
