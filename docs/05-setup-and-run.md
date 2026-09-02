# 05 — Setup & Run

Requires Python 3.11+ and Node 18+ (verified on Python 3.12.5 / Node 24.16).

## Backend

```bash
cd backend

python -m venv .venv
source .venv/Scripts/activate      # Git Bash on Windows
# .venv\Scripts\activate           # PowerShell / cmd
# source .venv/bin/activate        # macOS / Linux

pip install -r requirements.txt
cp .env.example .env
```

Run it:

```bash
uvicorn app.main:app --reload --port 8000
```

- API: http://127.0.0.1:8000
- Swagger UI: http://127.0.0.1:8000/docs

You do **not** start the MCP server yourself. The agent spawns it as a
subprocess over stdio when a request arrives.

## Frontend

```bash
cd frontend
npm install
npm run dev
```

Opens on http://localhost:5173. `VITE_API_BASE_URL` defaults to
`http://127.0.0.1:8000`; override it in `frontend/.env` if you change the port.

## Gemini API key

1. Visit https://aistudio.google.com/app/apikey
2. Sign in with a Google account — **no credit card, no billing setup**
3. Click *Create API key* and copy it
4. Put it in `backend/.env`:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
```

Restart uvicorn to pick up the change.

### Building without a key

`LLM_PROVIDER=mock` runs the entire pipeline with a deterministic offline
provider. Classification, routing, MCP, and the UI all work; only the
explanation text is canned. Useful for development, demos with no network, and
reproducible tests.

## Verifying the setup

```bash
# 1. API is up and MCP is connected
curl http://127.0.0.1:8000/health

# 2. MCP server starts standalone (waiting on stdin = healthy; Ctrl+C to exit)
cd backend && python -m mcp_server.server

# 3. Inspect MCP tools in a browser UI
npx @modelcontextprotocol/inspector python -m mcp_server.server

# 4. End-to-end analyze call
curl -X POST http://127.0.0.1:8000/analyze_labs \
  -H "Content-Type: application/json" \
  -d "{\"labs\":[{\"test_name\":\"Hemoglobin\",\"value\":7.2,\"unit\":\"g/dL\"}]}"

# 5. CSV upload
curl -X POST http://127.0.0.1:8000/analyze_labs/csv \
  -F "file=@../test_data/critical_panel.csv"

# 6. Unit tests
cd backend && pytest -v
```

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `CORS policy` error in browser console | Frontend origin not allowed | Add it to `CORS_ORIGINS` in `backend/.env`, restart |
| `503 Clinical tool server unavailable` | MCP subprocess failed to launch | Run `python -m mcp_server.server` directly to see the traceback |
| MCP client hangs on connect | A `print()` in server code corrupted stdout | Log to `stderr` only. See section 9 of [MCP Explained](./02-mcp-explained.md) |
| `502` on every request | Bad or missing Gemini key | Check `GEMINI_API_KEY`, or set `LLM_PROVIDER=mock` |
| `ModuleNotFoundError: app` | Wrong working directory | Run uvicorn from `backend/` |
| Frontend shows "Failed to fetch" | Backend not running | Start uvicorn first |
