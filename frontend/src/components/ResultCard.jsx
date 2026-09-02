import { useState } from "react";
import SeverityBadge from "./SeverityBadge";

/**
 * ResultCard - one lab result, fully explained.
 *
 * This component carries the assignment's key constraint: a user must
 * understand *why* a result was flagged, not just that it was. Each card
 * exposes, in the order the questions are asked:
 *
 *   1. the verdict           - badge and value, readable at a glance
 *   2. where the value sits  - a gauge showing every severity zone
 *   3. what it means         - the generated explanation, as a table
 *   4. how it was decided    - the literal comparison, collapsed by default
 *
 * Item 4 is the audit trail. It is hidden because most readers will not need
 * it, and always present because the ones who do should never have to trust
 * the interface.
 */

function formatNumber(n) {
  if (typeof n !== "number") return n;
  return Number.isInteger(n) ? String(n) : String(Number(n.toFixed(2)));
}

/**
 * Lay the five severity bands out on a shared 0-100 scale.
 *
 * Showing the whole gradient rather than only the normal band means the
 * distance between "just outside" and "critical" is visible, which is the
 * distinction that actually drives clinical urgency.
 */
function computeZones(value, range) {
  if (range == null || typeof value !== "number") return null;

  const { low, high, critical_low: criticalLow, critical_high: criticalHigh } = range;
  if (typeof low !== "number" || typeof high !== "number") return null;

  const span = high - low || Math.abs(high) || 1;

  // The scale spans the critical thresholds where they exist, and a
  // proportional margin where they do not.
  let min = criticalLow ?? low - span * 0.75;
  let max = criticalHigh ?? high + span * 0.75;

  // Keep the marker on screen when a value falls outside the critical bounds.
  const pad = (max - min) * 0.1 || 1;
  if (value < min) min = value - pad;
  if (value > max) max = value + pad;

  const total = max - min || 1;
  const pct = (from, to) => Math.max(0, ((to - from) / total) * 100);

  const zones = [];
  if (criticalLow != null && criticalLow > min) {
    zones.push({ key: "cl", kind: "critical", width: pct(min, criticalLow) });
  }
  zones.push({ key: "wl", kind: "warning", width: pct(Math.max(min, criticalLow ?? min), low) });
  zones.push({ key: "n", kind: "normal", width: pct(low, high) });
  zones.push({ key: "wh", kind: "warning", width: pct(high, Math.min(max, criticalHigh ?? max)) });
  if (criticalHigh != null && criticalHigh < max) {
    zones.push({ key: "ch", kind: "critical", width: pct(criticalHigh, max) });
  }

  return {
    min,
    max,
    zones: zones.filter((z) => z.width > 0),
    marker: Math.min(100, Math.max(0, ((value - min) / total) * 100)),
  };
}

function RangeGauge({ value, range, unit }) {
  const scale = computeZones(value, range);
  if (!scale) return null;

  const displayUnit = range.unit || unit || "";

  return (
    <div className="scale">
      <div
        className="scale__track"
        role="img"
        aria-label={`${formatNumber(value)} ${displayUnit}, against a normal range of ${formatNumber(range.low)} to ${formatNumber(range.high)}`}
      >
        {scale.zones.map((zone) => (
          <div
            key={zone.key}
            className={`scale__zone scale__zone--${zone.kind}`}
            style={{ width: `${zone.width}%` }}
          />
        ))}
        <div className="scale__marker" style={{ left: `${scale.marker}%` }} />
      </div>

      <div className="scale__labels">
        <span>{formatNumber(scale.min)}</span>
        <span className="scale__normal-label">
          normal {formatNumber(range.low)}–{formatNumber(range.high)}{" "}
          {displayUnit}
        </span>
        <span>{formatNumber(scale.max)}</span>
      </div>
    </div>
  );
}

const URGENCY = {
  emergency: { label: "Emergency", detail: "Seek medical attention today" },
  urgent: { label: "Urgent", detail: "Contact a doctor within a few days" },
  soon: { label: "Soon", detail: "Raise at your next appointment" },
  routine: { label: "Routine", detail: "No action beyond normal check-ups" },
};

/**
 * The generated explanation, laid out as a table.
 *
 * Each row answers one question a reader actually has. A paragraph of clinical
 * prose technically contains the same information, but it makes the reader
 * hunt for the part that applies to them - and the part they came for is
 * almost always "what do I do now", which is the hardest thing to find in
 * running text.
 *
 * Rows are omitted rather than shown empty: a normal result has no causes to
 * list and no questions to ask, and blank rows would imply something is
 * missing.
 *
 * Two rows are given a tinted ground: what the result means, and what to do
 * about it. Everything else on the card is context; those two are what the
 * reader came for, and in a six-row table of equal weight they were no easier
 * to find than the rest.
 */
function ExplanationTable({ explanation }) {
  const {
    headline,
    what_it_measures: whatItMeasures,
    what_result_means: whatResultMeans,
    possible_causes: causes,
    urgency,
    urgency_reason: urgencyReason,
    next_steps: nextSteps,
    questions_to_ask: questions,
  } = explanation;

  const urgencyMeta = URGENCY[urgency] ?? URGENCY.routine;

  return (
    <div className="explain">
      {headline && <p className="explain__headline">{headline}</p>}

      <table className="explain__table">
        <tbody>
          {whatItMeasures && (
            <tr>
              <th scope="row">What this test measures</th>
              <td>{whatItMeasures}</td>
            </tr>
          )}

          {whatResultMeans && (
            <tr className="explain__row--key">
              <th scope="row">What your result means</th>
              <td>{whatResultMeans}</td>
            </tr>
          )}

          {causes?.length > 0 && (
            <tr>
              <th scope="row">Common causes</th>
              <td>
                <ul className="explain__list">
                  {causes.map((cause, i) => (
                    <li key={i}>{cause}</li>
                  ))}
                </ul>
              </td>
            </tr>
          )}

          <tr>
            <th scope="row">How soon to act</th>
            <td>
              <span className={`urgency urgency--${urgency}`}>
                {urgencyMeta.label}
              </span>
              <span className="explain__urgency-detail">
                {urgencyReason || urgencyMeta.detail}
              </span>
            </td>
          </tr>

          {nextSteps?.length > 0 && (
            <tr className="explain__row--key">
              <th scope="row">What to do</th>
              <td>
                <ol className="explain__steps">
                  {nextSteps.map((step, i) => (
                    <li key={i}>{step}</li>
                  ))}
                </ol>
              </td>
            </tr>
          )}

          {questions?.length > 0 && (
            <tr>
              <th scope="row">Questions for your doctor</th>
              <td>
                <ul className="explain__list explain__list--quote">
                  {questions.map((question, i) => (
                    <li key={i}>{question}</li>
                  ))}
                </ul>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}


export default function ResultCard({ result }) {
  const [showReasoning, setShowReasoning] = useState(false);

  const {
    test_name: testName,
    value,
    unit,
    severity,
    reference_range: range,
    range_source: rangeSource,
    critical_basis: criticalBasis,
    comparison,
    deviation_text: deviationText,
    rule_fired: ruleFired,
    matched_by: matchedBy,
    unit_assumed: unitAssumed,
    explanation,
    next_step: nextStep,
    explanation_detail: detail,
    notes,
    error,
    category,
  } = result;

  const isQualitative = comparison === "qualitative";

  return (
    <article className={`card card--${severity}`}>
      <header className="card__header">
        <div className="card__identity">
          <h3 className="card__title">{testName}</h3>
          {category && <span className="card__category">{category}</span>}
        </div>
        <SeverityBadge severity={severity} />
      </header>

      <div className="card__measurement">
        <span className="card__value">{formatNumber(value)}</span>
        {unit && <span className="card__unit">{unit}</span>}
        {deviationText && <span className="card__deviation">{deviationText}</span>}
      </div>

      {!isQualitative && <RangeGauge value={value} range={range} unit={unit} />}

      {/* Data-quality caveats, shown prominently because they change how far
          the result should be trusted. */}
      {notes && <p className="card__note">{notes}</p>}
      {error && <p className="card__error">{error}</p>}
      {unitAssumed && !error && range?.unit && (
        <p className="card__note card__note--subtle">
          No unit was provided; {range.unit} was assumed.
        </p>
      )}

      {detail && <ExplanationTable explanation={detail} />}

      {/* No detail: either the row could not be interpreted, or the model was
          unavailable. Both cases get the one-line reason and the one action
          that resolves it - a full explanation table here would be six fields
          restating "this could not be read".

          An uninterpretable row's explanation *is* its error, already printed
          above as card__error. Printing it again under a heading made the card
          say the same sentence twice and made it look like the AI had written
          an explanation for a row it never saw, so only the action is shown. */}
      {!detail && (explanation || nextStep) && (
        <div className="card__brief">
          {explanation && explanation !== error && (
            <p className="card__text">{explanation}</p>
          )}
          {nextStep && (
            <p className="card__brief-action">
              <span className="card__label">What to do</span>
              {nextStep}
            </p>
          )}
        </div>
      )}

      {ruleFired && (
        <div className="card__reasoning">
          <button
            type="button"
            className="card__toggle"
            onClick={() => setShowReasoning((open) => !open)}
            aria-expanded={showReasoning}
          >
            <span aria-hidden="true">{showReasoning ? "▾" : "▸"}</span>
            How this was classified
          </button>

          {showReasoning && (
            <dl className="reasoning">
              <dt>Rule applied</dt>
              <dd>
                <code>{ruleFired}</code>
              </dd>

              {range && (
                <>
                  <dt>Reference range</dt>
                  <dd>
                    {formatNumber(range.low)}–{formatNumber(range.high)}{" "}
                    {range.unit}
                    {range.critical_low != null &&
                      ` · critical below ${formatNumber(range.critical_low)}`}
                    {range.critical_high != null &&
                      ` · critical above ${formatNumber(range.critical_high)}`}
                  </dd>
                </>
              )}

              <dt>Range source</dt>
              <dd>
                {rangeSource === "supplied" &&
                  "The reference interval supplied with this result, which takes precedence over the built-in table."}
                {rangeSource === "internal" &&
                  "The application's built-in clinical reference table."}
                {!rangeSource && "No reference interval was available."}
              </dd>

              {criticalBasis && criticalBasis !== "none" && (
                <>
                  <dt>Critical thresholds</dt>
                  <dd>
                    {criticalBasis === "table"
                      ? "Published panic values from the built-in table."
                      : "Estimated from the width of the supplied interval — indicative, not a published panic value."}
                  </dd>
                </>
              )}

              <dt>Compared as</dt>
              <dd>
                {isQualitative
                  ? "A word result (present / absent), matched against the expected result. Strips record presence, not amount."
                  : "A number, against a reference interval."}
              </dd>

              <dt>Test name matched</dt>
              <dd>
                {matchedBy === "exact" && "exactly"}
                {matchedBy === "alias" && "by a known alias or abbreviation"}
                {matchedBy === "fuzzy" &&
                  "approximately — verify this is correct"}
                {!matchedBy && "not matched to a test in the built-in table"}
              </dd>

              <dt>Decided by</dt>
              <dd>
                Deterministic threshold comparison, not the language model. The
                explanation above was written afterwards from this result.
              </dd>
            </dl>
          )}
        </div>
      )}
    </article>
  );
}
