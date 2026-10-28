from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QPushButton, QScrollArea, QSplitter, QWidget

from dd_simulator.ui.main_window import HTCAPTION, HTCLIENT, NATIVE_SNAP_STYLE, WS_THICKFRAME
from dd_simulator.ui.widgets.themed_dialog import DraggableTitleBar

from dataclasses import replace

from dd_simulator.app import build_application
from dd_simulator.ui.widgets.codex_cards import CARD_COLUMNS, CARD_VISIBLE_ROWS
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
    assert "character_sheet" in window.scene_view.tabs.buttons
    surface = window.findChild(QWidget, "characterSheetSurface")
    viewport = window.findChild(QWidget, "characterSheetViewport")
    assert surface is not None and viewport is not None
    # The sheet is a full-width grid of codex cards (was a centred 60 % column).
    assert surface.width() >= viewport.width() - 4
    assert len(surface.findChildren(QWidget, "characterSheetAttribute")) == 6
    assert surface.findChild(QWidget, "characterSheetIdentity") is not None

    window.close()
    app.processEvents()


def test_character_sheet_card_order_at_1600x900(tmp_path: Path) -> None:
    app, window, _themes = _window(tmp_path)
    window.controller.navigate("character_sheet")
    app.processEvents()
    surface = window.findChild(QWidget, "characterSheetSurface")

    def card(name: str) -> tuple:
        found = next(
            w for w in surface.findChildren(QWidget) if w.accessibleName() == name and w.isVisible()
        )
        top_left = found.mapTo(surface, found.rect().topLeft())
        return found, top_left, found.mapTo(surface, found.rect().bottomRight())

    _, identity, identity_end = card("Identity")
    _, scores, _ = card("Ability Scores")
    assert scores.x() == identity.x() and scores.y() >= identity_end.y()
    _, attacks, attacks_end = card("Weapon Attacks")
    _, vitals, vitals_end = card("Combat Summary")
    equipment_widget, equipment, _ = card("Equipment")
    _, skills, _ = card("Skills")
    half = surface.width() / 2
    # Combat Summary and Skills on the left of the right half, Weapon Attacks and
    # Equipment (with Abilities & Spells) on its right.
    assert vitals.x() >= half - 4 and vitals_end.x() <= attacks.x()
    assert attacks.y() == vitals.y()
    assert equipment.y() >= attacks_end.y() and equipment.x() == attacks.x()
    assert skills.y() > vitals.y() and skills.x() == vitals.x()
    powers = equipment_widget.findChild(QWidget, "characterSheetPowers")
    assert powers is not None and powers.mapTo(surface, powers.rect().topLeft()).y() > equipment.y() + 40
    # Both sections lay their entries out in two columns.
    rows = [w for w in equipment_widget.findChildren(QWidget, "pageCardName") if w.isVisible()]
    assert len({w.mapTo(surface, w.rect().topLeft()).x() for w in rows}) == 2
    _, role, role_end = card("Role & Character")
    _, possessions, _ = card("Possessions & Currency")
    assert possessions.x() == role.x() and possessions.y() >= role_end.y()

    window.close()
    app.processEvents()


def test_inventory_card_keeps_five_columns_and_scrolls_when_needed(
    tmp_path: Path,
) -> None:
    app, window, _themes = _window(tmp_path)
    card = window.inventory_card
    scroll = window.findChild(QScrollArea, "inventoryCardScroll")
    assert scroll is card.scroll
    assert scroll.alignment() == (
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
    )
    # The demo bag fits the 5x5 viewport; the card does not reflow with the splitter.
    assert card.grid.columns == CARD_COLUMNS
    assert len(card.grid.slots) == CARD_COLUMNS * CARD_VISIBLE_ROWS
    assert scroll.verticalScrollBar().maximum() == 0
    for sizes in ([850, 750], [1200, 360]):
        window.concept_splitter.setSizes(sizes)
        app.processEvents()
        assert card.grid.columns == CARD_COLUMNS

    # An item at a deep bag position grows the grid to that row plus one and scrolls.
    item = next(value for value in window.dashboard.inventory_preview if not value.is_empty)
    card.set_inventory((replace(item, position=40),), capacity=320)
    app.processEvents()
    assert card.grid.columns == CARD_COLUMNS
    assert len(card.grid.slots) == (40 // CARD_COLUMNS + 2) * CARD_COLUMNS
    assert card.grid.slots[40].item.name == item.name
    assert scroll.verticalScrollBar().maximum() > 0

    window.close()
    app.processEvents()


def test_release_26_7_concept_splitter_and_restore_drag(tmp_path: Path) -> None:
    app, window, _themes = _window(tmp_path)
    splitter = window.findChild(QSplitter, "conceptTSplitter")
    assert splitter is window.concept_splitter and splitter.count() == 2
    splitter.setSizes([720, 860])
    assert all(size > 0 for size in splitter.sizes())

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
    assert item_card.icon_label.width() == 46
    # The card is its own framed surface now; the rarity tone sits on the name.
    assert item_card.findChild(QWidget, "itemHoverSurface") is None
    assert item_card.isAncestorOf(item_card.description_label)
    assert item_card.title_label.property("tone") == "uncommon"

    action = window.dashboard.combat_skills[0]
    assert action.stats
    ability_card = AbilityHoverCard(action, window)
    assert dict(action.stats)["Type"] in ability_card.subtitle_label.text()
    for required in ("Cost", "Effect", "Range"):
        assert ability_card.rows[required].text()

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
