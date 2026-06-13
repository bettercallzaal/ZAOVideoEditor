"""Caption-burn pipe robustness: an early ffmpeg exit must not crash the burn.

Regression for the Pillow-fallback broken-pipe bug - when ffmpeg closed the
overlay pipe early, proc.stdin.write() raised an uncaught BrokenPipeError.
"""

import pytest

from backend.services.ffmpeg_service import _write_overlay_frames, _finish_overlay_pipe


class _FakeStdin:
    def __init__(self, break_after=None):
        self.break_after = break_after
        self.writes = 0
        self.closed = False

    def write(self, data):
        self.writes += 1
        if self.break_after is not None and self.writes > self.break_after:
            raise BrokenPipeError("pipe closed")

    def close(self):
        self.closed = True


class _FakeProc:
    def __init__(self, returncode=0, stderr=b"", break_after=None):
        self.stdin = _FakeStdin(break_after=break_after)
        self.returncode = returncode
        self._stderr = stderr

    def communicate(self):
        return (b"", self._stderr)


def _frames(n):
    for _ in range(n):
        yield b"\x00\x00\x00\x00"


def test_all_frames_written_no_break():
    proc = _FakeProc()
    broke = _write_overlay_frames(proc, _frames(10), total_frames=10)
    assert broke is False
    assert proc.stdin.writes == 10


def test_broken_pipe_stops_cleanly():
    proc = _FakeProc(break_after=3)
    broke = _write_overlay_frames(proc, _frames(100), total_frames=100)
    assert broke is True
    assert proc.stdin.writes == 4  # the 4th write raised


def test_finish_ok_when_exit_zero_even_if_pipe_broke():
    proc = _FakeProc(returncode=0)
    _finish_overlay_pipe(proc, pipe_broke=True)  # must not raise
    assert proc.stdin.closed


def test_finish_raises_on_ffmpeg_failure():
    proc = _FakeProc(returncode=1, stderr=b"some ffmpeg error")
    with pytest.raises(RuntimeError, match="caption burn failed"):
        _finish_overlay_pipe(proc, pipe_broke=False)


def test_finish_tolerates_close_error():
    proc = _FakeProc(returncode=0)
    def boom():
        raise BrokenPipeError()
    proc.stdin.close = boom
    _finish_overlay_pipe(proc, pipe_broke=True)  # must not raise


def test_progress_called():
    seen = []
    proc = _FakeProc()
    _write_overlay_frames(proc, _frames(100), total_frames=100,
                          on_progress=lambda p, m: seen.append(p))
    assert seen and all(15 <= p <= 95 for p in seen)
