"""Render Media/icon/icon.svg into platform icon assets.

Outputs (next to this script / in Media/icon/):
  icon_1024.png        master raster preview
  app.ico              Windows multi-size icon (used by PyInstaller)
  app.iconset/         macOS iconset (fed to iconutil -> app.icns)

Run with the project venv:  .venv/bin/python Media/icon/render_icon.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QImage, QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, "icon.svg")


def render(size: int) -> QImage:
    renderer = QSvgRenderer(QByteArray(open(SVG, "rb").read()))
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    renderer.render(p)
    p.end()
    return img


def main() -> int:
    app = QApplication(sys.argv)  # noqa: F841 (needed for QImage/SVG)

    # Master preview
    render(1024).save(os.path.join(HERE, "icon_1024.png"))

    # macOS .iconset
    iconset = os.path.join(HERE, "app.iconset")
    os.makedirs(iconset, exist_ok=True)
    for base in (16, 32, 128, 256, 512):
        render(base).save(os.path.join(iconset, f"icon_{base}x{base}.png"))
        render(base * 2).save(os.path.join(iconset, f"icon_{base}x{base}@2x.png"))

    # Windows .ico (Pillow packs multiple PNG-compressed sizes)
    try:
        from PIL import Image
        sizes = [16, 24, 32, 48, 64, 128, 256]
        master = os.path.join(HERE, "_ico_src.png")
        render(256).save(master)
        Image.open(master).save(
            os.path.join(HERE, "app.ico"),
            format="ICO",
            sizes=[(s, s) for s in sizes],
        )
        os.remove(master)
    except Exception as exc:  # pragma: no cover
        print(f"[warn] could not build app.ico via Pillow: {exc}")

    print("Rendered icon assets into", HERE)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
