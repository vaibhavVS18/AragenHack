/**
 * Single place that knows how to talk to the FastAPI backend.
 * Keeps fetch/URL/error handling out of the components.
 *
 * TODO(step 5): analyzeLabs(labs), analyzeLabsCsv(file), checkHealth().
 */
export const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
