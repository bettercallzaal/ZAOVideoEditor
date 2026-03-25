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
        # Try English first, then any available language
        for langs in [['en'], ['en-US', 'en-GB'], None]:
            try:
                if langs:
                    transcript = api.fetch(video_id, languages=langs)
                else:
                    transcript = api.fetch(video_id)
                segments = []
                for i, entry in enumerate(transcript):
                    segments.append({
                        'id': i,
                        'start': round(entry.start, 3),
                        'end': round(entry.start + entry.duration, 3),
                        'text': entry.text.strip(),
                    })
                if segments:
                    return segments
            except Exception:
                continue
        return None
    except Exception:
        return None


def try_ytdlp_subtitles(video_id: str) -> list | None:
    """Try to download subtitles via yt-dlp without downloading video (fast fallback)."""
    try:
        import yt_dlp
        import tempfile
        import json as _json

        with tempfile.TemporaryDirectory() as tmp_dir:
            sub_path = os.path.join(tmp_dir, 'subs')

            ydl_opts = {
                'skip_download': True,
                'writeautomaticsub': True,
                'writesubtitles': True,
                'subtitleslangs': ['en', 'en-US', 'en-GB', 'en.*'],
                'subtitlesformat': 'json3',
                'outtmpl': sub_path,
                'quiet': True,
                'no_warnings': True,
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f'https://www.youtube.com/watch?v={video_id}'])

            # Find the downloaded subtitle file
            sub_file = None
            for f in os.listdir(tmp_dir):
                if f.endswith('.json3') or f.endswith('.json'):
                    sub_file = os.path.join(tmp_dir, f)
                    break

            if not sub_file:
                # Try SRT/VTT fallback
                for f in os.listdir(tmp_dir):
                    if f.endswith(('.srt', '.vtt')):
                        sub_file = os.path.join(tmp_dir, f)
                        break

            if not sub_file:
                return None

            if sub_file.endswith('.json3') or sub_file.endswith('.json'):
                return _parse_json3_subs(sub_file)
            elif sub_file.endswith('.srt'):
                return _parse_srt_subs(sub_file)
            elif sub_file.endswith('.vtt'):
                return _parse_vtt_subs(sub_file)

        return None
    except Exception:
        return None


def _parse_json3_subs(filepath: str) -> list | None:
    """Parse YouTube json3 subtitle format."""
    import json as _json
    with open(filepath) as f:
        data = _json.load(f)

    events = data.get('events', [])
    segments = []
    seg_id = 0
    for event in events:
        # json3 events have tStartMs, dDurMs, and segs array
        start_ms = event.get('tStartMs', 0)
        dur_ms = event.get('dDurMs', 0)
        segs = event.get('segs', [])
        text = ''.join(s.get('utf8', '') for s in segs).strip()
        if text and text != '\n':
            segments.append({
                'id': seg_id,
                'start': round(start_ms / 1000, 3),
                'end': round((start_ms + dur_ms) / 1000, 3),
                'text': text,
            })
            seg_id += 1
    return segments if segments else None


def _parse_srt_subs(filepath: str) -> list | None:
    """Parse SRT subtitle file."""
    with open(filepath) as f:
        content = f.read()

    segments = []
    blocks = content.strip().split('\n\n')
    for i, block in enumerate(blocks):
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        # Parse timestamp line: 00:00:01,000 --> 00:00:04,000
        time_line = lines[1]
        match = re.match(r'(\d+:\d+:\d+[,\.]\d+)\s*-->\s*(\d+:\d+:\d+[,\.]\d+)', time_line)
        if not match:
            continue
        start = _timestamp_to_seconds(match.group(1))
        end = _timestamp_to_seconds(match.group(2))
        text = ' '.join(lines[2:]).strip()
        if text:
            segments.append({'id': i, 'start': start, 'end': end, 'text': text})
    return segments if segments else None


def _parse_vtt_subs(filepath: str) -> list | None:
    """Parse VTT subtitle file."""
    with open(filepath) as f:
        content = f.read()

    segments = []
    # Skip header
    blocks = content.strip().split('\n\n')
    seg_id = 0
    for block in blocks:
        lines = block.strip().split('\n')
        for j, line in enumerate(lines):
            match = re.match(r'(\d+:\d+:\d+\.\d+|\d+:\d+\.\d+)\s*-->\s*(\d+:\d+:\d+\.\d+|\d+:\d+\.\d+)', line)
            if match:
                start = _timestamp_to_seconds(match.group(1))
                end = _timestamp_to_seconds(match.group(2))
                text = ' '.join(lines[j+1:]).strip()
                # Remove VTT tags
                text = re.sub(r'<[^>]+>', '', text)
                if text:
                    segments.append({'id': seg_id, 'start': start, 'end': end, 'text': text})
                    seg_id += 1
                break
    return segments if segments else None


def _timestamp_to_seconds(ts: str) -> float:
    """Convert timestamp like 00:01:23,456 or 00:01:23.456 to seconds."""
    ts = ts.replace(',', '.')
    parts = ts.split(':')
    if len(parts) == 3:
        return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    elif len(parts) == 2:
        return float(parts[0]) * 60 + float(parts[1])
    return 0.0


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

    # Step 2: Try yt-dlp subtitle extraction (fast, no audio download)
    if on_progress:
        on_progress(10, 'No captions via API — trying yt-dlp subtitle extraction...')

    subtitles = try_ytdlp_subtitles(video_id)
    if subtitles:
        if on_progress:
            on_progress(90, f'Got subtitles via yt-dlp ({len(subtitles)} segments)')

        video_info = get_video_info(video_id)

        import json
        transcript_data = {
            'segments': subtitles,
            'source': 'ytdlp_subtitles',
            'video_id': video_id,
            'video_info': video_info,
        }
        with open(transcripts_dir / 'raw.json', 'w') as f:
            json.dump(transcript_data, f, indent=2)

        if on_progress:
            on_progress(100, 'Subtitles saved')

        return {
            'segments': subtitles,
            'segment_count': len(subtitles),
            'video_info': video_info,
            'source': 'ytdlp_subtitles',
        }

    # Step 3: Download audio and transcribe with faster-whisper (last resort)
    if on_progress:
        on_progress(15, 'No subtitles available — downloading audio for Whisper...')

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
