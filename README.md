# Clinical Lab Results Analyzer

AI-assisted triage for clinical lab results. Submit lab values, get them
classified as **Critical / Warning / Normal**, with an explanation of *why*
each was flagged and a suggested next step.

Built with **FastAPI + MCP + React + Gemini**.

> **Explainable by construction.** Severity is decided by deterministic
> threshold comparison in code — never by the LLM. Every result exposes the
> reference range it was compared against, how far outside it fell, and the
> exact rule that fired. The LLM's role is to translate that into clinical
> language, not to make the call.

## Architecture at a glance

```
React (Vite)  ──HTTP──►  FastAPI  ──►  Agent  ──MCP/stdio──►  MCP Server
                                          │                    · get_reference_range
                                          │                    · classify_lab_result
                                          │                    · route_by_severity
                                          └──HTTPS──►  Gemini (explanations only)
```

Node is build tooling only — Vite compiles the React app to static files.
All application logic is Python.

**Agent pipeline:** `Classify -> Route -> Explain`

1. **Classify** — compare each value to its reference range (via MCP)
2. **Route** — group and order by severity, critical first (via MCP)
3. **Explain** — one batched LLM call generates explanation + next step

## Quick start

```bash
# Backend
cd backend
python -m venv .venv && source .venv/Scripts/activate
pip install -r requirements.txt
cp .env.example .env                    # works immediately with LLM_PROVIDER=mock
uvicorn app.main:app --reload --port 8000

# Frontend (second terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. Full instructions in
[docs/05-setup-and-run.md](./docs/05-setup-and-run.md).

The default `LLM_PROVIDER=mock` runs the whole pipeline with **no API key**.
For real explanations, get a free key at
https://aistudio.google.com/app/apikey and set `LLM_PROVIDER=gemini`.

## Project structure

```
AragenHack/
├─ backend/
│  ├─ app/                    FastAPI + agent (HTTP and orchestration only)
│  │  ├─ main.py              routes, CORS, error handling
│  │  ├─ agent.py             Classify -> Route -> Explain
│  │  ├─ mcp_client.py        MCP client wrapper (stdio)
│  │  ├─ models.py            Pydantic schemas
│  │  ├─ csv_loader.py        CSV parsing and normalization
│  │  ├─ config.py            typed settings from .env
│  │  └─ llm/                 provider interface + gemini + mock
│  ├─ mcp_server/             ALL clinical logic lives here
│  │  ├─ server.py            MCP server entrypoint (stdio)
│  │  ├─ tools.py             the three MCP tools
│  │  └─ reference_ranges.py  clinical range table
│  └─ tests/
├─ frontend/src/
│  ├─ App.jsx                 shell: navigation, shared analysis state, routes
│  ├─ pages/                  Analyze · Datasets · Reference ranges · How it works
│  ├─ components/             LabInput · ResultsDisplay · ResultCard · SeverityBadge
│  └─ api/client.js           the only module that talks to the backend
├─ test_data/                 3 synthetic CSVs
├─ data/                      the Kaggle dataset (committed; CC0-1.0)
└─ docs/                      full documentation
```

## Pages

| Route | Purpose |
|-------|---------|
| `/` | Analyze — enter results manually or upload a CSV |
| `/datasets` | Run any bundled sample file in one click |
| `/reference` | The clinical threshold table, served over MCP |
| `/about` | How a verdict is produced, and its limitations |

## The Kaggle dataset

[Laboratory Test Results – Anonymized Dataset](https://www.kaggle.com/datasets/pinar-topuz/lab-test-results)
(`pinar-topuz/lab-test-results`, CC0-1.0) is committed at
[`data/lab_test_results_public.csv`](./data/lab_test_results_public.csv) — it is
3 KB and public domain, so the demo and its validation tests run straight from a
clone.

Three properties of it shaped the design:

1. **Turkish test names** — `Trombosit`, `Lökosit`, `İnsülin`. Handled by an
   explicit character fold plus aliases in the reference table.
2. **Per-row reference intervals** — `Min_Reference` / `Max_Reference`. These
   take precedence over the built-in table, because a laboratory's own interval
   is authoritative for its own result.
3. **Qualitative results** — urinalysis strips reporting `Negatif`, `Normal`,
   `1+`. Compared as words, not numbers.

The dataset also carries a `Status` column — the laboratory's own verdict. It is
never fed to the classifier, and
[`tests/test_kaggle_dataset.py`](./backend/tests/test_kaggle_dataset.py)
checks our classification against it: **27 rows, 0 unclassified, 0
disagreements.**

Run just that check:

```bash
cd backend && pytest tests/test_kaggle_dataset.py -v
```

## Documentation

| Doc | Contents |
|-----|----------|
| [01 Architecture](./docs/01-architecture.md) | Layers, diagrams, request lifecycle |
| [02 MCP Explained](./docs/02-mcp-explained.md) | MCP from scratch, and how ours works |
| [03 Classification Logic](./docs/03-classification-logic.md) | Reference ranges, severity bands, edge cases |
| [04 API Contract](./docs/04-api-contract.md) | Endpoints, schemas, error codes |
| [05 Setup & Run](./docs/05-setup-and-run.md) | Install, configure, verify, troubleshoot |
| [06 Decision Log](./docs/06-decision-log.md) | Why each design choice was made |

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| API | FastAPI (Python 3.12) | Async, Pydantic validation, auto-generated docs |
| Tools | MCP over stdio | Standard protocol; tools reusable by any MCP client |
| LLM | Google Gemini | Free tier, no credit card required |
| UI | React 19 + Vite 8 | Current standard; CRA is deprecated |

## Status

End-to-end working. **217 backend tests passing.**

- [x] Project structure, docs, tooling
- [x] MCP server: 4 tools over stdio, 16 lab tests
- [x] Agent: Classify -> Route -> Explain, entirely over MCP
- [x] FastAPI: JSON, CSV upload and bundled-dataset endpoints
- [x] Gemini explanation layer with degraded mode
- [x] React UI: 4 pages, color-coded results, per-result reasoning
- [x] Test data: 3 synthetic CSVs
- [x] Kaggle dataset: parsed, classified and validated against its own Status
