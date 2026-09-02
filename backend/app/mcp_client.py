"""Thin MCP client wrapper.

Spawns `mcp_server/server.py` as a subprocess, speaks JSON-RPC over stdio,
and exposes `call_tool(name, args)` to the agent. Owns the session
lifecycle so the agent never touches protocol details.

TODO(step 3): connect(), call_tool(), list_tools(), aclose().
"""
