import PipelineDiagram from "../components/PipelineDiagram";

/**
 * AboutPage - how a verdict is produced, and why it can be checked.
 *
 * The assignment's key constraint is that a user should understand why a
 * result was flagged. Per-result reasoning lives on each card; this page
 * covers what does not fit there: the pipeline, the division of labour
 * between code and model, and where the numbers come from.
 *
 * Laid out as alternating paper / mist bands. The rhythm is not decoration:
 * each band is one idea, and the change of ground marks where one ends.
 */

const FEATURES = [
  {
    group: "Getting results in",
    items: [
      "Type results in by hand, with autocomplete on test names and the unit filled in for you",
      "Upload a CSV, with the parsed rows shown back to you before anything is analysed",
      "Four bundled sample files, analysable in one click",
      "Messy headers accepted: Test Name, Result, Units and other common spellings",
      "Aliases and typos resolved - HGB, K+, SGPT, and the Turkish names in the Kaggle data",
    ],
  },
  {
    group: "Classification",
    items: [
      "16 built-in lab tests across haematology, chemistry, endocrine and liver",
      "Five severity bands from a test's four thresholds, boundaries inclusive of Normal",
      "Per-row reference intervals from the data take precedence over the built-in table",
      "Qualitative results compared as words, for urinalysis strips reporting Negatif or 1+",
      "Unreadable rows reported separately, never guessed at, and never sinking the rest of the file",
      "Conflicting units refused rather than converted",
    ],
  },
  {
    group: "Explanation",
    items: [
      "A structured explanation per result: what the test measures, what your value means, common causes, urgency, what to do, and questions for a doctor",
      "Written after classification, from the finished verdict",
      "The literal comparison shown on every card, with the range used and where it came from",
      "A gauge placing the value across all five severity bands",
      "Degraded mode: if the model is unreachable, severities and reasoning survive intact",
    ],
  },
  {
    group: "Reading and sharing",
    items: [
      "Results ordered most urgent first, with the most deviant value leading each group",
      "A proportional bar showing the shape of the whole panel before any number is read",
      "Filter by severity, or search across test name, category and explanation",
      "A generated PDF report with letterhead, page numbers and every explanation",
      "CSV export that keeps the reasoning, not just the verdicts",
    ],
  },
  {
    group: "The assistant",
    items: [
      "Answers questions about this application from an indexed corpus",
      "Retrieval over embeddings with cosine similarity - only the closest passages reach the model",
      "Runs on a local model through Ollama, falling back to Gemini when it is not running",
      "Reads the tone of a question and adjusts how it answers, never what it answers",
      "Refuses medical questions in code, before the model sees them",
      "Cites its sources under every answer",
    ],
  },
];


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
      <section className="band band--flush ground--paper">
        <h2 className="band__title">Code classifies. The model explains.</h2>
        <p className="band__lede">
          Severity is decided by arithmetic that can be checked. The language
          model is handed that decision and asked to put it into clinical
          language — it is never asked what the severity is.
        </p>
      </section>

      <section className="band ground--paper">
        <h2 className="band__title">What it does</h2>
        <p className="band__lede">
          Everything the application can do, grouped by the part of the job it
          belongs to.
        </p>

        <div className="features">
          {FEATURES.map((section) => (
            <div key={section.group} className="feature">
              <h3 className="feature__title">{section.group}</h3>
              <ul className="feature__list">
                {section.items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <section className="band ground--mist">
        <h2 className="band__title">Classify → Route → Explain</h2>

        <PipelineDiagram />

        <ol className="steps">
          {STEPS.map((item) => (
            <li key={item.step} className="step">
              <span className="step__number" aria-hidden="true">
                {item.step}
              </span>
              <div>
                <h3 className="step__name">
                  {item.name}
                  <span className="step__where">{item.where}</span>
                </h3>
                <p className="step__text">{item.text}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="band ground--paper">
        <h2 className="band__title">A verdict has to be reproducible</h2>
        <p className="band__lede">
          A language model asked to grade a potassium of 6.8 mEq/L might answer
          differently on two runs, and cannot show its arithmetic. The
          comparison <code>6.8 &gt; 6.5</code> is identical every time, is unit
          tested, and can be read by anyone. A hallucinated
          &ldquo;Normal&rdquo; on a critical value is the most dangerous
          failure this application could have, so that decision is kept out of
          the model entirely.
        </p>
        <p className="band__lede">
          It also means a model outage costs the explanation but never the
          verdict: if Gemini is unreachable, results still arrive classified,
          reasoning intact, with a notice where the prose would be.
        </p>
      </section>

      <section className="band ground--paper">
        <h2 className="band__title">Three grades, and one honest refusal</h2>

        <div className="bands">
          {BANDS.map(([label, key, text]) => (
            <div key={key} className={`band-row band-row--${key}`}>
              <strong>{label}</strong>
              <span>{text}</span>
            </div>
          ))}
        </div>

        <p className="band__lede">
          Boundaries are inclusive of Normal: a value exactly equal to the
          lower or upper limit is Normal. A row that cannot be interpreted at
          all — an unrecognised test, a non-numeric value, a unit that does not
          match the range — is reported separately as unreadable rather than
          guessed at.
        </p>
      </section>

      <section className="band ground--mist">
        <h2 className="band__title">Where the numbers come from</h2>

        <ol className="sources">
          <li>
            <strong>The interval supplied with the result.</strong> Reference
            ranges vary by laboratory, method and population, so a range that
            arrives alongside a result is authoritative for it. The Kaggle
            dataset supplies one per row.
          </li>
          <li>
            <strong>The built-in table.</strong> Used when the result carries
            no range, and the only source of genuine critical thresholds — the
            dataset has no concept of a panic value.
          </li>
          <li>
            <strong>Neither.</strong> The result is returned uninterpreted and
            flagged, rather than classified against a guess.
          </li>
        </ol>

        <p className="band__lede">
          Where a supplied range is used for a test the table does not know,
          critical thresholds are estimated from the range width and labelled
          <em> derived</em> on the card — so an estimate is never mistaken for
          a published panic value.
        </p>
      </section>

      <section className="band ground--paper">
        <h2 className="band__title">What MCP is doing here</h2>
        <p className="band__lede">
          The clinical logic runs in a separate process — an MCP server — that
          the agent talks to over JSON-RPC on stdio. The agent holds no medical
          knowledge and never imports that code directly; a test asserts the
          boundary holds. The practical benefit is that the same tools can be
          driven by any MCP client, not only this application.
        </p>
        <p className="band__lede">
          Four tools are exposed: <code>get_reference_range</code>,{" "}
          <code>list_reference_ranges</code>, <code>classify_lab_result</code>{" "}
          and <code>route_by_severity</code>.
        </p>
      </section>

      <section className="band ground--mist">
        <h2 className="band__title">What this does not do</h2>
        <ul className="limits">
          <li>Ranges are adult and sex-agnostic; no age or sex adjustment is applied.</li>
          <li>Glucose is assumed fasting.</li>
          <li>Units are never converted — a mismatched unit is refused rather than guessed.</li>
          <li>
            Qualitative strip results record presence, not amount, so they never
            escalate beyond Warning.
          </li>
          <li>This is a demonstration built for an assignment, not a medical device.</li>
        </ul>
      </section>
    </>
  );
}
