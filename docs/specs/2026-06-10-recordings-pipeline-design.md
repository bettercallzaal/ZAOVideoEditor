# ZAO Recordings Pipeline - Design (founding spec)

> Date: 2026-06-10. Status: approved, building Phase 1.
> Source spec: the "ZAO Video Editor - spec + brand reference" doc from `zabalgames`.
> This file is the architecture decision record for that build, living in the build repo.

## Goal

Replace Descript in the ZAO recordings pipeline. A raw workshop/show recording becomes:
1. a clean corrected video,
2. distribution clips,
3. a clean Markdown transcript, and
4. a live `/recordings/N` page,

with as few manual steps as possible.

## Who operates it

- **Now:** curated by Zaal, with Iman editing. Light editor allowlist.
- **Later:** opened to the ZAO community, **token-gated** first.
- The Supabase schema carries an `owner` per row and per-project isolation from day one, so
  opening it up is swapping the auth check, not a rewrite.

## Architecture - hybrid (decided)

A worker on a real server is mandatory: ffmpeg + WhisperX + multi-minute jobs cannot run on
Vercel serverless in any language. So:

```
Google Drive ──▶ Next.js app (Vercel) ──▶ Supabase (Postgres + Storage)
  (ingest)         review UI, auth,            jobs, projects, captions,
                   publish, /recordings/N      cut decisions, owner per row
                          │
                          ▼  (enqueue job)
                   Python engine (existing VPS) ── the media worker
                   transcribe · cut-plan · render · clip · caption-burn
                          │
                   Claude via Hermes subprocess (readable pass, false-starts)
```

- **Vercel** builds only the Next.js UI (what it is good at). The Python engine never touches
  Vercel - which is why the historic red deploy list was a Vercel misconfig, not our code.
- **VPS worker** = the existing Python FastAPI engine in this repo. Reuses the shipped work:
  ingest scaffold (PR #4), multi-aspect clips + caption burn (PR #5), highlight detection,
  the background task system.
- **Supabase** = shared state both sides read/write.

### Decisions locked in brainstorming

- **STT behind a `Transcriber` interface.** WhisperX/faster-whisper self-host is the default
  (zero marginal cost, ZAO ethos); Deepgram is a drop-in for later if the VPS is too slow or
  volume spikes. Keep both options open.
- **LLM via the Hermes pattern** - shell out to the `claude` CLI subprocess (Max-plan OAuth,
  zero marginal cost), with a fallback to the existing Ollama/OpenAI client when the CLI is
  absent.
- **Captions are non-destructive.** The trimmed master is caption-free forever. Captions,
  cut toggles, and clip ranges are editable rows; burn/clip export are re-runnable outputs.
  Never bake captions into the only copy. Renderer behind a `CaptionRenderer` interface (ASS
  now, Remotion later), style user-customizable.
- **One glossary.** Unify on `transcript-corrections.json` (safe vs review split). Retire the
  ad-hoc Python `dictionary.py` glossary in favour of the single JSON source of truth.
- **Publish via PR** by default - the worker/agent opens a PR into `zabalgames` with the new
  transcript md + `/recordings/N` page + recap, preserving the review gate and git history.

## Stage map (reuse vs build)

| Stage | What | Status |
|-------|------|--------|
| A Ingest (Drive/Gmail) | watch shared Drive folder, pull new video | new (Drive API) - URL/yt-dlp ingest from PR #4 stays as a 2nd source |
| B Transcribe | word-level timestamps + custom vocab | reuse engine, behind `Transcriber` interface |
| C Correct | glossary find/replace, safe auto + review flag | unify on `transcript-corrections.json` |
| D Cut plan | um/uh-only default, gaps, optional LLM false-starts | reuse filler/gap detect; Hermes false-start pass review-only |
| E Review UI | synced transcript, batch accept/reject, caption edit | new - Next.js + Supabase, the centerpiece |
| F Render | non-destructive cut + caption burn + clips | reuse PR #5, driven by Supabase rows |
| G Readable pass | brand-voice clean Markdown | new - Hermes with brand rules |
| H Publish | transcript md + `/recordings/N` + recap + index + YouTube | zabalgames scripts, via PR |

## Build phases

1. **Headless transcript pipeline** - input -> transcribe -> correct -> Hermes readable ->
   two transcripts (timestamped cut + clean readable Markdown). Retires Descript for the
   transcript path. **(Phase 1 - building now.)**
2. **Cut + render** - um/uh + gap cuts -> non-destructive ffmpeg render from an edit sheet.
3. **Review UI** - the Next.js/Supabase app: cut toggles, batch accept, caption editing.
4. **Captions + clips + auto-publish** - styled captions, shorts, `/recordings/N` + recap.

## Brand rules the tool must enforce (from the source spec)

No emojis. No em dashes. No decorative Unicode (use text labels). No crypto/web3 jargon in
public copy. "100+" for member count. Exact brand casing (WaveWarZ, COC Concertz, The ZAO,
BetterCallZaal, SongJam, ZABAL, ZAOstock, Stilo World, etc.). Conservative filler removal
(um/uh only by default; cadence words kept). Two separate transcript outputs (timestamped
cut transcript vs clean readable transcript). Always flag proper names + ambiguous terms for
review, never auto-change.

## Non-goals (for now)

Public multi-tenant auth, real-time collaborative editing, GPU autoscaling, and a hosted
render farm. All deferred until the team tool is proven and we open it token-gated.
