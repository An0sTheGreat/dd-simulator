"""Configurable inventory and equipment grids with semantic action requests."""

from dataclasses import replace
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, QPoint, Qt, Signal
from PySide6.QtGui import QCursor, QDrag, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QLabel,
    QMenu,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.ui.models.presentation import EquipmentSlotView, InventorySlotView
from dd_simulator.ui.item_icons import item_icon_label, refresh_item_icon
from dd_simulator.ui.widgets.hover_card import CARD_ICON_SIZE, TooltipCard, card_label

import json
import re


INVENTORY_SLOT_MIME = "application/x-dd-inventory-slot"
EQUIPMENT_SLOT_MIME = "application/x-dd-equipment-slot"
INVENTORY_SLOT_SIZE = 96
EQUIPMENT_BOARD_SIZE = 735
EQUIPMENT_SLOT_SIZE = 100
EQUIPMENT_SLOT_SPACING = 8
ART_ROOT = Path(__file__).resolve().parents[1] / "assets" / "inventory"

EQUIPMENT_SINGLE_ASSETS = {
    "ammunition": "equipment_singles/inv_ammunition.png",
    "body": "equipment_singles/inv_body.png",
    "feet": "equipment_singles/inv_feet.png",
    "hands": "equipment_singles/inv_hands.png",
    "head": "equipment_singles/inv_head.png",
    "main hand": "equipment_singles/inv_main_hand.png",
    "neck": "equipment_singles/inv_neck.png",
    "off hand": "equipment_singles/inv_off_hand.png",
    "ring": "equipment_singles/inv_ring.png",
}


def _current_theme_id() -> str:
    application = QApplication.instance()
    if application is None:
        return "high_fantasy"
    return str(application.property("themeId") or "high_fantasy")


@lru_cache(maxsize=16)
def _themed_artwork(
    asset_name: str,
    width: int,
    theme_id: str,
    height: int | None = None,
) -> QPixmap:
    """Return crisp, runtime-tinted layout art for either supported theme."""

    source = QPixmap(str(ART_ROOT / asset_name))
    if source.isNull():
        return QPixmap()
    if asset_name == "Inventory_Slot_1.png" or asset_name.startswith(
        "equipment_singles/"
    ):
        # The source includes five transparent pixels on each edge. Cropping
        # those makes inventory and equipment wells fill the same cell.
        source = source.copy(5, 5, 22, 22)
    pixmap = source.scaled(
        width,
        width if height is None else height,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.FastTransformation,
    )
    return pixmap


def _icon_context(item: InventorySlotView) -> str:
    return " ".join(
        value for value in (
            item.item_type,
            item.equip_slot,
            " ".join(item.compatible_slots),
            item.damage,
            item.armor,
            item.effects,
            item.description,
        ) if value
    )


def _readable_effect(raw: str) -> str:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return raw
    if not isinstance(value, dict):
        return raw
    details: list[str] = []
    resources = value.get("resources")
    if isinstance(resources, dict):
        details.extend(
            f"{str(name).replace('_', ' ').title()} {int(amount):+d}"
            for name, amount in resources.items()
            if isinstance(amount, (int, float))
        )
    removed = value.get("remove_statuses")
    if isinstance(removed, list) and removed:
        details.append("Removes " + ", ".join(str(status) for status in removed))
    summary = value.get("use_summary")
    if isinstance(summary, str) and summary.strip() and not details:
        details.append(summary.strip())
    return "; ".join(details) or "Utility effect"


def equipped_comparisons(
    item: InventorySlotView,
    equipment: tuple[EquipmentSlotView, ...],
) -> tuple[InventorySlotView | None, InventorySlotView | None]:
    """Return the default and optional off-hand comparison for an item."""

    compatible = {
        value.casefold().strip()
        for value in (item.compatible_slots or ((item.equip_slot,) if item.equip_slot else ()))
        if value.strip()
    }
    if not compatible:
        return None, None
    matches: dict[str, InventorySlotView] = {}
    for slot in equipment:
        key = slot.slot_name.casefold().strip()
        if key not in compatible or not slot.item_name:
            continue
        equipped = slot.item or InventorySlotView(
            slot.item_name, quantity=1,
            description=f"Equipped in the {slot.slot_name} slot.",
            equip_slot=slot.slot_name, category="equipment",
            compatible_slots=(slot.slot_name,),
        )
        matches[key] = replace(equipped, status="Equipped")
    main = matches.get("main hand")
    offhand = matches.get("off hand")
    default = main or offhand or next(iter(matches.values()), None)
    alternate = offhand if main is not None and offhand is not None else None
    return default, alternate


def _dice_average(text: str) -> float | None:
    match = re.search(r"(\d+)\s*d\s*(\d+)(?:\s*([+-])\s*(\d+))?", text)
    if match is None:
        return None
    count, sides, sign, bonus = match.groups()
    flat = int(bonus or 0) * (-1 if sign == "-" else 1)
    return int(count) * (int(sides) + 1) / 2 + flat


def _first_int(text: str) -> int | None:
    match = re.search(r"[+-]?\d+", text)
    return int(match.group()) if match else None


def _json_object(raw: str) -> dict | None:
    try:
        value = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _readable_pairs(raw: str, *, skip: tuple[str, ...] = ()) -> str:
    """Bonus, penalty and requirement JSON ({"strength": 2}) as "Strength +2"."""

    value = _json_object(raw)
    if value is None:
        return raw.strip()
    return ", ".join(
        f"{str(key).replace('_', ' ').title()} "
        + (f"{amount:+d}" if isinstance(amount, int) else str(amount))
        for key, amount in value.items()
        if key not in skip
    )


def _attack_bonus(item: InventorySlotView) -> int | None:
    value = _json_object(item.bonuses)
    if value is not None:
        attack = value.get("attack")
        return attack if isinstance(attack, int) else None
    match = re.search(r"([+-]\d+)\s*(?:to\s+)?attack", item.bonuses, re.IGNORECASE)
    return int(match.group(1)) if match else None


def comparison_deltas(
    item: InventorySlotView, equipped: InventorySlotView,
) -> list[tuple[str, bool]]:
    """(text, better) for each stat that differs from the equipped item."""

    deltas: list[tuple[str, bool]] = []
    for name, mine, theirs, higher_is_better, spec in (
        ("avg damage", _dice_average(item.damage), _dice_average(equipped.damage), True, "+.1f"),
        ("attack", _attack_bonus(item), _attack_bonus(equipped), True, "+d"),
        ("armor", _first_int(item.armor), _first_int(equipped.armor), True, "+d"),
        ("lb", item.weight or None, equipped.weight or None, False, "+.1f"),
    ):
        if mine is None and theirs is None:
            continue
        delta = (mine or 0) - (theirs or 0)
        if delta:
            deltas.append((f"{format(delta, spec)} {name}", (delta > 0) == higher_is_better))
    return deltas


def _item_rows(item: InventorySlotView) -> list[tuple[str, str]]:
    attack = _attack_bonus(item)
    rows = [
        ("Damage", item.damage),
        ("Healing", f"{item.healing} health" if item.healing else ""),
        ("Attack", f"{attack:+d}" if attack is not None else ""),
        ("Armor", item.armor),
        ("Effect", _readable_effect(item.effects) if _json_object(item.effects) != {} else ""),
        # Attack and armor have their own rows.
        ("Bonus", _readable_pairs(item.bonuses, skip=("attack", "armor"))),
        ("Penalty", _readable_pairs(item.penalties)),
        ("Durability", f"{item.durability} / {item.maximum_durability or '?'}"
            if item.durability is not None else ""),
        ("Charges", f"{item.charges} / {item.maximum_charges or '?'}"
            if item.charges is not None else ""),
        ("Quantity", str(item.quantity) if item.quantity > 1 else ""),
        ("Weight", f"{item.weight:.1f} lb" if item.weight else ""),
        ("Value", f"{item.value_gp} gold" if item.value_gp else ""),
        ("Requires", _readable_pairs(item.requirements)),
    ]
    return [row for row in rows if row[1]] or [("Effect", "Utility item")]


def _item_subtitle(item: InventorySlotView) -> str:
    kind = item.category if item.category not in ("", "misc") else item.item_type
    slots = item.compatible_slots or ((item.equip_slot,) if item.equip_slot else ())
    parts = [item.rarity.title(), kind.title(), " or ".join(slots)]
    if item.status == "Equipped":
        parts.append("Equipped")
    if item.quest_item:
        parts.append("Quest item")
    if not item.identified:
        parts.append("Unidentified")
    return " · ".join(part for part in parts if part)


class ItemHoverCard(TooltipCard):
    """Item card; ``compared_with`` adds green/red deltas against an equipped item."""

    def __init__(
        self,
        item: InventorySlotView,
        parent: QWidget,
        *,
        equipped_comparison: bool = False,
        comparison_hint: str = "",
        compared_with: InventorySlotView | None = None,
    ) -> None:
        rarity = item.rarity.casefold()
        extras: list[QWidget] = []
        comparison_block: QFrame | None = None
        if compared_with is not None:
            deltas = comparison_deltas(item, compared_with)
            block = QFrame()
            block.setObjectName("tooltipComparison")
            block_layout = QGridLayout(block)
            block_layout.setContentsMargins(0, 6, 0, 0)
            block_layout.setHorizontalSpacing(10)
            block_layout.setVerticalSpacing(2)
            heading = card_label(f"Compared with {compared_with.name}", "tooltipComparisonTitle")
            block_layout.addWidget(heading, 0, 0, 1, 3)
            for index, (text, better) in enumerate(deltas or [("No stat changes", True)]):
                delta = card_label(text, "tooltipDelta")
                if deltas:
                    delta.setProperty("better", better)
                block_layout.addWidget(delta, 1 + index // 3, index % 3)
            block_layout.setColumnStretch(3, 1)  # pack the deltas to the left
            comparison_block = block
            extras.append(block)
        footer = comparison_hint
        if not equipped_comparison and not footer:
            footer = (
                "Drag to an equipment slot to equip · Right-click for options"
                if item.can_equip else "Right-click for options"
            )
        icon = item_icon_label(
            item.name or "Empty slot",
            rarity=item.rarity,
            category=item.category,
            context=_icon_context(item),
            size=CARD_ICON_SIZE,
            object_name="tooltipIcon",
        )
        super().__init__(
            parent,
            object_name="itemHoverCard",
            card_kind="item",
            title=item.name or "Empty slot",
            tone=rarity,
            subtitle=_item_subtitle(item),
            icon=icon,
            rows=_item_rows(item),
            extras=extras,
            description=item.description.strip() or "No additional description is available.",
            footer=footer,
        )
        self.item = item
        self.comparison_block = comparison_block
        self.setProperty("rarity", rarity)

def _start_item_drag(
    widget: QWidget,
    icon_label: QLabel,
    mime_type: str,
    value: int,
) -> None:  # type: ignore[no-untyped-def]
    """Start a move drag using only the item's transparent icon."""

    mime = QMimeData()
    mime.setData(mime_type, str(value).encode("ascii"))
    drag = QDrag(widget)
    drag.setMimeData(mime)
    pixmap = icon_label.pixmap()
    if pixmap is not None and not pixmap.isNull():
        drag.setPixmap(pixmap)
        drag.setHotSpot(QPoint(pixmap.width() // 2, pixmap.height() // 2))
    drag.exec(Qt.DropAction.MoveAction)


def _clear_grid(layout: QGridLayout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            # detached now, so findChildren never sees a slot that is pending deletion
            widget.hide()
            widget.setParent(None)
            widget.deleteLater()


def _quantity_badge(value: int) -> QLabel:
    badge = QLabel(str(value))
    badge.setObjectName("itemQuantityBadge")
    badge.setAccessibleName(f"Quantity {value}")
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    badge.setFixedSize(max(24, 12 + 7 * len(str(value))), 20)
    return badge


def well_inset(slot_side: int) -> int:
    """Gap between the slot's outer edge and its well art: 2 px at the 50 px card slot."""

    return max(1, slot_side // 25)


class InventorySlotWidget(QFrame):
    activated = Signal(int)
    navigation_requested = Signal(int, str)
    context_action_requested = Signal(int, str)
    drop_requested = Signal(int, int)
    equipment_drop_requested = Signal(int, int)

    def __init__(
        self,
        item: InventorySlotView,
        index: int,
        comparison_item: InventorySlotView | None = None,
        offhand_comparison_item: InventorySlotView | None = None,
        *,
        slot_size: int = INVENTORY_SLOT_SIZE,
    ) -> None:
        super().__init__()
        self.item = item
        self.index = index
        self.setObjectName("inventorySlot")
        self.setProperty("empty", item.is_empty)
        self.setProperty("selected", item.selected)
        self.setProperty("rarity", item.rarity)
        self.setProperty("questItem", item.quest_item)
        self.setAccessibleName(
            f"Inventory slot {index + 1}: {item.name or 'empty'}"
        )
        self.setAcceptDrops(True)
        self.setFixedSize(slot_size, slot_size)
        self.setFocusPolicy(
            Qt.FocusPolicy.NoFocus if item.is_empty else Qt.FocusPolicy.StrongFocus
        )
        self._hover_suppressed = False
        self.hover_card: ItemHoverCard | None = None
        self.comparison_item = comparison_item
        self.offhand_comparison_item = offhand_comparison_item
        self.comparison_hover_card: ItemHoverCard | None = None
        self._using_offhand_comparison = False

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # The well art spreads over the themed slot frame to just inside its outer
        # edge (see _place_well); the icon stays centred on the slot.
        self.artwork_label = QLabel(self)
        self.artwork_label.setObjectName("inventorySlotArtwork")
        self.artwork_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.artwork_label.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored
        )
        self._place_well()
        self._refresh_artwork()
        # ponytail: inner well art hidden for now; drop this line to bring it back
        self.artwork_label.hide()
        self.icon_label = item_icon_label(
            item.name or "",
            rarity=item.rarity,
            category=item.category,
            context=_icon_context(item),
            size=max(16, slot_size * 68 // INVENTORY_SLOT_SIZE),
        )
        if item.is_empty:
            self.icon_label.hide()
        layout.addWidget(self.icon_label, 0, 0, Qt.AlignmentFlag.AlignCenter)
        self.artwork_label.installEventFilter(self)
        if item.durability is not None and item.maximum_durability:
            durability_state = "low" if item.durability <= 25 else "normal"
            self.setProperty("durabilityState", durability_state)
        if item.quantity > 1:
            quantity = _quantity_badge(item.quantity)
            layout.addWidget(
                quantity,
                0,
                0,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
            )

    def refresh_theme_icon(self) -> None:
        self._refresh_artwork()
        if self.item.is_empty:
            self.icon_label.hide()
            return
        refresh_item_icon(
            self.icon_label,
            self.item.name or "Empty",
            rarity=self.item.rarity,
            category=self.item.category,
            context=_icon_context(self.item),
        )
        if self.hover_card is not None:
            refresh_item_icon(
                self.hover_card.icon_label,
                self.item.name or "Empty",
                rarity=self.item.rarity,
                category=self.item.category,
                context=_icon_context(self.item),
            )
        if self.comparison_hover_card is not None and self.comparison_item is not None:
            refresh_item_icon(
                self.comparison_hover_card.icon_label,
                self.comparison_item.name or "Equipped item",
                rarity=self.comparison_item.rarity,
                category=self.comparison_item.category,
                context=_icon_context(self.comparison_item),
            )

    def _refresh_artwork(self) -> None:
        self.artwork_label.setPixmap(
            _themed_artwork(
                "Inventory_Slot_1.png",
                max(1, self.artwork_label.width()),
                _current_theme_id(),
                max(1, self.artwork_label.height()),
            )
        )

    def _place_well(self) -> None:
        inset = well_inset(self.width())
        self.artwork_label.setGeometry(self.rect().adjusted(inset, inset, -inset, -inset))
        self.artwork_label.lower()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._place_well()
        # the hidden well gets no resize events of its own, so refit the icon here
        self._fit_to_frame()

    def changeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().changeEvent(event)
        # slots are fixed-size, so a theme switch (new frame width) never resizes the well
        if event.type() == QEvent.Type.StyleChange:
            self._place_well()
            self._fit_to_frame()

    def _fit_to_frame(self) -> None:
        # the icon keeps to the frame's inside, so it never covers the bronze rim
        inner = self.contentsRect()
        side = min(inner.width(), inner.height())
        self.icon_label.setFixedSize(max(12, side * 7 // 8), max(12, side * 7 // 8))
        self.refresh_theme_icon()

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        # A repeated enter while our card is up (showing or closing a card can
        # synthesise one) must not stack a new card, or enter/close ping-pongs.
        showing = self.hover_card is not None and self.hover_card.isVisible()
        if not self.item.is_empty and not self._hover_suppressed and not showing:
            hint = (
                "Hold Left Ctrl: Compare Off Hand"
                if self.offhand_comparison_item is not None else ""
            )
            self.hover_card = ItemHoverCard(
                self.item, self, comparison_hint=hint, compared_with=self.comparison_item,
            )
            self.hover_card.show_near(QCursor.pos())
            self._show_comparison(False)
            application = QApplication.instance()
            if application is not None and self.offhand_comparison_item is not None:
                application.installEventFilter(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        application = QApplication.instance()
        if application is not None:
            application.removeEventFilter(self)
        self.hide_hover_card()
        self._hover_suppressed = False
        super().leaveEvent(event)

    def hide_hover_card(self) -> None:
        if self.hover_card is not None:
            self.hover_card.close()
            self.hover_card.deleteLater()
            self.hover_card = None
        if self.comparison_hover_card is not None:
            self.comparison_hover_card.close()
            self.comparison_hover_card.deleteLater()
            self.comparison_hover_card = None

    def _show_comparison(self, use_offhand: bool) -> None:
        comparison = (
            self.offhand_comparison_item
            if use_offhand and self.offhand_comparison_item is not None
            else self.comparison_item
        )
        if comparison is None or self.hover_card is None:
            return
        if self.comparison_hover_card is not None:
            self.comparison_hover_card.close()
            self.comparison_hover_card.deleteLater()
        self._using_offhand_comparison = use_offhand
        self.comparison_hover_card = ItemHoverCard(
            comparison, self, equipped_comparison=True,
        )
        self.comparison_hover_card.show_beside(self.hover_card)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if watched is self.artwork_label and event.type() == QEvent.Type.Resize:
            self._fit_to_frame()
        elif self.offhand_comparison_item is not None and event.type() in {
            QEvent.Type.KeyPress, QEvent.Type.KeyRelease,
        } and event.key() == Qt.Key.Key_Control:
            use_offhand = event.type() == QEvent.Type.KeyPress
            if use_offhand != self._using_offhand_comparison:
                self._show_comparison(use_offhand)
        return super().eventFilter(watched, event)

    def dismiss_hover_card(self) -> None:
        self._hover_suppressed = True
        self.hide_hover_card()

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def build_context_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("inventoryContextMenu")
        for label, action_name in (
            ("Inspect", "inspect"),
            ("Use", "use"),
            ("Equip", "equip"),
            ("Drop", "drop"),
        ):
            action = menu.addAction(label)
            enabled = not self.item.is_empty
            if action_name == "use":
                enabled = enabled and self.item.usable
            elif action_name == "equip":
                enabled = enabled and self.item.can_equip
            elif action_name == "drop":
                enabled = enabled and self.item.can_drop
            action.setEnabled(enabled)
            action.triggered.connect(
                lambda _checked=False, name=action_name: self.context_action_requested.emit(
                    self.index,
                    name,
                )
            )
        return menu

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.dismiss_hover_card()
        if event.button() == Qt.MouseButton.LeftButton and not self.item.is_empty:
            self.activated.emit(self.index)
            self.setFocus()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.buttons() & Qt.MouseButton.LeftButton and not self.item.is_empty:
            self.dismiss_hover_card()
            _start_item_drag(
                self,
                self.icon_label,
                INVENTORY_SLOT_MIME,
                self.index,
            )
            return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasFormat(INVENTORY_SLOT_MIME):
            event.acceptProposedAction()
        elif self.item.is_empty and event.mimeData().hasFormat(EQUIPMENT_SLOT_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.dismiss_hover_card()
        if event.mimeData().hasFormat(EQUIPMENT_SLOT_MIME) and self.item.is_empty:
            try:
                source = int(bytes(event.mimeData().data(EQUIPMENT_SLOT_MIME)).decode("ascii"))
            except (TypeError, ValueError):
                event.ignore()
                return
            self.equipment_drop_requested.emit(source, self.index)
            event.acceptProposedAction()
            return
        try:
            source = int(bytes(event.mimeData().data(INVENTORY_SLOT_MIME)).decode("ascii"))
        except (TypeError, ValueError):
            event.ignore()
            return
        self.drop_requested.emit(source, self.index)
        event.acceptProposedAction()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.dismiss_hover_card()
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if not self.item.is_empty:
                self.activated.emit(self.index)
            event.accept()
            return
        directions = {
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_Right: "right",
            Qt.Key.Key_Up: "up",
            Qt.Key.Key_Down: "down",
        }
        direction = directions.get(event.key())
        if direction:
            self.navigation_requested.emit(self.index, direction)
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.dismiss_hover_card()
        if self.item.is_empty:
            return
        self.build_context_menu().exec(event.globalPos())


class InventoryGrid(QWidget):
    selection_changed = Signal(int)
    context_action_requested = Signal(int, str)
    move_requested = Signal(int, int)
    equipment_drop_requested = Signal(int, int)
    focus_moved = Signal(int)

    def __init__(
        self,
        items: tuple[InventorySlotView, ...],
        *,
        columns: int = 4,
        slot_count: int | None = None,
        index_offset: int = 0,
        equipment: tuple[EquipmentSlotView, ...] = (),
        slot_size: int = INVENTORY_SLOT_SIZE,
        spacing: int = 0,
    ) -> None:
        super().__init__()
        self.setObjectName("inventoryGrid")
        self.slot_size = slot_size
        self.spacing = spacing
        self.columns = max(1, columns)
        self.slot_count = max(len(items), slot_count or len(items))
        self.index_offset = max(0, index_offset)
        self.equipment = equipment
        self.items = items
        self.slots: list[InventorySlotWidget] = []
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, -50, 0, 0)
        self.grid.setSpacing(spacing)
        self.set_items(items)

    def _refresh_geometry(self) -> None:
        rows = max(1, (self.slot_count + self.columns - 1) // self.columns)
        pitch = self.slot_size + self.spacing
        self.setFixedSize(
            self.columns * pitch - self.spacing,
            rows * pitch - self.spacing,
        )

    def _relayout_slots(self) -> None:
        for local_index, slot in enumerate(self.slots):
            self.grid.addWidget(
                slot,
                local_index // self.columns,
                local_index % self.columns,
            )
        self._refresh_geometry()

    def set_columns(self, columns: int) -> None:
        columns = max(1, columns)
        if columns != self.columns:
            self.columns = columns
            self._relayout_slots()

    def set_items(
        self,
        items: tuple[InventorySlotView, ...],
        *,
        index_offset: int | None = None,
    ) -> None:
        """Rebind the grid from presentation data only."""

        if index_offset is not None:
            self.index_offset = max(0, index_offset)
        self.items = items
        _clear_grid(self.grid)
        self.slots.clear()
        total = max(self.slot_count, len(items))
        padded = (*items, *(InventorySlotView(None) for _ in range(total - len(items))))
        for local_index, item in enumerate(padded):
            index = self.index_offset + local_index
            main_comparison, offhand_comparison = self._equipped_comparisons(item)
            slot = InventorySlotWidget(
                item, index, main_comparison, offhand_comparison,
                slot_size=self.slot_size,
            )
            slot.activated.connect(self.select_index)
            slot.navigation_requested.connect(self._move_focus)
            slot.context_action_requested.connect(self.context_action_requested)
            slot.drop_requested.connect(self.move_requested)
            slot.equipment_drop_requested.connect(self.equipment_drop_requested)
            self.slots.append(slot)
            self.grid.addWidget(
                slot,
                local_index // self.columns,
                local_index % self.columns,
            )
        self._refresh_geometry()

    def set_equipment(self, equipment: tuple[EquipmentSlotView, ...]) -> None:
        """Refresh equipped-item comparisons without replacing the grid widget."""

        self.equipment = equipment
        self.set_items(self.items, index_offset=self.index_offset)

    def _equipped_comparisons(
        self, item: InventorySlotView,
    ) -> tuple[InventorySlotView | None, InventorySlotView | None]:
        return equipped_comparisons(item, self.equipment)

    def select_index(self, index: int) -> None:
        local_index = index - self.index_offset
        if not 0 <= local_index < len(self.slots) or self.slots[local_index].item.is_empty:
            return
        for slot in self.slots:
            slot.set_selected(slot.index == index)
            slot.hide_hover_card()
        self.selection_changed.emit(index)

    def _move_focus(self, index: int, direction: str) -> None:
        offsets = {
            "left": -1,
            "right": 1,
            "up": -self.columns,
            "down": self.columns,
        }
        candidate = index + offsets[direction]
        while self.index_offset <= candidate < self.index_offset + len(self.slots):
            slot = self.slots[candidate - self.index_offset]
            if not slot.item.is_empty:
                slot.setFocus()
                self.focus_moved.emit(candidate)
                return
            candidate += offsets[direction]


class EquipmentSlotWidget(QFrame):
    activated = Signal(int)
    navigation_requested = Signal(int, str)
    context_action_requested = Signal(int, str)
    inventory_drop_requested = Signal(int, int)

    def __init__(
        self,
        slot: EquipmentSlotView,
        index: int,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.slot = slot
        self.index = index
        self.setObjectName("equipmentSlot")
        self.setProperty("empty", slot.item_name is None)
        self.setProperty("selected", slot.selected)
        self.setProperty(
            "rarity",
            slot.item.rarity.casefold() if slot.item is not None else "common",
        )
        self.setAccessibleName(f"{slot.slot_name}: {slot.item_name or 'empty'}")
        self.setAcceptDrops(True)
        self.setFixedSize(EQUIPMENT_SLOT_SIZE, EQUIPMENT_SLOT_SIZE)
        self.setFocusPolicy(
            Qt.FocusPolicy.StrongFocus
            if slot.item_name is not None
            else Qt.FocusPolicy.NoFocus
        )
        self._hover_suppressed = False
        hover_item = slot.item
        if hover_item is None and slot.item_name is not None:
            hover_item = InventorySlotView(
                slot.item_name,
                quantity=1,
                description=(
                    f"Equipped in the {slot.slot_name} slot."
                    + (f" Condition: {slot.condition}." if slot.condition else "")
                ),
                equip_slot=slot.slot_name,
                status="Equipped",
                category="equipment",
                compatible_slots=(slot.slot_name,),
            )
        self.hover_item = hover_item
        self.hover_card: ItemHoverCard | None = None

        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setVerticalSpacing(0)
        self.artwork_asset = EQUIPMENT_SINGLE_ASSETS.get(
            slot.slot_name.casefold(), "equipment_singles/inv_ring.png"
        )
        self.artwork_label = QLabel(self)
        self.artwork_label.setObjectName("equipmentSlotArtwork")
        self.artwork_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.artwork_label.setFixedSize(EQUIPMENT_SLOT_SIZE, EQUIPMENT_SLOT_SIZE)
        layout.addWidget(self.artwork_label, 0, 0, Qt.AlignmentFlag.AlignCenter)
        self.occupied_artwork_label = QLabel(self)
        self.occupied_artwork_label.setObjectName("equipmentOccupiedArtwork")
        self.occupied_artwork_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents, True
        )
        self.occupied_artwork_label.setFixedSize(
            EQUIPMENT_SLOT_SIZE, EQUIPMENT_SLOT_SIZE
        )
        self.occupied_artwork_label.setVisible(slot.item_name is not None)
        layout.addWidget(
            self.occupied_artwork_label, 0, 0, Qt.AlignmentFlag.AlignCenter
        )
        self.icon_label = item_icon_label(
            slot.item_name or "",
            rarity=hover_item.rarity if hover_item is not None else "common",
            category=hover_item.category if hover_item is not None else "equipment",
            context=_icon_context(hover_item) if hover_item is not None else slot.slot_name,
            size=200,
            object_name="equipmentItemIcon",
        )
        if slot.item_name is None:
            self.icon_label.hide()
        layout.addWidget(self.icon_label, 0, 0, Qt.AlignmentFlag.AlignCenter)
        quantity_value = 0
        if slot.item is not None:
            quantity_value = slot.item.quantity
        elif slot.slot_name.casefold() == "ammunition" and slot.condition.isdigit():
            quantity_value = int(slot.condition)
        if quantity_value > 1:
            quantity = _quantity_badge(quantity_value)
            layout.addWidget(
                quantity,
                0,
                0,
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
            )
        self._refresh_artwork()

    def set_display_size(self, size: int) -> None:
        size = max(1, min(EQUIPMENT_SLOT_SIZE, size))
        self.setFixedSize(size, size)
        self.artwork_label.setFixedSize(size, size)
        self.occupied_artwork_label.setFixedSize(size, size)
        icon_size = max(16, min(200, size - 4))
        if self.icon_label.width() != icon_size:
            self.icon_label.setFixedSize(icon_size, icon_size)
        self.refresh_theme_icon()

    def _refresh_artwork(self) -> None:
        self.artwork_label.setPixmap(
            _themed_artwork(
                self.artwork_asset,
                self.artwork_label.width(),
                _current_theme_id(),
                self.artwork_label.height(),
            )
        )
        self.occupied_artwork_label.setPixmap(
            _themed_artwork(
                "Inventory_Slot_1.png",
                self.occupied_artwork_label.width(),
                _current_theme_id(),
                self.occupied_artwork_label.height(),
            )
        )

    def refresh_theme_icon(self) -> None:
        self._refresh_artwork()
        if self.slot.item_name is None:
            self.icon_label.hide()
            return
        item = self.slot.item
        refresh_item_icon(
            self.icon_label,
            self.slot.item_name or self.slot.slot_name,
            rarity=item.rarity if item is not None else "common",
            category=item.category if item is not None else "equipment",
            context=_icon_context(item) if item is not None else self.slot.slot_name,
        )
        if self.hover_card is not None:
            hover_item = self.hover_card.item
            refresh_item_icon(
                self.hover_card.icon_label,
                hover_item.name or self.slot.slot_name,
                rarity=hover_item.rarity,
                category=hover_item.category,
                context=_icon_context(hover_item),
            )

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self.hover_item is not None and not self._hover_suppressed:
            self.hover_card = ItemHoverCard(self.hover_item, self)
            self.hover_card.show_near(QCursor.pos())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.hide_hover_card()
        self._hover_suppressed = False
        super().leaveEvent(event)

    def hide_hover_card(self) -> None:
        if self.hover_card is not None:
            self.hover_card.close()
            self.hover_card.deleteLater()
            self.hover_card = None

    def dismiss_hover_card(self) -> None:
        self._hover_suppressed = True
        self.hide_hover_card()

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", selected)
        self.style().unpolish(self)
        self.style().polish(self)

    def build_context_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("equipmentContextMenu")
        for label, action_name in (("Inspect", "inspect"), ("Unequip", "unequip")):
            action = menu.addAction(label)
            action.setEnabled(self.slot.item_name is not None)
            action.triggered.connect(
                lambda _checked=False, name=action_name: self.context_action_requested.emit(
                    self.index,
                    name,
                )
            )
        return menu

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.dismiss_hover_card()
        if event.button() == Qt.MouseButton.LeftButton and self.slot.item_name is not None:
            self.activated.emit(self.index)
            self.setFocus()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.buttons() & Qt.MouseButton.LeftButton and self.slot.item_name is not None:
            self.dismiss_hover_card()
            _start_item_drag(
                self,
                self.icon_label,
                EQUIPMENT_SLOT_MIME,
                self.index,
            )
            return
        super().mouseMoveEvent(event)

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.mimeData().hasFormat(INVENTORY_SLOT_MIME):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.dismiss_hover_card()
        try:
            source = int(bytes(event.mimeData().data(INVENTORY_SLOT_MIME)).decode("ascii"))
        except (TypeError, ValueError):
            event.ignore()
            return
        self.inventory_drop_requested.emit(source, self.index)
        event.acceptProposedAction()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.dismiss_hover_card()
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            if self.slot.item_name is not None:
                self.activated.emit(self.index)
            event.accept()
            return
        directions = {
            Qt.Key.Key_Left: "left",
            Qt.Key.Key_Right: "right",
            Qt.Key.Key_Up: "up",
            Qt.Key.Key_Down: "down",
        }
        direction = directions.get(event.key())
        if direction:
            self.navigation_requested.emit(self.index, direction)
            event.accept()
            return
        super().keyPressEvent(event)

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.dismiss_hover_card()
        if self.slot.item_name is None:
            return
        self.build_context_menu().exec(event.globalPos())


class EquipmentGrid(QWidget):
    selection_changed = Signal(int)
    context_action_requested = Signal(int, str)
    inventory_drop_requested = Signal(int, int)

    def __init__(
        self,
        slots: tuple[EquipmentSlotView, ...],
        *,
        columns: int = 4,
        slot_names: tuple[str, ...] | None = None,
        slot_size: int = EQUIPMENT_SLOT_SIZE,
        spacing: int = EQUIPMENT_SLOT_SPACING,
    ) -> None:
        super().__init__()
        self.setObjectName("equipmentGrid")
        self.columns = max(1, columns)
        self.slot_size = max(1, min(EQUIPMENT_SLOT_SIZE, slot_size))
        self.spacing = max(0, spacing)
        self.slot_names = slot_names
        self.slots: list[EquipmentSlotWidget] = []
        self.visual_indices: list[int] = []
        self.slots_by_index: dict[int, EquipmentSlotWidget] = {}
        self.empty_label: QLabel | None = None
        self.grid = QGridLayout(self)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(self.spacing)
        self.grid.setVerticalSpacing(self.spacing)
        self.set_slots(slots)

    def set_slots(self, slots: tuple[EquipmentSlotView, ...]) -> None:
        """Rebind equipment data while preserving the grid and its signal wiring."""

        _clear_grid(self.grid)
        self.slots.clear()
        self.visual_indices.clear()
        self.slots_by_index.clear()
        if self.empty_label is not None:
            self.empty_label.deleteLater()
            self.empty_label = None
        if not slots:
            self.empty_label = QLabel("No equipment slots configured", self)
            self.empty_label.setObjectName("equipmentGridEmptyState")
            self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.empty_label.setToolTip(
                "Equipment slots are supplied by character and campaign rules"
            )
            self.setFixedSize(self.slot_size, self.slot_size)
            return
        indexed_by_name = {
            slot.slot_name.casefold(): index for index, slot in enumerate(slots)
        }
        requested_names = tuple(
            name.casefold() for name in (
                self.slot_names
                if self.slot_names is not None
                else tuple(slot.slot_name for slot in slots)
            )
        )
        self.visual_indices = [
            indexed_by_name[name] for name in requested_names if name in indexed_by_name
        ]
        for visual_index, source_index in enumerate(self.visual_indices):
            slot = slots[source_index]
            widget = EquipmentSlotWidget(slot, source_index, self)
            widget.set_display_size(self.slot_size)
            widget.activated.connect(self.select_index)
            widget.navigation_requested.connect(self._move_focus)
            widget.context_action_requested.connect(self.context_action_requested)
            widget.inventory_drop_requested.connect(self.inventory_drop_requested)
            self.slots.append(widget)
            self.slots_by_index[source_index] = widget
            self.grid.addWidget(
                widget,
                visual_index // self.columns,
                visual_index % self.columns,
            )
        rows = max(1, (len(self.slots) + self.columns - 1) // self.columns)
        used_columns = min(self.columns, max(1, len(self.slots)))
        self.setFixedSize(
            used_columns * self.slot_size + (used_columns - 1) * self.spacing,
            rows * self.slot_size + (rows - 1) * self.spacing,
        )

    def refresh_theme_icon(self) -> None:
        for slot in self.slots:
            slot.refresh_theme_icon()

    def select_index(self, index: int) -> None:
        selected = self.slots_by_index.get(index)
        if selected is None or selected.slot.item_name is None:
            return
        for slot in self.slots:
            slot.set_selected(slot.index == index)
            slot.hide_hover_card()
        self.selection_changed.emit(index)

    def _move_focus(self, index: int, direction: str) -> None:
        offsets = {
            "left": -1,
            "right": 1,
            "up": -self.columns,
            "down": self.columns,
        }
        try:
            candidate = self.visual_indices.index(index) + offsets[direction]
        except ValueError:
            return
        while 0 <= candidate < len(self.visual_indices):
            source_index = self.visual_indices[candidate]
            slot = self.slots_by_index[source_index]
            if slot.slot.item_name is not None:
                slot.setFocus()
                return
            candidate += offsets[direction]
