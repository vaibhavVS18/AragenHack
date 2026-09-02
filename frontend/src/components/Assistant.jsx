import { useEffect, useRef, useState } from "react";

import { askAboutReport, askAssistant, getAssistantStatus } from "../api/client";

/**
 * Assistant - a docked help panel, bottom right.
 *
 * Answers questions about the application from an indexed corpus: the repo's
 * own documentation plus the reference table fetched over MCP. It does not
 * answer medical questions, and it declines rather than improvises when
 * nothing in the index matches.
 *
 * Sources are shown under each answer. An assistant that cites nothing is
 * indistinguishable from one that guessed, which in a clinical tool is not a
 * distinction worth blurring.
 */

const SUGGESTIONS = [
  "How is a result classified as critical?",
  "What is the normal range for potassium?",
  "Why doesn't the AI decide the severity?",
  "How do I upload a CSV?",
];

// Turns of context sent with each question. The backend caps this at 6, and
// three exchanges is what a follow-up actually needs.
const HISTORY_TURNS = 6;

// Offered instead when a report is attached. Each is answerable from the
// results alone - which is the point: they are the questions the report can
// be asked, not the ones a doctor should be.
const REPORT_SUGGESTIONS = [
  "Which of my results is most urgent?",
  "Why was that one flagged?",
  "How far outside normal is it?",
  "What order should I deal with these in?",
];

// Shown beside an answer so the reader knows how the question was read.
const TONE_LABEL = {
  worried: "read as a concern",
  urgent: "read as urgent",
  confused: "read as a request to explain",
  skeptical: "read as a challenge",
  frustrated: "read as a problem report",
  neutral: null,
};

/**
 * A message bubble carrying a pulse trace.
 *
 * The same signal motif as the Pulse Mark in the navbar, so the assistant
 * reads as part of this product rather than a generic chat plugin bolted on.
 * The previous icon was a bubble with a lopsided question mark, which said
 * "help widget" and nothing about what it knows.
 */
function AssistantIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M20.5 11.8a8.2 8.2 0 0 1-8.8 8.2 9 9 0 0 1-3.3-.8L3.5 21l1.6-4.6a8.2 8.2 0 0 1-1-4 8.2 8.2 0 0 1 8.2-8.2 8.2 8.2 0 0 1 8.2 8.2z" />
      <path d="M7.6 12.2h1.9l1.3-2.9 1.9 5.2 1.3-2.3h2.4" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="M6 18L18 6M6 6l12 12" />
    </svg>
  );
}

function Bubble({ turn }) {
  if (turn.role === "user") {
    // Marked per question, not per conversation: the report can be detached
    // partway through, and afterwards there is no other way to tell which of
    // the answers above were written with the reader's numbers in hand.
    return (
      <div className="chat__user">
        {turn.text}
        {turn.onReport && (
          <span className="chat__on-report" title="Asked with your report attached">
            on your report
          </span>
        )}
      </div>
    );
  }

  return (
    <div className="chat__reply">
      {turn.pending ? (
        <span className="chat__typing" aria-label="Thinking">
          <i /><i /><i />
        </span>
      ) : (
        <>
          <div className="chat__text">{turn.text}</div>

          {/* An answer about the reader's own results cites nothing - the
              report is already on the screen beside it. The engine still
              shows, so it is never unclear what produced the answer. */}
          {turn.sources?.length === 0 && turn.engine && (
            <p className="chat__meta">
              from your report · {turn.engine}
              {TONE_LABEL[turn.tone] ? ` · ${TONE_LABEL[turn.tone]}` : ""}
            </p>
          )}

          {turn.sources?.length > 0 && (
            <details className="chat__sources">
              <summary>
                {turn.sources.length} source
                {turn.sources.length === 1 ? "" : "s"}
                {turn.engine ? ` · ${turn.engine}` : ""}
                {TONE_LABEL[turn.tone] ? ` · ${TONE_LABEL[turn.tone]}` : ""}
              </summary>
              <ul>
                {turn.sources.map((s, i) => (
                  <li key={i}>
                    <span className="chat__source-title">{s.title}</span>
                    <span className="chat__source-file">{s.source}</span>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
    </div>
  );
}

export default function Assistant({ report, reportLabel, openSignal }) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState(null);
  const [turns, setTurns] = useState([]);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  // Whether the attached report is being sent with questions. It can be
  // switched off without leaving the panel, because "how does this app work?"
  // and "what does my potassium mean?" are different questions and the answer
  // to the first should not be bent around the reader's own numbers.
  const [useReport, setUseReport] = useState(true);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const panelRef = useRef(null);
  const fabRef = useRef(null);
  const lastReportRef = useRef(report);

  const attached = Boolean(report) && useReport;

  useEffect(() => {
    let cancelled = false;
    getAssistantStatus()
      .then((body) => !cancelled && setStatus(body))
      .catch(() => !cancelled && setStatus({ available: false }));
    return () => {
      cancelled = true;
    };
  }, []);

  // Opened from outside - the "Ask about this report" button under the
  // results. A counter rather than a boolean, so pressing the button a second
  // time reopens the panel after it has been closed; a boolean would already
  // be true and nothing would happen.
  useEffect(() => {
    if (!openSignal) return;
    setOpen(true);
    setUseReport(true);
  }, [openSignal]);

  // Focus follows the panel actually being on screen. Doing it in the effect
  // above focused nothing: `setOpen(true)` there had not rendered the panel
  // yet, so the input did not exist to receive it.
  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  /*
   * A new analysis clears the conversation about the previous one.
   *
   * The report prop is derived from whatever is on screen, so running a second
   * analysis silently swaps it. Left alone, the next question would go out with
   * the new results attached and the previous exchange - about entirely
   * different numbers - still in the history, and the model would be asked to
   * reconcile two panels that have nothing to do with each other.
   *
   * Cleared rather than kept behind a separator: a transcript describing values
   * that are no longer anywhere on the page is not history worth scrolling, and
   * every line of it is a chance to misread an old number as a current one.
   */
  useEffect(() => {
    if (report === lastReportRef.current) return;

    const hadReport = Boolean(lastReportRef.current);
    lastReportRef.current = report;
    if (!hadReport || !report) return;

    setTurns([]);
  }, [report]);

  // Close on a click outside the panel, and on Escape.
  //
  // The launcher is excluded from the outside test deliberately: it is its own
  // toggle, and without the exclusion a click on it would close the panel here
  // and immediately reopen it in the button's own handler.
  useEffect(() => {
    if (!open) return undefined;

    function onPointerDown(event) {
      if (
        panelRef.current?.contains(event.target) ||
        fabRef.current?.contains(event.target)
      ) {
        return;
      }
      setOpen(false);
    }

    function onKeyDown(event) {
      if (event.key === "Escape") setOpen(false);
    }

    // mousedown rather than click: a click that begins inside the panel and
    // ends outside it (selecting an answer, then releasing) should not close.
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  // Keep the newest turn in view as the conversation grows.
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns]);

  async function submit(text) {
    const asked = (text ?? question).trim();
    if (!asked || busy) return;

    setQuestion("");
    setBusy(true);
    setTurns((t) => [
      ...t,
      { role: "user", text: asked, onReport: attached },
      { role: "assistant", pending: true },
    ]);

    // The last three exchanges, oldest first. Enough for "what about the
    // second one?" to mean something; short enough that a long session does
    // not slowly bury the report under its own transcript.
    const history = turns
      .filter((t) => !t.pending && t.text)
      .slice(-HISTORY_TURNS)
      .map((t) => ({ role: t.role, text: t.text.slice(0, 2000) }));

    try {
      // Two modes, two endpoints. Attached, the answer comes from the reader's
      // results and nothing is retrieved; detached, it comes from the indexed
      // documentation. One endpoint doing both is what produced a textbook
      // definition of "critical" in answer to a question about a real value.
      const body = attached
        ? await askAboutReport(asked, report, history)
        : await askAssistant(asked, history);
      setTurns((t) => [
        ...t.slice(0, -1),
        {
          role: "assistant",
          text: body.answer,
          sources: body.sources,
          engine: body.engine,
          tone: body.tone,
        },
      ]);
    } catch (err) {
      setTurns((t) => [
        ...t.slice(0, -1),
        {
          role: "assistant",
          // A 404 here means one specific thing: the API server is running
          // code older than this page, from before /assistant/report existed.
          // Left as the raw body it reached the reader as the single word
          // "Not Found", which explains nothing and looks like the question
          // was the problem.
          text:
            err.status === 404
              ? "The API server is running an older version that does not have this endpoint yet. Restart it — from the backend folder: .venv/Scripts/uvicorn app.main:app --reload --port 8000"
              // 503 carries the server's own reason - daemon down, model not
              // pulled, or generation failed - each with its own fix, so it is
              // shown as written rather than flattened into one sentence.
              : err.message,
        },
      ]);
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  // Hidden until the status call returns, then shown either way.
  //
  // It used to hide whenever the backend could not answer, which was wrong
  // once the cloud fallback was removed: with Ollama stopped the widget simply
  // vanished, so the one thing worth saying - that the local model needs
  // starting - had nowhere to appear. An offline assistant that explains
  // itself is more use than no assistant at all.
  if (!status) return null;

  const offline = !status.available;

  return (
    <>
      {!open && (
        <button
          ref={fabRef}
          type="button"
          className="assistant-fab"
          onClick={() => setOpen(true)}
          aria-expanded={false}
          aria-label={report ? "Ask about your report" : "Ask about this app"}
        >
          <span className="assistant-fab__label">
            {report ? "Ask about your report" : "Ask about this app"}
          </span>
          <AssistantIcon />
        </button>
      )}

      {open && (
        <section className="assistant" aria-label="Assistant" ref={panelRef}>
          <header className="assistant__head">
            <div>
              <strong>{attached ? "Ask about your report" : "Ask about this app"}</strong>
              <span className="assistant__sub">
                {attached
                  ? "Your results are attached — answers can quote them"
                  : "How it classifies, what the ranges are, how to use it"}
              </span>
            </div>
            <button
              type="button"
              className="assistant__close"
              onClick={() => setOpen(false)}
              aria-label="Close assistant"
            >
              <CloseIcon />
            </button>
          </header>

          <div className="assistant__body" ref={scrollRef}>
            {/* Says exactly what is missing and the command that fixes it.
                Named the model rather than "the assistant is unavailable":
                two different things can be wrong - the daemon or the pull -
                and only the server knows which. */}
            {offline && (
              <div className="assistant__offline" role="status">
                <strong>Not connected to the local model.</strong>
                <p>
                  This assistant runs entirely on your machine through Ollama,
                  with no cloud fallback. Start Ollama, then install the models
                  it needs:
                </p>
                <code>ollama pull {status.ollama?.chat_model ?? "qwen2.5:3b"}</code>
                <code>ollama pull {status.ollama?.embed_model ?? "nomic-embed-text"}</code>
              </div>
            )}

            {!offline && turns.length === 0 && (
              <div className="assistant__intro">
                <p>
                  {attached
                    ? "Ask me about the results above and I'll answer from them — which is most urgent, why one was flagged, how far outside its range it sits. What they mean for your health is a question for a doctor."
                    : "I answer from this project's own documentation and reference table. I can't give medical advice — that belongs with a doctor."}
                </p>
                <div className="assistant__suggestions">
                  {(attached ? REPORT_SUGGESTIONS : SUGGESTIONS).map((s) => (
                    <button
                      key={s}
                      type="button"
                      className="assistant__chip"
                      onClick={() => submit(s)}
                    >
                      {s}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {turns.map((turn, i) => (
              <Bubble key={i} turn={turn} />
            ))}
          </div>

          {/* Sits directly above the box you type in, because that is the
              moment it matters: it answers "where is this question going?"
              while the question is being written, not once at the top of a
              panel that has since scrolled away behind the conversation. */}
          {report && (
            <div
              className={`assistant__attached ${useReport ? "" : "assistant__attached--off"}`}
            >
              <span className="assistant__attached-dot" aria-hidden="true" />
              <span className="assistant__attached-text">
                {useReport
                  ? `Answering from your report${reportLabel ? ` · ${reportLabel}` : ""}`
                  : "Answering about the app, not your report"}
              </span>
              <button
                type="button"
                className="assistant__attached-toggle"
                onClick={() => setUseReport((on) => !on)}
              >
                {useReport ? "Detach" : "Use them"}
              </button>
            </div>
          )}

          <form
            className="assistant__form"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <input
              ref={inputRef}
              className="field"
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder={offline ? "Start Ollama to ask a question" : "Ask a question…"}
              aria-label="Your question"
              disabled={busy || offline}
            />
            <button
              type="submit"
              className="btn btn--primary btn--sm"
              disabled={busy || offline || !question.trim()}
            >
              Ask
            </button>
          </form>
        </section>
      )}
    </>
  );
}
