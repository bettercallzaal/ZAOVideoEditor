# ZAO Video Editor

A local-first video processing app built for conversation-based content — podcasts, livestreams, Twitter/X Spaces, Zoom calls, and community recordings.

Upload a video, transcribe it locally, clean up the transcript, generate branded captions, burn them in, and export everything YouTube-ready. No cloud, no API keys, no accounts.

---

## What It Does

The full workflow in one app:

1. **Upload** a main video (mp4, mov, mkv, webm)
2. **Optionally add** intro and outro clips — auto-converted to match the main video
3. **Assemble** into a single source video via ffmpeg
4. **Remove dead air** — automatically cut silence with auto-editor (optional)
5. **Transcribe** locally with selectable engine (faster-whisper, WhisperX) and quality (fast/standard/high)
6. **Refine timestamps** — post-process word timing with stable-ts (optional)
7. **Correct** brand/name misspellings using a persistent shared dictionary
8. **Clean and polish** the transcript — remove fillers, fix stutters, improve punctuation
9. **Detect speakers** — identify who's talking using pyannote diarization (with energy-based fallback)
10. **Find and remove filler words** — um, uh, "you know", "kind of", contextual fillers like "like" and "basically"
11. **Edit** the transcript manually in a video-synced editor (click to seek, filter by speaker)
12. **Generate captions** — 6 professional styles from classic subtitles to Hormozi-style word highlighting
13. **Burn captions** into the video with selectable renderer (Pillow or MoviePy)
14. **Detect highlights** — find the most engaging moments for clips/shorts
15. **Export clips** — landscape or vertical 9:16 for YouTube Shorts, TikTok, Reels
16. **Generate YouTube metadata** — description, chapters, tags (NLP-powered, no external LLM)
17. **SEO checklist** — automated YouTube readiness validation before export
18. **Export** everything to a project folder: captioned video, SRT, ASS, transcript, metadata

Any stage can be re-run independently. Edit the transcript and regenerate just the captions. Switch styles and re-burn. Regenerate metadata without re-transcribing.

---

## Quick Start

### Prerequisites

- **Python 3.10+** with pip
- **Node.js 18+** with npm
- **ffmpeg** installed and on PATH

### Setup

```bash
# Clone the repo
git clone https://github.com/bettercallzaal/ZAO-Video-Editor.git
cd ZAO-Video-Editor

# Create Python virtual environment and install dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### Optional Tools

Install any of these for enhanced features. The app detects what's available and adapts the UI automatically:

```bash
pip install whisperx        # Better word-level timestamps + built-in diarization
pip install stable-ts       # Timestamp refinement post-processing
pip install auto-editor     # Automatic silence/dead-air removal
pip install moviepy         # Single-pass caption burn (no batch ffmpeg)
```

The system falls back gracefully — everything works with just the core dependencies.

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
| Transcription | Faster Whisper (core) + WhisperX (optional) + stable-ts (optional) |
| Speaker Diarization | pyannote.audio (with energy-based fallback) |
| Video/Audio | ffmpeg, ffprobe, auto-editor (optional) |
| Caption Rendering | Pillow (core) + MoviePy (optional) |
| Language | Python 3.13, Node.js |

Everything runs locally. No external APIs, no cloud services, no auth.

---

## Optional Tool Integrations

The app supports a multi-tool pipeline where each optional tool enhances a specific stage. All tools are detected at runtime via `/api/tools` — the frontend hides controls for tools that aren't installed.

| Tool | What It Does | Fallback Without It |
|------|-------------|-------------------|
| **WhisperX** | Batched transcription + wav2vec2 forced alignment for precise word timestamps + integrated pyannote diarization | faster-whisper (still accurate, just less precise word timing) |
| **stable-ts** | Post-processes any transcription to fix timestamp drift and jitter | Original timestamps used as-is |
| **auto-editor** | Analyzes audio levels and automatically cuts silent/dead-air sections from video | No silence removal (manual editing only) |
| **MoviePy** | Burns captions in a single CompositeVideoClip pass instead of batched ffmpeg filter graphs | Pillow + batched ffmpeg overlay (works, just slower for many captions) |

### How redundancy works

The tools aren't just alternatives — they chain together for better output:

```
Upload → Assemble → auto-editor (cut silence) → Extract Audio
       → WhisperX OR faster-whisper (transcribe)
       → stable-ts (refine timestamps)
       → Dictionary correct → Cleanup → Edit
       → Generate captions (6 styles)
       → MoviePy OR Pillow+ffmpeg (burn captions)
       → Metadata → SEO check → Export
```

- **Transcription**: WhisperX provides better word-level alignment than faster-whisper alone. Adding stable-ts on top refines timestamps further. Or use faster-whisper's 3-pass high-quality mode for consensus accuracy.
- **Silence removal**: auto-editor removes dead air before transcription, producing a tighter video and cleaner transcript.
- **Caption burn**: MoviePy composes all caption overlays in a single pass (no batching needed), while Pillow+ffmpeg works without MoviePy installed.

### Engine selection in the UI

The Upload panel shows:
- **Engine dropdown**: Auto / faster-whisper / WhisperX — Auto picks WhisperX if installed
- **Refine timestamps checkbox**: Uses stable-ts when available
- **Remove Dead Air toggle**: Shows only when auto-editor is installed, with threshold/padding controls and a "Preview Cuts" button

The Captions panel shows:
- **Renderer dropdown**: Auto / Pillow / MoviePy — Auto picks MoviePy if installed

---

## Project Structure

```
ZAOVideoEditor/
├── backend/
│   ├── main.py                    # FastAPI app, CORS, error handling, /api/tools endpoint
│   ├── requirements.txt
│   ├── routers/
│   │   ├── projects.py            # Project CRUD, file uploads, stage tracking
│   │   ├── assembly.py            # Intro/outro assembly, audio extraction (background task)
│   │   ├── transcription.py       # Multi-engine transcription with quality + engine selector
│   │   ├── transcript.py          # Dictionary correction, cleanup, editing
│   │   ├── captions.py            # Caption generation (6 styles), multi-renderer burn
│   │   ├── metadata.py            # YouTube description/chapters/tags
│   │   ├── speakers.py            # Speaker diarization endpoints
│   │   ├── fillers.py             # Filler word detection/removal endpoints
│   │   ├── clips.py               # Highlight detection and clip export endpoints
│   │   ├── silence.py             # Silence removal endpoints (auto-editor)
│   │   └── export.py              # Export package assembly
│   ├── services/
│   │   ├── ffmpeg_service.py      # ffmpeg operations + Pillow caption rendering (6 styles)
│   │   ├── whisper_service.py     # Multi-pass faster-whisper transcription engine
│   │   ├── whisperx_service.py    # WhisperX engine (word alignment + optional diarization)
│   │   ├── stable_ts_service.py   # stable-ts timestamp refinement
│   │   ├── auto_editor_service.py # auto-editor silence detection and removal
│   │   ├── moviepy_service.py     # MoviePy caption burn + transitions + clip export
│   │   ├── tool_availability.py   # Runtime detection of optional tools
│   │   ├── task_manager.py        # Background task thread pool with progress tracking
│   │   ├── dictionary.py          # Persistent correction dictionary
│   │   ├── cleanup.py             # Transcript polishing (fillers, punctuation)
│   │   ├── caption_gen.py         # Caption splitting, timing, 6 styles, SRT/ASS generation
│   │   ├── metadata_gen.py        # NLP-powered metadata (TF-IDF, entity extraction)
│   │   ├── diarization.py         # Speaker diarization (pyannote + energy fallback)
│   │   ├── filler_detection.py    # Word-level filler detection and removal
│   │   └── highlights.py          # Highlight/clip detection with engagement scoring
│   └── models/
│       └── schemas.py             # Pydantic models (engine, style, renderer fields)
├── frontend/
│   ├── src/
│   │   ├── App.jsx                # Project list / workspace routing
│   │   ├── api/client.js          # API client (tools, silence, engine, renderer)
│   │   └── components/
│   │       ├── Workspace.jsx      # Main layout: video + tabbed panels
│   │       ├── GuidedMode.jsx     # Step-by-step linear workflow
│   │       ├── VideoPlayer.jsx    # Video preview with seek control
│   │       ├── UploadPanel.jsx    # Upload + engine/quality/silence + transcribe
│   │       ├── TranscriptEditor.jsx # Editable transcript with speakers + fillers
│   │       ├── CaptionPanel.jsx   # 6 style previews + renderer selector + burn
│   │       ├── MetadataPanel.jsx  # Editable YouTube metadata with copy buttons
│   │       ├── DictionaryManager.jsx # Add/remove correction entries
│   │       ├── ClipsPanel.jsx     # Highlight detection and clip export
│   │       ├── SeoChecklist.jsx   # YouTube SEO readiness checklist
│   │       ├── ExportPanel.jsx    # SEO check + package and download exports
│   │       ├── StageStatus.jsx    # Pipeline stage indicators
│   │       ├── ProgressBar.jsx    # Animated progress with substeps
│   │       └── ProjectList.jsx    # Project creation and selection
│   └── vite.config.js             # Vite + Tailwind + API proxy
├── projects/                      # User project data (gitignored)
│   └── {project_name}/
│       ├── input/                 # Uploaded videos
│       ├── processing/            # assembled.mp4, trimmed.mp4, audio.wav, captioned.mp4
│       ├── transcripts/           # raw.json, corrected.json, cleaned.json, edited.json
│       ├── captions/              # captions.json, captions.srt, captions.ass, style.txt
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

- **Upload** — add main video, select engine + quality, optional intro/outro, optional silence removal, run assemble + transcribe
- **YouTube** — paste a YouTube URL, fetch video info, grab transcript (3-tier: instant captions → subtitle extraction → Whisper fallback)
- **Transcript** — correct, clean, edit, save, add dictionary entries, detect speakers, find/remove fillers
- **Captions** — pick from 6 styles, select renderer, generate, preview SRT/ASS, burn into video
- **Clips** — detect highlight moments, export clips (landscape or vertical 9:16 for Shorts/Reels)
- **Metadata** — generate YouTube description/chapters/tags, edit, copy, save
- **Dictionary** — manage shared brand/name corrections
- **Export** — SEO readiness checklist + package all outputs for download

Stage status indicators in the top bar show what's complete.

### Guided Mode

Same tools, linear flow. Five steps with Previous/Next navigation:

1. Upload & Transcribe
2. Edit Transcript
3. Generate Captions
4. YouTube Metadata
5. Export

### Transcription Engines

Two transcription engines with automatic selection:

| Engine | Word Timestamps | Diarization | Speed | Install |
|--------|----------------|-------------|-------|---------|
| **faster-whisper** (core) | Segment-level + word estimates | Separate (pyannote) | Fast | Included |
| **WhisperX** (optional) | wav2vec2 forced alignment (precise) | Built-in (pyannote) | Fast | `pip install whisperx` |

The UI defaults to "Auto" which picks WhisperX when available. Both engines support the same three quality levels:

| Quality | Model | Passes | Speed | Use case |
|---------|-------|--------|-------|----------|
| **Fast** | `base` (74M params) | 1 pass | Quick | Drafts, testing |
| **Standard** | `large-v3` (1.5B params) | 1 pass | Moderate | Good quality for most content |
| **High** | `large-v3` (1.5B params) | 3 passes | Slow | Best accuracy, consensus merge |

**High quality mode** (faster-whisper only) runs three transcription passes with different parameters (precise, exploratory, aggressive), then merges them using word-level confidence voting. For each word position, the highest-confidence version across all passes is selected.

### Timestamp Refinement (stable-ts)

When stable-ts is installed, a "Refine timestamps" checkbox appears in the Upload panel. After transcription completes, stable-ts re-aligns the transcript text against the audio using forced alignment, fixing timestamp drift and jitter. This runs automatically as a post-processing step and improves caption sync accuracy.

Install: `pip install stable-ts`

### Silence Removal (auto-editor)

When auto-editor is installed, a "Remove Dead Air" toggle appears in the Upload panel. It analyzes audio levels and automatically cuts silent sections from the video before transcription.

Controls:
- **Padding**: seconds of silence to keep around speech (default 0.1s)
- **Threshold**: audio level below which counts as silence (default 4%)
- **Preview Cuts**: shows how many sections would be cut and total time saved before applying

The trimmed video is saved as `processing/trimmed.mp4` and used for all downstream stages.

Install: `pip install auto-editor`

### Caption Styles

Six professional caption styles, selectable in the Captions panel with visual preview cards:

| Style | Font Size | Text | Background | Features |
|-------|-----------|------|------------|----------|
| **Classic** | 5% of height (~54px at 1080p) | White | None | 2px black outline |
| **Box** | 4.8% (~52px) | White | Semi-transparent black | Rounded box, 8px radius |
| **Bold Pop** | 6.5% (~70px) | White uppercase | None | 3px thick outline, large text |
| **Highlight** | 6.5% (~70px) | Gray → White per word | None | Word-by-word highlight (Hormozi/karaoke), 3px outline |
| **Brand Light** | 4% (~43px) | Dark `#141e27` | Beige `#e0ddaa` box | Your brand colors |
| **Brand Dark** | 4% (~43px) | Beige `#e0ddaa` | Dark `#141e27` box | Your brand colors |

**How caption rendering works:**

1. Each caption is rendered as a transparent PNG using Pillow:
   - Bold font discovery: Montserrat > Arial Bold > Helvetica Bold > SF Pro
   - Text outline via offset rendering technique (draw text at all surrounding positions)
   - Word-by-word highlight: renders N PNGs per caption, one per word, with active word in highlight color
2. PNGs are overlaid onto the video using ffmpeg `overlay` filter with time-based `enable` expressions
3. Batched in groups of 50 to avoid ffmpeg filter graph limits

**Alternative renderer (MoviePy):** When MoviePy is installed, a renderer selector appears. MoviePy composes all caption ImageClips onto the video in a single `CompositeVideoClip` pass, eliminating the batch approach.

**ASS subtitle output:** The generated `.ass` file includes proper styling for each style. For the Highlight style, ASS karaoke tags (`\kf`) are embedded so external players (VLC, YouTube upload) also show word-by-word highlighting.

Install MoviePy for single-pass rendering: `pip install moviepy`

### Background Task System

Long-running operations (assembly, transcription, silence removal, caption burn, clip export) run in background threads. The frontend polls `/api/tasks/{task_id}` for progress updates. This means:

- Navigating between tabs doesn't kill running processes
- Progress is tracked in real-time with descriptive messages
- Multiple operations can run in parallel across different projects

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

### Speaker Diarization

Identify who's speaking in multi-person recordings:

- **Primary**: pyannote/speaker-diarization-3.1 (requires one-time HuggingFace token acceptance)
- **Fallback**: Energy-based detection using ffmpeg silencedetect — alternates speaker assignment at silence boundaries (no dependencies needed)
- Labels each transcript segment as SPEAKER_0, SPEAKER_1, etc.
- **Rename speakers** from the Transcript tab (e.g., SPEAKER_0 → "Host", SPEAKER_1 → "Guest")
- **Filter by speaker** to view only one person's segments
- Color-coded speaker labels (8-color palette)

### Filler Word Detection & Removal

Three tiers of filler detection with configurable removal:

| Type | Examples | Detection |
|------|----------|-----------|
| **Filler words** | um, uh, er, ah, hmm | Direct match |
| **Filler phrases** | "you know", "I mean", "kind of", "sort of" | Multi-word match |
| **Contextual fillers** | like, basically, right, literally | Context-aware (avoids false positives like "I like this") |

- Scan transcript to see filler count and frequency per word
- Remove all, or selectively by type (e.g., "um/uh only" or "fillers + phrases")
- Word-level precision — removes the filler and rebuilds segment text

### Highlight Detection & Clip Export

Find the most engaging moments in a conversation and export them as clips:

**Detection scoring factors:**
- Engagement signals (words like "incredible", "realized", "never", "always")
- Question density (audience curiosity moments)
- Proper noun / entity density (topic-rich sections)
- Quote patterns (quotable statements)
- Vocabulary diversity (information-dense passages)
- Speaker change frequency (dynamic exchanges)

**Export options:**
- Standard landscape clip
- Vertical 9:16 crop for YouTube Shorts, TikTok, Instagram Reels
- Configurable: number of clips, min/max duration
- Non-overlapping — top highlights don't duplicate content

### YouTube SEO Checklist

Automated pre-export validation, shown in the Export tab:

- Transcript available
- Captions generated
- Description length (50+ chars, ideal 200-5000)
- First 150 characters hook quality (search snippet)
- Chapters start at 00:00 (YouTube requirement)
- Minimum 3 chapters (YouTube requirement)
- Tag count (5-20 recommended) and character limit (500 max)
- Burned captions (optional, recommended for social)
- Custom thumbnail reminder

Calculates a percentage score with color-coded progress bar (red/yellow/green).

### YouTube Transcript Grabber

Grab transcripts directly from YouTube videos instead of uploading and transcribing locally. Uses a **three-tier approach**, fastest first:

| Tier | Method | Speed | When It's Used |
|------|--------|-------|---------------|
| 1 | **youtube-transcript-api** | ~0.5 seconds | Fetches YouTube's existing auto-generated captions directly. Tries `en`, `en-US`, `en-GB`, then any language. |
| 2 | **yt-dlp subtitle extraction** | ~3-5 seconds | Downloads just the subtitle file (no video/audio). Parses json3, SRT, or VTT formats. |
| 3 | **faster-whisper** (local) | Minutes to hours | Downloads audio and transcribes locally. Only used when the video has zero captions. |

For most public YouTube videos, Tier 1 returns the full transcript in under a second. Tier 3 (Whisper) is the last resort.

#### Why a video might have no auto-captions

YouTube auto-generates captions for most videos, but several things can block it:

| Blocker | Why | Fix |
|---------|-----|-----|
| **Category = Music** | YouTube assumes music content has no useful speech, skips captioning entirely | Change to "People & Blogs" or "Entertainment" |
| **Visibility = Private** | Private videos are lowest priority in the caption processing queue, may never get processed | Change to Unlisted (only link-holders can see it) — captions persist if you switch back to Private |
| **Livestream VOD** | Stream recordings are lower priority than standard uploads | Combine with the fixes above and wait 24-48h |
| **Long duration (2h+)** | Compounds processing delays | Not much you can do — just wait longer |
| **Low/zero views** | YouTube deprioritizes low-engagement content | Making the video Unlisted/Public helps |

These blockers **stack** — a private, music-category, 2h livestream VOD hits all four. Fix the category and visibility first.

#### How to get YouTube to generate captions for your videos

**Per-video (YouTube Studio > Content > select video):**
1. **Advanced settings** → Change **Category** from "Music" to "People & Blogs"
2. **Basic info** → Change **Visibility** from "Private" to "Unlisted" or "Public"
3. Save and wait 24-48 hours for YouTube to process

**Channel-wide (YouTube Studio > Settings):**
1. **Upload defaults** → **Advanced settings** → Set default **Video language** to English
2. Set default **Category** to "People & Blogs" (not Music)
3. Automatic captions are enabled by default at the channel level

**Nudge processing:** After changing settings, edit the video description (add a word, save) to bump it in YouTube's processing queue.

**Upload your own captions:** If auto-captions never appear, you can upload an SRT file:
- YouTube Studio → select video → **Subtitles** → **ADD** → **Upload file** → select the `.srt` from your ZAO export
- Or use **Auto-sync**: paste plain transcript text and YouTube aligns the timing automatically

#### Standalone Text Splitter + YouTube Grabber

The app also includes a standalone tools page (deployed to Vercel) with two modes:
- **Paste Text** — paste any text and download it split into 49k character .txt files
- **YouTube Transcript** — grab a YouTube transcript and download it split into 49k character .txt files

The Vercel deployment uses a Python serverless function (`api/youtube.py`) for transcript fetching. **Note:** YouTube blocks most cloud provider IPs (Vercel, AWS, etc.), so the YouTube feature works best locally. Run `./start.sh` to use it from your local machine.

#### Cloud IP blocking

YouTube blocks transcript requests from cloud provider IPs (Vercel, AWS, GCP, Azure). This affects Tier 1 and Tier 2. Workarounds:
- **Run locally** — residential IPs are not blocked. This is the recommended approach.
- **Proxy** — `youtube-transcript-api` v1.0+ supports `WebshareProxyConfig` for rotating residential proxies (requires paid Webshare "Residential" plan)
- **Cookies** — not recommended, YouTube will eventually ban the authenticated account

---

### Stage Re-runs

Each stage writes intermediate files. You can re-run any stage independently:

| Want to... | Just do... |
|-----------|-----------|
| Fix a typo in the transcript | Edit in Transcript tab → Save Edits |
| Regenerate captions after editing | Captions tab → Generate Captions |
| Switch caption style | Select new style → Generate → Burn |
| Update metadata | Metadata tab → edit fields → Save |
| Re-export everything | Export tab → Create Export Package |

No need to re-transcribe or re-assemble.

### Correction Dictionary

Shared across all projects. Whisper often misspells brand names and people — the dictionary fixes them automatically.

Pre-loaded entries: ZAO, ZABAL, WaveWarZ, SongJam, Farcaster, Ohnahji

Add new corrections from the Transcript editor or the Dictionary tab.

### Progress Tracking

All long operations show real-time progress:

- **Upload**: actual MB uploaded / total
- **Silence removal**: sections found, time saved
- **Transcription**: per-pass progress with engine name and time elapsed
- **Timestamp refinement**: stable-ts alignment progress
- **Caption burn**: renderer and rendering progress
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
| GET | `/api/health` | Health check + version |
| GET | `/api/tools` | List installed optional tools |
| POST | `/api/projects` | Create project |
| GET | `/api/projects` | List projects |
| GET | `/api/projects/{name}` | Get project with stage status |
| DELETE | `/api/projects/{name}` | Delete project |
| POST | `/api/projects/{name}/upload` | Upload main video |
| POST | `/api/projects/{name}/upload-intro` | Upload intro |
| POST | `/api/projects/{name}/upload-outro` | Upload outro |
| POST | `/api/assembly/assemble` | Assemble video parts (background task) |
| POST | `/api/assembly/extract-audio` | Extract audio |
| POST | `/api/silence/preview` | Preview silence cuts (auto-editor) |
| POST | `/api/silence/remove` | Remove silence (background task) |
| POST | `/api/transcription/transcribe` | Transcribe (engine + quality + refine) |
| GET | `/api/transcription/{name}/raw` | Get raw transcript |
| POST | `/api/transcript/correct` | Apply dictionary corrections |
| POST | `/api/transcript/cleanup` | Clean and polish transcript |
| POST | `/api/transcript/save-edit` | Save user edits |
| GET | `/api/transcript/{name}/current` | Get best available transcript |
| GET/POST/DELETE | `/api/transcript/dictionary/*` | Manage dictionary |
| GET | `/api/captions/styles` | List available caption styles |
| POST | `/api/captions/generate` | Generate captions (style selector) |
| POST | `/api/captions/burn` | Burn captions (renderer selector, background task) |
| GET | `/api/captions/{name}` | Get generated captions |
| GET | `/api/captions/{name}/srt` | Get SRT content |
| GET | `/api/captions/{name}/ass` | Get ASS content |
| POST | `/api/metadata/generate` | Generate YouTube metadata |
| GET | `/api/metadata/{name}` | Get generated metadata |
| POST | `/api/metadata/{name}/save` | Save edited metadata |
| POST | `/api/export/package` | Create export package |
| GET | `/api/export/{name}/files` | List export files |
| GET | `/api/export/{name}/download/{file}` | Download export file |
| POST | `/api/speakers/diarize` | Run speaker diarization (background task) |
| POST | `/api/speakers/rename` | Rename speaker labels |
| GET | `/api/speakers/{name}` | Get speaker info |
| POST | `/api/fillers/detect` | Detect filler words in transcript |
| POST | `/api/fillers/remove` | Remove fillers and save transcript |
| POST | `/api/clips/detect` | Detect highlight moments |
| POST | `/api/clips/export` | Export clip as video (background task) |
| GET | `/api/clips/{name}/list` | List exported clips |
| GET | `/api/clips/{name}/download/{file}` | Download exported clip |
| POST | `/api/youtube/info` | Get YouTube video metadata |
| POST | `/api/youtube/transcribe` | Grab YouTube transcript (3-tier: captions → subtitles → whisper) |
| GET | `/api/tasks/{task_id}` | Poll background task status |
| GET | `/api/tasks/project/{name}` | Get all tasks for a project |

---

## What's Not Included (By Design)

This is scoped for one creator making YouTube-ready conversation videos:

- No timeline editor
- No multilingual workflows
- No auto-upload to YouTube
- No cloud sync, accounts, or auth
- No external LLM required (metadata uses local NLP: TF-IDF, entity extraction, topic segmentation)

---

## License

Private project.
