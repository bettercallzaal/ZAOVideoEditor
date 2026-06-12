# ZAO Recordings Studio

Turn a recording (or a link) into a clean transcript, a trimmed video, postable
vertical clips, and drafted social posts - in one local app, with no cloud setup.

Built for ZAO's recordings workflow (workshops, concerts, Spaces, livestreams) as
a self-hosted replacement for Descript + an auto-clipper. Local-first: transcription
runs on your machine, the LLM steps use the `claude` CLI (or any OpenAI/Groq/Ollama
key) at zero marginal cost, and everything degrades gracefully when an optional piece
is missing.

> Ecosystem context + roadmap: ZAOOS research docs 837 (founding spec) and 848
> (ecosystem fit). This repo is the build.

---

## Quick start (the easy way)

```bash
git clone https://github.com/bettercallzaal/ZAOVideoEditor
cd ZAOVideoEditor
./run.sh
```

First run sets up a Python venv, installs deps, and opens the **Studio** in your
browser at `http://localhost:8000`. Drop a recording (or paste a YouTube / Twitch /
Restream / `.m3u8` / `.mp4` link) and go.

Only hard requirement: **ffmpeg** on your PATH (`brew install ffmpeg` /
`sudo apt install ffmpeg`). `run.sh` checks and tells you if it is missing.

**For long recordings**, set a free `GROQ_API_KEY` (console.groq.com) before launch -
the Studio auto-routes transcription to Groq and a 17-minute file finishes in seconds
instead of minutes. Without it, the default Fast (base) model does ~17 min of audio in
~4-5 min on CPU. (large-v3, the "Best" option, is accurate but slow on CPU.)

---

## What the Studio does

A recording or link in, and out the other side:

1. **Transcribe** - fast local Whisper (or Groq), word-level timestamps.
2. **Brand-correct** - a glossary fixes ZAO terms automatically (WaveWarZ, SongJam,
   ZABAL Gamez, Stilo World, ...) and flags ambiguous ones for review. Fix a word in
   the editor and "teach the glossary" so it sticks for every future recording.
3. **Edit** - an in-page video player synced to an editable transcript. Click a word
   to jump there, double-click to fix it. **Delete a line and it is cut from the
   rendered video.** Toggle the auto-detected cuts (filler, dead air) with batch
   accept/reject. Rename detected speakers.
4. **Trim** - render a trimmed master non-destructively (the original is never touched;
   re-render any time after changing cuts).
5. **Clip** - LLM-ranked highlights become vertical 9:16 / 1:1 / 16:9 clips with burned
   captions and a drafted title + caption + hashtags each.
6. **Key moments** - one click extracts a recap, clickable chapters, and key quotes.
7. **Social** - drafted Farcaster + X posts for the episode and each clip, brand rules
   baked in (no emojis / em dashes, "100+", exact casing).
8. **Publish** - post to Farcaster / X / upload to YouTube directly (optional, see below).
9. **Library** - every past recording is listed; reopen and keep working.

Everything has Copy and Download buttons, so even with nothing configured you can
process a recording and grab the outputs to post manually.

---

## Optional integrations (all degrade gracefully)

| Set this | To enable |
|----------|-----------|
| `GROQ_API_KEY` | Near-instant cloud transcription for long files |
| `claude` CLI on PATH, or `OPENAI_API_KEY` / Ollama | Polished readable transcript, LLM-ranked clips, key moments, social drafts (otherwise a deterministic fallback) |
| `HF_TOKEN` + `pip install pyannote.audio` | Speaker detection (energy-based fallback works without it) |
| `pip install yt-dlp` | Ingest from a URL |
| `NEYNAR_API_KEY` + `FARCASTER_SIGNER_UUID` | Post to Farcaster |
| `X_API_KEY/SECRET` + `X_ACCESS_TOKEN/SECRET` (+ `pip install requests-oauthlib`) | Post to X |
| `backend/credentials.json` + `python scripts/youtube_auth.py` | Upload to YouTube |

Copy `.env.example` to `.env` and fill in only what you want. Publish buttons appear
in the UI only for the platforms you have configured.

---

## Use it from your own tools (API)

The Studio is a FastAPI app; the page just calls the same API. One call runs the whole
pipeline:

```bash
curl -F "file=@recording.mp4" -F "title=My Show" -F "clips=true" -F "socials=true" \
  http://localhost:8000/api/studio/full
# -> {"project": "...", "task_id": "..."}  then poll /api/tasks/{task_id}
```

Granular endpoints: `/api/studio/process`, `/ingest`, `/{p}/render`, `/{p}/clips`,
`/{p}/socials`, `/{p}/insights`, `/{p}/segments`, `/{p}/transcript`, `/{p}/cuts`,
`/{p}/speakers`, `/glossary`, `/{p}/publish/{farcaster,x,youtube}`, `/projects`.
Interactive docs at `http://localhost:8000/docs`.

---

## CLI (headless)

```bash
python scripts/process_recording.py recording.mp4 --title "WaveWarZ Talk" \
  --out ./out --render ./out/trimmed.mp4 \
  --publish-dir ./publish --number 12 --date 2026-06-12 --presenter "Hurricane Mike"
```

Accepts a local file or a URL. Outputs the transcripts, edit sheet, trimmed master,
and a `/recordings/N` publish bundle.

---

## Architecture

- **Python FastAPI engine** (`backend/`) - transcription, ffmpeg, clips, captions; runs
  anywhere ffmpeg + Python run. Serves the Studio page (`backend/static/studio.html`).
- **Next.js + Supabase team UI** (`web/`) - a multi-editor review surface for later,
  deployable on Vercel (set Root Directory to `web/`). Not required for local use.
- **Glossary** (`backend/data/transcript-corrections.json`) - the shared ZAO brand
  correction list; `safe` rules auto-apply, `review` rules are flagged.

The full app is a long-running server (it needs ffmpeg + Whisper), so it does not run on
Vercel serverless - run it locally with `./run.sh` or on a small VPS. Vercel only hosts
the optional `web/` review UI.

---

## Development

```bash
pip install -r backend/requirements-dev.txt   # light test deps
python -m pytest                                # 111 tests
cd web && npm install && npm run build          # the optional Next.js UI
```

CI runs the backend tests + the web build on every PR.

---

## License

MIT - see [LICENSE](./LICENSE).
