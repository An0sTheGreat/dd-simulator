"""Check narrator text contrast over every packaged location image in both shipped themes.

Each image is painted as SceneView paints it (cover-fit art under the overlay gradient) into an
832x876 scene. Over the conversation band (45-80% of the height) the 98th percentile of pixel
relative luminance is compared with the theme's QLabel#conversationNarrator colour.
Exits 1 if any WCAG contrast ratio is below 4.5:1.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QRect  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPixmap  # noqa: E402

from dd_simulator.ui.themes.theme_manager import ThemeManager  # noqa: E402
from dd_simulator.ui.widgets.scene_view import paint_backdrop  # noqa: E402

UI = ROOT / "src" / "dd_simulator" / "ui"
SCENE = (832, 876)
BAND = (0.45, 0.80)
PERCENTILE = 0.98
MINIMUM = 4.5
# The narrator text colour; the lookbehind keeps background-color: from matching.
NARRATOR_COLOR = re.compile(r"QLabel#conversationNarrator\s*\{[^}]*?(?<![-\w])color:\s*([^;}\s]+)")
LINEAR = [(c / 255 / 12.92) if c <= 10 else ((c / 255 + 0.055) / 1.055) ** 2.4 for c in range(256)]


def theme_colors() -> dict[str, tuple[QColor, QColor]]:
    """theme id -> (overlay colour, narrator colour), read from the compiled QSS."""

    manager = ThemeManager(
        themes_root=UI / "themes",
        preferences_path=Path(tempfile.gettempdir()) / "unused-contrast-preferences.json",
        default_theme_id="high_fantasy",
    )
    colors = {}
    for theme_id, loaded in manager.discover().items():
        qss = loaded.stylesheet
        overlay = re.search(r"QWidget#sceneView\s*\{[^}]*qproperty-overlayColor:\s*([^;}\s]+)", qss)
        narrator = NARRATOR_COLOR.search(qss)
        colors[theme_id] = (QColor(overlay.group(1)), QColor(narrator.group(1)))
    return colors


def luminance(color: QColor) -> float:
    return 0.2126 * LINEAR[color.red()] + 0.7152 * LINEAR[color.green()] + 0.0722 * LINEAR[color.blue()]


def contrast(a: float, b: float) -> float:
    return (max(a, b) + 0.05) / (min(a, b) + 0.05)


def band_luminance(path: Path, overlay: QColor) -> float:
    """98th-percentile relative luminance of the conversation-band pixels."""

    width, height = SCENE
    image = QImage(width, height, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    paint_backdrop(painter, QRect(0, 0, width, height), QPixmap(str(path)), overlay)
    painter.end()
    top, bottom = (round(height * edge) for edge in BAND)
    data = bytes(image.constBits())[top * width * 4 : bottom * width * 4]  # BGRA rows, no padding
    values = sorted(
        0.0722 * LINEAR[b] + 0.7152 * LINEAR[g] + 0.2126 * LINEAR[r] for b, g, r in zip(data[0::4], data[1::4], data[2::4])
    )
    return values[round(PERCENTILE * (len(values) - 1))]


def image_paths() -> list[Path]:
    return sorted((UI / "assets" / "location").glob("*/*.png"))


def main() -> int:
    _app = QGuiApplication.instance() or QGuiApplication([])
    failed = False
    for theme_id, (overlay, narrator) in theme_colors().items():
        text = luminance(narrator)
        ratios = [(contrast(text, band_luminance(path, overlay)), path) for path in image_paths()]
        worst, path = min(ratios)
        below = sum(ratio < MINIMUM for ratio, _ in ratios)
        print(f"{theme_id}: worst {worst:.2f}:1 on {path.parent.name}/{path.name}; {below}/{len(ratios)} below {MINIMUM}:1")
        failed |= below > 0
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
