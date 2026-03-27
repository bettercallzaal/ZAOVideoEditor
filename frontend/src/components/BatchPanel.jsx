import { useState, useEffect } from 'react';
import { batchProcess, getBatchStatus, pollTask } from '../api/client';

export default function BatchPanel({ projects, onClose }) {
  const [selected, setSelected] = useState([]);
  const [quality, setQuality] = useState('standard');
  const [engine, setEngine] = useState('auto');
  const [refineTimestamps, setRefineTimestamps] = useState(true);
  const [generateContent, setGenerateContent] = useState(true);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState(0);
  const [statusMsg, setStatusMsg] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  // Filter projects that have uploads but no transcripts (candidates for batch)
  const candidates = projects.filter(p => {
    const s = p.stages || {};
    return s.upload === 'complete' && s.transcription !== 'complete';
  });

  const allProjects = projects.filter(p => {
    const s = p.stages || {};
    return s.upload === 'complete';
  });

  const toggleProject = (name) => {
    setSelected(prev =>
      prev.includes(name) ? prev.filter(n => n !== name) : [...prev, name]
    );
  };

  const selectAllCandidates = () => {
    setSelected(candidates.map(p => p.name));
  };

  const handleProcess = async () => {
    if (selected.length === 0) return;
    setRunning(true);
    setError('');
    setResult(null);
    setProgress(0);
    setStatusMsg('Starting batch processing...');

    try {
      const task = await batchProcess(selected, {
        quality,
        engine,
        refineTimestamps,
        generateContent,
      });

      const finalTask = await pollTask(task.task_id, (t) => {
        setProgress(t.progress || 0);
        setStatusMsg(t.message || '');
      }, 2000);

      setResult(finalTask.result);
      setProgress(100);
      setStatusMsg('Batch processing complete');
    } catch (e) {
      setError(e.message);
      setStatusMsg('Failed');
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="bg-[#0f1419] border border-gray-800 rounded-lg p-5 space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-medium text-[#e0ddaa]">Batch Processing</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            Select projects to process sequentially (assemble, transcribe, correct, generate content)
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-gray-500 hover:text-gray-300 text-sm"
        >
          Close
        </button>
      </div>

      {/* Project selection */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-sm text-gray-400">
            {candidates.length > 0
              ? `${candidates.length} project(s) need processing`
              : 'All projects are already transcribed'}
          </span>
          {candidates.length > 0 && (
            <button
              onClick={selectAllCandidates}
              className="text-xs text-[#e0ddaa] hover:underline"
            >
              Select all unprocessed
            </button>
          )}
        </div>

        <div className="max-h-48 overflow-y-auto space-y-1">
          {allProjects.map(p => {
            const isCandidate = candidates.some(c => c.name === p.name);
            const isSelected = selected.includes(p.name);
            return (
              <label
                key={p.name}
                className={`flex items-center gap-2 p-2 rounded cursor-pointer ${
                  isSelected ? 'bg-[#e0ddaa]/10 border border-[#e0ddaa]/30' : 'bg-[#1a1f2e] border border-transparent'
                } ${running ? 'opacity-60 pointer-events-none' : ''}`}
              >
                <input
                  type="checkbox"
                  checked={isSelected}
                  onChange={() => toggleProject(p.name)}
                  disabled={running}
                  className="rounded"
                />
                <span className="text-sm text-white flex-1">{p.name}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                  isCandidate
                    ? 'bg-yellow-900/50 text-yellow-300'
                    : 'bg-green-900/50 text-green-300'
                }`}>
                  {isCandidate ? 'Needs processing' : 'Already transcribed'}
                </span>
              </label>
            );
          })}
          {allProjects.length === 0 && (
            <p className="text-xs text-gray-500 py-4 text-center">
              No projects with uploaded videos found.
            </p>
          )}
        </div>
      </div>

      {/* Options */}
      {!running && (
        <div className="flex flex-wrap gap-4 items-end">
          <div>
            <label className="text-xs text-gray-500 block mb-1">Quality</label>
            <select
              value={quality}
              onChange={(e) => setQuality(e.target.value)}
              className="bg-[#1a1f2e] border border-gray-700 rounded px-2 py-1.5 text-sm text-white"
            >
              <option value="fast">Fast</option>
              <option value="standard">Standard</option>
              <option value="high">High</option>
            </select>
          </div>
          <div>
            <label className="text-xs text-gray-500 block mb-1">Engine</label>
            <select
              value={engine}
              onChange={(e) => setEngine(e.target.value)}
              className="bg-[#1a1f2e] border border-gray-700 rounded px-2 py-1.5 text-sm text-white"
            >
              <option value="auto">Auto</option>
              <option value="faster-whisper">faster-whisper</option>
              <option value="whisperx">WhisperX</option>
            </select>
          </div>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={refineTimestamps}
              onChange={(e) => setRefineTimestamps(e.target.checked)}
              className="rounded"
            />
            <span className="text-xs text-gray-400">Refine timestamps</span>
          </label>
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={generateContent}
              onChange={(e) => setGenerateContent(e.target.checked)}
              className="rounded"
            />
            <span className="text-xs text-gray-400">Generate content</span>
          </label>
        </div>
      )}

      {/* Progress */}
      {(running || progress > 0) && (
        <div className="space-y-1">
          <div className="flex justify-between text-xs">
            <span className="text-gray-400">{statusMsg}</span>
            <span className="text-[#e0ddaa]">{progress}%</span>
          </div>
          <div className="w-full bg-gray-800 rounded-full h-2">
            <div
              className="bg-[#e0ddaa] h-2 rounded-full transition-all duration-500"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {/* Results */}
      {result && (
        <div className="bg-[#1a1f2e] rounded p-3 space-y-1">
          <p className="text-sm text-green-300">
            Processed: {result.processed} | Failed: {result.failed}
          </p>
          {result.results?.map((r, i) => (
            <div key={i} className="text-xs flex items-center gap-2">
              <span className={r.status === 'complete' ? 'text-green-400' : 'text-red-400'}>
                {r.status === 'complete' ? 'OK' : 'FAIL'}
              </span>
              <span className="text-gray-300">{r.project}</span>
              {r.segments && <span className="text-gray-500">({r.segments} segments)</span>}
              {r.error && <span className="text-red-400">{r.error}</span>}
            </div>
          ))}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {/* Action */}
      <button
        onClick={handleProcess}
        disabled={running || selected.length === 0}
        className="w-full bg-[#e0ddaa] text-[#141e27] py-2.5 rounded-lg font-medium hover:bg-[#d4d19e] disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {running
          ? `Processing ${selected.length} project(s)...`
          : `Process ${selected.length} Selected Project(s)`}
      </button>
    </div>
  );
}
