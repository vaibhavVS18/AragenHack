"""Tests for the agent pipeline.

These run against the real MCP server subprocess - the point of the agent is
that it talks to the tools over the protocol, so mocking that away would test
the wrong thing. The LLM is substituted, since its output is not deterministic
and its failure modes are what matter here.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.agent import LabAgent
from app.config import Settings
from app.llm.base import Explanation, LLMProvider, LLMUnavailableError
from app.models import LabInput, RowError

APP_DIR = Path(__file__).resolve().parent.parent / "app"


@pytest.fixture
def settings() -> Settings:
    return Settings(llm_provider="mock")


@pytest.fixture
def agent(settings: Settings) -> LabAgent:
    return LabAgent(settings)


def labs(*pairs: tuple) -> list[LabInput]:
    return [
        LabInput(test_name=p[0], value=p[1], unit=p[2] if len(p) > 2 else None)
        for p in pairs
    ]


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FailingProvider(LLMProvider):
    """Stands in for an LLM that is rate-limited, down, or misconfigured."""

    name = "failing"
    model = "none"

    async def explain(self, results):
        raise LLMUnavailableError("quota exceeded")


class ExplodingProvider(LLMProvider):
    """Raises something the agent was not told to expect."""

    name = "exploding"
    model = "none"

    async def explain(self, results):
        raise ValueError("unexpected boom")


class CountingProvider(LLMProvider):
    """Records how many times it was called and with how many results."""

    name = "counting"
    model = "none"

    def __init__(self) -> None:
        self.calls = 0
        self.batch_sizes: list[int] = []

    async def explain(self, results):
        self.calls += 1
        self.batch_sizes.append(len(results))
        return [Explanation(f"why {i}", f"do {i}") for i in range(len(results))]


# ---------------------------------------------------------------------------
# The pipeline
# ---------------------------------------------------------------------------

class TestPipeline:
    async def test_classifies_routes_and_explains(self, agent):
        response = await agent.analyze(labs(
            ("Glucose", 92, "mg/dL"),
            ("Potassium", 6.8, "mEq/L"),
            ("Creatinine", 2.1, "mg/dL"),
        ))

        assert [r.severity for r in response.results] == [
            "critical", "warning", "normal",
        ]
        assert all(r.explanation and r.next_step for r in response.results)

    async def test_results_arrive_ordered_by_severity(self, agent):
        response = await agent.analyze(labs(
            ("Glucose", 92, "mg/dL"),
            ("Vitamin D", 30, "ng/mL"),
            ("Hemoglobin", 6.0, "g/dL"),
            ("Creatinine", 2.1, "mg/dL"),
        ))
        assert [r.severity for r in response.results] == [
            "critical", "warning", "normal", "unknown",
        ]

    async def test_summary_matches_results(self, agent):
        response = await agent.analyze(labs(
            ("Potassium", 6.8, "mEq/L"),
            ("Glucose", 92, "mg/dL"),
            ("Vitamin D", 30, "ng/mL"),
        ))
        assert response.summary.total == 3
        assert response.summary.critical == 1
        assert response.summary.normal == 1
        assert response.summary.unknown == 1
        assert response.summary.abnormal == 1

    async def test_classification_reasoning_is_present(self, agent):
        response = await agent.analyze(labs(("Potassium", 6.8, "mEq/L")))
        result = response.results[0]

        assert result.rule_fired == "value (6.8) > critical_high (6.5)"
        assert result.reference_range.high == 5.1
        assert result.deviation_pct == pytest.approx(33.3, abs=0.1)
        assert result.direction == "above"

    async def test_patient_id_is_echoed(self, agent):
        response = await agent.analyze(labs(("Glucose", 92)), patient_id="ANON-1")
        assert response.patient_id == "ANON-1"

    async def test_empty_batch_returns_an_empty_response(self, agent):
        response = await agent.analyze([])
        assert response.results == []
        assert response.summary.total == 0

    async def test_row_errors_pass_through_without_failing_the_request(self, agent):
        errors = [RowError(row=4, error="Value 'N/A' is not numeric.")]
        response = await agent.analyze(labs(("Glucose", 92)), row_errors=errors)

        assert len(response.results) == 1
        assert response.summary.errors == 1
        assert response.errors[0].row == 4


class TestMCPUsage:
    async def test_agent_reports_the_mcp_tools_it_used(self, agent):
        response = await agent.analyze(labs(("Glucose", 92, "mg/dL")))
        assert set(response.meta.mcp_tools_used) == {
            "classify_lab_result", "route_by_severity",
        }

    async def test_health_reports_the_tool_server(self, agent):
        reachable, tools, error = await agent.health()
        assert reachable is True
        assert "classify_lab_result" in tools
        assert error is None


class TestExplainStep:
    async def test_one_batched_call_covers_the_whole_request(self, settings):
        # Per-result calls would multiply latency and rate-limit pressure.
        provider = CountingProvider()
        agent = LabAgent(settings, llm=provider)

        await agent.analyze(labs(
            ("Glucose", 92), ("Potassium", 6.8), ("Sodium", 128),
        ))

        assert provider.calls == 1
        assert provider.batch_sizes == [3]

    async def test_explanations_align_with_their_results(self, settings):
        # Explanations come back as a bare ordered array, so an off-by-one here
        # would attach the wrong advice to the wrong test.
        agent = LabAgent(settings, llm=CountingProvider())
        response = await agent.analyze(labs(
            ("Glucose", 92), ("Potassium", 6.8), ("Sodium", 128),
        ))
        assert [r.explanation for r in response.results] == ["why 0", "why 1", "why 2"]

    async def test_no_llm_call_for_an_empty_batch(self, settings):
        provider = CountingProvider()
        await LabAgent(settings, llm=provider).analyze([])
        assert provider.calls == 0

    async def test_every_result_is_explained_including_normals(self, agent):
        response = await agent.analyze(labs(
            ("Glucose", 92, "mg/dL"), ("Sodium", 140, "mEq/L"),
        ))
        assert all(r.severity == "normal" for r in response.results)
        assert all(r.explanation for r in response.results)


class TestDegradedMode:
    async def test_llm_failure_keeps_the_classifications(self, settings):
        agent = LabAgent(settings, llm=FailingProvider())
        response = await agent.analyze(labs(("Potassium", 6.8, "mEq/L")))

        result = response.results[0]
        assert result.severity == "critical"          # the important half survives
        assert result.rule_fired                       # reasoning survives
        assert result.explanation is None              # only the prose is lost

    async def test_llm_failure_is_reported_in_meta(self, settings):
        agent = LabAgent(settings, llm=FailingProvider())
        response = await agent.analyze(labs(("Glucose", 92)))

        assert response.meta.llm_available is False
        assert "quota exceeded" in response.meta.llm_error

    async def test_unexpected_provider_error_is_also_contained(self, settings):
        agent = LabAgent(settings, llm=ExplodingProvider())
        response = await agent.analyze(labs(("Glucose", 92)))

        assert response.results[0].severity == "normal"
        assert response.meta.llm_available is False
        assert "ValueError" in response.meta.llm_error

    async def test_missing_gemini_key_falls_back_to_mock(self):
        # A missing key should degrade the demo, not break startup.
        agent = LabAgent(Settings(llm_provider="gemini", gemini_api_key=""))
        assert agent.llm.name == "mock"


# ---------------------------------------------------------------------------
# Architectural constraint
# ---------------------------------------------------------------------------

class TestMCPBoundary:
    """The agent must reach the tools only through MCP.

    The assignment requires all agent communication to go through the MCP
    server. Importing the tool functions directly would still work, and would
    silently reduce the MCP server to decoration - so the boundary is asserted
    rather than trusted.
    """

    @staticmethod
    def _imported_modules(path: Path) -> set[str]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        modules: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                modules.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                modules.add(node.module)
        return modules

    def test_agent_does_not_import_the_tool_server(self):
        imported = self._imported_modules(APP_DIR / "agent.py")
        offenders = {m for m in imported if "mcp_server" in m}
        assert not offenders, (
            f"app/agent.py imports {offenders}. Clinical tools must be reached "
            "over MCP via app/mcp_client.py, not imported directly."
        )

    def test_no_module_in_app_imports_the_tool_server(self):
        offenders: dict[str, set[str]] = {}
        for path in APP_DIR.rglob("*.py"):
            bad = {m for m in self._imported_modules(path) if "mcp_server" in m}
            if bad:
                offenders[str(path.relative_to(APP_DIR))] = bad
        assert not offenders, (
            f"These modules bypass MCP: {offenders}. The FastAPI app must "
            "reach clinical logic only through the MCP client."
        )

    def test_agent_goes_through_the_mcp_client(self):
        imported = self._imported_modules(APP_DIR / "agent.py")
        assert any("mcp_client" in m for m in imported)
