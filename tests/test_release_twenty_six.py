from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QSplitter, QWidget

from dd_simulator.ui.main_window import HTCAPTION, HTCLIENT, NATIVE_SNAP_STYLE, WS_THICKFRAME
from dd_simulator.ui.widgets.themed_dialog import DraggableTitleBar

from dd_simulator.app import build_application
from dd_simulator.ui.widgets.inventory_grid import ItemHoverCard
from dd_simulator.ui.widgets.skills_grid import AbilityHoverCard


def _window(tmp_path: Path):
    app, window, themes = build_application([], config_dir=tmp_path)
    window.theme_requested.emit("high_fantasy")
    window.resize(1600, 900)
    window.show()
    window.controller.navigate("dashboard")
    app.processEvents()
    return app, window, themes


def test_release_26_6_character_sheet_is_centered_and_complete(tmp_path: Path) -> None:
    app, window, _themes = _window(tmp_path)
    window.controller.navigate("character_sheet")
    app.processEvents()

    assert window.current_page == "character_sheet"
    assert "character_sheet" in window.navigation_buttons
    surface = window.findChild(QWidget, "characterSheetSurface")
    viewport = window.findChild(QWidget, "characterSheetViewport")
    assert surface is not None and viewport is not None
    assert surface.width() * 5 <= viewport.width() * 3 + 10
    assert len(surface.findChildren(QWidget, "characterSheetAttribute")) == 6
    assert surface.findChild(QWidget, "characterSheetIdentity") is not None

    window.close()
    app.processEvents()


def test_inventory_uses_six_or_four_columns_and_scrolls_when_needed(
    tmp_path: Path,
) -> None:
    app, window, _themes = _window(tmp_path)
    window.utility_panel.set_current_tab(2)
    app.processEvents()

    scroll = window.findChild(QScrollArea, "inventoryUtilityScroll")
    assert scroll is not None
    assert scroll.alignment() == (
        Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
    )
    window.main_splitter.setSizes([850, 750])
    app.processEvents()
    assert window.utility_panel.inventory_grid.columns == 6
    assert len(window.utility_panel.inventory_grid.slots) == 36
    assert scroll.verticalScrollBar().maximum() > 0

    window.main_splitter.setSizes([1200, 360])
    app.processEvents()
    assert window.utility_panel.inventory_grid.columns == 4
    assert scroll.verticalScrollBar().maximum() > 0

    window.close()
    app.processEvents()


def test_release_26_7_sidebar_splitter_and_restore_drag(tmp_path: Path) -> None:
    app, window, _themes = _window(tmp_path)
    sidebar = window.findChild(QSplitter, "sidebarUtilitySplitter")
    assert sidebar is not None and sidebar.count() == 2
    sidebar.setSizes([320, 470])
    assert all(size > 0 for size in sidebar.sizes())

    title_bar = window.findChild(DraggableTitleBar, "topHeader")
    window.showMaximized()
    app.processEvents()
    assert window.isMaximized()
    local_position = title_bar.rect().center()
    assert title_bar.restore_from_maximized_drag(
        local_position,
        title_bar.mapToGlobal(local_position),
    )
    app.processEvents()
    assert not window.isMaximized()

    window.close()
    app.processEvents()


def test_title_bar_exposes_native_caption_but_preserves_controls(tmp_path: Path) -> None:
    app, window, _themes = _window(tmp_path)
    drag_surface = window.findChild(QLabel, "applicationTitle")
    assert window._native_title_hit_test(
        drag_surface.mapTo(window, drag_surface.rect().center())
    ) == HTCAPTION
    for name in (
        "themeSelector",
        "windowMinimizeButton",
        "windowMaximizeButton",
        "windowCloseButton",
    ):
        control = window.findChild(QWidget, name)
        assert control is not None
        assert window._native_title_hit_test(
            control.mapTo(window, control.rect().center())
        ) == HTCLIENT
    assert NATIVE_SNAP_STYLE & WS_THICKFRAME
    window.close()
    app.processEvents()


def test_release_26_6_hover_cards_are_semantic(
    tmp_path: Path,
) -> None:
    app, window, _themes = _window(tmp_path)

    item = next(
        value for value in window.dashboard.inventory_preview
        if not value.is_empty and value.rarity.casefold() == "uncommon"
    )
    item_card = ItemHoverCard(item, window)
    item_text = " ".join(label.text() for label in item_card.findChildren(QLabel))
    assert item_card.property("rarity") == "uncommon"
    assert "{" not in item_text and "remove_statuses" not in item_text
    assert item_card.icon_label.width() == 88
    surface = item_card.findChild(QWidget, "itemHoverSurface")
    assert surface is not None and surface.isAncestorOf(item_card.description_label)
    assert surface.property("rarity") == "uncommon"

    action = window.dashboard.combat_skills[0]
    assert action.stats
    ability_card = AbilityHoverCard(action, window)
    ability_text = " ".join(label.text() for label in ability_card.findChildren(QLabel))
    for required in ("Type:", "Cost:", "Effect:", "Range:"):
        assert required in ability_text

    item_card.deleteLater()
    ability_card.deleteLater()
    window.theme_requested.emit("modern_proof")
    app.processEvents()
    assert app.property("themeId") == "modern_proof"
    window.close()
    app.processEvents()


def test_release_26_7_title_controls_have_complete_frames(tmp_path: Path) -> None:
    app, window, _themes = _window(tmp_path)
    for name in ("windowMinimizeButton", "windowMaximizeButton", "windowCloseButton"):
        button = window.findChild(QPushButton, name)
        assert button is not None
        assert button.size().width() >= 30
        assert 28 <= button.size().height() <= 42

    window.close()
    app.processEvents()
