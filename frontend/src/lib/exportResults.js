/**
 * Export an analysis for use outside the app.
 *
 * CSV, for a reader who wants the numbers in a spreadsheet. The printable
 * report covers the other case: something to hand to a doctor.
 *
 * Both keep the classification fields (`rule_fired`, the range, the range's
 * source), because an exported result that has lost its reasoning is exactly
 * the "just abnormal" output the explainability requirement rules out.
 */

/** Columns in the CSV export, in reading order. */
const COLUMNS = [
  ["test_name", "Test"],
  ["value", "Value"],
  ["unit", "Unit"],
  ["severity", "Severity"],
  ["reference", "Reference range"],
  ["range_source", "Range source"],
  ["deviation_text", "Deviation"],
  ["rule_fired", "Rule applied"],
  ["matched_by", "Name matched"],
  ["comparison", "Compared as"],
  ["explanation", "Explanation"],
  ["next_step", "Suggested next step"],
  ["what_result_means", "What the result means"],
  ["possible_causes", "Common causes"],
  ["urgency", "Urgency"],
  ["next_steps", "What to do"],
  ["questions_to_ask", "Questions for your doctor"],
  ["error", "Error"],
];

/** Quote a CSV field, doubling any embedded quotes. */
function escapeCell(value) {
  if (value == null) return "";
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
}

/**
 * Flatten a result into one row's worth of scalars.
 *
 * The explanation is a nested object with three list fields; a spreadsheet
 * cell holds neither, so lists are joined and the object is lifted onto the
 * row. The reasoning fields come along too - an export that has lost why a
 * result was flagged is exactly the "just abnormal" output this application
 * exists to avoid.
 */
function flattenResult(result) {
  const range = result.reference_range;
  const explanation = result.explanation_detail ?? {};
  const joinList = (items) => (items ?? []).join(" · ");

  return {
    ...result,
    reference: range ? `${range.low}-${range.high} ${range.unit ?? ""}`.trim() : "",
    what_result_means: explanation.what_result_means ?? "",
    possible_causes: joinList(explanation.possible_causes),
    urgency: explanation.urgency ?? "",
    next_steps: joinList(explanation.next_steps),
    questions_to_ask: joinList(explanation.questions_to_ask),
  };
}

/** Render the response as CSV text. */
export function toCSV(response) {
  const header = COLUMNS.map(([, label]) => label).join(",");

  const rows = response.results
    .map(flattenResult)
    .map((result) => COLUMNS.map(([key]) => escapeCell(result[key])).join(","));

  // Unreadable rows are part of the record: omitting them would make the
  // export look complete when it is not.
  const errorRows = (response.errors ?? []).map((error) =>
    COLUMNS.map(([key]) => {
      if (key === "test_name") return escapeCell(error.test_name ?? `(row ${error.row})`);
      if (key === "severity") return "unreadable";
      if (key === "error") return escapeCell(error.error);
      return "";
    }).join(","),
  );

  return [header, ...rows, ...errorRows].join("\r\n");
}

/**
 * Hand a file to the browser.
 *
 * The object URL is revoked on the next tick rather than immediately: some
 * browsers have not started reading the blob by the time click() returns.
 */
export function download(filename, text, mimeType) {
  const blob = new Blob([text], { type: `${mimeType};charset=utf-8` });
  const url = URL.createObjectURL(blob);

  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();

  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/** Timestamped filename stem, e.g. lab-results-2026-09-02T14-05. */
function stem(response) {
  const when = new Date().toISOString().slice(0, 16).replace(/[:T]/g, "-");
  const who = (response.patient_id ?? "results")
    .replace(/[^\w.-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 40);
  return `lab-${who || "results"}-${when}`;
}

export function downloadCSV(response) {
  download(`${stem(response)}.csv`, toCSV(response), "text/csv");
}
