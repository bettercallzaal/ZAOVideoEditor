# NotebookLM Integration Research

> Researched 2026-03-27. NotebookLM has no public API — this doc covers workarounds and alternatives.

## The Problem

We want to automatically send transcripts from ZAO Video Editor into Google NotebookLM for analysis, content generation, and Audio Overview (podcast-style summaries). NotebookLM is the ideal tool for this but has no API.

---

## NotebookLM API Status

**No public API exists.** Google has not released any REST API, SDK, or Apps Script service for NotebookLM. The product is web-only at `notebooklm.google.com`.

- **NotebookLM Plus** ($9.99/mo): Higher limits (500 notebooks, 100-300 sources), no API
- **NotebookLM Enterprise**: Uses Discovery Engine API for notebook CRUD only (create/delete/share), not content generation. Google Cloud Enterprise customers only.
- **Google Apps Script**: No `NotebookLmApp` service exists
- **Browser automation**: Technically possible with Playwright/Selenium but fragile, breaks often, violates ToS

**Bottom line: There is no reliable automation path for NotebookLM today.**

---

## Best Manual Workflow (What Works Now)

### Optimal transcript format for NotebookLM

Use `.txt` files with metadata headers — 100% upload success rate vs ~60% for YouTube URL import:

```
Title: Music x Trading BattleZ - Episode 47
Date: 2026-03-25
Duration: 2:17:55
Host: Zaal Panthaki
Channel: WaveWarZ
Topics: music production, live trading, community engagement

[TRANSCRIPT BEGINS]

[00:00:00] ZAAL: Welcome back to the stream...
[00:00:15] GUEST: Thanks for having me...
```

### Key tips
- **Descriptive filenames**: `ep47-trading-battlez-2026-03-25.txt` not `transcript.txt`
- **Include timestamps**: NotebookLM can reference them in citations
- **Include speaker labels**: Helps attribution in generated content
- **Split transcripts over 50,000 words** into segments to prevent truncation
- **Use plain text, not PDF** — parses more reliably

### NotebookLM source limits

| Limit | Free | Plus ($9.99/mo) | Ultra ($249.99/mo) |
|-------|------|-----------------|---------------------|
| Notebooks | 100 | 500 | -- |
| Sources per notebook | 50 | 100-300 | 600 |
| Words per source | 500,000 | 500,000 | 500,000 |
| File size per upload | 200 MB | 200 MB | 200 MB |

### Custom instructions (Notebook Guide)

NotebookLM supports up to 10,000 characters of custom directives per notebook:
- Access: Open notebook > Notebook Guide > Customize
- Preset styles: "Analyst" (business insights), "Guide" (help center)
- Custom: Write your own role, tone, and output specifications

Effective template for our use case:
```
You are a content analyst for the WaveWarZ YouTube channel. Focus on:
- Extractable quotes and key moments with timestamps
- Topics suitable for social media posts
- Content gaps and follow-up episode ideas
- Trading insights and music production tips mentioned
Always cite timestamps when referencing specific moments.
```

### Audio Overview formats

| Format | Duration | Use Case |
|--------|----------|----------|
| Deep Dive | 6-15 min | Thorough exploration |
| Brief | 1-3 min | Quick summary |
| Critique | Variable | Constructive review |
| Debate | Variable | Two hosts argue perspectives |

Customizable before generation: tone (professional/educational/conversational), length, focus areas, expertise level, language (80+).

---

## Workaround 1: Google Drive Auto-Upload

Since NotebookLM can import from Google Drive, we can automate the upload step:

### Setup (one-time)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create project, enable Google Drive API
3. Create OAuth Desktop credentials, download `credentials.json`
4. First run opens browser for consent; stores `token.json` for future use

### Dependencies
```bash
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
```

### How it works
- Uploads transcript files to `ZAO Transcripts/{project_name}/` in your Drive
- Uses OAuth (your account), so files appear in your own Drive
- NotebookLM can then import them as sources
- One manual step remains: adding the Drive file as a NotebookLM source

### Integration plan
- Add `POST /api/projects/{name}/upload-to-drive` endpoint
- Button in Export tab: "Upload to Google Drive"
- Auto-creates folder structure, uploads all transcript/metadata files

---

## Workaround 2: Build Our Own NotebookLM (Gemini API)

The Gemini API can replicate all NotebookLM features programmatically.

### What Gemini can do
- **Document Q&A**: Upload transcript, ask questions grounded in it (1M+ token context)
- **Structured summaries**: JSON output with key points, quotes, timestamps
- **Podcast script generation**: Two-speaker conversational script from content
- **Audio generation**: Multi-speaker TTS via `gemini-2.5-flash-preview-tts`

### Cost
- Gemini 2.5 Flash: $0.30/$2.50 per M tokens
- A 2-hour transcript (~20K tokens): less than $0.02 per query
- Context caching: 90% discount on repeated queries against same transcript

### Full pipeline

```
Transcript → Gemini API (upload + cache)
  → Q&A chat (grounded answers with citations)
  → Structured summary (JSON: key points, quotes, timestamps)
  → Podcast script (two-host dialogue)
  → Multi-speaker TTS → Audio Overview WAV file
```

### Python SDK
```bash
pip install google-genai
```

### TTS limitations
- Input limit: 8,192 tokens per TTS call
- Must generate condensed podcast script first, then convert to audio
- Output is raw PCM at 24kHz mono 16-bit (convert to MP3 with ffmpeg)

### Available voices
Kore, Puck, and others — see [Gemini TTS docs](https://ai.google.dev/gemini-api/docs/speech-generation)

---

## Workaround 3: Podcastfy (Open Source NotebookLM Alternative)

Python package that generates podcast-style audio from documents:

```bash
pip install podcastfy
```

```python
from podcastfy.client import generate_podcast
audio = generate_podcast(urls=["transcript.txt"])
```

- **LLM backends**: OpenAI, Anthropic, Google, 156+ local HuggingFace models
- **TTS backends**: OpenAI TTS, ElevenLabs, Google TTS, Microsoft Edge TTS
- **Features**: Short (2-5 min) or longform (30+ min), multilingual, customizable
- **Integration fit**: Python package, could plug directly into FastAPI backend

---

## Recommended Implementation Path

### Phase 1: Export for NotebookLM (minimal effort)
- Add transcript export as formatted `.txt` with metadata headers
- Add "Upload to Google Drive" button (Drive API integration)
- User drags file into NotebookLM manually (one click)

### Phase 2: Gemini-powered content generation (medium effort)
- Add Gemini API integration for transcript analysis
- Generate: summaries, social posts, show notes, blog drafts, enhanced chapters
- Replaces/augments existing TF-IDF metadata generation
- Cost: ~$0.02-0.05 per episode

### Phase 3: Audio Overview generation (higher effort)
- Use Gemini TTS or Podcastfy to generate podcast-style audio summaries
- Two-speaker format discussing key points from each episode
- Auto-export as MP3 alongside other project outputs

---

## Content Generation from Transcripts

A single Claude or Gemini API call can generate all of these from one transcript:

| Output | Description | Use Case |
|--------|-------------|----------|
| Show notes | Timestamped summary with key topics | YouTube description, podcast feed |
| Blog post | 1500-word article from episode content | Website, SEO |
| Social posts | 5-10 platform-specific posts | Twitter/X, LinkedIn, Instagram |
| Tweet threads | Multi-tweet breakdowns of key points | Twitter/X engagement |
| Email newsletter | Summary with CTA | Audience retention |
| Chapter markers | Enhanced timestamps with descriptions | YouTube chapters |
| Quotable moments | Best quotes with timestamps | Social clips, audiograms |
| Short-form scripts | 30-60 second video scripts | TikTok, Reels, Shorts |

Cost estimate: ~$0.05-0.15 per episode with Claude Sonnet or Gemini Flash.

---

## Comparison of Approaches

| Approach | Effort | Cost | Automation Level | Quality |
|----------|--------|------|-----------------|---------|
| Manual NotebookLM | None | Free | Manual drag-and-drop | High (Google's prompts) |
| Drive upload + manual NotebookLM | Low | Free | Semi-auto (upload auto, import manual) |High |
| Gemini API (DIY NotebookLM) | Medium | ~$0.02/episode | Fully automated | High (your prompts) |
| Podcastfy (audio only) | Medium | Varies by TTS | Fully automated | Good |
| Claude/GPT content gen | Low | ~$0.05-0.15/episode | Fully automated | Excellent |

---

## Sources

- [NotebookLM FAQ](https://support.google.com/notebooklm/answer/16269187)
- [Gemini API File Input](https://ai.google.dev/gemini-api/docs/file-input-methods)
- [Gemini TTS Docs](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Gemini Context Caching](https://ai.google.dev/gemini-api/docs/caching)
- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Google Drive API Python Quickstart](https://developers.google.com/workspace/drive/api/quickstart/python)
- [Podcastfy GitHub](https://github.com/souzatharsis/podcastfy)
- [NotebookLM Custom Instructions](https://www.ai-supremacy.com/p/notebooklm-custom-instructions)
- [NotebookLM Power User Workflows](https://www.shareuhack.com/en/posts/notebooklm-advanced-guide-2026)
- [10 NotebookLM Super Prompts](https://www.analyticsvidhya.com/blog/2026/01/notebooklm-super-prompts-for-pro-level-productivity/)
