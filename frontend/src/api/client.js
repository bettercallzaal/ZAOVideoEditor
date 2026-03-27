const BASE = '/api';

async function request(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || 'Request failed');
  }
  return res.json();
}

// --- Task polling ---
export const getTaskStatus = (taskId) => request(`/tasks/${taskId}`);

/**
 * Poll a background task until it completes or errors.
 * Calls onProgress with each status update.
 * Returns the final task result.
 */
export async function pollTask(taskId, onProgress, intervalMs = 1000) {
  while (true) {
    const task = await getTaskStatus(taskId);
    if (onProgress) onProgress(task);

    if (task.status === 'complete') return task;
    if (task.status === 'error') throw new Error(task.error || 'Task failed');

    await new Promise(r => setTimeout(r, intervalMs));
  }
}

// --- Projects ---
export const createProject = (name, description = '') =>
  request('/projects', { method: 'POST', body: JSON.stringify({ name, description }) });

export const listProjects = () => request('/projects');

export const getProject = (name) => request(`/projects/${encodeURIComponent(name)}`);

export const deleteProject = (name) =>
  request(`/projects/${encodeURIComponent(name)}`, { method: 'DELETE' });

export const uploadMainVideo = async (name, file, onProgress) => {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${BASE}/projects/${encodeURIComponent(name)}/upload`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress({ loaded: e.loaded, total: e.total, percent: Math.round((e.loaded / e.total) * 100) });
      }
    };
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
      else reject(new Error(`Upload failed (${xhr.status})`));
    };
    xhr.onerror = () => reject(new Error('Upload failed'));
    const formData = new FormData();
    formData.append('file', file);
    xhr.send(formData);
  });
};

export const uploadIntro = async (name, file) => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${BASE}/projects/${encodeURIComponent(name)}/upload-intro`, { method: 'POST', body: formData });
  if (!res.ok) throw new Error('Intro upload failed');
  return res.json();
};

export const uploadOutro = async (name, file) => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${BASE}/projects/${encodeURIComponent(name)}/upload-outro`, { method: 'POST', body: formData });
  if (!res.ok) throw new Error('Outro upload failed');
  return res.json();
};

export const getVideoUrl = (name, stage = 'source') => {
  if (stage === 'captioned') return `${BASE}/serve-video/${encodeURIComponent(name)}/processing/captioned.mp4`;
  if (stage === 'assembled') return `${BASE}/serve-video/${encodeURIComponent(name)}/processing/assembled.mp4`;
  // For source, we don't know the extension — use the dynamic endpoint
  return `${BASE}/projects/${encodeURIComponent(name)}/video-stream?stage=${stage}`;
};

// --- Assembly (background task) ---
export const assembleVideo = (projectName, useIntro = false, useOutro = false) =>
  request('/assembly/assemble', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, use_intro: useIntro, use_outro: useOutro }),
  });

export const extractAudio = (projectName) =>
  request(`/assembly/extract-audio?project_name=${encodeURIComponent(projectName)}`, { method: 'POST' });

// --- Tools availability ---
export const getAvailableTools = () => request('/tools');

// --- Transcription (background task) ---
export const transcribe = (projectName, quality = 'standard', engine = 'auto', refineTimestamps = true) =>
  request('/transcription/transcribe', {
    method: 'POST',
    body: JSON.stringify({
      project_name: projectName,
      model_size: quality,
      engine,
      refine_timestamps: refineTimestamps,
    }),
  });

export const getRawTranscript = (projectName) =>
  request(`/transcription/${encodeURIComponent(projectName)}/raw`);

// --- Transcript ---
export const applyCorrections = (projectName) =>
  request('/transcript/correct', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName }),
  });

export const cleanupTranscript = (projectName) =>
  request('/transcript/cleanup', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName }),
  });

export const getCurrentTranscript = (projectName) =>
  request(`/transcript/${encodeURIComponent(projectName)}/current`);

export const saveTranscriptEdit = (projectName, segments) =>
  request('/transcript/save-edit', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, segments }),
  });

// --- Dictionary ---
export const getDictionary = () => request('/transcript/dictionary');

export const addDictEntry = (wrong, correct) =>
  request('/transcript/dictionary/add', {
    method: 'POST',
    body: JSON.stringify({ wrong, correct }),
  });

export const removeDictEntry = (wrong) =>
  request(`/transcript/dictionary/${encodeURIComponent(wrong)}`, { method: 'DELETE' });

// --- Captions ---
export const getCaptionStyles = () => request('/captions/styles');

export const generateCaptions = (projectName, style = 'classic') =>
  request('/captions/generate', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, style }),
  });

export const getCaptions = (projectName) =>
  request(`/captions/${encodeURIComponent(projectName)}`);

export const getSrt = (projectName) =>
  request(`/captions/${encodeURIComponent(projectName)}/srt`);

export const getAss = (projectName) =>
  request(`/captions/${encodeURIComponent(projectName)}/ass`);

export const saveCaptions = (projectName, captions) =>
  request(`/captions/${encodeURIComponent(projectName)}/save`, {
    method: 'POST',
    body: JSON.stringify({ captions }),
  });

// Burn captions (background task)
export const burnCaptions = (projectName, style = 'classic', renderer = 'auto') =>
  request('/captions/burn', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, style, renderer }),
  });

// --- Silence removal (auto-editor) ---
export const previewSilenceCuts = (projectName, margin = 0.1, threshold = 0.04) =>
  request('/silence/preview', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, margin, threshold }),
  });

export const removeSilence = (projectName, margin = 0.1, threshold = 0.04) =>
  request('/silence/remove', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, margin, threshold }),
  });

// --- Metadata ---
export const generateMetadata = (projectName) =>
  request('/metadata/generate', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName }),
  });

export const getMetadata = (projectName) =>
  request(`/metadata/${encodeURIComponent(projectName)}`);

export const saveMetadata = (projectName, description, chapters, tags) =>
  request(`/metadata/${encodeURIComponent(projectName)}/save`, {
    method: 'POST',
    body: JSON.stringify({ description, chapters, tags }),
  });

// --- Export ---
export const createExportPackage = (projectName) =>
  request('/export/package', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName }),
  });

export const listExportFiles = (projectName) =>
  request(`/export/${encodeURIComponent(projectName)}/files`);

export const getExportDownloadUrl = (projectName, filename) =>
  `${BASE}/export/${encodeURIComponent(projectName)}/download/${encodeURIComponent(filename)}`;

// --- Storage ---
export const getProjectStorage = (projectName) =>
  request(`/projects/${encodeURIComponent(projectName)}/storage`);

export const getCleanableFiles = (projectName) =>
  request(`/projects/${encodeURIComponent(projectName)}/cleanable`);

export const cleanupProject = (projectName) =>
  request(`/projects/${encodeURIComponent(projectName)}/cleanup`, { method: 'POST' });

export const getAllProjectsStorage = () => request('/storage');

// --- Speakers (diarization) ---
export const diarizeSpeakers = (projectName, numSpeakers = null) =>
  request('/speakers/diarize', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, num_speakers: numSpeakers }),
  });

export const getSpeakers = (projectName) =>
  request(`/speakers/${encodeURIComponent(projectName)}`);

export const renameSpeakers = (projectName, speakerMap) =>
  request('/speakers/rename', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, speaker_map: speakerMap }),
  });

// --- Fillers ---
export const detectFillers = (projectName) =>
  request('/fillers/detect', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName }),
  });

export const removeFillers = (projectName, types = null) =>
  request('/fillers/remove', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, types }),
  });

// --- Clips / Highlights ---
export const detectHighlights = (projectName, count = 5, minDuration = 30, maxDuration = 90) =>
  request('/clips/detect', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, count, min_duration: minDuration, max_duration: maxDuration }),
  });

export const exportClip = (projectName, start, end, title = '', vertical = false) =>
  request('/clips/export', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName, start, end, title, vertical }),
  });

export const listClips = (projectName) =>
  request(`/clips/${encodeURIComponent(projectName)}/list`);

export const getClipDownloadUrl = (projectName, filename) =>
  `${BASE}/clips/${encodeURIComponent(projectName)}/download/${encodeURIComponent(filename)}`;

// --- YouTube ---
export const getYouTubeInfo = (url) =>
  request('/youtube/info', { method: 'POST', body: JSON.stringify({ url }) });

export const youtubeTranscribe = (url, projectName, quality = 'standard') =>
  request('/youtube/transcribe', {
    method: 'POST',
    body: JSON.stringify({ url, project_name: projectName, quality }),
  });

// --- Content Generation ---
export const generateContent = (projectName) =>
  request('/content/generate', {
    method: 'POST',
    body: JSON.stringify({ project_name: projectName }),
  });

export const getContent = (projectName) =>
  request(`/content/${encodeURIComponent(projectName)}`);

// --- AI Tools: Tier 1 (CPU) ---
export const upscaleVideo = (projectName, scale = 2) =>
  request('/ai/upscale', { method: 'POST', body: JSON.stringify({ project_name: projectName, scale }) });

export const removeBackground = (projectName, bgColor = '#00FF00', model = 'u2net') =>
  request('/ai/remove-background', { method: 'POST', body: JSON.stringify({ project_name: projectName, bg_color: bgColor, model }) });

export const detectScenes = (projectName, threshold = 27.0) =>
  request('/ai/detect-scenes', { method: 'POST', body: JSON.stringify({ project_name: projectName, threshold }) });

export const enhanceAudio = (projectName) =>
  request('/ai/enhance-audio', { method: 'POST', body: JSON.stringify({ project_name: projectName }) });

export const generateThumbnails = (projectName, count = 5) =>
  request('/ai/thumbnails', { method: 'POST', body: JSON.stringify({ project_name: projectName, count }) });

export const listThumbnails = (projectName) =>
  request(`/ai/thumbnails/${encodeURIComponent(projectName)}`);

export const getThumbnailUrl = (projectName, filename) =>
  `${BASE}/serve-video/${encodeURIComponent(projectName)}/exports/thumbnails/${encodeURIComponent(filename)}`;

// --- AI Tools: Tier 2 (GPU) ---
export const generateVideo = (projectName, prompt, duration = 6, width = 768, height = 512) =>
  request('/ai/generate-video', { method: 'POST', body: JSON.stringify({ project_name: projectName, prompt, duration, width, height }) });

export const generateBroll = (projectName, prompt, duration = 6, count = 3) =>
  request('/ai/generate-broll', { method: 'POST', body: JSON.stringify({ project_name: projectName, prompt, duration, count }) });

export const textToSpeech = (projectName, text, language = 'en', speakerWav = null) =>
  request('/ai/text-to-speech', { method: 'POST', body: JSON.stringify({ project_name: projectName, text, language, speaker_wav: speakerWav }) });

export const generateMusic = (projectName, prompt, duration = 30, modelSize = 'small') =>
  request('/ai/generate-music', { method: 'POST', body: JSON.stringify({ project_name: projectName, prompt, duration, model_size: modelSize }) });

export const mixMusic = (projectName, volume = 0.15) =>
  request('/ai/mix-music', { method: 'POST', body: JSON.stringify({ project_name: projectName, volume }) });

export const generateAiThumbnail = (projectName, prompt) =>
  request('/ai/ai-thumbnail', { method: 'POST', body: JSON.stringify({ project_name: projectName, prompt }) });
