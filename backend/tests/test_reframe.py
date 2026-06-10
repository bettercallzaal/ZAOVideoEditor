"""Aspect reframing filter construction."""

import pytest

from backend.services.reframe_service import (
    build_vf, aspect_target, SUPPORTED_ASPECTS,
)


@pytest.mark.parametrize("aspect,dims", [
    ("9:16", (1080, 1920)),
    ("1:1", (1080, 1080)),
    ("16:9", (1920, 1080)),
])
def test_aspect_target(aspect, dims):
    assert aspect_target(aspect) == dims


def test_aspect_target_rejects_unknown():
    with pytest.raises(ValueError):
        aspect_target("4:3")


@pytest.mark.parametrize("aspect", SUPPORTED_ASPECTS)
def test_build_vf_centered(aspect):
    vf = build_vf(aspect)
    out_w, out_h = aspect_target(aspect)
    assert vf.startswith("crop=")
    assert f"scale={out_w}:{out_h}" in vf
    # commas inside the crop expression must be escaped or ffmpeg mis-parses
    crop_part = vf.split(",scale=")[0]
    assert "min(iw\\," in crop_part


def test_build_vf_focus_clamped():
    # focus outside 0..1 must be clamped into the expression
    vf_low = build_vf("9:16", focus_x=-5)
    vf_high = build_vf("9:16", focus_x=5)
    assert "iw*0.0" in vf_low
    assert "iw*1.0" in vf_high


def test_build_vf_focus_uses_clip():
    vf = build_vf("9:16", focus_x=0.5)
    assert "clip(" in vf
