import YouTubePanel from './components/YouTubePanel';

export default function StandalonePage() {
  return (
    <div className="min-h-screen bg-[#0f1419]">
      <header className="border-b border-gray-800 px-6 py-4">
        <h1 className="text-2xl font-bold text-[#e0ddaa]">ZAO YouTube Transcript Grabber</h1>
        <p className="text-sm text-gray-400 mt-1">
          Paste a YouTube URL to grab its transcript. Download as chunked .txt files.
        </p>
      </header>
      <main className="max-w-3xl mx-auto p-6">
        <YouTubePanel standalone={true} />
      </main>
    </div>
  );
}
