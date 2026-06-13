# Deploying the ZAO Recordings Studio

Three ways to run it, smallest to biggest.

## 1. Local (just you)

```bash
./run.sh
```
Opens at `http://localhost:8000`. No password, nothing exposed. See the README.

## 2. Shared instance (you + a few people) - Docker

The whole app + ffmpeg + yt-dlp in one container.

```bash
cp .env.example .env        # then edit .env (at minimum set STUDIO_PASSWORD)
docker compose up -d        # build + run
```

It serves on `http://<host>:8000`. Recordings persist in `./projects`; Whisper
models persist in a named volume so they download only once.

Set these in `.env` before sharing the URL:

| Variable | Why |
|----------|-----|
| `STUDIO_PASSWORD` | Required for any non-local instance - gates the whole app (HTTP Basic; any username, this password). Without it the instance is fully open. |
| `GROQ_API_KEY` | Fast transcription for long recordings (free tier) |
| `STUDIO_MAX_CONCURRENT` | How many transcriptions run at once (default 1; raise on a big/GPU box) |
| `STUDIO_MAX_UPLOAD_GB` | Upload size cap (default 10) |
| `STUDIO_CORS_ORIGINS` | Set if you call the API from another origin (`*` or a comma list) |

**Always put a public instance behind HTTPS** (a reverse proxy - Caddy or nginx -
terminating TLS), because the access password uses HTTP Basic. Example Caddy line:

```
studio.yourdomain.com {
    reverse_proxy localhost:8000
}
```

## 3. The team UI (real multi-user) - Vercel + worker

For multiple editors with their own accounts, deploy the Next.js + Supabase UI in
`web/` to Vercel (set the project Root Directory to `web/`) and point it at this
container as the worker via `NEXT_PUBLIC_WORKER_URL`. See `web/README.md`.

## Updating

```bash
git pull && docker compose up -d --build
```

## Notes

- CPU transcription is slow for long files; set `GROQ_API_KEY` for near-instant
  cloud transcription, or run on a GPU box and raise `STUDIO_MAX_CONCURRENT`.
- Publishing (Farcaster/X/YouTube) and Bonfire memory are opt-in and only active
  when their credentials are set - see `.env.example`.
- Health check: `GET /api/health` (used by Docker's healthcheck).

## Vercel

The Studio cannot run on Vercel (it needs a long-running server with ffmpeg +
Whisper). The root `vercel.json` makes Vercel ship a small static landing page so
deploys stay green instead of failing as a mis-detected Python build. To instead
deploy the optional Next.js team review UI, set the Vercel project Root Directory
to `web/` and delete the root `vercel.json`.
