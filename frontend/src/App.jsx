import { useCallback, useEffect, useMemo, useState } from "react";
import { NavLink, Route, Routes, useLocation } from "react-router-dom";

import Assistant from "./components/Assistant";
import SiteFooter from "./components/SiteFooter";
import StatusBar from "./components/StatusBar";
import ThemeToggle from "./components/ThemeToggle";
import { useTheme } from "./lib/useTheme";
import { buildReportDigest, describeReport } from "./lib/reportDigest";
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
 * Layout follows the Journiks pattern: a fixed top navbar over a centred
 * content column, rather than a sidebar. For four destinations a sidebar
 * spends 250px of permanent width on something a row of pills says in one
 * line, and it pushes the content column off-centre on wide screens.
 *
 * The analysis lifecycle (loading, error, response) lives here rather than in
 * a page, so a run started on the Datasets page is still on screen when the
 * user lands on Analyze. Pages stay presentational and take props.
 */

const NAV = [
  {
    to: "/",
    label: "Analyze",
    end: true,
    title: "Analyze lab results",
    blurb:
      "Enter results or upload a CSV. Each one is classified against a reference range, routed by severity, then explained.",
  },
  {
    to: "/datasets",
    label: "Datasets",
    title: "Sample datasets",
    blurb: "Files bundled with this repository, analyzable in one click.",
  },
  {
    to: "/reference",
    label: "Reference ranges",
    title: "Reference ranges",
    blurb:
      "The clinical thresholds used to classify, served from the MCP tool server.",
  },
  {
    to: "/about",
    label: "How it works",
    title: "How it works",
    blurb: "What decides a verdict, and why that decision can be checked.",
  },
];

function MenuIcon({ open }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d={open ? "M6 18L18 6M6 6l12 12" : "M4 6h16M4 12h16M4 18h16"}
      />
    </svg>
  );
}

export default function App() {
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [health, setHealth] = useState(null);
  const [catalogue, setCatalogue] = useState([]);
  const [menuOpen, setMenuOpen] = useState(false);
  // Bumped to ask the assistant to open. A counter, not a flag, so the button
  // works every time rather than only the first.
  const [assistantSignal, setAssistantSignal] = useState(0);

  // The current analysis, as text the assistant can be asked about. Derived
  // from the response already on screen, so the assistant can only ever
  // discuss what the reader is looking at.
  const reportDigest = useMemo(() => buildReportDigest(response), [response]);
  const reportLabel = useMemo(() => describeReport(response), [response]);

  // Owned here so the desktop and mobile copies of the toggle stay in step.
  const { theme, setTheme } = useTheme();

  const location = useLocation();
  const current =
    NAV.find((item) =>
      item.end
        ? location.pathname === item.to
        : location.pathname.startsWith(item.to),
    ) ?? null;

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
        // No patient argument: a CSV that carries a patient column has it
        // read server-side, which is the only place the label now comes from.
        body = await analyzeLabsCsv(payload.file);
      } else if (payload.kind === "dataset") {
        body = await analyzeDataset(payload.datasetId);
      } else {
        body = await analyzeLabs(payload.labs);
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
    onAskAboutReport: () => setAssistantSignal((n) => n + 1),
  };

  const linkClass = ({ isActive }) =>
    `navlink ${isActive ? "navlink--active" : ""}`;

  return (
    <div className="site">
      <a className="skip-link" href="#main">
        Skip to content
      </a>

      <nav className="navbar" aria-label="Main">
        <div className="navbar__inner">
          {/* The Pulse Mark: a serif "A" in a soft-cornered badge with a
              live-signal dot. Direction A from the Aragen brand board. */}
          <NavLink to="/" className="brand" onClick={() => setMenuOpen(false)}>
            <span className="brand__mark" aria-hidden="true">
              A
            </span>
            <span className="brand__word">
              Aragen<span className="brand__suffix">AI</span>
            </span>
          </NavLink>

          <div className="navbar__links">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={linkClass}
              >
                {item.label}
              </NavLink>
            ))}
          </div>

          <div className="navbar__actions">
            <StatusBar health={health} />
            <ThemeToggle theme={theme} onChange={setTheme} />
          </div>

          <div className="navbar__mobile">
            <ThemeToggle theme={theme} onChange={setTheme} />
            <button
              type="button"
              className="navbar__menu"
              aria-label={menuOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((open) => !open)}
            >
              <MenuIcon open={menuOpen} />
            </button>
          </div>
        </div>

        {menuOpen && (
          <div className="navbar__drawer">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={linkClass}
                onClick={() => setMenuOpen(false)}
              >
                {item.label}
              </NavLink>
            ))}
            <div className="navbar__drawer-foot">
              <StatusBar health={health} />
            </div>
          </div>
        )}
      </nav>

      <header className="pagehead">
        <div className="page-inner">
          <h1 className="pagehead__title">{current?.title ?? "Not found"}</h1>
          {current?.blurb && <p className="pagehead__blurb">{current.blurb}</p>}
        </div>
      </header>

      <main className="main" id="main">
        <div className="page-inner">
          <Routes>
            <Route path="/" element={<AnalyzePage {...shared} />} />
            <Route path="/datasets" element={<DatasetsPage {...shared} />} />
            <Route
              path="/reference"
              element={<ReferencePage catalogue={catalogue} />}
            />
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
        </div>
      </main>

      <SiteFooter />

      <Assistant
        report={reportDigest}
        reportLabel={reportLabel}
        openSignal={assistantSignal}
      />
    </div>
  );
}
