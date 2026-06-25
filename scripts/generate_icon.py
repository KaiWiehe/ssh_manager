"""
Regenerate Windows icon assets from assets/SSH-Logo.png.

Produces:
  * assets/ssh-manager.ico   – multi-frame ICO (16/20/24/32/40/48/64/128/256)
  * assets/ssh-manager.png   – 256x256 high-res PNG used by Tk's iconphoto()

The source PNG may be non-square; this script centers it on a transparent
square canvas (largest side, padded slightly) and downscales with LANCZOS so
each frame stays sharp – especially the small 16/20/24px frames that Windows
shows in the title bar / taskbar.

Run from repo root:
    python scripts/generate_icon.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "assets" / "SSH-Logo.png"
ICO_OUT = ROOT / "assets" / "ssh-manager.ico"
PNG_OUT = ROOT / "assets" / "ssh-manager.png"

# Frames Windows actually uses across DPI levels and contexts (title bar,
# taskbar, Alt+Tab, jumplists, Explorer thumbnails, …).
FRAME_SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]


def square_canvas(img: Image.Image) -> Image.Image:
    """Return a square RGBA copy of *img* with transparent padding."""
    img = img.convert("RGBA")
    side = max(img.size)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    offset = ((side - img.width) // 2, (side - img.height) // 2)
    canvas.paste(img, offset, img)
    return canvas


def build_frames(square: Image.Image) -> list[Image.Image]:
    """Downscale *square* (already square RGBA) to all target sizes."""
    frames: list[Image.Image] = []
    for size in FRAME_SIZES:
        if size == square.width:
            frames.append(square.copy())
        else:
            frames.append(square.resize((size, size), Image.LANCZOS))
    return frames


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Source logo not found: {SOURCE}")

    src = Image.open(SOURCE)
    print(f"Source: {SOURCE.name} {src.size} mode={src.mode}")

    square = square_canvas(src)
    print(f"Square canvas: {square.size}")

    # High-res PNG for Tk iconphoto() at runtime.
    png_master = square if square.width >= 256 else square.resize((256, 256), Image.LANCZOS)
    png_master = png_master.resize((256, 256), Image.LANCZOS) if png_master.width != 256 else png_master
    png_master.save(PNG_OUT, format="PNG", optimize=True)
    print(f"Wrote {PNG_OUT.relative_to(ROOT)} ({png_master.size})")

    frames = build_frames(square)
    # Pillow's ICO writer takes the largest image and the desired sizes list;
    # we hand it a 256² master and let it embed each requested size as a
    # separate frame. This keeps every frame sharp instead of letting Windows
    # rescale a single large frame at runtime.
    master = square.resize((256, 256), Image.LANCZOS) if square.width != 256 else square
    master.save(
        ICO_OUT,
        format="ICO",
        sizes=[(s, s) for s in FRAME_SIZES],
        bitmap_format="bmp",
    )
    print(f"Wrote {ICO_OUT.relative_to(ROOT)} with frames: {FRAME_SIZES}")

    # Verify what landed in the file.
    verify = Image.open(ICO_OUT)
    print("Verified ICO frames:", sorted(verify.info.get("sizes", set())))


if __name__ == "__main__":
    main()
