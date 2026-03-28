"""Quick Process pipeline — run the entire video processing pipeline in one click."""

import json
import shutil
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services import task_manager as tm
from ..services.ffmpeg_service import get_video_params, assemble_videos, extract_audio
from ..services.whisper_service import transcribe_audio, save_transcript
from ..services.dictionary import apply_corrections_to_segments

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


class QuickProcessRequest(BaseModel):
    project_name: str
    quality: str = "standard"
    engine: str = "auto"
    style: str = "classic"


def _resolve_engine(engine: str) -> str:
    """Resolve 'auto' engine to best available."""
    from ..services.tool_availability import check_tool
    if engine == "auto":
        return "whisperx" if check_tool("whisperx") else "faster-whisper"
    elif engine == "whisperx":
        return "whisperx" if check_tool("whisperx") else "faster-whisper"
    elif engine == "groq":
        return "groq" if check_tool("groq") else "faster-whisper"
    return "faster-whisper"


def _do_quick_process(task_id: str, project_dir: Path, project_name: str,
                      quality: str, engine: str, style: str):
    """Background worker that runs the full pipeline sequentially."""

    # ---- Step 1: Assemble video + extract audio (0-15%) ----
    tm.update_task(task_id, progress=0, message="Assembling video...")

    main_video = None
    for ext in [".mp4", ".mov", ".mkv", ".webm"]:
        p = project_dir / "input" / f"main{ext}"
        if p.exists():
            main_video = p
            break

    if not main_video:
        raise RuntimeError("No main video found. Upload a video first.")

    output_path = project_dir / "processing" / "assembled.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Check for intro/outro
    parts = []
    for ext in [".mp4", ".mov", ".mkv", ".webm"]:
        candidate = project_dir / "input" / f"intro{ext}"
        if candidate.exists():
            parts.append(str(candidate))
            break
    parts.append(str(main_video))
    for ext in [".mp4", ".mov", ".mkv", ".webm"]:
        candidate = project_dir / "input" / f"outro{ext}"
        if candidate.exists():
            parts.append(str(candidate))
            break

    if len(parts) == 1:
        tm.update_task(task_id, progress=5, message="Copying video...")
        shutil.copy2(parts[0], str(output_path))
    else:
        tm.update_task(task_id, progress=3, message=f"Assembling {len(parts)} video parts...")
        main_params = get_video_params(str(main_video))
        assemble_videos(parts, str(output_path), main_params)

    tm.update_task(task_id, progress=10, message="Extracting audio...")
    audio_path = project_dir / "processing" / "audio.wav"
    extract_audio(str(output_path), str(audio_path))

    tm.update_task(task_id, progress=15, message="Audio extracted.")

    # ---- Step 2: Transcribe (15-25%) ----
    tm.update_task(task_id, progress=15, message=f"Transcribing ({quality})...")

    actual_engine = _resolve_engine(engine)

    if actual_engine == "groq":
        from ..services.groq_service import transcribe_audio_groq
        transcript_data = transcribe_audio_groq(
            str(audio_path),
            on_progress=lambda pct, msg: tm.update_task(
                task_id, progress=15 + int(pct * 0.10), message=msg,
            ),
        )
    elif actual_engine == "whisperx":
        from ..services.whisperx_service import transcribe_audio_whisperx
        transcript_data = transcribe_audio_whisperx(
            str(audio_path),
            quality=quality,
            on_progress=lambda p, m: tm.update_task(
                task_id, progress=15 + int(p * 10), message=m,
            ),
        )
    else:
        transcript_data = transcribe_audio(
            str(audio_path),
            model_size=quality,
            quality=quality,
            on_progress=lambda step, pct, msg: tm.update_task(
                task_id, progress=15 + int((pct / 100) * 10), message=msg,
            ),
        )

    # Save raw transcript
    (project_dir / "transcripts").mkdir(parents=True, exist_ok=True)
    raw_path = project_dir / "transcripts" / "raw.json"
    save_transcript(transcript_data, str(raw_path))

    raw_text_path = project_dir / "transcripts" / "raw.txt"
    with open(raw_text_path, "w") as f:
        f.write(transcript_data.get("raw_text", ""))

    tm.update_task(task_id, progress=25, message="Transcription complete.")

    # ---- Step 3: Dictionary correct (25-35%) ----
    tm.update_task(task_id, progress=25, message="Applying dictionary corrections...")

    corrected_segments = apply_corrections_to_segments(transcript_data["segments"])
    corrected_data = {
        "segments": corrected_segments,
        "raw_text": " ".join(seg["text"] for seg in corrected_segments),
    }
    save_transcript(corrected_data, str(project_dir / "transcripts" / "corrected.json"))

    tm.update_task(task_id, progress=35, message="Dictionary corrections applied.")

    # ---- Step 4: LLM polish (35-50%) — non-fatal ----
    polished_segments = corrected_segments
    try:
        tm.update_task(task_id, progress=35, message="AI polishing transcript...")
        from ..services.content_gen import polish_transcript
        from ..services.dictionary import load_dictionary

        dict_data = load_dictionary()
        dict_terms = list(dict_data.get("corrections", {}).values())
        polished_segments = polish_transcript(corrected_segments, dictionary_terms=dict_terms)

        polished_data = {
            "segments": polished_segments,
            "raw_text": " ".join(seg["text"] for seg in polished_segments),
        }
        save_transcript(polished_data, str(project_dir / "transcripts" / "edited.json"))
        tm.update_task(task_id, progress=50, message="AI polish complete.")
    except Exception as e:
        print(f"Quick process: LLM polish skipped: {e}")
        # Save corrected as edited so downstream steps have a file
        save_transcript(corrected_data, str(project_dir / "transcripts" / "edited.json"))
        tm.update_task(task_id, progress=50, message="AI polish skipped (no LLM available).")

    # ---- Step 5: Generate content (50-65%) — non-fatal ----
    try:
        tm.update_task(task_id, progress=50, message="Generating content (recap + clips)...")
        from ..services.content_gen import generate_recap_and_clips

        content_result = generate_recap_and_clips(
            polished_segments,
            project_name=project_name,
        )
        content_path = project_dir / "metadata" / "content.json"
        content_path.parent.mkdir(parents=True, exist_ok=True)
        with open(content_path, "w") as f:
            json.dump(content_result, f, indent=2)
        tm.update_task(task_id, progress=65, message="Content generation complete.")
    except Exception as e:
        print(f"Quick process: content generation skipped: {e}")
        tm.update_task(task_id, progress=65, message="Content generation skipped (no LLM available).")

    # ---- Step 6: Generate captions (65-80%) ----
    tm.update_task(task_id, progress=65, message="Generating captions...")

    from ..services.caption_gen import (
        generate_captions_from_segments, save_captions,
        generate_srt, generate_ass,
    )

    captions = generate_captions_from_segments(polished_segments, style=style)
    captions_dir = project_dir / "captions"
    captions_dir.mkdir(parents=True, exist_ok=True)
    save_captions(captions, str(captions_dir / "captions.json"))

    srt_content = generate_srt(captions, style=style)
    with open(captions_dir / "captions.srt", "w") as f:
        f.write(srt_content)

    video_path = project_dir / "processing" / "assembled.mp4"
    params = get_video_params(str(video_path))
    ass_content = generate_ass(
        captions, style=style,
        video_width=params.get("width", 1920),
        video_height=params.get("height", 1080),
    )
    with open(captions_dir / "captions.ass", "w") as f:
        f.write(ass_content)

    tm.update_task(task_id, progress=80, message=f"Captions generated ({len(captions)} lines).")

    # ---- Step 7: Generate metadata (80-95%) ----
    tm.update_task(task_id, progress=80, message="Generating metadata...")

    from ..services.metadata_gen import generate_description, generate_chapters, generate_tags

    description = generate_description(polished_segments, project_name)
    chapters = generate_chapters(polished_segments)
    tags = generate_tags(polished_segments, project_name)

    metadata_dir = project_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    with open(metadata_dir / "description.txt", "w") as f:
        f.write(description)
    with open(metadata_dir / "chapters.txt", "w") as f:
        f.write(chapters)
    with open(metadata_dir / "tags.txt", "w") as f:
        f.write(tags)

    tm.update_task(task_id, progress=95, message="Metadata generated.")

    # ---- Done (95-100%) ----
    tm.update_task(task_id, progress=100, message="Pipeline complete!")

    return {
        "segments": len(transcript_data["segments"]),
        "language": transcript_data.get("language", "unknown"),
        "captions": len(captions),
        "engine": actual_engine,
        "style": style,
    }


@router.post("/quick-process")
async def quick_process(req: QuickProcessRequest):
    """Run the full processing pipeline in one shot."""
    project_dir = PROJECTS_DIR / req.project_name
    if not project_dir.exists():
        raise HTTPException(404, "Project not found")

    # Check for existing pipeline task
    existing = tm.get_active_task(req.project_name, "quick_process")
    if existing:
        return tm.task_to_dict(existing)

    # Validate quality
    quality = req.quality
    if quality not in ("fast", "standard", "high"):
        quality = "standard"

    task_id = tm.create_task(req.project_name, "quick_process")
    tm.run_in_background(
        task_id, _do_quick_process,
        project_dir, req.project_name, quality, req.engine, req.style,
    )
    return tm.task_to_dict(tm.get_task(task_id))
