"""Window backdrop scaled without colour banding.

The themes' page backgrounds are 1280x720 gradients. Stretched by QSS onto a large or
ultrawide window, each 8-bit step becomes a wide visible band, and Windows HDR mode
(which maps SDR content into its wider range) makes those bands stand out more. Qt
Widgets cannot output 10-bit colour, so instead the image is upscaled at 16 bits per
channel, where the steps blend into a smooth ramp, then dithered back to 8 bits. That
removes banding on SDR and HDR displays alike.

The background image stays declared in the theme QSS (QWidget#applicationRoot
border-image); this widget reads it from the application stylesheet.
"""

from __future__ import annotations

from functools import lru_cache
import math
from pathlib import Path
import random
import re

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication, QStyle, QStyleOption, QWidget

from dd_simulator.ui.themes.theme_manager import URL_PATTERN

ROOT_RULE = re.compile(r"QWidget#applicationRoot\s*\{(?P<body>[^}]*)\}")
NOISE_SIDE = 64


@lru_cache(maxsize=1)
def _noise() -> QImage:
    """Triangular grey noise of 0 to 2 eight-bit steps, at 16 bits per channel, for ``Plus``.

    Two steps wide (rather than one) because Windows HDR mode brightens SDR content and
    stretches every 8-bit step; ``dithered`` takes one step off first, so it is centred.
    """

    rnd = random.Random(7)  # fixed, so the dither pattern never shimmers between paints
    data = bytearray()
    for _ in range(NOISE_SIDE * NOISE_SIDE):
        level = rnd.randrange(256) + rnd.randrange(256)  # 1/256 of an 8-bit step per unit
        # opaque: Plus adds premultiplied colour, so a transparent tile would add nothing
        data += level.to_bytes(2, "little") * 3 + (0xFFFF).to_bytes(2, "little")
    image = QImage(bytes(data), NOISE_SIDE, NOISE_SIDE, NOISE_SIDE * 8, QImage.Format.Format_RGBA64)
    return image.copy()


# The two shipped backgrounds, as scripts/generate_chrome_textures.py draws them (keep the
# two in step): base colour, a glow from above the top centre (Screen), and an optional
# vignette. Painted live at 16 bits per channel, because the saved 8-bit JPG already holds
# the gradient as a staircase of steps that no upscale or dither can smooth out again.
DESIGN = QSize(1280, 720)  # the generator's canvas; scaled to the window, as the JPG was
RECIPES = {
    "background_stone": (
        "#16140f",
        ((0.0, (255, 168, 82, 70)), (0.45, (220, 120, 50, 26)), (1.0, (0, 0, 0, 0))),
        200,
    ),
    "background_charcoal": (
        "#0d0d0e",
        ((0.0, (150, 152, 160, 34)), (0.5, (90, 92, 100, 10)), (1.0, (0, 0, 0, 0))),
        0,
    ),
}


def _paint_recipe(name: str, pixels: QSize) -> QImage:
    base, glow_stops, vignette_alpha = RECIPES[name]
    image = QImage(pixels, QImage.Format.Format_RGBA64)
    image.fill(QColor(base))
    w, h = DESIGN.width(), DESIGN.height()
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(pixels.width() / w, pixels.height() / h)
    glow = QRadialGradient(QPointF(w / 2, -h * 0.15), h * 1.05)
    for at, rgba in glow_stops:
        glow.setColorAt(at, QColor(*rgba))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
    painter.fillRect(QRectF(0, 0, w, h), QBrush(glow))
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    if vignette_alpha:
        shade = QRadialGradient(QPointF(w / 2, h * 0.35), math.hypot(w, h) * 0.58)
        shade.setColorAt(0.0, QColor(0, 0, 0, 0))
        shade.setColorAt(0.45, QColor(0, 0, 0, 0))
        shade.setColorAt(1.0, QColor(0, 0, 0, vignette_alpha))
        painter.fillRect(QRectF(0, 0, w, h), QBrush(shade))
    painter.end()
    return image


def _to_dithered_pixmap(wide: QImage, ratio: float) -> QPixmap:
    """16-bit image to 8 bits with centred triangular dither (no banding)."""

    # minus one step (invert, add, invert), so the 0..2 step noise averages to zero
    step = QImage(1, 1, QImage.Format.Format_RGBA64)
    step.fill(QColor.fromRgba64(256, 256, 256, 0xFFFF))
    wide.invertPixels()
    painter = QPainter(wide)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.drawImage(wide.rect(), step)
    painter.end()
    wide.invertPixels()
    # The noise stays a 16-bit QImage: a QPixmap would store it at 8 bits, rounding the
    # sub-step noise to whole steps, which adds grain but keeps the bands.
    noise = _noise()
    painter = QPainter(wide)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    for y in range(0, wide.height(), NOISE_SIDE):
        for x in range(0, wide.width(), NOISE_SIDE):
            painter.drawImage(x, y, noise)
    painter.end()
    pixmap = QPixmap.fromImage(wide.convertToFormat(QImage.Format.Format_RGB32))
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def dithered(path: str, size: QSize, ratio: float = 1.0) -> QPixmap:
    """The backdrop for ``size`` (logical) at ``ratio`` device pixels per logical one,
    so nothing rescales it afterwards (a rescale would smooth the dither away again).
    A shipped background is repainted from its recipe; any other image is upscaled at
    16 bits per channel."""

    if size.isEmpty():
        return QPixmap()
    pixels = QSize(round(size.width() * ratio), round(size.height() * ratio))
    name = Path(path).stem
    if name in RECIPES:
        return _to_dithered_pixmap(_paint_recipe(name, pixels), ratio)
    source = QImage(path)
    if source.isNull():
        return QPixmap()
    wide = source.convertToFormat(QImage.Format.Format_RGBA64).scaled(
        pixels, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    return _to_dithered_pixmap(wide, ratio)


def stylesheet_backdrop(stylesheet: str) -> str | None:
    rule = ROOT_RULE.search(stylesheet)
    match = URL_PATTERN.search(rule["body"]) if rule else None
    return match["path"] if match else None


class BackdropRoot(QWidget):
    """The window's root widget: paints the theme backdrop, dithered, at its own size."""

    def __init__(self) -> None:
        super().__init__()
        self._path: str | None = None
        self._pixmap = QPixmap()
        self._rebuild = QTimer(self)
        self._rebuild.setSingleShot(True)
        self._rebuild.setInterval(300)  # once a resize drag settles; meanwhile it stretches
        self._rebuild.timeout.connect(self._render)

    def _render(self) -> None:
        application = QApplication.instance()
        self._path = stylesheet_backdrop(application.styleSheet()) if application else None
        ratio = self.devicePixelRatioF()
        self._pixmap = dithered(self._path, self.size(), ratio) if self._path else QPixmap()
        self.update()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if self._pixmap.isNull():
            self._render()
        else:
            self._rebuild.start()

    def changeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().changeEvent(event)
        # a theme switch restyles the app; a move to a screen with other scaling
        if event.type() in (QEvent.Type.StyleChange, QEvent.Type.DevicePixelRatioChange):
            self._rebuild.start()

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        painter = QPainter(self)
        if self._pixmap.isNull():
            # no backdrop image: the stylesheet's own background colour
            option = QStyleOption()
            option.initFrom(self)
            self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, option, painter, self)
            return
        if self._pixmap.deviceIndependentSize().toSize() == self.size():
            painter.drawPixmap(0, 0, self._pixmap)  # 1:1 on the device, dither intact
        else:  # mid-resize, until the rebuild timer fires: fast scaling keeps the drag smooth
            painter.drawPixmap(self.rect(), self._pixmap)
