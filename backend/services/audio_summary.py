"""Generate a podcast-style audio summary from a transcript recap.

Uses Ollama (or OpenAI/Groq) to generate a 2-speaker podcast script,
then gTTS for text-to-speech, and ffmpeg to concatenate segments.
"""

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

from .content_gen import _get_client


def _generate_podcast_script(recap_text: str) -> list[dict]:
    """Use an LLM to generate a short 2-speaker podcast script from the recap.

    Returns a list of dicts: [{"speaker": "Host1"|"Host2", "line": "..."}]
    """
    client, model = _get_client()
    if not client:
        raise RuntimeError(
            "No LLM available. Set OPENAI_API_KEY or GROQ_API_KEY, or run Ollama locally."
        )

    prompt = f"""You are a podcast script writer. Given this video recap, write a short 2-speaker podcast discussion.

RULES:
- Use exactly two speakers: "Host1" and "Host2"
- Host1 is the main narrator who introduces topics
- Host2 adds reactions, follow-up questions, and commentary
- Keep it conversational and engaging — like a real podcast
- 8-14 exchanges total (so the audio stays under 3 minutes)
- Each line should be 1-3 sentences max
- Start with a brief intro, cover the key points, end with a wrap-up
- Return ONLY a JSON array of objects with "speaker" and "line" fields
- No markdown fences

RECAP:
{recap_text}"""

    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.7,
        max_tokens=2048,
    )

    raw = response.choices[0].message.content.strip()

    # Strip <think> blocks from reasoning models like qwen3
    raw = re.sub(r'<think>[\s\S]*?</think>\s*', '', raw)

    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r'^```(?:json)?\s*', '', raw)
        raw = re.sub(r'\s*```$', '', raw)

    script = json.loads(raw)

    # Validate structure
    for entry in script:
        if "speaker" not in entry or "line" not in entry:
            raise ValueError("Invalid script format — each entry needs 'speaker' and 'line'")
        if entry["speaker"] not in ("Host1", "Host2"):
            entry["speaker"] = "Host1"  # fallback

    return script


def _synthesize_line(text: str, speaker: str, output_path: str):
    """Synthesize a single line of dialogue using gTTS.

    Uses different TLD settings for each speaker to create distinct voices.
    """
    from gtts import gTTS

    # Use different accents/TLDs to differentiate speakers
    if speaker == "Host1":
        tts = gTTS(text=text, lang='en', tld='com')       # US English
    else:
        tts = gTTS(text=text, lang='en', tld='co.uk')     # UK English

    tts.save(output_path)


def _concatenate_audio(segment_paths: list[str], output_path: str):
    """Concatenate audio segments into one file using ffmpeg."""
    if not segment_paths:
        raise ValueError("No audio segments to concatenate")

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        for path in segment_paths:
            f.write(f"file '{path}'\n")
        list_file = f.name

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-acodec", "libmp3lame",
            "-ab", "192k",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr}")
    finally:
        os.unlink(list_file)


def generate_audio_summary(recap_text: str, project_dir: str) -> str:
    """Generate a podcast-style audio summary from a recap.

    Args:
        recap_text: The recap text from content generation.
        project_dir: Path to the project directory.

    Returns:
        The file path to the generated audio summary MP3.
    """
    project_path = Path(project_dir)
    exports_dir = project_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(exports_dir / "audio_summary.mp3")

    # Step 1: Generate the podcast script via LLM
    script = _generate_podcast_script(recap_text)

    # Step 2: Synthesize each line
    segment_paths = []
    tmp_dir = tempfile.mkdtemp(prefix="audio_summary_")

    try:
        for i, entry in enumerate(script):
            seg_path = os.path.join(tmp_dir, f"seg_{i:03d}.mp3")
            _synthesize_line(entry["line"], entry["speaker"], seg_path)
            segment_paths.append(seg_path)

        # Step 3: Concatenate all segments
        _concatenate_audio(segment_paths, output_path)

    finally:
        # Clean up temp segments
        for p in segment_paths:
            try:
                os.unlink(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

    return output_path
