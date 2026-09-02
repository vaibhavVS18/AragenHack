"""Tests for the explanation layer.

No network. These cover the parts that break in practice: parsing whatever the
model actually returns, deciding which failures are worth retrying, and the
provider selection rules.

Live Gemini output is verified by hand rather than in CI - asserting on
generated prose would be a flaky test of a non-deterministic system.
"""

from __future__ import annotations

import json

import pytest

from app.config import Settings
from app.llm import get_provider
from app.llm.base import (
    LLMUnavailableError,
    build_result_payload,
    build_user_prompt,
    parse_explanations,
)
from app.llm.mock import MockProvider

VALID = json.dumps([
    {
        "headline": "Your result is slightly high.",
        "what_it_measures": "How much oxygen your blood can carry.",
        "what_result_means": "It sits just above the normal range.",
        "possible_causes": ["dehydration", "smoking"],
        "urgency": "soon",
        "urgency_reason": "Worth checking, not an emergency.",
        "next_steps": ["Book an appointment", "Ask for a repeat test"],
        "questions_to_ask": ["Could this be dehydration?"],
    }
])


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

class TestParseExplanations:
    def test_plain_json_array(self):
        [result] = parse_explanations(VALID, expected=1)
        assert result.headline == "Your result is slightly high."
        assert result.urgency == "soon"
        assert result.possible_causes == ("dehydration", "smoking")
        assert len(result.next_steps) == 2

    def test_markdown_fenced_json(self):
        # Models wrap JSON in code fences even when told not to.
        raw = f"```json\n{VALID}\n```"
        [result] = parse_explanations(raw, expected=1)
        assert result.headline == "Your result is slightly high."

    def test_bare_fence_without_language(self):
        assert parse_explanations(f"```\n{VALID}\n```", expected=1)

    def test_prose_around_the_array_is_ignored(self):
        raw = f"Here are the explanations you asked for:\n{VALID}\nHope that helps!"
        [result] = parse_explanations(raw, expected=1)
        assert result.next_steps == ("Book an appointment", "Ask for a repeat test")

    def test_array_wrapped_in_an_object(self):
        raw = json.dumps({"results": [{"headline": "why", "urgency": "routine"}]})
        assert parse_explanations(raw, expected=1)[0].headline == "why"

    def test_whitespace_is_trimmed(self):
        raw = json.dumps([{
            "headline": "  spaced  ",
            "urgency": "routine",
            "next_steps": ["  padded step  "],
        }])
        [result] = parse_explanations(raw, expected=1)
        assert result.headline == "spaced"
        assert result.next_steps == ("padded step",)

    def test_missing_keys_get_safe_defaults(self):
        [result] = parse_explanations('[{"headline": "only this"}]', expected=1)
        assert result.what_it_measures == ""
        assert result.next_steps == ()
        # An unspecified urgency must not become an invalid value downstream.
        assert result.urgency == "routine"

    def test_invalid_urgency_falls_back_to_routine(self):
        raw = json.dumps([{"headline": "x", "urgency": "catastrophic"}])
        assert parse_explanations(raw, expected=1)[0].urgency == "routine"

    def test_wrong_length_is_a_failure_not_a_realignment(self):
        # Silently truncating or padding would attach advice to the wrong test.
        with pytest.raises(LLMUnavailableError, match="1 explanations for 3"):
            parse_explanations(VALID, expected=3)

    def test_unparseable_output_raises(self):
        with pytest.raises(LLMUnavailableError, match="unparseable"):
            parse_explanations("I cannot help with that.", expected=1)

    def test_non_array_json_raises(self):
        with pytest.raises(LLMUnavailableError):
            parse_explanations('{"headline": "x"}', expected=1)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

class TestPromptBuilding:
    RESULT = {
        "test_name": "Potassium", "value": 6.8, "unit": "mEq/L",
        "severity": "critical", "specialty": "nephrology",
        "measures": "electrolyte essential for cardiac function",
        "reference_range": {"low": 3.5, "high": 5.1, "unit": "mEq/L"},
        "deviation_text": "33.3% above the upper limit of normal",
        "rule_fired": "value (6.8) > critical_high (6.5)",
        "band": "critical_high", "matched_by": "exact",
    }

    def test_payload_keeps_the_clinically_relevant_fields(self):
        payload = build_result_payload(self.RESULT)
        assert payload["severity"] == "critical"
        assert payload["normal_range"] == "3.5-5.1 mEq/L"
        assert payload["deviation"].startswith("33.3%")

    def test_payload_drops_internal_bookkeeping(self):
        # Sending everything would bury the relevant facts and cost tokens.
        payload = build_result_payload(self.RESULT)
        assert "rule_fired" not in payload
        assert "band" not in payload
        assert "matched_by" not in payload

    def test_payload_handles_a_result_with_no_range(self):
        payload = build_result_payload({"test_name": "Vitamin D", "severity": "unknown"})
        assert "normal_range" not in payload

    def test_prompt_states_the_expected_count(self):
        prompt = build_user_prompt([self.RESULT, self.RESULT])
        assert "exactly 2 objects" in prompt
        assert "Potassium" in prompt


# ---------------------------------------------------------------------------
# Mock provider
# ---------------------------------------------------------------------------

class TestMockProvider:
    async def test_returns_one_explanation_per_result(self):
        results = [{"test_name": "A", "severity": "normal"},
                   {"test_name": "B", "severity": "critical"}]
        assert len(await MockProvider().explain(results)) == 2

    async def test_empty_batch(self):
        assert await MockProvider().explain([]) == []

    async def test_output_is_deterministic(self):
        result = [{"test_name": "Glucose", "value": 92, "severity": "normal"}]
        assert await MockProvider().explain(result) == await MockProvider().explain(result)

    async def test_urgency_matches_severity(self):
        results = [
            {"test_name": "K", "severity": "critical", "specialty": "nephrology"},
            {"test_name": "G", "severity": "normal"},
        ]
        critical, normal = await MockProvider().explain(results)
        assert critical.urgency == "urgent"
        assert normal.urgency == "routine"
        assert critical.next_steps and normal.next_steps

    async def test_unknown_severity_asks_the_user_to_check_the_data(self):
        results = [{"test_name": "X", "severity": "unknown", "error": "bad unit"}]
        [explanation] = await MockProvider().explain(results)
        assert "could not be interpreted" in explanation.headline
        assert any("again" in step for step in explanation.next_steps)


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

class TestProviderSelection:
    def test_mock_is_selected_explicitly(self):
        assert get_provider(Settings(llm_provider="mock")).name == "mock"

    def test_gemini_without_a_key_degrades_to_mock(self):
        # A missing key should not break startup mid-demo.
        assert get_provider(
            Settings(llm_provider="gemini", gemini_api_key="")
        ).name == "mock"

    def test_gemini_with_a_key_is_selected(self):
        provider = get_provider(
            Settings(llm_provider="gemini", gemini_api_key="test-key-not-real")
        )
        assert provider.name == "gemini"

    def test_configured_model_is_used(self):
        provider = get_provider(Settings(
            llm_provider="gemini",
            gemini_api_key="test-key-not-real",
            gemini_model="gemini-3.6-flash",
        ))
        assert provider.model == "gemini-3.6-flash"

    def test_unknown_provider_is_rejected_at_startup(self):
        with pytest.raises(ValueError, match="LLM_PROVIDER"):
            Settings(llm_provider="chatgpt")


# ---------------------------------------------------------------------------
# Retry policy
# ---------------------------------------------------------------------------

class TestGeminiRetryPolicy:
    """Which failures are worth retrying.

    Retrying a permanent error just delays the fallback to
    classifications-without-explanations, which is the useful outcome.
    """

    @staticmethod
    def _is_permanent(message: str) -> bool:
        from app.llm.gemini import _is_permanent
        return _is_permanent(Exception(message))

    @pytest.mark.parametrize("message", [
        "400 API key not valid. Please pass a valid API key.",
        "403 PERMISSION_DENIED",
        "429 Quota exceeded for this project",
        "404 NOT_FOUND. This model models/gemini-2.0-flash is no longer available.",
        "UNAUTHENTICATED",
    ])
    def test_permanent_errors_are_not_retried(self, message):
        assert self._is_permanent(message) is True

    @pytest.mark.parametrize("message", [
        "503 Service Unavailable",
        "Deadline exceeded",
        "Connection reset by peer",
        "500 Internal error",
    ])
    def test_transient_errors_are_retried(self, message):
        assert self._is_permanent(message) is False

    def test_empty_api_key_is_rejected_on_construction(self):
        from app.llm.gemini import GeminiProvider
        with pytest.raises(LLMUnavailableError, match="empty"):
            GeminiProvider(api_key="   ")
