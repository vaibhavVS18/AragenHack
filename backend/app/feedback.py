"""Feedback storage.

Appended to a JSON Lines file rather than posted to a mail service. The
reference implementation this was modelled on used EmailJS with the service
id, template id and public key written into the front-end source - which works,
but publishes those credentials to anyone who opens the bundle or the repo.

JSONL because feedback is append-only and read rarely: one line per entry means
a crash mid-write costs at most the entry being written, the file stays
readable in a terminal, and no database has to exist for a form that might
receive a dozen submissions.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

FEEDBACK_PATH = Path(__file__).resolve().parent.parent / "feedback.jsonl"

# A single submission cannot be larger than this once serialised. The schema
# already caps each field; this guards against a pathological combination.
MAX_ENTRY_BYTES = 8_000


def record_feedback(entry: dict[str, Any]) -> dict[str, Any]:
    """Append one feedback entry, stamped with the time it arrived.

    Args:
        entry: The validated submission.

    Returns:
        The stored record, including its timestamp.

    Raises:
        OSError: if the file cannot be written. The caller maps this to a 503
            rather than pretending the feedback was kept.
    """
    record = {
        "received_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **entry,
    }

    line = json.dumps(record, ensure_ascii=False)
    if len(line.encode("utf-8")) > MAX_ENTRY_BYTES:
        raise ValueError("Feedback entry is too large to store.")

    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    with FEEDBACK_PATH.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")

    logger.info("Feedback recorded (rating=%s)", record.get("rating"))
    return record


def feedback_summary() -> dict[str, Any]:
    """Count of entries and the mean rating, for the form's own display.

    Malformed lines are skipped rather than raising: a corrupt line should not
    make the whole summary unavailable, and the count is a nicety.
    """
    if not FEEDBACK_PATH.exists():
        return {"count": 0, "average_rating": None}

    total = 0
    ratings: list[int] = []

    try:
        with FEEDBACK_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                total += 1
                try:
                    rating = json.loads(line).get("rating")
                except json.JSONDecodeError:
                    continue
                if isinstance(rating, int):
                    ratings.append(rating)
    except OSError as exc:
        logger.warning("Could not read feedback file: %s", exc)
        return {"count": 0, "average_rating": None}

    return {
        "count": total,
        "average_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
    }
