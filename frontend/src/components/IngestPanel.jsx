import { useState, useEffect } from 'react';
import { getIngestSources, probeIngestUrl, ingestUrl, pollTask } from '../api/client';

function slugify(title) {
  return (title || '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 50);
}

export default function IngestPanel({ onClose, onComplete }) {
  const [url, setUrl] = useState('');
  const [projectName, setProjectName] = useState('');
  const [sources, setSources] = useState([]);
  const [available, setAvailable] = useState(true);
  const [probe, setProbe] = useState(null);
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState('');

  useEffect(() => {
    getIngestSources()
      .then((d) => { setSources(d.sources || []); setAvailable(d.available); })
      .catch(() => setAvailable(false));
  }, []);

  const handleProbe = async () => {
    setError('');
    setProbe(null);
    if (!url.trim()) return;
    setBusy(true);
    try {
      const info = await probeIngestUrl(url.trim());
      setProbe(info);
      if (!projectName && info.title) setProjectName(slugify(info.title));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleIngest = async () => {
    setError('');
    if (!url.trim() || !projectName.trim()) {
      setError('A URL and a project name are both required.');
      return;
    }
    setBusy(true);
    setProgress({ progress: 0, message: 'Queued...' });
    try {
      const task = await ingestUrl(url.trim(), projectName.trim());
      const done = await pollTask(task.task_id, (t) => setProgress(t));
      if (onComplete) onComplete(projectName.trim(), done.result);
    } catch (e) {
      setError(e.message);
      setProgress(null);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="border border-gray-800 rounded-lg p-5 bg-[#141a21]">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-lg font-semibold text-[#e0ddaa]">Ingest from livestream / URL</h2>
        <button onClick={onClose} className="text-gray-500 hover:text-gray-300 text-sm">Close</button>
      </div>

      {!available && (
        <p className="text-sm text-amber-400 mb-3">
          yt-dlp is not installed. Run <code className="text-amber-300">pip install yt-dlp</code> to enable URL ingest.
        </p>
      )}

      <p className="text-xs text-gray-500 mb-3">
        Pull a finished stream or VOD by URL: {sources.map((s) => s.label).join(', ')}.
      </p>

      <label className="block text-sm text-gray-400 mb-1">Source URL</label>
      <div className="flex gap-2 mb-3">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://youtube.com/watch?v=... or .m3u8 / .mp4"
          className="flex-1 bg-[#0f1419] border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-[#e0ddaa] outline-none"
          disabled={busy || !available}
        />
        <button
          onClick={handleProbe}
          disabled={busy || !available || !url.trim()}
          className="text-sm border border-gray-700 px-3 py-2 rounded text-gray-300 hover:border-[#e0ddaa] disabled:opacity-40"
        >
          Check
        </button>
      </div>

      {probe && (
        <div className="text-xs text-gray-400 mb-3 bg-[#0f1419] border border-gray-800 rounded px-3 py-2">
          <div className="text-gray-200">{probe.title || '(no title)'}</div>
          <div className="mt-1">
            {probe.extractor && <span className="mr-3">Source: {probe.extractor}</span>}
            {probe.duration != null && <span className="mr-3">Duration: {Math.round(probe.duration)}s</span>}
            {probe.is_live && <span className="text-amber-400">LIVE - ingest the VOD after it ends</span>}
          </div>
        </div>
      )}

      <label className="block text-sm text-gray-400 mb-1">Project name</label>
      <input
        type="text"
        value={projectName}
        onChange={(e) => setProjectName(e.target.value)}
        placeholder="my-stream-2026-06-10"
        className="w-full bg-[#0f1419] border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 focus:border-[#e0ddaa] outline-none mb-4"
        disabled={busy || !available}
      />

      {progress && (
        <div className="mb-3">
          <div className="h-2 bg-gray-800 rounded overflow-hidden">
            <div className="h-full bg-[#e0ddaa] transition-all" style={{ width: `${progress.progress || 0}%` }} />
          </div>
          <p className="text-xs text-gray-400 mt-1">{progress.message}</p>
        </div>
      )}

      {error && <p className="text-sm text-red-400 mb-3">{error}</p>}

      <button
        onClick={handleIngest}
        disabled={busy || !available || !url.trim() || !projectName.trim()}
        className="bg-[#e0ddaa] text-[#0f1419] font-semibold px-4 py-2 rounded text-sm hover:opacity-90 disabled:opacity-40"
      >
        {busy ? 'Ingesting...' : 'Ingest into new project'}
      </button>
    </div>
  );
}
