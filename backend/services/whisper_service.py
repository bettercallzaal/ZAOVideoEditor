"""Multi-pass transcription engine.

Quality levels:
  - fast:     1 pass with base model (quick draft)
  - standard: 1 pass with large-v3 model
  - high:     3 passes with large-v3, different params, consensus merge
"""

import json
from pathlib import Path
from difflib import SequenceMatcher


# Each pass uses different parameters to capture different aspects
PASS_CONFIGS = [
    {
        "name": "precise",
        "beam_size": 5,
        "best_of": 5,
        "temperature": 0.0,
        "condition_on_previous_text": True,
        "no_speech_threshold": 0.6,
        "compression_ratio_threshold": 2.4,
    },
    {
        "name": "exploratory",
        "beam_size": 8,
        "best_of": 8,
        "temperature": 0.2,
        "condition_on_previous_text": False,
        "no_speech_threshold": 0.5,
        "compression_ratio_threshold": 2.6,
    },
    {
        "name": "aggressive",
        "beam_size": 5,
        "best_of": 5,
        "temperature": 0.0,
        "condition_on_previous_text": True,
        "no_speech_threshold": 0.4,
        "compression_ratio_threshold": 2.8,
    },
]


def _build_vocab_prompt() -> tuple[str | None, str | None]:
    """Build initial_prompt and hotwords from the correction dictionary.

    Returns (initial_prompt, hotwords) for faster-whisper.
    """
    try:
        from .dictionary import load_dictionary
        data = load_dictionary()
        corrections = data.get("corrections", {})
        if not corrections:
            return None, None

        # Unique correct terms for the prompt
        terms = sorted(set(corrections.values()))

        # initial_prompt: glossary format gives Whisper spelling context
        initial_prompt = "Glossary: " + ", ".join(terms)

        # hotwords: space-separated terms that boost token probabilities
        hotwords = ", ".join(terms)

        return initial_prompt, hotwords
    except Exception:
        return None, None


def _run_single_pass(model, audio_path: str, config: dict, on_progress=None) -> list:
    """Run a single transcription pass and return segments."""
    initial_prompt, hotwords = _build_vocab_prompt()

    segments_iter, info = model.transcribe(
        audio_path,
        beam_size=config["beam_size"],
        best_of=config.get("best_of", config["beam_size"]),
        temperature=config.get("temperature", 0.0),
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={
            "min_silence_duration_ms": 300,
            "speech_pad_ms": 200,
        },
        condition_on_previous_text=config.get("condition_on_previous_text", True),
        no_speech_threshold=config.get("no_speech_threshold", 0.6),
        compression_ratio_threshold=config.get("compression_ratio_threshold", 2.4),
        initial_prompt=initial_prompt,
        hotwords=hotwords,
    )

    duration = info.duration if info.duration else 1
    segments = []

    for i, segment in enumerate(segments_iter):
        words = []
        if segment.words:
            for w in segment.words:
                words.append({
                    "word": w.word,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "probability": round(w.probability, 3),
                })

        seg_data = {
            "id": i,
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "text": segment.text.strip(),
            "words": words,
            "avg_logprob": round(segment.avg_logprob, 4) if segment.avg_logprob else 0,
            "no_speech_prob": round(segment.no_speech_prob, 4) if segment.no_speech_prob else 0,
        }
        segments.append(seg_data)

        if on_progress:
            on_progress(segment.end, duration, i + 1)

    return segments, info


def _word_confidence(word: dict) -> float:
    """Get confidence score for a word."""
    return word.get("probability", 0)


def _segment_confidence(seg: dict) -> float:
    """Average word confidence for a segment."""
    words = seg.get("words", [])
    if not words:
        return 0
    return sum(_word_confidence(w) for w in words) / len(words)


def _align_and_merge_segments(all_pass_segments: list[list]) -> list:
    """Merge multiple transcription passes using confidence-weighted consensus.

    Strategy:
    1. Use the first pass (precise) as the base timeline
    2. For each segment, find overlapping segments from other passes
    3. Compare word-by-word and pick the highest-confidence version
    4. For segments where passes disagree significantly, use word-level voting
    """
    if len(all_pass_segments) == 1:
        return all_pass_segments[0]

    base_segments = all_pass_segments[0]
    other_passes = all_pass_segments[1:]

    merged = []

    for base_seg in base_segments:
        # Find overlapping segments from other passes
        overlapping = []
        for pass_segments in other_passes:
            for seg in pass_segments:
                # Check time overlap (at least 50% overlap)
                overlap_start = max(base_seg["start"], seg["start"])
                overlap_end = min(base_seg["end"], seg["end"])
                overlap_duration = overlap_end - overlap_start
                base_duration = base_seg["end"] - base_seg["start"]

                if base_duration > 0 and overlap_duration / base_duration > 0.5:
                    overlapping.append(seg)
                    break  # one match per pass

        # If no other passes matched this time range, keep base
        if not overlapping:
            merged.append(base_seg)
            continue

        # Collect all candidates: base + overlapping
        candidates = [base_seg] + overlapping

        # Pick the segment with highest average word confidence
        best_seg = max(candidates, key=_segment_confidence)

        # Now try word-level merge for even better quality
        if best_seg.get("words") and all(c.get("words") for c in candidates):
            merged_words = _merge_words(candidates)
            if merged_words:
                best_seg = dict(best_seg)
                best_seg["words"] = merged_words
                best_seg["text"] = "".join(w["word"] for w in merged_words).strip()

        merged.append(best_seg)

    # Re-number segments
    for i, seg in enumerate(merged):
        seg["id"] = i

    return merged


def _merge_words(candidates: list) -> list:
    """Word-level consensus merge across multiple transcription passes.

    For each word position, pick the word with highest confidence.
    Uses alignment to handle cases where passes have different word counts.
    """
    # Use the candidate with the most words as the reference
    ref = max(candidates, key=lambda c: len(c.get("words", [])))
    ref_words = ref.get("words", [])

    if not ref_words:
        return []

    # For each word in the reference, check if other passes have a
    # higher-confidence version at a similar timestamp
    merged = []
    for ref_word in ref_words:
        best_word = ref_word
        best_conf = _word_confidence(ref_word)

        for candidate in candidates:
            if candidate is ref:
                continue
            for cand_word in candidate.get("words", []):
                # Check if this word covers a similar time range
                time_diff = abs(cand_word["start"] - ref_word["start"])
                if time_diff < 0.5:
                    cand_conf = _word_confidence(cand_word)
                    if cand_conf > best_conf:
                        best_word = cand_word
                        best_conf = cand_conf

        merged.append(best_word)

    return merged


def transcribe_audio(audio_path: str, model_size: str = "large-v3",
                     quality: str = "standard", on_progress=None) -> dict:
    """Transcribe audio with configurable quality.

    Quality levels:
      fast:     1 pass, base model
      standard: 1 pass, large-v3
      high:     3 passes, large-v3, consensus merge
    """
    from faster_whisper import WhisperModel

    actual_model = model_size
    if quality == "fast":
        actual_model = "base"
    elif quality in ("standard", "high"):
        actual_model = "large-v3"

    if on_progress:
        on_progress("loading", 0, f"Loading Whisper {actual_model} model...")

    model = WhisperModel(actual_model, device="cpu", compute_type="int8")

    if quality == "high":
        # Multi-pass transcription
        all_pass_segments = []
        num_passes = len(PASS_CONFIGS)

        for pass_idx, config in enumerate(PASS_CONFIGS):
            pass_name = config["name"]

            if on_progress:
                on_progress("transcribing", 0,
                    f"Pass {pass_idx + 1}/{num_passes} ({pass_name})...")

            def pass_progress(time_done, duration, seg_count):
                if on_progress:
                    # Map progress: each pass gets an equal share
                    pass_share = 70 / num_passes
                    base_pct = 15 + (pass_idx * pass_share)
                    pct = base_pct + (time_done / duration) * pass_share
                    t_done = f"{int(time_done // 60)}:{int(time_done % 60):02d}"
                    t_total = f"{int(duration // 60)}:{int(duration % 60):02d}"
                    on_progress("transcribing", pct,
                        f"Pass {pass_idx + 1}/{num_passes} ({pass_name}): "
                        f"{t_done}/{t_total} ({seg_count} segments)")

            segments, info = _run_single_pass(model, audio_path, config, pass_progress)
            all_pass_segments.append(segments)

        if on_progress:
            on_progress("merging", 88, "Merging passes with confidence voting...")

        merged_segments = _align_and_merge_segments(all_pass_segments)
        raw_text = " ".join(seg["text"] for seg in merged_segments)

        return {
            "segments": merged_segments,
            "raw_text": raw_text,
            "language": info.language,
            "duration": info.duration,
            "quality": quality,
            "passes": num_passes,
        }
    else:
        # Single pass
        config = PASS_CONFIGS[0]  # precise config

        def single_progress(time_done, duration, seg_count):
            if on_progress:
                pct = 15 + (time_done / duration) * 75
                t_done = f"{int(time_done // 60)}:{int(time_done % 60):02d}"
                t_total = f"{int(duration // 60)}:{int(duration % 60):02d}"
                on_progress("transcribing", pct,
                    f"Transcribing... {t_done}/{t_total} ({seg_count} segments)")

        segments, info = _run_single_pass(model, audio_path, config, single_progress)
        raw_text = " ".join(seg["text"] for seg in segments)

        return {
            "segments": segments,
            "raw_text": raw_text,
            "language": info.language,
            "duration": info.duration,
            "quality": quality,
            "passes": 1,
        }


def save_transcript(transcript_data: dict, output_path: str):
    """Save transcript data to JSON."""
    with open(output_path, "w") as f:
        json.dump(transcript_data, f, indent=2)


def load_transcript(path: str) -> dict:
    """Load transcript data from JSON."""
    with open(path, "r") as f:
        return json.load(f)
