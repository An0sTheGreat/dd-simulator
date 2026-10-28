"""Render the Concept T tooltip cards to artifacts/previews for visual review."""

from __future__ import annotations

import dataclasses
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PySide6.QtCore import QPoint  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPixmap  # noqa: E402
from PySide6.QtWidgets import QWidget  # noqa: E402

from dd_simulator.app import build_application  # noqa: E402
from dd_simulator.ui.widgets.inventory_grid import ItemHoverCard, equipped_comparisons  # noqa: E402
from dd_simulator.ui.widgets.skills_grid import AbilityHoverCard, SkillHoverCard  # noqa: E402

GAP = 24


def main() -> int:
    output_dir = Path(__file__).resolve().parents[1] / "artifacts" / "previews"
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as config_dir:
        app, window, manager = build_application([], config_dir=Path(config_dir))
        dashboard = window.dashboard
        # The demo bag holds no weapons and the demo hero no spells, so derive the
        # mockup's pairs: a bag dagger, and a longsword compared with the equipped dagger.
        dagger = next(slot.item for slot in dashboard.equipment if slot.item and slot.item.damage)
        bag_dagger = dataclasses.replace(dagger, status="", rarity="common")
        longsword = dataclasses.replace(
            dagger, name="Warden's Longsword", status="", damage="1d8 + 3 slashing",
            bonuses='{"attack": 1}', weight=3.0, value_gp=45, durability=54, maximum_durability=60,
            description="Issued to wardens of the Greystone Road.",
        )
        compared = equipped_comparisons(longsword, dashboard.equipment)[0]
        spell = dataclasses.replace(dashboard.abilities[2], kind="spell")
        skill = next((s for s in dashboard.skills if s.next_level_xp), dashboard.skills[0])
        host = QWidget()
        for theme in ("high_fantasy", "modern_proof"):
            manager.apply_loaded_theme(app, manager.load_theme(theme), persist=False)
            cards = [
                ItemHoverCard(bag_dagger, host),
                ItemHoverCard(longsword, host, compared_with=compared),
                AbilityHoverCard(dashboard.abilities[0], host),
                AbilityHoverCard(spell, host),
                SkillHoverCard(skill, host),
            ]
            shots = []
            for card in cards:
                card.adjustSize()
                card.show()
                app.processEvents()
                shots.append(card.grab())
                card.close()
                card.deleteLater()
            width = sum(shot.width() for shot in shots) + GAP * (len(shots) + 1)
            height = max(shot.height() for shot in shots) + GAP * 2
            sheet = QPixmap(width, height)
            sheet.fill(QColor("#14100b" if theme == "high_fantasy" else "#0e0e10"))
            painter = QPainter(sheet)
            x = GAP
            for shot in shots:
                painter.drawPixmap(QPoint(x, GAP), shot)
                x += shot.width() + GAP
            painter.end()
            path = output_dir / f"tooltips-{theme}.png"
            sheet.save(str(path))
            print(path)
        host.deleteLater()
        window.close()
        window.deleteLater()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
