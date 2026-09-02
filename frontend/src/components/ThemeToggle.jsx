/**
 * ThemeToggle - light or dark, nothing else.
 *
 * A third "System" option was dropped: it is invisible state (two people on
 * the same setting can see different screens) and on a tool this small the
 * two explicit choices are clearer. The operating system preference is still
 * respected - it seeds the initial value on a first visit, in `useTheme`.
 *
 * Stateless by design; App owns the value so the desktop and mobile copies
 * of this control can never disagree.
 */

const MODES = [
  {
    id: "light",
    label: "Light",
    icon: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
      </>
    ),
  },
  {
    id: "dark",
    label: "Dark",
    icon: <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />,
  },
];

export default function ThemeToggle({ theme, onChange }) {
  return (
    <div className="theme" role="group" aria-label="Colour theme">
      {MODES.map((mode) => (
        <button
          key={mode.id}
          type="button"
          className={`theme__btn ${theme === mode.id ? "theme__btn--active" : ""}`}
          onClick={() => onChange(mode.id)}
          aria-pressed={theme === mode.id}
          title={`${mode.label} theme`}
        >
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.7"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            {mode.icon}
          </svg>
          <span className="sr-only">{mode.label}</span>
        </button>
      ))}
    </div>
  );
}
