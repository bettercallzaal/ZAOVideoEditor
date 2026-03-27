"""LLM-powered content generation from transcripts.

Generates recaps, clippable moments, show notes, and social posts
from a transcript using OpenAI or compatible APIs.
"""

import os
import json
import re


def _get_client():
    """Get an OpenAI-compatible client. Priority: Ollama (local) > OpenAI > Groq."""
    # 1. Try Ollama (local, free, no API key needed)
    try:
        import httpx
        r = httpx.get("http://localhost:11434/api/tags", timeout=2)
        if r.status_code == 200:
            models = r.json().get("models", [])
            # Pick best available model
            model_prefs = ["qwen3:30b", "qwen3:14b", "qwen3:8b", "llama3.2:latest", "mistral:latest"]
            model_names = [m["name"] for m in models]
            picked = None
            for pref in model_prefs:
                if pref in model_names:
                    picked = pref
                    break
            if not picked and model_names:
                picked = model_names[0]
            if picked:
                from openai import OpenAI
                return OpenAI(api_key="ollama", base_url="http://localhost:11434/v1"), picked
    except Exception:
        pass

    # 2. OpenAI
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        from openai import OpenAI
        return OpenAI(), "gpt-4o-mini"

    # 3. Groq (free tier)
    groq_key = os.environ.get("GROQ_API_KEY")
    if groq_key:
        from openai import OpenAI
        return OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1"), "llama-3.3-70b-versatile"

    return None, None


def _format_transcript(segments: list, max_chars: int = 80000) -> str:
    """Format transcript segments into timestamped text for the LLM."""
    lines = []
    for seg in segments:
        m = int(seg["start"] // 60)
        s = int(seg["start"] % 60)
        speaker = seg.get("speaker", "")
        prefix = f"[{m:02d}:{s:02d}]"
        if speaker:
            prefix += f" {speaker}:"
        lines.append(f"{prefix} {seg['text']}")

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[... transcript truncated for length ...]"
    return text


def generate_recap_and_clips(segments: list, project_name: str = "") -> dict:
    """Generate a recap and top clippable moments from transcript segments.

    Returns:
        {
            "recap": "...",
            "clips": [
                {
                    "title": "...",
                    "start": "MM:SS",
                    "end": "MM:SS",
                    "start_seconds": float,
                    "end_seconds": float,
                    "hook": "...",
                    "why_clip": "..."
                },
                ...
            ],
            "show_notes": "...",
            "tweets": ["...", ...],
            "model": "..."
        }
    """
    client, model = _get_client()
    if not client:
        raise RuntimeError(
            "No API key found. Set OPENAI_API_KEY or GROQ_API_KEY environment variable."
        )

    transcript_text = _format_transcript(segments)

    prompt = f"""You are a content strategist analyzing a video transcript. The project is called "{project_name}".

Analyze this transcript and return a JSON object with these fields:

1. "recap" — A 3-5 paragraph engaging summary of the entire conversation. Write it as if describing the episode to someone who hasn't seen it. Include the most interesting points, key takeaways, and notable moments. Use specific details from the transcript.

2. "clips" — An array of the TOP 8 most clippable moments. These are 30-90 second segments that would work as standalone short-form content (TikTok, Reels, Shorts). For each clip:
   - "title": A catchy 5-10 word title for the clip
   - "start": Start timestamp as "MM:SS"
   - "end": End timestamp as "MM:SS"
   - "hook": The first sentence/hook that would grab attention in the first 3 seconds
   - "why_clip": One sentence explaining why this moment is clippable (emotional, surprising, insightful, funny, controversial, etc.)

   Prioritize moments that are: surprising revelations, strong opinions, funny/emotional reactions, specific actionable advice, memorable quotes, heated exchanges, or "aha" moments. Avoid generic filler or transitions.

3. "show_notes" — Timestamped show notes suitable for a YouTube description. Include major topic transitions with timestamps.

4. "tweets" — 5 standalone tweets (under 280 chars each) that each highlight a different interesting moment or insight from the conversation. Include the timestamp reference.

IMPORTANT: Use the exact timestamps from the transcript. Return ONLY valid JSON, no markdown fences.

TRANSCRIPT:
{transcript_text}"""

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=4096,
    )

    raw = response.choices[0].message.content.strip()

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

    result = json.loads(raw)

    # Parse timestamps into seconds for seeking
    for clip in result.get("clips", []):
        clip["start_seconds"] = _parse_timestamp(clip.get("start", "0:00"))
        clip["end_seconds"] = _parse_timestamp(clip.get("end", "0:00"))

    result["model"] = model
    return result


def polish_transcript(segments: list, dictionary_terms: list[str] = None) -> list:
    """Use LLM to fix misspelled names, brands, and proper nouns in transcript segments.

    Processes segments in chunks of 25 to stay within context limits.
    Returns corrected segments in the same format.
    """
    client, model = _get_client()
    if not client:
        raise RuntimeError(
            "No LLM available. Ensure Ollama is running, or set OPENAI_API_KEY or GROQ_API_KEY."
        )

    terms_str = ", ".join(dictionary_terms) if dictionary_terms else "none provided"
    chunk_size = 25
    polished = []

    for i in range(0, len(segments), chunk_size):
        chunk = segments[i:i + chunk_size]

        # Build a compact representation for the LLM
        chunk_data = []
        for seg in chunk:
            chunk_data.append({
                "id": seg["id"],
                "text": seg["text"],
                "speaker": seg.get("speaker", ""),
            })

        prompt = f"""Fix any misspelled names, brands, proper nouns, or obvious transcription errors in these transcript segments.

Known correct spellings: {terms_str}

Rules:
- Only fix spelling/transcription errors. Do NOT change meaning, rephrase, or add content.
- If a segment looks correct, return it unchanged.
- Return ONLY a JSON array of objects with "id" and "text" fields (same ids as input).
- Do not include markdown fences or any text outside the JSON array.

Input segments:
{json.dumps(chunk_data, indent=2)}"""

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
            max_tokens=4096,
        )

        raw = response.choices[0].message.content.strip()

        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r'^```(?:json)?\s*', '', raw)
            raw = re.sub(r'\s*```$', '', raw)

        # Strip <think> blocks from reasoning models like qwen3
        raw = re.sub(r'<think>[\s\S]*?</think>\s*', '', raw)

        try:
            corrections = json.loads(raw)
            # Build lookup of corrections by id
            correction_map = {c["id"]: c["text"] for c in corrections}

            for seg in chunk:
                corrected_seg = dict(seg)
                if seg["id"] in correction_map:
                    corrected_seg["text"] = correction_map[seg["id"]]
                polished.append(corrected_seg)
        except (json.JSONDecodeError, KeyError):
            # If LLM returned bad JSON, keep original segments for this chunk
            polished.extend(chunk)

    return polished


def _parse_timestamp(ts: str) -> float:
    """Parse MM:SS or HH:MM:SS to seconds."""
    parts = ts.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return 0.0
