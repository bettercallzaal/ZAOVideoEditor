"""Shared test setup.

The render tests measure real pixels, so they skip without ffmpeg. On a developer
laptop that is a convenience. In CI it is a trap: every pixel test skips, the run
goes green, and nothing has verified the renderer. Set REQUIRE_FFMPEG=1 (CI does)
to turn that silent skip into a hard failure.
"""

import os
from shutil import which

import pytest


def has_ffmpeg() -> bool:
    return which("ffmpeg") is not None and which("ffprobe") is not None


def pytest_configure(config):
    if os.environ.get("REQUIRE_FFMPEG") == "1" and not has_ffmpeg():
        raise pytest.UsageError(
            "REQUIRE_FFMPEG=1 but ffmpeg/ffprobe are not on PATH. The render "
            "tests would all skip and this run would pass without verifying "
            "a single rendered frame."
        )
