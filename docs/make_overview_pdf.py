"""Generate the one-page project overview PDF.

Committed as a script rather than only as its output, so the PDF can be
regenerated when the project changes instead of drifting from it:

    cd backend && .venv/Scripts/python ../docs/make_overview_pdf.py

Deliberately dense. The brief was a summary of the tools and features, not a
second copy of the README - so it is built to fit two pages and stop, with
tables rather than prose, and every claim short enough to be scanned.

Palette and letterhead match app/report.py, because a reader who has seen the
generated lab report should recognise this as the same product.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# -- palette, shared with the lab report ---------------------------------

INK = colors.HexColor("#101828")
BODY = colors.HexColor("#3F4759")
MUTED = colors.HexColor("#6B7387")
HAIRLINE = colors.HexColor("#DDE2EC")
PANEL = colors.HexColor("#F4F6FA")
ACCENT = colors.HexColor("#4839CF")

PAGE_MARGIN = 14 * mm
HEADER_RULE_DROP = 12 * mm
HEADER_HEIGHT = PAGE_MARGIN + HEADER_RULE_DROP + 6 * mm
FOOTER_HEIGHT = 12 * mm

OUT = Path(__file__).resolve().parent / "AragenAI-Project-Overview.pdf"


# -- styles ---------------------------------------------------------------

def _styles() -> dict[str, ParagraphStyle]:
    base = ParagraphStyle(
        "base", fontName="Helvetica", fontSize=7.6, leading=10.2,
        textColor=BODY, alignment=TA_LEFT,
    )
    return {
        "title": ParagraphStyle(
            "title", parent=base, fontName="Helvetica-Bold", fontSize=16,
            leading=19, textColor=INK, spaceAfter=2,
        ),
        "lede": ParagraphStyle(
            "lede", parent=base, fontSize=9, leading=12.6, textColor=BODY,
            spaceAfter=9,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base, fontName="Helvetica-Bold", fontSize=9.5,
            leading=12, textColor=ACCENT, spaceBefore=8, spaceAfter=4,
        ),
        "cell": base,
        "cellb": ParagraphStyle(
            "cellb", parent=base, fontName="Helvetica-Bold", textColor=INK,
        ),
        "th": ParagraphStyle(
            "th", parent=base, fontName="Helvetica-Bold", fontSize=7,
            textColor=MUTED,
        ),
        "note": ParagraphStyle(
            "note", parent=base, fontSize=7.2, leading=9.6, textColor=MUTED,
        ),
    }


S = _styles()


def P(text: str, style: str = "cell") -> Paragraph:
    return Paragraph(text, S[style])


# -- letterhead -----------------------------------------------------------

def _mark(c, x, y, size):
    """The Pulse Mark: a rounded badge with a serif A and a signal dot."""
    c.saveState()
    c.setFillColor(ACCENT)
    c.roundRect(x, y, size, size, size * 0.28, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Times-Bold", size * 0.62)
    c.drawCentredString(x + size / 2, y + size * 0.29, "A")
    c.setFillColor(colors.HexColor("#34D399"))
    c.circle(x + size * 0.82, y + size * 0.82, size * 0.1, stroke=0, fill=1)
    c.restoreState()


def _page(canvas, doc):
    canvas.saveState()
    width, height = A4
    top = height - PAGE_MARGIN

    _mark(canvas, PAGE_MARGIN, top - 8 * mm, 8 * mm)

    x = PAGE_MARGIN + 11 * mm
    canvas.setFillColor(INK)
    canvas.setFont("Helvetica-Bold", 11.5)
    canvas.drawString(x, top - 5.6 * mm, "Aragen")
    # Measured, never guessed: a hardcoded offset drew the suffix on top of
    # the wordmark the first time this was written.
    canvas.setFillColor(ACCENT)
    canvas.setFont("Helvetica-Bold", 7)
    canvas.drawString(x + stringWidth("Aragen", "Helvetica-Bold", 11.5) + 1.2,
                      top - 4.2 * mm, "AI")

    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(width - PAGE_MARGIN, top - 4 * mm,
                           "Clinical Lab Results Analyzer")
    canvas.drawRightString(width - PAGE_MARGIN, top - 7.6 * mm,
                           f"Project overview · {date.today():%d %b %Y}")

    canvas.setStrokeColor(HAIRLINE)
    canvas.setLineWidth(0.6)
    canvas.line(PAGE_MARGIN, top - HEADER_RULE_DROP,
                width - PAGE_MARGIN, top - HEADER_RULE_DROP)

    canvas.line(PAGE_MARGIN, PAGE_MARGIN + 6 * mm,
                width - PAGE_MARGIN, PAGE_MARGIN + 6 * mm)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.6)
    canvas.drawString(PAGE_MARGIN, PAGE_MARGIN + 2.4 * mm,
                      "github.com/vaibhavVS18/AragenHack")
    canvas.drawRightString(width - PAGE_MARGIN, PAGE_MARGIN + 2.4 * mm,
                           f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


# -- table helper ---------------------------------------------------------

def table(headers: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data = [[P(h, "th") for h in headers]]
    data += [[P(c) for c in row] for row in rows]

    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PANEL),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, HAIRLINE),
        ("LINEBELOW", (0, 1), (-1, -2), 0.3, HAIRLINE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3.4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.4),
    ]))
    return t


# -- content --------------------------------------------------------------

FEATURES = [
    ["<b>Deterministic classification</b>",
     "Normal / Warning / Critical decided by a fixed threshold comparison — never by the LLM",
     "MCP tool <font face='Courier'>classify_lab_result</font>"],
    ["<b>Severity routing</b>",
     "Results ordered worst-first, with counts per severity",
     "MCP tool <font face='Courier'>route_by_severity</font>"],
    ["<b>Reference table</b>",
     "16 tests with aliases, units, and critical thresholds — served to the UI, never hardcoded in it",
     "MCP tool <font face='Courier'>list_reference_ranges</font>"],
    ["<b>Written explanations</b>",
     "What the test measures, what your result means, causes, urgency, next steps, questions for a doctor",
     "Google Gemini 3.5-flash-lite, one batched call"],
    ["<b>Audit trail</b>",
     "Every card expands to the literal comparison that fired, the range used, and where it came from",
     "Python; surfaced in the API response"],
    ["<b>PDF lab report</b>",
     "The panel as a real document: measured tables, row-aware page breaks, Page X of Y, branding",
     "ReportLab, server-side"],
    ["<b>CSV export</b>",
     "Full result set including ranges and the rule that fired",
     "Browser-side; no round trip"],
    ["<b>Assistant — about the app</b>",
     "Answers from the repository's own docs and the reference table, with sources shown",
     "Ollama qwen2.5:3b + nomic-embed-text; NumPy cosine similarity"],
    ["<b>Assistant — about your report</b>",
     "Ask about your own results in plain words; answers quote your numbers back",
     "Ollama qwen2.5:3b — no retrieval, the report is the whole context"],
    ["<b>Safety guards</b>",
     "Medical questions refused in code; greetings answered without a model",
     "Deterministic Python, before the LLM runs"],
    ["<b>CSV upload + preview</b>",
     "See exactly what was parsed before anything is classified",
     "FastAPI + python-multipart"],
    ["<b>Bundled datasets</b>",
     "Four files runnable in one click, including the real Kaggle set",
     "FastAPI"],
    ["<b>Test-name picker</b>",
     "Names come from the server; a name off the list cannot be submitted",
     "React combobox fed over MCP"],
    ["<b>Degraded mode</b>",
     "LLM unreachable? Every severity, range and rule still returned",
     "Agent failure policy"],
    ["<b>Feedback</b>",
     "Stored server-side rather than posted to a mail service with keys in the bundle",
     "FastAPI + JSONL"],
]

STACK = [
    ["FastAPI (Python 3.12)", "HTTP API, validation, generated OpenAPI docs"],
    ["MCP over stdio (SDK v2.1)", "All clinical logic behind 4 tools, reusable by any MCP client"],
    ["Google Gemini 3.5-flash-lite", "Explanations only. ~4.5× faster than larger flash models, no quality loss here"],
    ["Ollama qwen2.5:3b", "Assistant chat, local. Instruct not reasoning — qwen3:4b took ~60s on CPU"],
    ["Ollama nomic-embed-text", "Assistant embeddings, local, 768-dimension"],
    ["NumPy", "Vector index over 116 chunks. A vector DB would add a service and be slower"],
    ["ReportLab", "PDF generation. A print stylesheet cannot do measured tables or page breaks"],
    ["React 19 + Vite 8", "Four pages, two themes, shared analysis state in the shell"],
    ["pytest", "317 tests, no network and no API key required"],
]

PIPELINE = [
    ["<b>1. Classify</b>", "MCP tool", "Compare each value to its reference range. Decides the severity."],
    ["<b>2. Route</b>", "MCP tool", "Group and order by severity, critical first. Decides the order."],
    ["<b>3. Explain</b>", "Gemini", "One batched call for the whole panel. Decides only the wording."],
]

GUARANTEES = [
    ["MCP unavailable", "The request fails (503). Without classification there is nothing trustworthy to return."],
    ["LLM unavailable", "The request succeeds without explanations. Severity is computed locally and must not be lost to an outage."],
    ["Agent isolation", "The agent never imports the tool server — every call goes over MCP. A test asserts the boundary."],
    ["Assistant locality", "Chat and embeddings are local only. No cloud fallback, so lab values never leave the machine."],
]


def build() -> Path:
    doc = BaseDocTemplate(
        str(OUT), pagesize=A4,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        topMargin=HEADER_HEIGHT, bottomMargin=FOOTER_HEIGHT,
        title="Aragen AI - Clinical Lab Results Analyzer",
        author="Vaibhav Sharma",
        subject="Project overview: features and tools",
    )
    width = A4[0] - 2 * PAGE_MARGIN
    frame = Frame(PAGE_MARGIN, FOOTER_HEIGHT, width,
                  A4[1] - HEADER_HEIGHT - FOOTER_HEIGHT, id="body",
                  leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="main", frames=[frame], onPage=_page)])

    story = [
        P("Clinical Lab Results Analyzer", "title"),
        P("Submit lab values, get each one classified as <b>Critical / Warning / "
          "Normal</b> with an explanation of why it was flagged and a suggested "
          "next step — then take the panel away as a PDF, or ask an assistant "
          "about it in your own words. <b>Severity is decided by deterministic "
          "code, never by the language model.</b> The model translates a "
          "decision that has already been made.", "lede"),

        P("Pipeline", "h2"),
        table(["Step", "Runs on", "What it decides"], PIPELINE,
              [0.14 * width, 0.12 * width, 0.74 * width]),

        P("Features", "h2"),
        table(["Feature", "What it gives you", "Built with"], FEATURES,
              [0.20 * width, 0.49 * width, 0.31 * width]),
    ]

    story += [
        KeepTogether([
            P("Tools and libraries", "h2"),
            table(["Tool", "Role in this project"], STACK,
                  [0.28 * width, 0.72 * width]),
        ]),
        KeepTogether([
            P("Guarantees", "h2"),
            table(["Property", "Behaviour"], GUARANTEES,
                  [0.22 * width, 0.78 * width]),
        ]),
        Spacer(1, 5),
        P("Validated against the Kaggle dataset <i>Laboratory Test Results — "
          "Anonymized</i> (CC0-1.0): 27 rows, 0 unclassified, 0 disagreements "
          "with the laboratory's own verdict, which is never shown to the "
          "classifier. Turkish test names, per-row reference intervals and "
          "qualitative urinalysis values are all handled. "
          "<b>Not a medical device</b> — it compares numbers to published "
          "ranges and knows nothing about the person they came from.", "note"),
    ]

    doc.build(story)
    return OUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size / 1024:.1f} KB)")
