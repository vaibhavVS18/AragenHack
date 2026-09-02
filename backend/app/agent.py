"""The agent: Classify -> Route -> Explain.

Hard rule for this project: the agent owns NO clinical logic of its own.
  * Classify  -> delegated to the MCP tool `classify_lab_result`
  * Route     -> delegated to the MCP tool `route_by_severity`
  * Explain   -> delegated to the LLM provider (app/llm/)

It is an MCP *client*. It never imports mcp_server.tools directly.

TODO(step 3): LabAgent.analyze(labs) -> AnalyzeResponse.
"""
