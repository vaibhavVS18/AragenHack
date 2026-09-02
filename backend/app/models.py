"""Pydantic schemas - the contract between React, FastAPI and the agent.

Every shape that crosses an HTTP boundary is declared here, so the API's
surface is described in one file and FastAPI can generate accurate docs from
it automatically.

Note that these describe the *transport* shape. The MCP tools exchange plain
dicts, and the agent converts tool output into these models on the way out.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

Severity = Literal["critical", "warning", "normal", "unknown"]
MatchedBy = Literal["exact", "alias", "fuzzy"]
Urgency = Literal["emergency", "urgent", "soon", "routine"]


# ---------------------------------------------------------------------------
# Input
# ---------------------------------------------------------------------------

class LabInput(BaseModel):
    """One lab result as submitted by the user."""

    test_name: str = Field(
        ...,
        min_length=1,
        max_length=120,
        description="Lab test name. Aliases and minor typos are tolerated.",
        examples=["Hemoglobin", "HGB", "Potassium"],
    )
    value: float | str = Field(
        ...,
        description="Measured value. Numeric strings and censored results "
                    "such as '<0.1' are accepted.",
        examples=[7.2, "92", "<0.1"],
    )
    unit: str | None = Field(
        default=None,
        max_length=40,
        description="Unit as reported. If omitted, the canonical unit for the "
                    "test is assumed and the assumption is flagged.",
        examples=["g/dL", "mEq/L"],
    )

    # A reference interval that arrived with the result. The Kaggle dataset
    # supplies Min_Reference/Max_Reference per row, and a laboratory's own
    # interval is authoritative for its own result, so these take precedence
    # over the built-in table.
    reference_low: float | None = Field(
        default=None,
        description="Lower bound of the reference interval supplied with the result.",
        examples=[150],
    )
    reference_high: float | None = Field(
        default=None,
        description="Upper bound of the reference interval supplied with the result.",
        examples=[450],
    )
    reference_text: str | None = Field(
        default=None,
        max_length=80,
        description="Expected qualitative result, for word-valued tests such "
                    "as urinalysis strips.",
        examples=["Negatif", "Normal"],
    )

    @field_validator("test_name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("test_name cannot be blank")
        return value.strip()


class AnalyzeRequest(BaseModel):
    """Request body for POST /analyze_labs."""

    patient_id: str | None = Field(
        default=None,
        max_length=64,
        description="Optional free-form label, echoed back in the response.",
        examples=["ANON-0142"],
    )
    labs: list[LabInput] = Field(
        ...,
        min_length=1,
        description="Lab results to analyze.",
    )


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

class ReferenceRange(BaseModel):
    """The thresholds a value was compared against."""

    low: float
    high: float
    critical_low: float | None = None
    critical_high: float | None = None
    unit: str


class Explanation(BaseModel):
    """One result explained for the person whose result it is.

    Structured rather than a paragraph: named fields make the model answer the
    questions a reader actually has, and let the UI lay the answer out as a
    table instead of a wall of clinical prose.

    Every field here comes from the language model. Nothing in it influences
    the severity, which was already decided before the model was called.
    """

    headline: str = Field(
        description="One plain-English sentence: what this result shows.",
    )
    what_it_measures: str = Field(
        description="What the test measures and why, independent of this value.",
    )
    what_result_means: str = Field(
        description="Interpretation of this specific value against its range.",
    )
    urgency: Urgency = Field(
        description="How quickly to act: emergency, urgent, soon or routine.",
    )
    urgency_reason: str = Field(
        default="",
        description="Why that urgency - the practical risk of waiting.",
    )
    possible_causes: list[str] = Field(
        default_factory=list,
        description="Common reasons for a result like this, most likely first.",
    )
    next_steps: list[str] = Field(
        default_factory=list,
        description="Concrete actions in order, each starting with a verb.",
    )
    questions_to_ask: list[str] = Field(
        default_factory=list,
        description="Specific questions for the reader's doctor.",
    )


class LabResult(BaseModel):
    """A single classified and explained lab result.

    Fields fall into three groups:

    * measurement    - what was submitted
    * classification - computed deterministically, never by the LLM
    * explanation    - generated by the LLM from the classification above
    """

    # --- measurement ---
    test_name: str
    value: float | str
    unit: str | None = None

    # --- classification (deterministic) ---
    severity: Severity
    band: str | None = None
    reference_range: ReferenceRange | None = None
    range_source: Literal["supplied", "internal", "none"] | None = Field(
        default=None,
        description="Where the reference interval came from: 'supplied' means "
                    "it arrived with the result (e.g. a dataset column), "
                    "'internal' means the built-in clinical table.",
    )
    critical_basis: Literal["table", "derived", "none"] | None = Field(
        default=None,
        description="How the critical thresholds were set. 'table' is a "
                    "published panic value; 'derived' is estimated from the "
                    "supplied interval's width and is indicative only.",
    )
    comparison: Literal["numeric", "qualitative"] | None = Field(
        default=None,
        description="Whether the value was compared as a number or as a word "
                    "(urinalysis strips report 'Negatif', '1+').",
    )
    direction: Literal["below", "above", "within", "differs"] | None = None
    deviation_pct: float | None = None
    deviation_text: str | None = None
    rule_fired: str | None = Field(
        default=None,
        description="The literal comparison that produced the severity, so a "
                    "user can verify the verdict rather than trust it.",
    )
    matched_by: MatchedBy | None = None
    unit_assumed: bool = False

    # --- clinical context (from the reference table) ---
    category: str | None = None
    specialty: str | None = None
    measures: str | None = None

    # --- explanation (from the LLM) ---
    # The assignment specifies an explanation and a suggested next step, so
    # both are present as plain strings at the top level. `explanation_detail`
    # carries the same content broken into fields for the UI; the two strings
    # are derived from it, so they can never disagree with it.
    explanation: str | None = Field(
        default=None,
        description="Clinical explanation of this result, generated by the "
                    "LLM. Null when the LLM was unavailable - classification "
                    "above is unaffected either way.",
    )
    next_step: str | None = Field(
        default=None,
        description="The single most important suggested next step, "
                    "generated by the LLM.",
    )
    explanation_detail: Explanation | None = Field(
        default=None,
        description="The same explanation broken into fields - what the test "
                    "measures, what this value means, common causes, urgency, "
                    "the full ordered list of next steps, and questions to "
                    "ask a doctor. Drives the tabular display.",
    )

    # --- diagnostics ---
    notes: str | None = None
    error: str | None = None


class RowError(BaseModel):
    """A row that could not be read at all, kept separate from results."""

    row: int | None = Field(default=None, description="1-based source row, for CSV input.")
    test_name: str | None = None
    raw: dict[str, Any] | None = None
    error: str


class Summary(BaseModel):
    """Counts by severity, for the header of the results view."""

    total: int = 0
    critical: int = 0
    warning: int = 0
    normal: int = 0
    unknown: int = 0
    abnormal: int = 0
    errors: int = 0


class ResponseMeta(BaseModel):
    """How the response was produced - useful for debugging and demos."""

    llm_provider: str
    llm_model: str | None = None
    llm_available: bool = True
    llm_error: str | None = Field(
        default=None,
        description="Set when explanations were unavailable. Classification "
                    "is unaffected: it never depends on the LLM.",
    )
    elapsed_ms: int = 0
    mcp_tools_used: list[str] = Field(default_factory=list)


class AnalyzeResponse(BaseModel):
    """Response body for POST /analyze_labs.

    ``results`` is pre-sorted by the Route step (critical first). The frontend
    renders in the order given and does not re-sort.
    """

    patient_id: str | None = None
    summary: Summary
    results: list[LabResult]
    errors: list[RowError] = Field(default_factory=list)
    meta: ResponseMeta


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: Literal["ok", "degraded"]
    mcp_server: Literal["connected", "unavailable"]
    tools_available: list[str] = Field(default_factory=list)
    llm_provider: str
    llm_model: str | None = None
    detail: str | None = None


# ---------------------------------------------------------------------------
# Assistant
# ---------------------------------------------------------------------------

class AssistantTurn(BaseModel):
    """One earlier message in the conversation."""

    role: Literal["user", "assistant"]
    text: str = Field(max_length=2000)


class AssistantQuestion(BaseModel):
    """Request body for POST /assistant/ask."""

    question: str = Field(
        ...,
        min_length=2,
        max_length=500,
        description="A question about how this application works.",
        examples=["How is a result classified as critical?"],
    )

    history: list[AssistantTurn] = Field(
        default_factory=list,
        max_length=6,
        description="The last few messages of this conversation, oldest "
                    "first, so a follow-up can refer to what was already "
                    "said. Sent by the client each time - the server keeps no "
                    "session, so two readers can never share one.",
    )

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question cannot be blank")
        return value.strip()


class ReportQuestion(BaseModel):
    """Request body for POST /assistant/report.

    Separate from :class:`AssistantQuestion` because the two answer from
    different grounds and share no machinery: this one retrieves nothing, and
    the report is required rather than optional.
    """

    question: str = Field(..., min_length=2, max_length=500)

    report: str = Field(
        ...,
        min_length=1,
        max_length=6000,
        description="A digest of the results on screen. Built by the client "
                    "from the response it already holds - never re-analysed, "
                    "and never stored.",
    )

    history: list[AssistantTurn] = Field(
        default_factory=list,
        max_length=6,
        description="Earlier turns about THIS report, oldest first. The client "
                    "drops them when a new analysis replaces the report, so "
                    "two panels can never be mixed in one answer.",
    )

    @field_validator("question")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("question cannot be blank")
        return value.strip()


class AssistantSource(BaseModel):
    """A passage that informed an answer.

    Returned so the reader can see what the answer was built from. An
    assistant that cites nothing is indistinguishable from one that guessed.
    """

    title: str
    source: str
    score: float = Field(description="Cosine similarity to the question.")


class AssistantAnswer(BaseModel):
    """Response body for POST /assistant/ask."""

    answer: str
    tone: str = Field(
        description="How the question was read: neutral, worried, urgent, "
                    "confused, skeptical or frustrated. Adjusts wording only.",
    )
    engine: str = Field(
        description="Which backend answered, e.g. 'ollama:qwen2.5:3b'.",
    )
    grounded: bool = Field(
        description="False when nothing in the index matched, in which case "
                    "the assistant declines rather than improvising.",
    )
    sources: list[AssistantSource] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Feedback
# ---------------------------------------------------------------------------

class FeedbackSubmission(BaseModel):
    """Request body for POST /feedback.

    Only the message is required. Asking for a name and an email before
    someone can say "the CSV upload confused me" loses most of the feedback
    that would have been worth having.
    """

    message: str = Field(
        ...,
        min_length=3,
        max_length=2000,
        description="What the person wants to say.",
    )
    rating: int | None = Field(
        default=None,
        ge=1,
        le=5,
        description="Optional 1-5 rating.",
    )
    name: str | None = Field(default=None, max_length=80)
    email: str | None = Field(
        default=None,
        max_length=160,
        description="Optional, only so a reply is possible.",
    )
    page: str | None = Field(
        default=None,
        max_length=80,
        description="Which page it was sent from, for context.",
    )

    @field_validator("message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message cannot be blank")
        return value.strip()

    @field_validator("name", "email", "page")
    @classmethod
    def _empty_to_none(cls, value: str | None) -> str | None:
        return (value or "").strip() or None


class FeedbackReceipt(BaseModel):
    """Response body for POST /feedback."""

    received: bool = True
    received_at: str
    count: int = Field(description="Total submissions recorded so far.")


class FeedbackSummary(BaseModel):
    """Response body for GET /feedback/summary."""

    count: int
    average_rating: float | None = None
