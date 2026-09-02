/**
 * Turn an analysis response into the plain text the assistant reads.
 *
 * The assistant's answers must quote the reader's own numbers, so it is given
 * the report itself rather than a summary of it. What it is given is built
 * here, on the client, from the response already on screen: no second request,
 * and nothing in the prompt that the reader cannot also see.
 *
 * Three rules shape the format:
 *
 * 1. **Facts, not prose.** Each line is test, value, unit, severity, range and
 *    the rule that produced the severity. A small local model asked "why was
 *    this flagged?" can then restate a comparison instead of inventing one.
 * 2. **Already-ordered.** The backend routes by severity, so position carries
 *    meaning - "most urgent first" is true of the text as written, and the
 *    model does not have to work out an ordering of its own.
 * 3. **Bounded.** The backend caps the field at 6000 characters. A 40-row
 *    Kaggle file would blow past that, so rows are dropped from the least
 *    urgent end and the omission is stated rather than left silent.
 *
 * Every value here is copied from the response, never recomputed. The
 * deviation and the rule are the classifier's own words - a second
 * implementation of either in this file could disagree with the card the
 * reader is looking at, and then the assistant would too.
 */

const CHAR_BUDGET = 5600;

function line(result, position) {
  const {
    test_name: testName,
    value,
    unit,
    severity,
    reference_range: range,
    reference_text: referenceText,
    deviation_text: deviationText,
    rule_fired: ruleFired,
    next_step: nextStep,
    error,
  } = result;

  let head = `${position}. ${testName} = ${value ?? "not read"}`;
  if (unit) head += ` ${unit}`;
  head += ` - ${severity.toUpperCase()}`;

  const parts = [head];

  if (typeof range?.low === "number" && typeof range?.high === "number") {
    parts.push(
      `Normal range ${range.low}-${range.high}${range.unit ? ` ${range.unit}` : ""}`,
    );
  } else if (referenceText) {
    parts.push(`Expected: ${referenceText}`);
  }

  // The rule string is the whole reason this is trustworthy: it is the
  // comparison the MCP tool actually made, so an answer that repeats it is
  // repeating the classifier rather than guessing at one.
  if (ruleFired) parts.push(`Rule: ${ruleFired}`);
  if (deviationText) parts.push(deviationText);

  if (error) parts.push(`Could not be read: ${error}`);
  if (nextStep) parts.push(`Next step already given: ${nextStep}`);

  // Errors and next steps arrive as full sentences and bring their own stop;
  // the range and the rule do not. Trimming one before adding one covers both
  // without the caller having to know which is which.
  return `${parts.join(". ").replace(/\.\s*$/, "")}.`;
}

/**
 * Build the report text for a response, or null when there is nothing to send.
 *
 * @param {object|null} response - an /analyze response
 * @returns {string|null}
 */
export function buildReportDigest(response) {
  if (!response?.results?.length) return null;

  const { summary, results } = response;

  const head =
    "Results for this panel, most urgent first. " +
    `${summary.total} tested: ${summary.critical} critical, ` +
    `${summary.warning} warning, ${summary.normal} normal` +
    (summary.unknown ? `, ${summary.unknown} unreadable` : "") +
    ".";

  const lines = [];
  let used = head.length;

  for (const [index, result] of results.entries()) {
    const text = line(result, index + 1);

    if (used + text.length > CHAR_BUDGET) {
      const left = results.length - index;
      lines.push(
        `(${left} further result${left === 1 ? "" : "s"} omitted - ` +
          "they are the least urgent in this panel.)",
      );
      break;
    }

    lines.push(text);
    used += text.length + 1;
  }

  return [head, "", ...lines].join("\n");
}

/** A one-line description of the attached report, for the assistant header. */
export function describeReport(response) {
  if (!response?.results?.length) return null;

  const { total, critical, warning } = response.summary;
  const flagged = critical + warning;

  return (
    `${total} result${total === 1 ? "" : "s"}` +
    (flagged ? `, ${flagged} flagged` : ", none flagged")
  );
}
