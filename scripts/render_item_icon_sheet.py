"""Render a review sheet of packaged item icons, labelled with record name and rarity.

Picks about nine records from every catalog category, spread across visual tiers, and
draws each record's packaged library icon (`ui/item_icons.icon_path`) at 96 px.

Usage: python scripts/render_item_icon_sheet.py [OUT_PNG]   (default docs/design/item-icons.png)
"""

from __future__ import annotations

from collections import defaultdict
import sys
from pathlib import Path


from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QImage, QPainter

from dd_simulator.ui.item_icons import RARITY_TIER, icon_path, icon_records


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = PROJECT_ROOT / "docs" / "design" / "item-icons.png"
PER_CATEGORY = 9
CELL, ICON, LABEL = 128, 96, 30
RARITY_NAME = {tier: name.title() for name, tier in RARITY_TIER.items()}
RARITY_COLOUR = {0: "#d8d8d8", 1: "#5fd35f", 2: "#5fa8ff", 3: "#c77dff", 4: "#ffb347"}


def render_sheet(cells: list[tuple[Path, str, str, str]], out: Path, columns: int = 12) -> None:
    """Draw (icon, line 1, line 2, line-2 colour) cells in a grid and save a PNG."""

    rows = -(-len(cells) // columns)
    sheet = QImage(columns * CELL, rows * (ICON + LABEL + 8), QImage.Format.Format_RGB32)
    sheet.fill(QColor("#1e1e24"))
    painter = QPainter(sheet)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    font = QFont()
    font.setPixelSize(11)
    painter.setFont(font)
    metrics = QFontMetrics(font)
    for number, (path, first, second, colour) in enumerate(cells):
        x, y = number % columns * CELL, number // columns * (ICON + LABEL + 8)
        image = QImage(str(path))
        if image.isNull():
            raise SystemExit(f"Cannot read image: {path}")
        image = image.scaled(ICON, ICON, Qt.AspectRatioMode.KeepAspectRatio,
                             Qt.TransformationMode.SmoothTransformation)
        painter.drawImage(x + (CELL - image.width()) // 2, y + 4, image)
        for line, (text, pen) in enumerate(((first, "#ffffff"), (second, colour))):
            painter.setPen(QColor(pen))
            painter.drawText(QRect(x + 2, y + ICON + 6 + line * 14, CELL - 4, 14),
                             Qt.AlignmentFlag.AlignHCenter,
                             metrics.elidedText(text, Qt.TextElideMode.ElideRight, CELL - 4))
    painter.end()
    out.parent.mkdir(parents=True, exist_ok=True)
    if not sheet.save(str(out), "PNG", 0):
        raise SystemExit(f"Cannot write {out}")


def representative_cells() -> list[tuple[Path, str, str, str]]:
    by_category = defaultdict(list)
    for record in icon_records():
        by_category[record.category].append(record)
    cells = []
    for category in sorted(by_category):
        members = sorted(by_category[category], key=lambda r: (r.visual_tier, r.index))
        count = min(PER_CATEGORY, len(members))
        for pick in range(count):
            record = members[pick * (len(members) - 1) // max(count - 1, 1)]
            cells.append((icon_path(record), record.semantic_name,
                          f"{RARITY_NAME[record.visual_tier]} {category}",
                          RARITY_COLOUR[record.visual_tier]))
    return cells


def main(argv: list[str]) -> int:
    out = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUT
    app = QGuiApplication.instance() or QGuiApplication([])  # noqa: F841 - fonts need it
    cells = representative_cells()
    render_sheet(cells, out)
    print(f"{len(cells)} records rendered to {out}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
