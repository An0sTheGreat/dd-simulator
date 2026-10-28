"""Render the Concept T character strip, paperdoll and skill list in both themes.

Writes artifacts/previews/codex-left-<theme>.png (724 px wide) from the demo campaign.
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget

from dd_simulator.app import build_application
from dd_simulator.ui.widgets.codex_character import (
    CharacterStrip,
    PaperdollPanel,
    SkillDetailList,
)


def main() -> int:
    output_dir = Path(__file__).resolve().parents[1] / "artifacts" / "previews"
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as config_dir:
        app, window, manager = build_application([], config_dir=Path(config_dir))
        dashboard = window.dashboard
        for theme in ("high_fantasy", "modern_proof"):
            manager.apply_loaded_theme(app, manager.load_theme(theme), persist=False)
            root = QWidget()
            root.setObjectName("applicationRoot")
            root.setFixedWidth(724)
            layout = QVBoxLayout(root)
            # The mockup's panel frame: 14 px border plus 8 px padding.
            layout.setContentsMargins(22, 16, 22, 16)
            layout.setSpacing(24)
            layout.addWidget(CharacterStrip(dashboard))
            middle = QHBoxLayout()
            middle.setSpacing(12)
            middle.addWidget(PaperdollPanel(dashboard.player, dashboard.equipment))
            middle.addWidget(SkillDetailList(dashboard.skills), 1)
            layout.addLayout(middle)
            root.adjustSize()
            root.show()
            app.processEvents()
            path = output_dir / f"codex-left-{theme}.png"
            root.grab().save(str(path))
            print(path)
            root.close()
            root.deleteLater()
        window.close()
        window.deleteLater()
        app.processEvents()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
