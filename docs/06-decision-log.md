# 06 — Decision Log

Why things are the way they are. Chronological.

---

### D1 — Gemini as the LLM provider

**Context:** The assignment lists Claude, Gemini, and Ollama as options.

**Decision:** Google Gemini.

**Why:** Genuinely free tier with no credit card. Claude's API is pay-as-you-go
and requires billing setup. Ollama is free but slower, produces weaker clinical
prose, and forces a grader to install it locally before the demo will run.

**Mitigation:** All LLM access goes through `app/llm/base.py`. Switching
providers is one env variable plus one small module, not a rewrite.

---

### D2 — Code classifies, the LLM explains

**Context:** The LLM could be asked to assign severity directly.

**Decision:** Severity is computed by deterministic threshold comparison. The
LLM only writes prose, after severity is already known.

**Why:** Classification is 30% of the rubric and must be exact, reproducible,
and unit-testable. A hallucinated "Normal" on a critical value is a clinically
dangerous failure mode. The comparison `6.8 > 6.5` cannot hallucinate.

---

### D3 — MCP over stdio, not HTTP

**Context:** MCP supports both stdio and HTTP/SSE transports.

**Decision:** stdio.

**Why:** The tool server is local. stdio needs no port, no auth, no deployment,
and no second terminal — the client spawns the subprocess itself. HTTP would add
operational surface for zero benefit at this scale.

---

### D4 — The agent may never import from `mcp_server/`

**Context:** The assignment requires *all* agent communication to go through
MCP. It would be easy to import the tool functions directly "just for speed".

**Decision:** `app/agent.py` talks only to `app/mcp_client.py`. A test asserts
that the import boundary holds.

**Why:** Bypassing the protocol would leave an MCP server that exists but is
never used — failing the requirement while appearing to satisfy it.

---

### D5 — Batched LLM calls, not one per result

**Context:** The FAQ requires an LLM explanation for every result, including
normal ones.

**Decision:** One structured Gemini call per request carrying all results,
rather than one call per row.

**Why:** A 30-row CSV would otherwise mean 30 sequential round-trips — slow
enough to break a live demo and likely to trip free-tier rate limits. Every
result still receives a genuine model-generated explanation, which is what the
FAQ actually requires.

---

### D6 — Five-band severity model

**Context:** A simple in-range/out-of-range check cannot separate "slightly low"
from "call a doctor now".

**Decision:** Four thresholds per test producing five bands: critical low,
warning low, normal, warning high, critical high.

**Why:** The assignment requires three severities, and Critical vs. Warning is
precisely the distinction that makes routing useful. Boundaries are inclusive of
Normal, stated explicitly so the edge case is unambiguous.

---

### D7 — Partial success over all-or-nothing

**Context:** Real CSVs contain junk rows.

**Decision:** Bad rows produce entries in a separate `errors` array; valid rows
are still classified and returned.

**Why:** Failing an entire 50-row upload because one cell says "N/A" is hostile
behavior, and the rubric explicitly grades error handling.

---

### D8 — Degraded mode when the LLM is unavailable

**Context:** Free-tier APIs rate-limit and networks fail — especially during a
live demo.

**Decision:** If Gemini fails, return classifications with severities intact and
explanations marked unavailable, rather than failing the whole request.

**Why:** The clinically critical half of the answer — what is abnormal and how
abnormal — is computed locally and should never be lost to a third-party outage.

---

### D9 — Vite over Create React App

**Context:** Needed a React toolchain.

**Decision:** Vite 8 with React 19.

**Why:** CRA is deprecated and unmaintained. Vite is the current standard, with
much faster dev startup and hot reload. Node is used **only** as build tooling
here: `npm run build` emits static files and no Node process exists in
production.

---

### D10 — Gemini model: `gemini-3.5-flash-lite`

**Context:** `gemini-2.0-flash`, named in the original plan, has been retired -
the API returns 404 and points at newer models. Several replacements exist.

**Decision:** `gemini-3.5-flash-lite`, configurable via `GEMINI_MODEL`.

**Why:** Measured on the same 8-result critical panel:

| Model | Latency | Output |
|-------|---------|--------|
| gemini-3.6-flash | 13.6 s | 3270 chars |
| gemini-3.6-flash (thinking=low) | 13.1 s | 3047 chars |
| gemini-2.5-flash | 10.5 s | 3049 chars |
| **gemini-3.5-flash-lite** | **3.0 s** | 3087 chars |
| gemini-3.1-flash-lite | 2.8 s | 2997 chars |

Roughly 4.5x faster than `gemini-3.6-flash` with no observable loss in clinical
quality - side-by-side output named the same actions (immediate ECG for
hyperkalemia; iron panel, ferritin and reticulocyte count for anemia). The
larger models spend their extra time on internal reasoning that this task does
not need, because the hard decision (severity) was already made deterministically
before the model is called.

Thirty seconds of latency would have broken a live demo. Three seconds does not.

---

### D11 — The test suite never calls a real LLM

**Context:** After Gemini was wired up, the suite began calling the live API and
its runtime went from 50 seconds to 294.

**Decision:** `tests/conftest.py` pins `LLM_PROVIDER=mock` for every test run,
and the API fixture replaces the agent built by `lifespan`.

**Why:** Network calls make tests slow, flaky, dependent on a key the grader may
not have, and consume free-tier quota. Live Gemini output is verified by hand;
asserting on generated prose would be a flaky test of a non-deterministic system
anyway.

---

### D12 — The result's own reference interval wins over our table

**Context:** The Kaggle dataset ships `Min_Reference` and `Max_Reference` on
every row. Our built-in table also has ranges. They disagree - this laboratory
uses 12-15 g/dL for hemoglobin; our table says 12-17.5.

**Decision:** A reference interval supplied with a result takes precedence over
the built-in table. The table remains the fallback, and the only source of
genuine critical thresholds.

**Why:** Reference intervals legitimately vary by laboratory, method and
population. The range that arrived beside a value is authoritative for that
value; overriding it with our own would produce confidently wrong verdicts on
real data. Precedence is reported per result as `range_source`, so a user can
always see which was used.

**Consequence:** The dataset has no concept of a panic value, so criticals
still come from our table where the test is known. Where it is not (RDW, PDW,
PCT, Total IgE), criticals are estimated from the interval width and marked
`critical_basis: "derived"` - shown on the card as an estimate, never passed
off as a published threshold.

---

### D13 — Qualitative results are compared as words

**Context:** A third of the dataset is urinalysis strips reporting `Negatif`,
`Normal` or `1+`. Numeric parsing rejected all of them as "not numeric".

**Decision:** A separate qualitative comparison path. Observed and expected
values are folded to canonical tokens (`negative`, `positive`, `normal`,
`trace`) and compared as words.

**Why:** These are real results, not bad data - refusing them would have left a
third of the required dataset unclassified. A mismatch is graded Warning and
never Critical: a strip records presence, not amount, so it cannot by itself
support a claim of immediate danger.

---

### D14 — Turkish names folded to ASCII with an explicit map

**Context:** The dataset uses Turkish test names: `Trombosit`, `Lökosit`,
`İnsülin`, `Nötrofil%`.

**Decision:** An explicit character map (`ı İ ş ğ ö ü ç` -> ASCII) applied
during name normalization, plus Turkish aliases in the reference table.

**Why:** `unicodedata` normalization does not handle `ı` and `İ` the way it
handles the other diacritics, and getting them wrong silently breaks matching
for every test containing them. An explicit map is boring and correct.

A related trap: `Lökosit` is the white cell count, `Lökosit (Strip)` is a urine
dipstick. The fuzzy matcher must not collapse them - at a 0.82 cutoff it does
not, and a test asserts it.

---

### D15 — Four pages rather than one

**Context:** A single page had to carry input, results, the reference table and
an explanation of how classification works.

**Decision:** React Router with four routes: Analyze, Datasets, Reference
ranges, How it works.

**Why:** The explainability requirement produces genuinely different kinds of
content. Per-result reasoning belongs on the result card; the threshold table
and the description of the pipeline are reference material a user consults
occasionally, and crowding them into the analysis view buried the thing they
came to do. Analysis state lives in the shell, so a run started on Datasets is
still on screen after navigating to Analyze.

---

### D16 — Bundled datasets are analyzable in one click

**Context:** Demonstrating the app required finding a CSV on disk first.

**Decision:** `GET /datasets` publishes the repository's own sample files and
`POST /analyze_labs/dataset/{id}` runs one through the normal pipeline.

**Why:** A reviewer should be able to see the whole flow working within seconds
of starting the app. The catalogue is an explicit registry, not a directory
scan, and ids are never joined onto a filesystem path - so there is no
traversal surface.
