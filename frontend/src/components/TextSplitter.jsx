import { useState, useRef } from 'react';

const CHAR_LIMIT = 49000;

export default function TextSplitter() {
  const [text, setText] = useState('');
  const [fileName, setFileName] = useState('split_text');
  const textareaRef = useRef(null);

  const charCount = text.length;
  const numParts = charCount > 0 ? Math.ceil(charCount / CHAR_LIMIT) : 0;

  const buildChunks = () => {
    if (!text.trim()) return [];
    const lines = text.split('\n');
    const chunks = [];
    let current = '';

    for (const line of lines) {
      if (current.length + line.length + 1 > CHAR_LIMIT && current.length > 0) {
        chunks.push(current);
        current = line;
      } else {
        current += (current ? '\n' : '') + line;
      }
    }
    if (current) chunks.push(current);
    return chunks;
  };

  const getSafeName = () =>
    fileName.replace(/[^a-zA-Z0-9 _-]/g, '').trim() || 'split_text';

  const getPartFileName = (total, index) => {
    const safeName = getSafeName();
    return total === 1
      ? `${safeName}.txt`
      : `${safeName}_part${index + 1}_of_${total}.txt`;
  };

  const downloadBlob = (content, name) => {
    const blob = new Blob([content], { type: 'text/plain' });
    const dlUrl = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = dlUrl;
    a.download = name;
    a.click();
    URL.revokeObjectURL(dlUrl);
  };

  const handleDownloadPart = (index) => {
    const chunks = buildChunks();
    if (!chunks[index]) return;
    downloadBlob(chunks[index], getPartFileName(chunks.length, index));
  };

  const handleDownloadAll = () => {
    const chunks = buildChunks();
    if (!chunks.length) return;
    // Stagger downloads so the browser doesn't block them
    chunks.forEach((chunk, i) => {
      setTimeout(() => {
        downloadBlob(chunk, getPartFileName(chunks.length, i));
      }, i * 300);
    });
  };

  const handleClear = () => {
    setText('');
    textareaRef.current?.focus();
  };

  return (
    <div className="space-y-4">
      {/* File name input */}
      <div>
        <label className="text-xs text-gray-500 block mb-1">File name prefix</label>
        <input
          type="text"
          value={fileName}
          onChange={(e) => setFileName(e.target.value)}
          placeholder="split_text"
          className="w-64 bg-[#1a1f2e] border border-gray-700 rounded px-3 py-2 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-[#e0ddaa]"
        />
      </div>

      {/* Text area */}
      <div>
        <label className="text-xs text-gray-500 block mb-1">Paste your text below</label>
        <textarea
          ref={textareaRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Paste or type text here..."
          className="w-full h-96 bg-[#1a1f2e] border border-gray-700 rounded px-3 py-3 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-[#e0ddaa] resize-y font-mono leading-relaxed"
        />
      </div>

      {/* Stats */}
      <div className="flex items-center gap-4 text-xs text-gray-400">
        <span>{charCount.toLocaleString()} characters</span>
        {charCount > 0 && (
          <span>
            {numParts} {numParts === 1 ? 'file' : 'files'} @ 49k max each
          </span>
        )}
      </div>

      {/* Per-part download buttons */}
      {numParts > 1 && (
        <div className="flex flex-wrap gap-2">
          {Array.from({ length: numParts }, (_, i) => (
            <button
              key={i}
              onClick={() => handleDownloadPart(i)}
              className="text-xs bg-[#1a1f2e] border border-[#e0ddaa]/40 text-[#e0ddaa] px-3 py-1.5 rounded hover:bg-[#e0ddaa]/10"
            >
              Part {i + 1}
            </button>
          ))}
        </div>
      )}

      {/* Actions bar */}
      <div className="flex items-center justify-end gap-2">
        {text.length > 0 && (
          <button
            onClick={handleClear}
            className="text-xs bg-gray-700 text-gray-300 px-3 py-1.5 rounded hover:bg-gray-600"
          >
            Clear
          </button>
        )}
        <button
          onClick={handleDownloadAll}
          disabled={!text.trim()}
          className="text-sm bg-[#e0ddaa] text-[#141e27] px-5 py-1.5 rounded font-medium hover:bg-[#d4d19e] disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {numParts > 1 ? `Download All ${numParts} Parts` : 'Download .txt'}
        </button>
      </div>
    </div>
  );
}
