"""PDF report generation.

Builds a real PDF with ReportLab rather than styling a web page for print.
The difference matters: this gives genuine table primitives with measured
column widths and cell padding, page breaks that respect row boundaries,
a header and footer drawn on every page, and "Page 1 of 3" - none of which a
print stylesheet can do reliably across browsers.

Layout follows the Aragen brand: the Pulse Mark drawn as vector, an indigo
accent, and severity colours matching the interface so a printed report and
the screen agree.

Nothing here re-runs the analysis. The endpoint receives a response that has
already been produced and renders it, so producing a PDF costs no LLM call.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

# ---------------------------------------------------------------------------
# Palette - the interface's tokens, so screen and paper agree
# ---------------------------------------------------------------------------

INK = colors.HexColor("#101828")
BODY = colors.HexColor("#3F4759")
MUTED = colors.HexColor("#6B7387")
HAIRLINE = colors.HexColor("#DDE2EC")
PANEL = colors.HexColor("#F4F6FA")
ACCENT = colors.HexColor("#4839CF")
ACCENT_LIGHT = colors.HexColor("#8B7CF6")

SEVERITY_COLOURS = {
    "critical": (colors.HexColor("#C81E3A"), colors.HexColor("#FDF2F4")),
    "warning": (colors.HexColor("#B45309"), colors.HexColor("#FDF8EE")),
    "normal": (colors.HexColor("#047857"), colors.HexColor("#F0FAF5")),
    "unknown": (colors.HexColor("#6B7387"), colors.HexColor("#F4F6FA")),
}

SEVERITY_LABELS = {
    "critical": "CRITICAL",
    "warning": "WARNING",
    "normal": "NORMAL",
    "unknown": "NOT READ",
}

URGENCY_LABELS = {
    "emergency": "SEEK CARE TODAY",
    "urgent": "CONTACT A DOCTOR WITHIN DAYS",
    "soon": "RAISE AT NEXT APPOINTMENT",
    "routine": "NO ACTION NEEDED",
}

PAGE_MARGIN = 16 * mm

# The letterhead rule is drawn at PAGE_MARGIN + 12mm from the top. The content
# frame must start below it, not level with it: at 26mm the frame began 2mm
# ABOVE the rule and the title sat on top of it. 36mm leaves 8mm of air under
# the rule before the first line of text.
HEADER_RULE_DROP = 12 * mm
HEADER_HEIGHT = PAGE_MARGIN + HEADER_RULE_DROP + 8 * mm
FOOTER_HEIGHT = 16 * mm


# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------

def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["BodyText"]

    def style(name: str, **kwargs: Any) -> ParagraphStyle:
        return ParagraphStyle(name, parent=base, alignment=TA_LEFT, **kwargs)

    return {
        "title": style("title", fontName="Helvetica-Bold", fontSize=15,
                       leading=19, textColor=INK, spaceAfter=4),
        "subtitle": style("subtitle", fontName="Helvetica", fontSize=9,
                          leading=13, textColor=MUTED),
        "verdict": style("verdict", fontName="Helvetica-Bold", fontSize=11,
                         leading=14, textColor=INK),
        "verdict_detail": style("verdict_detail", fontName="Helvetica",
                                fontSize=8.5, leading=12, textColor=BODY),
        "section": style("section", fontName="Helvetica-Bold", fontSize=8,
                         leading=11, textColor=MUTED),
        "test": style("test", fontName="Helvetica-Bold", fontSize=11,
                      leading=14, textColor=INK),
        "value": style("value", fontName="Helvetica-Bold", fontSize=13,
                       leading=16, textColor=INK),
        "meta": style("meta", fontName="Helvetica", fontSize=8,
                      leading=11, textColor=MUTED),
        "headline": style("headline", fontName="Helvetica-Bold", fontSize=9.5,
                          leading=13, textColor=INK),
        "label": style("label", fontName="Helvetica-Bold", fontSize=7,
                       leading=10.5, textColor=MUTED, spaceBefore=1.5),
        "body": style("body", fontName="Helvetica", fontSize=8.2,
                      leading=11.4, textColor=BODY),
        "note": style("note", fontName="Helvetica", fontSize=7.5,
                      leading=10.5, textColor=MUTED),
        "statvalue": style("statvalue", fontName="Helvetica-Bold", fontSize=14,
                           leading=17, textColor=INK),
        "statlabel": style("statlabel", fontName="Helvetica", fontSize=6.5,
                           leading=9, textColor=MUTED),
    }


# ReportLab's base-14 fonts are WinAnsi-encoded. Typographic punctuation is
# nominally in that set but round-trips unreliably through extraction and some
# viewers, so it is folded to ASCII on the way in. The text still reads
# correctly; it just cannot render as a replacement glyph.
_PUNCTUATION = str.maketrans({
    "—": "-", "–": "-", "−": "-",
    "‘": "'", "’": "'",
    "“": '"', "”": '"',
    "…": "...", " ": " ", "·": "-",
})


def _clean(text: Any) -> str:
    """Fold typographic punctuation and escape for ReportLab's mini-XML."""
    return escape(str(text).translate(_PUNCTUATION))


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    """Paragraph with the text cleaned and escaped - values are user data."""
    return Paragraph(_clean(text), style)


# ---------------------------------------------------------------------------
# The severity chip, drawn rather than faked with a table
# ---------------------------------------------------------------------------

class SeverityChip(Flowable):
    """A rounded, filled label. ReportLab has no such primitive."""

    def __init__(self, text: str, fill: colors.Color, stroke: colors.Color,
                 text_colour: colors.Color, font_size: float = 7) -> None:
        super().__init__()
        self.text = text
        self.fill = fill
        self.stroke = stroke
        self.text_colour = text_colour
        self.font_size = font_size
        self.height = font_size + 6
        self.width = self.canv_width()

    def canv_width(self) -> float:
        return stringWidth(self.text, "Helvetica-Bold", self.font_size) + 12

    def draw(self) -> None:
        c = self.canv
        c.setFillColor(self.fill)
        c.setStrokeColor(self.stroke)
        c.setLineWidth(0.6)
        c.roundRect(0, 0, self.width, self.height, self.height / 2,
                    stroke=1, fill=1)
        c.setFillColor(self.text_colour)
        c.setFont("Helvetica-Bold", self.font_size)
        c.drawString(6, (self.height - self.font_size) / 2 + 1, self.text)


# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------

def _draw_mark(c: Canvas, x: float, y: float, size: float) -> None:
    """The Pulse Mark: rounded badge, serif A, signal dot."""
    c.saveState()
    c.setFillColor(ACCENT)
    c.roundRect(x, y, size, size, size * 0.28, stroke=0, fill=1)

    c.setFillColor(colors.white)
    c.setFont("Times-Bold", size * 0.6)
    c.drawCentredString(x + size / 2, y + size * 0.29, "A")

    c.setFillColor(colors.HexColor("#34D399"))
    dot = size * 0.13
    c.circle(x + size - dot * 1.6, y + dot * 1.6, dot / 2, stroke=0, fill=1)
    c.restoreState()


class ReportCanvas(Canvas):
    """Draws the letterhead and footer, and resolves "Page X of Y".

    Total page count is unknown until the document is built, so pages are
    buffered and the furniture is drawn in a second pass.
    """

    def __init__(self, *args: Any, patient_id: str | None = None,
                 printed_at: str = "", **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._saved = []
        self._patient_id = patient_id
        self._printed_at = printed_at

    def showPage(self) -> None:  # noqa: N802 - ReportLab's casing
        self._saved.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        total = len(self._saved)
        for state in self._saved:
            self.__dict__.update(state)
            self._draw_header()
            self._draw_footer(total)
            super().showPage()
        super().save()

    def _draw_header(self) -> None:
        width, height = A4
        top = height - PAGE_MARGIN

        _draw_mark(self, PAGE_MARGIN, top - 9 * mm, 9 * mm)

        # The suffix is placed from the measured width of the wordmark. A
        # hardcoded offset drew it on top of the word.
        word_x = PAGE_MARGIN + 12 * mm
        word_y = top - 6.5 * mm
        self.setFillColor(INK)
        self.setFont("Times-Bold", 14)
        self.drawString(word_x, word_y, "Aragen")

        self.setFillColor(MUTED)
        self.setFont("Helvetica-Bold", 6.5)
        self.drawString(
            word_x + stringWidth("Aragen", "Times-Bold", 14) + 2,
            word_y + 4.2,
            "AI",
        )

        self.setFillColor(MUTED)
        self.setFont("Helvetica", 8)
        self.drawRightString(width - PAGE_MARGIN, top - 4 * mm, self._printed_at)
        if self._patient_id:
            self.drawRightString(width - PAGE_MARGIN, top - 8 * mm,
                                 f"Patient: {self._patient_id}")

        self.setStrokeColor(INK)
        self.setLineWidth(1)
        self.line(PAGE_MARGIN, top - HEADER_RULE_DROP,
                  width - PAGE_MARGIN, top - HEADER_RULE_DROP)

    def _draw_footer(self, total: int) -> None:
        width = A4[0]
        baseline = PAGE_MARGIN

        self.setStrokeColor(HAIRLINE)
        self.setLineWidth(0.6)
        self.line(PAGE_MARGIN, baseline + 8 * mm,
                  width - PAGE_MARGIN, baseline + 8 * mm)

        self.setFillColor(MUTED)
        self.setFont("Helvetica", 7)
        self.drawString(
            PAGE_MARGIN, baseline + 4.5 * mm,
            "Values were checked against reference ranges by a fixed rule, not by the AI.",
        )
        self.drawString(
            PAGE_MARGIN, baseline + 1.8 * mm,
            "For information only - not a medical diagnosis.",
        )
        self.setFont("Helvetica-Bold", 7)
        self.drawRightString(width - PAGE_MARGIN, baseline + 4.5 * mm,
                             f"Page {self._pageNumber} of {total}")


# ---------------------------------------------------------------------------
# Content blocks
# ---------------------------------------------------------------------------

def _summary_table(summary: dict[str, Any], styles) -> Table:
    """The counts, across the top of the report."""
    # Short enough to sit on one line at five columns. Longer wording wrapped
    # mid-phrase and left the row ragged.
    cells = [
        ("RESULTS CHECKED", summary.get("total", 0)),
        ("URGENT ATTENTION", summary.get("critical", 0)),
        ("OUT OF RANGE", summary.get("warning", 0)),
        ("IN RANGE", summary.get("normal", 0)),
    ]
    if summary.get("errors"):
        cells.append(("NOT READ", summary["errors"]))

    table = Table(
        [
            [_p(label, styles["statlabel"]) for label, _ in cells],
            [_p(value, styles["statvalue"]) for _, value in cells],
        ],
        colWidths=[(A4[0] - 2 * PAGE_MARGIN) / len(cells)] * len(cells),
    )
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PANEL),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, 0), 9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 9),
    ]))
    return table


def _verdict(summary: dict[str, Any], results: list[dict[str, Any]], styles) -> Table:
    """The bottom line, stated before the detail."""
    critical = summary.get("critical", 0)
    warning = summary.get("warning", 0)
    normal = summary.get("normal", 0)

    if critical:
        severity = "critical"
        line = ("One result needs urgent attention." if critical == 1
                else f"{critical} results need urgent attention.")
        detail = (f"Start with {results[0]['test_name']} - it is furthest "
                  "outside its normal range.") if results else ""
    elif warning:
        severity = "warning"
        line = ("One result is outside the normal range." if warning == 1
                else f"{warning} results are outside the normal range.")
        detail = "Nothing here is an emergency, but these are worth following up."
    elif normal:
        severity = "normal"
        line = ("This result is within the normal range." if normal == 1
                else f"All {normal} results are within their normal ranges.")
        detail = "No action needed beyond your usual check-ups."
    else:
        severity = "unknown"
        line = "None of these results could be interpreted."
        detail = "Check the test names, values and units, then try again."

    accent, background = SEVERITY_COLOURS[severity]

    rows = [[_p(line, styles["verdict"])]]
    if detail:
        rows.append([_p(detail, styles["verdict_detail"])])

    table = Table(rows, colWidths=[A4[0] - 2 * PAGE_MARGIN])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), background),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (0, 0), 9),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, -1), (-1, -1), 0),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 9),
    ]))
    return table


def _bullets(items: list[str], styles, ordered: bool = False) -> list[Paragraph]:
    """Bullet or numbered lines, as paragraphs rather than a nested table.

    Markers are neutral rather than accent-coloured. On screen the accent
    means "interactive"; on paper nothing is, so a coloured marker only
    competes with the severity colour, which is the one that carries meaning.
    """
    out = []
    for index, item in enumerate(items, start=1):
        marker = f"{index}." if ordered else "-"
        out.append(Paragraph(
            f'<font color="#8892A6"><b>{marker}</b></font>&nbsp;&nbsp;{_clean(item)}',
            styles["body"],
        ))
    return out


def _result_block(result: dict[str, Any], styles) -> Table:
    """One result, as a single table that can break across pages.

    Structure matters here. An earlier version nested the header and the
    explanation inside a one-cell wrapper table so the border and severity
    rail had something to draw on - but a table cell is atomic, so the whole
    result could never split. A block taller than the space left on the page
    jumped to the next one and left the first page blank.

    So it is one flat table instead: the header and headline span both
    columns, each explanation field is a label/value row, and ReportLab splits
    it at row boundaries when it has to. The border and rail are applied to
    the table itself and redraw on each fragment.
    """
    severity = result.get("severity", "unknown")
    accent, background = SEVERITY_COLOURS[severity]

    unit = result.get("unit") or ""
    reference = result.get("reference_range")
    reference_text = (
        f"Normal range {reference['low']}-{reference['high']} {reference['unit']}"
        if reference else (result.get("error") or "No reference range")
    )

    label_width = 34 * mm
    body_width = A4[0] - 2 * PAGE_MARGIN - label_width - 28

    # --- header: name and chip, then value and the range it was judged against
    chip = SeverityChip(SEVERITY_LABELS.get(severity, "?"), background, accent, accent)

    title_row = Table(
        [[_p(result.get("test_name", ""), styles["test"]), chip]],
        colWidths=[(label_width + body_width) * 0.72,
                   (label_width + body_width) * 0.28],
    )
    title_row.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))

    # The value and its reference belong together: split across the full width
    # they read as two unrelated facts.
    measurement = Table(
        [[_p(f"{result.get('value')} {unit}".strip(), styles["value"]),
          _p(reference_text, styles["meta"])]],
        colWidths=[36 * mm, None],
    )
    measurement.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    detail = result.get("explanation_detail") or {}

    rows: list[list[Any]] = [[title_row, ""], [measurement, ""]]
    spans = [("SPAN", (0, 0), (1, 0)), ("SPAN", (0, 1), (1, 1))]

    if detail.get("headline"):
        rows.append([_p(detail["headline"], styles["headline"]), ""])
        spans.append(("SPAN", (0, len(rows) - 1), (1, len(rows) - 1)))

    first_field = len(rows)

    def field(label: str, value: Any) -> None:
        rows.append([_p(label, styles["label"]), value])

    if detail.get("what_it_measures"):
        field("WHAT THIS TEST MEASURES", _p(detail["what_it_measures"], styles["body"]))
    if detail.get("what_result_means"):
        field("WHAT YOUR RESULT MEANS", _p(detail["what_result_means"], styles["body"]))
    if detail.get("possible_causes"):
        field("COMMON CAUSES", _bullets(detail["possible_causes"], styles))
    if detail.get("urgency"):
        urgency_text = URGENCY_LABELS.get(detail["urgency"], detail["urgency"].upper())
        reason = detail.get("urgency_reason") or ""
        field("HOW SOON TO ACT",
              _p(f"{urgency_text} - {reason}" if reason else urgency_text,
                 styles["body"]))
    if detail.get("next_steps"):
        field("WHAT TO DO", _bullets(detail["next_steps"], styles, ordered=True))
    if detail.get("questions_to_ask"):
        field("QUESTIONS FOR YOUR DOCTOR", _bullets(detail["questions_to_ask"], styles))
    if not detail and result.get("error"):
        field("WHY", _p(result["error"], styles["body"]))

    block = Table(rows, colWidths=[label_width, body_width], repeatRows=0)
    block.setStyle(TableStyle([
        *spans,
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.6, HAIRLINE),
        ("LINEBEFORE", (0, 0), (0, -1), 2.5, accent),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        # The header rows read as one unit, so no rules between them.
        ("BOTTOMPADDING", (0, 0), (-1, 0), 0),
        ("TOPPADDING", (0, 1), (-1, 1), 0),
        ("TOPPADDING", (0, 0), (-1, 0), 10),
        ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        # A hairline between each explanation field.
        ("LINEABOVE", (0, first_field), (-1, -1), 0.4, HAIRLINE),
        ("RIGHTPADDING", (0, first_field), (0, -1), 10),
    ]))
    return block


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def build_report(response: dict[str, Any]) -> bytes:
    """Render an analysis response as a PDF.

    Args:
        response: An AnalyzeResponse, already produced. No analysis is rerun.

    Returns:
        The PDF file's bytes.
    """
    styles = _styles()
    summary = response.get("summary", {})
    results = response.get("results", [])
    errors = response.get("errors", [])
    patient_id = response.get("patient_id")
    printed_at = datetime.now().strftime("%d %B %Y at %H:%M")

    buffer = BytesIO()
    frame = Frame(
        PAGE_MARGIN,
        PAGE_MARGIN + FOOTER_HEIGHT,
        A4[0] - 2 * PAGE_MARGIN,
        A4[1] - PAGE_MARGIN - HEADER_HEIGHT - FOOTER_HEIGHT,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        id="body",
    )
    doc = BaseDocTemplate(
        buffer,
        pagesize=A4,
        title=f"Laboratory Results Report{f' - {patient_id}' if patient_id else ''}",
        author="Aragen AI",
        subject="Clinical laboratory results",
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN, bottomMargin=PAGE_MARGIN,
    )
    doc.addPageTemplates([PageTemplate(id="report", frames=[frame])])

    story: list[Any] = [
        _p("Laboratory Results Report", styles["title"]),
        _p("Values compared against reference ranges by a fixed rule; "
           "explanations written afterwards by an AI assistant.",
           styles["subtitle"]),
        Spacer(1, 12),
        _summary_table(summary, styles),
        Spacer(1, 12),
        _verdict(summary, results, styles),
        Spacer(1, 14),
    ]

    # Results arrive already ordered by severity; group headings follow that.
    current_severity = None
    for result in results:
        severity = result.get("severity", "unknown")
        if severity != current_severity:
            current_severity = severity
            count = sum(1 for r in results if r.get("severity") == severity)
            story.append(Spacer(1, 6))
            story.append(_p(
                f"{SEVERITY_LABELS.get(severity, severity.upper())}  ({count})",
                styles["section"],
            ))
            story.append(Spacer(1, 5))
        story.append(_result_block(result, styles))
        story.append(Spacer(1, 8))

    if errors:
        story.append(Spacer(1, 8))
        story.append(_p(f"ENTRIES WE COULD NOT READ  ({len(errors)})", styles["section"]))
        story.append(Spacer(1, 4))
        rows = [[
            _p(f"Row {item.get('row')}" if item.get("row") else "—", styles["label"]),
            _p(item.get("test_name") or "—", styles["body"]),
            _p(item.get("error", ""), styles["body"]),
        ] for item in errors]

        table = Table(rows, colWidths=[18 * mm, 34 * mm,
                                       A4[0] - 2 * PAGE_MARGIN - 52 * mm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (-1, -1), PANEL),
            ("LINEBELOW", (0, 0), (-1, -2), 0.4, HAIRLINE),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(table)

    doc.build(
        story,
        canvasmaker=lambda *args, **kwargs: ReportCanvas(
            *args, patient_id=patient_id, printed_at=printed_at, **kwargs
        ),
    )
    return buffer.getvalue()
