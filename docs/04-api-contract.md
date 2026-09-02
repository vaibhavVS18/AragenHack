# 04 — API Contract

Base URL (development): `http://127.0.0.1:8000`
Interactive docs once the server runs: `http://127.0.0.1:8000/docs`

## GET /health

Liveness probe. Also reports whether the MCP server is reachable and which LLM
provider is active — useful for confirming setup before a demo.

```json
{
  "status": "ok",
  "mcp_server": "connected",
  "tools_available": ["get_reference_range", "classify_lab_result", "route_by_severity"],
  "llm_provider": "mock"
}
```

## POST /analyze_labs

The assignment's required endpoint.

### Request

```json
{
  "patient_id": "ANON-0142",
  "labs": [
    { "test_name": "Hemoglobin", "value": 7.2, "unit": "g/dL"  },
    { "test_name": "Potassium",  "value": 6.8, "unit": "mEq/L" },
    { "test_name": "Glucose",    "value": 92,  "unit": "mg/dL" }
  ]
}
```

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `patient_id` | string | no | Free-form label, echoed back |
| `labs` | array | yes | 1..`MAX_LABS_PER_REQUEST` items |
| `labs[].test_name` | string | yes | Aliases and minor typos tolerated |
| `labs[].value` | number or string | yes | Strings are coerced; failures become row errors |
| `labs[].unit` | string | no | Assumed canonical if omitted |

### Response 200

```json
{
  "patient_id": "ANON-0142",
  "summary": { "total": 3, "critical": 2, "warning": 0, "normal": 1, "unknown": 0, "errors": 0 },
  "results": [
    {
      "test_name": "Potassium",
      "value": 6.8,
      "unit": "mEq/L",
      "severity": "critical",
      "reference_range": { "low": 3.5, "high": 5.1, "unit": "mEq/L" },
      "direction": "above",
      "deviation_pct": 33.3,
      "deviation_text": "33% above the upper limit of normal",
      "rule_fired": "value (6.8) > critical_high (6.5) -> critical_high",
      "matched_by": "exact",
      "explanation": "Severe hyperkalemia. At 6.8 mEq/L, cardiac conduction is at risk...",
      "next_step": "Obtain an ECG immediately and initiate potassium-lowering therapy."
    }
  ],
  "errors": [],
  "meta": { "llm_provider": "gemini", "model": "gemini-2.0-flash", "elapsed_ms": 1840 }
}
```

`results` arrives **pre-sorted** by the Route step: Critical -> Warning ->
Normal -> Unknown. The frontend renders in the order given and does not re-sort.

### Errors

| Status | Cause | Body |
|--------|-------|------|
| 400 | Empty `labs` array | `{"detail": "At least one lab result is required."}` |
| 413 | Too many rows | `{"detail": "Maximum 200 lab results per request."}` |
| 422 | Schema violation | FastAPI validation detail |
| 502 | LLM provider unreachable | Classifications still returned, explanations marked unavailable |
| 503 | MCP server failed to start | `{"detail": "Clinical tool server unavailable."}` |

**Degraded mode:** if Gemini fails, classification is unaffected. Results return
with severities intact and a null explanation plus a notice — the clinically
important half of the response never depends on the LLM.

## POST /analyze_labs/csv

Same response shape, `multipart/form-data` input.

| Field | Type | Notes |
|-------|------|-------|
| `file` | file | UTF-8 CSV |
| `patient_id` | string | optional |

Expected header (case-insensitive, order-independent):

```csv
test_name,value,unit
Hemoglobin,7.2,g/dL
Potassium,6.8,mEq/L
```

Accepted column aliases: `test_name` / `test` / `Test Name` / `analyte`,
`value` / `result` / `Result Value`, `unit` / `units` / `uom`.

Unparseable rows land in `errors` with their line number; the rest still
process.

## Severity vocabulary

`critical` · `warning` · `normal` · `unknown`

`unknown` means the test could not be resolved to a reference range. It is not
an error — the row is returned, uninterpreted, and flagged in the UI.
