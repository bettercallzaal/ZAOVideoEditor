from pydantic import BaseModel
from typing import Optional
from enum import Enum


class ProjectCreate(BaseModel):
    name: str
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
    project_name: str
    use_intro: bool = False
    use_outro: bool = False
    intro_type: Optional[str] = None  # "default" or "custom"
    outro_type: Optional[str] = None  # "default" or "custom"


class TranscriptionRequest(BaseModel):
    project_name: str
    model_size: str = "base"


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


class CaptionTheme(str, Enum):
    THEME_A = "theme_a"
    THEME_B = "theme_b"


class CaptionRequest(BaseModel):
    project_name: str
    theme: CaptionTheme = CaptionTheme.THEME_A


class BurnCaptionRequest(BaseModel):
    project_name: str
    theme: CaptionTheme = CaptionTheme.THEME_A


class MetadataRequest(BaseModel):
    project_name: str


class MetadataDraft(BaseModel):
    description: str
    chapters: str
    tags: str


class ExportRequest(BaseModel):
    project_name: str


class TranscriptEditRequest(BaseModel):
    project_name: str
    segments: list[TranscriptSegment]


class CleanupRequest(BaseModel):
    project_name: str
