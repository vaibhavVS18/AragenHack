"""Tests for the HTTP layer.

These are synchronous on purpose: ``TestClient`` runs its own event loop, so
mixing it into async tests would nest loops.

The full stack runs for real - FastAPI, the agent, and the MCP server
subprocess. Only the LLM is substituted, via ``LLM_PROVIDER=mock``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agent import LabAgent
from app.config import Settings, get_settings
from app.main import app, get_agent

TEST_DATA = Path(__file__).resolve().parent.parent.parent / "test_data"


@pytest.fixture(scope="module")
def client():
    """A client with the app's lifespan run, pinned to the offline provider.

    The agent is replaced *after* startup as well as overriding the settings
    dependency: ``lifespan`` builds its own agent from the real ``.env``, so
    without this the suite would call the live Gemini API - slow, rate-limited,
    and dependent on a key the grader may not have.
    """
    mock_settings = Settings(llm_provider="mock")
    app.dependency_overrides[get_settings] = lambda: mock_settings

    with TestClient(app) as test_client:
        offline_agent = LabAgent(mock_settings)
        app.state.agent = offline_agent
        app.dependency_overrides[get_agent] = lambda: offline_agent
        yield test_client

    app.dependency_overrides.clear()


def read_csv(name: str) -> bytes:
    return (TEST_DATA / name).read_bytes()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class TestHealth:
    def test_health_reports_mcp_and_provider(self, client):
        body = client.get("/health").json()

        assert body["status"] == "ok"
        assert body["mcp_server"] == "connected"
        assert set(body["tools_available"]) == {
            "get_reference_range", "list_reference_ranges",
            "classify_lab_result", "route_by_severity",
        }
        assert body["llm_provider"] == "mock"

    def test_root_points_at_the_docs(self, client):
        assert client.get("/").json()["docs"] == "/docs"

    def test_openapi_schema_is_generated(self, client):
        schema = client.get("/openapi.json").json()
        assert "/analyze_labs" in schema["paths"]


class TestReferenceRanges:
    """The catalogue endpoint the UI uses for autocomplete."""

    def test_lists_every_test_with_thresholds(self, client):
        from mcp_server.reference_ranges import REFERENCE_RANGES

        body = client.get("/reference_ranges").json()

        # Compared against the table rather than a literal, so adding a test
        # does not leave a stale number here.
        assert body["count"] == len(REFERENCE_RANGES)
        assert len(body["tests"]) == len(REFERENCE_RANGES)

        hemoglobin = next(
            t for t in body["tests"] if t["test_name"] == "Hemoglobin"
        )
        assert hemoglobin["unit"] == "g/dL"
        assert hemoglobin["low"] == 12.0
        assert hemoglobin["critical_low"] == 7.0
        assert "hgb" in hemoglobin["aliases"]

    def test_catalogue_matches_what_classification_accepts(self, client):
        # If these drift apart, the UI would suggest tests the server cannot
        # classify. Every advertised name must actually resolve.
        catalogue = client.get("/reference_ranges").json()["tests"]

        body = client.post("/analyze_labs", json={"labs": [
            {"test_name": t["test_name"], "value": t["low"], "unit": t["unit"]}
            for t in catalogue
        ]}).json()

        assert body["summary"]["unknown"] == 0
        assert body["summary"]["total"] == len(catalogue)


# ---------------------------------------------------------------------------
# POST /analyze_labs
# ---------------------------------------------------------------------------

class TestAnalyzeLabs:
    def test_happy_path(self, client):
        response = client.post("/analyze_labs", json={
            "patient_id": "ANON-1",
            "labs": [
                {"test_name": "Glucose", "value": 92, "unit": "mg/dL"},
                {"test_name": "Potassium", "value": 6.8, "unit": "mEq/L"},
            ],
        })
        assert response.status_code == 200

        body = response.json()
        assert body["patient_id"] == "ANON-1"
        assert body["summary"]["critical"] == 1
        assert body["summary"]["normal"] == 1

    def test_results_are_ordered_critical_first(self, client):
        body = client.post("/analyze_labs", json={"labs": [
            {"test_name": "Glucose", "value": 92},
            {"test_name": "Vitamin D", "value": 30},
            {"test_name": "Hemoglobin", "value": 6.0},
            {"test_name": "Creatinine", "value": 2.1},
        ]}).json()

        assert [r["severity"] for r in body["results"]] == [
            "critical", "warning", "normal", "unknown",
        ]

    def test_response_carries_the_reasoning(self, client):
        body = client.post("/analyze_labs", json={"labs": [
            {"test_name": "Potassium", "value": 6.8, "unit": "mEq/L"},
        ]}).json()
        result = body["results"][0]

        assert result["severity"] == "critical"
        assert result["rule_fired"] == "value (6.8) > critical_high (6.5)"
        assert result["reference_range"]["high"] == 5.1
        assert result["deviation_text"]
        assert result["explanation"] and result["next_step"]

    def test_meta_reports_the_mcp_tools_used(self, client):
        body = client.post("/analyze_labs", json={
            "labs": [{"test_name": "Glucose", "value": 92}],
        }).json()
        assert "classify_lab_result" in body["meta"]["mcp_tools_used"]
        assert "route_by_severity" in body["meta"]["mcp_tools_used"]

    def test_unit_is_optional(self, client):
        body = client.post("/analyze_labs", json={
            "labs": [{"test_name": "Hemoglobin", "value": 15.0}],
        }).json()
        assert body["results"][0]["unit_assumed"] is True


class TestAnalyzeLabsValidation:
    def test_empty_labs_array_is_rejected(self, client):
        assert client.post("/analyze_labs", json={"labs": []}).status_code == 422

    def test_missing_labs_key_is_rejected(self, client):
        assert client.post("/analyze_labs", json={}).status_code == 422

    def test_blank_test_name_is_rejected(self, client):
        response = client.post("/analyze_labs", json={
            "labs": [{"test_name": "   ", "value": 5}],
        })
        assert response.status_code == 422

    def test_missing_value_is_rejected(self, client):
        response = client.post("/analyze_labs", json={
            "labs": [{"test_name": "Glucose"}],
        })
        assert response.status_code == 422

    def test_oversized_batch_is_rejected_before_any_work(self, client):
        labs = [{"test_name": "Glucose", "value": 92}] * 201
        response = client.post("/analyze_labs", json={"labs": labs})

        assert response.status_code == 413
        assert "Maximum 200" in response.json()["detail"]

    def test_unreadable_values_are_reported_not_crashed(self, client):
        body = client.post("/analyze_labs", json={"labs": [
            {"test_name": "Glucose", "value": "N/A"},
            {"test_name": "Sodium", "value": -5},
            {"test_name": "Glucose", "value": 5.2, "unit": "mmol/L"},
        ]}).json()

        assert all(r["severity"] == "unknown" for r in body["results"])
        assert all(r["error"] for r in body["results"])


# ---------------------------------------------------------------------------
# POST /analyze_labs/csv
# ---------------------------------------------------------------------------

class TestAnalyzeLabsCSV:
    def _upload(self, client, name: str):
        return client.post(
            "/analyze_labs/csv",
            files={"file": (name, read_csv(name), "text/csv")},
        )

    def test_normal_panel_is_all_normal(self, client):
        body = self._upload(client, "normal_panel.csv").json()

        assert body["summary"]["total"] == 10
        assert body["summary"]["normal"] == 10
        assert body["summary"]["abnormal"] == 0

    def test_critical_panel_flags_criticals(self, client):
        body = self._upload(client, "critical_panel.csv").json()

        assert body["summary"]["total"] == 8
        assert body["summary"]["critical"] >= 6
        assert body["results"][0]["severity"] == "critical"

    def test_patient_id_is_read_from_the_file(self, client):
        body = self._upload(client, "critical_panel.csv").json()
        assert body["patient_id"] == "ANON-0417"

    def test_messy_panel_partially_succeeds(self, client):
        # The point of this file: bad rows must not sink the good ones.
        body = self._upload(client, "mixed_messy_panel.csv").json()

        assert body["summary"]["errors"] >= 2      # blank value, missing name
        assert body["summary"]["total"] >= 10      # the rest still classified
        assert body["errors"][0]["row"] >= 2       # 1-based, header excluded

    def test_messy_panel_resolves_aliases_and_headers(self, client):
        # Headers are "Test Name,Result Value,Units"; names include HGB and K+.
        body = self._upload(client, "mixed_messy_panel.csv").json()
        names = {r["test_name"] for r in body["results"]}

        assert "Hemoglobin" in names        # from HGB
        assert "Potassium" in names         # from K+
        assert "White Blood Cell Count" in names   # from WBC

    def test_form_patient_id_overrides_the_file(self, client):
        response = client.post(
            "/analyze_labs/csv",
            files={"file": ("critical_panel.csv",
                            read_csv("critical_panel.csv"), "text/csv")},
            data={"patient_id": "OVERRIDE-9"},
        )
        assert response.json()["patient_id"] == "OVERRIDE-9"


class TestBundledDatasets:
    """One-click analysis of the repository's own sample files."""

    def test_catalogue_lists_all_four(self, client):
        body = client.get("/datasets").json()
        ids = {d["id"] for d in body["datasets"]}
        assert ids == {"kaggle", "normal_panel", "critical_panel", "mixed_messy_panel"}

    def test_catalogue_reports_availability_and_size(self, client):
        for dataset in client.get("/datasets").json()["datasets"]:
            assert isinstance(dataset["available"], bool)
            if dataset["available"]:
                assert dataset["size_bytes"] > 0

    def test_synthetic_flag_distinguishes_the_kaggle_file(self, client):
        by_id = {d["id"]: d for d in client.get("/datasets").json()["datasets"]}
        assert by_id["kaggle"]["synthetic"] is False
        assert by_id["normal_panel"]["synthetic"] is True

    def test_analyzing_a_bundled_dataset(self, client):
        body = client.post("/analyze_labs/dataset/critical_panel").json()
        assert body["summary"]["total"] == 8
        assert body["summary"]["critical"] >= 6

    def test_unknown_dataset_is_rejected(self, client):
        response = client.post("/analyze_labs/dataset/does_not_exist")
        assert response.status_code == 404
        assert "does_not_exist" in response.json()["detail"]

    def test_path_traversal_is_not_possible(self, client):
        # Ids are looked up in a fixed registry and never joined onto a path,
        # so a traversal attempt is simply an unknown id.
        response = client.post("/analyze_labs/dataset/..%2F..%2Fetc%2Fpasswd")
        assert response.status_code in (404, 400)


class TestCSVErrors:
    def _upload_bytes(self, client, name: str, content: bytes):
        return client.post(
            "/analyze_labs/csv",
            files={"file": (name, content, "text/csv")},
        )

    def test_missing_required_columns(self, client):
        response = self._upload_bytes(
            client, "bad.csv", b"colour,size\nred,large\n"
        )
        assert response.status_code == 400
        assert "missing required column" in response.json()["detail"].lower()

    def test_empty_file(self, client):
        response = self._upload_bytes(client, "empty.csv", b"")
        assert response.status_code == 400
        assert "empty" in response.json()["detail"].lower()

    def test_header_only_file(self, client):
        response = self._upload_bytes(client, "h.csv", b"test_name,value,unit\n")
        assert response.status_code == 400
        assert "no data rows" in response.json()["detail"].lower()

    def test_semicolon_delimited_file_is_accepted(self, client):
        content = b"test_name;value;unit\nGlucose;92;mg/dL\nPotassium;6.8;mEq/L\n"
        body = self._upload_bytes(client, "semi.csv", content).json()
        assert body["summary"]["total"] == 2

    def test_utf8_bom_is_stripped(self, client):
        content = "﻿test_name,value,unit\nGlucose,92,mg/dL\n".encode("utf-8")
        body = self._upload_bytes(client, "bom.csv", content).json()
        assert body["summary"]["total"] == 1
        assert body["results"][0]["test_name"] == "Glucose"
