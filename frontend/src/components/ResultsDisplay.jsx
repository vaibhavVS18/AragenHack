/**
 * ResultsDisplay — renders the agent's response.
 *
 * Results arrive already ordered by the backend's Route step
 * (Critical -> Warning -> Normal) and are rendered in that order,
 * grouped under section headers with counts.
 *
 * Explainable-AI requirement: every abnormal row shows the value, the
 * reference range it was compared against, how far outside it falls,
 * the rule that fired, the LLM explanation, and the suggested next step.
 *
 * TODO(step 5): severity sections, ResultCard, empty + error states.
 */
export default function ResultsDisplay() {
  return null;
}
