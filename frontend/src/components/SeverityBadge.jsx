import { SEVERITY_META } from "./severity";

/**
 * SeverityBadge - the color-coded status pill.
 *
 *   critical  red     🚨
 *   warning   yellow  ⚠️
 *   normal    green   ✓
 *   unknown   grey    ?
 *
 * Colour is never the only signal. Each badge also carries an icon and a text
 * label, so the status survives a colourblind reader, a greyscale printout, or
 * a projector with poor contrast.
 */
export default function SeverityBadge({ severity, size = "md" }) {
  const meta = SEVERITY_META[severity] ?? SEVERITY_META.unknown;

  return (
    <span
      className={`badge badge--${severity} badge--${size}`}
      role="status"
      aria-label={`Severity: ${meta.label}`}
    >
      <span className="badge__icon" aria-hidden="true">
        {meta.icon}
      </span>
      {meta.label}
    </span>
  );
}
