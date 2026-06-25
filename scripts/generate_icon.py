"""
Regenerate Windows icon assets from the SVG logo source.

Produces:
  * assets/ssh-manager.ico   – multi-frame ICO (16/20/24/32/40/48/64/128/256)
  * assets/ssh-manager.png   – 256x256 high-res PNG used by Tk's iconphoto()

The authoritative source is ``assets/SSH-Logo.svg``.  The SVG contains a
white export/background rectangle plus actual white logo details.  Removing
"all white" from a rendered PNG breaks the artwork, while keeping the export
rectangle makes Windows show a nearly blank white tile at small sizes.  This
script therefore removes only that SVG background rectangle before rendering,
so the real white details are preserved and the icon background is transparent.

Run from repo root::

    python scripts/generate_icon.py
"""
from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageFilter

try:
    RESAMPLE_LANCZOS = Image.Resampling.LANCZOS
except AttributeError:  # Pillow < 9.1
    RESAMPLE_LANCZOS = Image.LANCZOS

ROOT = Path(__file__).resolve().parent.parent
SVG_SOURCE = ROOT / "assets" / "SSH-Logo.svg"
PNG_SOURCE_FALLBACK = ROOT / "assets" / "SSH-Logo.png"
ICO_OUT = ROOT / "assets" / "ssh-manager.ico"
PNG_OUT = ROOT / "assets" / "ssh-manager.png"

# Frames Windows actually uses across DPI levels and contexts (title bar,
# taskbar, Alt+Tab, jumplists, Explorer thumbnails, …).
FRAME_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

# Render large first, then downscale with Pillow.  This gives us consistent
# filtering and lets us optimize individual small frames.
RENDER_SIZE = 2048

# Alpha threshold used to compute the content bounding box for cropping
# transparent padding around the artwork.
CONTENT_ALPHA_THRESHOLD = 8

# Fraction of the final canvas size to leave as transparent margin around
# the cropped logo (each side).  7% keeps the icon readable at 16 px without
# making it feel glued to the edge.
SQUARE_MARGIN = 0.07

# Sizes at or below this get a light alpha dilation pass before downscaling so
# thin black strokes survive in Windows' tiny title-bar/taskbar variants.
DILATE_SIZE_LIMIT = 32


def _strip_svg_export_background(svg_text: str) -> str:
    """Remove the exported full-canvas white rectangle, not logo details.

    The SVG contains a first ``<rect ... fill:white;stroke:white .../>`` that is
    only an export/background card.  Later white ``<path>`` elements are real
    artwork (window interior / letters) and must stay intact.
    """
    pattern = re.compile(r"\s*<rect\b[^>]*style=\"[^\"]*fill:white;stroke:white[^\"]*\"\s*/>", re.I)
    stripped, count = pattern.subn("", svg_text, count=1)
    if count != 1:
        raise RuntimeError("Could not find the SVG export background rectangle")
    return stripped


def _render_svg_source() -> Image.Image:
    """Render SVG source to a large RGBA Pillow image."""
    try:
        import cairosvg  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "cairosvg is required to regenerate icons from assets/SSH-Logo.svg. "
            "Install it in the build/dev environment with `pip install cairosvg`."
        ) from exc

    svg_text = SVG_SOURCE.read_text(encoding="utf-8")
    svg_text = _strip_svg_export_background(svg_text)
    png_bytes = cairosvg.svg2png(
        bytestring=svg_text.encode("utf-8"),
        output_width=RENDER_SIZE,
        output_height=RENDER_SIZE,
    )
    return Image.open(BytesIO(png_bytes)).convert("RGBA")


def _load_source() -> Image.Image:
    if SVG_SOURCE.exists():
        img = _render_svg_source()
        print(f"Source: {SVG_SOURCE.name} rendered to {img.size}")
        return img
    if PNG_SOURCE_FALLBACK.exists():  # pragma: no cover - only for old checkouts
        img = Image.open(PNG_SOURCE_FALLBACK).convert("RGBA")
        print(f"Source fallback: {PNG_SOURCE_FALLBACK.name} {img.size}")
        return img
    raise SystemExit(f"Source logo not found: {SVG_SOURCE}")


def crop_to_content(img: Image.Image) -> Image.Image:
    """Crop *img* to its visible alpha bounding box."""
    alpha = img.split()[-1]
    mask = alpha.point(lambda v: 255 if v > CONTENT_ALPHA_THRESHOLD else 0)
    bbox = mask.getbbox()
    if bbox is None:
        return img
    return img.crop(bbox)


def square_canvas(img: Image.Image, margin: float = SQUARE_MARGIN) -> Image.Image:
    """Place *img* centered on a square transparent canvas with margin."""
    img = img.convert("RGBA")
    longest = max(img.size)
    side = int(round(longest / (1 - 2 * margin)))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    offset = ((side - img.width) // 2, (side - img.height) // 2)
    canvas.paste(img, offset, img)
    return canvas


def _dilate_alpha(img: Image.Image, radius: int = 1) -> Image.Image:
    """Slightly thicken visible content by dilating the alpha channel."""
    r, g, b, a = img.split()
    dilated = a.filter(ImageFilter.MaxFilter(radius * 2 + 1))
    return Image.merge("RGBA", (r, g, b, dilated))


def _sharpen_small_frame(img: Image.Image) -> Image.Image:
    """Improve contrast of tiny frames without changing the artwork shape."""
    # A tiny unsharp mask helps black SVG strokes survive resampling next to
    # white interior details at 16/20/24 px.
    return img.filter(ImageFilter.UnsharpMask(radius=0.6, percent=180, threshold=2))


def build_frames(square: Image.Image) -> list[Image.Image]:
    """Downscale *square* (already square RGBA) to all target sizes."""
    frames: list[Image.Image] = []
    src_side = square.width
    for size in FRAME_SIZES:
        frame_src = square
        if size <= DILATE_SIZE_LIMIT and src_side > size * 4:
            radius = max(1, int(round(src_side / size / 10)))
            frame_src = _dilate_alpha(square, radius=radius)
        frame = frame_src.resize((size, size), RESAMPLE_LANCZOS)
        if size <= DILATE_SIZE_LIMIT:
            frame = _sharpen_small_frame(frame)
        frames.append(frame)
    return frames


def _save_ico(frames: list[Image.Image]) -> None:
    # Pillow's ICO writer is most reliable when given a high-res base plus a
    # sizes list.  The small frames above are still useful for tests/inspection,
    # but Pillow may choose to encode from the largest internally depending on
    # version.  The source is now SVG-rendered and transparent, so that is fine.
    largest = max(frames, key=lambda f: f.width)
    largest.save(
        ICO_OUT,
        format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        bitmap_format="bmp",
    )


def main() -> None:
    src = _load_source()
    cropped = crop_to_content(src)
    print(f"After transparent-bg crop: {cropped.size} (was {src.size})")

    square = square_canvas(cropped)
    print(f"Square canvas: {square.size} (margin={SQUARE_MARGIN:.0%})")

    png_master = square.resize((256, 256), RESAMPLE_LANCZOS)
    png_master.save(PNG_OUT, format="PNG", optimize=True)
    print(f"Wrote {PNG_OUT.relative_to(ROOT)} ({png_master.size})")

    frames = build_frames(square)
    _save_ico(frames)
    print(f"Wrote {ICO_OUT.relative_to(ROOT)} with frames: {FRAME_SIZES}")

    verify = Image.open(ICO_OUT)
    print("Verified ICO frames:", sorted(verify.info.get("sizes", set())))


if __name__ == "__main__":
    main()
