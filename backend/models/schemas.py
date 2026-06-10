from pydantic import BaseModel, StringConstraints
from typing import Optional, Annotated
from enum import Enum


# Constrained project-name type: alphanumeric start, then alphanumerics, space,
# dot, dash, underscore. Blocks path separators and ".." traversal at parse time,
# so every request body carrying a project name is rejected (422) before it can
# be joined onto a filesystem path. See services/project_utils.validate_project_name.
ProjectName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100,
                      pattern=r"^[A-Za-z0-9][A-Za-z0-9 ._-]*$"),
]


class ProjectCreate(BaseModel):
    name: ProjectName
    description: Optional[str] = ""


class ProjectInfo(BaseModel):
    name: str
    description: str
    created_at: str
    stages: dict


class StageStatus(str, Enum):
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETE = "complete"
    ERROR = "error"


class AssemblyRequest(BaseModel):
    project_name: ProjectName
    use_intro: bool = False
    use_outro: bool = False
    intro_type: Optional[str] = None  # "default" or "custom"
    outro_type: Optional[str] = None  # "default" or "custom"


class TranscriptionRequest(BaseModel):
    project_name: ProjectName
    model_size: str = "base"
    engine: str = "auto"           # "faster-whisper", "whisperx", "groq", "auto"
    refine_timestamps: bool = True  # use stable-ts if available


class TranscriptSegment(BaseModel):
    id: int
    start: float
    end: float
    text: str
    words: Optional[list] = None


class TranscriptData(BaseModel):
    segments: list[TranscriptSegment]
    raw_text: str


class DictionaryEntry(BaseModel):
    wrong: str
    correct: str


class CaptionStyle(str, Enum):
    CLASSIC = "classic"
    BOX = "box"
    BOLD_POP = "bold_pop"
    HIGHLIGHT = "highlight"
    BRAND_LIGHT = "brand_light"
    BRAND_DARK = "brand_dark"


class CaptionRequest(BaseModel):
    project_name: ProjectName
    style: CaptionStyle = CaptionStyle.CLASSIC


class BurnCaptionRequest(BaseModel):
    project_name: ProjectName
    style: CaptionStyle = CaptionStyle.CLASSIC
    renderer: str = "auto"  # "pillow", "moviepy", "auto"


class MetadataRequest(BaseModel):
    project_name: ProjectName


class MetadataDraft(BaseModel):
    description: str
    chapters: str
    tags: str


class ExportRequest(BaseModel):
    project_name: ProjectName


class TranscriptEditRequest(BaseModel):
    project_name: ProjectName
    segments: list[TranscriptSegment]


class CleanupRequest(BaseModel):
    project_name: ProjectName
