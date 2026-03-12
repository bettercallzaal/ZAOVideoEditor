"""Speaker diarization using pyannote.audio + faster-whisper alignment.

Identifies which speaker is talking for each transcript segment.
Runs locally — requires a one-time Hugging Face token for model download,
but after that works fully offline.

Falls back to a simple energy-based approach if pyannote is not available.
"""

import json
import subprocess
from pathlib import Path
from collections import Counter


def diarize_audio(audio_path: str, num_speakers: int = None,
                  on_progress=None) -> list:
    """Run speaker diarization on an audio file.

    Returns list of speaker turns:
    [{"start": 0.0, "end": 5.2, "speaker": "SPEAKER_0"}, ...]
    """
    try:
        return _diarize_pyannote(audio_path, num_speakers, on_progress)
    except ImportError:
        if on_progress:
            on_progress("fallback", 10, "pyannote not available, using energy-based diarization...")
        return _diarize_energy_based(audio_path, on_progress)


def _diarize_pyannote(audio_path: str, num_speakers: int = None,
                      on_progress=None) -> list:
    """Diarize using pyannote.audio pipeline."""
    from pyannote.audio import Pipeline
    import torch

    if on_progress:
        on_progress("loading", 5, "Loading speaker diarization model...")

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
    )

    # Use MPS on Apple Silicon if available, else CPU
    device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
    pipeline.to(device)

    if on_progress:
        on_progress("diarizing", 20, "Running speaker diarization...")

    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = num_speakers

    diarization = pipeline(audio_path, **kwargs)

    turns = []
    for turn, _, speaker in diarization.itertracks(yield_label=True):
        turns.append({
            "start": round(turn.start, 3),
            "end": round(turn.end, 3),
            "speaker": speaker,
        })

    if on_progress:
        speakers = set(t["speaker"] for t in turns)
        on_progress("complete", 95, f"Found {len(speakers)} speakers, {len(turns)} turns")

    return turns


def _diarize_energy_based(audio_path: str, on_progress=None) -> list:
    """Simple fallback: use ffmpeg silence detection to estimate speaker turns.

    This won't identify WHO is speaking but will segment into turns
    based on pauses, which we can then label as alternating speakers.
    """
    if on_progress:
        on_progress("analyzing", 20, "Detecting speech segments via silence detection...")

    # Use ffmpeg silencedetect
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    info = json.loads(result.stdout)
    duration = float(info["format"]["duration"])

    # Detect silences
    cmd = [
        "ffmpeg", "-i", audio_path,
        "-af", "silencedetect=noise=-30dB:d=0.8",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    stderr = result.stderr

    # Parse silence boundaries
    import re
    silence_starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", stderr)]
    silence_ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", stderr)]

    # Build speech segments from silence gaps
    speech_segments = []
    last_end = 0.0

    for i, s_start in enumerate(silence_starts):
        if s_start > last_end + 0.3:  # Min speech duration
            speech_segments.append({"start": last_end, "end": s_start})
        if i < len(silence_ends):
            last_end = silence_ends[i]

    # Add final segment
    if last_end < duration - 0.3:
        speech_segments.append({"start": last_end, "end": duration})

    # Assign alternating speakers based on gaps
    turns = []
    current_speaker = "SPEAKER_0"
    for i, seg in enumerate(speech_segments):
        # Switch speaker on longer pauses (likely speaker change)
        if i > 0:
            gap = seg["start"] - speech_segments[i - 1]["end"]
            if gap > 1.5:
                current_speaker = "SPEAKER_1" if current_speaker == "SPEAKER_0" else "SPEAKER_0"

        turns.append({
            "start": round(seg["start"], 3),
            "end": round(seg["end"], 3),
            "speaker": current_speaker,
        })

    if on_progress:
        speakers = set(t["speaker"] for t in turns)
        on_progress("complete", 95, f"Found {len(speakers)} speakers (estimated), {len(turns)} turns")

    return turns


def assign_speakers_to_segments(segments: list, speaker_turns: list) -> list:
    """Map speaker labels onto transcript segments based on time overlap.

    For each segment, find which speaker turn has the most overlap
    and assign that speaker label.
    """
    labeled = []
    for seg in segments:
        seg_start = seg["start"]
        seg_end = seg["end"]
        seg_duration = seg_end - seg_start

        # Find overlapping speaker turns
        speaker_overlap = Counter()
        for turn in speaker_turns:
            overlap_start = max(seg_start, turn["start"])
            overlap_end = min(seg_end, turn["end"])
            overlap = max(0, overlap_end - overlap_start)
            if overlap > 0:
                speaker_overlap[turn["speaker"]] += overlap

        # Assign the speaker with most overlap
        new_seg = dict(seg)
        if speaker_overlap:
            new_seg["speaker"] = speaker_overlap.most_common(1)[0][0]
        else:
            new_seg["speaker"] = "UNKNOWN"

        labeled.append(new_seg)

    return labeled


def rename_speakers(segments: list, speaker_map: dict) -> list:
    """Rename speaker labels (e.g., SPEAKER_0 -> "Host", SPEAKER_1 -> "Guest")."""
    renamed = []
    for seg in segments:
        new_seg = dict(seg)
        speaker = seg.get("speaker", "UNKNOWN")
        new_seg["speaker"] = speaker_map.get(speaker, speaker)
        renamed.append(new_seg)
    return renamed
