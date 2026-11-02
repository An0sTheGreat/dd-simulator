from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from dd_simulator.ui import item_icons


def test_rarity_glow_blurs_once_and_the_pulse_only_repaints(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    app = QApplication.instance() or QApplication([])
    blurs: list[int] = []
    original = item_icons._blurred_glow
    monkeypatch.setattr(item_icons, "_blurred_glow", lambda *a: blurs.append(1) or original(*a))
    host = QWidget()
    host.resize(200, 200)
    icon = QLabel(host)
    pixmap = QPixmap(40, 40)
    pixmap.fill(QColor("white"))
    icon.setPixmap(pixmap)
    icon.setGeometry(60, 60, 40, 40)
    item_icons.apply_rarity_glow(icon, "rare")
    glow = icon.graphicsEffect()
    assert isinstance(glow, item_icons._RarityGlow)
    host.grab()
    for strength in (0.6, 0.8, 1.0):  # pulse ticks
        glow.set_strength(strength)
        host.grab()
    assert len(blurs) == 1
    image = host.grab().toImage()
    assert image.pixelColor(55, 80).alpha() > 0 and image.pixelColor(55, 80) != image.pixelColor(5, 5)
    host.deleteLater()
    app.processEvents()


def test_no_application_wide_python_key_filter() -> None:
    from dd_simulator.ui.widgets.scene_view import ChoiceGrid

    assert not hasattr(ChoiceGrid, "eventFilter") or ChoiceGrid.eventFilter is QWidget.eventFilter
