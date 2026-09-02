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
