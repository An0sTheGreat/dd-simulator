"""Flatten the speckled fill of the imported codex frame art.

Usage: python scripts/flatten_codex_speckle.py  (rerun after scripts/import_codex_assets.py)
The panel, tooltip, button and tab frames are small images stretched over large cards,
so their faint speckles became blotchy low-resolution spots. The speckle is mostly in
the alpha channel (the page shows through), so every mostly opaque pixel whose colour is
close to the image's dominant fill gets exactly that fill, opacity included; the gold
rims and corner ornaments are far from it and stay as they are.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from PySide6.QtGui import QColor, QGuiApplication, QImage

CODEX = Path(__file__).resolve().parents[1] / "src" / "dd_simulator" / "ui" / "assets" / "codex"
FRAMES = (
    "ui_panel_large", "ui_panel_small", "ui_quest_tracker", "ui_tooltip",
    "ui_button_normal", "ui_button_hover", "ui_button_pressed", "ui_button_disabled",
    "ui_tab_normal", "ui_tab_active",
)
TOLERANCE = 12  # per colour channel; the speckles sit within a few levels of the fill
MIN_ALPHA = 150  # leaves the anti-aliased outer edge alone


def flatten(path: Path) -> int:
    image = QImage(str(path)).convertToFormat(QImage.Format.Format_ARGB32)
    w, h = image.width(), image.height()
    pixels = [image.pixelColor(x, y) for y in range(h) for x in range(w)]
    fill = Counter(c.rgba() for c in pixels if c.alpha() >= MIN_ALPHA).most_common(1)[0][0]
    base = QColor.fromRgba(fill)
    changed = 0
    for y in range(h):
        for x in range(w):
            c = image.pixelColor(x, y)
            if c.alpha() >= MIN_ALPHA and c.rgba() != fill and all(
                abs(a - b) <= TOLERANCE
                for a, b in ((c.red(), base.red()), (c.green(), base.green()), (c.blue(), base.blue()))
            ):
                image.setPixelColor(x, y, base)
                changed += 1
    image.save(str(path))
    return changed


def main() -> int:
    _app = QGuiApplication.instance() or QGuiApplication([])
    for name in FRAMES:
        path = CODEX / f"{name}.png"
        if path.is_file():
            print(f"{name}: {flatten(path)} speckle pixels flattened")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
