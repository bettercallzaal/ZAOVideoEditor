import { useState, useEffect } from 'react';
import { generateContent, getContent } from '../api/client';

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${String(s).padStart(2, '0')}`;
}

export default function ContentPanel({ projectName, stages, onSeek }) {
  const [content, setContent] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [copiedField, setCopiedField] = useState('');

  const hasTranscript = ['raw', 'corrected', 'cleaned', 'edited'].some(
    s => stages[`transcription`] === 'complete' || stages[`transcript_${s}`]
  ) || stages.transcription === 'complete';

  // Load existing content on mount
  useEffect(() => {
    getContent(projectName).then(setContent).catch(() => {});
  }, [projectName]);

  const handleGenerate = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await generateContent(projectName);
      setContent(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCopy = (text, field) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedField(field);
      setTimeout(() => setCopiedField(''), 2000);
    });
  };

  const CopyBtn = ({ text, field }) => (
    <button
      onClick={() => handleCopy(text, field)}
      className="text-[10px] bg-gray-700 text-gray-300 px-2 py-0.5 rounded hover:bg-gray-600 shrink-0"
    >
      {copiedField === field ? 'Copied!' : 'Copy'}
    </button>
  );

  return (
    <div className="space-y-4 overflow-y-auto">
      {/* Generate button */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-sm font-medium text-gray-300">Recap & Clippable Moments</h3>
          <p className="text-xs text-gray-500 mt-0.5">
            AI-powered recap, top clips, show notes, and social posts
          </p>
        </div>
        <button
          onClick={handleGenerate}
          disabled={loading || !hasTranscript}
          className="bg-[#e0ddaa] text-[#141e27] px-4 py-1.5 rounded text-sm font-medium hover:bg-[#d4d19e] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {loading ? 'Generating...' : content ? 'Regenerate' : 'Generate'}
        </button>
      </div>

      {!hasTranscript && (
        <p className="text-xs text-gray-500">Transcribe a video first to generate content.</p>
      )}

      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">
          {error}
          {error.includes('API key') && (
            <p className="mt-1 text-xs">Set OPENAI_API_KEY or GROQ_API_KEY in your environment, then restart the backend.</p>
          )}
        </div>
      )}

      {loading && (
        <div className="bg-[#1a1f2e] rounded p-6 text-center">
          <p className="text-sm text-gray-400 animate-pulse">Analyzing transcript with AI...</p>
          <p className="text-xs text-gray-600 mt-1">This takes 10-30 seconds</p>
        </div>
      )}

      {content && !loading && (
        <>
          {/* Recap */}
          <section className="bg-[#1a1f2e] rounded-lg p-4 space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium text-[#e0ddaa]">Recap</h4>
              <CopyBtn text={content.recap} field="recap" />
            </div>
            <div className="text-sm text-gray-300 leading-relaxed whitespace-pre-line">
              {content.recap}
            </div>
          </section>

          {/* Clippable Moments */}
          {content.clips?.length > 0 && (
            <section className="space-y-2">
              <h4 className="text-sm font-medium text-[#e0ddaa]">
                Top Clippable Moments ({content.clips.length})
              </h4>
              <div className="space-y-2">
                {content.clips.map((clip, i) => (
                  <div
                    key={i}
                    className="bg-[#1a1f2e] rounded-lg p-3 hover:bg-[#1a1f2e]/80 cursor-pointer"
                    onClick={() => onSeek && onSeek(clip.start_seconds)}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono text-[#e0ddaa] shrink-0">
                            {clip.start} → {clip.end}
                          </span>
                          <span className="text-sm font-medium text-white truncate">
                            {clip.title}
                          </span>
                        </div>
                        <p className="text-xs text-gray-400 mt-1 italic">"{clip.hook}"</p>
                        <p className="text-[10px] text-gray-500 mt-0.5">{clip.why_clip}</p>
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); onSeek && onSeek(clip.start_seconds); }}
                        className="text-[10px] bg-gray-700 text-gray-300 px-2 py-1 rounded hover:bg-gray-600 shrink-0"
                      >
                        Seek
                      </button>
                    </div>
                  </div>
                ))}
              </div>
              <button
                onClick={() => handleCopy(
                  content.clips.map((c, i) => `${i + 1}. [${c.start}-${c.end}] ${c.title}\n   Hook: "${c.hook}"\n   ${c.why_clip}`).join('\n\n'),
                  'clips'
                )}
                className="text-xs bg-gray-700 text-gray-300 px-3 py-1 rounded hover:bg-gray-600"
              >
                {copiedField === 'clips' ? 'Copied!' : 'Copy All Clips'}
              </button>
            </section>
          )}

          {/* Show Notes */}
          {content.show_notes && (
            <section className="bg-[#1a1f2e] rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-sm font-medium text-[#e0ddaa]">Show Notes</h4>
                <CopyBtn text={content.show_notes} field="show_notes" />
              </div>
              <pre className="text-xs text-gray-300 whitespace-pre-wrap font-sans leading-relaxed">
                {content.show_notes}
              </pre>
            </section>
          )}

          {/* Tweets */}
          {content.tweets?.length > 0 && (
            <section className="space-y-2">
              <h4 className="text-sm font-medium text-[#e0ddaa]">Social Posts</h4>
              {content.tweets.map((tweet, i) => (
                <div key={i} className="bg-[#1a1f2e] rounded p-3 flex items-start justify-between gap-2">
                  <p className="text-xs text-gray-300 flex-1">{tweet}</p>
                  <CopyBtn text={tweet} field={`tweet-${i}`} />
                </div>
              ))}
            </section>
          )}

          {/* Model info */}
          <p className="text-[10px] text-gray-600 text-right">
            Generated with {content.model}
          </p>
        </>
      )}
    </div>
  );
}
