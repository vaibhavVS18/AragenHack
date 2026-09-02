"""The vector index: a NumPy matrix and a list of chunks.

No vector database. The corpus is a few hundred chunks, so a similarity search
is one matrix multiply - microseconds, in process, with nothing to run
alongside the app. Chroma or FAISS would each add a dependency or a service to
search less data than fits in a spreadsheet.

Vectors are L2-normalised on the way in, which turns cosine similarity into a
plain dot product and lets the whole search be a single ``matrix @ vector``.

The index records which embedding provider built it. Vector spaces are not
interchangeable - 768 dimensions from nomic-embed-text against 3072 from
Gemini - so an index built by one is rebuilt rather than searched by the other.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .corpus import Chunk

logger = logging.getLogger(__name__)

INDEX_VERSION = 1


@dataclass(frozen=True)
class Match:
    """One retrieved chunk and how well it matched."""

    chunk: Chunk
    score: float


class VectorStore:
    """An in-memory index over the assistant's corpus."""

    def __init__(self, chunks: list[Chunk], vectors: np.ndarray,
                 signature: str) -> None:
        if len(chunks) != vectors.shape[0]:
            raise ValueError(
                f"{len(chunks)} chunks but {vectors.shape[0]} vectors."
            )
        self.chunks = chunks
        self.vectors = vectors
        self.signature = signature

    # -- construction ------------------------------------------------------

    @classmethod
    def build(cls, chunks: list[Chunk], vectors: list[list[float]],
              signature: str) -> "VectorStore":
        matrix = np.asarray(vectors, dtype=np.float32)
        return cls(chunks, _normalise(matrix), signature)

    # -- search ------------------------------------------------------------

    def search(self, query_vector: list[float], top_k: int = 5,
               min_score: float = 0.0) -> list[Match]:
        """Return the closest chunks, best first.

        Because every vector is unit length, the dot product *is* the cosine
        similarity, so the entire search is one matrix multiply.
        """
        if not len(self.chunks):
            return []

        query = _normalise(np.asarray([query_vector], dtype=np.float32))[0]
        scores = self.vectors @ query

        # argpartition finds the top k without sorting the whole array; the
        # corpus is small enough that it hardly matters, but it costs nothing.
        count = min(top_k, len(scores))
        candidates = np.argpartition(-scores, count - 1)[:count]
        ordered = candidates[np.argsort(-scores[candidates])]

        return [
            Match(chunk=self.chunks[i], score=float(scores[i]))
            for i in ordered
            if scores[i] >= min_score
        ]

    # -- persistence -------------------------------------------------------

    def save(self, path: Path) -> None:
        """Write the index beside its metadata.

        Vectors go to ``.npz`` and the chunks to ``.json``: NumPy handles the
        matrix efficiently, and keeping the text readable makes an index easy
        to inspect when retrieval misbehaves.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path.with_suffix(".npz"), vectors=self.vectors)
        path.with_suffix(".json").write_text(
            json.dumps({
                "version": INDEX_VERSION,
                "signature": self.signature,
                "chunks": [
                    {"id": c.id, "title": c.title, "source": c.source, "text": c.text}
                    for c in self.chunks
                ],
            }, indent=2),
            encoding="utf-8",
        )

    @classmethod
    def load(cls, path: Path, signature: str) -> "VectorStore | None":
        """Load an index, or None if it is absent, stale or from another space."""
        vectors_path = path.with_suffix(".npz")
        meta_path = path.with_suffix(".json")

        if not (vectors_path.exists() and meta_path.exists()):
            return None

        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Assistant index unreadable, rebuilding: %s", exc)
            return None

        if meta.get("version") != INDEX_VERSION:
            logger.info("Assistant index is an older version; rebuilding.")
            return None

        if meta.get("signature") != signature:
            logger.info(
                "Assistant index was built with %s but %s is active; rebuilding.",
                meta.get("signature"), signature,
            )
            return None

        chunks = [
            Chunk(id=c["id"], title=c["title"], source=c["source"], text=c["text"])
            for c in meta.get("chunks", [])
        ]
        vectors = np.load(vectors_path)["vectors"]

        if len(chunks) != vectors.shape[0]:
            logger.warning("Assistant index is inconsistent; rebuilding.")
            return None

        return cls(chunks, vectors, signature)


def _normalise(matrix: np.ndarray) -> np.ndarray:
    """Scale each row to unit length, leaving zero rows alone."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms
