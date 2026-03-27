"""Batch processing endpoint — queue multiple projects for sequential processing."""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..services import task_manager as tm
from ..services.ffmpeg_service import get_video_params, assemble_videos, extract_audio
from ..services.whisper_service import transcribe_audio, save_transcript, load_transcript
from ..services.dictionary import apply_corrections_to_segments

router = APIRouter(prefix="/api/batch", tags=["batch"])

PROJECTS_DIR = Path(__file__).parent.parent.parent / "projects"


class BatchRequest(BaseModel):
    project_names: list[str]
    quality: str = "standard"
    engine: str = "auto"
    refine_timestamps: bool = True
    use_intro: bool = False
    use_outro: bool = False
    generate_content: bool = True


def _do_batch_process(task_id: str, project_names: list[str], quality: str,
                      engine: str, refine_timestamps: bool, use_intro: bool,
                      use_outro: bool, gen_content: bool):
    """Background batch processing worker."""
    total = len(project_names)
    results = []

    for idx, project_name in enumerate(project_names):
        project_dir = PROJECTS_DIR / project_name
        if not project_dir.exists():
            results.append({"project": project_name, "status": "error", "error": "Not found"})
            continue

        base_pct = int((idx / total) * 100)
        step_pct = int(100 / total)

        try:
            # --- Step 1: Assemble ---
            tm.update_task(
                task_id,
                progress=base_pct + int(step_pct * 0.05),
                message=f"[{idx + 1}/{total}] {project_name}: Assembling...",
            )

            import shutil

            main_video = None
            for ext in [".mp4", ".mov", ".mkv", ".webm"]:
                p = project_dir / "input" / f"main{ext}"
                if p.exists():
                    main_video = p
                    break

            if not main_video:
                results.append({"project": project_name, "status": "error", "error": "No video file"})
                continue

            output_path = project_dir / "processing" / "assembled.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            parts = []
            if use_intro:
                for ext in [".mp4", ".mov", ".mkv", ".webm"]:
                    candidate = project_dir / "input" / f"intro{ext}"
                    if candidate.exists():
                        parts.append(str(candidate))
                        break
            parts.append(str(main_video))
            if use_outro:
                for ext in [".mp4", ".mov", ".mkv", ".webm"]:
                    candidate = project_dir / "input" / f"outro{ext}"
                    if candidate.exists():
                        parts.append(str(candidate))
                        break

            if len(parts) == 1:
                shutil.copy2(parts[0], str(output_path))
            else:
                main_params = get_video_params(str(main_video))
                assemble_videos(parts, str(output_path), main_params)

            # Extract audio
            tm.update_task(
                task_id,
                progress=base_pct + int(step_pct * 0.15),
                message=f"[{idx + 1}/{total}] {project_name}: Extracting audio...",
            )
            audio_path = project_dir / "processing" / "audio.wav"
            extract_audio(str(output_path), str(audio_path))

            # --- Step 2: Transcribe ---
            tm.update_task(
                task_id,
                progress=base_pct + int(step_pct * 0.20),
                message=f"[{idx + 1}/{total}] {project_name}: Transcribing ({quality})...",
            )

            actual_engine = _resolve_engine(engine)

            if actual_engine == "whisperx":
                from ..services.whisperx_service import transcribe_audio_whisperx
                transcript_data = transcribe_audio_whisperx(
                    str(audio_path),
                    quality=quality,
                    on_progress=lambda p, m: tm.update_task(
                        task_id,
                        progress=base_pct + int(step_pct * (0.20 + p * 0.45)),
                        message=f"[{idx + 1}/{total}] {project_name}: {m}",
                    ),
                )
            else:
                transcript_data = transcribe_audio(
                    str(audio_path),
                    model_size=quality,
                    quality=quality,
                    on_progress=lambda step, pct, msg: tm.update_task(
                        task_id,
                        progress=base_pct + int(step_pct * (0.20 + (pct / 100) * 0.45)),
                        message=f"[{idx + 1}/{total}] {project_name}: {msg}",
                    ),
                )

            # Optional timestamp refinement
            if refine_timestamps:
                try:
                    from ..services.tool_availability import check_tool
                    if check_tool("stable_ts"):
                        tm.update_task(
                            task_id,
                            progress=base_pct + int(step_pct * 0.70),
                            message=f"[{idx + 1}/{total}] {project_name}: Refining timestamps...",
                        )
                        from ..services.stable_ts_service import refine_timestamps as refine_ts
                        transcript_data["segments"] = refine_ts(
                            str(audio_path), transcript_data["segments"],
                        )
                        transcript_data["timestamp_refined"] = True
                except Exception:
                    pass

            # Save raw transcript
            (project_dir / "transcripts").mkdir(parents=True, exist_ok=True)
            raw_path = project_dir / "transcripts" / "raw.json"
            save_transcript(transcript_data, str(raw_path))

            raw_text_path = project_dir / "transcripts" / "raw.txt"
            with open(raw_text_path, "w") as f:
                f.write(transcript_data.get("raw_text", ""))

            # --- Step 3: Dictionary correction ---
            tm.update_task(
                task_id,
                progress=base_pct + int(step_pct * 0.75),
                message=f"[{idx + 1}/{total}] {project_name}: Applying dictionary corrections...",
            )

            corrected_segments = apply_corrections_to_segments(transcript_data["segments"])
            corrected_data = {
                "segments": corrected_segments,
                "raw_text": " ".join(seg["text"] for seg in corrected_segments),
            }
            save_transcript(corrected_data, str(project_dir / "transcripts" / "corrected.json"))

            # --- Step 4: Generate content (optional) ---
            if gen_content:
                tm.update_task(
                    task_id,
                    progress=base_pct + int(step_pct * 0.80),
                    message=f"[{idx + 1}/{total}] {project_name}: Generating content...",
                )
                try:
                    from ..services.content_gen import generate_recap_and_clips
                    content_result = generate_recap_and_clips(
                        corrected_segments,
                        project_name=project_name,
                    )
                    content_path = project_dir / "metadata" / "content.json"
                    content_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(content_path, "w") as f:
                        json.dump(content_result, f, indent=2)
                except Exception as e:
                    # Content generation is non-fatal
                    print(f"Batch: content generation failed for {project_name}: {e}")

            results.append({
                "project": project_name,
                "status": "complete",
                "segments": len(transcript_data["segments"]),
                "language": transcript_data.get("language", "unknown"),
            })

        except Exception as e:
            import traceback
            traceback.print_exc()
            results.append({"project": project_name, "status": "error", "error": str(e)})

    return {
        "processed": len([r for r in results if r["status"] == "complete"]),
        "failed": len([r for r in results if r["status"] == "error"]),
        "results": results,
    }


def _resolve_engine(engine: str) -> str:
    """Resolve 'auto' engine to best available."""
    from ..services.tool_availability import check_tool
    if engine == "auto":
        return "whisperx" if check_tool("whisperx") else "faster-whisper"
    elif engine == "whisperx":
        return "whisperx" if check_tool("whisperx") else "faster-whisper"
    return "faster-whisper"


@router.post("/process")
async def batch_process(req: BatchRequest):
    """Queue multiple projects for sequential processing."""
    if not req.project_names:
        raise HTTPException(400, "No projects specified")

    # Validate all projects exist
    missing = [n for n in req.project_names if not (PROJECTS_DIR / n).exists()]
    if missing:
        raise HTTPException(404, f"Projects not found: {', '.join(missing)}")

    # Check for existing batch task
    existing = tm.get_active_task("__batch__", "batch_process")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task("__batch__", "batch_process")
    tm.run_in_background(
        task_id, _do_batch_process,
        req.project_names, req.quality, req.engine,
        req.refine_timestamps, req.use_intro, req.use_outro,
        req.generate_content,
    )
    return tm.task_to_dict(tm.get_task(task_id))


@router.get("/status")
async def batch_status():
    """Get the status of the current batch task, if any."""
    task = tm.get_active_task("__batch__", "batch_process")
    if not task:
        # Check for most recently completed batch task
        all_batch = [
            t for t in tm.get_project_tasks("__batch__")
            if t.operation == "batch_process"
        ]
        if all_batch:
            task = max(all_batch, key=lambda t: t.started_at)
        else:
            return {"status": "idle"}
    return tm.task_to_dict(task)
