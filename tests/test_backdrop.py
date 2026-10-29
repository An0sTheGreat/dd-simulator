from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from dd_simulator.ui.widgets.backdrop import dithered, stylesheet_backdrop

BACKGROUND = (
    Path(__file__).resolve().parents[1]
    / "src" / "dd_simulator" / "ui" / "themes" / "high_fantasy" / "assets" / "background_stone.jpg"
)


def _longest_flat_run(image: QImage, y: int) -> int:
    best = run = 1
    previous = image.pixel(0, y)
    for x in range(1, image.width()):
        pixel = image.pixel(x, y)
        run = run + 1 if pixel == previous else 1
        best = max(best, run)
        previous = pixel
    return best


def test_ultrawide_backdrop_is_dithered_instead_of_banded() -> None:
    QApplication.instance() or QApplication([])
    size = QSize(3440, 1440)
    plain = QImage(str(BACKGROUND)).scaled(
        size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    smooth = dithered(str(BACKGROUND), size).toImage()
    assert smooth.size() == size
    for y in (100, 700):
        # a plain stretch leaves bands hundreds of pixels wide; the dither breaks them up
        assert _longest_flat_run(plain, y) > 100
        assert _longest_flat_run(smooth, y) < 20
    # and keeps the colour: the average stays within a step of the plain stretch
    for x, y in ((200, 200), (1720, 700), (3200, 1300)):
        a, b = plain.pixelColor(x, y), smooth.pixelColor(x, y)
        assert abs(a.lightness() - b.lightness()) <= 3


def test_backdrop_path_comes_from_the_application_root_rule() -> None:
    qss = 'QWidget#applicationRoot {\n  border-image: url("C:/x/bg.jpg") 0 0 0 0 stretch stretch;\n}'
    assert stylesheet_backdrop(qss) == "C:/x/bg.jpg"
    assert stylesheet_backdrop("QLabel { color: red; }") is None
