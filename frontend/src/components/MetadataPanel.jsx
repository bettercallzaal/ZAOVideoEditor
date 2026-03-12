import { useState, useEffect } from 'react';
import ProgressBar from './ProgressBar';
import { generateMetadata, getMetadata, saveMetadata } from '../api/client';

export default function MetadataPanel({ projectName, stages, onComplete }) {
  const [description, setDescription] = useState('');
  const [chapters, setChapters] = useState('');
  const [tags, setTags] = useState('');
  const [processing, setProcessing] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState('');

  const loadMetadata = async () => {
    try {
      const data = await getMetadata(projectName);
      setDescription(data.description || '');
      setChapters(data.chapters || '');
      setTags(data.tags || '');
    } catch (e) {
      // No metadata yet
    }
  };

  useEffect(() => {
    if (stages.metadata === 'complete') loadMetadata();
  }, [stages.metadata]);

  const handleGenerate = async () => {
    setProcessing(true);
    setError('');
    setProgress(20);
    setProgressStatus('Analyzing transcript for topics and keywords...');
    try {
      const data = await generateMetadata(projectName);
      setDescription(data.description);
      setChapters(data.chapters);
      setTags(data.tags);
      setProgress(100);
      setProgressStatus('Metadata generated — review and edit, then save');
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
    setProgress(50);
    setProgressStatus('Saving metadata...');
    try {
      await saveMetadata(projectName, description, chapters, tags);
      setProgress(100);
      setProgressStatus('Metadata saved');
      onComplete();
    } catch (e) {
      setError(`Save failed: ${e.message}`);
    } finally {
      setProcessing(false);
    }
  };

  const handleCopy = (field, content) => {
    navigator.clipboard.writeText(content);
    setCopied(field);
    setTimeout(() => setCopied(''), 2000);
  };

  const handleCopyFull = () => {
    const full = [description, '', chapters, '', `Tags: ${tags}`].join('\n');
    navigator.clipboard.writeText(full);
    setCopied('full');
    setTimeout(() => setCopied(''), 2000);
  };

  const tagCount = tags ? tags.split(',').filter(t => t.trim()).length : 0;
  const tagCharCount = tags.length;
  const descCharCount = description.length;
  const chapterCount = chapters ? chapters.split('\n').filter(l => l.trim()).length : 0;

  const hasTranscript = stages.transcription === 'complete';
  if (!hasTranscript) {
    return <p className="text-gray-500 text-sm">Complete transcription first.</p>;
  }

  return (
    <div className="space-y-4">
      {!processing && (
        <div className="flex gap-2 flex-wrap">
          <button
            onClick={handleGenerate}
            className="bg-[#e0ddaa] text-[#141e27] px-4 py-2 rounded text-sm font-medium hover:bg-[#d4d19e]"
          >
            Generate Drafts
          </button>
          {(description || chapters || tags) && (
            <>
              <button
                onClick={handleSave}
                className="bg-gray-700 text-gray-200 px-4 py-2 rounded text-sm hover:bg-gray-600"
              >
                Save Changes
              </button>
              <button
                onClick={handleCopyFull}
                className="bg-gray-700 text-gray-200 px-4 py-2 rounded text-sm hover:bg-gray-600"
              >
                {copied === 'full' ? 'Copied' : 'Copy All'}
              </button>
            </>
          )}
        </div>
      )}

      {/* Progress */}
      {(processing || progress > 0) && (
        <ProgressBar progress={progress} status={progressStatus} />
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">{error}</div>
      )}

      {/* Description */}
      <div>
        <div className="flex justify-between items-center mb-1">
          <label className="text-sm font-medium text-gray-300">Description</label>
          <div className="flex items-center gap-3">
            <span className={`text-xs ${descCharCount > 5000 ? 'text-red-400' : 'text-gray-500'}`}>
              {descCharCount} / 5,000 chars
            </span>
            {description && (
              <button
                onClick={() => handleCopy('desc', description)}
                className="text-xs text-[#e0ddaa] hover:underline"
              >
                {copied === 'desc' ? 'Copied' : 'Copy'}
              </button>
            )}
          </div>
        </div>
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          className="w-full bg-[#1a1f2e] border border-gray-700 rounded p-3 text-sm text-gray-200 resize-y min-h-32 focus:outline-none focus:border-[#e0ddaa]"
          rows={8}
          placeholder="YouTube description will appear here..."
        />
        {description && (
          <p className="text-xs text-gray-600 mt-1">
            First 150 chars (search snippet): "{description.slice(0, 150)}"
          </p>
        )}
      </div>

      {/* Chapters */}
      <div>
        <div className="flex justify-between items-center mb-1">
          <label className="text-sm font-medium text-gray-300">Chapters</label>
          <div className="flex items-center gap-3">
            <span className="text-xs text-gray-500">{chapterCount} chapters</span>
            {chapters && (
              <button
                onClick={() => handleCopy('chapters', chapters)}
                className="text-xs text-[#e0ddaa] hover:underline"
              >
                {copied === 'chapters' ? 'Copied' : 'Copy'}
              </button>
            )}
          </div>
        </div>
        <textarea
          value={chapters}
          onChange={(e) => setChapters(e.target.value)}
          className="w-full bg-[#1a1f2e] border border-gray-700 rounded p-3 text-sm text-gray-200 resize-y font-mono focus:outline-none focus:border-[#e0ddaa]"
          rows={Math.max(4, chapterCount + 1)}
          placeholder="00:00 Introduction..."
        />
        {chapterCount > 0 && chapterCount < 3 && (
          <p className="text-xs text-yellow-500 mt-1">
            YouTube requires at least 3 chapters. Add more timestamps above.
          </p>
        )}
      </div>

      {/* Tags */}
      <div>
        <div className="flex justify-between items-center mb-1">
          <label className="text-sm font-medium text-gray-300">Tags</label>
          <div className="flex items-center gap-3">
            <span className={`text-xs ${tagCharCount > 500 ? 'text-red-400' : 'text-gray-500'}`}>
              {tagCount} tags, {tagCharCount} / 500 chars
            </span>
            {tags && (
              <button
                onClick={() => handleCopy('tags', tags)}
                className="text-xs text-[#e0ddaa] hover:underline"
              >
                {copied === 'tags' ? 'Copied' : 'Copy'}
              </button>
            )}
          </div>
        </div>
        <textarea
          value={tags}
          onChange={(e) => setTags(e.target.value)}
          className="w-full bg-[#1a1f2e] border border-gray-700 rounded p-3 text-sm text-gray-200 resize-y focus:outline-none focus:border-[#e0ddaa]"
          rows={3}
          placeholder="tag1, tag2, tag3..."
        />
      </div>
    </div>
  );
}
