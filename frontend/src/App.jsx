import { useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";

import StatusBar from "./components/StatusBar";
import AboutPage from "./pages/AboutPage";
import AnalyzePage from "./pages/AnalyzePage";
import DatasetsPage from "./pages/DatasetsPage";
import ReferencePage from "./pages/ReferencePage";
import {
  analyzeDataset,
  analyzeLabs,
  analyzeLabsCsv,
  checkHealth,
  getReferenceRanges,
} from "./api/client";

/**
 * App - application shell: navigation, shared state, routing.
 *
 * The analysis lifecycle (loading, error, response) lives here rather than in
 * a page, so a run started on the Datasets page is still on screen when the
 * user lands on Analyze. Pages stay presentational and receive what they need
 * as props.
 */

const NAV = [
  {
    to: "/",
    label: "Analyze",
    end: true,
    title: "Analyze lab results",
    blurb: "Enter results or upload a CSV. Each one is classified, routed by severity, then explained.",
    icon: (
      <path d="M4 14h3l2.2-5.5L12 17l2.2-6 1.4 3H20" strokeLinecap="round" strokeLinejoin="round" />
    ),
  },
  {
    to: "/datasets",
    label: "Datasets",
    title: "Sample datasets",
    blurb: "Files bundled with this repository, analyzable in one click.",
    icon: (
      <>
        <ellipse cx="12" cy="6" rx="7" ry="3" />
        <path d="M5 6v6c0 1.7 3.1 3 7 3s7-1.3 7-3V6" strokeLinecap="round" />
        <path d="M5 12v6c0 1.7 3.1 3 7 3s7-1.3 7-3v-6" strokeLinecap="round" />
      </>
    ),
  },
  {
    to: "/reference",
    label: "Reference ranges",
    title: "Reference ranges",
    blurb: "The clinical thresholds used to classify, served from the MCP tool server.",
    icon: (
      <>
        <rect x="4" y="4" width="16" height="16" rx="2" />
        <path d="M4 9.5h16M9.5 9.5V20" strokeLinecap="round" />
      </>
    ),
  },
  {
    to: "/about",
    label: "How it works",
    title: "How it works",
    blurb: "What decides a verdict, and why that decision can be checked.",
    icon: (
      <>
        <circle cx="12" cy="12" r="8" />
        <path d="M12 16v-4.5M12 8.4v.1" strokeLinecap="round" />
      </>
    ),
  },
];

function NavIcon({ children }) {
  return (
    <svg
      className="nav__icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

export default function App() {
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState(null);
  const [catalogue, setCatalogue] = useState([]);
  const [navOpen, setNavOpen] = useState(false);

  const location = useLocation();
  const current =
    NAV.find((item) => (item.end ? location.pathname === item.to : location.pathname.startsWith(item.to))) ??
    null;

  // Check the backend once on load so a stopped server is obvious immediately.
  useEffect(() => {
    let cancelled = false;

    checkHealth()
      .then((body) => !cancelled && setHealth(body))
      .catch((err) => !cancelled && setHealth({ error: err.message }));

    return () => {
      cancelled = true;
    };
  }, []);

  // The catalogue drives input autocomplete and the reference page. Fetched,
  // never hardcoded, so the UI cannot advertise tests the server would reject.
  useEffect(() => {
    let cancelled = false;

    getReferenceRanges()
      .then((body) => !cancelled && setCatalogue(body?.tests ?? []))
      .catch(() => {
        // Autocomplete is a convenience; losing it must not block input.
      });

    return () => {
      cancelled = true;
    };
  }, []);

  /**
   * Run an analysis. Accepts all three input shapes so every page submits
   * through one path and loading/error handling is never duplicated.
   */
  const runAnalysis = useCallback(async (payload) => {
    setLoading(true);
    setError(null);

    try {
      let body;
      if (payload.kind === "csv") {
        body = await analyzeLabsCsv(payload.file, payload.patientId);
      } else if (payload.kind === "dataset") {
        body = await analyzeDataset(payload.datasetId);
      } else {
        body = await analyzeLabs(payload.labs, payload.patientId);
      }
      setResponse(body);
      return body;
    } catch (err) {
      setError(err);
      setResponse(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const shared = {
    response,
    loading,
    error,
    catalogue,
    runAnalysis,
    dismissError: () => setError(null),
  };

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <aside className={`sidebar ${navOpen ? "sidebar--open" : ""}`}>
        <div className="brand">
          <span className="brand__mark" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 13h3.5l1.8-4.5L11 19l2.4-11 2 8 1.3-3H21"
                    strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
          <span className="brand__text">
            <strong>Lab Analyzer</strong>
            <small>Clinical results triage</small>
          </span>
        </div>

        <nav className="nav" aria-label="Main">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                `nav__link ${isActive ? "nav__link--active" : ""}`
              }
              // Closed here rather than in an effect on the route: the click
              // is what should close the drawer, and doing it in an effect
              // triggers a second render for no reason.
              onClick={() => setNavOpen(false)}
            >
              <NavIcon>{item.icon}</NavIcon>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar__foot">
          <StatusBar health={health} />
          <p className="sidebar__note">
            Classification is deterministic. The model explains results — it
            never decides them.
          </p>
        </div>
      </aside>

      {navOpen && (
        <button
          type="button"
          className="scrim"
          aria-label="Close navigation"
          onClick={() => setNavOpen(false)}
        />
      )}

      <div className="content">
        <header className="topbar">
          <button
            type="button"
            className="topbar__menu"
            aria-label="Open navigation"
            aria-expanded={navOpen}
            onClick={() => setNavOpen((open) => !open)}
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M4 7h16M4 12h16M4 17h16" strokeLinecap="round" />
            </svg>
          </button>

          <div className="topbar__heading">
            <h1 className="topbar__title">{current?.title ?? "Not found"}</h1>
            {current?.blurb && <p className="topbar__blurb">{current.blurb}</p>}
          </div>
        </header>

        <main className="main" id="main">
          <Routes>
            <Route path="/" element={<AnalyzePage {...shared} />} />
            <Route path="/datasets" element={<DatasetsPage {...shared} />} />
            <Route path="/reference" element={<ReferencePage catalogue={catalogue} />} />
            <Route path="/about" element={<AboutPage />} />
            <Route
              path="*"
              element={
                <div className="empty-state">
                  <p>That page does not exist.</p>
                </div>
              }
            />
          </Routes>
        </main>

        <footer className="footer">
          FastAPI · MCP (stdio) · React · Gemini — built for the GenAI
          full-stack assignment. Not a medical device; for demonstration only.
        </footer>
      </div>
    </div>
  );
}
