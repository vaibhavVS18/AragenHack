# 02 — MCP Explained (from scratch)

Written for someone who has never used MCP before.

## 1. The problem MCP solves

An LLM can only produce text. It cannot look anything up, run a calculation, or
read a database. To do those things it needs **tools** — functions it can ask a
program to run.

Before MCP, every framework invented its own tool format. A tool written for
LangChain didn't work in Claude Desktop; one written for OpenAI's SDK didn't
work anywhere else. Same function, rewritten N times.

**MCP (Model Context Protocol)** is an open standard that fixes this. Write your
tool once as an MCP server, and *any* MCP-compatible client can use it.

Think of it as **USB for AI tools**. Before USB, every device had its own port.
After USB, one connector works everywhere.

## 2. Direct call vs. MCP call

**Without MCP** — one process, ordinary Python:

```python
from mcp_server.tools import get_reference_range
result = get_reference_range("Hemoglobin")     # a normal function call
```

**With MCP** — two processes talking over a protocol:

```python
result = await session.call_tool(
    "get_reference_range",
    {"test_name": "Hemoglobin"},
)
```

The second version looks like more work, and for a single script it is. What you
buy is that the tool now lives behind a **standard interface** that anything can
connect to — including tools you didn't write.

## 3. The three roles

```
   HOST                    CLIENT                    SERVER
   the application         the connection            the tools
   ─────────────           ──────────────            ──────────────
   our FastAPI app   ───►  app/mcp_client.py  ───►   mcp_server/server.py
   (or Claude Desktop,      manages one session       exposes:
    or any AI IDE)          per server                  get_reference_range
                                                        classify_lab_result
                                                        route_by_severity
```

* **Host** — the program the user interacts with. Ours is the FastAPI app.
* **Client** — holds the connection to one server. One client per server.
* **Server** — exposes capabilities. Runs as its own process.

The key idea: **the server is a separate program.** It doesn't know or care who
connects to it.

## 4. How they talk

Messages are **JSON-RPC 2.0**. Two transports matter:

| Transport | How it works | When to use |
|-----------|--------------|-------------|
| **stdio** | Client launches the server as a subprocess, writes to its stdin, reads its stdout | Local tools. **We use this.** |
| **HTTP/SSE** | Server runs as a web service over the network | Remote/shared tools |

We use stdio because the tool server is local, needs no auth, no port, and no
deployment — the client simply spawns it.

### An actual conversation

```
1. HANDSHAKE
   client ──► {"method":"initialize","params":{"protocolVersion":"..."}}
   server ◄── {"result":{"capabilities":{"tools":{}}}}

2. DISCOVERY  — "what can you do?"
   client ──► {"method":"tools/list"}
   server ◄── {"result":{"tools":[
                {"name":"get_reference_range",
                 "description":"Look up the clinical reference range...",
                 "inputSchema":{"type":"object",
                                "properties":{"test_name":{"type":"string"}},
                                "required":["test_name"]}},
                ...]}}

3. INVOCATION — "run this one"
   client ──► {"method":"tools/call",
               "params":{"name":"get_reference_range",
                         "arguments":{"test_name":"Hemoglobin"}}}
   server ◄── {"result":{"content":[{"type":"text",
               "text":"{\"low\":13.5,\"high\":17.5,\"unit\":\"g/dL\"}"}]}}
```

Step 2 is what makes MCP more than remote function calls: the server
**describes itself**. The client learns the tool names, what they do, and their
exact argument schemas at runtime — nothing is hardcoded.

## 5. What MCP servers can expose

| Primitive | Meaning | Used here? |
|-----------|---------|------------|
| **Tools** | Functions the agent can call (actions) | ✅ all three |
| **Resources** | Read-only data the agent can load (like files) | ❌ not needed |
| **Prompts** | Reusable prompt templates the user can pick | ❌ not needed |

Tools are the only primitive this project needs.

## 6. Our MCP server

Three tools, each mapping to a step in the assignment's required agent logic:

### `get_reference_range(test_name) -> ReferenceRange`
Looks up thresholds for a test. Checks the hardcoded table first, then falls
back to alias resolution and fuzzy matching for messy real-world names
(`"HGB"`, `"Haemoglobin"`, `"hemoglobin "`). This is the assignment's
"Optional tool: reference_range_lookup".

### `classify_lab_result(test_name, value, unit) -> ClassifiedResult`
Calls `get_reference_range` internally, compares the value, returns severity
plus the full explainability payload: the range used, the deviation, and the
rule that fired.

### `route_by_severity(results) -> RoutedResults`
The assignment's Route step. Groups and orders Critical -> Warning -> Normal
and attaches per-group counts.

## 7. Why the assignment demands this

> "Ensure MCP server is built and for all the communication by Agent"

The word doing the work is **all**. It is not enough to build an MCP server and
then bypass it. The agent must not do this:

```python
# ❌ WRONG — bypasses MCP, fails the requirement
from mcp_server.tools import classify_lab_result
result = classify_lab_result(name, value, unit)
```

It must do this:

```python
# ✅ RIGHT — goes through the protocol
result = await self.mcp.call_tool(
    "classify_lab_result",
    {"test_name": name, "value": value, "unit": unit},
)
```

**Enforcement rule for this repo:** `app/agent.py` may never import from
`mcp_server/`. A test asserts this.

## 8. Cost of the boundary, and why it's fine

MCP is not free:

* Serialization — arguments and results become JSON both ways
* Process overhead — the server is a subprocess with its own memory
* Latency — microseconds become ~milliseconds per call

For us this is irrelevant. A 200-row CSV means 200 sub-millisecond IPC calls,
while a single Gemini request takes ~1–2 seconds. The LLM dominates the budget
completely; the MCP boundary is noise.

## 9. Debugging tips

**Run the server standalone** to check it starts without the agent:

```bash
cd backend && python -m mcp_server.server
```

It will sit waiting on stdin — that means it's healthy. `Ctrl+C` to exit.

**Inspect it interactively** with the official inspector:

```bash
npx @modelcontextprotocol/inspector python -m mcp_server.server
```

Opens a browser UI listing every tool and letting you call each one by hand.
The fastest way to confirm the server works before touching the agent.

**Never print to stdout inside the server.** On stdio transport, stdout *is* the
protocol channel — a stray `print()` corrupts the JSON-RPC stream and the client
disconnects. Log to **stderr** instead:

```python
import sys
print("debug info", file=sys.stderr)   # safe
```

This is the single most common MCP bug for beginners.

## 10. Further reading

* Spec — https://modelcontextprotocol.io
* Python SDK — https://github.com/modelcontextprotocol/python-sdk
* Inspector — https://github.com/modelcontextprotocol/inspector
