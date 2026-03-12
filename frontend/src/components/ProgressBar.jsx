export default function ProgressBar({ progress, status, substeps }) {
  return (
    <div className="bg-[#1a1f2e] rounded-lg p-4 space-y-3">
      {/* Status text */}
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-200">{status}</span>
        {progress > 0 && progress < 100 && (
          <span className="text-xs text-gray-400">{Math.round(progress)}%</span>
        )}
      </div>

      {/* Main progress bar */}
      <div className="w-full bg-gray-800 rounded-full h-2.5 overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-500 ease-out"
          style={{
            width: `${Math.max(progress, 2)}%`,
            background: progress >= 100
              ? '#4ade80'
              : 'linear-gradient(90deg, #e0ddaa, #d4d19e)',
          }}
        />
      </div>

      {/* Substeps */}
      {substeps && substeps.length > 0 && (
        <div className="space-y-1.5 pt-1">
          {substeps.map((step, i) => (
            <div key={i} className="flex items-center gap-2 text-xs">
              {step.status === 'complete' && (
                <span className="text-green-400 w-4 text-center">&#10003;</span>
              )}
              {step.status === 'active' && (
                <span className="w-4 text-center">
                  <span className="inline-block w-2.5 h-2.5 border-2 border-[#e0ddaa] border-t-transparent rounded-full animate-spin" />
                </span>
              )}
              {step.status === 'pending' && (
                <span className="text-gray-600 w-4 text-center">&#9675;</span>
              )}
              <span className={
                step.status === 'complete' ? 'text-gray-400' :
                step.status === 'active' ? 'text-gray-200' :
                'text-gray-600'
              }>
                {step.label}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
