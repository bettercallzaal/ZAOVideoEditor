# ZAO Recordings - review UI (Phase 3)

The Next.js + Supabase review app: the Descript-editor replacement. Lists
recordings, shows the transcript synced to playback, lets you toggle/accept/reject
cuts in batches, and renders a trimmed master via the Python media worker. This is
the surface Vercel deploys (it never runs ffmpeg/Whisper - that is the worker).

## Architecture

```
Browser (this app, on Vercel)
  - reads/writes Supabase (projects, transcripts, cuts, captions, jobs)
  - calls the Python worker for transcribe / render / serve-video
        |
        +-- Supabase (Postgres + Auth)
        +-- Python worker (FastAPI engine on the VPS)  <- ffmpeg / WhisperX live here
```

## Setup

1. Create a Supabase project. Run the migration:
   `web/supabase/migrations/0001_init.sql` (via the SQL editor or `supabase db push`).
   It creates the schema with per-row `owner` and an `editors` allowlist (RLS).
   Add editor emails to the `editors` table to grant access.
2. Run the Python worker (the repo's `backend/`) on a box with ffmpeg + faster-whisper:
   `uvicorn backend.main:app --host 0.0.0.0 --port 8000`.
3. `cp web/.env.example web/.env.local` and fill in the Supabase URL/anon key and
   the worker URL.
4. `cd web && npm install && npm run dev` -> http://localhost:3000.

## Deploy

Set the Vercel project's **Root Directory to `web`**. Vercel builds the Next.js
app and serves it. The worker stays on the VPS; set `NEXT_PUBLIC_WORKER_URL` to
its public address. (This is what fixes the long-standing red Vercel builds - the
old project was pointed at the Python repo root, which Vercel cannot build.)

## Auth

RLS gates access to the `editors` allowlist (Zaal + Iman now). To open to a
token-gated community later, replace the policy body in the migration with a
token-holding check - the schema already isolates by `owner`, so no restructure.

## Status

Scaffold of the core review loop (transcript + cut toggles + batch accept +
render). Needs a Supabase project and the worker running to go live. Caption
editing and the publish-to-zabalgames flow land in Phase 4.
