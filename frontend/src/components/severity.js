/**
 * Severity vocabulary shared by the badge, the summary chips and the section
 * headings.
 *
 * Kept in its own module rather than exported from SeverityBadge so that file
 * exports only a component - a file mixing components and constants breaks
 * React Fast Refresh during development.
 *
 * The icon and label exist so severity is never communicated by colour alone.
 */
export const SEVERITY_META = {
  critical: { label: "Critical", icon: "🚨" },
  warning: { label: "Warning", icon: "⚠️" },
  normal: { label: "Normal", icon: "✓" },
  unknown: { label: "Unknown", icon: "?" },
};

/** Display order everywhere: most urgent first. */
export const SEVERITY_ORDER = ["critical", "warning", "normal", "unknown"];
