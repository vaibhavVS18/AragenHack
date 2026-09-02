/**
 * AboutPage - how a verdict is produced, and why it can be checked.
 *
 * The assignment's key constraint is that a user should understand why a
 * result was flagged. Per-result reasoning lives on each card; this page
 * covers the part that does not fit there - the pipeline, the division of
 * labour between code and model, and where the numbers come from.
 */

const STEPS = [
  {
    step: "1",
    name: "Classify",
    where: "MCP tool · classify_lab_result",
    text: "The value is compared against a reference interval using fixed thresholds. Deterministic: the same input always produces the same severity.",
  },
  {
    step: "2",
    name: "Route",
    where: "MCP tool · route_by_severity",
    text: "Results are grouped and ordered Critical, then Warning, then Normal. Within a group the most deviant value leads.",
  },
  {
    step: "3",
    name: "Explain",
    where: "Gemini",
    text: "The already-classified results are sent to the model in one batched call. It writes the clinical meaning and a suggested next step. It is never asked what the severity is.",
  },
];

const BANDS = [
  ["Critical", "critical", "Beyond the critical threshold. Life-threatening; act now."],
  ["Warning", "warning", "Outside the reference range but not critical. Needs follow-up."],
  ["Normal", "normal", "Within the reference range, bounds included."],
];

export default function AboutPage() {
  return (
    <>
      <section className="panel">
        <h3 className="panel__title">The rule that shapes everything</h3>
        <p className="panel__text">
          <strong>Code classifies, the model explains.</strong> Severity is
          decided by arithmetic that can be checked; the language model is given
          that decision and asked to put it into clinical language. It is never
          asked what the severity is.
        </p>
      </section>

      <section className="panel">
        <h3 className="panel__title">The pipeline</h3>
        <ol className="steps">
          {STEPS.map((item) => (
            <li key={item.step} className="step">
              <span className="step__number" aria-hidden="true">{item.step}</span>
              <div>
                <h4 className="step__name">
                  {item.name}
                  <span className="step__where">{item.where}</span>
                </h4>
                <p className="step__text">{item.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="panel">
        <h3 className="panel__title">Why the model does not classify</h3>
        <p className="panel__text">
          A language model asked to grade a potassium of 6.8 mEq/L might answer
          differently on two runs, and cannot show its arithmetic. The
          comparison <code>6.8 &gt; 6.5</code> is identical every time, is unit
          tested, and can be read by anyone. Since a hallucinated
          &ldquo;Normal&rdquo; on a critical value is the most dangerous failure
          this application could have, that decision is kept out of the model.
        </p>
        <p className="panel__text">
          It also means a model outage costs the explanation but never the
          verdict: if Gemini is unreachable, results still arrive classified,
          with their reasoning intact and a notice in place of the prose.
        </p>
      </section>

      <section className="panel">
        <h3 className="panel__title">Severity bands</h3>
        <div className="bands">
          {BANDS.map(([label, key, text]) => (
            <div key={key} className={`band band--${key}`}>
              <strong>{label}</strong>
              <span>{text}</span>
            </div>
          ))}
        </div>
        <p className="panel__text">
          Boundaries are inclusive of Normal: a value exactly equal to the lower
          or upper limit is Normal. A row that cannot be interpreted at all — an
          unrecognised test, a non-numeric value, a unit that does not match the
          range — is reported separately as unreadable rather than being
          guessed at.
        </p>
      </section>

      <section className="panel">
        <h3 className="panel__title">Where the ranges come from</h3>
        <ol className="sources">
          <li>
            <strong>The interval supplied with the result.</strong> Reference
            ranges vary by laboratory, method and population, so a range that
            arrives alongside a result is authoritative for it. The Kaggle
            dataset supplies one per row.
          </li>
          <li>
            <strong>The built-in table.</strong> Used when the result carries no
            range, and the only source of genuine critical thresholds — the
            dataset has no concept of a panic value.
          </li>
          <li>
            <strong>Neither.</strong> The result is returned uninterpreted and
            flagged, rather than classified against a guess.
          </li>
        </ol>
        <p className="panel__text">
          Where a supplied range is used for a test the table does not know,
          critical thresholds are estimated from the range width and labelled
          <em> derived</em> on the card, so an estimate is never mistaken for a
          published panic value.
        </p>
      </section>

      <section className="panel">
        <h3 className="panel__title">What MCP is doing here</h3>
        <p className="panel__text">
          The clinical logic runs in a separate process — an MCP server — that
          the agent talks to over JSON-RPC on stdio. The agent holds no medical
          knowledge and never imports that code directly; a test asserts the
          boundary holds. The practical benefit is that the same tools can be
          used by any MCP client, not only this application.
        </p>
        <p className="panel__text">
          Four tools are exposed: <code>get_reference_range</code>,{" "}
          <code>list_reference_ranges</code>, <code>classify_lab_result</code>{" "}
          and <code>route_by_severity</code>.
        </p>
      </section>

      <section className="panel panel--muted">
        <h3 className="panel__title">Limitations</h3>
        <ul className="limits">
          <li>Ranges are adult and sex-agnostic; no age or sex adjustment is applied.</li>
          <li>Glucose is assumed fasting.</li>
          <li>Units are never converted — a mismatched unit is refused rather than guessed.</li>
          <li>Qualitative strip results record presence, not amount, so they never escalate beyond Warning.</li>
          <li>This is a demonstration for an assignment, not a medical device.</li>
        </ul>
      </section>
    </>
  );
}
