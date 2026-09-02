/**
 * CsvPreview - what the server actually read from the file.
 *
 * Shown before analysis, not after. A CSV can upload successfully and still be
 * parsed wrongly - a column mapped to the wrong field, a decimal comma read as
 * a thousands separator - and finding that out after waiting for a full
 * analysis is a poor way to spend the user's time and an LLM call.
 *
 * The rows here come from the same parser the analysis endpoint uses, so the
 * preview cannot disagree with what analysing would do.
 */
export default function CsvPreview({ preview, loading, error }) {
  if (loading) {
    return (
      <div className="preview">
        <div className="preview__head">
          <span className="skeleton" style={{ width: "10rem", height: "0.9rem" }} />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="preview preview--error">
        <strong>This file could not be read.</strong>
        <p className="preview__message">{error.message}</p>
      </div>
    );
  }

  if (!preview) return null;

  const { row_count: rowCount, error_count: errorCount, labs, errors, patient_id: patientId } = preview;
  const shown = labs.slice(0, 8);
  const hidden = labs.length - shown.length;

  return (
    <div className="preview">
      <div className="preview__head">
        <span className="preview__summary">
          <strong>{rowCount}</strong> row{rowCount === 1 ? "" : "s"} ready
          {errorCount > 0 && (
            <span className="preview__errors">
              {" "}
              · {errorCount} unreadable
            </span>
          )}
          {patientId && <span className="preview__patient">{patientId}</span>}
        </span>
        <span className="preview__note">Parsed by the server — analysis has not run yet.</span>
      </div>

      {rowCount > 0 && (
        <div className="table-scroll preview__table">
          <table className="table">
            <thead>
              <tr>
                <th scope="col">Test</th>
                <th scope="col">Value</th>
                <th scope="col">Unit</th>
                <th scope="col">Reference from file</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((lab, index) => (
                <tr key={index}>
                  <th scope="row" className="table__name">{lab.test_name}</th>
                  <td className="table__num">{lab.value}</td>
                  <td className="table__num">{lab.unit ?? "—"}</td>
                  <td className="table__num">
                    {lab.reference_low != null && lab.reference_high != null
                      ? `${lab.reference_low} – ${lab.reference_high}`
                      : lab.reference_text ?? "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {hidden > 0 && (
        <p className="preview__more">and {hidden} more row{hidden === 1 ? "" : "s"}</p>
      )}

      {errors.length > 0 && (
        <ul className="preview__problems">
          {errors.slice(0, 5).map((item, index) => (
            <li key={index}>
              {item.row != null && <span className="row-errors__row">Row {item.row}</span>}{" "}
              {item.error}
            </li>
          ))}
          {errors.length > 5 && <li>and {errors.length - 5} more…</li>}
        </ul>
      )}
    </div>
  );
}
