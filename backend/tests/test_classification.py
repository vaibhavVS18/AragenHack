"""Tests for the clinical classification logic.

These target ``mcp_server.tools`` directly rather than through MCP: the
protocol is a transport, and testing across it would slow the suite without
testing anything extra. ``test_mcp_server.py`` covers the protocol layer.
"""

from __future__ import annotations

import pytest

from mcp_server.reference_ranges import REFERENCE_RANGES, resolve_test
from mcp_server.tools import (
    classify_lab_result,
    get_reference_range,
    route_by_severity,
)


# ---------------------------------------------------------------------------
# Reference range lookup
# ---------------------------------------------------------------------------

class TestReferenceRangeLookup:
    def test_exact_name(self):
        result = get_reference_range("Hemoglobin")
        assert result["found"] is True
        assert result["test_name"] == "Hemoglobin"
        assert result["matched_by"] == "exact"
        assert (result["low"], result["high"]) == (12.0, 17.5)

    def test_case_and_whitespace_insensitive(self):
        assert get_reference_range("  hEmOgLoBiN  ")["matched_by"] == "exact"

    @pytest.mark.parametrize("alias,canonical", [
        ("HGB", "Hemoglobin"),
        ("haemoglobin", "Hemoglobin"),
        ("WBC", "White Blood Cell Count"),
        ("PLT", "Platelet Count"),
        ("K+", "Potassium"),
        ("Na", "Sodium"),
        ("SGPT", "ALT"),
        ("FBS", "Glucose"),
    ])
    def test_aliases_resolve(self, alias, canonical):
        result = get_reference_range(alias)
        assert result["found"] is True
        assert result["test_name"] == canonical
        assert result["matched_by"] == "alias"

    def test_typo_matches_fuzzily(self):
        result = get_reference_range("Hemoglobn")
        assert result["found"] is True
        assert result["test_name"] == "Hemoglobin"
        assert result["matched_by"] == "fuzzy"

    def test_unknown_test_reports_known_tests(self):
        result = get_reference_range("Vitamin D")
        assert result["found"] is False
        assert "Vitamin D" in result["error"]
        assert "Hemoglobin" in result["known_tests"]

    def test_empty_name_is_not_found(self):
        assert get_reference_range("")["found"] is False

    def test_unrelated_word_does_not_fuzzy_match(self):
        # The cutoff must be strict enough that noise stays unknown rather
        # than being classified against an arbitrary range.
        assert get_reference_range("banana")["found"] is False


# ---------------------------------------------------------------------------
# Severity bands
# ---------------------------------------------------------------------------

class TestSeverityBands:
    @pytest.mark.parametrize("value,expected,band", [
        (6.9,  "critical", "critical_low"),    # below critical_low 7.0
        (7.0,  "warning",  "warning_low"),     # exactly critical_low
        (11.9, "warning",  "warning_low"),     # just below low
        (12.0, "normal",   "normal"),          # exactly low  -> normal
        (15.0, "normal",   "normal"),          # mid range
        (17.5, "normal",   "normal"),          # exactly high -> normal
        (17.6, "warning",  "warning_high"),    # just above high
        (20.0, "warning",  "warning_high"),    # exactly critical_high
        (20.1, "critical", "critical_high"),   # above critical_high
    ])
    def test_hemoglobin_bands(self, value, expected, band):
        result = classify_lab_result("Hemoglobin", value, "g/dL")
        assert result["severity"] == expected
        assert result["band"] == band

    def test_boundaries_are_inclusive_of_normal(self):
        for name, definition in REFERENCE_RANGES.items():
            low = classify_lab_result(name, definition.low, definition.unit)
            high = classify_lab_result(name, definition.high, definition.unit)
            assert low["severity"] == "normal", f"{name} low bound"
            assert high["severity"] == "normal", f"{name} high bound"

    def test_missing_critical_low_never_yields_critical(self):
        # Creatinine has no critical_low: a very low value is a warning only.
        result = classify_lab_result("Creatinine", 0.01, "mg/dL")
        assert result["severity"] == "warning"
        assert "no critical_low defined" in result["rule_fired"]

    def test_critical_high_still_applies_without_critical_low(self):
        assert classify_lab_result("Creatinine", 9.0, "mg/dL")["severity"] == "critical"


# ---------------------------------------------------------------------------
# Explainability payload
# ---------------------------------------------------------------------------

class TestExplainability:
    def test_rule_fired_states_the_actual_comparison(self):
        result = classify_lab_result("Potassium", 6.8, "mEq/L")
        assert result["rule_fired"] == "value (6.8) > critical_high (6.5)"

    def test_deviation_is_relative_to_the_limit_crossed(self):
        # 6.8 vs an upper limit of 5.1 -> (6.8 - 5.1) / 5.1 = 33.3%
        result = classify_lab_result("Potassium", 6.8, "mEq/L")
        assert result["direction"] == "above"
        assert result["deviation_pct"] == pytest.approx(33.3, abs=0.1)

    def test_normal_result_has_zero_deviation(self):
        result = classify_lab_result("Glucose", 92, "mg/dL")
        assert result["direction"] == "within"
        assert result["deviation_pct"] == 0.0

    def test_range_and_clinical_context_are_returned(self):
        result = classify_lab_result("Hemoglobin", 6.5, "g/dL")
        assert result["reference_range"]["critical_low"] == 7.0
        assert result["specialty"] == "hematology"
        assert result["measures"]

    def test_fuzzy_match_is_flagged_for_the_user(self):
        result = classify_lab_result("Hemoglobn", 15.0, "g/dL")
        assert result["matched_by"] == "fuzzy"
        assert "matched approximately" in result["notes"]


# ---------------------------------------------------------------------------
# Invalid input
# ---------------------------------------------------------------------------

class TestInvalidInput:
    @pytest.mark.parametrize("value", ["N/A", "", "  ", "abc", None, True])
    def test_non_numeric_values_are_unknown_not_crashes(self, value):
        result = classify_lab_result("Glucose", value, "mg/dL")
        assert result["severity"] == "unknown"
        assert result["error"]

    def test_negative_value_is_rejected(self):
        result = classify_lab_result("Sodium", -5, "mEq/L")
        assert result["severity"] == "unknown"
        assert "negative" in result["error"]

    def test_numeric_string_is_accepted(self):
        assert classify_lab_result("Glucose", "92", "mg/dL")["severity"] == "normal"

    def test_thousands_separator_is_accepted(self):
        result = classify_lab_result("Platelet Count", "1,200", "10^3/uL")
        assert result["severity"] == "critical"

    def test_censored_value_uses_the_stated_limit(self):
        result = classify_lab_result("TSH", "<0.1", "uIU/mL")
        assert result["value"] == 0.1
        assert result["value_qualifier"] == "<"
        assert "censored" in result["notes"]

    def test_unknown_test_is_not_guessed(self):
        result = classify_lab_result("Vitamin D", 30, "ng/mL")
        assert result["severity"] == "unknown"
        assert result["reference_range"] is None


class TestUnitHandling:
    def test_matching_unit_classifies(self):
        assert classify_lab_result("Hemoglobin", 15.0, "g/dL")["severity"] == "normal"

    def test_unit_case_and_spacing_variants_accepted(self):
        for unit in ("g/dl", "G/DL", " g/dL "):
            assert classify_lab_result("Hemoglobin", 15.0, unit)["severity"] == "normal"

    def test_missing_unit_assumes_canonical_and_flags_it(self):
        result = classify_lab_result("Hemoglobin", 15.0, None)
        assert result["severity"] == "normal"
        assert result["unit_assumed"] is True

    def test_conflicting_unit_refuses_rather_than_converting(self):
        # 5.2 mmol/L glucose is normal, but 5.2 mg/dL would be critical.
        # Guessing here would produce a confidently wrong answer.
        result = classify_lab_result("Glucose", 5.2, "mmol/L")
        assert result["severity"] == "unknown"
        assert "not comparable" in result["error"]

    def test_micro_sign_variants_are_equivalent(self):
        for unit in ("10^3/uL", "10^3/µL", "K/uL"):
            assert classify_lab_result("White Blood Cell Count", 7.0, unit)["severity"] == "normal"


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

class TestRouting:
    @staticmethod
    def _batch():
        return [
            classify_lab_result("Glucose", 92, "mg/dL"),        # normal
            classify_lab_result("Potassium", 6.8, "mEq/L"),     # critical
            classify_lab_result("Vitamin D", 30, "ng/mL"),      # unknown
            classify_lab_result("Creatinine", 2.1, "mg/dL"),    # warning
            classify_lab_result("Hemoglobin", 6.0, "g/dL"),     # critical
        ]

    def test_ordered_critical_first_then_warning_then_normal(self):
        routed = route_by_severity(self._batch())
        assert [r["severity"] for r in routed["ordered"]] == [
            "critical", "critical", "warning", "normal", "unknown",
        ]

    def test_most_deviant_leads_within_a_group(self):
        routed = route_by_severity(self._batch())
        criticals = routed["groups"]["critical"]
        assert criticals[0]["deviation_pct"] >= criticals[1]["deviation_pct"]

    def test_summary_counts(self):
        summary = route_by_severity(self._batch())["summary"]
        assert summary == {
            "critical": 2, "warning": 1, "normal": 1, "unknown": 1,
            "total": 5, "abnormal": 3,
        }

    def test_highest_severity(self):
        assert route_by_severity(self._batch())["highest_severity"] == "critical"

    def test_empty_batch_is_safe(self):
        routed = route_by_severity([])
        assert routed["ordered"] == []
        assert routed["summary"]["total"] == 0
        assert routed["highest_severity"] == "normal"

    def test_all_normal_reports_normal_as_highest(self):
        batch = [classify_lab_result("Glucose", 92, "mg/dL")]
        assert route_by_severity(batch)["highest_severity"] == "normal"


# ---------------------------------------------------------------------------
# Table integrity - guards against typos when ranges are edited
# ---------------------------------------------------------------------------

class TestTableIntegrity:
    @pytest.mark.parametrize("key", list(REFERENCE_RANGES))
    def test_thresholds_are_ordered(self, key):
        d = REFERENCE_RANGES[key]
        assert d.low < d.high, f"{key}: low must be below high"
        if d.critical_low is not None:
            assert d.critical_low < d.low, f"{key}: critical_low must be below low"
        if d.critical_high is not None:
            assert d.critical_high > d.high, f"{key}: critical_high must exceed high"

    @pytest.mark.parametrize("key", list(REFERENCE_RANGES))
    def test_every_test_has_clinical_context(self, key):
        d = REFERENCE_RANGES[key]
        assert d.unit and d.measures and d.specialty and d.category

    @pytest.mark.parametrize("key", list(REFERENCE_RANGES))
    def test_canonical_name_resolves_to_itself(self, key):
        definition, matched_by = resolve_test(REFERENCE_RANGES[key].canonical_name)
        assert definition is REFERENCE_RANGES[key]
        assert matched_by == "exact"

    def test_no_alias_is_claimed_by_two_tests(self):
        seen: dict[str, str] = {}
        for key, d in REFERENCE_RANGES.items():
            for alias in d.aliases:
                assert alias not in seen, f"{alias!r} claimed by {seen.get(alias)} and {key}"
                seen[alias] = key
