"""
Regenerate Windows icon assets from assets/SSH-Logo.png.

Produces:
  * assets/ssh-manager.ico   – multi-frame ICO (16/20/24/32/40/48/64/128/256)
  * assets/ssh-manager.png   – 256x256 high-res PNG used by Tk's iconphoto()

The source PNG may be non-square and may have an opaque white "card"
background instead of real alpha transparency.  Naively centering such an
image on a square canvas and downscaling produces a tiny grey/white square
in the Windows title bar / taskbar (the dark logo strokes get averaged
into the bright background and effectively vanish at 16/20/24 px).

This script therefore:

  1. Converts the source to RGBA.
  2. Treats near-white pixels as background and makes them transparent
     so the logo has an actual silhouette.
  3. Crops to the visible content bbox (alpha > threshold) so transparent
     padding around the artwork doesn't shrink the visible content.
  4. Pads the cropped logo onto a square transparent canvas with a small
     uniform margin so the icon isn't glued to the edge.
  5. Builds individual frames per target size.  Small frames (<= 32 px)
     get a dilation pass on the alpha channel before downscaling, so the
     thin strokes survive aggressive LANCZOS resampling and the taskbar
     icon doesn't end up almost blank.

Run from repo root::

    python scripts/generate_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "SSH-Logo.png"
ICO_OUT = ROOT / "assets" / "ssh-manager.ico"
PNG_OUT = ROOT / "assets" / "ssh-manager.png"

# Frames Windows actually uses across DPI levels and contexts (title bar,
# taskbar, Alt+Tab, jumplists, Explorer thumbnails, …).
FRAME_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

# Pixels brighter than this on every channel are considered background
# and get removed (alpha = 0).  The shipped logo is pure black on white,
# so 240 is a safe threshold that still keeps anti-aliased stroke edges.
WHITE_BG_THRESHOLD = 240

# Alpha threshold used to compute the content bounding box for cropping
# transparent padding around the artwork.
CONTENT_ALPHA_THRESHOLD = 16

# Fraction of the final canvas size to leave as transparent margin around
# the cropped logo (each side).  8% gives a visually balanced icon while
# still keeping the artwork large enough to read at 16 px.
SQUARE_MARGIN = 0.08

# Sizes at or below this get a dilation pass on the alpha channel before
# downscaling so thin strokes don't disappear.
DILATE_SIZE_LIMIT = 32


def remove_white_background(img: Image.Image) -> Image.Image:
    """Make near-white pixels transparent.

    The source artwork is dark strokes on a solid white card.  Without
    this step the entire square ends up opaque and the icon collapses
    into a uniform light square at small sizes.
    """
    img = img.convert("RGBA")
    pixels = img.load()
    w, h = img.size
    thr = WHITE_BG_THRESHOLD
    for y in range(h):
        for x in range(w):
            r, g, b, a = pixels[x, y]
            if a == 0:
                continue
            if r >= thr and g >= thr and b >= thr:
                pixels[x, y] = (r, g, b, 0)
    return img


def crop_to_content(img: Image.Image) -> Image.Image:
    """Crop *img* to its visible alpha bounding box."""
    alpha = img.split()[-1]
    # Threshold the alpha so anti-aliased edges count as content but pure
    # background does not.
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


def _dilate_alpha(img: Image.Image, radius: int = 2) -> Image.Image:
    """Thicken visible content by dilating the alpha channel.

    Used before heavy downscaling so thin black strokes survive in the
    16/20/24 px frames Windows actually shows in the title bar.
    """
    r, g, b, a = img.split()
    dilated = a.filter(ImageFilter.MaxFilter(radius * 2 + 1))
    return Image.merge("RGBA", (r, g, b, dilated))


def build_frames(square: Image.Image) -> list[Image.Image]:
    """Downscale *square* (already square RGBA) to all target sizes."""
    frames: list[Image.Image] = []
    src_side = square.width
    for size in FRAME_SIZES:
        if size <= DILATE_SIZE_LIMIT and src_side > size * 4:
            # Scale of the dilation kernel relative to source resolution.
            # Aim for ~1 final pixel of extra stroke weight.
            radius = max(1, int(round(src_side / size / 4)))
            frame_src = _dilate_alpha(square, radius=radius)
        else:
            frame_src = square
        if size == frame_src.width:
            frames.append(frame_src.copy())
        else:
            frames.append(frame_src.resize((size, size), Image.LANCZOS))
    return frames


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Source logo not found: {SOURCE}")

    src = Image.open(SOURCE)
    print(f"Source: {SOURCE.name} {src.size} mode={src.mode}")

    keyed = remove_white_background(src)
    cropped = crop_to_content(keyed)
    print(
        f"After bg removal + crop: {cropped.size}"
        f" (was {src.size})"
    )

    square = square_canvas(cropped)
    print(f"Square canvas: {square.size} (margin={SQUARE_MARGIN:.0%})")

    # High-res 256² PNG for Tk iconphoto() at runtime.  No dilation – at
    # 256² the strokes are plenty visible.
    png_master = (
        square if square.width == 256 else square.resize((256, 256), Image.LANCZOS)
    )
    png_master.save(PNG_OUT, format="PNG", optimize=True)
    print(f"Wrote {PNG_OUT.relative_to(ROOT)} ({png_master.size})")

    frames = build_frames(square)

    # Pillow's ICO writer prefers a single source image plus a sizes list,
    # but that re-runs LANCZOS for every frame which is exactly what we
    # want to avoid (thin strokes disappear at 16 px).  Instead we save
    # the pre-baked frames via append_images so each ICO entry is the
    # individually optimized version we just built.
    largest = max(frames, key=lambda f: f.width)
    others = [f for f in frames if f is not largest]
    largest.save(
        ICO_OUT,
        format="ICO",
        sizes=[(f.width, f.height) for f in frames],
        append_images=others,
        bitmap_format="bmp",
    )
    print(f"Wrote {ICO_OUT.relative_to(ROOT)} with frames: {FRAME_SIZES}")

    # Verify what landed in the file.
    verify = Image.open(ICO_OUT)
    print("Verified ICO frames:", sorted(verify.info.get("sizes", set())))


if __name__ == "__main__":
    main()
