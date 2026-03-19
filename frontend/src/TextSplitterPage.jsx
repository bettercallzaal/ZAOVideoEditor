import TextSplitter from './components/TextSplitter';

export default function TextSplitterPage({ onBack }) {
  return (
    <div className="min-h-screen bg-[#0f1419]">
      <header className="border-b border-gray-800 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-[#e0ddaa]">Text Splitter</h1>
          <p className="text-sm text-gray-400 mt-1">
            Paste text and download it split into 49k character .txt files
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
        <TextSplitter />
      </main>
    </div>
  );
}
