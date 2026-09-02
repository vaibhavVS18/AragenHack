# 01 — Architecture

## Stack, and what each piece is actually for

| Layer | Technology | Responsibility |
|-------|-----------|----------------|
| UI | React 19 + Vite 8 | Input forms, CSV upload, color-coded result rendering |
| API | FastAPI (Python 3.12) | HTTP transport, validation, error handling |
| Agent | Python | Orchestrates Classify -> Route -> Explain |
| Tools | MCP server (Python) | All clinical logic: ranges, classification, routing |
| LLM | Google Gemini | Natural-language explanations only |

> **Node is build tooling, not a backend.** Vite (which runs on Node) compiles
> JSX into browser JavaScript and serves it during development. `npm run build`
> emits static files and Node disappears from the picture. Every piece of
> application logic is Python.

## System diagram

```
┌──────────────────────────────────────────────────────────────┐
│  BROWSER                                                     │
│  React: LabInput -> App -> ResultsDisplay -> ResultCard       │
└───────────────────────────┬──────────────────────────────────┘
                            │ HTTP  POST /analyze_labs
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  FastAPI  (app/main.py)          ← thin transport layer      │
│  CORS · schema validation · error mapping                    │
└───────────────────────────┬──────────────────────────────────┘
                            ▼
┌──────────────────────────────────────────────────────────────┐
│  AGENT  (app/agent.py)                                       │
│    1. CLASSIFY  ─┐                                           │
│    2. ROUTE     ─┼─ via MCP client, never direct imports     │
│    3. EXPLAIN   ─┼─ via LLM provider                         │
└──────────┬───────┴───────────────────────┬───────────────────┘
           │ MCP / JSON-RPC over stdio     │ HTTPS
           ▼                               ▼
┌────────────────────────────┐   ┌─────────────────────────────┐
│  MCP SERVER (subprocess)   │   │  Gemini API                 │
│  · get_reference_range     │   │  explanation + next step    │
│  · classify_lab_result     │   │  (never decides severity)   │
│  · route_by_severity       │   └─────────────────────────────┘
└────────────────────────────┘
```

## The one rule that shapes everything

**Code classifies. The LLM explains.**

Severity is decided by deterministic comparison against a reference range —
never by asking the model. This matters for three reasons:

1. **Correctness.** Classification is 30% of the grade and must be exact.
   `7.2 < 8.0` is not a judgement call.
2. **Reproducibility.** Same input always gives the same severity. Testable.
3. **Safety.** A hallucinated "Normal" on a critical potassium value is the
   kind of failure that makes a clinical tool worse than no tool.

The LLM's job starts *after* severity is known: turn a classified result into
language a clinician can act on.

## Request lifecycle

```
1. User submits labs (form rows or CSV file)
2. FastAPI validates the payload against Pydantic schemas
3. Agent opens an MCP session (subprocess, stdio)
4. For each lab   -> MCP: classify_lab_result(name, value, unit)
     internally   -> MCP: get_reference_range(name)  [tool calling tool]
     returns      -> severity + range + deviation + rule_fired
5. All results    -> MCP: route_by_severity(results)
     returns      -> ordered Critical -> Warning -> Normal, with counts
6. Agent batches the routed results into ONE Gemini call
     returns      -> { explanation, next_step } per result
7. Agent merges classification + explanation
8. FastAPI returns JSON; React renders grouped, color-coded cards
```

## Why the layers are split this way

**FastAPI is deliberately thin.** It knows HTTP, not medicine. Swapping it for
Flask or a CLI would not touch a line of clinical logic.

**The agent owns no domain knowledge.** It sequences steps. It does not know
what a normal hemoglobin is — it asks the MCP server.

**The MCP server owns all clinical truth.** Reference ranges and severity rules
live in exactly one place, behind a protocol boundary. Because it is a real MCP
server, Claude Desktop or any other MCP client can use the same tools without
touching this codebase.

**The LLM sits behind an interface** (`app/llm/base.py`) so Gemini can be
swapped for Claude, Ollama, or the deterministic mock via one env variable.
