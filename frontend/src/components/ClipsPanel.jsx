import { useState } from 'react';
import ProgressBar from './ProgressBar';
import {
  detectHighlights, exportClip, listClips,
  getClipDownloadUrl, pollTask,
} from '../api/client';

function formatTime(s) {
  const m = Math.floor(s / 60);
  const sec = Math.floor(s % 60);
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

export default function ClipsPanel({ projectName, stages, onSeek }) {
  const [highlights, setHighlights] = useState([]);
  const [clips, setClips] = useState([]);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState('');
  const [error, setError] = useState('');
  const [count, setCount] = useState(5);
  const [minDur, setMinDur] = useState(30);
  const [maxDur, setMaxDur] = useState(90);

  const hasTranscript = stages.transcription === 'complete';

  const handleDetect = async () => {
    setProcessing(true);
    setError('');
    setProgress(20);
    setProgressStatus('Analyzing transcript for highlights...');
    try {
      const data = await detectHighlights(projectName, count, minDur, maxDur);
      setHighlights(data.highlights);
      setProgress(100);
      setProgressStatus(`Found ${data.count} highlights`);
    } catch (e) {
      setError(e.message);
    } finally {
      setProcessing(false);
    }
  };

  const handleExport = async (highlight, vertical = false) => {
    setProcessing(true);
    setError('');
    setProgress(10);
    setProgressStatus(`Exporting "${highlight.title}"...`);
    try {
      const task = await exportClip(
        projectName, highlight.start, highlight.end,
        highlight.title, vertical,
      );
      await pollTask(task.task_id, (t) => {
        setProgress(t.progress);
        if (t.message) setProgressStatus(t.message);
      });
      setProgress(100);
      setProgressStatus('Clip exported');
      // Refresh clips list
      const clipList = await listClips(projectName);
      setClips(clipList);
    } catch (e) {
      setError(e.message);
    } finally {
      setProcessing(false);
    }
  };

  const loadClips = async () => {
    try {
      const clipList = await listClips(projectName);
      setClips(clipList);
    } catch (e) { /* no clips yet */ }
  };

  if (!hasTranscript) {
    return <p className="text-gray-500 text-sm">Complete transcription first.</p>;
  }

  return (
    <div className="space-y-4">
      {/* Settings */}
      <div className="flex gap-3 items-end flex-wrap">
        <div>
          <label className="text-xs text-gray-500 block mb-1">Clips</label>
          <input type="number" value={count} onChange={(e) => setCount(+e.target.value)}
            min={1} max={20}
            className="w-16 bg-[#1a1f2e] border border-gray-700 rounded px-2 py-1 text-sm text-white" />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Min (sec)</label>
          <input type="number" value={minDur} onChange={(e) => setMinDur(+e.target.value)}
            min={10} max={120}
            className="w-16 bg-[#1a1f2e] border border-gray-700 rounded px-2 py-1 text-sm text-white" />
        </div>
        <div>
          <label className="text-xs text-gray-500 block mb-1">Max (sec)</label>
          <input type="number" value={maxDur} onChange={(e) => setMaxDur(+e.target.value)}
            min={30} max={300}
            className="w-16 bg-[#1a1f2e] border border-gray-700 rounded px-2 py-1 text-sm text-white" />
        </div>
        {!processing && (
          <button onClick={handleDetect}
            className="bg-[#e0ddaa] text-[#141e27] px-4 py-1.5 rounded text-sm font-medium hover:bg-[#d4d19e]">
            Find Highlights
          </button>
        )}
      </div>

      {/* Progress */}
      {(processing || progress > 0) && (
        <ProgressBar progress={progress} status={progressStatus} />
      )}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">{error}</div>
      )}

      {/* Highlights */}
      {highlights.length > 0 && !processing && (
        <div className="space-y-3">
          <h3 className="text-sm font-medium text-gray-300">Detected Highlights</h3>
          {highlights.map((h, i) => (
            <div key={i} className="bg-[#1a1f2e] rounded p-3 space-y-2">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <p className="text-sm text-gray-200 font-medium">{h.title}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    <button onClick={() => onSeek(h.start)} className="text-[#e0ddaa] hover:underline">
                      {formatTime(h.start)}
                    </button>
                    {' - '}
                    <button onClick={() => onSeek(h.end)} className="text-[#e0ddaa] hover:underline">
                      {formatTime(h.end)}
                    </button>
                    {' '}({h.duration}s)
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs px-2 py-0.5 rounded ${
                    h.score >= 70 ? 'bg-green-900/40 text-green-400' :
                    h.score >= 40 ? 'bg-yellow-900/40 text-yellow-400' :
                    'bg-gray-700 text-gray-400'
                  }`}>
                    {h.score}
                  </span>
                </div>
              </div>
              <div className="flex gap-2 text-xs flex-wrap">
                {h.reasons.map((r, j) => (
                  <span key={j} className="bg-gray-800 text-gray-400 px-2 py-0.5 rounded">{r}</span>
                ))}
              </div>
              <div className="flex gap-2">
                <button onClick={() => handleExport(h, false)}
                  className="text-xs bg-gray-700 text-gray-300 px-3 py-1 rounded hover:bg-gray-600">
                  Export Clip
                </button>
                <button onClick={() => handleExport(h, true)}
                  className="text-xs bg-gray-700 text-gray-300 px-3 py-1 rounded hover:bg-gray-600">
                  Export Vertical (9:16)
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Exported clips */}
      {clips.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-300">Exported Clips</h3>
          {clips.map((name, i) => (
            <div key={i} className="flex justify-between items-center bg-[#1a1f2e] rounded p-2">
              <span className="text-sm text-gray-300">{name}</span>
              <a href={getClipDownloadUrl(projectName, name)}
                className="text-xs text-[#e0ddaa] hover:underline" download>
                Download
              </a>
            </div>
          ))}
        </div>
      )}

      {highlights.length === 0 && clips.length === 0 && !processing && (
        <button onClick={loadClips} className="text-xs text-gray-500 hover:text-gray-300">
          Load existing clips
        </button>
      )}
    </div>
  );
}
