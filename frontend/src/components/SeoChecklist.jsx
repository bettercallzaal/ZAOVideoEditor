import { useState, useEffect } from 'react';
import { getMetadata, getCaptions, getCurrentTranscript } from '../api/client';

const CHECK = '\u2713';
const CROSS = '\u2717';
const WARN = '!';

export default function SeoChecklist({ projectName, stages }) {
  const [checks, setChecks] = useState([]);
  const [score, setScore] = useState(0);
  const [loading, setLoading] = useState(false);

  const runChecks = async () => {
    setLoading(true);
    const results = [];

    // 1. Transcript exists
    const hasTranscript = stages.transcription === 'complete';
    results.push({
      label: 'Transcript available',
      status: hasTranscript ? 'pass' : 'fail',
      detail: hasTranscript
        ? 'Transcript helps YouTube index your content'
        : 'Run transcription to enable captions and metadata',
    });

    // 2. Captions generated
    const hasCaptions = stages.captions === 'complete';
    results.push({
      label: 'Captions / subtitles generated',
      status: hasCaptions ? 'pass' : 'fail',
      detail: hasCaptions
        ? 'SRT/ASS ready for upload'
        : 'Generate captions from the transcript',
    });

    // 3. Metadata checks
    let meta = null;
    try { meta = await getMetadata(projectName); } catch (e) { /* no metadata */ }

    const hasDesc = meta && meta.description && meta.description.length > 50;
    results.push({
      label: 'Description written (50+ chars)',
      status: hasDesc ? 'pass' : 'fail',
      detail: hasDesc
        ? `${meta.description.length} characters`
        : 'Write a description in the Metadata tab',
    });

    if (meta && meta.description) {
      const first150 = meta.description.slice(0, 150);
      const hasHook = first150.length >= 100 && !first150.toLowerCase().startsWith('in this');
      results.push({
        label: 'Strong first 150 chars (search snippet)',
        status: hasHook ? 'pass' : 'warn',
        detail: hasHook
          ? `Hook: "${first150.slice(0, 60)}..."`
          : 'First 150 chars appear in YouTube search results — make them count',
      });

      const descLen = meta.description.length;
      results.push({
        label: 'Description length (200-5000 chars)',
        status: descLen >= 200 && descLen <= 5000 ? 'pass' : descLen < 200 ? 'warn' : 'fail',
        detail: `${descLen} characters${descLen < 200 ? ' — aim for 200+ words for SEO' : ''}`,
      });
    }

    // 4. Chapters
    if (meta && meta.chapters) {
      const lines = meta.chapters.split('\n').filter(l => l.trim());
      const startsAt00 = lines.length > 0 && lines[0].trim().startsWith('00:00');
      const enoughChapters = lines.length >= 3;

      results.push({
        label: 'Chapters start at 00:00',
        status: startsAt00 ? 'pass' : 'fail',
        detail: startsAt00 ? 'Required by YouTube' : 'First chapter must start at 00:00',
      });
      results.push({
        label: 'At least 3 chapters',
        status: enoughChapters ? 'pass' : 'fail',
        detail: `${lines.length} chapters${!enoughChapters ? ' — YouTube requires minimum 3' : ''}`,
      });
    } else {
      results.push({
        label: 'Chapters generated',
        status: 'fail',
        detail: 'Generate chapters in the Metadata tab',
      });
    }

    // 5. Tags
    if (meta && meta.tags) {
      const tagCount = meta.tags.split(',').filter(t => t.trim()).length;
      const tagChars = meta.tags.length;

      results.push({
        label: 'Tags added (5-20 recommended)',
        status: tagCount >= 5 ? 'pass' : tagCount >= 1 ? 'warn' : 'fail',
        detail: `${tagCount} tags, ${tagChars}/500 characters`,
      });

      results.push({
        label: 'Tags within 500 char limit',
        status: tagChars <= 500 ? 'pass' : 'fail',
        detail: tagChars > 500 ? `${tagChars} chars — over the 500 limit` : `${tagChars} characters`,
      });
    } else {
      results.push({
        label: 'Tags generated',
        status: 'fail',
        detail: 'Generate tags in the Metadata tab',
      });
    }

    // 6. Captions burned (optional but good)
    const hasBurn = stages.burn_captions === 'complete';
    results.push({
      label: 'Captions burned into video (optional)',
      status: hasBurn ? 'pass' : 'info',
      detail: hasBurn
        ? 'Burned-in captions improve engagement for social sharing'
        : 'Consider burning captions for social media clips',
    });

    // 7. Reminder: thumbnail
    results.push({
      label: 'Custom thumbnail prepared',
      status: 'info',
      detail: 'Custom thumbnails get 90% more clicks than auto-generated ones',
    });

    // Calculate score
    const passCount = results.filter(r => r.status === 'pass').length;
    const totalGraded = results.filter(r => r.status !== 'info').length;
    const pct = totalGraded > 0 ? Math.round((passCount / totalGraded) * 100) : 0;

    setChecks(results);
    setScore(pct);
    setLoading(false);
  };

  useEffect(() => {
    runChecks();
  }, [stages]);

  const statusIcon = (status) => {
    switch (status) {
      case 'pass': return <span className="text-green-400">{CHECK}</span>;
      case 'fail': return <span className="text-red-400">{CROSS}</span>;
      case 'warn': return <span className="text-yellow-400">{WARN}</span>;
      default: return <span className="text-gray-500">-</span>;
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium text-gray-300">YouTube SEO Readiness</h3>
        <div className="flex items-center gap-2">
          <div className={`text-lg font-bold ${
            score >= 80 ? 'text-green-400' : score >= 50 ? 'text-yellow-400' : 'text-red-400'
          }`}>
            {score}%
          </div>
          <button onClick={runChecks} disabled={loading}
            className="text-xs text-gray-500 hover:text-gray-300">
            Refresh
          </button>
        </div>
      </div>

      {/* Progress bar */}
      <div className="w-full bg-gray-800 rounded-full h-2">
        <div
          className={`h-2 rounded-full transition-all ${
            score >= 80 ? 'bg-green-500' : score >= 50 ? 'bg-yellow-500' : 'bg-red-500'
          }`}
          style={{ width: `${score}%` }}
        />
      </div>

      {/* Checklist */}
      <div className="space-y-1">
        {checks.map((check, i) => (
          <div key={i} className={`flex gap-3 p-2 rounded ${
            check.status === 'fail' ? 'bg-red-900/10' : ''
          }`}>
            <div className="w-5 text-center shrink-0 mt-0.5">{statusIcon(check.status)}</div>
            <div className="flex-1 min-w-0">
              <p className="text-sm text-gray-200">{check.label}</p>
              <p className="text-xs text-gray-500">{check.detail}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
