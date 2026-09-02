import { useMemo, useState } from "react";

import ResultCard from "./ResultCard";
import { SEVERITY_META, SEVERITY_ORDER } from "./severity";
import { downloadCSV } from "../lib/exportResults";
import { downloadReport } from "../api/client";

/**
 * ResultsDisplay - renders the agent's response.
 *
 * Laid out as three bands, because they carry different kinds of information:
 *
 *   paper - the triage summary. Counts and filters, the thing read first.
 *   mist  - the results themselves, grouped by severity.
 *   paper - rows that could not be read, kept visually apart from verdicts.
 *
 * Results arrive already ordered by the backend's Route step, so this
 * component groups them without re-sorting. Ordering is a clinical decision
 * and belongs on the server, beside the rules that produced it.
 *
 * Filtering is a view concern: it never changes what was analyzed, and the
 * counts always describe the full response, so a hidden critical result can
 * never look like an absent one.
 */

/**
 * The bottom line, in one sentence.
 *
 * A reader who has just submitted results wants to know whether anything is
 * wrong before they want anything else. Counts alone do not say that - "1
 * Critical" is a number, not an answer - so the verdict is stated in words
 * first and the tiles support it.
 *
 * Worded from the reader's side. Internal vocabulary (classify, route, triage,
 * MCP) does not belong on this screen.
 */
function Verdict({ summary, topResult }) {
  const { critical = 0, warning = 0, normal = 0, unknown = 0, total = 0 } = summary;

  if (total === 0) return null;

  let tone = "normal";
  let line;
  let detail = null;

  if (critical > 0) {
    tone = "critical";
    line =
      critical === 1
        ? "One result needs urgent attention."
        : `${critical} results need urgent attention.`;
    if (topResult) {
      detail = `Start with ${topResult.test_name} — it is furthest outside its normal range.`;
    }
  } else if (warning > 0) {
    tone = "warning";
    line =
      warning === 1
        ? "One result is outside the normal range."
        : `${warning} results are outside the normal range.`;
    detail = "Nothing here is an emergency, but these are worth following up.";
  } else if (normal > 0) {
    line =
      normal === 1
        ? "This result is within the normal range."
        : `All ${normal} results are within their normal ranges.`;
    detail = "No action needed beyond your usual check-ups.";
  } else {
    tone = "unknown";
    line = "None of these results could be interpreted.";
    detail = "Check the test names, values and units, then try again.";
  }

  return (
    <div className={`verdict verdict--${tone}`}>
      <p className="verdict__line">{line}</p>
      {detail && <p className="verdict__detail">{detail}</p>}
      {unknown > 0 && critical + warning + normal > 0 && (
        <p className="verdict__detail">
          {unknown === 1 ? "One entry" : `${unknown} entries`} could not be
          interpreted and {unknown === 1 ? "is" : "are"} listed separately below.
        </p>
      )}
    </div>
  );
}


/**
 * SeveritySummary - the shape of the panel, then the counts.
 *
 * A row of bare numbers made the reader do the arithmetic: "2" and "5" and
 * "3" say nothing about whether this panel is mostly fine or mostly alarming.
 * A single proportional bar answers that before any number is read, and the
 * legend underneath carries the exact counts for anyone who wants them.
 *
 * Each legend entry is also the severity filter, so the thing that describes
 * the panel is the thing that narrows it.
 */
function SeveritySummary({ summary, active, onToggle }) {
  const total = SEVERITY_ORDER.reduce((sum, s) => sum + (summary[s] ?? 0), 0);

  const bands = SEVERITY_ORDER.map((severity) => ({
    severity,
    count: summary[severity] ?? 0,
    label: SEVERITY_META[severity].label,
    icon: SEVERITY_META[severity].icon,
  }));

  // Critical and Warning always show, even at zero: an absent row is
  // ambiguous, whereas "Critical — none" is reassurance.
  const legend = bands.filter(
    (b) => b.count > 0 || b.severity === "critical" || b.severity === "warning",
  );

  return (
    <div className="severity">
      {total > 0 && (
        <div
          className="severity__bar"
          role="img"
          aria-label={bands
            .filter((b) => b.count > 0)
            .map((b) => `${b.count} ${b.label}`)
            .join(", ")}
        >
          {bands
            .filter((b) => b.count > 0)
            .map((b) => (
              <span
                key={b.severity}
                className={`severity__seg severity__seg--${b.severity}`}
                style={{ width: `${(b.count / total) * 100}%` }}
                title={`${b.count} ${b.label}`}
              />
            ))}
        </div>
      )}

      <div className="severity__legend">
        {legend.map((band) => {
          const isActive = active.has(band.severity);
          const isEmpty = band.count === 0;

          return (
            <button
              key={band.severity}
              type="button"
              className={`sev-item sev-item--${band.severity} ${
                isActive ? "sev-item--active" : ""
              } ${isEmpty ? "sev-item--empty" : ""}`}
              onClick={() => !isEmpty && onToggle(band.severity)}
              disabled={isEmpty}
              aria-pressed={isActive}
              title={isEmpty ? undefined : `Show only ${band.label}`}
            >
              <span className="sev-item__dot" aria-hidden="true" />
              <span className="sev-item__label">{band.label}</span>
              <span className="sev-item__count">
                {isEmpty ? "none" : band.count}
              </span>
            </button>
          );
        })}

        {summary.errors > 0 && (
          <span className="sev-item sev-item--unknown sev-item--static">
            <span className="sev-item__dot" aria-hidden="true" />
            <span className="sev-item__label">Unreadable</span>
            <span className="sev-item__count">{summary.errors}</span>
          </span>
        )}
      </div>
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
    <section className="band ground--paper">
      <h2 className="band__title">Entries we could not read</h2>
      <p className="band__lede">
        These were skipped — everything else was still checked. Usually a
        missing value, a blank test name, or a test we do not have a reference
        range for.
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

export default function ResultsDisplay({ response, onAskAboutReport }) {
  const [severityFilter, setSeverityFilter] = useState(new Set());
  const [query, setQuery] = useState("");
  const [building, setBuilding] = useState(false);
  const [reportError, setReportError] = useState(null);

  const visible = useMemo(() => {
    if (!response) return [];
    const term = query.trim().toLowerCase();

    return response.results.filter((result) => {
      if (severityFilter.size && !severityFilter.has(result.severity)) return false;
      if (!term) return true;
      return (
        result.test_name.toLowerCase().includes(term) ||
        (result.category ?? "").toLowerCase().includes(term) ||
        (result.explanation ?? "").toLowerCase().includes(term)
      );
    });
  }, [response, severityFilter, query]);

  if (!response) return null;

  const { summary, results, errors, meta, patient_id: patientId } = response;

  const groups = SEVERITY_ORDER.map((severity) => ({
    severity,
    items: visible.filter((r) => r.severity === severity),
  })).filter((group) => group.items.length > 0);

  const filtering = severityFilter.size > 0 || query.trim() !== "";

  function toggleSeverity(severity) {
    setSeverityFilter((current) => {
      const next = new Set(current);
      if (next.has(severity)) next.delete(severity);
      else next.add(severity);
      return next;
    });
  }

  function clearFilters() {
    setSeverityFilter(new Set());
    setQuery("");
  }

  async function handleDownloadReport() {
    setBuilding(true);
    setReportError(null);
    try {
      await downloadReport(response);
    } catch (err) {
      setReportError(err);
    } finally {
      setBuilding(false);
    }
  }

  return (
    <div className="results" aria-live="polite">
      {/* ---- 02 · triage summary ---- */}
      <section className="band ground--paper">
        <div className="results__header">
          <h2 className="band__title">
            Your results
            {patientId && <span className="results__patient">{patientId}</span>}
          </h2>

        </div>

        {reportError && (
          <div className="notice notice--error" role="alert">
            <div className="notice__body">
              <strong>{reportError.message}</strong>
              {reportError.hint && (
                <p className="notice__hint">{reportError.hint}</p>
              )}
            </div>
          </div>
        )}

        <Verdict summary={summary} topResult={results[0]} />

        <SeveritySummary
          summary={summary}
          active={severityFilter}
          onToggle={toggleSeverity}
        />

        <div className="actions">
          <div className="actions__text">
            <strong>Take this with you.</strong> The report includes every
            result, what it means, and what to do next — laid out to hand to a
            doctor.
          </div>
          <div className="actions__buttons">
            <button
              type="button"
              className="btn btn--ghost"
              onClick={() => downloadCSV(response)}
            >
              Export CSV
            </button>
            <button
              type="button"
              className="btn btn--primary btn--lg"
              onClick={handleDownloadReport}
              disabled={building}
            >
              {building ? "Building report…" : "Download PDF report"}
            </button>
          </div>
        </div>

        {results.length > 3 && (
          <div className="filters">
            <input
              className="field"
              type="search"
              placeholder="Filter by test, category or explanation…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              aria-label="Filter results"
            />
            {filtering && (
              <>
                <span className="filters__count">
                  {visible.length} of {results.length} shown
                </span>
                <button
                  type="button"
                  className="btn btn--ghost btn--sm"
                  onClick={clearFilters}
                >
                  Clear filters
                </button>
              </>
            )}
          </div>
        )}

        <DegradedNotice meta={meta} />
      </section>

      {/* ---- 03 · the results themselves ---- */}
      <section className="band ground--mist">
        {results.length === 0 && errors.length === 0 && (
          <p className="empty">No results to show.</p>
        )}

        {results.length > 0 && visible.length === 0 && (
          <p className="empty">
            Nothing matches those filters.{" "}
            <button type="button" className="link-btn" onClick={clearFilters}>
              Clear them
            </button>
            .
          </p>
        )}

        {groups.map(({ severity, items }) => (
            <section key={severity} className="group">
              <h3 className={`section__title section__title--${severity}`}>
                <span aria-hidden="true">{SEVERITY_META[severity].icon}</span>
                {SEVERITY_META[severity].label}
                <span className="section__count">{items.length}</span>
              </h3>

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

        {/* Placed after the explanations, not beside the download buttons: a
            question about a result only forms once the result has been read,
            and this is where the reading ends. */}
        {onAskAboutReport && visible.length > 0 && (
          <div className="ask-report">
            <div className="ask-report__text">
              <strong>Still unclear?</strong> Ask about these results in your own
              words — which one matters most, why it was flagged, how far out it
              is. The assistant answers from this report.
            </div>
            <button
              type="button"
              className="btn btn--primary ask-report__btn"
              onClick={onAskAboutReport}
            >
              Ask about your report
            </button>
          </div>
        )}
      </section>

      {/* ---- 04 · rows that failed to parse ---- */}
      <RowErrors errors={errors} />

    </div>
  );
}
