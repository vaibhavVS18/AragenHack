import { Link } from "react-router-dom";

import ErrorPanel from "../components/ErrorPanel";
import LabInput from "../components/LabInput";
import ResultsDisplay from "../components/ResultsDisplay";

/**
 * AnalyzePage - the main workflow: submit results, read the verdict.
 *
 * Input, then output, in one column so the reading order matches the order
 * the work happens in.
 */

/**
 * Placeholder shown while a request is in flight.
 *
 * A skeleton in the shape of the coming result keeps the layout from jumping
 * when it arrives, and reads as progress rather than as a stall - which
 * matters here, since the batched LLM call takes a few seconds.
 */
function ResultsSkeleton() {
  return (
    <section className="results" aria-hidden="true">
      <div className="stats">
        {[0, 1, 2].map((i) => (
          <div key={i} className="stat">
            <span className="skeleton" style={{ width: "2.2rem", height: "1.9rem" }} />
            <span className="skeleton" style={{ width: "4.5rem", height: "0.7rem", marginTop: 6 }} />
          </div>
        ))}
      </div>

      {[0, 1].map((i) => (
        <div key={i} className="card">
          <span className="skeleton" style={{ display: "block", width: "38%", height: "1.1rem" }} />
          <span className="skeleton" style={{ display: "block", width: "22%", height: "1.8rem", marginTop: 12 }} />
          <span className="skeleton" style={{ display: "block", width: "100%", height: "10px", marginTop: 16, borderRadius: 999 }} />
          <span className="skeleton" style={{ display: "block", width: "92%", height: "0.85rem", marginTop: 18 }} />
          <span className="skeleton" style={{ display: "block", width: "76%", height: "0.85rem", marginTop: 7 }} />
        </div>
      ))}
    </section>
  );
}

export default function AnalyzePage({
  response,
  loading,
  error,
  catalogue,
  runAnalysis,
  dismissError,
}) {
  return (
    <>
      <LabInput
        onAnalyze={runAnalysis}
        loading={loading}
        catalogue={catalogue}
      />

      <ErrorPanel error={error} onDismiss={dismissError} />

      {loading && (
        <>
          <div className="loading" role="status">
            <span className="spinner" aria-hidden="true" />
            Classifying results over MCP, then generating explanations…
          </div>
          <ResultsSkeleton />
        </>
      )}

      {!loading && !response && !error && (
        <div className="empty-state">
          <p>
            Results appear here once analyzed. Use <strong>Load sample</strong>{" "}
            above for a quick run, or pick a{" "}
            <Link to="/datasets">bundled dataset</Link>.
          </p>
        </div>
      )}

      {!loading && <ResultsDisplay response={response} />}
    </>
  );
}
