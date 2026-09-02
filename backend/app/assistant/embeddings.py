"""Embeddings for the assistant, from the local Ollama model.

Local only. A hosted fallback was tried and removed: the two produce different
vector spaces - 768 dimensions from nomic-embed-text, 3072 from Gemini - so an
index built with one cannot be searched with the other. Falling back therefore
does not degrade gracefully; it throws the index away and rebuilds it from
scratch in the middle of answering someone, and quietly sends the corpus
somewhere the operator did not choose.

The index still records which provider built it, and is rebuilt rather than
searched when that changes - the check costs nothing and is the difference
between a rebuild and confident nonsense.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol

import httpx

from ..config import Settings

logger = logging.getLogger(__name__)

# Ollama can be slow on a cold model load; a whole corpus is a big first call.
EMBED_TIMEOUT = httpx.Timeout(120.0, connect=5.0)

# Probing whether the daemon is up must never be the slow part of a request.
PROBE_TIMEOUT = httpx.Timeout(3.0, connect=1.5)


class EmbeddingUnavailable(RuntimeError):
    """No embedding provider could be reached."""


class EmbeddingProvider(Protocol):
    """What the index requires of an embedding backend."""

    #: Identifies the vector space, e.g. "ollama:nomic-embed-text".
    signature: str

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch, returning one vector per input in the same order."""
        ...


class OllamaEmbeddings:
    """Local embeddings through the Ollama HTTP API."""

    def __init__(self, base_url: str, model: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self.signature = f"ollama:{model}"

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        async with httpx.AsyncClient(timeout=EMBED_TIMEOUT) as client:
            try:
                response = await client.post(
                    f"{self._base_url}/api/embed",
                    json={"model": self._model, "input": texts},
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise EmbeddingUnavailable(
                    f"Ollama embeddings failed ({self._model}): {exc}"
                ) from exc

        payload = response.json()
        vectors = payload.get("embeddings")
        if not vectors or len(vectors) != len(texts):
            raise EmbeddingUnavailable(
                f"Ollama returned {len(vectors or [])} vectors for {len(texts)} inputs."
            )
        return vectors


async def ollama_available(base_url: str) -> tuple[bool, list[str]]:
    """Ask the local daemon whether it is up, and what it has installed.

    Returns ``(reachable, model_names)``. Never raises: "Ollama is not running"
    is an ordinary state of the world here, not an error, and the callers all
    need to carry on and say something useful about it.
    """
    try:
        async with httpx.AsyncClient(timeout=PROBE_TIMEOUT) as client:
            response = await client.get(f"{base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
    except httpx.HTTPError:
        return False, []

    payload: dict[str, Any] = response.json()
    return True, [m.get("name", "") for m in payload.get("models", [])]


def _model_present(models: list[str], wanted: str) -> bool:
    """Whether a model is installed, ignoring the implicit ``:latest`` tag.

    ``ollama list`` reports "nomic-embed-text:latest" for what everyone writes
    and configures as "nomic-embed-text". Comparing the raw strings finds
    nothing and reports a pulled model as missing.
    """
    def base(name: str) -> str:
        return name.split(":", 1)[0]

    return any(m == wanted or base(m) == base(wanted) for m in models)


async def get_embedding_provider(settings: Settings) -> EmbeddingProvider:
    """Return the local embedding backend.

    Ollama only. A hosted fallback would embed queries into a different space
    from the one the corpus was indexed in - 3072 dimensions against 768 - so
    the cached index would be thrown away and rebuilt the moment the daemon
    stopped, in the middle of answering someone.

    Raises:
        EmbeddingUnavailable: if Ollama or the model is not ready.
    """
    reachable, models = await ollama_available(settings.ollama_base_url)

    if not reachable:
        raise EmbeddingUnavailable(
            "Not connected to the local Ollama model. Start Ollama, then make "
            f"sure the model is installed: ollama pull {settings.ollama_embed_model}"
        )

    if not _model_present(models, settings.ollama_embed_model):
        raise EmbeddingUnavailable(
            f"Ollama is running but the model {settings.ollama_embed_model} is "
            f"not installed. Run: ollama pull {settings.ollama_embed_model}"
        )

    return OllamaEmbeddings(settings.ollama_base_url, settings.ollama_embed_model)
