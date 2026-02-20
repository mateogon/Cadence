from __future__ import annotations

from pathlib import Path

from PIL import Image
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer


def render_svg_to_png(svg_path: Path, png_path: Path, size: int) -> None:
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {svg_path}")

    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(painter)
    painter.end()
    image.save(str(png_path), "PNG")


def tighten_icon(image: Image.Image, fill_ratio: float = 0.9) -> Image.Image:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox()
    if not bbox:
        return rgba

    cropped = rgba.crop(bbox)
    w, h = rgba.size
    target_side = int(min(w, h) * max(0.5, min(0.98, fill_ratio)))
    cw, ch = cropped.size
    if cw == 0 or ch == 0:
        return rgba

    scale = min(target_side / cw, target_side / ch)
    nw = max(1, int(round(cw * scale)))
    nh = max(1, int(round(ch * scale)))
    resized = cropped.resize((nw, nh), Image.Resampling.LANCZOS)

    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ox = (w - nw) // 2
    oy = (h - nh) // 2
    out.paste(resized, (ox, oy), resized)
    return out


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    branding = root / "assets" / "branding"
    svg_path = branding / "cadence-logo.svg"
    ico_path = branding / "cadence-logo.ico"
    if not svg_path.exists():
        raise FileNotFoundError(f"Missing SVG: {svg_path}")

    sizes = [16, 24, 32, 48, 64, 128, 256]
    master_png = branding / ".cadence-logo-master.png"
    render_svg_to_png(svg_path, master_png, 1024)
    master = Image.open(master_png).convert("RGBA")
    master_tight = tighten_icon(master, fill_ratio=0.9)

    tmp_pngs: list[Path] = []
    for s in sizes:
        png_path = branding / f".cadence-logo-{s}.png"
        resized = master_tight.resize((s, s), Image.Resampling.LANCZOS)
        resized.save(png_path, format="PNG")
        tmp_pngs.append(png_path)

    base = Image.open(tmp_pngs[-1]).convert("RGBA")
    base.save(str(ico_path), format="ICO", sizes=[(s, s) for s in sizes])

    for p in [master_png, *tmp_pngs]:
        try:
            p.unlink()
        except OSError:
            pass

    print(f"Wrote: {ico_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
