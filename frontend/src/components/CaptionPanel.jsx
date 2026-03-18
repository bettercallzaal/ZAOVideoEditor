import { useState, useEffect, useCallback } from 'react';
import ProgressBar from './ProgressBar';
import CaptionTimeline from './CaptionTimeline';
import { formatTime } from '../utils/format';
import {
  generateCaptions, getCaptions, saveCaptions,
  burnCaptions, getSrt, getAss, pollTask, getAvailableTools,
} from '../api/client';

const CAPTION_STYLES = [
  {
    id: 'classic',
    name: 'Classic',
    description: 'Clean white text with black outline',
    preview: { text: '#FFFFFF', outline: '#000000', bg: null, uppercase: false },
  },
  {
    id: 'box',
    name: 'Box',
    description: 'White text on dark semi-transparent box',
    preview: { text: '#FFFFFF', outline: null, bg: 'rgba(0,0,0,0.7)', uppercase: false },
  },
  {
    id: 'bold_pop',
    name: 'Bold Pop',
    description: 'Large bold uppercase with thick outline',
    preview: { text: '#FFFFFF', outline: '#000000', bg: null, uppercase: true },
  },
  {
    id: 'highlight',
    name: 'Highlight',
    description: 'Word-by-word highlight (Hormozi style)',
    preview: { text: '#666666', outline: '#000000', bg: null, uppercase: true, highlight: '#FFFFFF' },
  },
  {
    id: 'brand_light',
    name: 'Brand Light',
    description: 'Dark text on beige background',
    preview: { text: '#141e27', outline: null, bg: '#e0ddaa', uppercase: false },
  },
  {
    id: 'brand_dark',
    name: 'Brand Dark',
    description: 'Beige text on dark background',
    preview: { text: '#e0ddaa', outline: null, bg: '#141e27', uppercase: false },
  },
];

function StylePreview({ style, selected, onSelect }) {
  const p = style.preview;
  const sampleWords = p.uppercase ? 'THIS IS HOW' : 'This is how';

  return (
    <button
      onClick={() => onSelect(style.id)}
      className={`text-left p-2 rounded-lg border-2 transition-all ${
        selected
          ? 'border-[#e0ddaa] bg-[#1a1f2e]'
          : 'border-gray-700/50 bg-[#0f1419] hover:border-gray-600'
      }`}
    >
      <div className="bg-gray-900 rounded h-10 flex items-end justify-center pb-1.5 mb-1 relative overflow-hidden">
        <div className="absolute inset-0 opacity-20">
          <div className="absolute top-2 left-2 right-5 h-0.5 bg-gray-600 rounded" />
          <div className="absolute top-4 left-2 right-8 h-0.5 bg-gray-600 rounded" />
        </div>
        <span
          className="text-[10px] font-bold relative z-10 px-1 py-0.5 rounded"
          style={{
            color: p.text,
            backgroundColor: p.bg || 'transparent',
            textShadow: p.outline
              ? `1px 1px 0 ${p.outline}, -1px -1px 0 ${p.outline}, 1px -1px 0 ${p.outline}, -1px 1px 0 ${p.outline}`
              : 'none',
          }}
        >
          {p.highlight ? (
            <>
              <span style={{ color: p.text }}>THIS </span>
              <span style={{ color: p.highlight }}>IS </span>
              <span style={{ color: p.text }}>HOW</span>
            </>
          ) : sampleWords}
        </span>
      </div>
      <p className="text-xs font-medium text-gray-200">{style.name}</p>
    </button>
  );
}

export default function CaptionPanel({
  projectName,
  stages,
  onComplete,
  onSeek,
  currentTime = 0,
  videoDuration = 0,
  onCaptionsChange,
  onStyleChange,
  onPositionChange,
}) {
  const [captions, setCaptions] = useState([]);
  const [style, setStyle] = useState('classic');
  const [renderer, setRenderer] = useState('auto');
  const [tools, setTools] = useState({});
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState('');
  const [substeps, setSubsteps] = useState([]);
  const [error, setError] = useState('');
  const [selectedId, setSelectedId] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [editText, setEditText] = useState('');
  const [hasUnsaved, setHasUnsaved] = useState(false);
  const [showStyles, setShowStyles] = useState(false);
  const [view, setView] = useState('editor'); // editor | srt | ass
  const [srtContent, setSrtContent] = useState('');
  const [assContent, setAssContent] = useState('');
  const [searchText, setSearchText] = useState('');
  const [replaceText, setReplaceText] = useState('');
  const [showSearch, setShowSearch] = useState(false);

  const loadCaptions = async () => {
    try {
      const data = await getCaptions(projectName);
      setCaptions(data);
      if (onCaptionsChange) onCaptionsChange(data);
    } catch (e) {
      // No captions yet
    }
  };

  useEffect(() => {
    if (stages.captions === 'complete') loadCaptions();
  }, [stages.captions]);

  useEffect(() => {
    getAvailableTools().then(setTools).catch(() => {});
  }, []);

  // Notify parent of style changes
  useEffect(() => {
    if (onStyleChange) onStyleChange(style);
  }, [style]);

  const handleGenerate = async () => {
    setProcessing(true);
    setError('');
    setProgress(10);
    const styleName = CAPTION_STYLES.find(s => s.id === style)?.name || style;
    setProgressStatus(`Generating captions (${styleName})...`);
    setSubsteps([{ label: 'Generate captions + SRT + ASS', status: 'active' }]);
    try {
      const result = await generateCaptions(projectName, style);
      setProgress(100);
      setProgressStatus(`Generated ${result.caption_count} captions`);
      setSubsteps([{ label: 'Generate captions + SRT + ASS', status: 'complete' }]);
      await loadCaptions();
      setHasUnsaved(false);
      onComplete();
    } catch (e) {
      setError(e.message);
      setProgressStatus('Failed');
    } finally {
      setProcessing(false);
    }
  };

  const handleSave = async () => {
    setProcessing(true);
    setError('');
    setProgress(30);
    setProgressStatus('Saving captions...');
    try {
      await saveCaptions(projectName, captions);
      setProgress(100);
      setProgressStatus('Captions saved');
      setHasUnsaved(false);
      onComplete();
    } catch (e) {
      setError(e.message);
    } finally {
      setProcessing(false);
    }
  };

  const handleBurn = async () => {
    // Save first if there are unsaved changes
    if (hasUnsaved) {
      try {
        await saveCaptions(projectName, captions);
        setHasUnsaved(false);
      } catch (e) {
        setError(`Save failed before burn: ${e.message}`);
        return;
      }
    }
    setProcessing(true);
    setError('');
    setProgress(5);
    setProgressStatus('Starting caption burn...');
    setSubsteps([{ label: 'Render captioned video', status: 'active' }]);
    try {
      const task = await burnCaptions(projectName, style, renderer);
      await pollTask(task.task_id, (t) => {
        setProgress(t.progress);
        if (t.message) setProgressStatus(t.message);
      }, 2000);
      setProgress(100);
      setProgressStatus('Captions burned into video');
      setSubsteps([{ label: 'Render captioned video', status: 'complete' }]);
      onComplete();
    } catch (e) {
      setError(e.message);
      setProgressStatus('Failed');
    } finally {
      setProcessing(false);
    }
  };

  // --- Caption editing ---

  const updateCaption = useCallback((id, changes) => {
    setCaptions(prev => {
      const updated = prev.map(c => c.id === id ? { ...c, ...changes } : c);
      if (onCaptionsChange) onCaptionsChange(updated);
      return updated;
    });
    setHasUnsaved(true);
  }, [onCaptionsChange]);

  const handleTimingChange = useCallback((id, start, end) => {
    updateCaption(id, { start: Math.round(start * 1000) / 1000, end: Math.round(end * 1000) / 1000 });
  }, [updateCaption]);

  const handleEditStart = (cap) => {
    setEditingId(cap.id);
    setEditText(cap.text);
    setSelectedId(cap.id);
  };

  const handleEditSave = () => {
    if (editingId !== null) {
      updateCaption(editingId, { text: editText });
      setEditingId(null);
    }
  };

  const handleDelete = (id) => {
    setCaptions(prev => {
      const updated = prev.filter(c => c.id !== id);
      if (onCaptionsChange) onCaptionsChange(updated);
      return updated;
    });
    setHasUnsaved(true);
    if (selectedId === id) setSelectedId(null);
  };

  const handleSplit = (id) => {
    setCaptions(prev => {
      const idx = prev.findIndex(c => c.id === id);
      if (idx === -1) return prev;
      const cap = prev[idx];
      const words = cap.text.split(' ');
      if (words.length < 2) return prev;
      const mid = Math.ceil(words.length / 2);
      const midTime = cap.start + (cap.end - cap.start) / 2;
      const maxId = Math.max(...prev.map(c => c.id)) + 1;

      const first = {
        ...cap,
        text: words.slice(0, mid).join(' '),
        end: midTime,
      };
      const second = {
        id: maxId,
        start: midTime,
        end: cap.end,
        text: words.slice(mid).join(' '),
      };
      const updated = [...prev.slice(0, idx), first, second, ...prev.slice(idx + 1)];
      if (onCaptionsChange) onCaptionsChange(updated);
      return updated;
    });
    setHasUnsaved(true);
  };

  const handleMergeWithNext = (id) => {
    setCaptions(prev => {
      const idx = prev.findIndex(c => c.id === id);
      if (idx === -1 || idx >= prev.length - 1) return prev;
      const curr = prev[idx];
      const next = prev[idx + 1];
      const merged = {
        ...curr,
        text: curr.text + ' ' + next.text,
        end: next.end,
      };
      const updated = [...prev.slice(0, idx), merged, ...prev.slice(idx + 2)];
      if (onCaptionsChange) onCaptionsChange(updated);
      return updated;
    });
    setHasUnsaved(true);
  };

  // Search & replace
  const handleReplaceAll = () => {
    if (!searchText) return;
    setCaptions(prev => {
      const updated = prev.map(c => ({
        ...c,
        text: c.text.replaceAll(searchText, replaceText),
      }));
      if (onCaptionsChange) onCaptionsChange(updated);
      return updated;
    });
    setHasUnsaved(true);
  };

  const handlePreviewSrt = async () => {
    try {
      const data = await getSrt(projectName);
      setSrtContent(data.content);
      setView('srt');
    } catch (e) { setError(e.message); }
  };

  const handlePreviewAss = async () => {
    try {
      const data = await getAss(projectName);
      setAssContent(data.content);
      setView('ass');
    } catch (e) { setError(e.message); }
  };

  const hasTranscript = ['correction', 'cleanup', 'editing', 'transcription'].some(
    s => stages[s] === 'complete'
  );

  if (!hasTranscript) {
    return <p className="text-gray-500 text-sm">Complete transcription first.</p>;
  }

  // Find the caption at the current playback time (for scrolling highlight)
  const activeCaptionId = captions.find(
    c => currentTime >= c.start && currentTime <= c.end
  )?.id;

  return (
    <div className="flex flex-col h-full gap-2">
      {/* Top toolbar */}
      <div className="flex items-center gap-2 flex-wrap shrink-0">
        {!processing && (
          <>
            <button
              onClick={handleGenerate}
              className="text-xs bg-[#e0ddaa] text-[#141e27] px-3 py-1.5 rounded font-medium hover:bg-[#d4d19e]"
            >
              {captions.length > 0 ? 'Regenerate' : 'Generate'}
            </button>
            {hasUnsaved && (
              <button
                onClick={handleSave}
                className="text-xs bg-green-700 text-white px-3 py-1.5 rounded hover:bg-green-600"
              >
                Save
              </button>
            )}
            {captions.length > 0 && (
              <button
                onClick={handleBurn}
                className="text-xs bg-gray-700 text-gray-200 px-3 py-1.5 rounded hover:bg-gray-600"
              >
                Burn to Video
              </button>
            )}
            <button
              onClick={() => setShowStyles(!showStyles)}
              className={`text-xs px-3 py-1.5 rounded ${showStyles ? 'bg-[#e0ddaa]/20 text-[#e0ddaa]' : 'bg-gray-700 text-gray-300 hover:bg-gray-600'}`}
            >
              Style: {CAPTION_STYLES.find(s => s.id === style)?.name}
            </button>
            <button
              onClick={() => setShowSearch(!showSearch)}
              className="text-xs bg-gray-700 text-gray-300 px-3 py-1.5 rounded hover:bg-gray-600"
            >
              Find/Replace
            </button>
            {captions.length > 0 && (
              <>
                <button onClick={handlePreviewSrt} className="text-[10px] text-gray-500 hover:text-gray-300">SRT</button>
                <button onClick={handlePreviewAss} className="text-[10px] text-gray-500 hover:text-gray-300">ASS</button>
              </>
            )}
          </>
        )}
        {hasUnsaved && <span className="text-[10px] text-yellow-500">unsaved</span>}
        {captions.length > 0 && (
          <span className="text-[10px] text-gray-500 ml-auto">{captions.length} captions</span>
        )}
      </div>

      {/* Search & Replace */}
      {showSearch && (
        <div className="flex gap-2 items-center bg-[#1a1f2e] rounded p-2 shrink-0">
          <input
            value={searchText}
            onChange={(e) => setSearchText(e.target.value)}
            placeholder="Find..."
            className="flex-1 bg-[#0f1419] border border-gray-700 rounded px-2 py-1 text-xs text-white"
          />
          <input
            value={replaceText}
            onChange={(e) => setReplaceText(e.target.value)}
            placeholder="Replace..."
            className="flex-1 bg-[#0f1419] border border-gray-700 rounded px-2 py-1 text-xs text-white"
          />
          <button onClick={handleReplaceAll} className="text-xs bg-gray-700 text-gray-300 px-2 py-1 rounded hover:bg-gray-600">
            Replace All
          </button>
        </div>
      )}

      {/* Style picker (collapsible) */}
      {showStyles && (
        <div className="shrink-0">
          <div className="grid grid-cols-6 gap-1.5">
            {CAPTION_STYLES.map((s) => (
              <StylePreview key={s.id} style={s} selected={style === s.id} onSelect={(id) => { setStyle(id); setShowStyles(false); }} />
            ))}
          </div>
          {(tools.moviepy || tools.pycaps) && (
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[10px] text-gray-500">Renderer:</span>
              <select
                value={renderer}
                onChange={(e) => setRenderer(e.target.value)}
                className="bg-[#1a1f2e] border border-gray-700 rounded px-2 py-0.5 text-xs text-white"
              >
                <option value="auto">Auto</option>
                <option value="pillow">Pillow</option>
                {tools.moviepy && <option value="moviepy">MoviePy</option>}
              </select>
            </div>
          )}
        </div>
      )}

      {/* Progress */}
      {(processing || progress === 100) && (
        <div className="shrink-0">
          <ProgressBar progress={progress} status={progressStatus} substeps={substeps} />
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded p-2 text-xs text-red-300 shrink-0">{error}</div>
      )}

      {/* Timeline */}
      {captions.length > 0 && view === 'editor' && (
        <div className="shrink-0">
          <CaptionTimeline
            captions={captions}
            duration={videoDuration}
            currentTime={currentTime}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onSeek={onSeek}
            onTimingChange={handleTimingChange}
          />
        </div>
      )}

      {/* Caption list editor */}
      {view === 'editor' && captions.length > 0 && (
        <div className="flex-1 overflow-y-auto min-h-0 space-y-0.5">
          {captions.map((cap, idx) => {
            const isActive = cap.id === activeCaptionId;
            const isSelected = cap.id === selectedId;

            return (
              <div
                key={cap.id}
                className={`group flex gap-1.5 rounded px-2 py-1.5 transition-colors ${
                  isSelected ? 'bg-[#e0ddaa]/10 border border-[#e0ddaa]/30' :
                  isActive ? 'bg-[#1a1f2e]' :
                  'hover:bg-[#1a1f2e]/50'
                }`}
                onClick={() => setSelectedId(cap.id)}
              >
                {/* Time + seek */}
                <button
                  onClick={(e) => { e.stopPropagation(); onSeek(cap.start); }}
                  className="text-[#e0ddaa] text-[10px] font-mono shrink-0 hover:underline w-14 text-right pt-0.5"
                >
                  {formatTime(cap.start, true)}
                </button>

                {/* Text */}
                <div className="flex-1 min-w-0">
                  {editingId === cap.id ? (
                    <div className="flex gap-1">
                      <textarea
                        value={editText}
                        onChange={(e) => setEditText(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleEditSave(); }
                          if (e.key === 'Escape') setEditingId(null);
                        }}
                        className="flex-1 bg-[#0f1419] border border-[#e0ddaa]/50 rounded px-2 py-1 text-xs text-white resize-none focus:outline-none focus:border-[#e0ddaa]"
                        rows={2}
                        autoFocus
                      />
                      <div className="flex flex-col gap-0.5">
                        <button onClick={handleEditSave} className="text-[10px] bg-green-700 px-1.5 py-0.5 rounded text-white">OK</button>
                        <button onClick={() => setEditingId(null)} className="text-[10px] bg-gray-700 px-1.5 py-0.5 rounded text-gray-300">Esc</button>
                      </div>
                    </div>
                  ) : (
                    <p
                      onDoubleClick={() => handleEditStart(cap)}
                      className={`text-xs cursor-text ${isActive ? 'text-white' : 'text-gray-300'} hover:text-white`}
                    >
                      {cap.text}
                    </p>
                  )}
                </div>

                {/* Actions (visible on hover or select) */}
                <div className={`flex items-start gap-0.5 shrink-0 ${isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'} transition-opacity`}>
                  <button
                    onClick={(e) => { e.stopPropagation(); handleSplit(cap.id); }}
                    title="Split caption"
                    className="text-[10px] text-gray-500 hover:text-gray-300 px-1"
                  >
                    Split
                  </button>
                  {idx < captions.length - 1 && (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleMergeWithNext(cap.id); }}
                      title="Merge with next"
                      className="text-[10px] text-gray-500 hover:text-gray-300 px-1"
                    >
                      Merge
                    </button>
                  )}
                  <button
                    onClick={(e) => { e.stopPropagation(); handleDelete(cap.id); }}
                    title="Delete caption"
                    className="text-[10px] text-red-500/70 hover:text-red-400 px-1"
                  >
                    Del
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Timing editor for selected caption */}
      {selectedId !== null && view === 'editor' && (() => {
        const cap = captions.find(c => c.id === selectedId);
        if (!cap) return null;
        return (
          <div className="shrink-0 flex items-center gap-3 bg-[#1a1f2e] rounded p-2">
            <span className="text-[10px] text-gray-500">Start:</span>
            <input
              type="number"
              step="0.1"
              value={cap.start}
              onChange={(e) => handleTimingChange(cap.id, parseFloat(e.target.value) || 0, cap.end)}
              className="w-20 bg-[#0f1419] border border-gray-700 rounded px-2 py-0.5 text-xs text-white font-mono"
            />
            <span className="text-[10px] text-gray-500">End:</span>
            <input
              type="number"
              step="0.1"
              value={cap.end}
              onChange={(e) => handleTimingChange(cap.id, cap.start, parseFloat(e.target.value) || 0)}
              className="w-20 bg-[#0f1419] border border-gray-700 rounded px-2 py-0.5 text-xs text-white font-mono"
            />
            <span className="text-[10px] text-gray-500">
              Duration: {(cap.end - cap.start).toFixed(1)}s
            </span>
          </div>
        );
      })()}

      {/* SRT/ASS preview */}
      {view !== 'editor' && (
        <div className="flex-1 overflow-y-auto min-h-0 bg-[#0f1419] border border-gray-700 rounded p-3">
          <div className="flex justify-between mb-2">
            <span className="text-xs text-gray-500">{view.toUpperCase()} Preview</span>
            <button onClick={() => setView('editor')} className="text-xs text-gray-500 hover:text-gray-300">
              Back to Editor
            </button>
          </div>
          <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">
            {view === 'srt' ? srtContent : assContent}
          </pre>
        </div>
      )}
    </div>
  );
}
