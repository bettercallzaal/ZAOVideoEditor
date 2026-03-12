import { useState, useEffect } from 'react';
import ProgressBar from './ProgressBar';
import { generateCaptions, getCaptions, burnCaptions, getSrt, getAss, pollTask } from '../api/client';

export default function CaptionPanel({ projectName, stages, onComplete }) {
  const [captions, setCaptions] = useState([]);
  const [theme, setTheme] = useState('theme_a');
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState('');
  const [substeps, setSubsteps] = useState([]);
  const [error, setError] = useState('');
  const [srtContent, setSrtContent] = useState('');
  const [assContent, setAssContent] = useState('');

  const loadCaptions = async () => {
    try {
      const data = await getCaptions(projectName);
      setCaptions(data);
    } catch (e) {
      // No captions yet
    }
  };

  useEffect(() => {
    if (stages.captions === 'complete') loadCaptions();
  }, [stages.captions]);

  const handleGenerate = async () => {
    setProcessing(true);
    setError('');
    setProgress(10);
    setProgressStatus('Generating captions from transcript...');
    setSubsteps([
      { label: 'Generate captions + SRT + ASS', status: 'active' },
    ]);
    try {
      const result = await generateCaptions(projectName, theme);
      setProgress(100);
      setProgressStatus(`Generated ${result.caption_count} captions (${theme === 'theme_a' ? 'Dark on Light' : 'Light on Dark'})`);
      setSubsteps([{ label: 'Generate captions + SRT + ASS', status: 'complete' }]);
      await loadCaptions();
      onComplete();
    } catch (e) {
      setError(e.message);
      setProgressStatus('Failed');
    } finally {
      setProcessing(false);
    }
  };

  const handleBurn = async () => {
    setProcessing(true);
    setError('');
    setProgress(5);
    setProgressStatus('Starting caption burn...');
    setSubsteps([
      { label: 'Render captioned video', status: 'active' },
    ]);

    try {
      const task = await burnCaptions(projectName, theme);

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

  const handlePreviewSrt = async () => {
    try {
      const data = await getSrt(projectName);
      setSrtContent(data.content);
      setAssContent('');
    } catch (e) {
      setError(e.message);
    }
  };

  const handlePreviewAss = async () => {
    try {
      const data = await getAss(projectName);
      setAssContent(data.content);
      setSrtContent('');
    } catch (e) {
      setError(e.message);
    }
  };

  const hasTranscript = ['correction', 'cleanup', 'editing', 'transcription'].some(
    s => stages[s] === 'complete'
  );

  if (!hasTranscript) {
    return <p className="text-gray-500 text-sm">Complete transcription first.</p>;
  }

  return (
    <div className="space-y-4">
      {/* Theme selection */}
      <div>
        <h3 className="text-sm font-medium text-gray-300 mb-2">Caption Theme</h3>
        <div className="flex gap-3">
          <label
            className={`flex items-center gap-2 p-3 rounded border cursor-pointer ${
              theme === 'theme_a' ? 'border-[#e0ddaa]' : 'border-gray-700'
            }`}
          >
            <input type="radio" value="theme_a" checked={theme === 'theme_a'} onChange={() => setTheme('theme_a')} />
            <span className="inline-block px-2 py-0.5 rounded text-xs" style={{ background: '#e0ddaa', color: '#141e27' }}>
              Dark on Light
            </span>
          </label>
          <label
            className={`flex items-center gap-2 p-3 rounded border cursor-pointer ${
              theme === 'theme_b' ? 'border-[#e0ddaa]' : 'border-gray-700'
            }`}
          >
            <input type="radio" value="theme_b" checked={theme === 'theme_b'} onChange={() => setTheme('theme_b')} />
            <span className="inline-block px-2 py-0.5 rounded text-xs" style={{ background: '#141e27', color: '#e0ddaa', border: '1px solid #e0ddaa' }}>
              Light on Dark
            </span>
          </label>
        </div>
      </div>

      {/* Actions */}
      {!processing && (
        <div className="flex gap-2">
          <button
            onClick={handleGenerate}
            className="bg-[#e0ddaa] text-[#141e27] px-4 py-2 rounded text-sm font-medium hover:bg-[#d4d19e]"
          >
            Generate Captions
          </button>
          {stages.captions === 'complete' && (
            <button
              onClick={handleBurn}
              className="bg-gray-700 text-gray-200 px-4 py-2 rounded text-sm hover:bg-gray-600"
            >
              Burn into Video
            </button>
          )}
        </div>
      )}

      {/* Progress */}
      {(processing || progress === 100) && (
        <ProgressBar progress={progress} status={progressStatus} substeps={substeps} />
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">{error}</div>
      )}

      {/* Preview buttons */}
      {stages.captions === 'complete' && !processing && (
        <div className="flex gap-2">
          <button onClick={handlePreviewSrt} className="text-xs text-[#e0ddaa] hover:underline">Preview SRT</button>
          <button onClick={handlePreviewAss} className="text-xs text-[#e0ddaa] hover:underline">Preview ASS</button>
        </div>
      )}

      {/* Caption preview */}
      {captions.length > 0 && !srtContent && !assContent && !processing && (
        <div className="space-y-1 max-h-96 overflow-y-auto">
          <h4 className="text-xs text-gray-500 mb-2">{captions.length} captions</h4>
          {captions.map((cap) => (
            <div key={cap.id} className="flex gap-2 text-xs py-1 border-b border-gray-800">
              <span className="text-gray-500 font-mono w-20 shrink-0">
                {Math.floor(cap.start / 60)}:{Math.floor(cap.start % 60).toString().padStart(2, '0')}
              </span>
              <span className="text-gray-300">{cap.text}</span>
            </div>
          ))}
        </div>
      )}

      {/* SRT/ASS preview */}
      {(srtContent || assContent) && (
        <div className="bg-[#0f1419] border border-gray-700 rounded p-3 max-h-96 overflow-y-auto">
          <div className="flex justify-between mb-2">
            <span className="text-xs text-gray-500">{srtContent ? 'SRT' : 'ASS'} Preview</span>
            <button onClick={() => { setSrtContent(''); setAssContent(''); }} className="text-xs text-gray-500 hover:text-gray-300">Close</button>
          </div>
          <pre className="text-xs text-gray-300 whitespace-pre-wrap font-mono">{srtContent || assContent}</pre>
        </div>
      )}
    </div>
  );
}
