import ResultCard from "./ResultCard";
import { SEVERITY_META, SEVERITY_ORDER } from "./severity";

/**
 * ResultsDisplay - renders the agent's response.
 *
 * Results arrive already ordered by the backend's Route step, so this
 * component groups them under headings without re-sorting. Ordering is a
 * clinical decision and belongs on the server, beside the severity rules that
 * produced it, rather than duplicated here where the two could drift apart.
 */

function SummaryTiles({ summary }) {
  const tiles = [
    ...SEVERITY_ORDER.map((severity) => ({
      key: severity,
      value: summary[severity] ?? 0,
      label: SEVERITY_META[severity].label,
    })),
    { key: "errors", value: summary.errors ?? 0, label: "Unreadable" },
  ];

  // A zero count for a severity that did not occur is noise; a zero for
  // Critical is reassurance. Criticals and warnings therefore always show.
  const visible = tiles.filter(
    (tile) => tile.value > 0 || tile.key === "critical" || tile.key === "warning",
  );

  return (
    <div className="stats">
      {visible.map((tile) => (
        <div key={tile.key} className={`stat stat--${tile.key}`}>
          <span className="stat__value">{tile.value}</span>
          <span className="stat__label">{tile.label}</span>
        </div>
      ))}
    </div>
  );
}

function DegradedNotice({ meta }) {
  if (meta.llm_available) return null;

  return (
    <div className="notice notice--warn" role="status">
      <div className="notice__body">
        <strong>Explanations unavailable.</strong> The language model could not
        be reached, so results below show classification only. Severity,
        reference ranges and reasoning are computed locally and are unaffected.
        {meta.llm_error && (
          <code className="notice__detail">{meta.llm_error}</code>
        )}
      </div>
    </div>
  );
}

function RowErrors({ errors }) {
  if (!errors?.length) return null;

  return (
    <section className="row-errors">
      <h2 className="section__title">
        Rows that could not be read
        <span className="section__count">{errors.length}</span>
      </h2>
      <p className="section__hint">
        These rows were skipped. Every other row was still analyzed.
      </p>
      <ul className="row-errors__list">
        {errors.map((item, index) => (
          <li key={index} className="row-errors__item">
            {item.row != null && (
              <span className="row-errors__row">Row {item.row}</span>
            )}
            {item.test_name && (
              <span className="row-errors__test">{item.test_name}</span>
            )}
            <span className="row-errors__message">{item.error}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

export default function ResultsDisplay({ response }) {
  if (!response) return null;

  const { summary, results, errors, meta, patient_id: patientId } = response;

  // Preserve the server's ordering; only split it into labelled sections.
  const groups = SEVERITY_ORDER.map((severity) => ({
    severity,
    items: results.filter((r) => r.severity === severity),
  })).filter((group) => group.items.length > 0);

  return (
    <section className="results" aria-live="polite">
      <header className="results__header">
        <h2 className="results__title">
          Results
          {patientId && <span className="results__patient">{patientId}</span>}
        </h2>
        <span className="results__meta">
          {meta.llm_provider}
          {meta.llm_model ? ` · ${meta.llm_model}` : ""} ·{" "}
          {(meta.elapsed_ms / 1000).toFixed(1)}s
        </span>
      </header>

      <SummaryTiles summary={summary} />
      <DegradedNotice meta={meta} />

      {results.length === 0 && errors.length === 0 && (
        <p className="empty">No results to show.</p>
      )}

      {groups.map(({ severity, items }) => (
        <section key={severity} className="group">
          <h2 className={`section__title section__title--${severity}`}>
            <span aria-hidden="true">{SEVERITY_META[severity].icon}</span>
            {SEVERITY_META[severity].label}
            <span className="section__count">{items.length}</span>
          </h2>

          {severity === "unknown" && (
            <p className="section__hint">
              These could not be matched to a reference range or read as a
              number, so no classification was attempted.
            </p>
          )}

          <div className="group__cards">
            {items.map((result, index) => (
              <ResultCard key={`${result.test_name}-${index}`} result={result} />
            ))}
          </div>
        </section>
      ))}

      <RowErrors errors={errors} />

      <footer className="results__footer">
        Severity is determined by deterministic comparison against reference
        ranges via MCP tools. The language model writes the explanations only —
        it never decides whether a result is abnormal.
      </footer>
    </section>
  );
}
