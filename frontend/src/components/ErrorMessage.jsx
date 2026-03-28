export default function ErrorMessage({ error, onRetry, onDismiss }) {
  if (!error) return null;

  const message = typeof error === 'string' ? error : error.message || 'An error occurred';
  const action = typeof error === 'object' && error !== null ? error.action : undefined;

  return (
    <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300 relative">
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="absolute top-2 right-2 text-red-400 hover:text-red-200 text-xs leading-none"
          aria-label="Dismiss"
        >
          x
        </button>
      )}
      <p>{message}</p>
      {action && (
        <p className="mt-1 text-xs text-red-400">{action}</p>
      )}
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-2 text-xs bg-red-800 text-red-200 px-3 py-1 rounded hover:bg-red-700"
        >
          Retry
        </button>
      )}
    </div>
  );
}
