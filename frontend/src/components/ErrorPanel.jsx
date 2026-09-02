/**
 * ErrorPanel - a failed request, explained.
 *
 * Carries the hint the API client attaches (most usefully "is the backend
 * running?"), because the fix is nearly always something the user can do.
 */
export default function ErrorPanel({ error, onDismiss }) {
  if (!error) return null;

  return (
    <div className="notice notice--error" role="alert">
      <div className="notice__body">
        <strong>{error.message}</strong>
        {error.hint && <p className="notice__hint">{error.hint}</p>}
        {error.detail && <code className="notice__detail">{error.detail}</code>}
      </div>
      {onDismiss && (
        <button
          type="button"
          className="notice__close"
          onClick={onDismiss}
          aria-label="Dismiss error"
        >
          ×
        </button>
      )}
    </div>
  );
}
