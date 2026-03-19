"""YouTube transcript extraction service.

Downloads audio from YouTube videos via yt-dlp, then transcribes
using the existing faster-whisper pipeline.
Also tries youtube-transcript-api first for speed when captions exist.
"""

import re
import os
import tempfile
from pathlib import Path


def extract_video_id(url: str) -> str:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from: {url}")


def get_video_info(video_id: str) -> dict:
    """Get basic video metadata without downloading."""
    import yt_dlp

    ydl_opts = {
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=False)
        return {
            'title': info.get('title', ''),
            'duration': info.get('duration', 0),
            'channel': info.get('channel', ''),
            'upload_date': info.get('upload_date', ''),
            'was_live': info.get('was_live', False),
            'view_count': info.get('view_count', 0),
        }


def try_youtube_captions(video_id: str) -> list | None:
    """Try to get transcript via youtube-transcript-api (fast, no download needed)."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=['en'])
        segments = []
        for i, entry in enumerate(transcript):
            segments.append({
                'id': i,
                'start': round(entry.start, 3),
                'end': round(entry.start + entry.duration, 3),
                'text': entry.text.strip(),
            })
        return segments
    except Exception:
        return None


def download_audio(video_id: str, output_dir: str, on_progress=None) -> tuple[str, dict]:
    """Download audio from YouTube video. Returns (audio_path, video_info)."""
    import yt_dlp

    audio_path = os.path.join(output_dir, 'yt_audio.wav')

    progress_state = {'last_pct': 0}

    def progress_hook(d):
        if d['status'] == 'downloading' and on_progress:
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                pct = int((downloaded / total) * 100)
                if pct > progress_state['last_pct']:
                    progress_state['last_pct'] = pct
                    on_progress(pct, f'Downloading audio... {pct}%')

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(output_dir, 'yt_audio.%(ext)s'),
        'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'}],
        'quiet': True,
        'no_warnings': True,
        'progress_hooks': [progress_hook],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f'https://www.youtube.com/watch?v={video_id}', download=True)

    video_info = {
        'title': info.get('title', ''),
        'duration': info.get('duration', 0),
        'channel': info.get('channel', ''),
        'was_live': info.get('was_live', False),
    }

    return audio_path, video_info


def transcribe_youtube(video_id: str, project_dir: str, quality: str = 'standard',
                       on_progress=None) -> dict:
    """Full pipeline: download audio → transcribe → save to project.

    Returns dict with segments, video_info, and source method.
    """
    project_path = Path(project_dir)
    transcripts_dir = project_path / 'transcripts'
    transcripts_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: Try YouTube captions first (instant)
    if on_progress:
        on_progress(5, 'Checking for existing YouTube captions...')

    captions = try_youtube_captions(video_id)
    if captions:
        if on_progress:
            on_progress(90, f'Found YouTube captions ({len(captions)} segments)')

        video_info = get_video_info(video_id)

        # Save as raw transcript
        import json
        transcript_data = {
            'segments': captions,
            'source': 'youtube_captions',
            'video_id': video_id,
            'video_info': video_info,
        }
        with open(transcripts_dir / 'raw.json', 'w') as f:
            json.dump(transcript_data, f, indent=2)

        if on_progress:
            on_progress(100, 'YouTube captions saved')

        return {
            'segments': captions,
            'segment_count': len(captions),
            'video_info': video_info,
            'source': 'youtube_captions',
        }

    # Step 2: Download audio and transcribe with faster-whisper
    if on_progress:
        on_progress(10, 'No captions available — downloading audio...')

    with tempfile.TemporaryDirectory() as tmp_dir:
        audio_path, video_info = download_audio(
            video_id, tmp_dir,
            on_progress=lambda pct, msg: on_progress(10 + int(pct * 0.3), msg) if on_progress else None,
        )

        if on_progress:
            on_progress(40, 'Transcribing with faster-whisper...')

        # Use existing whisper service
        from .whisper_service import transcribe_audio

        model_size = {'fast': 'base', 'standard': 'large-v3', 'high': 'large-v3'}.get(quality, 'large-v3')

        result = transcribe_audio(
            audio_path,
            model_size=model_size,
            quality=quality,
            on_progress=lambda stage, pct, msg: on_progress(40 + int(pct * 0.5), msg) if on_progress else None,
        )

        # Save as raw transcript
        import json
        transcript_data = {
            'segments': result['segments'],
            'source': 'whisper_from_youtube',
            'video_id': video_id,
            'video_info': video_info,
        }
        with open(transcripts_dir / 'raw.json', 'w') as f:
            json.dump(transcript_data, f, indent=2)

        if on_progress:
            on_progress(100, f'Transcribed {len(result["segments"])} segments')

        return {
            'segments': result['segments'],
            'segment_count': len(result['segments']),
            'video_info': video_info,
            'source': 'whisper_from_youtube',
        }
