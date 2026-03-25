import { useState } from 'react';
import TextSplitter from './components/TextSplitter';
import YouTubePanel from './components/YouTubePanel';

export default function TextSplitterPage({ onBack }) {
  const [mode, setMode] = useState('paste'); // 'paste' | 'youtube'

  return (
    <div className="min-h-screen bg-[#0f1419]">
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#e0ddaa]">Text Splitter</h1>
          <p className="text-sm text-gray-400 mt-1">
            {mode === 'paste'
              ? 'Paste text and download it split into 49k character .txt files'
              : 'Grab a YouTube transcript and download it split into 49k character .txt files'}
          </p>
        </div>
        {onBack && (
          <button
            onClick={onBack}
            className="text-sm text-gray-400 hover:text-white"
          >
            &larr; Back
          </button>
        )}
      </header>
      <main className="max-w-3xl mx-auto p-6">
        {/* Mode toggle */}
        <div className="flex gap-2 mb-6">
          <button
            onClick={() => setMode('paste')}
            className={`text-sm px-4 py-2 rounded font-medium transition-colors ${
              mode === 'paste'
                ? 'bg-[#e0ddaa] text-[#141e27]'
                : 'bg-[#1a1f2e] text-gray-400 border border-gray-700 hover:text-white hover:border-gray-500'
            }`}
          >
            Paste Text
          </button>
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
        </div>

        {mode === 'paste' ? <TextSplitter /> : <YouTubePanel standalone={true} />}
      </main>
    </div>
  );
}
