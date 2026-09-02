/**
 * StatusBar - backend readiness, shown in the header on every page.
 *
 * A stopped backend is the most common failure in development, so it is made
 * visible before the user fills in a form rather than after they submit it.
 */
export default function StatusBar({ health }) {
  if (!health) {
    return (
      <div className="status">
        <span className="status__dot" aria-hidden="true" />
        Checking backend…
      </div>
    );
  }

  if (health.error) {
    return (
      <div className="status status--down" title={health.error}>
        <span className="status__dot" aria-hidden="true" />
        Backend unreachable
      </div>
    );
  }

  const degraded = health.status !== "ok";
  return (
    <div className={`status ${degraded ? "status--degraded" : "status--up"}`}>
      <span className="status__dot" aria-hidden="true" />
      MCP {health.mcp_server} · {health.tools_available.length} tools ·{" "}
      {health.llm_provider}
      {health.llm_model ? ` (${health.llm_model})` : ""}
    </div>
  );
}
