"""MCP server entrypoint (stdio transport).

Registers the functions in tools.py as MCP tools and serves them over
stdio. Run standalone for debugging:

    python -m mcp_server.server

TODO(step 2): FastMCP instance + @mcp.tool() registrations.
"""
