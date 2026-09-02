import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";

import ErrorPanel from "../components/ErrorPanel";
import LabInput from "../components/LabInput";
import ResultsDisplay from "../components/ResultsDisplay";

/**
 * AnalyzePage - the main workflow: submit results, read the verdict.
 *
 * Laid out as numbered bands - input first, then the results component's own
 * sequence. The numbering makes the pipeline legible: a reader can see there
 * is an input step and an output step without being told.
 */

/**
 * Placeholder shown while a request is in flight.
 *
 * Shaped like the result that is coming, so the layout does not jump when it
 * lands, and it reads as progress rather than a stall - which matters, since
 * the batched LLM call takes a few seconds.
 */
function ResultsSkeleton() {
  return (
    <section className="band ground--mist" aria-hidden="true">
      <div className="severity">
        <span className="skeleton" style={{ height: 10, borderRadius: 999 }} />
        <div className="severity__legend">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="skeleton"
              style={{ width: "6.5rem", height: "1.9rem", borderRadius: 999 }}
            />
          ))}
        </div>
      </div>

      <div className="group__cards" style={{ marginTop: "var(--s5)" }}>
        {[0, 1].map((i) => (
          <div key={i} className="card">
            <span className="skeleton" style={{ display: "block", width: "38%", height: "1.1rem" }} />
            <span className="skeleton" style={{ display: "block", width: "22%", height: "1.8rem", marginTop: 12 }} />
            <span className="skeleton" style={{ display: "block", width: "100%", height: "10px", marginTop: 16, borderRadius: 999 }} />
            <span className="skeleton" style={{ display: "block", width: "92%", height: "0.85rem", marginTop: 18 }} />
            <span className="skeleton" style={{ display: "block", width: "76%", height: "0.85rem", marginTop: 7 }} />
          </div>
        ))}
      </div>
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
  onAskAboutReport,
}) {
  const resultsRef = useRef(null);
  // Identity of the analysis just completed. Scrolling keys off this rather
  // than off `response` itself, so re-rendering for an unrelated reason (a
  // filter change, a theme switch) never yanks the page around again.
  const runId = response
    ? `${response.meta?.elapsed_ms}-${response.summary?.total}-${response.patient_id ?? ""}`
    : null;

  useEffect(() => {
    if (!runId || !resultsRef.current) return;

    // A long panel pushes the results below the fold, and a user who has just
    // pressed Analyze is looking for the verdict, not the form they filled in.
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    resultsRef.current.scrollIntoView({
      behavior: reduced ? "auto" : "smooth",
      block: "start",
    });
  }, [runId]);

  return (
    <>
      <section className="band band--flush ground--paper">
        <h2 className="band__title">Enter your lab results</h2>
        <p className="band__lede">
          Type them in, or upload a CSV — an uploaded file is read back to you
          before anything is checked, so you can confirm it came through
          correctly. Nothing to hand?{" "}
          <Link to="/datasets">Try a sample</Link>.
        </p>

        <LabInput
          onAnalyze={runAnalysis}
          loading={loading}
          catalogue={catalogue}
        />
      </section>

      <ErrorPanel error={error} onDismiss={dismissError} />

      {loading && (
        <>
          <div className="loading" role="status">
            <span className="spinner" aria-hidden="true" />
            Checking each value against its reference range, then writing
            the explanations…
          </div>
          <ResultsSkeleton />
        </>
      )}

      {!loading && !response && !error && (
        <div className="empty-state">
          <p>
            Results appear here once analyzed. Use <strong>Load sample</strong>{" "}
            for a quick run, or pick a{" "}
            <Link to="/datasets">bundled dataset</Link>.
          </p>
        </div>
      )}

      <div ref={resultsRef} className="results-anchor">
        {!loading && (
          <ResultsDisplay response={response} onAskAboutReport={onAskAboutReport} />
        )}
      </div>
    </>
  );
}
