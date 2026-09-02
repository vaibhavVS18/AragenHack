import { useMemo, useRef, useState } from "react";

import CsvPreview from "./CsvPreview";
import TestNameInput from "./TestNameInput";
import { previewCsv } from "../api/client";

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
 * There is no patient field. A CSV that carries a patient column still has it
 * read and echoed back, and a bundled dataset is labelled by its name - but
 * asking someone to type one in added a step to every single analysis for a
 * value almost none of them wanted to set.
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
  const [dragging, setDragging] = useState(false);
  const [preview, setPreview] = useState(null);
  const [previewing, setPreviewing] = useState(false);
  const [previewError, setPreviewError] = useState(null);
  const fileInputRef = useRef(null);

  // Look up the canonical unit so it can be filled in automatically. Keyed by
  // name and by alias, so a name the catalogue accepts under either spelling
  // is recognised here too - and so this map doubles as the set of names that
  // are allowed to be submitted.
  const unitByTest = useMemo(() => {
    const map = new Map();
    (catalogue ?? []).forEach((test) => {
      map.set(test.test_name.toLowerCase(), test.unit);
      (test.aliases ?? []).forEach((alias) => map.set(alias, test.unit));
    });
    return map;
  }, [catalogue]);

  /**
   * Whether a typed name is one the server can actually classify.
   *
   * Empty is not invalid - a blank row is scaffolding for the next entry, not
   * a mistake. And while the catalogue is still loading nothing is rejected,
   * because at that moment every name would look wrong.
   */
  function isKnown(name) {
    const key = name.trim().toLowerCase();
    if (!key || unitByTest.size === 0) return true;
    return unitByTest.has(key);
  }

  function updateRow(index, field, value, chosen) {
    setRows((current) => {
      const next = current.map((row, i) =>
        i === index ? { ...row, [field]: value } : row,
      );

      if (field === "test_name") {
        if (chosen) {
          // Picked from the list: an explicit choice of test, so its unit
          // replaces whatever was there. Only filling an empty unit left the
          // previous test's unit behind when the name was changed - pick
          // Hemoglobin then switch to Potassium and the row still said g/dL.
          next[index].unit = chosen.unit;
        } else {
          // Typed freely: suggest a unit, but never overwrite one the user
          // entered themselves.
          const unit = unitByTest.get(value.trim().toLowerCase());
          if (unit && !next[index].unit) next[index].unit = unit;
        }
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

  /**
   * Take a file and immediately ask the server what it parses to.
   *
   * Previewing costs one cheap request and no LLM call, so it runs on every
   * selection rather than behind a button - a mis-mapped column should be
   * visible straight away, not after a full analysis.
   */
  async function selectFile(chosen) {
    setFile(chosen);
    setPreview(null);
    setPreviewError(null);
    if (!chosen) return;

    setPreviewing(true);
    try {
      setPreview(await previewCsv(chosen));
    } catch (err) {
      setPreviewError(err);
    } finally {
      setPreviewing(false);
    }
  }

  function clearAll() {
    setRows([{ ...EMPTY_ROW }]);
    setFile(null);
    setPreview(null);
    setPreviewError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  // Rows with a name and a value are the ones worth submitting; blanks are
  // scaffolding for the next entry, not errors.
  const filledRows = rows.filter(
    (row) => row.test_name.trim() && String(row.value).trim(),
  );

  // A name outside the catalogue cannot produce a classification, so it is
  // stopped here rather than spending an analysis to come back as "unknown".
  const badNames = rows.filter(
    (row) => row.test_name.trim() && !isKnown(row.test_name),
  );

  const canSubmit = loading
    ? false
    : mode === "form"
      ? filledRows.length > 0 && badNames.length === 0
      : file != null && !previewing && !previewError;

  function handleSubmit(event) {
    event.preventDefault();
    if (!canSubmit) return;

    if (mode === "form") {
      onAnalyze({
        kind: "form",
        labs: filledRows.map((row) => ({
          test_name: row.test_name.trim(),
          value: String(row.value).trim(),
          unit: row.unit.trim() || null,
        })),
      });
    } else {
      onAnalyze({ kind: "csv", file });
    }
  }

  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files?.[0];
    if (dropped) selectFile(dropped);
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
              <TestNameInput
                value={row.test_name}
                onChange={(name, test) => updateRow(index, "test_name", name, test)}
                catalogue={catalogue}
                rowIndex={index}
                invalid={!isKnown(row.test_name)}
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
        <>
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
            onChange={(e) => selectFile(e.target.files?.[0] ?? null)}
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
          <CsvPreview preview={preview} loading={previewing} error={previewError} />
        </>
      )}

      <div className="input__footer">
        <button type="submit" className="btn btn--primary" disabled={!canSubmit}>
          {loading ? "Analyzing…" : "Analyze results"}
        </button>
      </div>

      {mode === "form" && badNames.length > 0 && (
        <p className="input__count input__count--warn">
          {badNames.length === 1
            ? `"${badNames[0].test_name.trim()}" is not a test this can classify.`
            : `${badNames.length} test names are not ones this can classify.`}{" "}
          Choose from the list to continue.
        </p>
      )}

      {mode === "form" && badNames.length === 0 && filledRows.length > 0 && (
        <p className="input__count">
          {filledRows.length} result{filledRows.length === 1 ? "" : "s"} ready
        </p>
      )}
    </form>
  );
}
