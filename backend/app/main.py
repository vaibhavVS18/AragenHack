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

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agent import LabAgent
from .config import Settings, get_settings
from .csv_loader import CSVFormatError, parse_csv
from .datasets import DatasetNotFound, list_datasets, load_dataset
from .mcp_client import MCPUnavailableError
from .models import AnalyzeRequest, AnalyzeResponse, HealthResponse

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
