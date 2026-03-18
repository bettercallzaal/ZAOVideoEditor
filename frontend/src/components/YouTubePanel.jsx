import { useState } from 'react';
import ProgressBar from './ProgressBar';
import { formatTime } from '../utils/format';
import { getYouTubeInfo, youtubeTranscribe, pollTask, getCurrentTranscript } from '../api/client';

export default function YouTubePanel({ projectName, stages, onComplete }) {
  const [url, setUrl] = useState('');
  const [videoInfo, setVideoInfo] = useState(null);
  const [quality, setQuality] = useState('standard');
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState('');
  const [error, setError] = useState('');
  const [transcript, setTranscript] = useState(null);
  const [copied, setCopied] = useState(false);

  const handleCopyAll = () => {
    if (!transcript?.segments?.length) return;
    const text = transcript.segments.map(s => s.text).join('\n');
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleCopyWithTimestamps = () => {
    if (!transcript?.segments?.length) return;
    const text = transcript.segments
      .map(s => `[${formatTime(s.start)}] ${s.text}`)
      .join('\n');
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const CHAR_LIMIT = 49000;

  const downloadChunkedFiles = () => {
    if (!transcript?.segments?.length) return;
    const fullText = transcript.segments.map(s => s.text).join('\n');
    const title = videoInfo?.title?.replace(/[^a-zA-Z0-9 _-]/g, '').trim().slice(0, 40) || 'transcript';

    // Split into chunks at line boundaries, respecting the char limit
    const chunks = [];
    let current = '';
    for (const line of fullText.split('\n')) {
      if (current.length + line.length + 1 > CHAR_LIMIT && current.length > 0) {
        chunks.push(current);
        current = line;
      } else {
        current += (current ? '\n' : '') + line;
      }
    }
    if (current) chunks.push(current);

    // Download each chunk as a .txt file
    chunks.forEach((chunk, i) => {
      const blob = new Blob([chunk], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${title}_part${i + 1}_of_${chunks.length}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    });
  };

  const handleFetchInfo = async () => {
    if (!url.trim()) return;
    setError('');
    setVideoInfo(null);
    try {
      const info = await getYouTubeInfo(url);
      setVideoInfo(info);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleTranscribe = async () => {
    setProcessing(true);
    setError('');
    setProgress(5);
    setProgressStatus('Starting YouTube transcription...');
    try {
      const task = await youtubeTranscribe(url, projectName, quality);
      const result = await pollTask(task.task_id, (t) => {
        setProgress(t.progress);
        if (t.message) setProgressStatus(t.message);
      }, 2000);
      setProgress(100);
      setProgressStatus(result.result?.source === 'youtube_captions'
        ? `Got ${result.result.segment_count} segments from YouTube captions`
        : `Transcribed ${result.result.segment_count} segments with faster-whisper`
      );
      // Load the transcript
      try {
        const data = await getCurrentTranscript(projectName);
        setTranscript(data);
      } catch { /* ok */ }
      onComplete();
    } catch (e) {
      setError(e.message);
      setProgressStatus('Failed');
    } finally {
      setProcessing(false);
    }
  };

  const formatDuration = (seconds) => {
    if (!seconds) return '';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = Math.floor(seconds % 60);
    if (h > 0) return `${h}h ${m}m ${s}s`;
    return `${m}m ${s}s`;
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="text-xs text-gray-500 block mb-1">YouTube URL</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleFetchInfo()}
            placeholder="https://www.youtube.com/watch?v=..."
            className="flex-1 bg-[#1a1f2e] border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-[#e0ddaa]"
          />
          <button
            onClick={handleFetchInfo}
            disabled={!url.trim() || processing}
            className="bg-gray-700 text-gray-200 px-4 py-2 rounded text-sm hover:bg-gray-600 disabled:opacity-50"
          >
            Fetch
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">{error}</div>
      )}

      {videoInfo && (
        <div className="bg-[#1a1f2e] rounded p-4 space-y-3">
          <h3 className="text-sm font-medium text-white">{videoInfo.title}</h3>
          <div className="flex gap-4 text-xs text-gray-400">
            <span>{videoInfo.channel}</span>
            <span>{formatDuration(videoInfo.duration)}</span>
            {videoInfo.was_live && (
              <span className="text-orange-400">Was Live</span>
            )}
            {videoInfo.view_count > 0 && (
              <span>{videoInfo.view_count.toLocaleString()} views</span>
            )}
          </div>

          <div className="flex gap-3 items-end">
            <div>
              <label className="text-xs text-gray-500 block mb-1">Quality</label>
              <select
                value={quality}
                onChange={(e) => setQuality(e.target.value)}
                className="bg-[#0f1419] border border-gray-700 rounded px-2 py-1.5 text-sm text-white"
              >
                <option value="fast">Fast (base model)</option>
                <option value="standard">Standard (large model)</option>
                <option value="high">High (3-pass)</option>
              </select>
            </div>
            {!processing && (
              <button
                onClick={handleTranscribe}
                className="bg-[#e0ddaa] text-[#141e27] px-6 py-1.5 rounded text-sm font-medium hover:bg-[#d4d19e]"
              >
                Grab Transcript
              </button>
            )}
          </div>
        </div>
      )}

      {(processing || progress > 0) && (
        <ProgressBar progress={progress} status={progressStatus} />
      )}

      {transcript && transcript.segments && transcript.segments.length > 0 && (
        <div className="space-y-2">
          {(() => {
            const totalChars = transcript.segments.map(s => s.text).join('\n').length;
            const numParts = Math.ceil(totalChars / CHAR_LIMIT);
            return (
              <>
                <div className="flex justify-between items-center">
                  <h3 className="text-sm font-medium text-gray-300">
                    Transcript ({transcript.segments.length} segments)
                    <span className="text-xs text-gray-500 ml-2">
                      {totalChars.toLocaleString()} chars
                    </span>
                  </h3>
                  <div className="flex items-center gap-2">
                    {copied && <span className="text-xs text-green-400">Copied!</span>}
                    <button
                      onClick={handleCopyAll}
                      className="text-xs bg-gray-700 text-gray-300 px-2.5 py-1 rounded hover:bg-gray-600"
                    >
                      Copy Text
                    </button>
                    <button
                      onClick={handleCopyWithTimestamps}
                      className="text-xs bg-gray-700 text-gray-300 px-2.5 py-1 rounded hover:bg-gray-600"
                    >
                      Copy + Timestamps
                    </button>
                    <button
                      onClick={downloadChunkedFiles}
                      className="text-xs bg-[#e0ddaa] text-[#141e27] px-2.5 py-1 rounded font-medium hover:bg-[#d4d19e]"
                    >
                      Download .txt ({numParts} {numParts === 1 ? 'file' : 'files'})
                    </button>
                  </div>
                </div>
              </>
            );
          })()}
          <div className="max-h-96 overflow-y-auto bg-[#0f1419] border border-gray-800 rounded p-3 space-y-1">
            {transcript.segments.map((seg, i) => (
              <div key={i} className="flex gap-2 text-xs">
                <span className="text-[#e0ddaa] font-mono shrink-0 w-12 text-right">
                  {formatTime(seg.start)}
                </span>
                <span className="text-gray-300">{seg.text}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
