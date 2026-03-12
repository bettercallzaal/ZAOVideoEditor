import { useState, useEffect } from 'react';
import { getDictionary, addDictEntry, removeDictEntry } from '../api/client';

export default function DictionaryManager() {
  const [dict, setDict] = useState({});
  const [newWrong, setNewWrong] = useState('');
  const [newCorrect, setNewCorrect] = useState('');
  const [status, setStatus] = useState('');

  const loadDict = async () => {
    try {
      const data = await getDictionary();
      setDict(data.corrections || {});
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  };

  useEffect(() => { loadDict(); }, []);

  const handleAdd = async (e) => {
    e.preventDefault();
    if (!newWrong.trim() || !newCorrect.trim()) return;
    try {
      await addDictEntry(newWrong.trim(), newCorrect.trim());
      setStatus(`Added: "${newWrong}" -> "${newCorrect}"`);
      setNewWrong('');
      setNewCorrect('');
      await loadDict();
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  };

  const handleRemove = async (wrong) => {
    try {
      await removeDictEntry(wrong);
      await loadDict();
      setStatus(`Removed: "${wrong}"`);
    } catch (e) {
      setStatus(`Error: ${e.message}`);
    }
  };

  const entries = Object.entries(dict);

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-medium text-gray-300">Correction Dictionary</h3>
      <p className="text-xs text-gray-500">
        Brand names and people that transcription often misspells. Shared across all projects.
      </p>

      {/* Add form */}
      <form onSubmit={handleAdd} className="flex gap-2">
        <input
          value={newWrong}
          onChange={(e) => setNewWrong(e.target.value)}
          placeholder="Wrong spelling..."
          className="flex-1 bg-[#1a1f2e] border border-gray-700 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-[#e0ddaa]"
        />
        <input
          value={newCorrect}
          onChange={(e) => setNewCorrect(e.target.value)}
          placeholder="Correct spelling..."
          className="flex-1 bg-[#1a1f2e] border border-gray-700 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-[#e0ddaa]"
        />
        <button
          type="submit"
          className="bg-[#e0ddaa] text-[#141e27] px-4 py-1.5 rounded text-sm font-medium hover:bg-[#d4d19e]"
        >
          Add
        </button>
      </form>

      {status && (
        <div className="text-xs text-gray-400 bg-[#1a1f2e] p-2 rounded">{status}</div>
      )}

      {/* Entries */}
      {entries.length === 0 ? (
        <p className="text-gray-500 text-sm">No corrections yet.</p>
      ) : (
        <div className="space-y-1">
          {entries.map(([wrong, correct]) => (
            <div
              key={wrong}
              className="flex items-center justify-between bg-[#1a1f2e] rounded px-3 py-2"
            >
              <div className="text-sm">
                <span className="text-red-400 line-through">{wrong}</span>
                <span className="text-gray-500 mx-2">-&gt;</span>
                <span className="text-green-400">{correct}</span>
              </div>
              <button
                onClick={() => handleRemove(wrong)}
                className="text-xs text-gray-500 hover:text-red-400"
              >
                Remove
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
