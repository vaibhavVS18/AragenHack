import { useMemo, useState } from "react";

/**
 * ReferencePage - the clinical range table the classifier actually uses.
 *
 * Publishing the thresholds is part of the explainability requirement: a
 * reader who wants to check a verdict should be able to see the rule that
 * produced it, not just the verdict.
 *
 * Presented as a band strip per test rather than a row of numbers. A table of
 * `critical_low | low | high | critical_high` is complete but not legible - it
 * makes the reader reconstruct the shape of the range in their head. The strip
 * shows it directly, in the same colours as the gauge on a result card, so the
 * two read as one idea rather than two encodings of it.
 *
 * The table is fetched from the backend over MCP, so what is shown here is by
 * construction the same data used to classify.
 */

/**
 * Lay the five bands out as percentages of a shared scale.
 *
 * A missing critical threshold yields a zero-width band, which is then
 * dropped: it means "never critical on this side", and drawing a sliver there
 * would say the opposite.
 */
function bands(test) {
  const { low, high, critical_low: cl, critical_high: ch } = test;
  const span = high - low || Math.abs(high) || 1;

  const min = cl ?? low - span * 0.5;
  const max = ch ?? high + span * 0.5;
  const total = max - min || 1;
  const pct = (a, b) => Math.max(0, ((b - a) / total) * 100);

  return [
    { key: "cl", kind: "critical", width: cl != null ? pct(min, cl) : 0 },
    { key: "wl", kind: "warning", width: pct(cl ?? min, low) },
    { key: "n", kind: "normal", width: pct(low, high) },
    { key: "wh", kind: "warning", width: pct(high, ch ?? max) },
    { key: "ch", kind: "critical", width: ch != null ? pct(ch, max) : 0 },
  ].filter((band) => band.width > 0);
}

function TestRow({ test }) {
  const { critical_low: cl, critical_high: ch } = test;

  return (
    <article className="ref">
      <div className="ref__head">
        <h4 className="ref__name">{test.test_name}</h4>
        <span className="ref__unit">{test.unit}</span>
      </div>

      {test.measures && <p className="ref__measures">{test.measures}</p>}

      <div className="ref__strip" aria-hidden="true">
        {bands(test).map((band) => (
          <span
            key={band.key}
            className={`ref__band ref__band--${band.kind}`}
            style={{ width: `${band.width}%` }}
          />
        ))}
      </div>

      <div className="ref__scale">
        <span className="ref__mark ref__mark--critical">
          {cl != null ? `below ${cl}` : "no critical low"}
        </span>
        <span className="ref__mark ref__mark--normal">
          {test.low} – {test.high}
        </span>
        <span className="ref__mark ref__mark--critical">
          {ch != null ? `above ${ch}` : "no critical high"}
        </span>
      </div>

      {test.aliases?.length > 0 && (
        <p className="ref__aliases">
          <span>Also accepted as</span> {test.aliases.slice(0, 8).join(", ")}
        </p>
      )}
    </article>
  );
}

export default function ReferencePage({ catalogue }) {
  const [query, setQuery] = useState("");

  const grouped = useMemo(() => {
    const term = query.trim().toLowerCase();

    const matches = (test) =>
      !term ||
      test.test_name.toLowerCase().includes(term) ||
      (test.measures ?? "").toLowerCase().includes(term) ||
      (test.aliases ?? []).some((alias) => alias.includes(term));

    const byCategory = new Map();
    for (const test of catalogue.filter(matches)) {
      const list = byCategory.get(test.category) ?? [];
      list.push(test);
      byCategory.set(test.category, list);
    }
    return [...byCategory.entries()];
  }, [catalogue, query]);

  const total = catalogue.length;
  const shown = grouped.reduce((sum, [, tests]) => sum + tests.length, 0);

  return (
    <>
      <section className="band band--flush ground--paper">
        <h2 className="band__title">Every threshold, as the classifier sees it</h2>
        <p className="band__lede">
          Served from the MCP tool server — the same data used to classify, not
          a copy. A result that carries its own reference interval, as the
          Kaggle dataset does, is classified against that instead: a
          laboratory's own range is authoritative for its own result.
        </p>

        <div className="reference__controls">
          <input
            className="field"
            type="search"
            placeholder="Filter by name, alias or what it measures…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            aria-label="Filter tests"
          />
          <span className="reference__count">
            {shown} of {total} tests
          </span>
        </div>

        <div className="ref-key" aria-hidden="true">
          <span className="ref-key__item">
            <i className="ref__band--critical" /> Critical
          </span>
          <span className="ref-key__item">
            <i className="ref__band--warning" /> Warning
          </span>
          <span className="ref-key__item">
            <i className="ref__band--normal" /> Normal
          </span>
        </div>
      </section>

      {total === 0 && (
        <div className="empty-state">
          <p>Could not load the reference table. Is the backend running?</p>
        </div>
      )}

      {total > 0 && shown === 0 && (
        <div className="empty-state">
          <p>No test matches “{query}”.</p>
        </div>
      )}

      {grouped.map(([category, tests]) => (
        <section key={category} className="band ground--mist">
          <h3 className="section__title">
            {category}
            <span className="section__count">{tests.length}</span>
          </h3>

          <div className="ref-grid">
            {tests.map((test) => (
              <TestRow key={test.test_name} test={test} />
            ))}
          </div>
        </section>
      ))}

      <p className="reference__note">
        Boundaries are inclusive of Normal: a value exactly equal to the lower
        or upper limit is Normal. Where a test has no critical threshold on one
        side, a value beyond the range there is a Warning and never Critical —
        a very low creatinine, for instance, is not an emergency. Ranges are
        adult and sex-agnostic; see <code>docs/03-classification-logic.md</code>{" "}
        for the documented assumptions.
      </p>
    </>
  );
}
