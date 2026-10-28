"""Generate the title-bar ornaments and page backgrounds for both shipped themes.

Usage: python scripts/generate_chrome_textures.py
Writes into src/dd_simulator/ui/themes/<theme>/assets/. Everything is drawn with QPainter
and noise from fixed per-layer seeds, so the output is original art and reruns produce
the same pixels.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)

THEMES = Path(__file__).resolve().parents[1] / "src" / "dd_simulator" / "ui" / "themes"
W, H = 1280, 720
RULE_H = 26  # header crest-rule strip height; the hairline sits at RULE_Y
RULE_Y = 17


def noise(w: int, h: int, seed: int) -> QImage:
    rnd = random.Random(seed)
    return QImage(rnd.randbytes(w * h), w, h, w, QImage.Format.Format_Grayscale8).copy()


def overlay_noise(p: QPainter, cells_w: int, seed: int, opacity: float) -> None:
    cells_h = max(2, round(cells_w * H / W))
    img = noise(cells_w, cells_h, seed).scaled(
        W, H, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )
    p.save()
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Overlay)
    p.setOpacity(opacity)
    p.drawImage(0, 0, img)
    p.restore()


def grain(p: QPainter, w: int, h: int, opacity: float, seed: int) -> None:
    p.save()
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Overlay)
    p.setOpacity(opacity)
    p.drawTiledPixmap(0, 0, w, h, QPixmap.fromImage(noise(512, 512, seed)))
    p.restore()


def cracks(p: QPainter, seed: int, count: int, color: QColor) -> None:
    rnd = random.Random(seed)
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(color, 1.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for _ in range(count):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H)
        path = QPainterPath(QPointF(x, y))
        angle = rnd.uniform(0, math.tau)
        for _ in range(rnd.randint(4, 9)):
            angle += rnd.uniform(-0.7, 0.7)
            step = rnd.uniform(10, 34)
            x, y = x + math.cos(angle) * step, y + math.sin(angle) * step
            path.lineTo(x, y)
        p.drawPath(path)
    p.restore()


def vignette(p: QPainter, w: int, h: int, alpha: int, center: QPointF, radius: float) -> None:
    g = QRadialGradient(center, radius)
    g.setColorAt(0.0, QColor(0, 0, 0, 0))
    g.setColorAt(0.45, QColor(0, 0, 0, 0))
    g.setColorAt(1.0, QColor(0, 0, 0, alpha))
    p.fillRect(0, 0, w, h, QBrush(g))


def top_glow(p: QPainter, w: int, h: int, stops: tuple[tuple[float, QColor], ...]) -> None:
    g = QRadialGradient(QPointF(w / 2, -h * 0.15), h * 1.05)
    for at, color in stops:
        g.setColorAt(at, color)
    p.save()
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Screen)
    p.fillRect(0, 0, w, h, QBrush(g))
    p.restore()


def stone(out: Path) -> None:
    """High Fantasy: dark stone lit by candlelight from the top, with fine noise."""
    img = QImage(W, H, QImage.Format.Format_RGB32)
    img.fill(QColor("#16140f"))
    p = QPainter(img)
    overlay_noise(p, 6, 11, 0.55)
    overlay_noise(p, 18, 12, 0.45)
    overlay_noise(p, 60, 13, 0.25)
    cracks(p, 14, 26, QColor(0, 0, 0, 90))
    grain(p, W, H, 0.16, 15)
    top_glow(
        p, W, H,
        ((0.0, QColor(255, 168, 82, 70)), (0.45, QColor(220, 120, 50, 26)), (1.0, QColor(0, 0, 0, 0))),
    )
    vignette(p, W, H, 200, QPointF(W / 2, H * 0.35), math.hypot(W, H) * 0.58)
    p.end()
    img.save(str(out / "background_stone.jpg"), "JPG", 80)


def charcoal(out: Path) -> None:
    """Modern Dark: flat deep charcoal with a faint cool glow from the top."""
    w, h = 640, 360
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor("#0d0d0e"))
    p = QPainter(img)
    top_glow(
        p, w, h,
        ((0.0, QColor(150, 152, 160, 34)), (0.5, QColor(90, 92, 100, 10)), (1.0, QColor(0, 0, 0, 0))),
    )
    grain(p, w, h, 0.03, 31)  # dithers the gradient so the JPG does not band
    p.end()
    img.save(str(out / "background_charcoal.jpg"), "JPG", 88)


def diamond(p: QPainter, cx: float, cy: float, r: float, fill: QColor) -> None:
    path = QPainterPath(QPointF(cx, cy - r))
    for x, y in ((cx + r, cy), (cx, cy + r), (cx - r, cy)):
        path.lineTo(x, y)
    path.closeSubpath()
    p.fillPath(path, fill)


def canvas(w: int, h: int) -> tuple[QImage, QPainter]:
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    return img, p


def with_alpha(color: QColor, alpha: int) -> QColor:
    c = QColor(color)
    c.setAlpha(alpha)
    return c


def save_mirrored(img: QImage, out: Path, stem: str) -> None:
    img.save(str(out / f"{stem}_left.png"))
    img.flipped(Qt.Orientation.Horizontal).save(str(out / f"{stem}_right.png"))


def title_rules(out: Path, color: QColor) -> None:
    """Hairlines either side of the campaign title, ending in a diamond by the title."""
    w, h = 300, 24
    img, p = canvas(w, h)
    g = QLinearGradient(0, 0, w, 0)
    g.setColorAt(0, with_alpha(color, 0))
    g.setColorAt(1, with_alpha(color, 230))
    p.fillRect(QRectF(0, h / 2 - 0.5, w - 16, 1), QBrush(g))
    diamond(p, w - 8, h / 2, 4, color)
    p.end()
    save_mirrored(img, out, "title_rule")


def header_rules(out: Path, color: QColor) -> None:
    """Left/right halves of the page-wide hairline under the header; stretched to width."""
    w = 600
    img, p = canvas(w, RULE_H)
    g = QLinearGradient(0, 0, w, 0)
    for at, alpha in ((0.0, 0), (0.44, 40), (0.84, 200), (1.0, 230)):
        g.setColorAt(at, with_alpha(color, alpha))
    p.fillRect(QRectF(0, RULE_Y - 0.5, w, 1), QBrush(g))
    p.end()
    save_mirrored(img, out, "header_rule")


def shield_crest(out: Path, gold: QColor, gold_hi: QColor) -> None:
    """High Fantasy: small heater shield centred on the hairline."""
    w = 64
    img, p = canvas(w, RULE_H)
    cx, y = w / 2, RULE_Y
    p.fillRect(QRectF(0, y - 0.5, w, 1), with_alpha(gold, 230))
    shield = QPainterPath(QPointF(cx - 10, y - 12))
    shield.lineTo(cx + 10, y - 12)
    shield.lineTo(cx + 10, y - 3)
    shield.cubicTo(cx + 10, y + 3, cx + 5, y + 6, cx, y + 8)
    shield.cubicTo(cx - 5, y + 6, cx - 10, y + 3, cx - 10, y - 3)
    shield.closeSubpath()
    p.fillPath(shield.translated(0, 1.0), QColor(0, 0, 0, 170))
    fill = QLinearGradient(0, y - 12, 0, y + 8)
    fill.setColorAt(0, QColor("#3b2b17"))
    fill.setColorAt(1, QColor("#1a130b"))
    p.fillPath(shield, QBrush(fill))
    p.setPen(QPen(gold, 1.4))
    p.drawPath(shield)
    diamond(p, cx, y - 3, 4, gold_hi)
    for sign in (-1, 1):
        diamond(p, cx + sign * 18, y, 2.5, gold)
    p.end()
    img.save(str(out / "header_crest.png"))


def flat_crest(out: Path, color: QColor) -> None:
    """Modern Dark: an outlined diamond on the hairline, no shading."""
    w = 64
    img, p = canvas(w, RULE_H)
    cx, y = w / 2, RULE_Y
    p.fillRect(QRectF(0, y - 0.5, w, 1), with_alpha(color, 230))
    diamond(p, cx, y, 7, color)
    diamond(p, cx, y, 5.2, QColor("#0d0d0e"))
    diamond(p, cx, y, 2.4, color)
    p.end()
    img.save(str(out / "header_crest.png"))


def dropdown_arrow(out: Path, color: QColor) -> None:
    """Modern Dark: a thin chevron for the underline theme combo."""
    img, p = canvas(10, 6)
    p.setPen(QPen(color, 1.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline([QPointF(1, 1), QPointF(5, 5), QPointF(9, 1)])
    p.end()
    img.save(str(out / "dropdown_arrow.png"))


def main() -> None:
    app = QGuiApplication([])
    fantasy = THEMES / "high_fantasy" / "assets"
    stone(fantasy)
    gold = QColor("#d9b46c")
    title_rules(fantasy, gold)
    header_rules(fantasy, gold)
    shield_crest(fantasy, gold, QColor("#f2d592"))

    modern = THEMES / "modern_proof" / "assets"
    charcoal(modern)
    neutral = QColor("#c0c0c4")  # Modern Dark accent_primary
    title_rules(modern, neutral)
    header_rules(modern, neutral)
    flat_crest(modern, neutral)
    dropdown_arrow(modern, neutral)
    del app


if __name__ == "__main__":
    main()
