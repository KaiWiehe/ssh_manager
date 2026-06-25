"""Regression tests for the generated Windows icon assets.

After commit 98e60a6 the new SSH-Logo.png had an opaque white background.
The icon generator (re-)introduced in that commit only padded the source
to a square, so every ICO frame ended up as a uniform white/grey square
(no visible silhouette).  In Windows that showed up as an almost blank
title-bar icon and a white taskbar tile.

These tests guard against that specific regression by asserting that
every generated frame (the 256 px PNG used by ``iconphoto`` *and* each
ICO frame) has a real, sizeable visible silhouette – i.e. the visible
content bbox covers a meaningful fraction of the frame and the alpha
coverage isn't ~100 % (which is what a solid background would produce).
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image


ROOT = Path(__file__).resolve().parent.parent
PNG_PATH = ROOT / "assets" / "ssh-manager.png"
ICO_PATH = ROOT / "assets" / "ssh-manager.ico"

# The frames the generator is expected to emit and Windows actually uses.
EXPECTED_FRAMES = {16, 20, 24, 32, 40, 48, 64, 128, 256}

# Alpha threshold for "visible" pixels.  Same value the generator uses
# when cropping to content.
VISIBLE_ALPHA = 16

# A correctly generated frame has a visible bbox >= this fraction of the
# frame's width/height.  The old buggy output had silhouettes around
# 10-15 % (and at small sizes effectively 0 % because everything dissolved
# into a uniform grey square).
MIN_BBOX_FRACTION = 0.50

# Conversely, if the background isn't really transparent we get
# essentially 100 % alpha coverage – which is exactly the regression.
# A genuine logo silhouette caps out well below this.
MAX_ALPHA_COVERAGE = 0.90


def _visible_bbox_and_coverage(frame: Image.Image) -> tuple[tuple[int, int, int, int] | None, float]:
    """Return the visible (alpha > threshold) bbox and overall coverage."""
    rgba = frame.convert("RGBA")
    alpha = rgba.split()[-1]
    mask = alpha.point(lambda v: 255 if v > VISIBLE_ALPHA else 0)
    bbox = mask.getbbox()
    visible_pixels = sum(1 for v in mask.getdata() if v)
    coverage = visible_pixels / (rgba.width * rgba.height)
    return bbox, coverage


def _assert_healthy_frame(frame: Image.Image, label: str) -> None:
    bbox, coverage = _visible_bbox_and_coverage(frame)
    assert bbox is not None, f"{label}: frame is entirely transparent (blank)"
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    frac_w = w / frame.width
    frac_h = h / frame.height
    assert frac_w >= MIN_BBOX_FRACTION, (
        f"{label}: visible width fraction {frac_w:.2f} below threshold "
        f"{MIN_BBOX_FRACTION:.2f} (regression: logo collapsed to tiny silhouette)"
    )
    assert frac_h >= MIN_BBOX_FRACTION, (
        f"{label}: visible height fraction {frac_h:.2f} below threshold "
        f"{MIN_BBOX_FRACTION:.2f} (regression: logo collapsed to tiny silhouette)"
    )
    assert coverage <= MAX_ALPHA_COVERAGE, (
        f"{label}: alpha coverage {coverage:.2f} above threshold "
        f"{MAX_ALPHA_COVERAGE:.2f} – the background is probably opaque, "
        f"which yields a uniform white/grey square at small sizes."
    )


def test_runtime_png_exists_and_is_high_res() -> None:
    assert PNG_PATH.exists(), f"missing {PNG_PATH}"
    img = Image.open(PNG_PATH)
    assert img.size == (256, 256), f"expected 256x256, got {img.size}"


def test_runtime_png_has_visible_silhouette() -> None:
    img = Image.open(PNG_PATH)
    _assert_healthy_frame(img, label="ssh-manager.png")


def test_ico_has_expected_frames() -> None:
    assert ICO_PATH.exists(), f"missing {ICO_PATH}"
    ico = Image.open(ICO_PATH)
    sizes = {s[0] for s in ico.info.get("sizes", set())}
    missing = EXPECTED_FRAMES - sizes
    assert not missing, f"ICO is missing frames: {sorted(missing)}"


@pytest.mark.parametrize("size", sorted(EXPECTED_FRAMES))
def test_ico_frame_has_visible_silhouette(size: int) -> None:
    ico = Image.open(ICO_PATH)
    ico.size = (size, size)
    frame = ico.convert("RGBA")
    assert frame.size == (size, size)
    _assert_healthy_frame(frame, label=f"ssh-manager.ico@{size}")
