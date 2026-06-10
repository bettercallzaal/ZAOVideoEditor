import { useState, useEffect } from 'react';
import ProgressBar from './ProgressBar';
import { formatTime } from '../utils/format';
import {
  detectHighlights, exportClip, batchExportClips, listClips,
  getClipDownloadUrl, pollTask,
} from '../api/client';

const ASPECTS = ['9:16', '1:1', '16:9'];

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
  const [aspects, setAspects] = useState(['9:16']);
  const [burnCaptions, setBurnCaptions] = useState(true);
  const [speakerAware, setSpeakerAware] = useState(false);

  const hasTranscript = stages.transcription === 'complete';

  const toggleAspect = (a) => {
    setAspects((prev) => prev.includes(a) ? prev.filter((x) => x !== a) : [...prev, a]);
  };

  const opts = () => ({
    aspects: aspects.length ? aspects : ['9:16'],
    burnCaptions, speakerAware,
  });

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

  const handleExport = async (highlight) => {
    setProcessing(true);
    setError('');
    setProgress(10);
    setProgressStatus(`Exporting "${highlight.title}"...`);
    try {
      const task = await exportClip(projectName, highlight.start, highlight.end, highlight.title, opts());
      await pollTask(task.task_id, (t) => {
        setProgress(t.progress);
        if (t.message) setProgressStatus(t.message);
      });
      setProgressStatus('Clip exported');
      await loadClips();
    } catch (e) {
      setError(e.message);
    } finally {
      setProcessing(false);
    }
  };

  const handleBatch = async () => {
    setProcessing(true);
    setError('');
    setProgress(5);
    setProgressStatus('Clipping the whole stream...');
    try {
      const task = await batchExportClips(projectName, {
        count, minDuration: minDur, maxDuration: maxDur, ...opts(),
        highlights: highlights.length ? highlights : null,
      });
      await pollTask(task.task_id, (t) => {
        setProgress(t.progress);
        if (t.message) setProgressStatus(t.message);
      });
      setProgressStatus('All clips exported');
      await loadClips();
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
    } catch { /* no clips yet */ }
  };

  useEffect(() => { loadClips(); }, []);

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
        {!processing && (
          <button onClick={handleBatch}
            className="bg-[#e0ddaa] text-[#141e27] px-4 py-1.5 rounded text-sm font-medium hover:bg-[#d4d19e]">
            Clip Whole Stream
          </button>
        )}
      </div>

      {/* Output options */}
      <div className="flex gap-4 items-center flex-wrap text-xs text-gray-400">
        <div className="flex gap-2 items-center">
          <span>Aspects:</span>
          {ASPECTS.map((a) => (
            <button key={a} onClick={() => toggleAspect(a)}
              className={`px-2 py-0.5 rounded border ${
                aspects.includes(a)
                  ? 'border-[#e0ddaa] text-[#e0ddaa]'
                  : 'border-gray-700 text-gray-500'
              }`}>
              {a}
            </button>
          ))}
        </div>
        <label className="flex gap-1 items-center cursor-pointer">
          <input type="checkbox" checked={burnCaptions} onChange={(e) => setBurnCaptions(e.target.checked)} />
          Burn captions
        </label>
        <label className="flex gap-1 items-center cursor-pointer">
          <input type="checkbox" checked={speakerAware} onChange={(e) => setSpeakerAware(e.target.checked)} />
          Speaker-aware crop
        </label>
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
                <span className={`text-xs px-2 py-0.5 rounded ${
                  h.score >= 70 ? 'bg-green-900/40 text-green-400' :
                  h.score >= 40 ? 'bg-yellow-900/40 text-yellow-400' :
                  'bg-gray-700 text-gray-400'
                }`}>
                  {h.score}
                </span>
              </div>
              <div className="flex gap-2 text-xs flex-wrap">
                {h.reasons.map((r, j) => (
                  <span key={j} className="bg-gray-800 text-gray-400 px-2 py-0.5 rounded">{r}</span>
                ))}
              </div>
              <button onClick={() => handleExport(h)}
                className="text-xs bg-gray-700 text-gray-300 px-3 py-1 rounded hover:bg-gray-600">
                Export ({(aspects.length ? aspects : ['9:16']).join(', ')})
              </button>
            </div>
          ))}
        </div>
      )}

      {/* Exported clips */}
      {clips.length > 0 && (
        <div className="space-y-2">
          <h3 className="text-sm font-medium text-gray-300">Exported Clips</h3>
          {clips.map((c, i) => (
            <div key={i} className="bg-[#1a1f2e] rounded p-2 space-y-1">
              <div className="flex justify-between items-center">
                <span className="text-sm text-gray-300">{c.filename}</span>
                <a href={getClipDownloadUrl(projectName, c.filename)}
                  className="text-xs text-[#e0ddaa] hover:underline" download>
                  Download
                </a>
              </div>
              {c.copy && (
                <div className="text-xs text-gray-400 border-t border-gray-800 pt-1">
                  <p className="text-gray-200">{c.copy.title}</p>
                  <p>{c.copy.caption}</p>
                  {c.copy.hashtags?.length > 0 && (
                    <p className="text-[#e0ddaa]">{c.copy.hashtags.join(' ')}</p>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {highlights.length === 0 && clips.length === 0 && !processing && (
        <p className="text-xs text-gray-500">
          No clips yet. "Find Highlights" to review moments, or "Clip Whole Stream" to render them all at once.
        </p>
      )}
    </div>
  );
}
