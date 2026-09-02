"""Shared test configuration.

The suite must never call a real LLM API. Doing so makes tests slow, flaky,
dependent on a key the grader may not have, and consumes free-tier quota.

Environment variables take precedence over ``.env`` in pydantic-settings, so
pinning them here neutralises whatever a developer has configured locally.
This runs at import time, before any module reads settings.
"""

from __future__ import annotations

import os

os.environ["LLM_PROVIDER"] = "mock"
os.environ["GEMINI_API_KEY"] = ""
