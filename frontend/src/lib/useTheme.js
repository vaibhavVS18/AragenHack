import { useCallback, useEffect, useState } from "react";

/**
 * Light / dark theme, owned in one place.
 *
 * The toggle is rendered twice - once in the desktop navbar, once in the
 * mobile row - so the state cannot live inside the component: two copies
 * would drift apart and disagree after a viewport resize. App owns it and
 * passes it down.
 *
 * The choice is written to `data-theme` on the root element, which flips
 * `color-scheme` and therefore every `light-dark()` token at once. It is
 * remembered in localStorage, wrapped in try/catch because private windows
 * and blocked site data make that throw rather than return null.
 */

const STORAGE_KEY = "aragen-theme";

/**
 * The stored choice, or light on a first visit.
 *
 * Light is the deliberate default rather than the operating system
 * preference: this is a clinical reading tool, and the light theme is the one
 * that matches printed lab reports and the environments they are read in. A
 * visitor who prefers dark switches once and the choice sticks.
 */
function initialTheme() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored === "light" || stored === "dark") return stored;
  } catch {
    // Storage unavailable; fall back to the default.
  }
  return "light";
}

export function useTheme() {
  const [theme, setTheme] = useState(initialTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      // Storage unavailable; the theme still applies for this session.
    }
  }, [theme]);

  const toggle = useCallback(
    () => setTheme((current) => (current === "dark" ? "light" : "dark")),
    [],
  );

  return { theme, setTheme, toggle };
}
