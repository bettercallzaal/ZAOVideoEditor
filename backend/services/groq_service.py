"""Groq cloud transcription engine.

Uses the Groq API (OpenAI-compatible) for fast cloud transcription.
Handles the 25MB file limit by compressing to MP3 and chunking if needed.
"""

import json
import os
import subprocess
import tempfile
import math
from pathlib import Path


GROQ_FILE_LIMIT = 25 * 1024 * 1024  # 25 MB
GROQ_MODEL = "whisper-large-v3"


def _get_api_key() -> str:
    """Get Groq API key from environment."""
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY environment variable is not set. "
            "Get a key at https://console.groq.com and set it in your environment."
        )
    return key


def _build_prompt() -> str | None:
    """Build a prompt from dictionary terms (same glossary format as whisper_service)."""
    try:
        from .dictionary import load_dictionary
        data = load_dictionary()
        corrections = data.get("corrections", {})
        if not corrections:
            return None
        terms = sorted(set(corrections.values()))
        return "Glossary: " + ", ".join(terms)
    except Exception:
        return None


def _get_audio_duration(audio_path: str) -> float:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "csv=p=0",
                audio_path,
            ],
            capture_output=True, text=True, timeout=10,
        )
        return float(result.stdout.strip())
    except Exception:
        return 0.0


def _compress_to_mp3(audio_path: str, output_path: str, bitrate: str = "64k") -> str:
    """Compress audio to MP3 for upload size reduction."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", audio_path,
            "-vn", "-ac", "1", "-ar", "16000",
            "-b:a", bitrate,
            output_path,
        ],
        capture_output=True, timeout=300,
        check=True,
    )
    return output_path


def _split_audio(audio_path: str, chunk_duration: float, tmp_dir: str) -> list[str]:
    """Split audio into chunks of chunk_duration seconds."""
    total_duration = _get_audio_duration(audio_path)
    if total_duration <= 0:
        return [audio_path]

    num_chunks = math.ceil(total_duration / chunk_duration)
    chunks = []

    for i in range(num_chunks):
        start = i * chunk_duration
        chunk_path = os.path.join(tmp_dir, f"chunk_{i:03d}.mp3")
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", audio_path,
                "-ss", str(start), "-t", str(chunk_duration),
                "-vn", "-ac", "1", "-ar", "16000",
                "-b:a", "64k",
                chunk_path,
            ],
            capture_output=True, timeout=300,
            check=True,
        )
        chunks.append(chunk_path)

    return chunks


def _prepare_audio(audio_path: str, tmp_dir: str) -> list[tuple[str, float]]:
    """Prepare audio for Groq upload: compress and chunk if needed.

    Returns list of (file_path, time_offset) tuples.
    """
    file_size = os.path.getsize(audio_path)

    # If already small enough, use directly (Groq accepts wav, mp3, etc.)
    if file_size <= GROQ_FILE_LIMIT:
        return [(audio_path, 0.0)]

    # Compress to MP3 first
    compressed_path = os.path.join(tmp_dir, "compressed.mp3")
    _compress_to_mp3(audio_path, compressed_path)
    compressed_size = os.path.getsize(compressed_path)

    if compressed_size <= GROQ_FILE_LIMIT:
        return [(compressed_path, 0.0)]

    # Still too large — split into chunks
    # Estimate chunk duration to stay under 25MB
    total_duration = _get_audio_duration(compressed_path)
    if total_duration <= 0:
        raise RuntimeError("Cannot determine audio duration for chunking")

    bytes_per_second = compressed_size / total_duration
    # Target 20MB per chunk for safety margin
    chunk_duration = (20 * 1024 * 1024) / bytes_per_second
    chunk_duration = max(60, chunk_duration)  # at least 60 seconds

    chunks = _split_audio(compressed_path, chunk_duration, tmp_dir)
    offsets = [(chunk, i * chunk_duration) for i, chunk in enumerate(chunks)]
    return offsets


def _transcribe_chunk(file_path: str, api_key: str, prompt: str | None) -> dict:
    """Send a single file to Groq for transcription."""
    import urllib.request
    import urllib.error

    url = "https://api.groq.com/openai/v1/audio/transcriptions"

    # Build multipart form data manually (no external deps)
    boundary = "----GroqBoundary9876543210"
    body_parts = []

    # model field
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append('Content-Disposition: form-data; name="model"\r\n\r\n')
    body_parts.append(f"{GROQ_MODEL}\r\n")

    # response_format field
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append('Content-Disposition: form-data; name="response_format"\r\n\r\n')
    body_parts.append("verbose_json\r\n")

    # timestamp_granularities[] field
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append('Content-Disposition: form-data; name="timestamp_granularities[]"\r\n\r\n')
    body_parts.append("word\r\n")
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append('Content-Disposition: form-data; name="timestamp_granularities[]"\r\n\r\n')
    body_parts.append("segment\r\n")

    # language field
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append('Content-Disposition: form-data; name="language"\r\n\r\n')
    body_parts.append("en\r\n")

    # prompt field
    if prompt:
        body_parts.append(f"--{boundary}\r\n")
        body_parts.append('Content-Disposition: form-data; name="prompt"\r\n\r\n')
        body_parts.append(f"{prompt}\r\n")

    # File field — read binary data
    with open(file_path, "rb") as f:
        file_data = f.read()

    filename = os.path.basename(file_path)
    file_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: audio/mpeg\r\n\r\n"
    )

    closing = f"\r\n--{boundary}--\r\n"

    # Assemble body: text parts (encoded) + file header + binary data + closing
    text_part = "".join(body_parts).encode("utf-8")
    full_body = text_part + file_header.encode("utf-8") + file_data + closing.encode("utf-8")

    req = urllib.request.Request(
        url,
        data=full_body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        if e.code == 401:
            raise RuntimeError("Groq API key is invalid. Check your GROQ_API_KEY.")
        elif e.code == 413:
            raise RuntimeError(
                f"File too large for Groq API (even after compression). "
                f"Try a shorter audio file."
            )
        elif e.code == 429:
            raise RuntimeError(
                "Groq rate limit exceeded. Wait a moment and try again, "
                "or switch to a local engine."
            )
        else:
            raise RuntimeError(f"Groq API error {e.code}: {error_body}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach Groq API: {e.reason}")


def transcribe_audio_groq(audio_path: str, on_progress=None) -> dict:
    """Transcribe audio using the Groq cloud API.

    Returns the same format as whisper_service.transcribe_audio():
    {
        "segments": [...],
        "raw_text": "...",
        "language": "en",
        "duration": float,
        "quality": "cloud",
        "passes": 1,
        "engine": "groq",
    }
    """
    api_key = _get_api_key()
    prompt = _build_prompt()

    if on_progress:
        on_progress(5, "Preparing audio for Groq...")

    with tempfile.TemporaryDirectory(prefix="groq_") as tmp_dir:
        chunks = _prepare_audio(audio_path, tmp_dir)
        num_chunks = len(chunks)

        all_segments = []
        full_text_parts = []
        total_duration = _get_audio_duration(audio_path)

        for idx, (chunk_path, time_offset) in enumerate(chunks):
            if on_progress:
                pct = 10 + (idx / num_chunks) * 80
                msg = (
                    f"Transcribing with Groq ({idx + 1}/{num_chunks})..."
                    if num_chunks > 1
                    else "Transcribing with Groq..."
                )
                on_progress(pct, msg)

            result = _transcribe_chunk(chunk_path, api_key, prompt)

            # Parse segments from Groq response
            groq_segments = result.get("segments", [])
            for seg in groq_segments:
                words = []
                for w in seg.get("words", []):
                    words.append({
                        "word": w.get("word", ""),
                        "start": round(w.get("start", 0) + time_offset, 3),
                        "end": round(w.get("end", 0) + time_offset, 3),
                        "probability": round(w.get("probability", 0), 3),
                    })

                all_segments.append({
                    "id": len(all_segments),
                    "start": round(seg.get("start", 0) + time_offset, 3),
                    "end": round(seg.get("end", 0) + time_offset, 3),
                    "text": seg.get("text", "").strip(),
                    "words": words,
                })

            chunk_text = result.get("text", "")
            if chunk_text:
                full_text_parts.append(chunk_text.strip())

            # Use duration from Groq response if available
            if result.get("duration"):
                total_duration = max(total_duration, time_offset + result["duration"])

    if on_progress:
        on_progress(95, "Groq transcription complete")

    raw_text = " ".join(full_text_parts) if full_text_parts else " ".join(
        seg["text"] for seg in all_segments
    )

    return {
        "segments": all_segments,
        "raw_text": raw_text,
        "language": "en",
        "duration": round(total_duration, 1),
        "quality": "cloud",
        "passes": 1,
        "engine": "groq",
    }
