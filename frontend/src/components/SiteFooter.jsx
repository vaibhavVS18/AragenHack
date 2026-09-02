import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import Feedback from "./Feedback";

/**
 * SiteFooter - the end of the page.
 *
 * Brand, the page links, and how to reach the author. The "built with" and
 * reference columns were removed: the stack is already on the How it works
 * page, where someone asking that question actually is, and a footer that
 * lists its own dependencies is talking to nobody.
 *
 * The typewriter signature is kept from the reference implementation, because
 * it is a signature and a little character is the point.
 */

const SIGNATURE = "Designed & built by Vaibhav Sharma";

// Filled marks with the official geometry - GitHub and LinkedIn are
// trademarks with defined shapes, and the earlier stroke-drawn versions were
// recognisably wrong.
//
// Neutral at rest, brand colour on hover, the same way the portfolio does it.
// Four saturated logos sitting permanently in a footer pull the eye to the
// least important thing on the page; on hover the colour confirms what you
// are about to click.
//
// GitHub's mark is near-black, which disappears on a dark ground, so it takes
// the theme's ink value rather than the literal brand hex.
const LINKS = [
  {
    label: "Portfolio",
    href: "https://vaibhavportfolio.in/",
    brand: "var(--accent)",
    path: "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm6.92 6h-2.95a15.7 15.7 0 0 0-1.38-3.56A8 8 0 0 1 18.92 8zM12 4.04c.83 1.2 1.48 2.53 1.91 3.96h-3.82c.43-1.43 1.08-2.76 1.91-3.96zM4.26 14A8.1 8.1 0 0 1 4 12c0-.69.1-1.36.26-2h3.38a16.5 16.5 0 0 0 0 4H4.26zm.82 2h2.95c.32 1.25.78 2.45 1.38 3.56A8 8 0 0 1 5.08 16zm2.95-8H5.08a8 8 0 0 1 4.33-3.56A15.7 15.7 0 0 0 8.03 8zM12 19.96c-.83-1.2-1.48-2.53-1.91-3.96h3.82c-.43 1.43-1.08 2.76-1.91 3.96zM14.34 14H9.66a14.6 14.6 0 0 1 0-4h4.68a14.6 14.6 0 0 1 0 4zm.25 5.56c.6-1.11 1.06-2.31 1.38-3.56h2.95a8 8 0 0 1-4.33 3.56zM16.36 14a16.5 16.5 0 0 0 0-4h3.38c.16.64.26 1.31.26 2s-.1 1.36-.26 2h-3.38z",
  },
  {
    label: "GitHub",
    href: "https://github.com/vaibhavVS18",
    brand: "light-dark(#181717, #ffffff)",
    path: "M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23a11.5 11.5 0 0 1 6 0c2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12",
  },
  {
    label: "LinkedIn",
    href: "https://www.linkedin.com/in/vaibhav-sharma-90619a291/",
    brand: "#0A66C2",
    // The mark is a filled square with the "in" knocked out, so it needs a
    // light shape behind it or the letters take the button's background.
    knockout: true,
    path: "M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 1 1 0-4.124 2.062 2.062 0 0 1 0 4.124zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z",
  },
  {
    label: "Email",
    href: "mailto:vaibhav.iiituna1111@gmail.com",
    brand: "#EA4335",
    path: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 4-8 5-8-5V6l8 5 8-5v2z",
  },
];


/**
 * Types the signature out, pauses, deletes, repeats.
 *
 * Paused entirely when the visitor prefers reduced motion - a looping
 * animation in the footer is exactly the kind of thing that setting is for.
 */
function Signature() {
  const [reduced] = useState(
    () => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false,
  );
  // Initialised to the finished string when motion is reduced, rather than
  // set from inside the effect: assigning state there starts a second render
  // for a value that was knowable before the first.
  const [text, setText] = useState(() => (reduced ? SIGNATURE : ""));
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (reduced) return undefined;

    let delay = 90;
    if (!deleting && text.length === SIGNATURE.length) delay = 2200;
    else if (deleting) delay = 45;

    const timer = setTimeout(() => {
      if (!deleting && text.length < SIGNATURE.length) {
        setText(SIGNATURE.slice(0, text.length + 1));
      } else if (!deleting) {
        setDeleting(true);
      } else if (text.length > 0) {
        setText(SIGNATURE.slice(0, text.length - 1));
      } else {
        setDeleting(false);
      }
    }, delay);

    return () => clearTimeout(timer);
  }, [text, deleting, reduced]);

  return (
    <p className="signature">
      <span>{text}</span>
      {!reduced && <i className="signature__caret" aria-hidden="true" />}
    </p>
  );
}

export default function SiteFooter() {
  const [feedbackOpen, setFeedbackOpen] = useState(false);

  return (
    <footer className="site-footer">
      <div className="page-inner">
        <div className="site-footer__grid">
          <div className="site-footer__brand">
            <span className="brand__mark" aria-hidden="true">
              A
            </span>
            <div>
              <span className="brand__word">
                Aragen<span className="brand__suffix">AI</span>
              </span>
              <p className="site-footer__tagline">
                Read the result. Reveal the risk.
              </p>

              <button
                type="button"
                className="btn btn--ghost btn--sm site-footer__feedback"
                onClick={() => setFeedbackOpen(true)}
              >
                Give feedback
              </button>
            </div>
          </div>

          <nav className="site-footer__col" aria-label="Footer">
            <h4>Pages</h4>
            <Link to="/">Analyze</Link>
            <Link to="/datasets">Datasets</Link>
            <Link to="/reference">Reference ranges</Link>
            <Link to="/about">How it works</Link>
          </nav>

          <div className="site-footer__col">
            <h4>Find me</h4>
            <div className="socials">
              {LINKS.map((link) => (
                <a
                  key={link.label}
                  className={`social ${link.knockout ? "social--knockout" : ""}`}
                  style={{ "--brand": link.brand }}
                  href={link.href}
                  target={link.href.startsWith("mailto:") ? undefined : "_blank"}
                  rel="noreferrer"
                  aria-label={link.label}
                  title={link.label}
                >
                  {link.knockout && <span className="social__backing" aria-hidden="true" />}
                  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d={link.path} />
                  </svg>
                </a>
              ))}
            </div>
          </div>
        </div>

        <div className="site-footer__base">
          <Signature />
          <span className="site-footer__year">
            © {new Date().getFullYear()} · GenAI full-stack assignment
          </span>
        </div>
      </div>

      <Feedback open={feedbackOpen} onClose={() => setFeedbackOpen(false)} />
    </footer>
  );
}
