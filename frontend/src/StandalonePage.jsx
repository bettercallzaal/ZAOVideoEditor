import { useState } from 'react';
import YouTubePanel from './components/YouTubePanel';
import TextSplitter from './components/TextSplitter';

export default function StandalonePage() {
  const [mode, setMode] = useState('youtube'); // 'youtube' | 'paste'

  return (
    <div className="min-h-screen bg-[#0f1419]">
      <header className="border-b border-gray-800 px-6 py-4">
        <h1 className="text-2xl font-bold text-[#e0ddaa]">ZAO Tools</h1>
        <p className="text-sm text-gray-400 mt-1">
          {mode === 'youtube'
            ? 'Grab a YouTube transcript and download as chunked .txt files'
            : 'Paste text and download it split into 49k character .txt files'}
        </p>
      </header>
      <main className="max-w-3xl mx-auto p-6">
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setMode('youtube')}
            className={`text-sm px-4 py-2 rounded font-medium transition-colors ${
              mode === 'youtube'
                ? 'bg-[#e0ddaa] text-[#141e27]'
                : 'bg-[#1a1f2e] text-gray-400 border border-gray-700 hover:text-white hover:border-gray-500'
            }`}
          >
            YouTube Transcript
          </button>
          <button
            onClick={() => setMode('paste')}
            className={`text-sm px-4 py-2 rounded font-medium transition-colors ${
              mode === 'paste'
                ? 'bg-[#e0ddaa] text-[#141e27]'
                : 'bg-[#1a1f2e] text-gray-400 border border-gray-700 hover:text-white hover:border-gray-500'
            }`}
          >
            Text Splitter
          </button>
        </div>

        {mode === 'youtube' ? <YouTubePanel standalone={true} /> : <TextSplitter />}
      </main>
    </div>
  );
}
