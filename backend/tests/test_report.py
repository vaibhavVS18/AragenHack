"""Tests for the generated PDF report.

A PDF is opaque, so these assert the things that can actually go wrong:
that it is a valid document, that it paginates rather than truncating, and
that the words which must appear on a clinical report do appear.

The layout itself is verified by eye. Asserting on glyph positions would
break on every deliberate design change while catching nothing real.
"""

from __future__ import annotations

from io import BytesIO

import pytest
from pypdf import PdfReader

from app.report import build_report

RESPONSE = {
    "patient_id": "ANON-0417",
    "summary": {
        "total": 3, "critical": 1, "warning": 1, "normal": 1,
        "unknown": 0, "abnormal": 2, "errors": 1,
    },
    "results": [
        {
            "test_name": "Potassium", "value": 6.9, "unit": "mEq/L",
            "severity": "critical",
            "reference_range": {"low": 3.5, "high": 5.1, "critical_low": 2.5,
                                "critical_high": 6.5, "unit": "mEq/L"},
            "rule_fired": "value (6.9) > critical_high (6.5)",
            "explanation": "Your potassium is dangerously high.",
            "next_step": "Seek emergency medical evaluation immediately",
            "explanation_detail": {
                "headline": "Your potassium level is dangerously high.",
                "what_it_measures": "An electrolyte your heart depends on.",
                "what_result_means": "6.9 mEq/L is well above the normal range.",
                "urgency": "emergency",
                "urgency_reason": "It can disturb heart rhythm.",
                "possible_causes": ["Kidney problems", "Certain medications"],
                "next_steps": ["Seek emergency medical evaluation immediately",
                               "Bring this report with you"],
                "questions_to_ask": ["What is causing this?"],
            },
        },
        {
            "test_name": "Hemoglobin", "value": 10.8, "unit": "g/dL",
            "severity": "warning",
            "reference_range": {"low": 12.0, "high": 17.5, "critical_low": 7.0,
                                "critical_high": 20.0, "unit": "g/dL"},
            "rule_fired": "critical_low (7) <= value (10.8) < low (12)",
            "explanation": "Mildly low.",
            "next_step": "Book an appointment",
            "explanation_detail": {
                "headline": "Your hemoglobin is a little low.",
                "what_it_measures": "How well your blood carries oxygen.",
                "what_result_means": "Slightly below the normal range.",
                "urgency": "soon", "urgency_reason": "Worth checking.",
                "possible_causes": ["Iron deficiency"],
                "next_steps": ["Book an appointment"],
                "questions_to_ask": [],
            },
        },
        {
            "test_name": "Calcium", "value": 10.0, "unit": "mg/dL",
            "severity": "normal",
            "reference_range": {"low": 8.5, "high": 10.5, "critical_low": 6.0,
                                "critical_high": 13.0, "unit": "mg/dL"},
            "rule_fired": "low (8.5) <= value (10) <= high (10.5)",
            "explanation": "Normal.",
            "next_step": "Keep to your routine testing schedule",
            "explanation_detail": {
                "headline": "Your calcium is normal.",
                "what_it_measures": "A mineral for bones and nerves.",
                "what_result_means": "Comfortably within range.",
                "urgency": "routine", "urgency_reason": "No action needed.",
                "possible_causes": [],
                "next_steps": ["Keep to your routine testing schedule"],
                "questions_to_ask": [],
            },
        },
    ],
    "errors": [{"row": 7, "test_name": "Creatinine", "error": "Missing value."}],
    "meta": {"llm_provider": "mock", "llm_model": None, "llm_available": True,
             "llm_error": None, "elapsed_ms": 1200, "mcp_tools_used": []},
}


@pytest.fixture(scope="module")
def pdf_bytes() -> bytes:
    return build_report(RESPONSE)


@pytest.fixture(scope="module")
def reader(pdf_bytes: bytes) -> PdfReader:
    return PdfReader(BytesIO(pdf_bytes))


@pytest.fixture(scope="module")
def text(reader: PdfReader) -> str:
    return "\n".join(page.extract_text() for page in reader.pages)


class TestDocument:
    def test_is_a_valid_pdf(self, pdf_bytes):
        assert pdf_bytes.startswith(b"%PDF-")
        assert len(pdf_bytes) > 2000

    def test_metadata_identifies_the_report(self, reader):
        assert "Laboratory Results Report" in reader.metadata.title
        assert "ANON-0417" in reader.metadata.title
        assert reader.metadata.author == "Aragen AI"

    def test_paginates_rather_than_truncating(self, reader, text):
        # Every result must appear, however many pages that takes.
        assert len(reader.pages) >= 1
        for name in ("Potassium", "Hemoglobin", "Calcium"):
            assert name in text

    def test_every_page_carries_the_footer(self, reader):
        for index, page in enumerate(reader.pages, start=1):
            page_text = page.extract_text()
            assert f"Page {index} of {len(reader.pages)}" in page_text, (
                f"page {index} has no page number"
            )
            assert "not a medical diagnosis" in page_text

    def test_every_page_carries_the_letterhead(self, reader):
        for page in reader.pages:
            page_text = page.extract_text()
            assert "Aragen" in page_text
            assert "ANON-0417" in page_text


class TestContent:
    def test_summary_counts_appear(self, text):
        # Labels must fit one line at five columns; a wrap here would mean the
        # wording grew past the column width again.
        for label in ("RESULTS CHECKED", "URGENT ATTENTION", "OUT OF RANGE",
                      "IN RANGE", "NOT READ"):
            assert label in text, f"{label!r} missing or wrapped"

    def test_verdict_leads_the_document(self, text):
        assert "One result needs urgent attention" in text
        assert "Start with Potassium" in text

    def test_severity_sections_are_labelled(self, text):
        assert "CRITICAL (1)" in text
        assert "WARNING (1)" in text
        assert "NORMAL (1)" in text

    def test_explanation_fields_are_laid_out(self, text):
        # Labels wrap inside a 34mm column, so assert on the leading words
        # rather than the whole phrase.
        for label in ("WHAT THIS TEST", "WHAT YOUR", "COMMON CAUSES",
                      "HOW SOON TO ACT", "WHAT TO DO", "QUESTIONS FOR"):
            assert label in text, f"{label!r} missing"

    def test_urgency_is_stated_in_plain_words(self, text):
        # "emergency" is our vocabulary; the report says what it means.
        assert "SEEK CARE TODAY" in text

    def test_reference_ranges_are_printed(self, text):
        assert "Normal range 3.5-5.1 mEq/L" in text

    def test_unreadable_rows_are_reported(self, text):
        assert "ENTRIES WE COULD NOT READ" in text
        assert "Missing value." in text

    def test_no_replacement_glyphs(self, text):
        # Typographic punctuation is folded to ASCII on the way in; anything
        # that slipped through would surface here.
        assert "�" not in text


class TestPagination:
    """The blank-first-page bug.

    Each result used to be wrapped in a one-cell table so the border and rail
    had something to draw on. A table cell is atomic, so a result taller than
    the space left on the page moved to the next one whole - leaving the first
    page empty below the summary. The block is now one flat table that splits
    at row boundaries.
    """

    @staticmethod
    def _single_result_pdf():
        response = {
            **RESPONSE,
            "summary": {"total": 1, "critical": 0, "warning": 1, "normal": 0,
                        "unknown": 0, "abnormal": 1, "errors": 0},
            "results": [RESPONSE["results"][0]],
            "errors": [],
        }
        return build_report(response)

    def test_one_result_fits_a_single_page(self):
        reader = PdfReader(BytesIO(self._single_result_pdf()))
        assert len(reader.pages) == 1, (
            f"one result should not need {len(reader.pages)} pages"
        )

    def test_no_page_is_left_substantially_empty(self):
        # A page carrying only furniture means a block jumped rather than split.
        reader = PdfReader(BytesIO(build_report(RESPONSE)))
        for index, page in enumerate(reader.pages, start=1):
            body = page.extract_text()
            for furniture in ("Aragen", "not a medical diagnosis",
                              f"Page {index} of {len(reader.pages)}"):
                body = body.replace(furniture, "")
            assert len(body.strip()) > 200, (
                f"page {index} carries almost no content"
            )


class TestEdgeCases:
    def test_empty_analysis_still_produces_a_document(self):
        pdf = build_report({
            "patient_id": None,
            "summary": {"total": 0, "critical": 0, "warning": 0, "normal": 0,
                        "unknown": 0, "abnormal": 0, "errors": 0},
            "results": [], "errors": [],
            "meta": {"llm_provider": "mock", "llm_model": None,
                     "llm_available": True, "llm_error": None,
                     "elapsed_ms": 0, "mcp_tools_used": []},
        })
        assert pdf.startswith(b"%PDF-")

    def test_result_without_an_explanation_still_renders(self):
        # Degraded mode: the LLM failed, classification survived.
        response = {
            **RESPONSE,
            "results": [{**RESPONSE["results"][0],
                         "explanation": None, "next_step": None,
                         "explanation_detail": None}],
            "errors": [],
        }
        text = PdfReader(BytesIO(build_report(response))).pages[0].extract_text()
        assert "Potassium" in text
        assert "6.9" in text

    def test_markup_in_user_data_is_escaped_not_rendered(self):
        # Test names come from an uploaded file; ReportLab paragraphs accept a
        # mini-XML, so an unescaped tag would corrupt the document.
        response = {
            **RESPONSE,
            "results": [{**RESPONSE["results"][0],
                         "test_name": "<b>Potassium</b> & <i>K+</i>"}],
            "errors": [],
        }
        text = PdfReader(BytesIO(build_report(response))).pages[0].extract_text()
        assert "<b>Potassium</b>" in text
