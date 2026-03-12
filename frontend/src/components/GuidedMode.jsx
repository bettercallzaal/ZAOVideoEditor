import { useState } from 'react';
import VideoPlayer from './VideoPlayer';
import UploadPanel from './UploadPanel';
import TranscriptEditor from './TranscriptEditor';
import CaptionPanel from './CaptionPanel';
import MetadataPanel from './MetadataPanel';
import ExportPanel from './ExportPanel';

const STEPS = [
  { id: 'upload', label: '1. Upload & Transcribe', component: UploadPanel },
  { id: 'transcript', label: '2. Edit Transcript', component: TranscriptEditor },
  { id: 'captions', label: '3. Generate Captions', component: CaptionPanel },
  { id: 'metadata', label: '4. YouTube Metadata', component: MetadataPanel },
  { id: 'export', label: '5. Export', component: ExportPanel },
];

export default function GuidedMode({ projectName, project, videoSrc, onSeek, seekTime, onStageComplete, onExit, onBack }) {
  const [currentStep, setCurrentStep] = useState(0);

  const step = STEPS[currentStep];
  const StepComponent = step.component;

  return (
    <div className="h-screen flex flex-col bg-[#0f1419]">
      {/* Top bar */}
      <header className="border-b border-gray-800 px-4 py-2 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <button onClick={onBack} className="text-gray-400 hover:text-white text-sm">&larr; Projects</button>
          <h2 className="text-lg font-semibold text-[#e0ddaa]">{projectName}</h2>
          <span className="text-xs bg-[#e0ddaa]/20 text-[#e0ddaa] px-2 py-0.5 rounded">Guided Mode</span>
        </div>
        <button onClick={onExit} className="text-xs text-gray-400 hover:text-white">
          Switch to Workspace
        </button>
      </header>

      <div className="flex flex-1 min-h-0">
        {/* Left: Video */}
        <div className="w-1/2 border-r border-gray-800 flex flex-col">
          <VideoPlayer src={videoSrc} seekTime={seekTime} />
        </div>

        {/* Right: Guided steps */}
        <div className="w-1/2 flex flex-col min-h-0">
          {/* Step navigation */}
          <div className="flex border-b border-gray-800 shrink-0">
            {STEPS.map((s, i) => (
              <button
                key={s.id}
                onClick={() => setCurrentStep(i)}
                className={`flex-1 px-2 py-2 text-xs text-center ${
                  i === currentStep
                    ? 'text-[#e0ddaa] border-b-2 border-[#e0ddaa] bg-[#1a1f2e]'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {s.label}
              </button>
            ))}
          </div>

          {/* Step content */}
          <div className="flex-1 overflow-y-auto p-4">
            <StepComponent
              projectName={projectName}
              stages={project.stages}
              onSeek={onSeek}
              onComplete={onStageComplete}
            />
          </div>

          {/* Navigation buttons */}
          <div className="border-t border-gray-800 px-4 py-3 flex justify-between shrink-0">
            <button
              onClick={() => setCurrentStep(Math.max(0, currentStep - 1))}
              disabled={currentStep === 0}
              className="text-sm text-gray-400 hover:text-white disabled:opacity-30"
            >
              &larr; Previous
            </button>
            <button
              onClick={() => setCurrentStep(Math.min(STEPS.length - 1, currentStep + 1))}
              disabled={currentStep === STEPS.length - 1}
              className="text-sm bg-[#e0ddaa] text-[#141e27] px-4 py-1.5 rounded font-medium hover:bg-[#d4d19e] disabled:opacity-30"
            >
              Next &rarr;
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
