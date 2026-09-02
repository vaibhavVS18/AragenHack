"""The agent: Classify -> Route -> Explain.

The agent owns no clinical knowledge. It sequences the three steps and
delegates every one of them:

* **Classify** - MCP tool ``classify_lab_result``
* **Route**    - MCP tool ``route_by_severity``
* **Explain**  - the configured LLM provider

It deliberately does not import from ``mcp_server``. All tool access goes
through :mod:`app.mcp_client`, which is what makes the assignment's "all
communication by the agent goes through MCP" requirement structurally true.
``tests/test_agent.py`` asserts that boundary.

Failure policy
--------------
The two dependencies fail differently, on purpose:

* MCP unavailable  -> the request fails (503). Without classification there is
  nothing trustworthy to return.
* LLM unavailable  -> the request succeeds without explanations. Severities are
  computed locally and must never be lost to a third-party outage.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from .config import Settings
from .llm import LLMProvider, LLMUnavailableError, get_provider
from .mcp_client import MCPClient, MCPUnavailableError
from .models import (
    AnalyzeResponse,
    LabInput,
    LabResult,
    ResponseMeta,
    RowError,
    Summary,
)

logger = logging.getLogger(__name__)


class LabAgent:
    """Runs the Classify -> Route -> Explain pipeline for a batch of labs."""

    def __init__(
        self,
        settings: Settings,
        mcp_client: MCPClient | None = None,
        llm: LLMProvider | None = None,
    ) -> None:
        # Dependencies are injectable so tests can substitute doubles without
        # patching module globals.
        self._settings = settings
        self._mcp = mcp_client or MCPClient(settings)
        self._llm = llm or get_provider(settings)

    # -- public API --------------------------------------------------------

    async def analyze(
        self,
        labs: list[LabInput],
        patient_id: str | None = None,
        row_errors: list[RowError] | None = None,
    ) -> AnalyzeResponse:
        """Classify, route and explain a batch of lab results.

        Args:
            labs: Validated lab inputs.
            patient_id: Optional label echoed back in the response.
            row_errors: Rows rejected before classification, typically from
                CSV parsing. Reported alongside the results rather than
                failing the request.

        Returns:
            The complete response: results ordered by severity, each carrying
            its classification reasoning and generated explanation.

        Raises:
            MCPUnavailableError: if the clinical tool server cannot be reached.
        """
        started = time.perf_counter()
        row_errors = list(row_errors or [])

        # --- Classify + Route (both via MCP) ---
        async with self._mcp.connect() as tools:
            classified = [
                await tools.classify_lab_result(
                    lab.test_name,
                    lab.value,
                    lab.unit,
                    reference_low=lab.reference_low,
                    reference_high=lab.reference_high,
                    reference_text=lab.reference_text,
                )
                for lab in labs
            ]
            routed = await tools.route_by_severity(classified)
            tools_used = list(tools.tools_used)

        ordered: list[dict[str, Any]] = routed["ordered"]

        # --- Explain (via the LLM) ---
        explanations, llm_error = await self._explain(ordered)

        results = [
            self._to_model(result, explanations.get(index))
            for index, result in enumerate(ordered)
        ]

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return AnalyzeResponse(
            patient_id=patient_id,
            summary=self._summarize(routed["summary"], len(row_errors)),
            results=results,
            errors=row_errors,
            meta=ResponseMeta(
                llm_provider=self._llm.name,
                llm_model=self._llm.model,
                llm_available=llm_error is None,
                llm_error=llm_error,
                elapsed_ms=elapsed_ms,
                mcp_tools_used=tools_used,
            ),
        )

    async def reference_ranges(self) -> dict[str, Any]:
        """List every test the tool server can classify.

        Fetched over MCP like everything else, so the clinical table remains
        the single source of truth and the UI never hardcodes a catalogue that
        could drift from the one actually used to classify.
        """
        async with self._mcp.connect() as tools:
            return await tools.list_reference_ranges()

    async def health(self) -> tuple[bool, list[str], str | None]:
        """Report whether the clinical tool server is reachable."""
        return await self._mcp.health()

    @property
    def llm(self) -> LLMProvider:
        """The active explanation provider, for reporting in /health."""
        return self._llm

    # -- steps -------------------------------------------------------------

    async def _explain(
        self, ordered: list[dict[str, Any]]
    ) -> tuple[dict[int, Any], str | None]:
        """Generate explanations for the routed results.

        One batched call covers the whole request. Calling per result would
        multiply latency and rate-limit pressure by the number of rows while
        producing no better output, since each explanation is independent.

        Returns ``(explanations_by_index, error)``. A failure yields an empty
        mapping and an error string - never an exception, because losing the
        prose must not lose the classifications.
        """
        if not ordered:
            return {}, None

        try:
            generated = await self._llm.explain(ordered)
        except LLMUnavailableError as exc:
            logger.warning("Explanation step degraded: %s", exc)
            return {}, str(exc)
        except Exception as exc:  # provider raised something unexpected
            logger.exception("Unexpected error from LLM provider")
            return {}, f"{type(exc).__name__}: {exc}"

        return dict(enumerate(generated)), None

    # -- assembly ----------------------------------------------------------

    @staticmethod
    def _to_model(result: dict[str, Any], explanation: Any | None) -> LabResult:
        """Merge a classified result with its generated prose."""
        model = LabResult(**result)
        if explanation is not None:
            model.explanation = explanation.explanation or None
            model.next_step = explanation.next_step or None
        return model

    @staticmethod
    def _summarize(counts: dict[str, int], error_count: int) -> Summary:
        """Build the response summary from the Route step's counts."""
        return Summary(
            total=counts.get("total", 0),
            critical=counts.get("critical", 0),
            warning=counts.get("warning", 0),
            normal=counts.get("normal", 0),
            unknown=counts.get("unknown", 0),
            abnormal=counts.get("abnormal", 0),
            errors=error_count,
        )


__all__ = ["LabAgent", "MCPUnavailableError"]
