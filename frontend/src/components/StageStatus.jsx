const STAGE_ORDER = [
  'upload', 'assembly', 'transcription', 'correction',
  'cleanup', 'editing', 'captions', 'burn_captions', 'metadata', 'export',
];

const SHORT_LABELS = {
  upload: 'UL',
  assembly: 'AS',
  transcription: 'TR',
  correction: 'CR',
  cleanup: 'CL',
  editing: 'ED',
  captions: 'CP',
  burn_captions: 'BN',
  metadata: 'MT',
  export: 'EX',
};

export default function StageStatus({ stages }) {
  return (
    <div className="flex gap-1">
      {STAGE_ORDER.map((key) => {
        const status = stages[key] || 'not_started';
        const colors = {
          complete: 'bg-green-700 text-green-100',
          in_progress: 'bg-yellow-700 text-yellow-100',
          error: 'bg-red-700 text-red-100',
          not_started: 'bg-gray-800 text-gray-500',
        };
        return (
          <span
            key={key}
            title={key.replace(/_/g, ' ')}
            className={`text-[10px] px-1.5 py-0.5 rounded ${colors[status]}`}
          >
            {SHORT_LABELS[key]}
          </span>
        );
      })}
    </div>
  );
}
