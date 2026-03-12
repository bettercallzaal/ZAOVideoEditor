import { useState, useRef } from 'react';
import ProgressBar from './ProgressBar';
import {
  uploadMainVideo, uploadIntro, uploadOutro,
  assembleVideo, transcribe, pollTask,
} from '../api/client';

export default function UploadPanel({ projectName, stages, onComplete }) {
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
  const mainRef = useRef(null);
  const introRef = useRef(null);
  const outroRef = useRef(null);

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

  const handleIntroUpload = async () => {
    const file = introRef.current?.files[0];
    if (!file) return;
    try {
      await uploadIntro(projectName, file);
      setIntroUploaded(true);
    } catch (e) {
      setError(`Intro upload failed: ${e.message}`);
    }
  };

  const handleOutroUpload = async () => {
    const file = outroRef.current?.files[0];
    if (!file) return;
    try {
      await uploadOutro(projectName, file);
      setOutroUploaded(true);
    } catch (e) {
      setError(`Outro upload failed: ${e.message}`);
    }
  };

  const handleProcess = async () => {
    setProcessing(true);
    setError('');
    setProgress(0);

    const steps = ['Assemble video + extract audio', 'Transcribe audio'];

    try {
      // Step 1: Assemble (background task)
      updateStep(steps, 0);
      setProgress(5);
      setProgressStatus('Assembling video...');
      const assembleTask = await assembleVideo(projectName, useIntro && introUploaded, useOutro && outroUploaded);

      await pollTask(assembleTask.task_id, (t) => {
        setProgress(5 + (t.progress / 100) * 25);
        if (t.message) setProgressStatus(t.message);
      });
      setProgress(30);

      // Step 2: Transcribe (background task)
      updateStep(steps, 1);
      setProgressStatus('Starting transcription...');
      const transcribeTask = await transcribe(projectName, quality);

      await pollTask(transcribeTask.task_id, (t) => {
        // Map transcription progress into 30-95 range
        const mapped = 30 + (t.progress / 100) * 65;
        setProgress(Math.min(mapped, 95));
        if (t.message) setProgressStatus(t.message);
      });

      setProgress(100);
      const finalTask = await pollTask(transcribeTask.task_id, null, 100);
      const r = finalTask.result || {};
      setProgressStatus(`Done! ${r.segments || '?'} segments, language: ${r.language || '?'}`);
      updateStep(steps, 2);
      onComplete();
    } catch (e) {
      setError(`Processing failed: ${e.message}`);
      setProgressStatus('Failed');
    } finally {
      setProcessing(false);
    }
  };

  return (
    <div className="space-y-6">
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

      {/* Intro/Outro */}
      <section>
        <h3 className="text-sm font-medium text-gray-300 mb-2">Intro / Outro (Optional)</h3>
        <div className="space-y-3">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={useIntro} onChange={(e) => setUseIntro(e.target.checked)} className="rounded" />
            <span className="text-sm text-gray-400">Add intro</span>
          </label>
          {useIntro && (
            <div className="flex gap-2 ml-6">
              <input ref={introRef} type="file" accept=".mp4,.mov,.mkv,.webm" className="flex-1 text-sm text-gray-400 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:bg-gray-700 file:text-gray-300 file:cursor-pointer" />
              <button onClick={handleIntroUpload} className="text-xs bg-gray-700 px-3 py-1 rounded text-gray-300 hover:bg-gray-600">Upload Intro</button>
              {introUploaded && <span className="text-green-400 text-xs self-center">Ready</span>}
            </div>
          )}
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={useOutro} onChange={(e) => setUseOutro(e.target.checked)} className="rounded" />
            <span className="text-sm text-gray-400">Add outro</span>
          </label>
          {useOutro && (
            <div className="flex gap-2 ml-6">
              <input ref={outroRef} type="file" accept=".mp4,.mov,.mkv,.webm" className="flex-1 text-sm text-gray-400 file:mr-3 file:py-1 file:px-3 file:rounded file:border-0 file:text-xs file:bg-gray-700 file:text-gray-300 file:cursor-pointer" />
              <button onClick={handleOutroUpload} className="text-xs bg-gray-700 px-3 py-1 rounded text-gray-300 hover:bg-gray-600">Upload Outro</button>
              {outroUploaded && <span className="text-green-400 text-xs self-center">Ready</span>}
            </div>
          )}
        </div>
      </section>

      {/* Transcription quality + Process button */}
      {stages.upload === 'complete' && !processing && (
        <section className="space-y-3">
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
          <button onClick={handleProcess} className="w-full bg-[#e0ddaa] text-[#141e27] py-3 rounded-lg font-medium hover:bg-[#d4d19e]">
            Assemble + Transcribe
          </button>
          <p className="text-xs text-gray-500 mt-1">Assembles video, extracts audio, and runs local transcription.</p>
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
