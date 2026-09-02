import { useMemo, useRef, useState } from "react";

/**
 * LabInput - how lab results get into the app.
 *
 * Two input modes, both accepted by the assignment:
 *   1. Manual entry - editable rows of { test_name, value, unit }
 *   2. CSV upload   - a file from /test_data or the Kaggle dataset
 *
 * This component owns input state only. It hands a payload to App and never
 * calls the API or interprets results itself, so the analysis flow lives in
 * exactly one place.
 *
 * The test catalogue is fetched from the backend rather than hardcoded here.
 * Duplicating it in the UI would let the two drift, and the UI would then
 * suggest tests the server cannot actually classify.
 */

const EMPTY_ROW = { test_name: "", value: "", unit: "" };

const SAMPLE_ROWS = [
  { test_name: "Hemoglobin", value: "6.1", unit: "g/dL" },
  { test_name: "Potassium", value: "6.9", unit: "mEq/L" },
  { test_name: "Glucose", value: "92", unit: "mg/dL" },
  { test_name: "Creatinine", value: "2.1", unit: "mg/dL" },
];

export default function LabInput({ onAnalyze, loading, catalogue }) {
  const [mode, setMode] = useState("form");
  const [rows, setRows] = useState([{ ...EMPTY_ROW }]);
  const [file, setFile] = useState(null);
  const [patientId, setPatientId] = useState("");
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef(null);

  // Look up the canonical unit so it can be filled in automatically.
  const unitByTest = useMemo(() => {
    const map = new Map();
    (catalogue ?? []).forEach((test) => {
      map.set(test.test_name.toLowerCase(), test.unit);
      (test.aliases ?? []).forEach((alias) => map.set(alias, test.unit));
    });
    return map;
  }, [catalogue]);

  function updateRow(index, field, value) {
    setRows((current) => {
      const next = current.map((row, i) =>
        i === index ? { ...row, [field]: value } : row,
      );

      // Filling in a recognised test name suggests its unit, but never
      // overwrites a unit the user typed themselves.
      if (field === "test_name") {
        const unit = unitByTest.get(value.trim().toLowerCase());
        if (unit && !next[index].unit) next[index].unit = unit;
      }
      return next;
    });
  }

  function addRow() {
    setRows((current) => [...current, { ...EMPTY_ROW }]);
  }

  function removeRow(index) {
    setRows((current) =>
      current.length === 1 ? [{ ...EMPTY_ROW }] : current.filter((_, i) => i !== index),
    );
  }

  function loadSample() {
    setRows(SAMPLE_ROWS.map((row) => ({ ...row })));
  }

  function clearAll() {
    setRows([{ ...EMPTY_ROW }]);
    setFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  // Rows with a name and a value are the ones worth submitting; blanks are
  // scaffolding for the next entry, not errors.
  const filledRows = rows.filter(
    (row) => row.test_name.trim() && String(row.value).trim(),
  );

  const canSubmit = loading
    ? false
    : mode === "form"
      ? filledRows.length > 0
      : file != null;

  function handleSubmit(event) {
    event.preventDefault();
    if (!canSubmit) return;

    if (mode === "form") {
      onAnalyze({
        kind: "form",
        patientId: patientId.trim() || null,
        labs: filledRows.map((row) => ({
          test_name: row.test_name.trim(),
          value: String(row.value).trim(),
          unit: row.unit.trim() || null,
        })),
      });
    } else {
      onAnalyze({ kind: "csv", patientId: patientId.trim() || null, file });
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) setFile(dropped);
  }

  return (
    <form className="input" onSubmit={handleSubmit}>
      <div className="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={mode === "form"}
          className={`tab ${mode === "form" ? "tab--active" : ""}`}
          onClick={() => setMode("form")}
        >
          Enter results
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={mode === "csv"}
          className={`tab ${mode === "csv" ? "tab--active" : ""}`}
          onClick={() => setMode("csv")}
        >
          Upload CSV
        </button>
      </div>

      {mode === "form" ? (
        <div className="rows">
          <div className="rows__head">
            <span>Test name</span>
            <span>Value</span>
            <span>Unit</span>
            <span className="sr-only">Remove</span>
          </div>

          {rows.map((row, index) => (
            <div className="row" key={index}>
              <input
                className="field"
                list="known-tests"
                placeholder="e.g. Hemoglobin"
                value={row.test_name}
                onChange={(e) => updateRow(index, "test_name", e.target.value)}
                aria-label={`Test name, row ${index + 1}`}
              />
              <input
                className="field"
                placeholder="e.g. 13.5"
                value={row.value}
                onChange={(e) => updateRow(index, "value", e.target.value)}
                aria-label={`Value, row ${index + 1}`}
              />
              <input
                className="field"
                placeholder="e.g. g/dL"
                value={row.unit}
                onChange={(e) => updateRow(index, "unit", e.target.value)}
                aria-label={`Unit, row ${index + 1}`}
              />
              <button
                type="button"
                className="row__remove"
                onClick={() => removeRow(index)}
                aria-label={`Remove row ${index + 1}`}
                title="Remove row"
              >
                ×
              </button>
            </div>
          ))}

          <datalist id="known-tests">
            {(catalogue ?? []).map((test) => (
              <option key={test.test_name} value={test.test_name}>
                {test.low}–{test.high} {test.unit}
              </option>
            ))}
          </datalist>

          <div className="rows__actions">
            <button type="button" className="btn btn--ghost" onClick={addRow}>
              + Add row
            </button>
            <button type="button" className="btn btn--ghost" onClick={loadSample}>
              Load sample
            </button>
            <button type="button" className="btn btn--ghost" onClick={clearAll}>
              Clear
            </button>
          </div>
        </div>
      ) : (
        <div
          className={`drop ${dragging ? "drop--active" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={handleDrop}
        >
          <input
            ref={fileInputRef}
            id="csv-file"
            type="file"
            accept=".csv,text/csv"
            className="sr-only"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <label htmlFor="csv-file" className="drop__label">
            {file ? (
              <>
                <strong>{file.name}</strong>
                <span className="drop__hint">
                  {(file.size / 1024).toFixed(1)} KB · click to choose another
                </span>
              </>
            ) : (
              <>
                <strong>Drop a CSV here, or click to browse</strong>
                <span className="drop__hint">
                  Columns: test_name, value, unit — samples in /test_data
                </span>
              </>
            )}
          </label>
        </div>
      )}

      <div className="input__footer">
        <input
          className="field field--patient"
          placeholder="Patient ID (optional)"
          value={patientId}
          onChange={(e) => setPatientId(e.target.value)}
          aria-label="Patient ID"
        />
        <button type="submit" className="btn btn--primary" disabled={!canSubmit}>
          {loading ? "Analyzing…" : "Analyze results"}
        </button>
      </div>

      {mode === "form" && filledRows.length > 0 && (
        <p className="input__count">
          {filledRows.length} result{filledRows.length === 1 ? "" : "s"} ready
        </p>
      )}
    </form>
  );
}
