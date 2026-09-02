/**
 * App — top-level container and the only stateful component.
 *
 * Data flow (one direction, no shared mutable state):
 *
 *   LabInput  --labs-->  App  --POST /analyze_labs-->  FastAPI
 *                         |
 *                         +--results-->  ResultsDisplay
 *
 * App owns: labs, results, loading, error.
 * Children stay presentational and receive everything via props.
 */
export default function App() {
  return (
    <div className="app">
      <header className="app__header">
        <h1>Clinical Lab Results Analyzer</h1>
        <p className="app__subtitle">
          AI-assisted triage with explainable classifications
        </p>
      </header>

      <main className="app__main">
        {/* step 5: <LabInput onAnalyze={...} /> */}
        {/* step 5: <ResultsDisplay results={...} /> */}
        <p className="app__placeholder">Scaffold ready — components land in step 5.</p>
      </main>
    </div>
  );
}
