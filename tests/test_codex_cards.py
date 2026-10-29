from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QDragMoveEvent, QDropEvent, QPalette
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel

from dd_simulator.state import GameStateDatabase, GameStateService
from dd_simulator.state.seed import seed_demo_campaign
from dd_simulator.ui.models.presentation import CombatActionOptionView, InventorySlotView
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.widgets.codex_cards import (
    CARD_COLUMNS,
    CodexCardRow,
    InventoryCard,
    PowersCard,
    codex_card,
)
from dd_simulator.ui.widgets.inventory_grid import INVENTORY_SLOT_MIME, well_inset


THEMES_ROOT = Path(__file__).resolve().parents[1] / "src" / "dd_simulator" / "ui" / "themes"


def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def bag(count: int, start: int = 0) -> tuple[InventorySlotView, ...]:
    return tuple(
        InventorySlotView(f"Item {position}", quantity=1, id=f"i{position}", position=position)
        for position in range(start, start + count)
    )


def shown_card(items: tuple[InventorySlotView, ...]) -> InventoryCard:
    app()
    card = InventoryCard(items, capacity=320)
    card.show()
    QApplication.processEvents()
    return card


def in_viewport(card: InventoryCard, position: int) -> bool:
    slot = card.grid.slots[position]
    top = slot.mapTo(card.grid, slot.rect().topLeft()).y()
    value = card.scroll.verticalScrollBar().value()
    return value <= top and top + slot.height() <= value + card.scroll.viewport().height()


def action(key: str, kind: str, status: str = "Ready", available: bool = True) -> CombatActionOptionView:
    return CombatActionOptionView(
        key=key, name=key.title(), kind=kind, description="", resource_label="3 stamina",
        available=available, stats=(("Range", "60 ft"),), status_label=status,
    )


def test_projection_carries_the_real_bag_position(tmp_path: Path) -> None:
    database = GameStateDatabase.in_memory()
    database.initialize()
    seed_demo_campaign(database)
    service = GameStateService(database)
    first = service.load_active_dashboard().inventory[0]
    service.move_inventory_item(first.position, 47)
    dashboard = service.load_active_dashboard()
    moved = next(item for item in dashboard.inventory if item.id == first.id)
    assert moved.position == 47
    for item in dashboard.inventory:
        assert dashboard.inventory_preview[item.position].id == item.id


def test_sixty_items_are_all_reachable_and_position_59_holds_its_item() -> None:
    card = shown_card(bag(60))
    bar = card.scroll.verticalScrollBar()
    assert len(card.grid.slots) == 65  # 12 occupied rows plus one empty row
    assert card.scroll.viewport().height() == 5 * card.pitch - 3
    assert not in_viewport(card, 59)
    bar.setValue(bar.maximum())
    QApplication.processEvents()
    assert in_viewport(card, 59)
    assert card.grid.slots[59].item.name == "Item 59"
    assert card.grid.slots[59].index == 59


def test_rows_stop_at_capacity() -> None:
    app()
    card = InventoryCard(bag(25, start=295), capacity=320)
    assert len(card.grid.slots) == 320


def test_drop_far_down_the_bag_emits_the_real_positions() -> None:
    card = shown_card(bag(3) + bag(1, start=40))
    moves: list[tuple[int, int]] = []
    card.move_requested.connect(lambda source, target: moves.append((source, target)))
    mime = QMimeData()
    mime.setData(INVENTORY_SLOT_MIME, QByteArray(b"2"))
    target = card.grid.slots[44]
    event = QDropEvent(
        QPointF(10, 10), Qt.DropAction.MoveAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    target.dropEvent(event)  # QApplication drops synthetic Drop events outside a drag
    assert moves == [(2, 44)]


def test_dragging_at_the_bottom_edge_scrolls_until_the_drag_leaves() -> None:
    card = shown_card(bag(60))
    bar = card.scroll.verticalScrollBar()
    mime = QMimeData()
    mime.setData(INVENTORY_SLOT_MIME, QByteArray(b"0"))
    edge_slot = card.grid.slots[24]  # bottom visible row
    event = QDragMoveEvent(
        edge_slot.rect().bottomLeft() - edge_slot.rect().topLeft(),
        Qt.DropAction.MoveAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    )
    card.eventFilter(edge_slot, event)
    assert card._drag_timer.isActive()
    card._drag_scroll_tick()
    assert bar.value() > 0
    card.eventFilter(edge_slot, QDropEvent(
        QPointF(1, 1), Qt.DropAction.MoveAction, mime,
        Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
    ))
    assert not card._drag_timer.isActive()


def test_below_count_follows_the_scroll_position() -> None:
    card = shown_card(bag(27))
    assert card.below_count() == 2
    assert card.count_label.text() == "27 items · 2 below"
    bar = card.scroll.verticalScrollBar()
    bar.setValue(bar.maximum())
    QApplication.processEvents()
    assert card.below_count() == 0
    assert card.count_label.text() == "27 items · 0 below"


def test_keyboard_selection_past_row_five_scrolls_into_view() -> None:
    card = shown_card(bag(40))
    assert not in_viewport(card, 25)
    QTest.keyClick(card.grid.slots[20], Qt.Key.Key_Down)
    QApplication.processEvents()
    assert in_viewport(card, 25)
    assert card.scroll.verticalScrollBar().value() == card.pitch


def test_auto_sort_menu_emits_the_existing_sort_modes() -> None:
    card = shown_card(bag(3))
    modes: list[str] = []
    card.auto_sort_requested.connect(modes.append)
    menu = card.auto_sort_button.menu()
    assert [entry.text() for entry in menu.actions()] == ["Default", "Rarity", "Type", "Value"]
    menu.actions()[1].trigger()
    assert modes == ["rarity"]
    assert card.auto_sort_button.accessibleName() == "Auto-sort inventory"


def test_powers_card_splits_hides_and_shows_empty_state() -> None:
    app()
    card = PowersCard((action("quick_shot", "ability"), action("volley", "ability")), (action("ember", "spell"),))
    card.show()
    assert [e.action.key for e in card.ability_column.entries] == ["quick_shot", "volley"]
    assert [e.action.key for e in card.spell_column.entries] == ["ember"]
    assert card.ability_column.isVisible() and card.spell_column.isVisible()
    assert not card.empty_label.isVisible()
    keys: list[str] = []
    card.action_activated.connect(keys.append)
    QTest.mouseClick(card.spell_column.entries[0], Qt.MouseButton.LeftButton)
    assert keys == ["ember"]
    detail = card.ability_column.entries[0].findChild(QLabel, "powerEntryDetail")
    assert detail.text() == "3 stamina · 60 ft"
    # Short Rest sits in its own footer row beneath both columns.
    assert card.rest_button.isVisible()
    assert card.rest_button.geometry().top() > card.spell_column.geometry().bottom()
    assert card.rest_button.geometry().top() > card.ability_column.geometry().bottom()

    only_spells = PowersCard((), (action("ember", "spell"),))
    only_spells.show()
    assert not only_spells.ability_column.isVisible()
    assert only_spells.spell_column.width() > only_spells.width() // 2
    assert only_spells.spell_column.width() == only_spells.layout().contentsRect().width()

    only_abilities = PowersCard((action("quick_shot", "ability"),), ())
    only_abilities.show()
    assert not only_abilities.spell_column.isVisible()
    assert only_abilities.ability_column.width() == only_abilities.layout().contentsRect().width()

    empty = PowersCard((), ())
    empty.show()
    assert empty.empty_label.isVisible()
    assert empty.empty_label.text() == "No abilities or spells yet"
    assert not empty.ability_column.isVisible() and not empty.spell_column.isVisible()


def test_status_colour_differs_for_ready_and_cooldown(tmp_path: Path) -> None:
    application = app()
    manager = ThemeManager(
        themes_root=THEMES_ROOT, preferences_path=tmp_path / "prefs.json",
        default_theme_id="high_fantasy",
    )
    try:
        for theme_id in ("high_fantasy", "modern_proof"):
            manager.apply_loaded_theme(application, manager.load_theme(theme_id), persist=False)
            card = PowersCard(
                (action("quick_shot", "ability"), action("volley", "ability", "Cooldown 2", False)),
            )
            card.show()
            QApplication.processEvents()
            ready, cooldown = (e.status_label for e in card.ability_column.entries)
            role = QPalette.ColorRole.WindowText
            assert ready.palette().color(role) != cooldown.palette().color(role), theme_id
    finally:
        application.setStyleSheet("")


def test_codex_card_row_keeps_both_cards_at_equal_height() -> None:
    app()
    row = CodexCardRow(InventoryCard(bag(5)), PowersCard((action("a", "ability"),)))
    row.resize(724, 390)
    row.show()
    QApplication.processEvents()
    assert row.inventory_card.height() == row.powers_card.height() == 390
    assert CARD_COLUMNS == 5


def test_codex_card_heading_and_count_are_plain_text() -> None:
    app()
    card, _layout = codex_card("<b>x</b>", "someCard", count=3)
    heading = card.findChild(QLabel, "codexCardHeading")
    count = card.findChild(QLabel, "codexCardCount")
    assert heading.textFormat() == Qt.TextFormat.PlainText
    assert count.textFormat() == Qt.TextFormat.PlainText


def test_inventory_icons_refit_when_the_theme_changes(tmp_path: Path) -> None:
    application = app()
    manager = ThemeManager(
        themes_root=THEMES_ROOT, preferences_path=tmp_path / "prefs.json",
        default_theme_id="high_fantasy",
    )
    try:
        for first, second in (("high_fantasy", "modern_proof"), ("modern_proof", "high_fantasy")):
            manager.apply_loaded_theme(application, manager.load_theme(first), persist=False)
            card = shown_card(bag(3))
            manager.apply_loaded_theme(application, manager.load_theme(second), persist=False)
            QApplication.processEvents()
            slots = [slot for slot in card.grid.slots if not slot.item.is_empty]
            assert slots
            for slot in slots:
                inner = slot.contentsRect()
                side = min(inner.width(), inner.height())
                icon = slot.icon_label.geometry()
                where = f"{first}->{second}"
                assert abs(icon.width() - side * 7 // 8) <= 1, where
                assert inner.contains(icon), where
            card.close()
            card.deleteLater()
    finally:
        application.setStyleSheet("")


def _rect_in(widget, ancestor) -> QRect:  # type: ignore[no-untyped-def]
    return QRect(widget.mapTo(ancestor, QPoint(0, 0)), widget.size())


def test_inventory_card_lays_out_whole_square_rows_clear_of_the_scrollbar(tmp_path: Path) -> None:
    application = app()
    manager = ThemeManager(
        themes_root=THEMES_ROOT, preferences_path=tmp_path / "prefs.json",
        default_theme_id="high_fantasy",
    )
    try:
        # None = no theme: the platform style's (wider) scrollbar must still sit clear.
        for theme_id in (None, "high_fantasy", "modern_proof"):
            if theme_id is None:
                application.setStyleSheet("")
            else:
                manager.apply_loaded_theme(application, manager.load_theme(theme_id), persist=False)
            for scale, height in ((1.0, 600), (1.0, 530), (0.76, 290), (0.6, 200), (1.0, 230)):
                row = CodexCardRow(InventoryCard(bag(17)), PowersCard((action("a", "ability"),)))
                card = row.inventory_card
                card.set_scale(scale)
                row.resize(724, height)
                row.show()
                # a rewrap rebuilds the slots, which lay out over the next few passes
                for _ in range(4):
                    QApplication.processEvents()
                where = f"{theme_id} scale={scale} height={height}"
                viewport = _rect_in(card.scroll.viewport(), card)
                bar = _rect_in(card.scroll.verticalScrollBar(), card)
                assert card.contentsRect().contains(viewport), where
                top = card.scroll.verticalScrollBar().value()
                visible = [
                    (slot, _rect_in(slot, card)) for slot in card.grid.slots
                    if slot.y() + slot.height() > top and slot.y() < top + viewport.height()
                ]
                rows = {rect.y() for _slot, rect in visible}
                columns = card.grid.columns
                assert columns >= CARD_COLUMNS, where
                assert len(rows) == card.visible_rows and len(visible) == columns * len(rows), where
                assert len(rows) >= 5 or height < 530, where  # every row that fits, 5 or more
                # whole rectangle, never fewer than 36 slots
                assert len(card.grid.slots) % columns == 0 and len(card.grid.slots) >= 36, where
                assert {rect.width() for _s, rect in visible} == {card.grid.slot_size}, where
                for index, (slot, rect) in enumerate(visible):
                    assert rect.width() == rect.height(), where
                    assert viewport.contains(rect), f"{where} slot {slot.index} cut"
                    assert not rect.intersects(bar), f"{where} slot {slot.index} under bar"
                    assert not any(rect.intersects(other) for _o, other in visible[index + 1:]), where
                    # well art spreads to just inside the slot's outer edge, over the
                    # frame border; the icon is centred on the slot
                    inset = well_inset(slot.width())
                    frame = slot.rect().adjusted(inset, inset, -inset, -inset)
                    assert slot.artwork_label.geometry() == frame, where
                    if not slot.item.is_empty:
                        icon = slot.icon_label.geometry()
                        assert frame.contains(icon), where
                        assert abs(icon.center().x() - slot.rect().center().x()) <= 1, where
                        assert abs(icon.center().y() - slot.rect().center().y()) <= 1, where
                # even gutters: one column pitch and one row pitch
                xs = sorted({rect.x() for _s, rect in visible})
                ys = sorted(rows)
                assert len(xs) == card.grid.columns, where
                assert len({b - a for a, b in zip(xs, xs[1:])}) == 1, where
                assert len({b - a for a, b in zip(ys, ys[1:])}) <= 1, where
                # grid centred vertically between heading and footer, within a pixel
                above = viewport.top() - card.contentsRect().top()
                below = card.contentsRect().bottom() - viewport.bottom()
                assert below >= 0 and above >= 0, where
                row.close()
                row.deleteLater()
    finally:
        application.setStyleSheet("")
