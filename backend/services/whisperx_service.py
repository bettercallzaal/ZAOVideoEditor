"""WhisperX transcription engine — word-level alignment + optional diarization."""

import time
import os


def transcribe_audio_whisperx(
    audio_path: str,
    quality: str = "standard",
    diarize: bool = False,
    hf_token: str = None,
    on_progress=None,
) -> dict:
    """Transcribe using WhisperX with forced alignment for accurate word timestamps.

    Returns same format as whisper_service.transcribe_audio().
    """
    import whisperx

    device = "cpu"
    compute_type = "int8"

    # Model selection by quality
    model_map = {
        "fast": "base",
        "standard": "large-v3",
        "high": "large-v3",
    }
    model_size = model_map.get(quality, "large-v3")

    if on_progress:
        on_progress(5, f"Loading WhisperX model ({model_size})...")

    model = whisperx.load_model(
        model_size, device, compute_type=compute_type,
    )

    if on_progress:
        on_progress(15, "Transcribing audio...")

    # Build initial_prompt from dictionary for better name/brand recognition
    initial_prompt = None
    try:
        from .dictionary import load_dictionary
        data = load_dictionary()
        terms = sorted(set(data.get("corrections", {}).values()))
        if terms:
            initial_prompt = "Glossary: " + ", ".join(terms)
    except Exception:
        pass

    start_time = time.time()
    audio = whisperx.load_audio(audio_path)
    transcribe_opts = {"batch_size": 8}
    if initial_prompt:
        transcribe_opts["initial_prompt"] = initial_prompt
    result = model.transcribe(audio, **transcribe_opts)

    if on_progress:
        on_progress(50, "Aligning word timestamps...")

    # Forced alignment for word-level timestamps
    language = result.get("language", "en")
    align_model, align_metadata = whisperx.load_align_model(
        language_code=language, device=device,
    )
    result = whisperx.align(
        result["segments"], align_model, align_metadata,
        audio, device, return_char_alignments=False,
    )

    if on_progress:
        on_progress(75, "Processing results...")

    # Optional diarization
    if diarize:
        if on_progress:
            on_progress(80, "Running speaker diarization...")
        token = hf_token or os.environ.get("HF_TOKEN")
        if token:
            diarize_model = whisperx.DiarizationPipeline(
                use_auth_token=token, device=device,
            )
            diarize_segments = diarize_model(audio)
            result = whisperx.assign_word_speakers(diarize_segments, result)

    # Convert to our standard segment format
    segments = []
    raw_parts = []
    for i, seg in enumerate(result.get("segments", [])):
        words = []
        for w in seg.get("words", []):
            words.append({
                "word": w.get("word", ""),
                "start": w.get("start", seg.get("start", 0)),
                "end": w.get("end", seg.get("end", 0)),
                "probability": w.get("score", 0.9),
            })

        segment = {
            "id": i,
            "start": seg.get("start", 0),
            "end": seg.get("end", 0),
            "text": seg.get("text", "").strip(),
            "words": words,
        }

        if diarize and "speaker" in seg:
            segment["speaker"] = seg["speaker"]

        segments.append(segment)
        raw_parts.append(seg.get("text", "").strip())

    elapsed = time.time() - start_time

    if on_progress:
        on_progress(100, f"WhisperX complete ({elapsed:.0f}s)")

    return {
        "segments": segments,
        "raw_text": " ".join(raw_parts),
        "language": language,
        "duration": elapsed,
        "quality": quality,
        "engine": "whisperx",
        "passes": 1,
    }
