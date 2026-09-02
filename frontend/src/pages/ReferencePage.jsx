import { useMemo, useState } from "react";

/**
 * ReferencePage - the clinical range table the classifier actually uses.
 *
 * Publishing the thresholds is part of the explainability requirement: a user
 * who wants to check a verdict should be able to see the rule that produced
 * it, not just the verdict.
 *
 * The table is fetched from the backend over MCP, so what is shown here is by
 * construction the same data used to classify.
 */
export default function ReferencePage({ catalogue }) {
  const [query, setQuery] = useState("");

  const grouped = useMemo(() => {
    const term = query.trim().toLowerCase();

    const matches = (test) =>
      !term ||
      test.test_name.toLowerCase().includes(term) ||
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
      <div className="reference__controls">
        <input
          className="field"
          type="search"
          placeholder="Filter by name or alias, e.g. HGB, trombosit"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Filter tests"
        />
        <span className="reference__count">
          {shown} of {total} tests
        </span>
      </div>

      {total === 0 && (
        <div className="empty-state">
          <p>Could not load the reference table. Is the backend running?</p>
        </div>
      )}

      {grouped.map(([category, tests]) => (
        <section key={category} className="reference__group">
          <h3 className="section__title">{category}</h3>

          <div className="table-scroll">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">Test</th>
                  <th scope="col">Unit</th>
                  <th scope="col">Critical low</th>
                  <th scope="col">Normal</th>
                  <th scope="col">Critical high</th>
                  <th scope="col">Also accepted as</th>
                </tr>
              </thead>
              <tbody>
                {tests.map((test) => (
                  <tr key={test.test_name}>
                    <th scope="row" className="table__name">
                      {test.test_name}
                      <span className="table__measures">{test.measures}</span>
                    </th>
                    <td className="table__num">{test.unit}</td>
                    <td className="table__num table__num--critical">
                      {test.critical_low ?? "—"}
                    </td>
                    <td className="table__num table__num--normal">
                      {test.low} – {test.high}
                    </td>
                    <td className="table__num table__num--critical">
                      {test.critical_high ?? "—"}
                    </td>
                    <td className="table__aliases">
                      {(test.aliases ?? []).slice(0, 6).join(", ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <p className="reference__note">
        A dash means that side has no critical band — a very low creatinine, for
        instance, is not an emergency. Ranges are adult and sex-agnostic; see
        <code> docs/03-classification-logic.md</code> for the full list of
        documented assumptions.
      </p>
    </>
  );
}
