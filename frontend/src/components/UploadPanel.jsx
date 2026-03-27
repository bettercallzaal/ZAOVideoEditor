import { useState, useRef, useEffect } from 'react';
import ProgressBar from './ProgressBar';
import {
  uploadMainVideo, uploadIntro, uploadOutro,
  assembleVideo, transcribe, pollTask,
  getAvailableTools, previewSilenceCuts, removeSilence,
  getDictionary, listTemplates, saveTemplate, deleteTemplate,
} from '../api/client';

export default function UploadPanel({ projectName, stages, onComplete, onTranscribed }) {
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [useIntro, setUseIntro] = useState(false);
  const [useOutro, setUseOutro] = useState(false);
  const [introUploaded, setIntroUploaded] = useState(false);
  const [outroUploaded, setOutroUploaded] = useState(false);
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState('');
  const [substeps, setSubsteps] = useState([]);
  const [error, setError] = useState('');
  const [quality, setQuality] = useState('standard');
  const [engine, setEngine] = useState('auto');
  const [refineTimestamps, setRefineTimestamps] = useState(true);
  const [tools, setTools] = useState({});
  const [silenceMargin, setSilenceMargin] = useState(0.1);
  const [silenceThreshold, setSilenceThreshold] = useState(0.04);
  const [silencePreview, setSilencePreview] = useState(null);
  const [removeSilenceEnabled, setRemoveSilenceEnabled] = useState(false);
  const mainRef = useRef(null);
  const introRef = useRef(null);
  const outroRef = useRef(null);

  const [dictCount, setDictCount] = useState(0);
  const [templates, setTemplates] = useState({});
  const [savePresetName, setSavePresetName] = useState('');
  const [showSavePreset, setShowSavePreset] = useState(false);

  // Load available tools, dictionary, and templates on mount
  useEffect(() => {
    getAvailableTools().then(setTools).catch(() => {});
    getDictionary().then(d => setDictCount(Object.keys(d.corrections || {}).length)).catch(() => {});
    listTemplates().then(setTemplates).catch(() => {});
  }, []);

  const handleLoadTemplate = (name) => {
    const tpl = templates[name];
    if (!tpl) return;
    if (tpl.quality) setQuality(tpl.quality);
    if (tpl.engine) setEngine(tpl.engine);
    if (tpl.refine_timestamps !== undefined) setRefineTimestamps(tpl.refine_timestamps);
    if (tpl.remove_silence !== undefined) setRemoveSilenceEnabled(tpl.remove_silence);
    if (tpl.silence_margin !== undefined) setSilenceMargin(tpl.silence_margin);
    if (tpl.silence_threshold !== undefined) setSilenceThreshold(tpl.silence_threshold);
    if (tpl.use_intro !== undefined) setUseIntro(tpl.use_intro);
    if (tpl.use_outro !== undefined) setUseOutro(tpl.use_outro);
  };

  const handleSaveTemplate = async () => {
    const name = savePresetName.trim();
    if (!name) return;
    const settings = {
      quality,
      engine,
      refine_timestamps: refineTimestamps,
      remove_silence: removeSilenceEnabled,
      silence_margin: silenceMargin,
      silence_threshold: silenceThreshold,
      use_intro: useIntro,
      use_outro: useOutro,
    };
    try {
      await saveTemplate(name, settings);
      const updated = await listTemplates();
      setTemplates(updated);
      setSavePresetName('');
      setShowSavePreset(false);
    } catch (e) {
      setError(`Failed to save preset: ${e.message}`);
    }
  };

  const handleDeleteTemplate = async (name) => {
    try {
      await deleteTemplate(name);
      const updated = await listTemplates();
      setTemplates(updated);
    } catch (e) {
      setError(`Failed to delete preset: ${e.message}`);
    }
  };

  const updateStep = (steps, activeIndex) => {
    setSubsteps(steps.map((label, i) => ({
      label,
      status: i < activeIndex ? 'complete' : i === activeIndex ? 'active' : 'pending',
    })));
  };

  const handleUpload = async () => {
    const file = mainRef.current?.files[0];
    if (!file) return;

    setUploading(true);
    setError('');
    setUploadProgress(0);
    setProgressStatus(`Uploading ${file.name}...`);

    try {
      await uploadMainVideo(projectName, file, (p) => {
        setUploadProgress(p.percent);
        const mb = (p.loaded / 1024 / 1024).toFixed(1);
        const totalMb = (p.total / 1024 / 1024).toFixed(1);
        setProgressStatus(`Uploading ${file.name}... ${mb} MB / ${totalMb} MB`);
      });
      setUploadProgress(100);
      setProgressStatus('Upload complete');
      onComplete();
    } catch (e) {
      setError(`Upload failed: ${e.message}`);
    } finally {
      setUploading(false);
    }
  };

  const handleIntroSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUseIntro(true);
    setProgressStatus(`Uploading intro: ${file.name}...`);
    try {
      await uploadIntro(projectName, file);
      setIntroUploaded(true);
      setProgressStatus('');
    } catch (err) {
      setError(`Intro upload failed: ${err.message}`);
    }
  };

  const handleOutroSelect = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUseOutro(true);
    setProgressStatus(`Uploading outro: ${file.name}...`);
    try {
      await uploadOutro(projectName, file);
      setOutroUploaded(true);
      setProgressStatus('');
    } catch (err) {
      setError(`Outro upload failed: ${err.message}`);
    }
  };

  const handlePreviewSilence = async () => {
    setError('');
    setProgressStatus('Previewing silence cuts...');
    setProgress(30);
    try {
      const data = await previewSilenceCuts(projectName, silenceMargin, silenceThreshold);
      setSilencePreview(data);
      setProgress(100);
      setProgressStatus(`Found ${data.cut_count} silent sections (${data.removed_seconds}s)`);
    } catch (e) {
      setError(e.message);
      setProgress(0);
    }
  };

  const handleProcess = async () => {
    setProcessing(true);
    setError('');
    setProgress(0);

    const steps = ['Assemble video + extract audio'];
    if (removeSilenceEnabled && tools.auto_editor) {
      steps.push('Remove dead air');
    }
    steps.push('Transcribe audio');
    if (refineTimestamps && tools.stable_ts) {
      // Refinement is part of transcription step
    }

    try {
      let stepIdx = 0;

      // Step 1: Assemble
      updateStep(steps, stepIdx);
      setProgress(5);
      setProgressStatus('Assembling video...');
      const assembleTask = await assembleVideo(projectName, useIntro && introUploaded, useOutro && outroUploaded);

      await pollTask(assembleTask.task_id, (t) => {
        setProgress(5 + (t.progress / 100) * 20);
        if (t.message) setProgressStatus(t.message);
      });
      setProgress(25);
      stepIdx++;

      // Step 2 (optional): Remove silence
      if (removeSilenceEnabled && tools.auto_editor) {
        updateStep(steps, stepIdx);
        setProgressStatus('Removing dead air...');
        const silenceTask = await removeSilence(projectName, silenceMargin, silenceThreshold);

        await pollTask(silenceTask.task_id, (t) => {
          setProgress(25 + (t.progress / 100) * 10);
          if (t.message) setProgressStatus(t.message);
        });
        setProgress(35);
        stepIdx++;
      }

      // Step 3: Transcribe
      updateStep(steps, stepIdx);
      const baseProgress = removeSilenceEnabled && tools.auto_editor ? 35 : 25;
      setProgressStatus('Starting transcription...');
      const transcribeTask = await transcribe(projectName, quality, engine, refineTimestamps);

      await pollTask(transcribeTask.task_id, (t) => {
        const mapped = baseProgress + (t.progress / 100) * (95 - baseProgress);
        setProgress(Math.min(mapped, 95));
        if (t.message) setProgressStatus(t.message);
      });

      setProgress(100);
      const finalTask = await pollTask(transcribeTask.task_id, null, 100);
      const r = finalTask.result || {};

      let doneMsg = `Done! ${r.segments || '?'} segments, language: ${r.language || '?'}`;
      if (r.engine) doneMsg += `, engine: ${r.engine}`;
      if (r.timestamp_refined) doneMsg += ' (timestamps refined)';
      setProgressStatus(doneMsg);

      updateStep(steps, steps.length);
      onComplete();
      if (onTranscribed) onTranscribed();
    } catch (e) {
      setError(`Processing failed: ${e.message}`);
      setProgressStatus('Failed');
    } finally {
      setProcessing(false);
    }
  };

  const engineLabel = (e) => {
    if (e === 'auto') return tools.whisperx ? 'Auto (WhisperX)' : 'Auto (faster-whisper)';
    if (e === 'groq') return 'Groq Cloud';
    if (e === 'whisperx') return 'WhisperX';
    return 'faster-whisper';
  };

  return (
    <div className="space-y-6">
      {/* Presets */}
      {(Object.keys(templates).length > 0 || showSavePreset) && (
        <section className="bg-[#1a1f2e] rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-medium text-gray-400 uppercase tracking-wide">Presets</h3>
            <button
              onClick={() => setShowSavePreset(prev => !prev)}
              className="text-[10px] text-[#e0ddaa] hover:underline"
            >
              {showSavePreset ? 'Cancel' : 'Save current as preset'}
            </button>
          </div>
          {Object.keys(templates).length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {Object.keys(templates).map(name => (
                <div key={name} className="flex items-center gap-0.5">
                  <button
                    onClick={() => handleLoadTemplate(name)}
                    className="text-xs bg-gray-700 text-gray-200 px-2.5 py-1 rounded-l hover:bg-gray-600 font-medium"
                  >
                    {name}
                  </button>
                  <button
                    onClick={() => handleDeleteTemplate(name)}
                    className="text-xs bg-gray-700 text-gray-500 px-1.5 py-1 rounded-r hover:bg-red-900/50 hover:text-red-300"
                    title={`Delete "${name}" preset`}
                  >
                    x
                  </button>
                </div>
              ))}
            </div>
          )}
          {showSavePreset && (
            <div className="flex gap-2">
              <input
                type="text"
                value={savePresetName}
                onChange={(e) => setSavePresetName(e.target.value)}
                placeholder="Preset name..."
                className="flex-1 bg-[#0f1419] border border-gray-700 rounded px-2 py-1 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-[#e0ddaa]"
                onKeyDown={(e) => e.key === 'Enter' && handleSaveTemplate()}
              />
              <button
                onClick={handleSaveTemplate}
                disabled={!savePresetName.trim()}
                className="text-xs bg-[#e0ddaa] text-[#141e27] px-3 py-1 rounded font-medium hover:bg-[#d4d19e] disabled:opacity-50"
              >
                Save
              </button>
            </div>
          )}
        </section>
      )}

      {/* Save preset button when no presets exist yet */}
      {Object.keys(templates).length === 0 && !showSavePreset && stages.upload === 'complete' && !processing && (
        <button
          onClick={() => setShowSavePreset(true)}
          className="text-xs text-gray-500 hover:text-[#e0ddaa]"
        >
          Save current settings as a preset...
        </button>
      )}

      {/* Main video upload */}
      <section>
        <h3 className="text-sm font-medium text-gray-300 mb-2">Main Video</h3>
        <div className="flex gap-2">
          <input
            ref={mainRef}
            type="file"
            accept=".mp4,.mov,.mkv,.webm"
            disabled={uploading}
            className="flex-1 text-sm text-gray-400 file:mr-3 file:py-1.5 file:px-3 file:rounded file:border-0 file:text-sm file:bg-[#e0ddaa] file:text-[#141e27] file:cursor-pointer disabled:opacity-50"
          />
          <button
            onClick={handleUpload}
            disabled={uploading}
            className="bg-[#e0ddaa] text-[#141e27] px-4 py-1.5 rounded text-sm font-medium hover:bg-[#d4d19e] disabled:opacity-50"
          >
            {uploading ? 'Uploading...' : 'Upload'}
          </button>
        </div>
        {stages.upload === 'complete' && !uploading && (
          <p className="text-green-400 text-xs mt-1">Video uploaded</p>
        )}
      </section>

      {/* Upload progress */}
      {uploading && (
        <ProgressBar progress={uploadProgress} status={progressStatus} />
      )}

      {/* Intro/Outro — auto-uploads on file select */}
      <section>
        <h3 className="text-sm font-medium text-gray-300 mb-2">Intro / Outro <span className="text-gray-600 font-normal">(optional — select file to add)</span></h3>
        <div className="flex gap-3">
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <input
                ref={introRef}
                type="file"
                accept=".mp4,.mov,.mkv,.webm"
                onChange={handleIntroSelect}
                className="flex-1 text-sm text-gray-400 file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:bg-gray-700 file:text-gray-300 file:cursor-pointer"
              />
              {introUploaded && <span className="text-green-400 text-xs shrink-0">Intro ready</span>}
            </div>
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-2">
              <input
                ref={outroRef}
                type="file"
                accept=".mp4,.mov,.mkv,.webm"
                onChange={handleOutroSelect}
                className="flex-1 text-sm text-gray-400 file:mr-2 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:bg-gray-700 file:text-gray-300 file:cursor-pointer"
              />
              {outroUploaded && <span className="text-green-400 text-xs shrink-0">Outro ready</span>}
            </div>
          </div>
        </div>
      </section>

      {/* Processing options */}
      {stages.upload === 'complete' && !processing && (
        <section className="space-y-4">
          {/* Silence removal (auto-editor) */}
          {tools.auto_editor && (
            <div className="bg-[#1a1f2e] rounded-lg p-3 space-y-2">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={removeSilenceEnabled}
                  onChange={(e) => setRemoveSilenceEnabled(e.target.checked)}
                  className="rounded"
                />
                <span className="text-sm text-gray-300 font-medium">Remove Dead Air</span>
                <span className="text-xs text-gray-500">(auto-editor)</span>
              </label>
              {removeSilenceEnabled && (
                <div className="ml-6 space-y-2">
                  <div className="flex gap-4">
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">Padding (sec)</label>
                      <input
                        type="number" step="0.05" min="0" max="1"
                        value={silenceMargin}
                        onChange={(e) => setSilenceMargin(+e.target.value)}
                        className="w-20 bg-[#0f1419] border border-gray-700 rounded px-2 py-1 text-sm text-white"
                      />
                    </div>
                    <div>
                      <label className="text-xs text-gray-500 block mb-1">Threshold</label>
                      <input
                        type="number" step="0.01" min="0.01" max="0.2"
                        value={silenceThreshold}
                        onChange={(e) => setSilenceThreshold(+e.target.value)}
                        className="w-20 bg-[#0f1419] border border-gray-700 rounded px-2 py-1 text-sm text-white"
                      />
                    </div>
                    <div className="self-end">
                      <button
                        onClick={handlePreviewSilence}
                        className="text-xs bg-gray-700 text-gray-300 px-3 py-1.5 rounded hover:bg-gray-600"
                      >
                        Preview Cuts
                      </button>
                    </div>
                  </div>
                  {silencePreview && (
                    <div className="text-xs text-gray-400 bg-[#0f1419] rounded p-2">
                      <p>{silencePreview.cut_count} silent sections found</p>
                      <p>Original: {silencePreview.original_duration}s → Trimmed: {silencePreview.edited_duration}s
                        <span className="text-[#e0ddaa] ml-1">(-{silencePreview.removed_seconds}s)</span>
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Transcription quality */}
          <div>
            <h3 className="text-sm font-medium text-gray-300 mb-2">Transcription Quality</h3>
            <div className="flex gap-3">
              {[
                { value: 'fast', label: 'Fast', desc: 'Base model, 1 pass — quick draft' },
                { value: 'standard', label: 'Standard', desc: 'Large model, 1 pass — good quality' },
                { value: 'high', label: 'High', desc: 'Large model, 3 passes — best accuracy' },
              ].map((opt) => (
                <label
                  key={opt.value}
                  className={`flex-1 p-3 rounded border cursor-pointer ${
                    quality === opt.value ? 'border-[#e0ddaa] bg-[#e0ddaa]/10' : 'border-gray-700'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <input
                      type="radio"
                      value={opt.value}
                      checked={quality === opt.value}
                      onChange={() => setQuality(opt.value)}
                    />
                    <span className="text-sm text-gray-200 font-medium">{opt.label}</span>
                  </div>
                  <p className="text-xs text-gray-500 mt-1 ml-5">{opt.desc}</p>
                </label>
              ))}
            </div>
          </div>

          {/* Engine + refinement options */}
          <div className="flex gap-4 items-start">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Engine</label>
              <select
                value={engine}
                onChange={(e) => setEngine(e.target.value)}
                className="bg-[#1a1f2e] border border-gray-700 rounded px-2 py-1.5 text-sm text-white"
              >
                <option value="auto">{engineLabel('auto')}</option>
                <option value="faster-whisper">faster-whisper</option>
                {tools.whisperx && <option value="whisperx">WhisperX (better word timing)</option>}
                {tools.groq && <option value="groq">Groq Cloud (fast)</option>}
              </select>
            </div>
            {tools.stable_ts && (
              <label className="flex items-center gap-2 pt-5">
                <input
                  type="checkbox"
                  checked={refineTimestamps}
                  onChange={(e) => setRefineTimestamps(e.target.checked)}
                  className="rounded"
                />
                <span className="text-sm text-gray-400">Refine timestamps</span>
                <span className="text-xs text-gray-600">(stable-ts)</span>
              </label>
            )}
          </div>

          <button onClick={handleProcess} className="w-full bg-[#e0ddaa] text-[#141e27] py-3 rounded-lg font-medium hover:bg-[#d4d19e]">
            {removeSilenceEnabled ? 'Assemble + Trim + Transcribe' : 'Assemble + Transcribe'}
          </button>
          <div className="flex items-center justify-between mt-1">
            <p className="text-xs text-gray-500">
              {removeSilenceEnabled
                ? 'Assembles video, removes dead air, extracts audio, and runs local transcription.'
                : 'Assembles video, extracts audio, and runs local transcription.'}
            </p>
            {dictCount > 0 && (
              <span className="text-xs text-[#e0ddaa]/60 shrink-0 ml-2">
                {dictCount} dictionary terms will guide transcription
              </span>
            )}
          </div>
        </section>
      )}

      {/* Processing progress */}
      {(processing || progress > 0) && (
        <ProgressBar progress={progress} status={progressStatus} substeps={substeps} />
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">{error}</div>
      )}
    </div>
  );
}
