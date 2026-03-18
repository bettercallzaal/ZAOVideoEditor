"""Vercel serverless function for YouTube transcript extraction.

Uses youtube-transcript-api (lightweight, no ffmpeg/whisper needed).
Falls back to yt-dlp metadata only if captions aren't available.
"""

import re
import json
from http.server import BaseHTTPRequestHandler


def extract_video_id(url: str) -> str:
    patterns = [
        r'(?:v=|/v/|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    raise ValueError("Invalid YouTube URL")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        body = json.loads(self.rfile.read(content_length)) if content_length else {}

        url = body.get('url', '')
        action = body.get('action', 'transcribe')  # 'info' or 'transcribe'

        try:
            video_id = extract_video_id(url)
        except ValueError as e:
            self._respond(400, {'error': str(e)})
            return

        if action == 'info':
            self._handle_info(video_id)
        else:
            self._handle_transcribe(video_id)

    def _handle_info(self, video_id):
        try:
            from youtube_transcript_api import YouTubeTranscriptApi
            api = YouTubeTranscriptApi()
            transcript_list = api.list(video_id)
            languages = []
            for t in transcript_list:
                languages.append({
                    'language': t.language,
                    'code': t.language_code,
                    'auto_generated': t.is_generated,
                })
            self._respond(200, {
                'video_id': video_id,
                'has_captions': True,
                'languages': languages,
            })
        except Exception:
            self._respond(200, {
                'video_id': video_id,
                'has_captions': False,
                'languages': [],
            })

    def _handle_transcribe(self, video_id):
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

            full_text = '\n'.join(s['text'] for s in segments)

            self._respond(200, {
                'video_id': video_id,
                'segment_count': len(segments),
                'char_count': len(full_text),
                'segments': segments,
            })
        except Exception as e:
            self._respond(400, {
                'error': f'Could not get transcript: {str(e)}',
                'video_id': video_id,
            })

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
