"""Retrieval-augmented assistant for questions about this application.

Deliberately separate from the classification pipeline. The assistant is an
addition to the assignment, not part of it, and it must never be able to
influence how a lab result is classified or explained.

Its knowledge is limited to this application: how classification works, what
thresholds are used, what a severity means, how to upload a CSV. It does not
answer medical questions - a small local model giving unsourced clinical
advice is exactly the failure mode the rest of this system is built to avoid.
"""

from .service import AssistantService, AssistantUnavailable

__all__ = ["AssistantService", "AssistantUnavailable"]
