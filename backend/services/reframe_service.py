"""Aspect-ratio reframing for clips.

Turns a 16:9 source into vertical 9:16, square 1:1, or keeps 16:9, producing the
ffmpeg crop+scale video filter. Crop is centered by default; if OpenCV is
available it can center the crop on the dominant face ("speaker-aware" crop),
falling back to center when no face is found.
"""

import subprocess
from typing import Optional


# target pixel dimensions per aspect (standard short-form sizes)
ASPECT_TARGETS = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "16:9": (1920, 1080),
}

SUPPORTED_ASPECTS = list(ASPECT_TARGETS.keys())


def aspect_target(aspect: str) -> tuple:
    if aspect not in ASPECT_TARGETS:
        raise ValueError(f"Unsupported aspect ratio: {aspect}")
    return ASPECT_TARGETS[aspect]


def build_vf(aspect: str, focus_x: Optional[float] = None) -> str:
    """Build the ffmpeg -vf crop+scale chain for the target aspect.

    aspect: one of "9:16", "1:1", "16:9".
    focus_x: horizontal focal point as a 0..1 fraction of source width. When
             None, the crop is centered. Used for face/speaker-aware framing.
    Returns a filter string safe to concatenate with other filters via ",".
    """
    out_w, out_h = aspect_target(aspect)
    ar = f"{out_w}/{out_h}"

    # Crop width/height as ffmpeg expressions over input dims (iw, ih).
    # Fit the largest rectangle of the target ratio inside the source.
    # Commas inside expression functions (min/clip) MUST be escaped as "\," or
    # ffmpeg reads them as filter separators and the filterchain fails to parse.
    crop_w = r"min(iw\,ih*" + ar + ")"
    crop_h = r"min(ih\,iw/(" + ar + "))"

    if focus_x is None:
        x_expr = f"(iw-{crop_w})/2"
    else:
        f = max(0.0, min(1.0, focus_x))
        # Center the crop on focus point, clamped to stay inside the frame.
        x_expr = f"clip(iw*{f}-({crop_w})/2" + r"\,0\," + f"iw-{crop_w})"

    y_expr = f"(ih-{crop_h})/2"

    return f"crop={crop_w}:{crop_h}:{x_expr}:{y_expr},scale={out_w}:{out_h}"


def detect_focus_x(video_path: str, sample_time: float = 1.0) -> Optional[float]:
    """Return the dominant face's horizontal center as a 0..1 fraction.

    Samples one frame at sample_time and runs OpenCV Haar face detection. Returns
    None if OpenCV is unavailable, no frame is grabbed, or no face is found - the
    caller then uses a centered crop.
    """
    try:
        import cv2  # noqa: F401
        import numpy as np
    except ImportError:
        return None

    try:
        # Grab a single frame at sample_time as raw image bytes via ffmpeg.
        result = subprocess.run(
            ["ffmpeg", "-ss", str(sample_time), "-i", video_path,
             "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "-"],
            capture_output=True, timeout=30,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        import cv2
        import numpy as np
        arr = np.frombuffer(result.stdout, dtype=np.uint8)
        img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if img is None:
            return None
        h, w = img.shape[:2]
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5)
        if len(faces) == 0:
            return None
        # Pick the largest face; return its horizontal center fraction.
        fx, fy, fw, fh = max(faces, key=lambda r: r[2] * r[3])
        return (fx + fw / 2) / w
    except Exception:
        return None
