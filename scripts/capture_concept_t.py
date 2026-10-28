"""Capture the Concept T dashboard and Journal page in both shipped themes.

Usage: capture_concept_t.py [OUT] [--size 1280x720 ...] [--scale 75 100 150 ...]
Files are named <page>-<theme>-<width>x<height>-<scale>.png.
--set readme writes the six README images into docs/screenshots/ (1280 px wide).
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QCursor, QEnterEvent, QPainter  # noqa: E402

from dd_simulator.app import build_application  # noqa: E402
from dd_simulator.state import GameStateService  # noqa: E402
from dd_simulator.state.combat import CombatService, EnemySpec  # noqa: E402
from dd_simulator.state.database import GameStateDatabase  # noqa: E402
from dd_simulator.ui.main_window import MainWindow  # noqa: E402
from dd_simulator.ui.widgets.hover_card import PositionedHoverCard  # noqa: E402
from dd_simulator.ui.widgets.inventory_grid import InventorySlotWidget  # noqa: E402


def settle(app, seconds: float = 0.3) -> None:  # type: ignore[no-untyped-def]
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        app.processEvents()


README_WIDTH = 1280


def save_readme(image, out: Path, name: str) -> None:  # type: ignore[no-untyped-def]
    path = out / name
    image.scaledToWidth(README_WIDTH, Qt.TransformationMode.SmoothTransformation).save(str(path))
    print(path)


def grab_with_cards(app, window):  # type: ignore[no-untyped-def]
    """Window grab with open hover cards (separate top-level widgets) composited on top."""
    image = window.grab().toImage()
    origin = window.mapToGlobal(QPoint(0, 0))
    painter = QPainter(image)
    for card in app.topLevelWidgets():
        if isinstance(card, PositionedHoverCard) and card.isVisible():
            painter.drawPixmap(card.mapToGlobal(QPoint(0, 0)) - origin, card.grab())
    painter.end()
    return image


def capture_readme(app, window, theme_manager, out: Path) -> None:  # type: ignore[no-untyped-def]
    def pick_theme(theme: str) -> None:
        window.theme_selector.setCurrentIndex(window.theme_selector.findData(theme))
        settle(app, 1.5)

    window.resize(1600, 900)
    window.font_size_requested.emit(100)
    pick_theme("high_fantasy")
    for page, name in (
        ("dashboard", "adventure-fantasy.png"),
        ("journal", "journal-fantasy.png"),
        ("character_sheet", "character-sheet-fantasy.png"),
    ):
        window._show_navigation(page)
        settle(app)
        save_readme(window.grab().toImage(), out, name)

    # Tooltip: put an equippable item in the first bag slot so the hover card compares it.
    window._show_navigation("dashboard")
    longsword = replace(
        window.dashboard.equipment[0].item, name="Warden's Longsword", rarity="rare",
        damage="1d8 + 3 slashing", weight=3.0, value_gp=60, id="item-readme-sword",
        status="", description="A heavy blade carried by the Greystone wardens.",
    )
    window._reload_dashboard(
        replace(window.dashboard, inventory=(longsword, *window.dashboard.inventory[1:]))
    )
    settle(app)
    slot = next(
        s for s in window.findChildren(InventorySlotWidget)
        if s.isVisible() and s.item.name == longsword.name
    )
    assert slot.comparison_item is not None, "no equipped comparison"
    center = slot.mapToGlobal(slot.rect().center())
    QCursor.setPos(center)
    point = QPointF(5, 5)
    slot.enterEvent(QEnterEvent(point, point, point))
    settle(app)
    save_readme(grab_with_cards(app, window), out, "tooltip-fantasy.png")
    slot.leaveEvent(None)  # type: ignore[arg-type]
    settle(app, 0.1)

    pick_theme("modern_proof")
    window._show_navigation("dashboard")
    settle(app)
    save_readme(window.grab().toImage(), out, "adventure-dark.png")
    pick_theme("high_fantasy")

    # Combat: two-enemy encounter, same setup as tests/test_main_window.py.
    database = GameStateDatabase.in_memory()
    service = GameStateService(database)
    service.initialize()
    service.ensure_demo_campaign()
    rolls = iter((20, 10, 1))
    service.combat = CombatService(database, roll=lambda _a, _b: next(rolls))
    service.start_combat(
        enemies=(
            EnemySpec("Training Goblin", 10, 10, 2, 4, distance_feet=5),
            EnemySpec("Training Wolf", 10, 10, 2, 4, distance_feet=5),
        )
    )
    combat = MainWindow(
        theme_manager.available_themes(),
        service.load_active_dashboard(),
        game_state_service=service,
    )
    try:
        combat.resize(1600, 900)
        combat.show()
        settle(app, 1.0)
        save_readme(combat.grab().toImage(), out, "combat-fantasy.png")
    finally:
        combat.close()
        combat.deleteLater()
        app.processEvents()
        database.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("out", nargs="?", default=str(ROOT / "artifacts" / "previews"))
    parser.add_argument("--size", nargs="+", default=["1600x900"])
    parser.add_argument("--scale", nargs="+", type=int, default=[100])
    parser.add_argument("--pages", nargs="+", default=["dashboard", "journal"])
    parser.add_argument("--set", choices=["readme"], help="write a fixed image set instead")
    args = parser.parse_args()
    if args.set == "readme" and args.out == str(ROOT / "artifacts" / "previews"):
        args.out = str(ROOT / "docs" / "screenshots")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    config = Path(tempfile.mkdtemp(prefix="ddsim-capture-"))
    try:
        app, window, manager = build_application([], config_dir=config)
        window.show()
        if args.set == "readme":
            capture_readme(app, window, manager, out)
            window.close()
            app.processEvents()
            return 0
        window._show_navigation("dashboard")
        for theme in ("high_fantasy", "modern_proof"):
            window.theme_selector.setCurrentIndex(window.theme_selector.findData(theme))
            settle(app, 1.5)
            for size in args.size:
                width, height = (int(part) for part in size.split("x"))
                window.resize(width, height)
                for scale in args.scale:
                    window.font_size_requested.emit(scale)
                    for page in args.pages:
                        window._show_navigation(page)
                        settle(app)
                        path = out / f"{page}-{theme}-{width}x{height}-{scale}.png"
                        window.grab().save(str(path))
                        print(path)
        window.font_size_requested.emit(100)
        window.close()
        app.processEvents()
    finally:
        shutil.rmtree(config, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
