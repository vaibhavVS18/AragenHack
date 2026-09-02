"""FastAPI entrypoint - deliberately thin.

This layer knows HTTP, not medicine. It validates input, hands work to the
agent, and maps failures onto status codes. Every clinical decision happens
behind the MCP server; swapping FastAPI for anything else would not touch a
line of that logic.

Run locally::

    uvicorn app.main:app --reload --port 8000

Interactive docs at http://127.0.0.1:8000/docs
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from .agent import LabAgent
from .assistant import AssistantService, AssistantUnavailable
from .config import Settings, get_settings
from .csv_loader import CSVFormatError, parse_csv
from .datasets import DatasetNotFound, list_datasets, load_dataset
from .feedback import feedback_summary, record_feedback
from .mcp_client import MCPUnavailableError
from .models import (
    AnalyzeRequest,
    AnalyzeResponse,
    AssistantAnswer,
    FeedbackReceipt,
    FeedbackSubmission,
    FeedbackSummary,
    AssistantQuestion,
    AssistantSource,
    HealthResponse,
    ReportQuestion,
)
from .report import build_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Build the agent once at startup and report the environment.

    The MCP server is not started here - the agent spawns it per request. What
    this does is surface a misconfiguration in the logs at boot rather than on
    the first request during a demo.
    """
    settings = get_settings()
    app.state.settings = settings
    app.state.agent = LabAgent(settings)
    app.state.assistant = AssistantService(settings)

    logger.info("LLM provider: %s (%s)",
                app.state.agent.llm.name, app.state.agent.llm.model or "n/a")
    if settings.llm_provider == "gemini" and not settings.gemini_api_key.strip():
        logger.warning(
            "LLM_PROVIDER=gemini but GEMINI_API_KEY is empty - "
            "falling back to the offline mock provider."
        )

    reachable, tools, error = await app.state.agent.health()
    if reachable:
        logger.info("MCP server reachable, tools: %s", ", ".join(tools))
    else:
        logger.error("MCP server unreachable at startup: %s", error)

    yield


app = FastAPI(
    title="Clinical Lab Results Analyzer",
    version="1.0.0",
    description=(
        "Classifies laboratory results as Critical, Warning or Normal and "
        "explains why.\n\n"
        "Classification is deterministic: values are compared against "
        "reference ranges by an MCP tool server, never by a language model. "
        "The LLM generates the clinical explanation and suggested next step "
        "*after* severity has already been decided."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Dependencies
# ---------------------------------------------------------------------------

def get_agent(request: Request) -> LabAgent:
    """The shared agent instance built at startup."""
    return request.app.state.agent


def get_assistant(request: Request) -> AssistantService:
    """The shared assistant instance built at startup."""
    return request.app.state.assistant


def enforce_batch_limit(count: int, settings: Settings) -> None:
    """Reject oversized batches before any work begins.

    Raises:
        HTTPException: 413 if the batch exceeds the configured limit.
    """
    if count > settings.max_labs_per_request:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Maximum {settings.max_labs_per_request} lab results per "
                f"request; received {count}."
            ),
        )


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@app.exception_handler(MCPUnavailableError)
async def _mcp_unavailable(request: Request, exc: MCPUnavailableError):
    """The tool server is the source of clinical truth; without it, refuse.

    Returning uninterpreted values would look like a result while carrying no
    classification, which is worse than an explicit failure.
    """
    logger.error("MCP server unavailable: %s", exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Clinical tool server unavailable.",
            "hint": (
                "Run 'python -m mcp_server.server' from the backend directory "
                "to see why it failed to start."
            ),
            "error": str(exc),
        },
    )


@app.exception_handler(CSVFormatError)
async def _csv_format_error(request: Request, exc: CSVFormatError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


@app.exception_handler(AssistantUnavailable)
async def _assistant_unavailable(request: Request, exc: AssistantUnavailable):
    """The assistant is an extra; its absence must never look like an outage."""
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(DatasetNotFound)
async def _dataset_not_found(request: Request, exc: DatasetNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc.args[0])})


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    return {
        "service": "Clinical Lab Results Analyzer",
        "docs": "/docs",
        "health": "/health",
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and dependency check",
)
async def health(agent: LabAgent = Depends(get_agent)) -> HealthResponse:
    """Report whether the MCP tool server and LLM provider are ready.

    Returns 200 even when degraded, so a monitor can distinguish "the API is
    down" from "the API is up but a dependency is not".
    """
    reachable, tools, error = await agent.health()
    return HealthResponse(
        status="ok" if reachable else "degraded",
        mcp_server="connected" if reachable else "unavailable",
        tools_available=tools,
        llm_provider=agent.llm.name,
        llm_model=agent.llm.model,
        detail=error,
    )


@app.get(
    "/reference_ranges",
    summary="List every test that can be classified",
    responses={503: {"description": "Clinical tool server unavailable"}},
)
async def reference_ranges(agent: LabAgent = Depends(get_agent)) -> dict:
    """Return the clinical reference table.

    Lets the frontend offer autocomplete and show users what is supported
    without hardcoding a catalogue that could drift from the one actually used
    to classify.
    """
    return await agent.reference_ranges()


@app.post(
    "/analyze_labs",
    response_model=AnalyzeResponse,
    summary="Classify and explain lab results",
    responses={
        413: {"description": "Too many lab results in one request"},
        503: {"description": "Clinical tool server unavailable"},
    },
)
async def analyze_labs(
    payload: AnalyzeRequest,
    agent: LabAgent = Depends(get_agent),
    settings: Settings = Depends(get_settings),
) -> AnalyzeResponse:
    """Run the Classify -> Route -> Explain pipeline over a batch of results.

    Results come back ordered by severity, critical first, each carrying the
    reference range it was compared against, how far outside it fell, the rule
    that fired, and a generated clinical explanation.
    """
    enforce_batch_limit(len(payload.labs), settings)
    return await agent.analyze(payload.labs, patient_id=payload.patient_id)


@app.get(
    "/assistant/status",
    summary="Whether the assistant can answer, and on what",
)
async def assistant_status(
    assistant: AssistantService = Depends(get_assistant),
    settings: Settings = Depends(get_settings),
) -> dict:
    """Report which backends are ready.

    The widget calls this before showing itself, so a missing model reads as a
    disabled button with a reason rather than a question that fails.
    """
    if not settings.assistant_enabled:
        return {"available": False, "detail": "Assistant disabled by configuration."}
    return await assistant.status()


@app.post(
    "/assistant/ask",
    summary="Ask a question about how this application works",
    responses={503: {"description": "No assistant backend available"}},
)
async def assistant_ask(
    payload: AssistantQuestion,
    assistant: AssistantService = Depends(get_assistant),
    agent: LabAgent = Depends(get_agent),
    settings: Settings = Depends(get_settings),
) -> AssistantAnswer:
    """Answer from the indexed documentation and reference table.

    The reference catalogue is fetched over MCP and passed in, so the
    assistant's knowledge of thresholds comes from the same source used to
    classify rather than from a copy that could drift.
    """
    if not settings.assistant_enabled:
        raise HTTPException(status_code=503, detail="Assistant is disabled.")

    # Only fetched when there is an index to build. It is used for nothing
    # else, so once the index exists this round trip is pure latency - about
    # 1.5s on every question, spent spawning an MCP server to produce a table
    # that would be discarded on arrival.
    catalogue = None
    if not assistant.is_indexed:
        try:
            catalogue = await agent.reference_ranges()
        except MCPUnavailableError:
            # The documentation alone still answers most questions.
            logger.warning("Assistant indexing without the reference table.")

    answer = await assistant.ask(
        payload.question,
        catalogue,
        [(turn.role, turn.text) for turn in payload.history],
    )
    return AssistantAnswer(
        answer=answer.answer,
        tone=answer.tone,
        engine=answer.engine,
        grounded=answer.grounded,
        sources=[
            AssistantSource(title=s.title, source=s.source, score=s.score)
            for s in answer.sources
        ],
    )


@app.post(
    "/assistant/report",
    summary="Ask a question about one set of results",
    responses={503: {"description": "No assistant backend available"}},
)
async def assistant_report(
    payload: ReportQuestion,
    assistant: AssistantService = Depends(get_assistant),
    settings: Settings = Depends(get_settings),
) -> AssistantAnswer:
    """Answer from the reader's own results, and from nothing else.

    A separate endpoint rather than a flag on ``/assistant/ask``. It needs no
    catalogue, builds no index and makes no embedding call - the reader's
    results are the whole ground. Sharing the retrieval path meant the
    documentation competed with those results and won.
    """
    if not settings.assistant_enabled:
        raise HTTPException(status_code=503, detail="Assistant is disabled.")

    answer = await assistant.ask_about_report(
        payload.question,
        payload.report,
        [(turn.role, turn.text) for turn in payload.history],
    )
    return AssistantAnswer(
        answer=answer.answer,
        tone=answer.tone,
        engine=answer.engine,
        grounded=answer.grounded,
        sources=[],
    )


@app.post(
    "/feedback",
    response_model=FeedbackReceipt,
    summary="Record feedback about the application",
    responses={503: {"description": "Feedback could not be stored"}},
)
async def submit_feedback(payload: FeedbackSubmission) -> FeedbackReceipt:
    """Append one piece of feedback.

    Stored server-side rather than sent through a mail service: doing the
    latter means shipping a provider's keys in the front-end bundle, where
    anyone can read them.
    """
    try:
        record = record_feedback(payload.model_dump())
    except (OSError, ValueError) as exc:
        logger.error("Could not store feedback: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="Feedback could not be saved. Please try again.",
        ) from exc

    return FeedbackReceipt(
        received_at=record["received_at"],
        count=feedback_summary()["count"],
    )


@app.get(
    "/feedback/summary",
    response_model=FeedbackSummary,
    summary="How much feedback has been left",
)
async def get_feedback_summary() -> FeedbackSummary:
    """Counts only. Individual submissions are never served back."""
    return FeedbackSummary(**feedback_summary())


@app.post(
    "/report",
    summary="Render an analysis as a PDF report",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def report(payload: AnalyzeResponse) -> Response:
    """Render an already-produced analysis as a PDF.

    Takes the response rather than the request, so generating a report costs
    no second analysis and no further LLM call - the caller sends back what it
    was given. Building the PDF server-side with real table primitives gives
    measured columns, page breaks that respect row boundaries, and a header
    and footer on every page, which a print stylesheet cannot do reliably.
    """
    pdf = build_report(payload.model_dump())
    stamp = datetime.now().strftime("%Y-%m-%d-%H%M")
    label = (payload.patient_id or "results").replace(" ", "-")[:40]
    filename = f"aragen-lab-report-{label}-{stamp}.pdf"

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get(
    "/datasets",
    summary="List the sample datasets bundled with the repository",
)
async def datasets() -> dict:
    """Describe the bundled CSVs the UI can analyze without a file upload."""
    return {"datasets": list_datasets()}


@app.post(
    "/analyze_labs/dataset/{dataset_id}",
    response_model=AnalyzeResponse,
    summary="Analyze a bundled sample dataset",
    responses={
        404: {"description": "Unknown dataset, or its file is not present"},
        503: {"description": "Clinical tool server unavailable"},
    },
)
async def analyze_dataset(
    dataset_id: str,
    agent: LabAgent = Depends(get_agent),
    settings: Settings = Depends(get_settings),
) -> AnalyzeResponse:
    """Run the pipeline over one of the repository's own sample files.

    Lets the UI demonstrate the whole flow in a single click, rather than
    requiring the user to find a CSV on disk first.
    """
    raw, dataset = load_dataset(dataset_id)
    labs, row_errors, csv_patient_id = parse_csv(raw)
    enforce_batch_limit(len(labs), settings)

    return await agent.analyze(
        labs,
        patient_id=csv_patient_id or dataset.name,
        row_errors=row_errors,
    )


@app.post(
    "/preview_csv",
    summary="Parse a CSV without classifying or calling the LLM",
    responses={400: {"description": "File could not be read as a lab-results CSV"}},
)
async def preview_csv(
    file: UploadFile = File(..., description="UTF-8 CSV to inspect"),
) -> dict:
    """Show what a CSV parses to, before any analysis happens.

    Uses the same parser as the analysis endpoint, so the preview cannot
    disagree with what a subsequent upload would do. Nothing is classified and
    no LLM call is made, which makes this cheap enough to run on every file
    selection - the user sees mis-parsed columns immediately rather than after
    waiting for a full analysis.
    """
    raw = await file.read()
    labs, row_errors, patient_id = parse_csv(raw)

    return {
        "filename": file.filename,
        "size_bytes": len(raw),
        "patient_id": patient_id,
        "row_count": len(labs),
        "error_count": len(row_errors),
        "labs": [lab.model_dump() for lab in labs],
        "errors": [error.model_dump() for error in row_errors],
    }


@app.post(
    "/analyze_labs/csv",
    response_model=AnalyzeResponse,
    summary="Classify and explain lab results from a CSV upload",
    responses={
        400: {"description": "File could not be read as a lab-results CSV"},
        413: {"description": "Too many lab results in one file"},
        503: {"description": "Clinical tool server unavailable"},
    },
)
async def analyze_labs_csv(
    file: UploadFile = File(..., description="UTF-8 CSV with test_name, value, unit"),
    patient_id: str | None = Form(default=None),
    agent: LabAgent = Depends(get_agent),
    settings: Settings = Depends(get_settings),
) -> AnalyzeResponse:
    """Same analysis, with a CSV file as the input.

    Unreadable rows are reported in the response's ``errors`` list while every
    valid row is still classified.
    """
    labs, row_errors, csv_patient_id = parse_csv(await file.read())
    enforce_batch_limit(len(labs), settings)

    return await agent.analyze(
        labs,
        patient_id=patient_id or csv_patient_id,
        row_errors=row_errors,
    )
