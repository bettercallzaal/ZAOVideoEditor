import { useState, useEffect } from 'react';
import ProgressBar from './ProgressBar';
import { createExportPackage, listExportFiles, getExportDownloadUrl } from '../api/client';

export default function ExportPanel({ projectName, stages, onComplete }) {
  const [files, setFiles] = useState([]);
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState('');
  const [error, setError] = useState('');

  const loadFiles = async () => {
    try {
      const data = await listExportFiles(projectName);
      setFiles(data);
    } catch (e) {
      // No exports yet
    }
  };

  useEffect(() => { loadFiles(); }, []);

  const handleExport = async () => {
    setExporting(true);
    setError('');
    setProgress(10);
    setProgressStatus('Packaging export files...');

    const interval = setInterval(() => {
      setProgress(prev => prev >= 80 ? prev : prev + 15);
    }, 500);

    try {
      const result = await createExportPackage(projectName);
      clearInterval(interval);
      setProgress(100);
      setProgressStatus(`Export complete — ${result.files.length} files packaged`);
      setFiles(result.files);
      onComplete();
    } catch (e) {
      clearInterval(interval);
      setError(`Export failed: ${e.message}`);
      setProgressStatus('Failed');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-4">
      {!exporting && (
        <button
          onClick={handleExport}
          className="bg-[#e0ddaa] text-[#141e27] px-6 py-3 rounded-lg font-medium hover:bg-[#d4d19e] w-full"
        >
          Create Export Package
        </button>
      )}
      <p className="text-xs text-gray-500">
        Packages all available outputs: video, captions (SRT/ASS), transcript, and metadata files.
      </p>

      {/* Progress */}
      {(exporting || progress > 0) && (
        <ProgressBar progress={progress} status={progressStatus} />
      )}

      {/* Error */}
      {error && (
        <div className="bg-red-900/30 border border-red-800 rounded p-3 text-sm text-red-300">{error}</div>
      )}

      {files.length > 0 && (
        <div className="space-y-1">
          <h4 className="text-sm font-medium text-gray-300">Export Files</h4>
          {files.map((f) => (
            <div key={f} className="flex items-center justify-between bg-[#1a1f2e] rounded px-3 py-2">
              <span className="text-sm text-gray-300">{f}</span>
              <a
                href={getExportDownloadUrl(projectName, f)}
                download
                className="text-xs text-[#e0ddaa] hover:underline"
              >
                Download
              </a>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
