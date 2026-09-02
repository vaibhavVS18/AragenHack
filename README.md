# Clinical Lab Results Analyzer

AI-assisted triage for clinical lab results. Submit lab values, get each one
classified as **Critical / Warning / Normal**, with an explanation of *why* it
was flagged and a suggested next step — then take the whole panel away as a PDF.

Built with **FastAPI · MCP · React · Gemini · Ollama**.

> **Explainable by construction.** Severity is decided by deterministic
> threshold comparison in code — never by the LLM. Every result exposes the
> reference range it was compared against, how far outside it fell, and the
> exact rule that fired. The LLM's job is to translate that into language a
> patient can act on, not to make the call.

---

## Features at a glance

| Feature | What it gives you | Built with |
|---|---|---|
| **Deterministic classification** | Normal / Warning / Critical from a fixed rule, never from the LLM | MCP tool `classify_lab_result` |
| **Severity routing** | Results ordered worst-first, with counts | MCP tool `route_by_severity` |
| **Reference table over MCP** | 16 tests with aliases, units and critical thresholds | MCP tool `list_reference_ranges` |
| **Written explanations** | What the test measures, what your result means, causes, urgency, next steps, questions for a doctor | Google Gemini `3.5-flash-lite`, one batched call |
| **Audit trail per result** | The literal comparison that fired, the range used, and where it came from | Python, surfaced in the API response |
| **PDF report** | The whole panel as a real document — measured tables, row-aware page breaks, `Page X of Y`, Aragen branding | ReportLab (server-side) |
| **CSV export** | Full result set including ranges and rules | Browser-side, no round trip |
| **Chat assistant — about the app** | Answers from the repo's own docs, with sources shown | Ollama `qwen2.5:3b` + `nomic-embed-text`, NumPy cosine similarity |
| **Chat assistant — about your report** | Ask about *your* results in your own words; it quotes your numbers back | Ollama `qwen2.5:3b`, no retrieval — the report is the whole context |
| **Safety guards** | Medical questions refused in code; greetings answered without a model | Deterministic Python, before the LLM runs |
| **CSV upload + preview** | See exactly what was parsed before anything is analyzed | FastAPI + `python-multipart` |
| **Bundled datasets** | Four files runnable in one click, including the real Kaggle set | FastAPI |
| **Test-name picker** | Names come from the server; unknown names cannot be submitted | React combobox fed by MCP |
| **Degraded mode** | LLM down? You still get every severity, range and rule | Agent failure policy |
| **Feedback** | Stored server-side, not posted to a third party with keys in the bundle | FastAPI + JSONL |
| **Four pages, two themes** | Analyze · Datasets · Reference ranges · How it works | React 19 + Vite 8 |

A two-page PDF summary of all of the above:
**[docs/AragenAI-Project-Overview.pdf](./docs/AragenAI-Project-Overview.pdf)**

---

## Contents

- [What it does](#what-it-does)
- [Architecture](#architecture)
- [Run it from a clone](#run-it-from-a-clone)
- [Features](#features)
- [The assistant](#the-assistant)
- [API](#api)
- [Project structure](#project-structure)
- [The Kaggle dataset](#the-kaggle-dataset)
- [Tests](#tests)
- [Tech stack](#tech-stack)
- [Documentation](#documentation)
- [Limitations](#limitations)

---

## What it does

1. You enter lab results — by hand, by CSV upload, or by running a bundled
   dataset.
2. Each value is compared against a reference range by a **fixed rule** and
   graded Normal, Warning or Critical.
3. Results are **ordered by severity**, worst first.
4. An LLM writes the explanation for each one: what the test measures, what the
   result means, how soon to act, common causes, what to do, and questions to
   ask a doctor.
5. You can download the panel as a **PDF report**, export it as CSV, or **ask an
   assistant about it** in your own words.

The classification and the explanation are strictly separated. If the LLM is
unreachable, you still get every severity, range and rule — only the prose is
missing, and the UI says so.

---

## Architecture

```
React (Vite)  ──HTTP──►  FastAPI  ──►  Agent  ──MCP/stdio──►  MCP Server
     │                      │             │                   · get_reference_range
     │                      │             │                   · list_reference_ranges
     │                      │             │                   · classify_lab_result
     │                      │             │                   · route_by_severity
     │                      │             │
     │                      │             └──HTTPS──►  Gemini   (explanations only)
     │                      │
     └── assistant ─────────┴──HTTP──►  Ollama (local)         (help + report Q&A)
```

Node is build tooling only — Vite compiles React to static files. All
application logic is Python.

**Agent pipeline — `Classify → Route → Explain`**

| Step | Where it runs | What it decides |
|---|---|---|
| **Classify** | MCP tool `classify_lab_result` | The severity. Pure comparison, no model. |
| **Route** | MCP tool `route_by_severity` | The order and the counts. |
| **Explain** | Gemini, one batched call | The wording. Never the severity. |

The agent never imports `mcp_server`. Every tool call goes over the MCP client,
which is what makes *"all communication by the agent goes through MCP"*
structurally true rather than a claim — `tests/test_agent.py` asserts that
boundary.

**Failure policy**, deliberately asymmetric:

- **MCP unavailable** → the request fails (503). Without classification there is
  nothing trustworthy to return.
- **LLM unavailable** → the request succeeds without explanations. Severities are
  computed locally and must never be lost to a third-party outage.

---

## Run it from a clone

### Prerequisites

- **Python 3.12+**
- **Node 18+**
- *(optional)* **[Ollama](https://ollama.com)** — only for the help assistant

### 1. Clone

```bash
git clone https://github.com/vaibhavVS18/AragenHack.git
cd AragenHack
```

### 2. Backend

```bash
cd backend
python -m venv .venv

# Windows (Git Bash)          source .venv/Scripts/activate
# Windows (PowerShell)        .venv\Scripts\Activate.ps1
# macOS / Linux               source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

The MCP server is **not** started separately — the agent spawns it over stdio
per request. On startup you should see:

```
MCP server reachable, tools: get_reference_range, list_reference_ranges,
                             classify_lab_result, route_by_severity
```

### 3. Frontend

In a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**.

### 4. Explanations (optional but recommended)

The default `LLM_PROVIDER=mock` runs the entire pipeline **with no API key** —
useful for grading, development and offline demos. For real explanations, get a
free key at <https://aistudio.google.com/app/apikey> (no card required) and edit
`backend/.env`:

```ini
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-key-here
```

### 5. The assistant (optional)

The help widget runs **entirely on your own machine**. Install Ollama, then:

```bash
ollama pull qwen2.5:3b        # answers questions
ollama pull nomic-embed-text  # indexes the documentation
```

Without them the widget still appears and tells you exactly what to start — it
never silently sends your questions to a cloud model.

### Verify the install

```bash
cd backend && pytest -q          # 317 tests, no network required
```

---

## Features

### Input

- **Manual entry** — add rows of test / value / unit. The test name is a
  searchable picker: names come from the reference table over MCP, so the UI can
  never suggest something the server cannot classify. Selecting a test fills its
  unit automatically, and a name that is not on the list is cleared rather than
  submitted.
- **CSV upload** — drag and drop, with a **preview of what was parsed** before
  anything is analyzed, so a mis-mapped column is visible immediately.
- **Bundled datasets** — three synthetic CSVs plus the real Kaggle file, each
  runnable in one click.

### Classification

- **Five-band severity model** — `critical_low`, `low`, `normal`, `high`,
  `critical_high` — collapsed to the three labels the spec asks for. Normal
  boundaries are inclusive.
- **Range precedence** — a laboratory's own per-row interval beats the built-in
  table, which beats nothing at all. A lab's interval is authoritative for its
  own result.
- **Qualitative comparison** — urinalysis strips reporting `Negatif`, `Normal`,
  `1+` are compared as words, not coerced to numbers.
- **Unit compatibility** — a value in the wrong unit is reported, never silently
  converted.
- **Turkish name folding** — `Trombosit`, `Lökosit`, `İnsülin` resolve correctly
  (`ı` and `İ` do not decompose under NFKD, so the fold is explicit).
- **Fuzzy + alias matching** — `HGB`, `Hb`, `haemoglobin` all reach Hemoglobin.

### Output

- **Verdict first** — one sentence saying whether anything is wrong, before any
  numbers.
- **A proportional severity bar** — the shape of the panel at a glance, with the
  legend doubling as a filter.
- **Per-result card** — value, a gauge showing where it sits across every
  severity band, and the explanation laid out as a table: what the test
  measures, what your result means, common causes, how soon to act, what to do,
  and questions for your doctor.
- **The audit trail** — every card can expand to show the literal comparison
  that produced its severity (`value (6.9) > critical_high (6.5)`), which range
  was used and where it came from.
- **Unreadable rows are reported, never dropped** — a row that fails to parse
  appears with the reason; a row that parses but cannot be classified is
  `unknown` with a one-line fix. Neither costs an LLM call.

### Reports

- **PDF report** — generated server-side with ReportLab: real tables, measured
  columns, row-aware page breaks and `Page X of Y`. Not a print stylesheet.
- **CSV export** — the full result set including ranges and rules.

### The rest

- Four pages: **Analyze · Datasets · Reference ranges · How it works**
- Light and dark themes, light by default
- Live backend status in the navbar (MCP connection, tool count, active model)
- A feedback modal that stores submissions server-side — rather than posting to
  a mail service, which would ship the provider's key in the JS bundle

---

## The assistant

A retrieval-augmented help widget, bottom right. It has **two modes**, kept
deliberately separate because they answer from different grounds.

### Mode 1 — about the app (RAG)

Indexes the repository's own documentation plus the reference table fetched over
MCP: **116 chunks**, embedded with `nomic-embed-text`, searched by cosine
similarity over a NumPy array. No vector database — at this size an in-memory
matrix is faster than any of them and adds no dependency.

Every answer shows its sources. An assistant that cites nothing is
indistinguishable from one that guessed.

### Mode 2 — about your report

Press **Ask about your report** under any result set. The panel attaches a
digest of what is on screen and answers from **that alone** — no retrieval, no
index, no embedding call:

```
which of my results is most urgent?
→ The most urgent result is Potassium at 6.9 mEq/L, which is CRITICAL. It is
  35.3% above the upper limit of normal (5.1 mEq/L).
```

Sharing one path was tried and abandoned: asked *"why is it critical?"* about a
real panel, retrieval returned three documentation chunks and the model answered
with a textbook definition, never looking at the reader's value. Skipping
retrieval also removes ~700ms per answer.

The report is built on the client from the response already on screen — never
re-analyzed, never stored. A new analysis clears the conversation about the
previous one, so two panels can never be mixed in one answer.

### Three guards, all before the model

| Guard | Catches | Why deterministic |
|---|---|---|
| **Small talk** | `hi`, `thanks`, `ok` | `hi` embeds 0.487 from *"Can you tell me if I am ill?"* — above the retrieval floor — so the model answered *that*. Greetings carry no lexical signal; no threshold separates them from real questions. |
| **Scope** | `am I going to be ok?`, `should I take a supplement?` | The prompt asked the model to decline and it complied with the user instead. A gate in code cannot be talked around. |
| **Tone** | worried / urgent / confused / skeptical | Steers the wording without changing the facts. |

### Local only

Both the chat model and the embeddings run through Ollama with **no cloud
fallback**. That is a correctness decision, not a preference: the two embedding
backends produce different vector spaces (768 dimensions against 3072), so
falling back would discard the index and rebuild it mid-question — and would
move the reader's own lab values off their machine without telling them.

When Ollama is not running, the assistant says which model is missing and the
exact command to install it.

---

## API

Interactive docs at **http://localhost:8000/docs**.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Backend, MCP and LLM status |
| `GET` | `/reference_ranges` | The clinical table, over MCP |
| `POST` | `/analyze_labs` | Classify + explain a JSON batch |
| `POST` | `/analyze_labs/csv` | Same, from an uploaded CSV |
| `POST` | `/analyze_labs/dataset/{id}` | Same, from a bundled dataset |
| `POST` | `/preview_csv` | Parse a CSV without classifying or calling the LLM |
| `GET` | `/datasets` | List bundled datasets |
| `POST` | `/report` | Render an analysis as a PDF |
| `GET` | `/assistant/status` | Whether the assistant can answer, and on what |
| `POST` | `/assistant/ask` | Ask about the application (RAG) |
| `POST` | `/assistant/report` | Ask about one set of results (no retrieval) |
| `POST` | `/feedback` | Record feedback |
| `GET` | `/feedback/summary` | Count and average rating |

Full schemas and error codes: [docs/04-api-contract.md](./docs/04-api-contract.md).

---

## Project structure

```
AragenHack/
├─ backend/
│  ├─ app/                     FastAPI + agent — HTTP and orchestration only
│  │  ├─ main.py               routes, CORS, error handling
│  │  ├─ agent.py              Classify → Route → Explain
│  │  ├─ mcp_client.py         MCP client wrapper (stdio)
│  │  ├─ models.py             Pydantic schemas
│  │  ├─ csv_loader.py         CSV parsing and normalisation
│  │  ├─ report.py             ReportLab PDF generation
│  │  ├─ feedback.py           JSONL feedback store
│  │  ├─ config.py             typed settings from .env
│  │  ├─ llm/                  provider interface · gemini · mock
│  │  └─ assistant/            RAG help widget
│  │     ├─ service.py         retrieve → prompt → generate; report mode
│  │     ├─ corpus.py          docs + reference table → chunks
│  │     ├─ embeddings.py      Ollama embeddings
│  │     ├─ store.py           NumPy cosine-similarity index
│  │     ├─ scope.py           medical-question gate
│  │     ├─ smalltalk.py       greetings, answered without a model
│  │     └─ sentiment.py       tone detection
│  ├─ mcp_server/              ALL clinical logic lives here
│  │  ├─ server.py             MCP server entrypoint (stdio)
│  │  ├─ tools.py              the four MCP tools
│  │  └─ reference_ranges.py   clinical range table — 16 tests
│  └─ tests/                   317 tests
├─ frontend/src/
│  ├─ App.jsx                  shell: navigation, shared analysis state, routes
│  ├─ pages/                   Analyze · Datasets · Reference ranges · How it works
│  ├─ components/              LabInput · ResultsDisplay · ResultCard · Assistant …
│  ├─ lib/                     report digest, CSV export, theme
│  └─ api/client.js            the only module that talks to the backend
├─ test_data/                  3 synthetic CSVs
├─ data/                       the Kaggle dataset (committed; CC0-1.0)
└─ docs/                       full documentation
```

---

## The Kaggle dataset

[Laboratory Test Results – Anonymized Dataset](https://www.kaggle.com/datasets/pinar-topuz/lab-test-results)
(`pinar-topuz/lab-test-results`, CC0-1.0) is committed at
[`data/lab_test_results_public.csv`](./data/lab_test_results_public.csv) — 3 KB
and public domain, so the demo and its validation tests run straight from a
clone.

Three properties of it shaped the design:

1. **Turkish test names** — `Trombosit`, `Lökosit`, `İnsülin`. Handled by an
   explicit character fold plus aliases in the reference table.
2. **Per-row reference intervals** — `Min_Reference` / `Max_Reference`, which
   take precedence over the built-in table.
3. **Qualitative results** — urinalysis strips reporting `Negatif`, `Normal`,
   `1+`. Compared as words.

The dataset also carries a `Status` column — the laboratory's own verdict. It is
never fed to the classifier;
[`tests/test_kaggle_dataset.py`](./backend/tests/test_kaggle_dataset.py) checks
our classification *against* it:

> **27 rows · 0 unclassified · 0 disagreements**

```bash
cd backend && pytest tests/test_kaggle_dataset.py -v
```

---

## Tests

```bash
cd backend && pytest -q      # 317 passed
```

No network and no API key — `tests/conftest.py` pins `LLM_PROVIDER=mock` at
import time, because environment variables outrank `.env` in pydantic-settings.
Without it the suite would call live Gemini: slow, flaky, and dependent on a key
the grader may not have.

| File | Covers |
|---|---|
| `test_classification.py` | Severity bands, boundaries, precedence, qualitative, units |
| `test_mcp_server.py` | Tool contracts and schemas |
| `test_agent.py` | Pipeline order, and that the agent never imports `mcp_server` |
| `test_api.py` | Every endpoint, success and failure |
| `test_llm.py` | Provider interface, parsing, degraded mode |
| `test_report.py` | PDF renders, paginates, and is a valid document |
| `test_assistant.py` | Scope guard, small talk, chunking, retrieval, report separation |
| `test_kaggle_dataset.py` | The real dataset, against its own verdicts |

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| API | FastAPI (Python 3.12) | Async, Pydantic validation, generated OpenAPI docs |
| Tools | MCP over stdio (SDK v2.1) | Standard protocol; the tools are reusable by any MCP client |
| Explanations | Google Gemini `3.5-flash-lite` | Free tier, no card. ~4.5× faster than the larger flash models with no measurable quality loss here — severity is already decided before the model is called |
| Assistant chat | Ollama `qwen2.5:3b` | Local. Instruct, not reasoning: `qwen3:4b` took ~60s per answer on CPU and narrated its thinking into the reply |
| Assistant embeddings | Ollama `nomic-embed-text` | Local, 768-dim, fast on CPU |
| Vector search | NumPy | 116 chunks. A vector DB would add a dependency and a service to be slower |
| PDF | ReportLab | Real tables and row-aware page breaks; a print stylesheet cannot do either reliably |
| UI | React 19 + Vite 8 | Current standard; CRA is deprecated |
| Routing | react-router-dom 7 | Four pages, shared analysis state in the shell |

---

## Documentation

| Doc | Contents |
|---|---|
| [01 Architecture](./docs/01-architecture.md) | Layers, diagrams, request lifecycle |
| [02 MCP Explained](./docs/02-mcp-explained.md) | MCP from scratch, and how ours works |
| [03 Classification Logic](./docs/03-classification-logic.md) | Reference ranges, severity bands, edge cases |
| [04 API Contract](./docs/04-api-contract.md) | Endpoints, schemas, error codes |
| [05 Setup & Run](./docs/05-setup-and-run.md) | Install, configure, verify, troubleshoot |
| [06 Decision Log](./docs/06-decision-log.md) | Why each design choice was made |
| [Project Overview (PDF)](./docs/AragenAI-Project-Overview.pdf) | Two-page summary of every feature and tool — regenerate with `docs/make_overview_pdf.py` |

---

## Limitations

Worth stating plainly, because the alternative is implying otherwise.

- **This is not a medical device.** It compares numbers to published reference
  ranges. It does not diagnose, and it does not know anything about the person
  the numbers came from — age, sex, pregnancy, medication and prior results all
  change what a value means.
- **The reference table is a teaching set**, not a laboratory's own. Where a CSV
  supplies its own interval, that one is used instead.
- **16 tests are covered.** Anything outside the table is reported as `unknown`
  rather than guessed at.
- **Explanations are generated.** They are grounded in a classification the code
  made, but the wording comes from a language model and should be read as such.
- **The assistant answers about this application and your own results.** It
  refuses medical questions in code, not by asking the model nicely.

---

## Licence

Written as a GenAI full-stack assignment; no licence is applied to the code.
The bundled dataset is CC0-1.0, from the Kaggle link above.
