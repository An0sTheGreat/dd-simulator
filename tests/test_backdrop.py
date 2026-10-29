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


def test_scaled_displays_get_the_backdrop_at_device_resolution() -> None:
    QApplication.instance() or QApplication([])
    pixmap = dithered(str(BACKGROUND), QSize(1600, 900), 1.25)
    # drawn 1:1 on a 125 % display, so no rescale smooths the dither away
    assert (pixmap.width(), pixmap.height()) == (2000, 1125)
    assert pixmap.devicePixelRatio() == 1.25


def test_shipped_backgrounds_are_painted_without_the_jpg_staircase() -> None:
    from dd_simulator.ui.widgets import backdrop

    QApplication.instance() or QApplication([])
    size = QSize(1720, 720)
    truth = backdrop._paint_recipe("background_stone", size)  # 16-bit reference gradient
    smooth = dithered(str(BACKGROUND), size).toImage()

    def patch_error(x0: int, y0: int, n: int = 32) -> float:
        cells = [(x, y) for x in range(x0, x0 + n) for y in range(y0, y0 + n // 2)]
        shown = sum(smooth.pixelColor(x, y).red() for x, y in cells) / len(cells)
        true = sum(truth.pixelColor(x, y).redF() for x, y in cells) / len(cells) * 255
        return abs(shown - true)

    # Averaged over a patch, the dithered 8-bit image tracks the true gradient to a small
    # fraction of a step. The stretched JPG's bands were off by up to a whole step, and
    # noise rounded to whole steps (an 8-bit tile) still left about a third of one.
    errors = [patch_error(860, y) for y in range(0, 690, 30)] + [patch_error(x, 150) for x in range(0, 1680, 60)]
    assert max(errors) < 0.15
