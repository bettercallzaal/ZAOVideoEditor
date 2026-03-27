"""Check which optional tools are installed. Results cached at startup."""

import os

_cache = {}


_NO_CACHE_TOOLS = {"groq"}  # env-var based checks should not be cached


def check_tool(name: str) -> bool:
    if name not in _NO_CACHE_TOOLS and name in _cache:
        return _cache[name]

    available = False
    try:
        if name == "whisperx":
            import whisperx  # noqa: F401
            available = True
        elif name == "stable_ts":
            import stable_whisper  # noqa: F401
            available = True
        elif name == "auto_editor":
            import subprocess
            result = subprocess.run(
                ["auto-editor", "--help"],
                capture_output=True, timeout=5,
            )
            available = result.returncode == 0
        elif name == "pycaps":
            import pycaps  # noqa: F401
            available = True
        elif name == "moviepy":
            from moviepy import VideoFileClip  # noqa: F401
            available = True

        # --- Tier 1: CPU-friendly tools ---
        elif name == "realesrgan":
            import subprocess
            result = subprocess.run(
                ["realesrgan-ncnn-vulkan", "-h"],
                capture_output=True, timeout=5,
            )
            available = result.returncode == 0
        elif name == "rembg":
            import rembg  # noqa: F401
            available = True
        elif name == "scenedetect":
            import scenedetect  # noqa: F401
            available = True
        elif name == "denoiser":
            import denoiser  # noqa: F401
            available = True

        # --- Tier 2: GPU tools ---
        elif name == "ltx_video":
            try:
                from ltx_pipelines.text_to_video import TextToVideoPipeline  # noqa: F401
                available = True
            except ImportError:
                # Try diffusers fallback
                from diffusers import LTXPipeline  # noqa: F401
                available = True
        elif name == "coqui_tts":
            from TTS.api import TTS  # noqa: F401
            available = True
        elif name == "musicgen":
            from audiocraft.models import MusicGen  # noqa: F401
            available = True
        elif name == "diffusers":
            import diffusers  # noqa: F401
            available = True
        elif name == "torch_gpu":
            import torch
            available = torch.cuda.is_available()
        elif name == "groq":
            available = bool(os.environ.get("GROQ_API_KEY", "").strip())
    except Exception:
        pass

    _cache[name] = available
    return available


def get_available_tools() -> dict:
    """Return availability of all optional tools, grouped by tier."""
    # Original pipeline tools
    pipeline = ["whisperx", "stable_ts", "auto_editor", "pycaps", "moviepy", "groq"]

    # Tier 1: CPU-friendly
    tier1 = ["realesrgan", "rembg", "scenedetect", "denoiser"]

    # Tier 2: GPU tools
    tier2 = ["ltx_video", "coqui_tts", "musicgen", "diffusers", "torch_gpu"]

    all_tools = pipeline + tier1 + tier2
    return {t: check_tool(t) for t in all_tools}


def require_tool(name: str):
    """Raise ImportError if tool is not available."""
    if not check_tool(name):
        raise ImportError(f"{name} is not installed. Install it to use this feature.")
