"""
Regenerate Windows icon assets from the SVG logo source.

Produces:
  * assets/ssh-manager.ico   – multi-frame ICO (16/20/24/32/40/48/64/128/256)
  * assets/ssh-manager.png   – 256x256 high-res PNG used by Tk's iconphoto()

The authoritative source is ``assets/SSH-Logo.svg``.  The current logo is a
minimal black terminal prompt on a transparent background.  It intentionally
stays bold and simple so the Windows title-bar icon remains readable at 16 px.

Run from repo root::

    python scripts/generate_icon.py
"""
from __future__ import annotations

import re
import struct
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

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
# the cropped logo (each side).  7% keeps the icon readable for taskbar/Alt+Tab.
SQUARE_MARGIN = 0.07

# Extra margin for tiny title-bar frames.  Windows often uses the 16/20/24 px
# ICO entries directly in the top-left window corner; if the artwork reaches the
# frame edge it looks clipped.  These tiny variants intentionally breathe more.
SMALL_FRAME_MARGIN = 0.12

# Sizes at or below this use the extra-margin small-frame source.
SMALL_FRAME_SIZE_LIMIT = 24

# Sizes at or below this get a light alpha dilation pass before downscaling so
# thin black strokes survive in Windows' tiny title-bar/taskbar variants.
DILATE_SIZE_LIMIT = 32


def _strip_svg_export_background(svg_text: str) -> str:
    """Remove a legacy exported full-canvas white rectangle, if present.

    Older logo sources contained a first ``<rect ... fill:white;stroke:white
    .../>`` that was only an export/background card. The current prompt logo has
    no background, so absence of that rectangle is fine.
    """
    pattern = re.compile(r"\s*<rect\b[^>]*style=\"[^\"]*fill:white;stroke:white[^\"]*\"\s*/>", re.I)
    stripped, _count = pattern.subn("", svg_text, count=1)
    return stripped


def _render_simple_prompt_logo() -> Image.Image:
    """Render the repo's simple prompt SVG with Pillow when CairoSVG is absent."""
    scale = RENDER_SIZE / 256
    img = Image.new("RGBA", (RENDER_SIZE, RENDER_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def p(x: float, y: float) -> tuple[int, int]:
        return (round(x * scale), round(y * scale))

    stroke = round(34 * scale)
    radius = stroke // 2
    black = (0, 0, 0, 255)
    chevron = [p(56, 50), p(124, 128), p(56, 206)]
    underscore = [p(139, 192), p(214, 192)]
    draw.line(chevron, fill=black, width=stroke, joint="curve")
    draw.line(underscore, fill=black, width=stroke)
    for x, y in chevron + underscore:
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=black)
    return img


def _render_svg_source() -> Image.Image:
    """Render SVG source to a large RGBA Pillow image."""
    svg_text = SVG_SOURCE.read_text(encoding="utf-8")
    if 'data-generator="simple-prompt"' in svg_text:
        return _render_simple_prompt_logo()

    try:
        import cairosvg  # type: ignore[import-not-found]
    except Exception as exc:  # pragma: no cover - environment dependent
        raise SystemExit(
            "cairosvg is required to regenerate icons from assets/SSH-Logo.svg. "
            "Install it in the build/dev environment with `pip install cairosvg`."
        ) from exc

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


def build_frames(cropped: Image.Image, square: Image.Image) -> list[Image.Image]:
    """Downscale source artwork to all target sizes.

    Tiny title-bar frames need more breathing room than taskbar/Alt+Tab frames;
    otherwise Windows shows a clipped-looking icon in the top-left corner.
    """
    frames: list[Image.Image] = []
    small_square = square_canvas(cropped, margin=SMALL_FRAME_MARGIN)
    for size in FRAME_SIZES:
        frame_src = small_square if size <= SMALL_FRAME_SIZE_LIMIT else square
        src_side = frame_src.width
        if size <= DILATE_SIZE_LIMIT and src_side > size * 4:
            # Keep dilation deliberately gentle for tiny frames; too much alpha
            # dilation pushes strokes into the border and looks clipped.
            radius = 1 if size <= SMALL_FRAME_SIZE_LIMIT else max(1, int(round(src_side / size / 12)))
            frame_src = _dilate_alpha(frame_src, radius=radius)
        frame = frame_src.resize((size, size), RESAMPLE_LANCZOS)
        if size <= DILATE_SIZE_LIMIT:
            frame = _sharpen_small_frame(frame)
        frames.append(frame)
    return frames


def _save_ico(frames: list[Image.Image]) -> None:
    """Write an ICO file from the already optimized frames.

    Pillow's ICO writer may rebuild small frames from the largest image and
    ignore our extra-margin 16/20/24 px variants.  A tiny ICO writer keeps the
    exact PNG-encoded frames we prepared above.  PNG-compressed ICO frames are
    supported by Windows Vista+ and PyInstaller preserves them as resources.
    """
    encoded_frames: list[tuple[int, int, bytes]] = []
    for frame in frames:
        buffer = BytesIO()
        frame.save(buffer, format="PNG", optimize=True)
        encoded_frames.append((frame.width, frame.height, buffer.getvalue()))

    count = len(encoded_frames)
    header = struct.pack("<HHH", 0, 1, count)
    directory = bytearray()
    image_data = bytearray()
    offset = 6 + 16 * count
    for width, height, data in encoded_frames:
        directory.extend(
            struct.pack(
                "<BBBBHHII",
                0 if width == 256 else width,
                0 if height == 256 else height,
                0,
                0,
                1,
                32,
                len(data),
                offset,
            )
        )
        image_data.extend(data)
        offset += len(data)

    ICO_OUT.write_bytes(header + directory + image_data)


def main() -> None:
    src = _load_source()
    cropped = crop_to_content(src)
    print(f"After transparent-bg crop: {cropped.size} (was {src.size})")

    square = square_canvas(cropped)
    print(f"Square canvas: {square.size} (margin={SQUARE_MARGIN:.0%})")

    png_master = square.resize((256, 256), RESAMPLE_LANCZOS)
    png_master.save(PNG_OUT, format="PNG", optimize=True)
    print(f"Wrote {PNG_OUT.relative_to(ROOT)} ({png_master.size})")

    frames = build_frames(cropped, square)
    _save_ico(frames)
    print(f"Wrote {ICO_OUT.relative_to(ROOT)} with frames: {FRAME_SIZES}")

    verify = Image.open(ICO_OUT)
    print("Verified ICO frames:", sorted(verify.info.get("sizes", set())))


if __name__ == "__main__":
    main()
