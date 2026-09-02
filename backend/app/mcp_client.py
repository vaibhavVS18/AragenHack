"""MCP client wrapper - the agent's only route to the clinical tools.

Spawns ``mcp_server/server.py`` as a subprocess, speaks JSON-RPC over stdio,
and exposes a small typed surface. The agent depends on this module and never
imports ``mcp_server`` directly, which is what keeps the assignment's
"all communication by the agent goes through MCP" requirement true rather than
merely claimed.

Connection lifecycle
--------------------
A session is opened per request and closed when it ends::

    async with MCPClient(settings).connect() as tools:
        result = await tools.classify_lab_result("Potassium", 6.8, "mEq/L")

Spawning a subprocess per request costs a few hundred milliseconds. A pooled
long-lived session would save that, but anyio task scopes must be entered and
exited in the same task, which is fragile across an ASGI lifespan. The trade is
cheap here: a single LLM call takes 1-2 seconds, so process startup is a small
fraction of a request and the simpler lifecycle removes a whole class of async
bugs.
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from mcp import ClientSession, StdioServerParameters, stdio_client

from .config import Settings

logger = logging.getLogger(__name__)


class MCPUnavailableError(RuntimeError):
    """The clinical tool server could not be reached.

    Raised on connection failure or when a tool returns a protocol-level
    error. Callers map this to HTTP 503: without the tools there is nothing
    trustworthy to return.
    """


class MCPToolSession:
    """Typed access to the tools on an open MCP session.

    Wrapping the raw ``call_tool`` in named methods keeps argument names and
    JSON decoding in one place, so the agent reads as clinical steps rather
    than protocol plumbing.
    """

    def __init__(self, session: ClientSession) -> None:
        self._session = session
        self.tools_used: list[str] = []

    # -- protocol ---------------------------------------------------------

    async def list_tool_names(self) -> list[str]:
        """Names of every tool the server advertises."""
        listed = await self._session.list_tools()
        return [tool.name for tool in listed.tools]

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        """Invoke a tool and decode its JSON payload.

        MCP returns tool output as content blocks. Ours are JSON documents
        serialized as text, so the payload is decoded here and every caller
        receives ordinary Python data.
        """
        try:
            result = await self._session.call_tool(name, arguments)
        except Exception as exc:  # transport died mid-call
            raise MCPUnavailableError(
                f"MCP tool {name!r} failed: {exc}"
            ) from exc

        if name not in self.tools_used:
            self.tools_used.append(name)

        if getattr(result, "is_error", False):
            detail = result.content[0].text if result.content else "unknown error"
            raise MCPUnavailableError(f"MCP tool {name!r} returned an error: {detail}")

        # Prefer the structured payload when the SDK provides one; fall back to
        # decoding the text block.
        structured = getattr(result, "structured_content", None)
        if structured:
            return structured

        if not result.content:
            raise MCPUnavailableError(f"MCP tool {name!r} returned no content.")

        raw = result.content[0].text
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MCPUnavailableError(
                f"MCP tool {name!r} returned malformed JSON: {raw[:200]}"
            ) from exc

    # -- the three clinical tools -----------------------------------------

    async def get_reference_range(self, test_name: str) -> dict[str, Any]:
        """Look up the reference range for a test."""
        return await self.call("get_reference_range", {"test_name": test_name})

    async def list_reference_ranges(self) -> dict[str, Any]:
        """List every test the server can classify, with its thresholds."""
        return await self.call("list_reference_ranges", {})

    async def classify_lab_result(
        self,
        test_name: str,
        value: float | str,
        unit: str | None = None,
        reference_low: float | None = None,
        reference_high: float | None = None,
        reference_text: str | None = None,
    ) -> dict[str, Any]:
        """Classify one result. This is the agent's Classify step.

        The reference arguments carry an interval that arrived with the result
        itself - the Kaggle dataset supplies one per row - which the tool
        prefers over its built-in table.
        """
        return await self.call("classify_lab_result", {
            "test_name": test_name,
            "value": value,
            "unit": unit,
            "reference_low": reference_low,
            "reference_high": reference_high,
            "reference_text": reference_text,
        })

    async def route_by_severity(
        self, results: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Order results by urgency. This is the agent's Route step."""
        return await self.call("route_by_severity", {"results": results})


class MCPClient:
    """Spawns and connects to the clinical tool server."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    @property
    def _params(self) -> StdioServerParameters:
        command, *args = self._settings.mcp_server_command
        return StdioServerParameters(
            command=command,
            args=args,
            cwd=self._settings.mcp_server_cwd,
        )

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[MCPToolSession]:
        """Open a session with the tool server.

        The subprocess is started on entry and terminated on exit, so no
        server process outlives the request that needed it.
        """
        try:
            async with stdio_client(self._params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    logger.debug("MCP session initialized")
                    yield MCPToolSession(session)
        except MCPUnavailableError:
            raise
        except Exception as exc:
            raise MCPUnavailableError(
                f"Could not start the clinical tool server: {exc}"
            ) from exc

    async def health(self) -> tuple[bool, list[str], str | None]:
        """Check the server starts and advertises its tools.

        Returns ``(reachable, tool_names, error)``. Never raises, so a health
        endpoint can report a problem instead of becoming one.
        """
        try:
            async with self.connect() as tools:
                return True, await tools.list_tool_names(), None
        except Exception as exc:
            return False, [], str(exc)
