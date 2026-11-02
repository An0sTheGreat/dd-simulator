"""Live resizing without live layout: a blurred still of the window while a drag lasts.

Laying out and painting the dashboard costs 50-65 ms a frame, far over the 16 ms a smooth
drag needs, so while the user drags a window edge (or the column divider) the content
keeps its old geometry under a slightly blurred snapshot, and the one real layout runs
when the drag ends.
"""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QGraphicsBlurEffect,
    QGraphicsPixmapItem,
    QGraphicsScene,
    QSplitter,
    QSplitterHandle,
    QWidget,
)

BLUR_RADIUS = 2  # at a third of the size, so ~6 px on screen: slight, still recognisable
BLUR_SCALE = 3


def blurred(pixmap: QPixmap) -> QPixmap:
    """A slight blur of ``pixmap``, done at a third of its size so it costs a few ms."""

    small = pixmap.toImage().scaled(
        max(1, pixmap.width() // BLUR_SCALE), max(1, pixmap.height() // BLUR_SCALE),
        Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation,
    )
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(QPixmap.fromImage(small))
    effect = QGraphicsBlurEffect()
    effect.setBlurRadius(BLUR_RADIUS)
    item.setGraphicsEffect(effect)
    scene.addItem(item)
    out = QImage(small.size(), QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.black)
    painter = QPainter(out)
    scene.render(painter, QRectF(out.rect()), QRectF(small.rect()))
    painter.end()
    return QPixmap.fromImage(out)


class ResizeVeil(QWidget):
    """Covers its parent with a stretched, blurred snapshot until ``lift``."""

    def __init__(self, parent: QWidget, snapshot: QPixmap) -> None:
        super().__init__(parent)
        self.setObjectName("resizeVeil")
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.image = blurred(snapshot)
        self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]
        # fast scaling: a blurred image hides the difference, and this must stay cheap
        QPainter(self).drawPixmap(self.rect(), self.image)


class ResizeHost(QWidget):
    """The window's central widget: lays out ``content`` except during a live resize."""

    def __init__(self, content: QWidget) -> None:
        super().__init__()
        self.setObjectName("resizeHost")
        self.content = content
        content.setParent(self)
        self.veil: ResizeVeil | None = None

    def minimumSizeHint(self) -> QSize:
        return self.content.minimumSizeHint()

    def sizeHint(self) -> QSize:
        return self.content.sizeHint()

    @property
    def live_resizing(self) -> bool:
        return self.veil is not None

    def begin_live_resize(self) -> None:
        if self.veil is None:
            self.veil = ResizeVeil(self, self.content.grab())

    def end_live_resize(self) -> None:
        if self.veil is None:
            return
        veil, self.veil = self.veil, None
        self.content.setGeometry(self.rect())  # the one real layout
        veil.hide()
        veil.deleteLater()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if self.veil is not None:
            self.veil.setGeometry(self.rect())
        else:
            self.content.setGeometry(self.rect())


class VeilSplitterHandle(QSplitterHandle):
    """While the divider is dragged, the panes stay put under a blurred snapshot; the
    splitter (opaque resize off) draws its line and moves them once on release."""

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        splitter = self.splitter()
        if event.button() == Qt.MouseButton.LeftButton and splitter is not None:
            splitter.veil = ResizeVeil(splitter, splitter.grab())
            self.raise_()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().mouseReleaseEvent(event)
        splitter = self.splitter()
        veil = getattr(splitter, "veil", None)
        if veil is not None:
            splitter.veil = None
            veil.hide()
            veil.deleteLater()


def install_veil_handles(splitter: QSplitter) -> None:
    splitter.setOpaqueResize(False)
    splitter.veil = None  # type: ignore[attr-defined]
