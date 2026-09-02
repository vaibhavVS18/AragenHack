/**
 * The single place that knows how to talk to the FastAPI backend.
 *
 * Components never call fetch directly. Keeping URLs, headers and error
 * translation here means a change to the API surface touches one file, and
 * every component receives errors in the same shape.
 */

export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

/**
 * An error carrying enough context for the UI to say something useful.
 *
 * `status` is null when the request never reached the server, which is the
 * common case in development (backend not started yet) and deserves different
 * advice than a 500.
 */
export class ApiError extends Error {
  constructor(message, { status = null, hint = null, detail = null } = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.hint = hint;
    this.detail = detail;
  }
}

/** Turn FastAPI's several error shapes into one readable message. */
function extractMessage(body, status) {
  if (!body) return `Request failed (HTTP ${status}).`;

  const { detail } = body;

  // 422 from Pydantic: detail is an array of per-field errors.
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = (item.loc ?? []).filter((p) => p !== "body").join(".");
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("; ");
  }

  if (typeof detail === "string") return detail;
  return `Request failed (HTTP ${status}).`;
}

async function request(path, options = {}) {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, options);
  } catch (cause) {
    // Network-level failure: no response at all.
    throw new ApiError("Could not reach the backend.", {
      hint: `Is the API running at ${API_BASE_URL}? Start it with: uvicorn app.main:app --reload --port 8000`,
      detail: cause.message,
    });
  }

  let body = null;
  try {
    body = await response.json();
  } catch {
    // Some error responses have no JSON body; that is not itself fatal.
  }

  if (!response.ok) {
    throw new ApiError(extractMessage(body, response.status), {
      status: response.status,
      hint: body?.hint ?? null,
      detail: body?.error ?? null,
    });
  }

  return body;
}

/**
 * Analyze lab results submitted as JSON.
 *
 * @param {Array<{test_name: string, value: string|number, unit?: string}>} labs
 * @param {string|null} patientId
 * @returns {Promise<object>} The AnalyzeResponse payload.
 */
export function analyzeLabs(labs, patientId = null) {
  return request("/analyze_labs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      patient_id: patientId || null,
      labs,
    }),
  });
}

/**
 * Analyze lab results from an uploaded CSV file.
 *
 * @param {File} file
 * @param {string|null} patientId Overrides any patient column in the file.
 */
export function analyzeLabsCsv(file, patientId = null) {
  const form = new FormData();
  form.append("file", file);
  if (patientId) form.append("patient_id", patientId);

  // No Content-Type header: the browser must set the multipart boundary.
  return request("/analyze_labs/csv", { method: "POST", body: form });
}

/**
 * Analyze one of the sample datasets bundled with the repository.
 *
 * @param {string} datasetId Id from `listDatasets`, e.g. "kaggle".
 */
export function analyzeDataset(datasetId) {
  return request(`/analyze_labs/dataset/${encodeURIComponent(datasetId)}`, {
    method: "POST",
  });
}

/**
 * Parse a CSV without classifying it or calling the LLM.
 *
 * Used to show the user what was actually read from their file before they
 * commit to an analysis.
 *
 * @param {File} file
 */
export function previewCsv(file) {
  const form = new FormData();
  form.append("file", file);
  return request("/preview_csv", { method: "POST", body: form });
}

/** List the bundled sample datasets and whether each file is present. */
export function listDatasets() {
  return request("/datasets");
}

/**
 * Fetch the clinical reference table.
 *
 * Comes from the MCP tool server, so the UI never hardcodes a catalogue that
 * could drift from the one actually used to classify.
 */
export function getReferenceRanges() {
  return request("/reference_ranges");
}

/**
 * Render an analysis as a PDF and hand it to the browser.
 *
 * The already-computed response is posted back rather than the original
 * request, so producing a report costs no second analysis and no further LLM
 * call. The PDF is built server-side with real table primitives - a print
 * stylesheet cannot do measured columns, row-aware page breaks or page
 * numbering reliably.
 *
 * @param {object} response The AnalyzeResponse to render.
 */
export async function downloadReport(response) {
  let res;
  try {
    res = await fetch(`${API_BASE_URL}/report`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(response),
    });
  } catch (cause) {
    throw new ApiError("Could not reach the backend to build the report.", {
      hint: `Is the API running at ${API_BASE_URL}?`,
      detail: cause.message,
    });
  }

  if (!res.ok) {
    let body = null;
    try {
      body = await res.json();
    } catch {
      // A failed PDF response may not carry JSON.
    }
    throw new ApiError(extractMessage(body, res.status), { status: res.status });
  }

  // The filename the server chose, so the browser tab and the saved file agree.
  const disposition = res.headers.get("Content-Disposition") ?? "";
  const match = /filename="?([^"]+)"?/.exec(disposition);
  const filename = match?.[1] ?? "aragen-lab-report.pdf";

  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}

/**
 * Ask the assistant a question about the application.
 *
 * Answers come from the indexed documentation and reference table. For
 * questions about a reader's own results use `askAboutReport` instead.
 *
 * `history` carries the recent turns so a follow-up can refer to what was
 * already said. It is sent from here every time rather than kept server-side:
 * a conversation held in the caller's own state cannot be handed to the wrong
 * reader, and there is no session to expire.
 *
 * @param {string} question
 * @param {Array<{role: string, text: string}>} [history] - oldest first
 * @returns {Promise<{answer: string, sources: Array, engine: string, tone: string}>}
 */
export function askAssistant(question, history = []) {
  const body = { question };
  if (history.length) body.history = history;

  return request("/assistant/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

/**
 * Ask about one particular set of results.
 *
 * A different endpoint from `askAssistant`, not a flag on it. That one
 * searches the documentation; this one answers from the report and nothing
 * else. Sharing a path meant the documentation competed with the reader's own
 * results and won - "why is it critical?" came back as a textbook definition
 * assembled from three doc chunks.
 *
 * @param {string} question
 * @param {string} report - text from `buildReportDigest`
 * @param {Array<{role: string, text: string}>} [history] - turns about THIS
 *   report only, oldest first
 */
export function askAboutReport(question, report, history = []) {
  return request("/assistant/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, report, history }),
  });
}

/** Whether the assistant has a usable backend, and which models are ready. */
export function getAssistantStatus() {
  return request("/assistant/status");
}

/**
 * Record feedback about the application.
 *
 * Stored by the backend rather than posted to a mail service: doing the latter
 * means shipping the provider's keys in this bundle, where anyone can read
 * them.
 *
 * @param {{message: string, rating: number|null, name: string|null,
 *          email: string|null, page: string|null}} feedback
 */
export function submitFeedback(feedback) {
  return request("/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(feedback),
  });
}

/** How much feedback has been left, for the form's own display. */
export function getFeedbackSummary() {
  return request("/feedback/summary");
}

/** Check that the API, the MCP tool server and the LLM provider are ready. */
export function checkHealth() {
  return request("/health");
}
