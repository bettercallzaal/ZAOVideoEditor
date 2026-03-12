import { useState, useEffect } from 'react';
import ProgressBar from './ProgressBar';
import {
  getCurrentTranscript, applyCorrections, cleanupTranscript,
  saveTranscriptEdit, addDictEntry,
  diarizeSpeakers, renameSpeakers, pollTask,
  detectFillers, removeFillers,
} from '../api/client';

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

// Speaker color palette
const SPEAKER_COLORS = [
  'text-blue-400', 'text-green-400', 'text-purple-400', 'text-orange-400',
  'text-pink-400', 'text-cyan-400', 'text-yellow-400', 'text-red-400',
];

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
  const [fillerStats, setFillerStats] = useState(null);
  const [showSpeakerRename, setShowSpeakerRename] = useState(false);
  const [speakerNames, setSpeakerNames] = useState({});
  const [filterSpeaker, setFilterSpeaker] = useState(null);

  // Detect unique speakers
  const speakers = [...new Set(segments.map(s => s.speaker).filter(Boolean))];
  const speakerColorMap = {};
  speakers.forEach((s, i) => { speakerColorMap[s] = SPEAKER_COLORS[i % SPEAKER_COLORS.length]; });

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
      setSubsteps(steps.map((l, i) => ({ label: l, status: i === 0 ? 'active' : 'pending' })));
      setProgress(10);
      setProgressStatus('Applying dictionary corrections...');
      await applyCorrections(projectName);
      setProgress(50);
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

  const handleDiarize = async () => {
    setProcessing(true);
    setError('');
    setProgress(5);
    setProgressStatus('Starting speaker detection...');
    setSubsteps([{ label: 'Identify speakers', status: 'active' }]);
    try {
      const task = await diarizeSpeakers(projectName);
      await pollTask(task.task_id, (t) => {
        setProgress(t.progress);
        if (t.message) setProgressStatus(t.message);
      });
      setProgress(100);
      setProgressStatus('Speakers identified');
      setSubsteps([{ label: 'Identify speakers', status: 'complete' }]);
      await loadTranscript();
    } catch (e) {
      setError(e.message);
      setProgressStatus('Failed');
    } finally {
      setProcessing(false);
    }
  };

  const handleDetectFillers = async () => {
    setProcessing(true);
    setError('');
    setProgress(30);
    setProgressStatus('Scanning for filler words...');
    try {
      const data = await detectFillers(projectName);
      setFillerStats(data);
      setProgress(100);
      setProgressStatus(`Found ${data.total_fillers} fillers (${data.total_duration}s)`);
    } catch (e) {
      setError(e.message);
    } finally {
      setProcessing(false);
    }
  };

  const handleRemoveFillers = async (types = null) => {
    setProcessing(true);
    setError('');
    setProgress(30);
    setProgressStatus('Removing filler words...');
    try {
      const data = await removeFillers(projectName, types);
      setProgress(100);
      setProgressStatus(`Removed ${data.removed} fillers, saved ${data.duration_saved}s`);
      setFillerStats(null);
      await loadTranscript();
      onComplete();
    } catch (e) {
      setError(e.message);
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

  const handleRenameSpeakers = async () => {
    try {
      await renameSpeakers(projectName, speakerNames);
      setShowSpeakerRename(false);
      await loadTranscript();
    } catch (e) {
      setError(e.message);
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

  const filteredSegments = filterSpeaker
    ? segments.filter(s => s.speaker === filterSpeaker)
    : segments;

  return (
    <div className="space-y-4">
      {/* Actions */}
      {!processing && (
        <div className="flex gap-2 flex-wrap">
          <button onClick={handleCorrectAndClean}
            className="text-xs bg-gray-700 px-3 py-1.5 rounded text-gray-300 hover:bg-gray-600">
            Correct + Clean
          </button>
          <button onClick={handleDiarize}
            className="text-xs bg-gray-700 px-3 py-1.5 rounded text-gray-300 hover:bg-gray-600">
            Detect Speakers
          </button>
          <button onClick={handleDetectFillers}
            className="text-xs bg-gray-700 px-3 py-1.5 rounded text-gray-300 hover:bg-gray-600">
            Find Fillers
          </button>
          <button onClick={handleSaveAll}
            className="text-xs bg-[#e0ddaa] text-[#141e27] px-3 py-1.5 rounded font-medium hover:bg-[#d4d19e]">
            Save Edits
          </button>
          <button onClick={() => setShowDictAdd(!showDictAdd)}
            className="text-xs bg-gray-700 px-3 py-1.5 rounded text-gray-300 hover:bg-gray-600">
            + Dictionary
          </button>
          <span className="text-xs text-gray-500 self-center">
            Source: {source}
          </span>
        </div>
      )}

      {/* Speaker filter */}
      {speakers.length > 1 && (
        <div className="flex gap-2 items-center flex-wrap">
          <span className="text-xs text-gray-500">Filter:</span>
          <button
            onClick={() => setFilterSpeaker(null)}
            className={`text-xs px-2 py-0.5 rounded ${!filterSpeaker ? 'bg-[#e0ddaa] text-[#141e27]' : 'bg-gray-700 text-gray-400'}`}
          >All</button>
          {speakers.map(s => (
            <button key={s} onClick={() => setFilterSpeaker(s)}
              className={`text-xs px-2 py-0.5 rounded ${filterSpeaker === s ? 'bg-[#e0ddaa] text-[#141e27]' : 'bg-gray-700 text-gray-400'}`}>
              {s}
            </button>
          ))}
          {!showSpeakerRename && (
            <button onClick={() => setShowSpeakerRename(true)}
              className="text-xs text-[#e0ddaa] hover:underline ml-2">
              Rename
            </button>
          )}
        </div>
      )}

      {/* Speaker rename */}
      {showSpeakerRename && (
        <div className="bg-[#1a1f2e] p-3 rounded space-y-2">
          <p className="text-xs text-gray-400">Rename speakers:</p>
          {speakers.map(s => (
            <div key={s} className="flex gap-2 items-center">
              <span className={`text-xs font-mono w-24 ${speakerColorMap[s]}`}>{s}</span>
              <input
                value={speakerNames[s] || ''}
                onChange={(e) => setSpeakerNames(prev => ({ ...prev, [s]: e.target.value }))}
                placeholder={`e.g., Host, ${s}`}
                className="flex-1 bg-[#0f1419] border border-gray-700 rounded px-2 py-1 text-sm text-white"
              />
            </div>
          ))}
          <div className="flex gap-2">
            <button onClick={handleRenameSpeakers}
              className="text-xs bg-[#e0ddaa] text-[#141e27] px-3 py-1 rounded hover:bg-[#d4d19e]">
              Apply
            </button>
            <button onClick={() => setShowSpeakerRename(false)}
              className="text-xs bg-gray-700 text-gray-300 px-3 py-1 rounded">
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Filler stats */}
      {fillerStats && (
        <div className="bg-[#1a1f2e] rounded p-3 space-y-2">
          <div className="flex justify-between items-center">
            <p className="text-sm text-gray-300">
              Found <span className="text-[#e0ddaa] font-medium">{fillerStats.total_fillers}</span> fillers
              ({fillerStats.total_duration}s of audio)
            </p>
            <button onClick={() => handleRemoveFillers()}
              className="text-xs bg-red-800 text-red-200 px-3 py-1 rounded hover:bg-red-700">
              Remove All
            </button>
          </div>
          <div className="flex gap-2 flex-wrap">
            {Object.entries(fillerStats.stats).sort((a, b) => b[1] - a[1]).map(([word, count]) => (
              <span key={word} className="text-xs bg-gray-800 text-gray-400 px-2 py-0.5 rounded">
                "{word}" x{count}
              </span>
            ))}
          </div>
          <div className="flex gap-2">
            <button onClick={() => handleRemoveFillers(['filler_word'])}
              className="text-xs bg-gray-700 text-gray-300 px-3 py-1 rounded hover:bg-gray-600">
              Remove um/uh only
            </button>
            <button onClick={() => handleRemoveFillers(['filler_word', 'filler_phrase'])}
              className="text-xs bg-gray-700 text-gray-300 px-3 py-1 rounded hover:bg-gray-600">
              Remove fillers + phrases
            </button>
            <button onClick={() => setFillerStats(null)}
              className="text-xs text-gray-500 hover:text-gray-300">
              Dismiss
            </button>
          </div>
        </div>
      )}

      {/* Add to dictionary */}
      {showDictAdd && (
        <div className="flex gap-2 bg-[#1a1f2e] p-3 rounded">
          <input value={dictWord} onChange={(e) => setDictWord(e.target.value)}
            placeholder="Wrong spelling..."
            className="flex-1 bg-[#0f1419] border border-gray-700 rounded px-2 py-1 text-sm text-white" />
          <input value={dictCorrection} onChange={(e) => setDictCorrection(e.target.value)}
            placeholder="Correct spelling..."
            className="flex-1 bg-[#0f1419] border border-gray-700 rounded px-2 py-1 text-sm text-white" />
          <button onClick={handleAddToDict}
            className="text-xs bg-[#e0ddaa] text-[#141e27] px-3 py-1 rounded hover:bg-[#d4d19e]">
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
          {filteredSegments.map((seg) => (
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
              {seg.speaker && (
                <span className={`text-xs font-mono shrink-0 w-20 truncate ${speakerColorMap[seg.speaker] || 'text-gray-500'}`}>
                  {seg.speaker}
                </span>
              )}
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
                      <button onClick={() => handleSaveEdit(seg.id)}
                        className="text-xs bg-green-700 px-2 py-1 rounded text-white">OK</button>
                      <button onClick={() => setEditingId(null)}
                        className="text-xs bg-gray-700 px-2 py-1 rounded text-gray-300">Cancel</button>
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
