# Transcription Services Research

> Researched 2026-03-27. Comparison of transcription options for the ZAO Video Editor pipeline.

## Current System

ZAO uses a **3-tier approach** for YouTube videos and **local faster-whisper** for uploaded videos:

1. **youtube-transcript-api** (~0.5s) — fetches YouTube's existing captions
2. **yt-dlp subtitle extraction** (~3-5s) — downloads subtitle files without video
3. **faster-whisper local** (minutes-hours) — last resort, downloads audio and transcribes on CPU

The dictionary feeds into Whisper via `initial_prompt` + `hotwords` for better name/brand recognition. User edits auto-learn new corrections.

---

## Cloud Transcription Services Comparison

| Service | Speed (10 min) | Custom Vocab | Cost/hour | Free Tier | Best For |
|---------|---------------|-------------|-----------|-----------|----------|
| **faster-whisper (local)** | 2-5 min CPU | `initial_prompt` + `hotwords` (224 tokens) | Free | N/A | Privacy, no cost |
| **Groq Whisper** | 2-3 sec | `prompt` (224 tokens) | $0.04 | 8 hrs/day | Fast + free |
| **OpenAI whisper-1** | 10-20 sec | `prompt` (224 tokens) | $0.36 | No | SRT/VTT output, word timestamps |
| **OpenAI gpt-4o-transcribe** | 10-20 sec | `prompt` (more flexible) | $0.36 | No | Best accuracy, diarization |
| **Deepgram Nova-3** | 5-10 sec | Keyterm prompting (500 tokens) | $0.46 | $200 credit | Best custom vocab (90% recall boost) |
| **AssemblyAI** | 30-60 sec | `word_boost` (2500 words) + `custom_spelling` | $0.37 | $50 credit | Most dictionary-like features |

---

## Service Details

### Groq Whisper API (Best Free Option)

- Runs Whisper on custom LPU hardware — 189-299x real-time speed
- **Models**: whisper-large-v3, whisper-large-v3-turbo, distil-whisper-large-v3-en
- **Free tier**: 20 req/min, 2000 req/day, 8 hours audio/day
- **File size**: 25 MB (free), 100 MB (dev)
- **OpenAI-compatible API** — drop-in replacement using OpenAI SDK
- **Supports `prompt` parameter** for custom vocabulary (same as OpenAI's Whisper)

```python
from groq import Groq
client = Groq()
transcription = client.audio.transcriptions.create(
    file=open("audio.wav", "rb"),
    model="whisper-large-v3-turbo",
    prompt="ZAO, Zaal Panthaki, WaveWarZ, SongJam, Farcaster",
    response_format="verbose_json",
    timestamp_granularities=["word", "segment"],
)
```

### Deepgram Nova-3 (Best Custom Vocabulary)

- **Keyterm prompting**: Up to 500 tokens, 90% keyword recall improvement
- **Keyword boosting** (Nova-2): Exponential boost factors per word, 100 keyword limit
- **$200 free credit** on signup, never expires (~700+ hours of audio)
- **Custom model training**: $10,000 enterprise option

```python
from deepgram import DeepgramClient
deepgram = DeepgramClient(API_KEY)
response = deepgram.listen.v1.media.transcribe_file(
    request=audio_file.read(),
    model="nova-3",
    smart_format=True,
    keyterm=["Zaal Panthaki", "WaveWarZ", "SongJam"],
)
```

### AssemblyAI (Best Dictionary-Like Features)

- **word_boost**: Up to 2,500 words/phrases, boost levels: low/default/high
- **custom_spelling**: Define explicit spelling corrections (e.g., "zao" variants → "ZAO")
- **$50 free credit** on signup
- Speaker diarization included at no extra cost

```python
import assemblyai as aai
config = aai.TranscriptionConfig(
    word_boost=["ZAO", "Zaal", "WaveWarZ", "SongJam"],
    boost_param="high",
    custom_spelling={"ZAO": ["zao", "zow"], "WaveWarZ": ["wave wars", "wavewars"]},
    speaker_labels=True,
)
transcript = aai.Transcriber().transcribe("audio.wav", config=config)
```

### OpenAI gpt-4o-transcribe (Best Accuracy)

- Newer model, better than whisper-1 for accuracy
- More flexible prompt handling (closer to GPT instruction-following)
- **No SRT/VTT output** — only JSON and text
- **No word-level timestamps** — whisper-1 still needed for caption timing
- **Speaker diarization** via `gpt-4o-transcribe-diarize` model
- 25 MB file size limit — chunk longer files

---

## Dictionary-Guided Transcription (Current Implementation)

### Whisper initial_prompt
- 224 token limit (~150-200 words)
- Glossary format: `"Glossary: ZAO, WaveWarZ, SongJam, Farcaster, Ohnahji, Saltorius"`
- Acts as prior context — biases Whisper toward those spellings
- Cannot guarantee correct spellings, only influences probability

### Whisper hotwords (faster-whisper only)
- Directly boosts token probabilities for specified words
- Combined with initial_prompt, shares the 448 token budget
- No effect if `prefix` parameter is set

### Post-processing dictionary
- Regex replacement with word boundaries (`\b`)
- Sorted by length descending (longer phrases first)
- Auto-learn from user edits (candidates → 2 occurrences → promoted)

---

## Learning/Feedback Architecture

### Current (implemented)
```
Audio → Whisper (initial_prompt from dictionary) → Dictionary correction → User edit
                                                                            ↓
                                                         Diff → update dictionary candidates
```

### Future improvements (not yet implemented)

| Enhancement | Effort | Impact |
|-------------|--------|--------|
| LLM post-processing (Claude/GPT fixes proper nouns) | Low | High |
| Phonetic/fuzzy matching (catch "sal torius" → "Saltorius") | Medium | Medium |
| Per-speaker correction profiles | Medium | Medium |
| LoRA fine-tuning from corrected transcripts | High | Very high |
| Confidence-aware correction (low-confidence words flagged more aggressively) | Low | Medium |

### LoRA Fine-Tuning (if needed later)
- Minimum ~1.5 hours of corrected audio-text pairs for measurable improvement
- Sweet spot: 5-8 hours of domain-specific data
- LoRA rank 8-32, targeting q_proj and v_proj attention layers
- Can run on consumer GPU (8GB+ VRAM)
- Catch: HuggingFace fine-tuned models need conversion for faster-whisper (CTranslate2 format)

---

## Recommended Next Steps

1. **Add Groq as fast cloud option** — free, 2-3 sec transcription, supports prompt parameter
2. **Add LLM polish step** — send transcript + dictionary to Claude/Gemini for context-aware correction
3. **Add phonetic matching** — use `rapidfuzz` for fuzzy dictionary lookups
4. **Consider Deepgram** for episodes where accuracy is critical — $200 free credit, best custom vocab

---

## Sources

- [faster-whisper GitHub](https://github.com/SYSTRAN/faster-whisper)
- [OpenAI Whisper Prompting Guide](https://developers.openai.com/cookbook/examples/whisper_prompting_guide)
- [Groq Speech-to-Text Docs](https://console.groq.com/docs/speech-to-text)
- [Deepgram Keyterm Prompting](https://developers.deepgram.com/docs/keyterm)
- [Deepgram Keywords](https://developers.deepgram.com/docs/keywords)
- [AssemblyAI Word Boost](https://www.assemblyai.com/docs/speech-to-text/custom-vocabulary)
- [OpenAI Transcription API](https://developers.openai.com/api/docs/guides/speech-to-text)
- [Whisper Fine-Tuning with LoRA](https://huggingface.co/blog/fine-tune-whisper)
- [OpenAI Cookbook: Correcting Misspellings](https://developers.openai.com/cookbook/examples/whisper_correct_misspelling)
