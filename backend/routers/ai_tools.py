"""API router for AI-powered tools.

Tier 1 (CPU): upscale, background removal, scene detection, audio enhancement
Tier 2 (GPU): video generation, TTS/voice cloning, music generation, thumbnails
"""

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from ..services import task_manager as tm
from ..services.tool_availability import check_tool
from ..services.project_utils import get_project_dir as _get_project_dir, find_video as _find_video, PROJECTS_DIR

router = APIRouter(prefix="/api/ai", tags=["ai-tools"])


# ===== TIER 1: CPU-FRIENDLY =====

# --- Upscale ---

def _do_upscale(task_id: str, project_dir: Path, scale: int):
    from ..services.upscale_service import upscale_video
    video = _find_video(project_dir)
    output = project_dir / "processing" / f"upscaled_{scale}x.mp4"
    return upscale_video(
        str(video), str(output), scale=scale,
        on_progress=lambda p, m: tm.update_task(task_id, progress=p, message=m),
    )


@router.post("/upscale")
async def upscale(payload: dict):
    """Upscale video resolution (2x or 4x). Background task."""
    project_dir = _get_project_dir(payload["project_name"])
    scale = payload.get("scale", 2)

    existing = tm.get_active_task(payload["project_name"], "upscale")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(payload["project_name"], "upscale")
    tm.run_in_background(task_id, _do_upscale, project_dir, scale)
    return tm.task_to_dict(tm.get_task(task_id))


# --- Background removal ---

def _do_remove_bg(task_id: str, project_dir: Path, bg_color: str, model: str):
    from ..services.background_removal_service import remove_background_video
    video = _find_video(project_dir)
    output = project_dir / "processing" / "no_background.mp4"
    return remove_background_video(
        str(video), str(output), model=model, bg_color=bg_color,
        on_progress=lambda p, m: tm.update_task(task_id, progress=p, message=m),
    )


@router.post("/remove-background")
async def remove_bg(payload: dict):
    """Remove video background. Background task."""
    project_dir = _get_project_dir(payload["project_name"])

    if not check_tool("rembg"):
        raise HTTPException(400, "rembg not installed. pip install rembg")

    bg_color = payload.get("bg_color", "#00FF00")
    model = payload.get("model", "u2net")

    existing = tm.get_active_task(payload["project_name"], "remove_bg")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(payload["project_name"], "remove_bg")
    tm.run_in_background(task_id, _do_remove_bg, project_dir, bg_color, model)
    return tm.task_to_dict(tm.get_task(task_id))


# --- Scene detection ---

@router.post("/detect-scenes")
async def detect_scenes(payload: dict):
    """Detect scene boundaries and generate chapter markers."""
    project_dir = _get_project_dir(payload["project_name"])

    if not check_tool("scenedetect"):
        raise HTTPException(400, "PySceneDetect not installed. pip install scenedetect[opencv]")

    from ..services.scene_detect_service import detect_and_generate_chapters

    video = _find_video(project_dir)
    threshold = payload.get("threshold", 27.0)
    result = detect_and_generate_chapters(
        str(video), str(project_dir), threshold=threshold,
    )
    return result


# --- Audio enhancement ---

def _do_enhance_audio(task_id: str, project_dir: Path):
    from ..services.audio_enhance_service import enhance_video_audio
    video = _find_video(project_dir)
    output = project_dir / "processing" / "enhanced_audio.mp4"
    return enhance_video_audio(
        str(video), str(output),
        on_progress=lambda p, m: tm.update_task(task_id, progress=p, message=m),
    )


@router.post("/enhance-audio")
async def enhance_audio(payload: dict):
    """Enhance video audio — denoise and normalize. Background task."""
    project_dir = _get_project_dir(payload["project_name"])

    existing = tm.get_active_task(payload["project_name"], "enhance_audio")
    if existing:
        return tm.task_to_dict(existing)

    task_id = tm.create_task(payload["project_name"], "enhance_audio")
    tm.run_in_background(task_id, _do_enhance_audio, project_dir)
    return tm.task_to_dict(tm.get_task(task_id))


# --- Thumbnails ---

@router.post("/thumbnails")
async def generate_thumbnails(payload: dict):
    """Extract candidate thumbnails from video."""
    project_dir = _get_project_dir(payload["project_name"])
    count = payload.get("count", 5)

    from ..services.thumbnail_service import generate_project_thumbnails

    video = _find_video(project_dir)
    return generate_project_thumbnails(str(video), str(project_dir), count=count)


@router.get("/thumbnails/{project_name}")
async def list_thumbnails(project_name: str):
    """List available thumbnail candidates."""
    project_dir = _get_project_dir(project_name)
    thumb_dir = project_dir / "exports" / "thumbnails"
    if not thumb_dir.exists():
        return []
    return [
        {"filename": f.name, "path": str(f)}
        for f in sorted(thumb_dir.glob("*.jpg"))
    ]


# ===== TIER 2: GPU TOOLS =====

# --- Video generation (LTX-2) ---

def _do_generate_video(task_id: str, project_dir: Path, prompt: str,
                       duration: float, width: int, height: int):
    from ..services.video_gen_service import generate_video
    output = project_dir / "processing" / "broll" / "generated.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)
    return generate_video(
        prompt, str(output), duration=duration, width=width, height=height,
        on_progress=lambda p, m: tm.update_task(task_id, progress=p, message=m),
    )


@router.post("/generate-video")
async def gen_video(payload: dict):
    """Generate a video clip from text prompt (LTX-2). Background task."""
    project_dir = _get_project_dir(payload["project_name"])

    if not check_tool("ltx_video"):
        raise HTTPException(400,
            "LTX-2 not installed. pip install ltx-pipelines  or  pip install diffusers transformers accelerate")

    prompt = payload.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "Prompt is required")

    duration = payload.get("duration", 6.0)
    width = payload.get("width", 768)
    height = payload.get("height", 512)

    task_id = tm.create_task(payload["project_name"], "generate_video")
    tm.run_in_background(task_id, _do_generate_video, project_dir,
                         prompt, duration, width, height)
    return tm.task_to_dict(tm.get_task(task_id))


# --- B-roll generation ---

@router.post("/generate-broll")
async def gen_broll(payload: dict):
    """Generate multiple B-roll clips from a prompt. Background task."""
    project_dir = _get_project_dir(payload["project_name"])

    if not check_tool("ltx_video"):
        raise HTTPException(400, "LTX-2 not installed")

    def _do(task_id, project_dir, prompt, duration, count):
        from ..services.video_gen_service import generate_broll
        return generate_broll(
            prompt, str(project_dir), duration=duration, count=count,
            on_progress=lambda p, m: tm.update_task(task_id, progress=p, message=m),
        )

    prompt = payload.get("prompt", "")
    duration = payload.get("duration", 6.0)
    count = payload.get("count", 3)

    task_id = tm.create_task(payload["project_name"], "generate_broll")
    tm.run_in_background(task_id, _do, project_dir, prompt, duration, count)
    return tm.task_to_dict(tm.get_task(task_id))


# --- Text-to-speech / Voice cloning ---

def _do_tts(task_id: str, project_dir: Path, text: str,
            language: str, speaker_wav: str):
    from ..services.tts_service import generate_voiceover
    return generate_voiceover(
        text, str(project_dir),
        speaker_wav=speaker_wav, language=language,
        on_progress=lambda p, m: tm.update_task(task_id, progress=p, message=m),
    )


@router.post("/text-to-speech")
async def tts(payload: dict):
    """Generate voiceover from text. Background task."""
    project_dir = _get_project_dir(payload["project_name"])

    if not check_tool("coqui_tts"):
        raise HTTPException(400, "Coqui TTS not installed. pip install TTS")

    text = payload.get("text", "")
    if not text:
        raise HTTPException(400, "Text is required")

    language = payload.get("language", "en")
    speaker_wav = payload.get("speaker_wav")

    task_id = tm.create_task(payload["project_name"], "tts")
    tm.run_in_background(task_id, _do_tts, project_dir, text, language, speaker_wav)
    return tm.task_to_dict(tm.get_task(task_id))


# --- Music generation ---

def _do_music(task_id: str, project_dir: Path, prompt: str,
              duration: float, model_size: str):
    from ..services.music_gen_service import generate_background_music
    return generate_background_music(
        prompt, str(project_dir), duration=duration,
        on_progress=lambda p, m: tm.update_task(task_id, progress=p, message=m),
    )


@router.post("/generate-music")
async def gen_music(payload: dict):
    """Generate background music from text prompt. Background task."""
    project_dir = _get_project_dir(payload["project_name"])

    if not check_tool("musicgen"):
        raise HTTPException(400, "MusicGen not installed. pip install audiocraft")

    prompt = payload.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "Prompt is required")

    duration = payload.get("duration", 30.0)
    model_size = payload.get("model_size", "small")

    task_id = tm.create_task(payload["project_name"], "generate_music")
    tm.run_in_background(task_id, _do_music, project_dir, prompt,
                         duration, model_size)
    return tm.task_to_dict(tm.get_task(task_id))


# --- Mix music into video ---

@router.post("/mix-music")
async def mix_music(payload: dict):
    """Mix generated background music with video audio."""
    project_dir = _get_project_dir(payload["project_name"])

    from ..services.music_gen_service import mix_audio_with_music

    video = _find_video(project_dir)
    music = project_dir / "processing" / "background_music.wav"
    if not music.exists():
        raise HTTPException(404, "No background music found. Generate music first.")

    output = project_dir / "processing" / "with_music.mp4"
    volume = payload.get("volume", 0.15)

    result = mix_audio_with_music(str(video), str(music), str(output),
                                  music_volume=volume)
    return result


# --- AI thumbnail generation ---

@router.post("/ai-thumbnail")
async def ai_thumbnail(payload: dict):
    """Generate a thumbnail using AI image generation (Stable Diffusion)."""
    project_dir = _get_project_dir(payload["project_name"])

    if not check_tool("diffusers") or not check_tool("torch_gpu"):
        raise HTTPException(400,
            "AI thumbnail generation requires diffusers + CUDA GPU")

    from ..services.thumbnail_service import generate_ai_thumbnail

    prompt = payload.get("prompt", "")
    if not prompt:
        raise HTTPException(400, "Prompt is required")

    output = project_dir / "exports" / "thumbnails" / "ai_thumb.jpg"
    output.parent.mkdir(parents=True, exist_ok=True)

    result = generate_ai_thumbnail(prompt, str(output))
    return result
