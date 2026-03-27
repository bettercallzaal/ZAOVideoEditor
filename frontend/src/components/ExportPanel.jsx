import { useState, useEffect } from 'react';
import ProgressBar from './ProgressBar';
import SeoChecklist from './SeoChecklist';
import StoragePanel from './StoragePanel';
import { createExportPackage, listExportFiles, getExportDownloadUrl, getNotebookLMDownloadUrl, getNotebookLMText, getGDriveStatus, uploadToGDrive } from '../api/client';

export default function ExportPanel({ projectName, stages, onComplete }) {
  const [files, setFiles] = useState([]);
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [progressStatus, setProgressStatus] = useState('');
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [gdriveAvailable, setGdriveAvailable] = useState(false);
  const [gdriveUploading, setGdriveUploading] = useState(false);
  const [gdriveResult, setGdriveResult] = useState(null);

  const loadFiles = async () => {
    try {
      const data = await listExportFiles(projectName);
      setFiles(data);
    } catch (e) {
      // No exports yet
    }
  };

  useEffect(() => {
    loadFiles();
    getGDriveStatus()
      .then((res) => setGdriveAvailable(res.configured))
      .catch(() => setGdriveAvailable(false));
  }, []);

  const handleExport = async () => {
    setExporting(true);
    setError('');
    setProgress(50);
    setProgressStatus('Packaging export files...');

    try {
      const result = await createExportPackage(projectName);
      setProgress(100);
      setProgressStatus(`Export complete — ${result.files.length} files packaged`);
      setFiles(result.files);
      onComplete();
    } catch (e) {
      setError(`Export failed: ${e.message}`);
      setProgress(0);
      setProgressStatus('');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* SEO Checklist */}
      <SeoChecklist projectName={projectName} stages={stages} />

      <hr className="border-gray-800" />

      {/* Export button */}
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

      {/* NotebookLM export */}
      <div className="flex gap-2">
        <a
          href={getNotebookLMDownloadUrl(projectName)}
          className="flex-1 text-center bg-gray-700 text-gray-300 px-4 py-2 rounded-lg text-sm hover:bg-gray-600"
        >
          Export for NotebookLM
        </a>
        <button
          onClick={async () => {
            try {
              const text = await getNotebookLMText(projectName);
              await navigator.clipboard.writeText(text);
              setCopied(true);
              setTimeout(() => setCopied(false), 2000);
            } catch (e) {
              setError(`Copy failed: ${e.message}`);
            }
          }}
          className="flex-1 bg-gray-700 text-gray-300 px-4 py-2 rounded-lg text-sm hover:bg-gray-600"
        >
          {copied ? 'Copied!' : 'Copy for NotebookLM'}
        </button>
      </div>
      <p className="text-xs text-gray-500">
        Formatted plain-text transcript with timestamps, optimized for Google NotebookLM.
      </p>

      {/* Google Drive upload */}
      {gdriveAvailable && (
        <div className="space-y-2">
          <button
            onClick={async () => {
              setGdriveUploading(true);
              setGdriveResult(null);
              setError('');
              try {
                const result = await uploadToGDrive(projectName);
                setGdriveResult(result);
              } catch (e) {
                setError(`Google Drive upload failed: ${e.message}`);
              } finally {
                setGdriveUploading(false);
              }
            }}
            disabled={gdriveUploading}
            className="bg-blue-600 text-white px-6 py-3 rounded-lg font-medium hover:bg-blue-500 disabled:opacity-50 w-full"
          >
            {gdriveUploading ? 'Uploading to Google Drive...' : 'Upload to Google Drive'}
          </button>
          <p className="text-xs text-gray-500">
            Uploads transcripts, captions, and metadata to Google Drive under "ZAO Transcripts/{projectName}/".
          </p>
          {gdriveResult && gdriveResult.files && gdriveResult.files.length > 0 && (
            <div className="space-y-1">
              <h4 className="text-sm font-medium text-gray-300">Uploaded to Drive</h4>
              {gdriveResult.files.map((f) => (
                <div key={f.id} className="flex items-center justify-between bg-[#1a1f2e] rounded px-3 py-2">
                  <span className="text-sm text-gray-300">{f.name}</span>
                  {f.link && (
                    <a
                      href={f.link}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-xs text-[#e0ddaa] hover:underline"
                    >
                      Open in Drive
                    </a>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

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

      <hr className="border-gray-800" />

      {/* Storage info & cleanup */}
      <StoragePanel projectName={projectName} />
    </div>
  );
}
