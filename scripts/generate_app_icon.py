"""Generate the application icon: a gold d20 on a crimson tile with a gold rim.

Usage: python scripts/generate_app_icon.py
Writes src/dd_simulator/ui/assets/icons/app/dd_simulator.ico (16-256 px, PNG entries)
and dd_simulator.png (512 px, for the window icon and docs). Each size is drawn with
QPainter at that size, so small icons stay crisp; the "20" is left off below 48 px.
Original art; reruns produce the same pixels.
"""

from __future__ import annotations

import math
import struct
from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontDatabase,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPolygonF,
    QRadialGradient,
)

ASSETS = Path(__file__).resolve().parents[1] / "src" / "dd_simulator" / "ui" / "assets"
OUT = ASSETS / "icons" / "app"
FONT = ASSETS / "fonts" / "Oxanium-Bold.ttf"  # bundled, so every machine draws the same "20"
ICO_SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
LIGHT = (-0.55, -0.83)  # from the upper left


def _tile(p: QPainter, s: float) -> None:
    rect = QRectF(0.03 * s, 0.03 * s, 0.94 * s, 0.94 * s)
    radius = 0.22 * s
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    glow = QRadialGradient(QPointF(0.42 * s, 0.36 * s), 0.75 * s)
    glow.setColorAt(0.0, QColor("#8e2a2c"))
    glow.setColorAt(0.65, QColor("#4a1316"))
    glow.setColorAt(1.0, QColor("#24090b"))
    p.fillPath(path, glow)
    rim = max(1.0, 0.035 * s)
    inset = rect.adjusted(rim / 2, rim / 2, -rim / 2, -rim / 2)
    border = QPainterPath()
    border.addRoundedRect(inset, radius - rim / 2, radius - rim / 2)
    gold = QLinearGradient(0, 0, 0, s)
    gold.setColorAt(0.0, QColor("#f2d48a"))
    gold.setColorAt(1.0, QColor("#8a5f26"))
    p.setPen(QPen(gold, rim))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawPath(border)


def _d20(p: QPainter, s: float) -> None:
    cx, cy, r = 0.5 * s, 0.515 * s, 0.355 * s

    def at(x: float, y: float) -> QPointF:
        return QPointF(cx + x * r, cy + y * r)

    h = [at(math.cos(math.radians(a)), -math.sin(math.radians(a))) for a in (90, 30, -30, -90, -150, 150)]
    t0, t1, t2 = at(0, -0.5), at(-0.52, 0.34), at(0.52, 0.34)
    faces = [
        (h[5], h[0], t0), (h[0], h[1], t0),  # top
        (h[5], t0, t1), (h[1], t2, t0),  # upper sides
        (h[5], t1, h[4]), (h[1], h[2], t2),  # sides
        (h[4], t1, h[3]), (h[2], h[3], t2),  # lower sides
        (t1, t2, h[3]),  # bottom
    ]
    shadow = QRadialGradient(QPointF(cx + 0.04 * s, cy + 0.05 * s), r * 1.2)
    shadow.setColorAt(0.0, QColor(0, 0, 0, 120))
    shadow.setColorAt(1.0, QColor(0, 0, 0, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(shadow)
    p.drawEllipse(QPointF(cx + 0.04 * s, cy + 0.05 * s), r * 1.15, r * 1.15)

    edge = QPen(QColor("#3b240e"), max(0.6, 0.012 * s))
    edge.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    for face in faces:
        mx = sum(pt.x() for pt in face) / 3 - cx
        my = sum(pt.y() for pt in face) / 3 - cy
        length = math.hypot(mx, my) or 1.0
        lit = 0.55 + 0.45 * ((mx * LIGHT[0] + my * LIGHT[1]) / length)
        p.setBrush(_gold(lit))
        p.setPen(edge)
        p.drawPolygon(QPolygonF(list(face)))
    front = QLinearGradient(t0, QPointF(cx, t1.y()))
    front.setColorAt(0.0, QColor("#fff0bd"))
    front.setColorAt(1.0, QColor("#e3b65c"))
    p.setBrush(front)
    p.drawPolygon(QPolygonF([t0, t1, t2]))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.setPen(QPen(QColor("#2e1b0a"), max(0.8, 0.02 * s)))
    p.drawPolygon(QPolygonF(h))

    if s >= 48:
        family = QFontDatabase.applicationFontFamilies(QFontDatabase.addApplicationFont(str(FONT)))[0]
        font = QFont(family)
        font.setBold(True)
        font.setPixelSize(max(9, round(0.19 * s)))
        p.setFont(font)
        p.setPen(QColor("#4a1316"))
        p.drawText(QRectF(cx - 0.3 * r, cy - 0.1 * r, 0.6 * r, 0.42 * r), Qt.AlignmentFlag.AlignCenter, "20")


def _gold(lit: float) -> QColor:
    dark, light = QColor("#6e4a1c"), QColor("#f4d27e")
    k = max(0.0, min(1.0, lit))
    return QColor(
        round(dark.red() + (light.red() - dark.red()) * k),
        round(dark.green() + (light.green() - dark.green()) * k),
        round(dark.blue() + (light.blue() - dark.blue()) * k),
    )


def render(size: int) -> QImage:
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    _tile(p, size)
    _d20(p, size)
    p.end()
    return image


def _png(image: QImage) -> bytes:
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return bytes(data)


def write_ico(path: Path, sizes: tuple[int, ...]) -> None:
    """ICO container with one PNG entry per size (Windows Vista and later)."""

    blobs = [_png(render(size)) for size in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = len(header) + 16 * len(sizes)
    entries = b""
    for size, blob in zip(sizes, blobs):
        side = 0 if size >= 256 else size  # 0 means 256 in the directory
        entries += struct.pack("<BBBBHHII", side, side, 0, 0, 1, 32, len(blob), offset)
        offset += len(blob)
    path.write_bytes(header + entries + b"".join(blobs))


def main() -> int:
    _app = QGuiApplication.instance() or QGuiApplication([])
    OUT.mkdir(parents=True, exist_ok=True)
    write_ico(OUT / "dd_simulator.ico", ICO_SIZES)
    render(512).save(str(OUT / "dd_simulator.png"))
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
