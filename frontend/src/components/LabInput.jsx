/**
 * LabInput — how lab results get into the app.
 *
 * Two input modes, both required by the assignment:
 *   1. Manual form  — add rows of { test_name, value, unit }
 *   2. CSV upload   — drop a file from /test_data or the Kaggle dataset
 *
 * Owns only input state. Hands a clean payload to App via onAnalyze;
 * it never calls the API itself and never interprets results.
 *
 * TODO(step 5): row editor, file picker, client-side validation.
 */
export default function LabInput() {
  return null;
}
