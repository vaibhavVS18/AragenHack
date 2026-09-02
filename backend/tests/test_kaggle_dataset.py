"""Validation against the real Kaggle dataset.

Source: "Laboratory Test Results - Anonymized Dataset"
(pinar-topuz/lab-test-results, CC0-1.0), stored at ``data/``.

The dataset carries a ``Status`` column - the laboratory's own verdict of
Normal / Yüksek (high) / Düşük (low). That is ground truth, and these tests
check our classifier against it.

Note what is *not* used: ``Status``, ``Comment`` and ``Recommended_Followup``
never reach the classifier. Only ``Test_Name``, ``Result``, ``Unit`` and the
reference columns do. Feeding the answer in would make the comparison
meaningless.

Skipped automatically when the dataset is absent, so the suite still runs on a
fresh clone.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

from app.csv_loader import parse_csv
from mcp_server.tools import classify_lab_result, route_by_severity

DATASET = Path(__file__).resolve().parent.parent.parent / "data" / "lab_test_results_public.csv"

pytestmark = pytest.mark.skipif(
    not DATASET.exists(),
    reason="Kaggle dataset not present in data/ - see README",
)

# The dataset's Status vocabulary is Turkish.
STATUS_NORMAL = {"normal"}
STATUS_ABNORMAL = {"yüksek", "yuksek", "düşük", "dusuk", "high", "low"}


@pytest.fixture(scope="module")
def raw_bytes() -> bytes:
    return DATASET.read_bytes()


@pytest.fixture(scope="module")
def parsed(raw_bytes):
    labs, errors, patient_id = parse_csv(raw_bytes)
    return labs, errors, patient_id


@pytest.fixture(scope="module")
def classified(parsed):
    labs, _, _ = parsed
    return [
        classify_lab_result(
            lab.test_name, lab.value, lab.unit,
            lab.reference_low, lab.reference_high, lab.reference_text,
        )
        for lab in labs
    ]


@pytest.fixture(scope="module")
def expected_statuses(raw_bytes):
    """The dataset's own Status per row, used only for comparison."""
    text = raw_bytes.decode("utf-8-sig")
    return [row["Status"].strip().lower() for row in csv.DictReader(io.StringIO(text))]


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

class TestIngestion:
    def test_every_row_parses(self, parsed):
        labs, errors, _ = parsed
        assert len(labs) == 27
        assert errors == []

    def test_turkish_names_resolve_to_canonical_tests(self, classified):
        names = {r["test_name"] for r in classified}
        # Trombosit, Lökosit, Eritrosit, Hematokrit, İnsülin, Serbest T4
        assert "Platelet Count" in names
        assert "White Blood Cell Count" in names
        assert "Red Blood Cell Count" in names
        assert "Hematocrit" in names
        assert "Insulin" in names
        assert "Free T4" in names

    def test_urinalysis_strips_are_not_confused_with_blood_counts(self, classified):
        # "Lökosit" is the WBC count; "Lökosit (Strip)" is a urine dipstick.
        # Fuzzy matching must not collapse the two.
        by_name = {r["test_name"]: r for r in classified}
        assert by_name["White Blood Cell Count"]["comparison"] == "numeric"
        assert by_name["Lökosit (Strip)"]["comparison"] == "qualitative"

    def test_reference_interval_is_read_from_the_row(self, parsed):
        labs, _, _ = parsed
        platelets = next(l for l in labs if l.test_name == "Trombosit")
        assert (platelets.reference_low, platelets.reference_high) == (150.0, 450.0)

    def test_qualitative_expectation_is_read_from_the_row(self, parsed):
        labs, _, _ = parsed
        nitrite = next(l for l in labs if l.test_name == "Nitrit (Strip)")
        assert nitrite.reference_text == "Negatif"
        assert nitrite.reference_low is None


# ---------------------------------------------------------------------------
# Classification vs the dataset's own verdict
# ---------------------------------------------------------------------------

class TestAgreementWithDataset:
    def test_nothing_is_left_unclassified(self, classified):
        unknown = [r for r in classified if r["severity"] == "unknown"]
        assert unknown == [], (
            "Unclassified rows: "
            + ", ".join(f"{r['test_name']} ({r['error']})" for r in unknown)
        )

    def test_every_severity_is_one_of_the_three_grades(self, classified):
        assert {r["severity"] for r in classified} <= {"critical", "warning", "normal"}

    def test_our_verdict_matches_the_laboratory_verdict(
        self, classified, expected_statuses
    ):
        # The dataset grades Normal / Yüksek / Düşük. We grade Normal /
        # Warning / Critical. They agree at the level both express: whether
        # the result is normal.
        mismatches = []
        for result, status in zip(classified, expected_statuses):
            ours_is_normal = result["severity"] == "normal"
            theirs_is_normal = status in STATUS_NORMAL

            if theirs_is_normal != ours_is_normal:
                mismatches.append(
                    f"{result['test_name']}: dataset={status!r} ours={result['severity']!r}"
                )

        assert not mismatches, "Disagreements: " + "; ".join(mismatches)

    def test_the_one_abnormal_row_is_flagged(self, classified, expected_statuses):
        abnormal = [
            r for r, s in zip(classified, expected_statuses) if s in STATUS_ABNORMAL
        ]
        assert len(abnormal) == 1

        strip = abnormal[0]
        assert strip["test_name"] == "Eritrosit (Strip)"
        assert strip["severity"] == "warning"
        assert strip["comparison"] == "qualitative"
        assert "!=" in strip["rule_fired"]


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------

class TestRangeProvenance:
    def test_the_rows_own_interval_is_preferred(self, classified):
        # Hemoglobin: this laboratory uses 12-15 g/dL; our built-in table says
        # 12-17.5. The row's interval must win, because a laboratory's own
        # range is authoritative for its own result.
        hemoglobin = next(r for r in classified if r["test_name"] == "Hemoglobin")
        assert hemoglobin["range_source"] == "supplied"
        assert hemoglobin["reference_range"]["high"] == 15.0

    def test_known_tests_keep_their_real_critical_thresholds(self, classified):
        # The dataset has no concept of a critical value. Where we know the
        # test, our published panic values are still applied.
        hemoglobin = next(r for r in classified if r["test_name"] == "Hemoglobin")
        assert hemoglobin["critical_basis"] == "table"
        assert hemoglobin["reference_range"]["critical_low"] == 7.0

    def test_unknown_tests_label_their_criticals_as_derived(self, classified):
        # RDW is not in our table, so any critical threshold is an estimate
        # and must say so rather than pose as a clinical panic value.
        rdw = next(r for r in classified if r["test_name"] == "RDW")
        assert rdw["range_source"] == "supplied"
        assert rdw["critical_basis"] == "derived"

    def test_every_result_carries_its_reasoning(self, classified):
        for result in classified:
            assert result["rule_fired"], f"{result['test_name']} has no rule"
            assert result["range_source"] in {"supplied", "internal"}
            assert result["comparison"] in {"numeric", "qualitative"}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

class TestRouting:
    def test_the_abnormal_result_is_routed_first(self, classified):
        routed = route_by_severity(classified)
        assert routed["ordered"][0]["test_name"] == "Eritrosit (Strip)"
        assert routed["summary"]["total"] == 27
        assert routed["summary"]["abnormal"] == 1
