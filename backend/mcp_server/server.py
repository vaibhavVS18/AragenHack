"""MCP server entrypoint - exposes the clinical tools over stdio.

This module is a thin adapter and nothing else. Every function below simply
forwards to its implementation in ``tools.py``. All clinical logic lives there,
which keeps it testable without a protocol in the way.

Run standalone to check the server starts::

    python -m mcp_server.server

It will block waiting on stdin - that means it is healthy. Ctrl+C to exit.

Inspect the tools interactively::

    npx @modelcontextprotocol/inspector python -m mcp_server.server

IMPORTANT - never write to stdout from this process. On the stdio transport
stdout *is* the JSON-RPC channel, so a stray ``print()`` corrupts the stream
and the client silently disconnects. Use ``log()`` below, which writes to
stderr.
"""

from __future__ import annotations

import sys
from typing import Any

from mcp.server import MCPServer

from . import tools

mcp = MCPServer(
    name="clinical-labs",
    version="1.0.0",
    instructions=(
        "Clinical laboratory reference tools. Use get_reference_range to look "
        "up normal ranges, classify_lab_result to determine the severity of a "
        "single result, and route_by_severity to order a batch of classified "
        "results by clinical urgency. Classification is deterministic: these "
        "tools compare values against published thresholds and never guess."
    ),
)


def log(message: str) -> None:
    """Write a diagnostic line to stderr - never stdout (see module docstring)."""
    print(f"[mcp:clinical-labs] {message}", file=sys.stderr, flush=True)


@mcp.tool()
def get_reference_range(test_name: str) -> dict[str, Any]:
    """Look up the clinical reference range for a laboratory test.

    Resolves common aliases and abbreviations ("HGB", "SGPT", "K+") and
    tolerates minor misspellings. Returns the normal low/high bounds, the
    critical thresholds on each side, the expected unit, and the clinical
    specialty associated with the test.

    Args:
        test_name: Lab test name as written by the user, e.g. "Hemoglobin".

    Returns:
        A dict with "found": true and the range details, or "found": false
        together with the list of tests this server knows about.
    """
    result = tools.get_reference_range(test_name)
    log(f"get_reference_range({test_name!r}) -> found={result['found']}")
    return result


@mcp.tool()
def list_reference_ranges() -> dict[str, Any]:
    """List every laboratory test this server can classify.

    Returns each test's canonical name, unit, normal bounds, critical
    thresholds, category, specialty and known aliases. Use this to discover
    what is supported rather than assuming a fixed catalogue.

    Returns:
        A dict with "count" and "tests".
    """
    result = tools.list_reference_ranges()
    log(f"list_reference_ranges() -> {result['count']} tests")
    return result


@mcp.tool()
def classify_lab_result(
    test_name: str,
    value: float | str,
    unit: str | None = None,
    reference_low: float | None = None,
    reference_high: float | None = None,
    reference_text: str | None = None,
) -> dict[str, Any]:
    """Classify a single lab result as Normal, Warning or Critical.

    Deterministic: the value is compared against a reference interval using
    fixed thresholds. Returns the severity together with the full reasoning -
    which range was used and where it came from, the direction and size of any
    deviation, and the literal comparison that produced the verdict.

    Two comparison modes are supported. Numeric results are compared against
    an interval. Qualitative results such as "Negatif", "Normal" or "1+",
    which urinalysis strips report, are compared against an expected word
    given in `reference_text`.

    If `reference_low` and `reference_high` are supplied they take precedence
    over the built-in table, because a laboratory's own interval is
    authoritative for its own result. Critical thresholds still come from the
    built-in table where the test is known; otherwise they are estimated from
    the interval width and reported as "derived".

    A severity of "unknown" is not a fourth grade - it marks a row that could
    not be interpreted (unrecognised test, non-numeric value, incompatible
    unit) and is reported rather than guessed.

    Args:
        test_name: Lab test name, e.g. "Potassium" or "Trombosit".
        value: Measured value. Numbers, numeric strings, censored results
            ("<0.1") and qualitative words are accepted.
        unit: Unit as reported, e.g. "mEq/L".
        reference_low: Lower bound supplied with the result, if any.
        reference_high: Upper bound supplied with the result, if any.
        reference_text: Expected qualitative result, e.g. "Negatif".

    Returns:
        A classified result dict including severity, reference_range,
        range_source, critical_basis, deviation_text and rule_fired.
    """
    result = tools.classify_lab_result(
        test_name, value, unit, reference_low, reference_high, reference_text
    )
    log(f"classify_lab_result({test_name!r}, {value!r}, {unit!r})"
        f" -> {result['severity']} [{result.get('range_source')}]")
    return result


@mcp.tool()
def route_by_severity(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Group and order classified lab results by clinical urgency.

    Critical results come first, then warnings, then normals, then any that
    could not be interpreted. Within each group the most deviant value leads.

    Args:
        results: Classified results, as returned by classify_lab_result.

    Returns:
        A dict with "ordered" (flat list, most urgent first), "groups"
        (results keyed by severity), "summary" (counts per severity) and
        "highest_severity".
    """
    routed = tools.route_by_severity(results)
    log(f"route_by_severity({len(results)} results) -> {routed['summary']}")
    return routed


def main() -> None:
    """Serve the tools over stdio."""
    log("starting on stdio transport")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
