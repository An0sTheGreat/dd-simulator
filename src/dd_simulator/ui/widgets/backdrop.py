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
import random
import re

from PySide6.QtCore import QEvent, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
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


def dithered(path: str, size: QSize, ratio: float = 1.0) -> QPixmap:
    """``path`` stretched to ``size`` (logical) at ``ratio`` device pixels per logical one,
    with 16-bit interpolation and triangular dither, so nothing rescales it afterwards
    (a rescale would smooth the dither away again)."""

    source = QImage(path)
    if source.isNull() or size.isEmpty():
        return QPixmap()
    pixels = QSize(round(size.width() * ratio), round(size.height() * ratio))
    wide = source.convertToFormat(QImage.Format.Format_RGBA64).scaled(
        pixels, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    # minus one step (invert, add, invert), so the 0..2 step noise averages to zero
    step = QImage(1, 1, QImage.Format.Format_RGBA64)
    step.fill(QColor.fromRgba64(256, 256, 256, 0xFFFF))
    wide.invertPixels()
    painter = QPainter(wide)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.drawImage(wide.rect(), step)
    painter.end()
    wide.invertPixels()
    painter = QPainter(wide)
    painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    painter.drawTiledPixmap(wide.rect(), QPixmap.fromImage(_noise()))
    painter.end()
    pixmap = QPixmap.fromImage(wide.convertToFormat(QImage.Format.Format_RGB32))
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


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
        self._rebuild.setInterval(120)  # once a resize drag settles; meanwhile it stretches
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
        else:  # mid-resize, until the rebuild timer fires
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(self.rect(), self._pixmap)
