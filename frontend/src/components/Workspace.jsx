import { useState, useEffect, useRef, useCallback } from 'react';
import VideoPlayer from './VideoPlayer';
import CaptionOverlay from './CaptionOverlay';
import StageStatus from './StageStatus';
import UploadPanel from './UploadPanel';
import TranscriptEditor from './TranscriptEditor';
import CaptionPanel from './CaptionPanel';
import MetadataPanel from './MetadataPanel';
import DictionaryManager from './DictionaryManager';
import ExportPanel from './ExportPanel';
import ClipsPanel from './ClipsPanel';
import AiToolsPanel from './AiToolsPanel';
import YouTubePanel from './YouTubePanel';
import SeoChecklist from './SeoChecklist';
import GuidedMode from './GuidedMode';
import { getProject, getVideoUrl } from '../api/client';

const TABS = [
  { id: 'upload', label: 'Upload' },
  { id: 'youtube', label: 'YouTube' },
  { id: 'transcript', label: 'Transcript' },
  { id: 'captions', label: 'Captions' },
  { id: 'clips', label: 'Clips' },
  { id: 'ai', label: 'AI Tools' },
  { id: 'metadata', label: 'Metadata' },
  { id: 'dictionary', label: 'Dictionary' },
  { id: 'export', label: 'Export' },
];

export default function Workspace({ projectName, onBack }) {
  const [project, setProject] = useState(null);
  const [activeTab, setActiveTab] = useState('upload');
  const [guidedMode, setGuidedMode] = useState(false);
  const [videoSrc, setVideoSrc] = useState('');
  const [seekTime, setSeekTime] = useState(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [videoDuration, setVideoDuration] = useState(0);
  const [videoRect, setVideoRect] = useState(null);
  const videoRef = useRef(null);

  // Caption state shared between CaptionPanel and CaptionOverlay
  const [liveCaptions, setLiveCaptions] = useState([]);
  const [captionStyle, setCaptionStyle] = useState(() => {
    try { return localStorage.getItem(`zao:${projectName}:captionStyle`) || 'classic'; } catch { return 'classic'; }
  });
  const [captionPosition, setCaptionPosition] = useState(() => {
    try {
      const saved = localStorage.getItem(`zao:${projectName}:captionPos`);
      return saved ? JSON.parse(saved) : { x: 50, y: 88 };
    } catch { return { x: 50, y: 88 }; }
  });
  const [selectedCaptionId, setSelectedCaptionId] = useState(null);

  // Persist caption position and style to localStorage
  useEffect(() => {
    try { localStorage.setItem(`zao:${projectName}:captionPos`, JSON.stringify(captionPosition)); } catch {}
  }, [captionPosition, projectName]);
  useEffect(() => {
    try { localStorage.setItem(`zao:${projectName}:captionStyle`, captionStyle); } catch {}
  }, [captionStyle, projectName]);

  const refreshProject = useCallback(async () => {
    try {
      const data = await getProject(projectName);
      setProject(data);

      // Set video source based on what's available
      if (data.stages.burn_captions === 'complete') {
        setVideoSrc(getVideoUrl(projectName, 'captioned'));
      } else if (data.stages.assembly === 'complete') {
        setVideoSrc(getVideoUrl(projectName, 'assembled'));
      } else if (data.stages.upload === 'complete') {
        setVideoSrc(getVideoUrl(projectName, 'source'));
      }
    } catch (e) {
      console.error('Failed to load project:', e);
    }
  }, [projectName]);

  useEffect(() => { refreshProject(); }, [refreshProject]);

  // When switching to captions tab, use un-captioned source
  useEffect(() => {
    if (!project) return;
    if (activeTab === 'captions') {
      if (project.stages.assembly === 'complete') {
        setVideoSrc(getVideoUrl(projectName, 'assembled'));
      } else if (project.stages.upload === 'complete') {
        setVideoSrc(getVideoUrl(projectName, 'source'));
      }
    } else if (project.stages.burn_captions === 'complete') {
      setVideoSrc(getVideoUrl(projectName, 'captioned'));
    }
  }, [activeTab, project, projectName]);

  const handleSeek = (time) => {
    setSeekTime(time);
  };

  const handleTimeUpdate = useCallback((time) => {
    setCurrentTime(time);
    // Update video rect for overlay positioning
    if (videoRef.current) {
      const rect = videoRef.current.getVideoRect();
      if (rect) setVideoRect(rect);
      const dur = videoRef.current.getDuration();
      if (dur && dur !== videoDuration) setVideoDuration(dur);
    }
  }, [videoDuration]);

  const handleStageComplete = () => {
    refreshProject();
  };

  if (!project) return <div className="p-6 text-gray-400">Loading project...</div>;

  if (guidedMode) {
    return (
      <GuidedMode
        projectName={projectName}
        project={project}
        videoSrc={videoSrc}
        onSeek={handleSeek}
        seekTime={seekTime}
        onStageComplete={handleStageComplete}
        onExit={() => setGuidedMode(false)}
        onBack={onBack}
      />
    );
  }

  const showCaptionOverlay = activeTab === 'captions' && liveCaptions.length > 0;

  return (
    <div className="h-screen flex flex-col bg-[#0f1419]">
      {/* Top bar */}
      <header className="border-b border-gray-800 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="text-gray-400 hover:text-white text-sm">&larr; Projects</button>
          <h2 className="text-lg font-semibold text-[#e0ddaa]">{projectName}</h2>
        </div>
        <div className="flex items-center gap-3">
          <button
            onClick={() => setGuidedMode(true)}
            className="text-xs bg-[#1a1f2e] text-[#e0ddaa] px-3 py-1.5 rounded border border-[#e0ddaa]/30 hover:border-[#e0ddaa]/60"
          >
            Guided Mode
          </button>
          <StageStatus stages={project.stages} />
        </div>
      </header>

      {/* Main content */}
      <div className="flex flex-1 min-h-0">
        {/* Left: Video player with caption overlay */}
        <div className="w-1/2 border-r border-gray-800 flex flex-col">
          <VideoPlayer
            src={videoSrc}
            seekTime={seekTime}
            ref={videoRef}
            onTimeUpdate={handleTimeUpdate}
          >
            {showCaptionOverlay && (
              <CaptionOverlay
                captions={liveCaptions}
                currentTime={currentTime}
                style={captionStyle}
                position={captionPosition}
                onPositionChange={setCaptionPosition}
                videoRect={videoRect}
                selectedId={selectedCaptionId}
                onSelect={setSelectedCaptionId}
              />
            )}
          </VideoPlayer>
        </div>

        {/* Right: Panels */}
        <div className="w-1/2 flex flex-col min-h-0">
          {/* Tabs */}
          <div className="flex border-b border-gray-800 shrink-0">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 text-sm ${
                  activeTab === tab.id
                    ? 'text-[#e0ddaa] border-b-2 border-[#e0ddaa]'
                    : 'text-gray-400 hover:text-gray-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* Tab content */}
          <div className="flex-1 overflow-hidden p-4 flex flex-col">
            {activeTab === 'upload' && (
              <UploadPanel
                projectName={projectName}
                stages={project.stages}
                onComplete={handleStageComplete}
              />
            )}
            {activeTab === 'youtube' && (
              <YouTubePanel
                projectName={projectName}
                stages={project.stages}
                onComplete={handleStageComplete}
              />
            )}
            {activeTab === 'transcript' && (
              <TranscriptEditor
                projectName={projectName}
                stages={project.stages}
                onSeek={handleSeek}
                onComplete={handleStageComplete}
              />
            )}
            {activeTab === 'captions' && (
              <CaptionPanel
                projectName={projectName}
                stages={project.stages}
                onComplete={handleStageComplete}
                onSeek={handleSeek}
                currentTime={currentTime}
                videoDuration={videoDuration}
                onCaptionsChange={setLiveCaptions}
                onStyleChange={setCaptionStyle}
                onPositionChange={setCaptionPosition}
              />
            )}
            {activeTab === 'metadata' && (
              <MetadataPanel
                projectName={projectName}
                stages={project.stages}
                onComplete={handleStageComplete}
              />
            )}
            {activeTab === 'clips' && (
              <ClipsPanel
                projectName={projectName}
                stages={project.stages}
                onSeek={handleSeek}
              />
            )}
            {activeTab === 'ai' && (
              <AiToolsPanel
                projectName={projectName}
                stages={project.stages}
                onComplete={handleStageComplete}
                onSeek={handleSeek}
              />
            )}
            {activeTab === 'dictionary' && (
              <DictionaryManager />
            )}
            {activeTab === 'export' && (
              <ExportPanel
                projectName={projectName}
                stages={project.stages}
                onComplete={handleStageComplete}
              />
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
