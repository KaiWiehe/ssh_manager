"""Regression tests for the generated Windows icon assets.

The app icons are generated from ``assets/SSH-Logo.svg``.  The logo is a bold
black prompt mark on a transparent background; every ICO frame must retain
enough contrast so Windows does not show a blank tile or a tiny invisible mark
in the title bar/taskbar.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image, ImageStat


ROOT = Path(__file__).resolve().parent.parent
SVG_PATH = ROOT / "assets" / "SSH-Logo.svg"
PNG_PATH = ROOT / "assets" / "ssh-manager.png"
ICO_PATH = ROOT / "assets" / "ssh-manager.ico"

# The frames the generator is expected to emit and Windows actually uses.
EXPECTED_FRAMES = {16, 20, 24, 32, 40, 48, 64, 128, 256}
VISIBLE_ALPHA = 8
MIN_BBOX_FRACTION = 0.50
MAX_ALPHA_COVERAGE = 0.90

# Contrast thresholds are intentionally conservative.  They catch solid/blank
# frames while allowing small 16px icons where details are naturally limited.
MIN_LUMINANCE_STDDEV = 25.0
MIN_DARK_PIXEL_FRACTION = 0.02


def _alpha_bbox_and_coverage(frame: Image.Image) -> tuple[tuple[int, int, int, int] | None, float]:
    rgba = frame.convert("RGBA")
    alpha = rgba.split()[-1]
    mask = alpha.point(lambda v: 255 if v > VISIBLE_ALPHA else 0)
    bbox = mask.getbbox()
    visible_pixels = sum(1 for v in mask.getdata() if v)
    coverage = visible_pixels / (rgba.width * rgba.height)
    return bbox, coverage


def _visible_luminance(frame: Image.Image) -> Image.Image:
    rgba = frame.convert("RGBA")
    white_bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(white_bg, rgba).convert("L")


def _assert_healthy_frame(frame: Image.Image, label: str) -> None:
    bbox, coverage = _alpha_bbox_and_coverage(frame)
    assert bbox is not None, f"{label}: frame is entirely transparent (blank)"
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    frac_w = w / frame.width
    frac_h = h / frame.height
    assert frac_w >= MIN_BBOX_FRACTION, f"{label}: visible width fraction {frac_w:.2f} is too small"
    assert frac_h >= MIN_BBOX_FRACTION, f"{label}: visible height fraction {frac_h:.2f} is too small"
    assert coverage <= MAX_ALPHA_COVERAGE, (
        f"{label}: alpha coverage {coverage:.2f} is too high; background is probably opaque"
    )

    lum = _visible_luminance(frame)
    stddev = ImageStat.Stat(lum).stddev[0]
    dark_fraction = sum(1 for value in lum.getdata() if value < 80) / (frame.width * frame.height)
    assert stddev >= MIN_LUMINANCE_STDDEV, f"{label}: contrast stddev {stddev:.2f} is too low"
    assert dark_fraction >= MIN_DARK_PIXEL_FRACTION, (
        f"{label}: dark pixel fraction {dark_fraction:.3f} is too low; icon may look blank"
    )


def test_svg_logo_source_exists() -> None:
    assert SVG_PATH.exists(), f"missing {SVG_PATH}"


def test_runtime_png_exists_and_is_high_res() -> None:
    assert PNG_PATH.exists(), f"missing {PNG_PATH}"
    img = Image.open(PNG_PATH)
    assert img.size == (256, 256), f"expected 256x256, got {img.size}"


def test_runtime_png_has_visible_contrast() -> None:
    img = Image.open(PNG_PATH)
    _assert_healthy_frame(img, label="ssh-manager.png")


def test_ico_has_expected_frames() -> None:
    assert ICO_PATH.exists(), f"missing {ICO_PATH}"
    ico = Image.open(ICO_PATH)
    sizes = {s[0] for s in ico.info.get("sizes", set())}
    missing = EXPECTED_FRAMES - sizes
    assert not missing, f"ICO is missing frames: {sorted(missing)}"


@pytest.mark.parametrize("size", sorted(EXPECTED_FRAMES))
def test_ico_frame_has_visible_contrast(size: int) -> None:
    ico = Image.open(ICO_PATH)
    ico.size = (size, size)
    frame = ico.convert("RGBA")
    assert frame.size == (size, size)
    _assert_healthy_frame(frame, label=f"ssh-manager.ico@{size}")
