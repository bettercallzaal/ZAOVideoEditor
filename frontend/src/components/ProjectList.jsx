import { useState } from 'react';

export default function ProjectList({ projects, onCreate, onOpen, onDelete }) {
  const [newName, setNewName] = useState('');
  const [creating, setCreating] = useState(false);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!newName.trim()) return;
    setCreating(true);
    try {
      await onCreate(newName.trim());
      setNewName('');
    } finally {
      setCreating(false);
    }
  };

  const stageLabels = {
    upload: 'Upload',
    assembly: 'Assembly',
    transcription: 'Transcription',
    correction: 'Correction',
    cleanup: 'Cleanup',
    editing: 'Editing',
    captions: 'Captions',
    burn_captions: 'Burn',
    metadata: 'Metadata',
    export: 'Export',
  };

  return (
    <div>
      <form onSubmit={handleCreate} className="flex gap-3 mb-8">
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New project name..."
          className="flex-1 bg-[#1a1f2e] border border-gray-700 rounded-lg px-4 py-2 text-white placeholder-gray-500 focus:outline-none focus:border-[#e0ddaa]"
        />
        <button
          type="submit"
          disabled={creating || !newName.trim()}
          className="bg-[#e0ddaa] text-[#141e27] px-6 py-2 rounded-lg font-medium hover:bg-[#d4d19e] disabled:opacity-50"
        >
          {creating ? 'Creating...' : 'Create Project'}
        </button>
      </form>

      {projects.length === 0 ? (
        <p className="text-gray-500 text-center py-12">No projects yet. Create one above.</p>
      ) : (
        <div className="space-y-3">
          {projects.map((p) => (
            <div
              key={p.name}
              className="bg-[#1a1f2e] border border-gray-800 rounded-lg p-4 hover:border-gray-600 transition-colors"
            >
              <div className="flex items-center justify-between mb-3">
                <h3
                  className="text-lg font-medium text-white cursor-pointer hover:text-[#e0ddaa]"
                  onClick={() => onOpen(p.name)}
                >
                  {p.name}
                </h3>
                <div className="flex gap-2">
                  <button
                    onClick={() => onOpen(p.name)}
                    className="bg-[#e0ddaa] text-[#141e27] px-4 py-1.5 rounded text-sm font-medium hover:bg-[#d4d19e]"
                  >
                    Open
                  </button>
                  <button
                    onClick={() => onDelete(p.name)}
                    className="bg-red-900/50 text-red-300 px-3 py-1.5 rounded text-sm hover:bg-red-900/80"
                  >
                    Delete
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {Object.entries(p.stages || {}).map(([key, status]) => (
                  <span
                    key={key}
                    className={`text-xs px-2 py-0.5 rounded ${
                      status === 'complete'
                        ? 'bg-green-900/50 text-green-300'
                        : status === 'in_progress'
                        ? 'bg-yellow-900/50 text-yellow-300'
                        : 'bg-gray-800 text-gray-500'
                    }`}
                  >
                    {stageLabels[key] || key}
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
