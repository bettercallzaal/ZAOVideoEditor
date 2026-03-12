import { useState, useEffect } from 'react';
import ProgressBar from './ProgressBar';
import {
  getCurrentTranscript, applyCorrections, cleanupTranscript,
  saveTranscriptEdit, addDictEntry,
} from '../api/client';

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

export default function TranscriptEditor({ projectName, stages, onSeek, onComplete }) {
  const [segments, setSegments] = useState([]);
  const [source, setSource] = useState('');
  const [loading, setLoading] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState('');
  const [substeps, setSubsteps] = useState([]);
  const [error, setError] = useState('');
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState('');
  const [dictWord, setDictWord] = useState('');
  const [dictCorrection, setDictCorrection] = useState('');
  const [showDictAdd, setShowDictAdd] = useState(false);

  const loadTranscript = async () => {
    try {
      setLoading(true);
      const data = await getCurrentTranscript(projectName);
      setSegments(data.segments || []);
      setSource(data.source || '');
    } catch (e) {
      setError('No transcript found. Run transcription first.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (stages.transcription === 'complete') loadTranscript();
  }, [stages.transcription]);

  const handleCorrectAndClean = async () => {
    setProcessing(true);
    setError('');
    setProgress(0);

    const steps = ['Apply dictionary corrections', 'Clean and polish transcript'];

    try {
      // Step 1
      setSubsteps(steps.map((l, i) => ({ label: l, status: i === 0 ? 'active' : 'pending' })));
      setProgress(10);
      setProgressStatus('Applying dictionary corrections...');
      await applyCorrections(projectName);
      setProgress(50);

      // Step 2
      setSubsteps(steps.map((l, i) => ({ label: l, status: i === 0 ? 'complete' : 'active' })));
      setProgressStatus('Cleaning and polishing transcript...');
      await cleanupTranscript(projectName);
      setProgress(100);

      setSubsteps(steps.map((l) => ({ label: l, status: 'complete' })));
      setProgressStatus('Transcript corrected and polished');
      await loadTranscript();
      onComplete();
    } catch (e) {
      setError(e.message);
      setProgressStatus('Failed');
    } finally {
      setProcessing(false);
    }
  };

  const handleSaveAll = async () => {
    setProcessing(true);
    setProgress(30);
    setProgressStatus('Saving edits...');
    setSubsteps([{ label: 'Save edited transcript', status: 'active' }]);
    try {
      await saveTranscriptEdit(projectName, segments);
      setProgress(100);
      setProgressStatus('Edits saved');
      setSubsteps([{ label: 'Save edited transcript', status: 'complete' }]);
      onComplete();
    } catch (e) {
      setError(`Save failed: ${e.message}`);
    } finally {
      setProcessing(false);
    }
  };

  const handleEdit = (seg) => {
    setEditingId(seg.id);
    setEditText(seg.text);
  };

  const handleSaveEdit = (segId) => {
    setSegments(prev =>
      prev.map(s => s.id === segId ? { ...s, text: editText } : s)
    );
    setEditingId(null);
  };

  const handleAddToDict = async () => {
    if (!dictWord.trim() || !dictCorrection.trim()) return;
    try {
      await addDictEntry(dictWord.trim(), dictCorrection.trim());
      setProgressStatus(`Added "${dictWord}" -> "${dictCorrection}" to dictionary`);
      setProgress(100);
      setSubsteps([{ label: `"${dictWord}" -> "${dictCorrection}"`, status: 'complete' }]);
      setDictWord('');
      setDictCorrection('');
      setShowDictAdd(false);
    } catch (e) {
      setError(`Failed to add: ${e.message}`);
    }
  };

  if (stages.transcription !== 'complete') {
    return (
      <div className="text-gray-500 text-sm">
        Run transcription first (Upload tab).
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Actions */}
      {!processing && (
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={handleCorrectAndClean}
            className="text-xs bg-gray-700 px-3 py-1.5 rounded text-gray-300 hover:bg-gray-600"
          >
            Correct + Clean
          </button>
          <button
            onClick={handleSaveAll}
            className="text-xs bg-[#e0ddaa] text-[#141e27] px-3 py-1.5 rounded font-medium hover:bg-[#d4d19e]"
          >
            Save Edits
          </button>
          <button
            onClick={() => setShowDictAdd(!showDictAdd)}
            className="text-xs bg-gray-700 px-3 py-1.5 rounded text-gray-300 hover:bg-gray-600"
          >
            + Dictionary
          </button>
          <span className="text-xs text-gray-500 self-center">
            Source: {source}
          </span>
        </div>
      )}

      {/* Add to dictionary */}
      {showDictAdd && (
        <div className="flex gap-2 bg-[#1a1f2e] p-3 rounded">
          <input
            value={dictWord}
            onChange={(e) => setDictWord(e.target.value)}
            placeholder="Wrong spelling..."
            className="flex-1 bg-[#0f1419] border border-gray-700 rounded px-2 py-1 text-sm text-white"
          />
          <input
            value={dictCorrection}
            onChange={(e) => setDictCorrection(e.target.value)}
            placeholder="Correct spelling..."
            className="flex-1 bg-[#0f1419] border border-gray-700 rounded px-2 py-1 text-sm text-white"
          />
          <button
            onClick={handleAddToDict}
            className="text-xs bg-[#e0ddaa] text-[#141e27] px-3 py-1 rounded hover:bg-[#d4d19e]"
          >
            Add
          </button>
        </div>
      )}

      {/* Progress */}
      {(processing || progress > 0) && (
        <ProgressBar progress={progress} status={progressStatus} substeps={substeps} />
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">{error}</div>
      )}

      {/* Segments */}
      {loading ? (
        <div className="flex items-center gap-2 text-gray-400 text-sm py-4">
          <span className="inline-block w-4 h-4 border-2 border-gray-400 border-t-transparent rounded-full animate-spin" />
          Loading transcript...
        </div>
      ) : (
        <div className="space-y-1">
          {segments.map((seg) => (
            <div
              key={seg.id}
              className="group flex gap-2 hover:bg-[#1a1f2e] rounded p-2 transition-colors"
            >
              <button
                onClick={() => onSeek(seg.start)}
                className="text-[#e0ddaa] text-xs font-mono shrink-0 hover:underline w-12 text-right"
              >
                {formatTime(seg.start)}
              </button>
              <div className="flex-1 min-w-0">
                {editingId === seg.id ? (
                  <div className="flex gap-2">
                    <textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      className="flex-1 bg-[#0f1419] border border-gray-600 rounded px-2 py-1 text-sm text-white resize-none"
                      rows={2}
                      autoFocus
                    />
                    <div className="flex flex-col gap-1">
                      <button
                        onClick={() => handleSaveEdit(seg.id)}
                        className="text-xs bg-green-700 px-2 py-1 rounded text-white"
                      >
                        OK
                      </button>
                      <button
                        onClick={() => setEditingId(null)}
                        className="text-xs bg-gray-700 px-2 py-1 rounded text-gray-300"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <p
                    onClick={() => handleEdit(seg)}
                    className="text-sm text-gray-200 cursor-text hover:text-white"
                  >
                    {seg.text}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
