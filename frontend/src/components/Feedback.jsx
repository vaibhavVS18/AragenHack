import { useEffect, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { getFeedbackSummary, submitFeedback } from "../api/client";

/**
 * Feedback - a modal, opened from the footer.
 *
 * A dialog rather than a permanent section: feedback is something a person
 * decides to give, and a form sitting at the bottom of every page occupies
 * space on all of them to serve the few visits where someone has something to
 * say.
 *
 * Only the message is required. Asking for a name and an email before someone
 * can say "the CSV upload confused me" loses most of the feedback that would
 * have been worth having.
 *
 * Submissions are stored by the backend. The pattern this was modelled on
 * posted to EmailJS with the service key in the front-end source, which
 * publishes those credentials in the bundle.
 */

const STARS = [1, 2, 3, 4, 5];

const PAGE_NAMES = {
  "/": "Analyze",
  "/datasets": "Datasets",
  "/reference": "Reference ranges",
  "/about": "How it works",
};

export default function Feedback({ open, onClose }) {
  const [message, setMessage] = useState("");
  const [rating, setRating] = useState(null);
  const [hovered, setHovered] = useState(null);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [state, setState] = useState("idle"); // idle | sending | sent | error
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null);

  const location = useLocation();
  const messageRef = useRef(null);
  const returnFocusRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;

    // Remember what had focus so it can be handed back on close, and lock the
    // page behind the dialog so scrolling does not run through to it.
    returnFocusRef.current = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    messageRef.current?.focus();

    function onKeyDown(event) {
      if (event.key === "Escape") onClose();
    }
    document.addEventListener("keydown", onKeyDown);

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.body.style.overflow = previousOverflow;
      returnFocusRef.current?.focus?.();
    };
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return undefined;

    let cancelled = false;
    getFeedbackSummary()
      .then((body) => !cancelled && setSummary(body))
      .catch(() => {
        // The count is decoration; losing it must not hide the form.
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  async function onSubmit(event) {
    event.preventDefault();
    if (!message.trim() || state === "sending") return;

    setState("sending");
    setError(null);

    try {
      const receipt = await submitFeedback({
        message: message.trim(),
        rating,
        name: name.trim() || null,
        email: email.trim() || null,
        page: PAGE_NAMES[location.pathname] ?? location.pathname,
      });
      setState("sent");
      setSummary((s) => ({ ...(s ?? {}), count: receipt.count }));
    } catch (err) {
      setState("error");
      setError(err);
    }
  }

  function reset() {
    setMessage("");
    setRating(null);
    setName("");
    setEmail("");
    setState("idle");
    setError(null);
  }

  function closeAndReset() {
    onClose();
    // Cleared after the dialog has gone, so the form does not visibly empty
    // itself on the way out.
    setTimeout(reset, 200);
  }

  if (!open) return null;

  return (
    <div className="modal" role="presentation">
      <button
        type="button"
        className="modal__backdrop"
        aria-label="Close feedback"
        onClick={closeAndReset}
      />

      <div
        className="modal__card"
        role="dialog"
        aria-modal="true"
        aria-labelledby="feedback-title"
      >
        <header className="modal__head">
          <div>
            <h3 className="modal__title" id="feedback-title">
              Your feedback
            </h3>
            <p className="modal__sub">
              What worked, what didn&rsquo;t, what you expected instead.
              {summary?.count > 0 && (
                <span className="feedback__count">
                  {summary.count} received
                  {summary.average_rating
                    ? ` · ${summary.average_rating}/5 average`
                    : ""}
                </span>
              )}
            </p>
          </div>
          <button
            type="button"
            className="modal__close"
            onClick={closeAndReset}
            aria-label="Close"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 18L18 6M6 6l12 12" strokeLinecap="round" />
            </svg>
          </button>
        </header>

        {state === "sent" ? (
          <div className="modal__body feedback__done">
            <span className="feedback__tick" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <path
                  d="M5 12.5l4.5 4.5L19 7.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            </span>
            <div>
              <h4 className="feedback__title">Thank you — that&rsquo;s been recorded.</h4>
              <p className="feedback__lede">
                {email.trim()
                  ? "If a reply is needed, it will go to the address you left."
                  : "It goes straight to whoever is working on this."}
              </p>
            </div>
            <div className="feedback__done-actions">
              <button type="button" className="btn btn--ghost btn--sm" onClick={reset}>
                Leave more
              </button>
              <button type="button" className="btn btn--primary btn--sm" onClick={closeAndReset}>
                Done
              </button>
            </div>
          </div>
        ) : (
          <form className="modal__body feedback__form" onSubmit={onSubmit}>
            <div
              className="stars"
              role="radiogroup"
              aria-label="Rating, optional"
              onMouseLeave={() => setHovered(null)}
            >
              {STARS.map((value) => {
                const filled = (hovered ?? rating ?? 0) >= value;
                return (
                  <button
                    key={value}
                    type="button"
                    role="radio"
                    aria-checked={rating === value}
                    aria-label={`${value} out of 5`}
                    className={`stars__btn ${filled ? "stars__btn--on" : ""}`}
                    onMouseEnter={() => setHovered(value)}
                    // Clicking the current rating clears it, so an accidental
                    // star is not permanent.
                    onClick={() => setRating((r) => (r === value ? null : value))}
                  >
                    <svg viewBox="0 0 24 24" aria-hidden="true">
                      <path d="M12 2.6l2.9 5.9 6.5.95-4.7 4.6 1.1 6.5-5.8-3.05-5.8 3.05 1.1-6.5-4.7-4.6 6.5-.95z" />
                    </svg>
                  </button>
                );
              })}
              <span className="stars__hint">
                {rating ? `${rating}/5` : "Rating, optional"}
              </span>
            </div>

            <textarea
              ref={messageRef}
              className="field feedback__message"
              rows={4}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Tell us what you think…"
              aria-label="Your feedback"
              maxLength={2000}
              required
            />

            <div className="feedback__row">
              <input
                className="field"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Name (optional)"
                aria-label="Your name, optional"
                maxLength={80}
              />
              <input
                className="field"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email (optional, for a reply)"
                aria-label="Your email, optional"
                maxLength={160}
              />
            </div>

            {state === "error" && (
              <p className="feedback__error" role="alert">
                {error?.message ?? "That could not be sent."} Nothing was lost —
                your message is still in the box.
              </p>
            )}

            <div className="modal__actions">
              <button type="button" className="btn btn--ghost" onClick={closeAndReset}>
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={!message.trim() || state === "sending"}
              >
                {state === "sending" ? "Sending…" : "Send feedback"}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}
