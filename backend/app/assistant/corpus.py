"""What the assistant knows, and how it is cut into retrievable pieces.

Two sources, both derived rather than authored:

* The repository's own Markdown - the docs directory and the README. These
  already explain the architecture, the classification rules and the API, so
  writing a separate knowledge base would mean maintaining the same facts
  twice and letting them drift.
* The clinical reference table, fetched over MCP. It is not read from
  ``mcp_server`` directly: no module under ``app/`` may import that package,
  and a test enforces it.

Chunking splits on Markdown headings first and only falls back to size when a
section is genuinely long. A heading marks a change of subject, so a chunk that
respects it tends to be about one thing - which is what makes a retrieved
chunk answerable rather than merely similar.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .knowledge import knowledge_entries

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DOCS_DIR = REPO_ROOT / "docs"
README = REPO_ROOT / "README.md"

# Chunks below this are usually a stray heading; above it, they start covering
# more than one idea and retrieval gets vague.
MIN_CHUNK_CHARS = 120
MAX_CHUNK_CHARS = 1400
OVERLAP_CHARS = 150


@dataclass(frozen=True)
class Chunk:
    """One retrievable passage."""

    id: str
    title: str
    source: str
    text: str

    def for_embedding(self) -> str:
        """Text as embedded.

        The title is prepended so the heading's words are part of the vector.
        A section titled "Where the ranges come from" whose body never repeats
        that phrasing would otherwise be unreachable by a query that uses it.
        """
        return f"{self.title}\n\n{self.text}"


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

_HEADING = re.compile(r"^(#{1,4})\s+(.*)$", re.M)
_CODE_FENCE = re.compile(r"^```", re.M)


def _split_by_heading(text: str) -> list[tuple[str, str]]:
    """Split Markdown into ``(heading, body)`` sections.

    Fenced code blocks are tracked so a ``#`` comment inside one is not
    mistaken for a heading - shell examples in these docs are full of them.
    """
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_heading = ""
    current: list[str] = []
    in_fence = False

    for line in lines:
        if _CODE_FENCE.match(line):
            in_fence = not in_fence

        match = None if in_fence else _HEADING.match(line)
        if match:
            if current:
                sections.append((current_heading, current))
            current_heading = match.group(2).strip()
            current = []
        else:
            current.append(line)

    if current:
        sections.append((current_heading, current))

    return [(heading, "\n".join(body).strip()) for heading, body in sections]


def _split_long(text: str) -> Iterable[str]:
    """Break an over-long section on paragraph boundaries, with overlap.

    The overlap carries the tail of one chunk into the next so a sentence
    split across the boundary is still retrievable from either side.
    """
    if len(text) <= MAX_CHUNK_CHARS:
        yield text
        return

    paragraphs = text.split("\n\n")
    buffer = ""

    for paragraph in paragraphs:
        if len(buffer) + len(paragraph) + 2 > MAX_CHUNK_CHARS and buffer:
            yield buffer.strip()
            buffer = buffer[-OVERLAP_CHARS:] + "\n\n" + paragraph
        else:
            buffer = f"{buffer}\n\n{paragraph}" if buffer else paragraph

    if buffer.strip():
        yield buffer.strip()


def markdown_chunks() -> list[Chunk]:
    """Every Markdown document in the repository, cut into chunks."""
    files = sorted(DOCS_DIR.glob("*.md")) if DOCS_DIR.exists() else []
    if README.exists():
        files.append(README)

    chunks: list[Chunk] = []
    for path in files:
        source = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
        document_title = path.stem.replace("-", " ").title()

        for heading, body in _split_by_heading(path.read_text(encoding="utf-8")):
            if len(body) < MIN_CHUNK_CHARS:
                continue

            title = f"{document_title} - {heading}" if heading else document_title
            for index, piece in enumerate(_split_long(body)):
                if len(piece) < MIN_CHUNK_CHARS:
                    continue
                chunks.append(Chunk(
                    id=f"{source}#{len(chunks)}-{index}",
                    title=title,
                    source=source,
                    text=piece,
                ))

    return chunks


# ---------------------------------------------------------------------------
# Clinical reference table
# ---------------------------------------------------------------------------

def reference_range_chunks(catalogue: dict[str, Any]) -> list[Chunk]:
    """One chunk per lab test, from the catalogue served over MCP.

    Written as prose rather than a table: "Hemoglobin is measured in g/dL. The
    normal range is 12.0 to 17.5" embeds far better against a question phrased
    as "what is the normal range for hemoglobin" than a row of pipe-separated
    numbers does.
    """
    chunks: list[Chunk] = []

    for test in catalogue.get("tests", []):
        name = test["test_name"]
        parts = [
            f"{name} is a {test.get('category', 'laboratory')} test measured "
            f"in {test['unit']}.",
        ]
        if test.get("measures"):
            parts.append(f"It reflects {test['measures']}.")

        parts.append(
            f"The normal reference range for {name} is {test['low']} to "
            f"{test['high']} {test['unit']}. A value inside this range, "
            f"including the bounds themselves, is classified Normal."
        )

        if test.get("critical_low") is not None:
            parts.append(
                f"A {name} below {test['critical_low']} {test['unit']} is "
                "classified Critical."
            )
        else:
            parts.append(
                f"{name} has no critical low threshold: a low value is a "
                "Warning, never Critical."
            )

        if test.get("critical_high") is not None:
            parts.append(
                f"A {name} above {test['critical_high']} {test['unit']} is "
                "classified Critical."
            )
        else:
            parts.append(
                f"{name} has no critical high threshold: a high value is a "
                "Warning, never Critical."
            )

        parts.append(
            f"Anything outside the normal range but inside the critical "
            f"thresholds is a Warning. Abnormal {name} results are associated "
            f"with {test.get('specialty', 'internal medicine')}."
        )

        if test.get("aliases"):
            parts.append(
                f"{name} is also accepted as: {', '.join(test['aliases'])}."
            )

        chunks.append(Chunk(
            id=f"reference/{name.lower().replace(' ', '-')}",
            title=f"Reference range - {name}",
            source="reference_ranges (MCP)",
            text=" ".join(parts),
        ))

    return chunks


def curated_chunks() -> list[Chunk]:
    """The hand-written, user-facing entries.

    These lead the corpus because they are phrased the way a user asks. The
    developer docs answer the same questions in developer language: "how can I
    test this?" matched the setup guide and returned a pytest command.
    """
    return [
        Chunk(id=f"knowledge/{i}", title=title, source="app guide", text=body)
        for i, (title, body) in enumerate(knowledge_entries())
    ]


def build_corpus(catalogue: dict[str, Any] | None = None) -> list[Chunk]:
    """The assistant's full knowledge base."""
    chunks = curated_chunks()
    if catalogue:
        chunks.extend(reference_range_chunks(catalogue))
    chunks.extend(markdown_chunks())
    return chunks
