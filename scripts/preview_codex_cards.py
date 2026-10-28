"""Render the Concept T inventory and powers cards to artifacts/previews for visual review."""

from __future__ import annotations

import dataclasses
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402

from dd_simulator.state import GameStateDatabase, GameStateService  # noqa: E402
from dd_simulator.ui.fonts import register_application_fonts  # noqa: E402
from dd_simulator.ui.themes.theme_manager import ThemeManager  # noqa: E402
from dd_simulator.ui.widgets.codex_cards import CodexCardRow, InventoryCard, PowersCard  # noqa: E402


def main() -> int:
    app = QApplication.instance() or QApplication([])
    register_application_fonts()
    service = GameStateService(GameStateDatabase.in_memory())
    service.initialize()
    dashboard = service.load_active_dashboard()
    items = list(dashboard.inventory)
    while len(items) < 27:
        source = items[len(items) % max(1, len(dashboard.inventory))]
        items.append(dataclasses.replace(source, position=len(items), id=f"preview-{len(items)}"))
    dashboard = dataclasses.replace(dashboard, inventory=tuple(items))
    out = ROOT / "artifacts" / "previews"
    out.mkdir(parents=True, exist_ok=True)
    manager = ThemeManager(themes_root=ROOT / "src" / "dd_simulator" / "ui" / "themes", preferences_path=out / "preview-prefs.json", default_theme_id="high_fantasy")
    for theme in ("high_fantasy", "modern_proof"):
        manager.apply_loaded_theme(app, manager.load_theme(theme), persist=False)
        row = CodexCardRow(
            InventoryCard(dashboard.inventory, capacity=dashboard.inventory_capacity, equipment=dashboard.equipment),
            PowersCard(dashboard.abilities, dashboard.spells),
        )
        row.resize(724, 390)
        row.show()
        app.processEvents()
        path = out / f"codex-cards-{theme}.png"
        row.grab().save(str(path))
        row.close()
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
