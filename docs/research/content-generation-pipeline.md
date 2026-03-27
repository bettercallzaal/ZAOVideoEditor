# Content Generation Pipeline Research

> Researched 2026-03-27. How to turn transcripts into content automatically — blog posts, social media, show notes, audio summaries.

## Goal

After transcribing a stream/video in ZAO, automatically generate:
- Show notes with timestamps
- Blog post draft
- Social media posts (Twitter/X, LinkedIn, Instagram)
- Chapter markers (enhanced beyond current TF-IDF approach)
- Quotable moments with timestamps
- Audio summary (NotebookLM-style "Audio Overview")

---

## Approach 1: LLM API (Recommended — Simplest, Most Flexible)

A single API call to Claude or Gemini can generate ALL content outputs from one transcript.

### Cost Comparison

| Model | Input (per M tokens) | Output (per M tokens) | Cost per episode (~20K tokens) |
|-------|---------------------|----------------------|-------------------------------|
| Claude Haiku 4.5 | $1.00 | $5.00 | ~$0.02 |
| Claude Sonnet 4.6 | $3.00 | $15.00 | ~$0.05 |
| Gemini 2.5 Flash | $0.30 | $2.50 | ~$0.01 |
| GPT-4o | $2.50 | $10.00 | ~$0.04 |
| GPT-4.1-mini | $0.40 | $1.60 | ~$0.01 |

### Integration plan

Add `POST /api/projects/{name}/generate-content` endpoint:

```python
import anthropic

def generate_content(transcript_text: str, project_name: str) -> dict:
    client = anthropic.Anthropic()

    response = client.messages.create(
        model="claude-sonnet-4-6-20250514",
        max_tokens=4096,
        system="You are a content strategist for the WaveWarZ YouTube channel.",
        messages=[{
            "role": "user",
            "content": f"""Based on this transcript, generate ALL of the following as JSON:

1. "show_notes": Timestamped summary with key topics (for YouTube description)
2. "blog_post": 800-1200 word blog post covering main insights
3. "tweets": 5 standalone tweets, each highlighting a different insight
4. "linkedin_post": 1 LinkedIn post with key takeaway
5. "chapters": Enhanced chapter markers with timestamps and descriptions
6. "quotes": Top 5 quotable moments with exact timestamps
7. "short_form_hooks": 3 hooks for 30-second video clips with start/end timestamps

TRANSCRIPT:
{transcript_text}"""
        }],
    )
    return json.loads(response.content[0].text)
```

### Gemini alternative (cheaper, longer context)

```python
from google import genai
from google.genai import types

client = genai.Client()
file = client.files.upload(file='transcript.txt')

# Cache for multiple queries
cached = client.caches.create(
    model='gemini-2.5-flash',
    config=types.CreateCachedContentConfig(
        contents=[types.Content(role='user', parts=[file])],
        system_instruction='Content strategist for WaveWarZ YouTube channel.',
        ttl='3600s',
    ),
)

# Generate different content types against cached transcript
show_notes = client.models.generate_content(
    model='gemini-2.5-flash',
    contents='Generate timestamped show notes for YouTube description.',
    config=types.GenerateContentConfig(cached_content=cached.name),
)
```

Context caching gives **90% discount** on repeated queries against the same transcript.

---

## Approach 2: Audio Overview (Podcast-Style Summary)

### Option A: Gemini TTS (Native multi-speaker)

```python
from google import genai
from google.genai import types

client = genai.Client()

# Step 1: Generate podcast script from transcript
script = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=[transcript_file,
        "Generate a 3-minute podcast script between Host1 and Host2 discussing key points."],
).text

# Step 2: Convert to multi-speaker audio
response = client.models.generate_content(
    model="gemini-2.5-flash-preview-tts",
    contents=script,
    config=types.GenerateContentConfig(
        response_modalities=["AUDIO"],
        speech_config=types.SpeechConfig(
            multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                speaker_voice_configs=[
                    types.SpeakerVoiceConfig(speaker='Host1',
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name='Kore'))),
                    types.SpeakerVoiceConfig(speaker='Host2',
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name='Puck'))),
                ]
            )
        )
    )
)
# Save as WAV, convert to MP3 with ffmpeg
```

**Limitation**: TTS input capped at 8,192 tokens — generate a condensed script first.

### Option B: Podcastfy (Open Source)

```bash
pip install podcastfy
```

```python
from podcastfy.client import generate_podcast
audio = generate_podcast(
    urls=["transcript.txt"],
    tts_model="openai",  # or "elevenlabs", "google", "edge"
)
```

Supports: OpenAI, Anthropic, Google, 156+ local models for script generation. OpenAI TTS, ElevenLabs, Google TTS, Edge TTS for voices.

### Option C: ElevenLabs (Best Voice Quality)

| Plan | Price | Credits/mo | Best For |
|------|-------|-----------|----------|
| Free | $0 | 10K | Testing |
| Starter | $5/mo | 30K | Light use |
| Creator | $11/mo | 100K | Regular episodes |
| Pro | $99/mo | 500K | Heavy production |

```python
from elevenlabs import ElevenLabs
client = ElevenLabs(api_key="...")
audio = client.text_to_speech.convert(
    text="Welcome to today's episode recap...",
    voice_id="voice_id_here",
    model_id="eleven_multilingual_v2",
)
```

### Option D: OpenAI TTS

| Model | Cost | Voices |
|-------|------|--------|
| tts-1 | $15/M chars | 13 voices |
| tts-1-hd | $15/M chars | 13 voices |
| gpt-4o-mini-tts | $0.60/M input + $12/M audio output | 13 voices |

---

## Approach 3: All-in-One Platforms

### Castmagic ($179/mo for API access)
- Upload audio → get transcription + 40+ content outputs automatically
- Blog posts, social posts, show notes, newsletters, titles, quotes
- API available on Rising Star plan
- Zapier/Make/Pipedream integrations

### Descript ($0.05/min API)
- Full audio/video editor with transcription
- "AI Actions": turn into blog post, social posts, show notes (UI only, not in API)
- API focuses on media editing, not content generation

### Opus Clip (Closed beta API)
- Long video → short viral clips with captions
- Two models: ClipBasic (talking-head), ClipAnything (any footage)
- Requires high-volume annual Pro plan

---

## Approach 4: Workflow Automation

### n8n (Self-hostable, recommended)
- Open source, free to self-host
- 70+ LangChain nodes for AI workflows
- Template: "YouTube video to blog post with Gemini"
- Complex multi-step: transcript → Claude → blog + social + show notes → publish

### Make.com ($9/mo)
- Visual builder, good LLM integrations
- 10K operations/month

### Zapier ($19.99/mo)
- Simplest setup, direct ChatGPT integration
- 750 tasks/month

---

## Recommended Implementation for ZAO

### Phase 1: LLM Content Generation (do this first)
- Add `anthropic` or `google-genai` to backend requirements
- New endpoint: `POST /api/projects/{name}/generate-content`
- Reads `transcripts/edited.json`, generates all content as JSON
- New "Content" tab in frontend showing generated outputs with copy buttons
- Cost: ~$0.02-0.15 per episode
- Replaces/augments existing TF-IDF metadata generation

### Phase 2: Audio Summary
- Integrate Podcastfy or Gemini TTS for podcast-style recaps
- Generate 2-5 minute audio summary per episode
- Export as MP3 alongside other project outputs

### Phase 3: Export Integrations
- "Upload to Google Drive" button (for NotebookLM import)
- "Copy for NotebookLM" button (formatted .txt with metadata headers)
- Optional: direct Zapier/n8n webhook for publishing pipeline

---

## Sources

- [Claude API Pricing](https://platform.claude.com/docs/en/about-claude/pricing)
- [Gemini API Pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini TTS Docs](https://ai.google.dev/gemini-api/docs/speech-generation)
- [Gemini Context Caching](https://ai.google.dev/gemini-api/docs/caching)
- [Podcastfy GitHub](https://github.com/souzatharsis/podcastfy)
- [ElevenLabs API Pricing](https://elevenlabs.io/pricing/api)
- [OpenAI TTS Guide](https://developers.openai.com/api/docs/guides/text-to-speech)
- [Castmagic Docs](https://docs.castmagic.io/)
- [Opus Clip API](https://www.opus.pro/api)
- [Descript API](https://docs.descriptapi.com/)
- [n8n AI Workflows](https://blog.n8n.io/best-ai-workflow-automation-tools/)
- [AutoContent API](https://autocontentapi.com/)
