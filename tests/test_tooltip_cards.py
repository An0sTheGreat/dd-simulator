from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import replace

import pytest
from PySide6.QtCore import QEvent, QObject, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QEnterEvent, QHelpEvent
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QToolTip, QWidget

from dd_simulator.ui.models.presentation import (
    CombatActionOptionView,
    EquipmentSlotView,
    InventorySlotView,
    SkillView,
)
from dd_simulator.ui.widgets.codex_cards import PowerEntry
from dd_simulator.ui.widgets.codex_character import SkillDetailRow
from dd_simulator.ui.widgets.hover_card import PositionedHoverCard, card_bounds, place_card
from dd_simulator.ui.widgets.inventory_grid import (
    InventorySlotWidget,
    ItemHoverCard,
    equipped_comparisons,
)
from dd_simulator.ui.widgets.skills_grid import AbilityHoverCard, CombatSkillGridItem, SkillHoverCard


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


_HOSTS: list[QWidget] = []


def _host() -> QWidget:
    # A card's parent must stay referenced, or PySide deletes the card with it.
    _HOSTS.clear()
    _HOSTS.append(QWidget())
    return _HOSTS[0]


def _flush() -> None:
    QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _enter(widget: QWidget) -> None:
    point = QPointF(5, 5)
    widget.enterEvent(QEnterEvent(point, point, point))


def _leave(widget: QWidget) -> None:
    widget.leaveEvent(QEvent(QEvent.Type.Leave))


def _open_cards() -> list[PositionedHoverCard]:
    return [
        w for w in QApplication.topLevelWidgets()
        if isinstance(w, PositionedHoverCard) and w.isVisible()
    ]


DAGGER = InventorySlotView(
    "Iron Dagger", quantity=1, rarity="uncommon", item_type="equipment", category="weapon",
    equip_slot="Main Hand", compatible_slots=("Main Hand",), damage="1d4 + 1 piercing",
    weight=1.0, value_gp=10, description="A balanced dagger.",
)
LONGSWORD = replace(
    DAGGER, name="Warden's Longsword", rarity="rare", damage="1d8 + 3 slashing", weight=3.0,
)
POWER = CombatActionOptionView(
    key="x", name="Test Power", kind="ability", description="Does a thing.",
    resource_label="5 stamina", available=True, status_label="Ready",
)
EQUIPMENT = (
    EquipmentSlotView("Main Hand", "Iron Dagger", item=DAGGER),
    EquipmentSlotView("Head", None),
)


def test_item_card_shows_rows_and_subtitle() -> None:
    _app()
    card = ItemHoverCard(LONGSWORD, _host())

    assert card.rows["Damage"].text() == "1d8 + 3 slashing"
    assert card.rows["Weight"].text() == "3.0 lb"
    assert card.rows["Value"].text() == "10 gold"
    assert card.subtitle_label.text() == "Rare · Weapon · Main Hand"
    assert card.comparison_block is None


def test_ability_and_spell_cards_show_tone_badge_cost_and_range() -> None:
    _app()
    stats = (("Type", "Physical"), ("Cost", "5 stamina"), ("Range", "Melee"))
    for kind, tone in (("ability", "ability"), ("spell", "spell")):
        action = CombatActionOptionView(
            key="x", name="Test Power", kind=kind, description="Does a thing.",
            resource_label="5 stamina", available=True, stats=stats, status_label="Ready",
        )
        card = AbilityHoverCard(action, _host())

        assert card.title_label.property("tone") == tone
        assert card.badge_label is not None and card.badge_label.text() == "READY"
        assert card.rows["Cost"].text() == "5 stamina"
        assert card.rows["Range"].text() == "Melee"
        assert "Type" not in card.rows


def test_skill_card_shows_next_level_row_and_xp_bar() -> None:
    _app()
    skill = SkillView("Attack", 52, current_xp=380, next_level_xp=600)
    card = SkillHoverCard(skill, _host())

    assert card.rows["Next level"].text() == "380 / 600 XP"
    bar = card.findChild(QProgressBar, "tooltipXpBar")
    assert bar is not None and (bar.value(), bar.maximum()) == (380, 600)


def test_comparison_block_marks_better_and_worse_deltas() -> None:
    _app()
    compared, alternate = equipped_comparisons(LONGSWORD, EQUIPMENT)
    assert compared is not None and alternate is None
    card = ItemHoverCard(LONGSWORD, _host(), compared_with=compared)

    assert card.comparison_block is not None
    deltas = {
        label.text(): label.property("better")
        for label in card.comparison_block.findChildren(QLabel, "tooltipDelta")
    }
    damage = next(text for text in deltas if text.endswith("avg damage"))
    weight = next(text for text in deltas if text.endswith("lb"))
    assert damage.startswith("+") and deltas[damage] is True
    assert weight == "+2.0 lb" and deltas[weight] is False


@pytest.mark.parametrize("slots", [("Head",), ("Off Hand",)])
def test_incompatible_item_has_no_comparison(slots: tuple[str, ...]) -> None:
    _app()
    item = replace(DAGGER, name="Other", equip_slot=slots[0], compatible_slots=slots)
    compared, alternate = equipped_comparisons(item, EQUIPMENT)
    assert compared is None and alternate is None

    slot = InventorySlotWidget(item, 0, comparison_item=compared)
    _enter(slot)
    assert slot.hover_card is not None
    assert slot.hover_card.comparison_block is None
    _leave(slot)


@pytest.mark.parametrize("rarity", ["common", "uncommon", "rare", "epic", "legendary"])
def test_title_tone_matches_rarity(rarity: str) -> None:
    _app()
    card = ItemHoverCard(replace(DAGGER, rarity=rarity), _host())
    assert card.title_label.property("tone") == rarity


@pytest.mark.parametrize("anchor", [QPoint(1590, 400), QPoint(800, 890), QPoint(1595, 895)])
def test_card_near_edges_stays_inside_window(anchor: QPoint) -> None:
    _app()
    host = QWidget()
    host.setGeometry(0, 0, 1600, 900)
    host.show()
    window = QRect(0, 0, 1600, 900)
    card = ItemHoverCard(LONGSWORD, host)
    card.adjustSize()

    bounds = card_bounds(host, anchor, card.size())
    placed = QRect(place_card(card.size(), anchor, bounds), card.size())

    assert bounds.contains(placed)
    assert window.contains(placed)


def test_one_card_at_a_time_and_none_after_leave() -> None:
    _app()
    host = QWidget()
    first = InventorySlotWidget(DAGGER, 0)
    second = InventorySlotWidget(LONGSWORD, 1)
    first.setParent(host)
    second.setParent(host)

    _enter(first)
    _enter(second)
    assert len([c for c in _open_cards() if not c.property("companion")]) == 1

    _leave(first)
    _leave(second)
    _flush()
    assert _open_cards() == []


class _WindowShowSpy(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.strays: list[tuple[str, str]] = []

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]  # noqa: N802
        shown = event.type() == QEvent.Type.Show and watched.isWidgetType() and watched.isWindow()
        if shown and not _is_card_window(watched):
            self.strays.append((type(watched).__name__, watched.objectName()))
        return False


def _is_card_window(widget: QWidget) -> bool:
    flags = widget.windowFlags()
    return (
        isinstance(widget, PositionedHoverCard)
        and Qt.WindowType.ToolTip in flags
        and Qt.WindowType.FramelessWindowHint in flags
    )


def test_hover_opens_no_window_but_the_card() -> None:
    # A card child shown before it had a parent became a native captioned window.
    app = _app()
    host = _host()
    host.resize(400, 300)
    rows = (
        SkillDetailRow(SkillView("Attack", 52, current_xp=380, next_level_xp=600)),
        InventorySlotWidget(LONGSWORD, 0, comparison_item=DAGGER),
        PowerEntry(POWER),
    )
    spy = _WindowShowSpy()
    app.installEventFilter(spy)
    try:
        for row in rows:
            row.setParent(host)
            _enter(row)
            assert _open_cards(), type(row).__name__
            visible = [w for w in QApplication.topLevelWidgets() if w.isVisible()]
            assert visible and all(_is_card_window(w) for w in visible), visible
            _leave(row)
            _flush()
    finally:
        app.removeEventFilter(spy)
    assert spy.strays == []


def test_native_tooltip_is_suppressed_while_a_card_shows() -> None:
    _app()
    item = CombatSkillGridItem(POWER)
    assert item.toolTip()
    _enter(item)
    assert _open_cards()
    event = QHelpEvent(QEvent.Type.ToolTip, QPoint(5, 5), item.mapToGlobal(QPoint(5, 5)))
    QApplication.sendEvent(item, event)
    assert not QToolTip.isVisible()
    _leave(item)
    _flush()


def test_skill_row_hover_makes_a_card_and_leaves_tooltip_empty() -> None:
    _app()
    row = SkillDetailRow(SkillView("Attack", 52, current_xp=380, next_level_xp=600))

    _enter(row)
    assert isinstance(row.hover_card, SkillHoverCard)
    assert row.toolTip() == ""
    _leave(row)
    _flush()
    assert row.hover_card is None and _open_cards() == []
