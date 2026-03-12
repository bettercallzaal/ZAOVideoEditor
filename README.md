# ZAO Video Editor

A local-first video processing app built for conversation-based content — podcasts, livestreams, Twitter/X Spaces, Zoom calls, and community recordings.

Upload a video, transcribe it locally, clean up the transcript, generate branded captions, burn them in, and export everything YouTube-ready. No cloud, no API keys, no accounts.

---

## What It Does

The full workflow in one app:

1. **Upload** a main video (mp4, mov, mkv, webm)
2. **Optionally add** intro and outro clips — auto-converted to match the main video
3. **Assemble** into a single source video via ffmpeg
4. **Transcribe** locally using Faster Whisper with configurable quality (fast/standard/high)
5. **Correct** brand/name misspellings using a persistent shared dictionary
6. **Clean and polish** the transcript — remove fillers, fix stutters, improve punctuation
7. **Edit** the transcript manually in a video-synced editor (click to seek)
8. **Generate captions** — single-line, 3-6 words, readable timing
9. **Choose a caption theme** — Dark on Light or Light on Dark
10. **Burn captions** into the video with Pillow + ffmpeg overlay
11. **Generate YouTube metadata** — description, chapters, tags (NLP-powered, no external LLM)
12. **Export** everything to a project folder: captioned video, SRT, ASS, transcript, metadata

Any stage can be re-run independently. Edit the transcript and regenerate just the captions. Switch themes and re-burn. Regenerate metadata without re-transcribing.

---

## Quick Start

### Prerequisites

- **Python 3.10+** with pip
- **Node.js 18+** with npm
- **ffmpeg** installed and on PATH

### Setup

```bash
# Clone or navigate to the project
cd ZAOVideoEditor

# Create Python virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Run

```bash
# Option 1: Use the start script
./start.sh

# Option 2: Run manually in two terminals

# Terminal 1 — Backend
source venv/bin/activate
uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend
cd frontend
npm run dev
```

Open **http://localhost:5173**

Backend API docs at **http://localhost:8000/docs**

> First transcription will download the Whisper model. The "fast" model is ~150MB; "standard" and "high" quality use `large-v3` (~3GB). Subsequent runs use the cached model.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19, Vite 7, Tailwind CSS 4 |
| Backend | FastAPI, Uvicorn, Pydantic |
| Transcription | Faster Whisper (local, CPU, int8) |
| Video/Audio | ffmpeg, ffprobe |
| Caption Rendering | Pillow (PIL) for text-to-PNG, ffmpeg overlay filter |
| Language | Python 3.13, Node.js |

Everything runs locally. No external APIs, no cloud services, no auth.

---

## Project Structure

```
ZAOVideoEditor/
├── backend/
│   ├── main.py                    # FastAPI app entry, CORS, error handling, task polling
│   ├── requirements.txt
│   ├── routers/
│   │   ├── projects.py            # Project CRUD, file uploads, stage tracking
│   │   ├── assembly.py            # Intro/outro assembly, audio extraction (background task)
│   │   ├── transcription.py       # Multi-pass transcription with quality selector (background task)
│   │   ├── transcript.py          # Dictionary correction, cleanup, editing
│   │   ├── captions.py            # Caption generation, SRT/ASS, burn-in (background task)
│   │   ├── metadata.py            # YouTube description/chapters/tags
│   │   └── export.py              # Export package assembly
│   ├── services/
│   │   ├── ffmpeg_service.py      # All ffmpeg operations + Pillow caption rendering
│   │   ├── whisper_service.py     # Multi-pass transcription engine with consensus merge
│   │   ├── task_manager.py        # Background task thread pool with progress tracking
│   │   ├── dictionary.py          # Persistent correction dictionary
│   │   ├── cleanup.py             # Transcript polishing (fillers, punctuation)
│   │   ├── caption_gen.py         # Caption splitting, timing, SRT/ASS generation
│   │   └── metadata_gen.py        # NLP-powered metadata generation (TF-IDF, entity extraction)
│   └── models/
│       └── schemas.py             # Pydantic request/response models
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Project list / workspace routing
│   │   ├── api/client.js          # API client with task polling
│   │   └── components/
│   │       ├── Workspace.jsx      # Main layout: video + tabbed panels
│   │       ├── GuidedMode.jsx     # Step-by-step linear workflow
│   │       ├── VideoPlayer.jsx    # Video preview with seek control
│   │       ├── UploadPanel.jsx    # Upload + quality selector + assemble + transcribe
│   │       ├── TranscriptEditor.jsx # Editable transcript synced to video
│   │       ├── CaptionPanel.jsx   # Theme selection, generate, burn, preview
│   │       ├── MetadataPanel.jsx  # Editable YouTube metadata with copy buttons
│   │       ├── DictionaryManager.jsx # Add/remove correction entries
│   │       ├── ExportPanel.jsx    # Package and download exports
│   │       ├── StageStatus.jsx    # Pipeline stage indicators
│   │       ├── ProgressBar.jsx    # Animated progress with substeps
│   │       └── ProjectList.jsx    # Project creation and selection
│   └── vite.config.js             # Vite + Tailwind + API proxy
├── projects/                      # User project data (gitignored)
│   └── {project_name}/
│       ├── input/                 # Uploaded videos
│       ├── processing/            # Assembled video, audio, captioned video
│       ├── transcripts/           # raw.json, corrected.json, cleaned.json, edited.json
│       ├── captions/              # captions.json, captions.srt, captions.ass
│       ├── metadata/              # description.txt, chapters.txt, tags.txt
│       └── exports/               # Final packaged output files
├── shared/
│   └── dictionary.json            # Persistent brand/name corrections
├── start.sh                       # Starts both servers
└── .gitignore
```

---

## How It Works

### Workspace Mode

The default view. Video player on the left, tabbed panels on the right:

- **Upload** — add main video, select transcription quality, optional intro/outro, run assemble + transcribe
- **Transcript** — correct, clean, edit, save, add dictionary entries
- **Captions** — pick theme, generate, preview SRT/ASS, burn into video
- **Metadata** — generate YouTube description/chapters/tags, edit, copy, save
- **Dictionary** — manage shared brand/name corrections
- **Export** — package all outputs for download

Stage status indicators in the top bar show what's complete.

### Guided Mode

Same tools, linear flow. Five steps with Previous/Next navigation:

1. Upload & Transcribe
2. Edit Transcript
3. Generate Captions
4. YouTube Metadata
5. Export

### Transcription Quality

Three quality levels, selectable per-project before processing:

| Quality | Model | Passes | Speed | Use case |
|---------|-------|--------|-------|----------|
| **Fast** | `base` (74M params) | 1 pass | Quick | Drafts, testing |
| **Standard** | `large-v3` (1.5B params) | 1 pass | Moderate | Good quality for most content |
| **High** | `large-v3` (1.5B params) | 3 passes | Slow | Best accuracy, consensus merge |

**High quality mode** runs three transcription passes with different parameters (precise, exploratory, aggressive), then merges them using word-level confidence voting. For each word position, the highest-confidence version across all passes is selected. This significantly improves accuracy for names, technical terms, and unclear audio.

Pass configurations:
- **Precise**: beam_size=5, temperature=0.0, condition_on_previous_text=True
- **Exploratory**: beam_size=8, temperature=0.2, condition_on_previous_text=False
- **Aggressive**: beam_size=5, temperature=0.0, no_speech_threshold=0.4

### Background Task System

Long-running operations (assembly, transcription, caption burn) run in background threads. The frontend polls `/api/tasks/{task_id}` for progress updates. This means:

- Navigating between tabs doesn't kill running processes
- Progress is tracked in real-time with descriptive messages
- Multiple operations can run in parallel across different projects

### Caption Rendering

Captions are burned into video using a **Pillow + ffmpeg overlay** approach (no libass dependency required):

1. Each caption is rendered as a transparent PNG using Pillow (PIL)
2. Font selection: tries system fonts (Arial, Helvetica, DejaVu Sans)
3. Rounded rectangle background with theme-specific colors
4. ffmpeg `overlay` filter with `enable='between(t,start,end)'` expressions
5. Processes in batches of 50 overlays to avoid ffmpeg filter graph limits
6. Multi-pass: each batch feeds into the next until all captions are burned

### YouTube Metadata Generation

The metadata generator uses NLP techniques to produce YouTube-ready descriptions, chapter timestamps, and tags — no external LLM required.

**Description generation:**
- Detects guest name and show name from intro patterns
- First 150 characters optimized as search snippet / hook (what YouTube shows in results)
- Constructs summary from detected entities and themes (not raw transcript quotes)
- Lists key topics extracted via named entity recognition

**Chapter generation (timestamps):**
- Topic boundary detection using three signals:
  - **Vocabulary shift**: Jaccard distance between sliding windows of content words
  - **Speech gaps**: pauses > 0.8s between segments
  - **Transition phrases**: "let's talk about", "moving on", "the idea for", etc.
- Scales chapter count by video length (3 for <5min, up to 12 for 60+ min)
- Titles constructed from most distinctive entities in each section using TF-IDF concentration scoring
- Entity-aware: detects proper nouns, brand names, and multi-word entities (e.g., "Gods and Chain", "Goldman Sachs")
- Titles are clean topic labels, not raw transcript quotes

**Tag generation:**
- Primary keyword first (project name)
- Named entities and proper nouns (brands, people, products)
- Multi-word bigram phrases with frequency filtering
- TF-IDF scored single keywords
- Up to 20 tags within YouTube's 500-character limit

**Frontend UX:**
- Character counters (description: 5,000 limit, tags: 500 limit)
- Chapter count with YouTube minimum (3) warning
- Search snippet preview (first 150 chars)
- Copy buttons per field + "Copy All" for full package
- All fields are editable before saving

### Stage Re-runs

Each stage writes intermediate files. You can re-run any stage independently:

| Want to... | Just do... |
|-----------|-----------|
| Fix a typo in the transcript | Edit in Transcript tab → Save Edits |
| Regenerate captions after editing | Captions tab → Generate Captions |
| Switch caption theme | Select new theme → Generate → Burn |
| Update metadata | Metadata tab → edit fields → Save |
| Re-export everything | Export tab → Create Export Package |

No need to re-transcribe or re-assemble.

### Correction Dictionary

Shared across all projects. Whisper often misspells brand names and people — the dictionary fixes them automatically.

Pre-loaded entries: ZAO, ZABAL, WaveWarZ, SongJam, Farcaster, Ohnahji

Add new corrections from the Transcript editor or the Dictionary tab.

### Caption Themes

| Theme | Text Color | Background |
|-------|-----------|-----------|
| Dark on Light | `#141e27` | `#e0ddaa` |
| Light on Dark | `#e0ddaa` | `#141e27` |

Captions are bottom-centered, single-line, 34-38px font, small bottom margin.

### Progress Tracking

All long operations show real-time progress:

- **Upload**: actual MB uploaded / total
- **Transcription**: per-pass progress with time elapsed (e.g., "Pass 2/3 (exploratory): 2:15/10:30")
- **Caption burn**: ffmpeg rendering progress per batch
- All panels show animated progress bars with step checklists

---

## Supported Formats

**Input**: mp4, mov, mkv, webm

**Output**: mp4 (h264/aac, high quality, original resolution and frame rate preserved)

**Exports**: captioned.mp4, captions.srt, captions.ass, transcript.json, transcript.txt, description.txt, chapters.txt, tags.txt

---

## API Endpoints

All under `/api/`. Full interactive docs at `http://localhost:8000/docs`.

| Method | Endpoint | Description |
|--------|---------|-------------|
| POST | `/api/projects` | Create project |
| GET | `/api/projects` | List projects |
| GET | `/api/projects/{name}` | Get project with stage status |
| DELETE | `/api/projects/{name}` | Delete project |
| POST | `/api/projects/{name}/upload` | Upload main video |
| POST | `/api/projects/{name}/upload-intro` | Upload intro |
| POST | `/api/projects/{name}/upload-outro` | Upload outro |
| POST | `/api/assembly/assemble` | Assemble video parts (background task) |
| POST | `/api/assembly/extract-audio` | Extract audio |
| POST | `/api/transcription/transcribe` | Transcribe audio (background task, quality selector) |
| GET | `/api/transcription/{name}/raw` | Get raw transcript |
| POST | `/api/transcript/correct` | Apply dictionary corrections |
| POST | `/api/transcript/cleanup` | Clean and polish transcript |
| POST | `/api/transcript/save-edit` | Save user edits |
| GET | `/api/transcript/{name}/current` | Get best available transcript |
| GET/POST/DELETE | `/api/transcript/dictionary/*` | Manage dictionary |
| POST | `/api/captions/generate` | Generate captions + SRT + ASS |
| POST | `/api/captions/burn` | Burn captions into video (background task) |
| POST | `/api/metadata/generate` | Generate YouTube metadata |
| GET | `/api/metadata/{name}` | Get generated metadata |
| POST | `/api/metadata/{name}/save` | Save edited metadata |
| POST | `/api/export/package` | Create export package |
| GET | `/api/export/{name}/files` | List export files |
| GET | `/api/export/{name}/download/{file}` | Download export file |
| GET | `/api/tasks/{task_id}` | Poll background task status |
| GET | `/api/tasks/project/{name}` | Get all tasks for a project |

---

## What's Not Included (By Design)

This is an MVP scoped for one creator making YouTube-ready conversation videos:

- No speaker diarization
- No timeline editor
- No clip extraction / shorts
- No multilingual workflows
- No auto-upload to YouTube
- No cloud sync, accounts, or auth
- No karaoke word-by-word highlighting (structure supports adding later)
- No external LLM required (metadata uses local NLP: TF-IDF, entity extraction, topic segmentation)

---

## License

Private project.
