"""Tests for the MCP protocol layer.

``test_classification.py`` covers the clinical logic directly. This file
covers the thing that logic is wrapped in: that the server starts, advertises
its tools with usable schemas, and returns correct results when those tools
are invoked over a real stdio connection.

Each test spawns the server as a subprocess, exactly as the agent does.
"""

from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from mcp import ClientSession, StdioServerParameters, stdio_client

BACKEND_DIR = Path(__file__).resolve().parent.parent

EXPECTED_TOOLS = {
    "get_reference_range",
    "list_reference_ranges",
    "classify_lab_result",
    "route_by_severity",
}


@asynccontextmanager
async def mcp_session():
    """Spawn the MCP server over stdio and yield an initialized session."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "mcp_server.server"],
        cwd=str(BACKEND_DIR),
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def call(session: ClientSession, tool: str, args: dict) -> dict:
    """Call a tool and decode its JSON payload."""
    result = await session.call_tool(tool, args)
    return json.loads(result.content[0].text)


class TestServerHandshake:
    async def test_server_starts_and_identifies_itself(self):
        async with mcp_session() as session:
            info = (await session.initialize()).server_info
            assert info.name == "clinical-labs"

    async def test_all_three_tools_are_advertised(self):
        async with mcp_session() as session:
            names = {t.name for t in (await session.list_tools()).tools}
            assert names == EXPECTED_TOOLS

    async def test_tools_expose_descriptions_and_schemas(self):
        # Discovery is what makes MCP more than remote function calls: a client
        # must be able to learn how to call a tool without prior knowledge.
        # A zero-argument tool legitimately has no properties, so the schema
        # must be well formed rather than non-empty.
        async with mcp_session() as session:
            for tool in (await session.list_tools()).tools:
                assert tool.description, f"{tool.name} has no description"
                assert tool.input_schema.get("type") == "object", (
                    f"{tool.name} has no object input schema"
                )
                assert "properties" in tool.input_schema, (
                    f"{tool.name} declares no properties key"
                )

    async def test_tools_that_take_arguments_describe_them(self):
        async with mcp_session() as session:
            tools = {t.name: t for t in (await session.list_tools()).tools}

        for name in ("get_reference_range", "classify_lab_result", "route_by_severity"):
            assert tools[name].input_schema["properties"], f"{name} has no parameters"

    async def test_list_reference_ranges_takes_no_arguments(self):
        async with mcp_session() as session:
            tools = {t.name: t for t in (await session.list_tools()).tools}

        schema = tools["list_reference_ranges"].input_schema
        assert schema["properties"] == {}
        assert not schema.get("required")

    async def test_classify_schema_requires_name_and_value(self):
        async with mcp_session() as session:
            tools = {t.name: t for t in (await session.list_tools()).tools}
            required = set(tools["classify_lab_result"].input_schema["required"])
            assert required == {"test_name", "value"}   # unit is optional


class TestToolsOverProtocol:
    async def test_reference_range_lookup(self):
        async with mcp_session() as session:
            data = await call(session, "get_reference_range", {"test_name": "HGB"})
            assert data["found"] is True
            assert data["test_name"] == "Hemoglobin"
            assert data["matched_by"] == "alias"

    async def test_classification_matches_direct_call(self):
        # The protocol must not change the answer. Same input, same verdict.
        from mcp_server.tools import classify_lab_result as direct

        async with mcp_session() as session:
            over_mcp = await call(session, "classify_lab_result", {
                "test_name": "Potassium", "value": 6.8, "unit": "mEq/L",
            })
        assert over_mcp == direct("Potassium", 6.8, "mEq/L")

    async def test_optional_unit_may_be_omitted(self):
        async with mcp_session() as session:
            data = await call(session, "classify_lab_result", {
                "test_name": "Hemoglobin", "value": 15.0,
            })
            assert data["severity"] == "normal"
            assert data["unit_assumed"] is True

    async def test_invalid_input_returns_a_result_not_an_error(self):
        # Bad clinical data is an expected outcome, not a protocol failure.
        async with mcp_session() as session:
            data = await call(session, "classify_lab_result", {
                "test_name": "Glucose", "value": "N/A",
            })
            assert data["severity"] == "unknown"
            assert data["error"]

    async def test_routing_over_protocol(self):
        async with mcp_session() as session:
            batch = [
                await call(session, "classify_lab_result",
                           {"test_name": n, "value": v, "unit": u})
                for n, v, u in [
                    ("Glucose", 92, "mg/dL"),
                    ("Potassium", 6.8, "mEq/L"),
                    ("Creatinine", 2.1, "mg/dL"),
                ]
            ]
            routed = await call(session, "route_by_severity", {"results": batch})

        assert [r["severity"] for r in routed["ordered"]] == [
            "critical", "warning", "normal",
        ]
        assert routed["summary"]["abnormal"] == 2

    async def test_full_pipeline_in_one_session(self):
        # Classify then route over a single connection, as the agent does.
        async with mcp_session() as session:
            labs = [("Hemoglobin", 6.0), ("Glucose", 92), ("Sodium", 128)]
            classified = [
                await call(session, "classify_lab_result",
                           {"test_name": n, "value": v})
                for n, v in labs
            ]
            routed = await call(session, "route_by_severity", {"results": classified})

        assert routed["highest_severity"] == "critical"
        assert routed["summary"]["total"] == 3


class TestProtocolHygiene:
    async def test_stdout_carries_only_protocol_traffic(self):
        # The classic stdio failure: a stray print() in server code corrupts
        # the JSON-RPC stream. If logging ever moves to stdout, the session
        # below fails to initialize and this test catches it.
        async with mcp_session() as session:
            assert (await session.list_tools()).tools

    async def test_unknown_tool_is_rejected(self):
        # The SDK reports this as an error *result* rather than raising, so the
        # connection survives and the caller can handle it.
        async with mcp_session() as session:
            result = await session.call_tool("drop_database", {})
            assert result.is_error is True
            assert "drop_database" in result.content[0].text
