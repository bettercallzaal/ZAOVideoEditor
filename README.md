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
8. **YouTube package** - a ready-to-paste title, description with 0:00 chapters, and tags.
9. **Subtitles** - download the transcript as SRT or WebVTT for any platform.
10. **Speakers** - rename detected speakers and see a per-speaker talk-time breakdown.
11. **Publish** - post to Farcaster / X / upload to YouTube directly (optional, see below).
12. **Bundle** - pack the clips, copy, recap, posts, and transcripts into one zip to hand
    off or bulk-post.
13. **Library** - every past recording is listed; reopen and keep working. Search across
    all recordings for a phrase and jump to the moment.

Everything has Copy and Download buttons, so even with nothing configured you can
process a recording and grab the outputs to post manually.

---

## Livestream day (during the live)

The Studio also helps while a stream is actually running, then bridges straight
into the clip pipeline once the VOD exists. All of it lives in the **Live session**
panel on the intake screen.

- **Go-live detection** - paste a stream URL and **Check if live** tells you whether
  it is live right now (via the yt-dlp probe), prefilling the session title from the
  stream so you can start in one click.
- **Day-of casts** - the 15-minute-warning and "live now" posts for a session, in
  the team's exact templates, filled from the schedule. Pick a session (or type the
  details), get both casts brand-clean and ready to copy.
- **Live clip-marking** - start a live session, then tap **Mark moment** (with an
  optional note) every time something is clippable. Each mark stores its
  seconds-from-start. After the stream, paste the VOD URL: it downloads and processes
  into the same project, and **Make clips from marks** turns every mark into a clip -
  a window of `[mark - pre]` to `[mark + post]` (defaults 20s / 40s), clamped to the
  video, with an offset knob for drift between when you hit start and the VOD's t=0.
  Renders 9:16 + 1:1 through the same captioned clip pipeline.
- **Live transcript** - **Start live transcript** captures the stream's audio in 15s
  clips (share the tab playing the stream, or fall back to the mic) and transcribes
  each on the fast path as you go, so the words scroll by while you mark. Same Groq /
  local routing and brand glossary as the main pipeline.
- **Suggested moments** - as the live transcript fills in, the Studio surfaces
  clippable cues (excitement phrases, ZAO brand mentions, audience questions) you can
  accept as marks with one tap. It only suggests; you decide.
- **Now playing** - post the track on the DJ deck to social, live: type it, pull it
  from the now-playing file/URL OBS or Serato already writes, or identify it from the
  live audio via AudD (`AUDD_API_TOKEN`). Either way you get a brand-clean post.
- **End-of-stream recap** - when the session wraps, generate a recap + chapters +
  clip ideas straight from the live transcript, before the VOD even downloads.

The flow: check if live -> start the session and the live transcript -> mark moments
live (or accept suggestions), post now-playing tracks -> end-of-stream recap -> after
the stream, attach the VOD -> make clips from your marks -> the clips, copy, and recap
flow through the normal editor.

You can also **search across every recording** from the library: type a phrase and
jump straight to the moment in whichever past recording said it (then clip it).

---

## ZABAL Gamez export

For the ZABAL Gamez workshop series, the Studio outputs directly into the team's repo
formats instead of a hand-built page:

- a `recaps.json` block (date, presenter, track, summary, topics, takeaways, chapters,
  youtube, transcript) and a transcript `.md` with the right frontmatter,
- written straight into a local checkout of the
  [ZAODEVZ/zabalgames](https://github.com/zaoDEVZ/zabalgames) repo when
  `STUDIO_ZABALGAMES_PATH` is set (no auto-push - you review the `git diff`),
- using the team's own `data/transcript-corrections.json` glossary when
  `STUDIO_GLOSSARY_PATH` points at it.

YouTube VODs from Restream are the canonical source; the **Use YouTube captions** toggle
pulls the VOD's own captions (a 26-minute talk in ~3s) and skips Whisper entirely.

The casts panel also generates the team's distribution casts from their real
`distribution-casts-2026-06-11.md`: the day-of two-beat, a **this-week cast** built
from dated confirmed sessions in `workshop-leads.json`, and the static announce casts.

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
| `STUDIO_ZABALGAMES_PATH` | Write the export into a local zabalgames checkout |
| `STUDIO_GLOSSARY_PATH` | Use a specific glossary file (e.g. the zabalgames one) |
| `STUDIO_PASSWORD` | Gate the whole app behind HTTP Basic auth (for a shared instance) |
| `AUDD_API_TOKEN` | Identify the now-playing track from live audio (audd.io) |

Copy `.env.example` to `.env` and fill in only what you want. Publish buttons appear
in the UI only for the platforms you have configured. Other hardening knobs:
`STUDIO_MAX_CONCURRENT` (transcription slots), `STUDIO_MAX_UPLOAD_GB` (upload cap),
`STUDIO_CORS_ORIGINS`.

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
`/{p}/speakers`, `/{p}/speaker-stats`, `/glossary`, `/{p}/publish/{farcaster,x,youtube}`,
`/{p}/youtube`, `/{p}/subtitles/{srt,vtt}`, `/{p}/bundle`, `/projects`, `/search`,
`/{p}/zabal-export`, `/sessions`, `/casts/{day-of,this-week,static}`.

Livestream-day endpoints: `/golive`, `/live/start`, `/{p}/live/mark`, `/{p}/marks`,
`/{p}/live/vod`, `/{p}/clips-from-marks`, `/{p}/live/audio-chunk`,
`/{p}/live/transcript`, `/{p}/live/suggested-marks`, `/{p}/live/recap`,
`/now-playing/{post,source}`, `/{p}/now-playing/identify`. Interactive docs at
`http://localhost:8000/docs`.

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

## Hosting a shared instance

For a team instance (not just local), the app ships a container and a guard:

```bash
docker compose up -d            # builds the ffmpeg + Python image, mounts projects/ and models/
```

Set `STUDIO_PASSWORD` to put the whole app behind HTTP Basic auth, and the hardening
knobs above to cap uploads and transcription concurrency. Full deployment notes
(VPS, reverse proxy, volumes, health check) are in [DEPLOY.md](./DEPLOY.md). CI builds
and smoke-tests the image on every PR.

---

## Development

```bash
pip install -r backend/requirements-dev.txt   # light test deps
python -m pytest                                # 234 tests
cd web && npm install && npm run build          # the optional Next.js UI
```

CI runs the backend tests + the web build on every PR.

---

## Project status

Built and shipped:

- Recordings pipeline (transcribe -> brand glossary -> non-destructive edit/trim ->
  captioned vertical clips -> recap/chapters/quotes -> social drafts -> publish),
  one-command local app (`./run.sh`), and a headless CLI.
- Ingest from a URL (YouTube / Twitch / Restream / HLS / mp4) plus a YouTube-captions
  fast path that skips Whisper.
- ZABAL Gamez export into the team's `recaps.json` + transcript `.md` formats, using
  their glossary, written into a local checkout for review.
- Opt-in Bonfire memory ingest (a recap episode is posted only when you press the
  button; secret-scanned and PII-redacted first).
- Livestream day: go-live detection, day-of / this-week / announce casts, live
  clip-marking, live transcription, auto-mark suggestions, now-playing-to-social, and
  an end-of-stream recap from the live transcript.
- Cross-recording library search (find a phrase across every recording, jump to it).
- Distribution outputs: subtitle export (SRT / WebVTT), a YouTube package (title +
  description with 0:00 chapters + tags), speaker talk-time analytics, and a one-zip
  distribution bundle (clips, copy, recap, posts, transcripts).
- Production packaging: Docker, optional access password, hardening knobs, CI that
  builds and smoke-tests the image.
- 234 backend tests.

Needs an operator (not buildable here):

- Hosting the shared instance (a box with ffmpeg + SSH).
- A `GITHUB_TOKEN` if the team wants a true auto-PR into zabalgames (today it writes
  into a local checkout for you to review and push).
- Scheduled / channel-level go-live polling and auto-prep, which belongs in the
  zabalgames `/live` infra (the Studio does on-demand go-live checks today).

Resolved follow-ups: the Pillow caption-fallback broken-pipe bug (an early ffmpeg
exit no longer crashes the burn), and the dependency pinning / CI dev-deps gap
(`requests` was missing) - runtime and dev deps are now pinned and a clean
`requirements-dev.txt` install runs the full suite. No in-repo linter is configured.

---

## License

MIT - see [LICENSE](./LICENSE).
