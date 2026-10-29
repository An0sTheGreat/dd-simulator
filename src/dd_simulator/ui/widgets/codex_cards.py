"""Concept T left-column cards: the scrolling Inventory card and the Abilities & Spells card."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.ui.models.presentation import (
    CombatActionOptionView,
    EquipmentSlotView,
    InventorySlotView,
)
from dd_simulator.ui.power_icons import action_icon_path
from dd_simulator.ui.widgets.inventory_grid import InventoryGrid
from dd_simulator.ui.widgets.scene_view import ElidedLabel
from dd_simulator.ui.widgets.skills_grid import AbilityHoverCard


CARD_COLUMNS = 5
CARD_VISIBLE_ROWS = 5
CARD_MIN_SLOTS = 36
CARD_SLOT_SIZE = 68
CARD_SLOT_SPACING = 3
CARD_SCROLLBAR_GAP = 5  # between the fifth column and the scrollbar, as in the mockup
CARD_SCROLLBAR_GUTTER = 10  # 5 px gap + 5 px themed scrollbar, as in the mockup
DRAG_SCROLL_ZONE = 24
DRAG_SCROLL_STEP = 12
POWER_ICON_SIZE = 38
SORT_MODES = (("Default", "default"), ("Rarity", "rarity"), ("Type", "type"), ("Value", "value"))


def _heading(title: str, count: int | None = None) -> QWidget:
    row = QWidget()
    row.setObjectName("codexCardHeadingRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    label = QLabel(title.upper())
    label.setObjectName("codexCardHeading")
    label.setTextFormat(Qt.TextFormat.PlainText)
    layout.addWidget(label)
    divider = QFrame()
    divider.setObjectName("codexCardDivider")
    divider.setFixedHeight(1)
    layout.addWidget(divider, 1, Qt.AlignmentFlag.AlignVCenter)
    if count is not None:
        number = QLabel(str(count))
        number.setObjectName("codexCardCount")
        number.setTextFormat(Qt.TextFormat.PlainText)
        number.setAccessibleName(f"{count} {title.casefold()}")
        layout.addWidget(number)
    return row


def plain_label(text: str, object_name: str, *, word_wrap: bool = False) -> QLabel:
    """Game or model text, never interpreted as rich text."""

    label = QLabel(text)
    label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(word_wrap)
    return label


def codex_card(
    title: str, object_name: str, *, count: int | None = None
) -> tuple[QFrame, QVBoxLayout]:
    """The shared page card: codex frame, small-caps heading with divider and optional count.

    Styled by ``QFrame[codexCard="true"]`` and ``QFrame[pageCard="true"]`` in each theme.
    """

    card = QFrame()
    card.setObjectName(object_name)
    return card, make_codex_card(card, title, count=count)


def make_codex_card(card: QFrame, title: str, *, count: int | None = None) -> QVBoxLayout:
    """Turn an existing frame (a panel subclass) into a page card; returns its layout."""

    card.setProperty("codexCard", True)
    card.setProperty("pageCard", True)
    card.setAccessibleName(title)
    layout = QVBoxLayout(card)
    layout.setContentsMargins(8, 2, 8, 4)
    layout.setSpacing(5)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    layout.addWidget(_heading(title, count))
    return layout


def icon_row(icon: QWidget, name: str, meta: str, *, rarity: str = "") -> QWidget:
    """Icon, name (rarity-coloured when given) and a muted meta line, as in the codex cards."""

    row = QWidget()
    row.setObjectName("pageCardRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(icon)
    text = QVBoxLayout()
    text.setContentsMargins(0, 0, 0, 0)
    text.setSpacing(0)
    title = plain_label(name, "pageCardName", word_wrap=True)
    title.setProperty("rarity", rarity)
    text.addWidget(title)
    text.addWidget(plain_label(meta, "pageCardMeta", word_wrap=True))
    layout.addLayout(text, 1)
    return row


def bag_slots(
    items: tuple[InventorySlotView, ...],
    capacity: int,
    *,
    columns: int = CARD_COLUMNS,
    visible_rows: int = CARD_VISIBLE_ROWS,
) -> tuple[InventorySlotView, ...]:
    """Lay occupied items out by bag position in whole rows: at least 36 slots, every
    visible row, every row up to the last item plus one spare row."""

    placed = {
        item.position if item.position is not None else index: item
        for index, item in enumerate(items)
    }
    highest = max(placed, default=-1)
    rows = max(-(-CARD_MIN_SLOTS // columns), visible_rows, highest // columns + 2)
    count = min(max(0, capacity), rows * columns)
    return tuple(placed.get(position, InventorySlotView(None)) for position in range(count))


class InventoryCard(QFrame):
    """Viewport over the whole bag that wraps to as many whole columns and rows of
    fixed-size slots as the card has room for; slot indices are real bag positions."""

    selection_changed = Signal(int)
    context_action_requested = Signal(int, str)
    move_requested = Signal(int, int)
    equipment_drop_requested = Signal(int, int)
    auto_sort_requested = Signal(str)

    def __init__(
        self,
        items: tuple[InventorySlotView, ...] = (),
        *,
        capacity: int = 320,
        equipment: tuple[EquipmentSlotView, ...] = (),
    ) -> None:
        super().__init__()
        self.setObjectName("inventoryCard")
        self.setProperty("codexCard", True)
        self.setAccessibleName("Inventory")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.items: tuple[InventorySlotView, ...] = ()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 2, 8, 2)
        layout.setSpacing(6)
        layout.addWidget(_heading("Inventory"))

        self.grid = InventoryGrid(
            (), columns=CARD_COLUMNS, equipment=equipment,
            slot_size=CARD_SLOT_SIZE, spacing=CARD_SLOT_SPACING,
        )
        self.grid.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.selection_changed.connect(self.selection_changed)
        self.grid.context_action_requested.connect(self.context_action_requested)
        self.grid.move_requested.connect(self.move_requested)
        self.grid.equipment_drop_requested.connect(self.equipment_drop_requested)
        self.grid.focus_moved.connect(self.scroll_to_position)

        self.pitch = CARD_SLOT_SIZE + CARD_SLOT_SPACING
        self.scroll = QScrollArea()
        self.scroll.setObjectName("inventoryCardScroll")
        self.scroll.setAccessibleName("Inventory slots")
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(False)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.scroll.setWidget(self.grid)
        self.visible_rows = CARD_VISIBLE_ROWS
        self._fit_scroll()
        bar = self.scroll.verticalScrollBar()
        bar.valueChanged.connect(self._refresh_footer)
        # Whole rows only, centred between heading and footer when the card is taller.
        layout.addStretch(1)
        layout.addWidget(self.scroll)
        layout.addStretch(1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, CARD_SCROLLBAR_GUTTER, 0)
        self.count_label = QLabel()
        self.count_label.setObjectName("inventoryCardCount")
        footer.addWidget(self.count_label, 1)
        self.auto_sort_button = QToolButton()
        self.auto_sort_button.setObjectName("inventoryCardAutoSort")
        self.auto_sort_button.setText("AUTO-SORT")
        self.auto_sort_button.setAccessibleName("Auto-sort inventory")
        self.auto_sort_button.setToolTip("Choose how unequipped inventory is sorted")
        self.auto_sort_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self.auto_sort_button)
        menu.setObjectName("autoSortInventoryMenu")
        for label, mode in SORT_MODES:
            menu.addAction(label).triggered.connect(
                lambda _checked=False, value=mode: self.auto_sort_requested.emit(value)
            )
        self.auto_sort_button.setMenu(menu)
        footer.addWidget(self.auto_sort_button)
        layout.addLayout(footer)
        self._fit_scroll()  # again, now the minimum height can count the footer

        self._drag_y = 0
        self._drag_timer = QTimer(self)
        self._drag_timer.setInterval(40)
        self._drag_timer.timeout.connect(self._drag_scroll_tick)
        self.set_inventory(items, capacity=capacity)

    def _fit_scroll(self) -> None:
        # The gutter is sized from the scrollbar the active style really draws, so a
        # wider bar (no theme, another style) never covers the fifth column.
        bar = self.scroll.verticalScrollBar()
        bar.ensurePolished()
        # never narrower than five columns; wider cards wrap to more (see _fit_rows)
        self.scroll.setMinimumWidth(
            CARD_COLUMNS * self.pitch - CARD_SLOT_SPACING + CARD_SCROLLBAR_GAP
            + bar.sizeHint().width()
        )
        # scroll area has no frame
        self.scroll.setFixedHeight(self.visible_rows * self.pitch - CARD_SLOT_SPACING)
        # one wheel notch (3 steps) is about one row
        bar.setSingleStep(self.pitch // 3)
        # Let a short card show fewer whole rows instead of clipping the bottom one.
        chrome = self.sizeHint().height() - self.scroll.height()
        self.setMinimumHeight(chrome + self.pitch - CARD_SLOT_SPACING)

    def _fit_rows(self) -> None:
        chrome = self.sizeHint().height() - self.scroll.height()
        rows = (self.height() - chrome + CARD_SLOT_SPACING) // self.pitch
        rows = max(1, rows)
        bar = self.scroll.verticalScrollBar().sizeHint().width()
        width = self.contentsRect().width() - self.layout().contentsMargins().left() * 2
        columns = max(
            CARD_COLUMNS,
            (width - bar - CARD_SCROLLBAR_GAP + CARD_SLOT_SPACING) // self.pitch,
        )
        if (rows, columns) != (self.visible_rows, self.grid.columns):
            self.visible_rows = rows
            self.grid.set_columns(columns)  # rewraps the existing slots in place
            self._fit_scroll()
            count = len(bag_slots(self.items, self.capacity, columns=columns, visible_rows=rows))
            if count != len(self.grid.slots):
                self._rebuild_keeping_selection()
            self._refresh_footer()

    def _rebuild_keeping_selection(self) -> None:
        selected = [slot.index for slot in self.grid.slots if slot.property("selected")]
        focused = [slot.index for slot in self.grid.slots if slot.hasFocus()]
        self.set_inventory(self.items, capacity=self.capacity)
        for slot in self.grid.slots:
            if slot.index in selected:
                slot.set_selected(True)
            if slot.index in focused:
                slot.setFocus()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self._fit_rows()

    def changeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().changeEvent(event)
        if event.type() == QEvent.Type.StyleChange:
            self._fit_scroll()
            self._fit_rows()

    def set_scale(self, scale: float) -> None:
        """Shrink the bag slots (keeping five rows visible) when the codex column is short."""

        size = round(CARD_SLOT_SIZE * max(0.6, min(1.0, scale)))
        if size == self.grid.slot_size:
            return
        self.grid.slot_size = size
        self.pitch = size + CARD_SLOT_SPACING
        self._fit_scroll()
        self._rebuild_keeping_selection()

    def set_inventory(
        self,
        items: tuple[InventorySlotView, ...],
        *,
        capacity: int = 320,
        equipment: tuple[EquipmentSlotView, ...] | None = None,
    ) -> None:
        """Rebind from presentation data; the scroll position survives the rebind."""

        self.items = items
        self.capacity = capacity
        if equipment is not None:
            self.grid.equipment = equipment
        slots = bag_slots(
            items, capacity, columns=self.grid.columns, visible_rows=self.visible_rows
        )
        self.grid.slot_count = len(slots)
        self.grid.set_items(slots)
        for slot in self.grid.slots:
            slot.installEventFilter(self)
        self._refresh_footer()

    def below_count(self) -> int:
        """Occupied slots whose row starts below the bottom edge of the viewport."""

        # the scroll area has no frame, so its fixed height is the viewport's
        bottom = self.scroll.verticalScrollBar().value() + self.scroll.height()
        return sum(
            1 for slot in self.grid.slots
            if not slot.item.is_empty and (slot.index // self.grid.columns) * self.pitch >= bottom
        )

    def _refresh_footer(self) -> None:
        self.count_label.setText(f"{len(self.items)} items · {self.below_count()} below")

    def scroll_to_position(self, position: int) -> None:
        if 0 <= position < len(self.grid.slots):
            self.scroll.ensureWidgetVisible(self.grid.slots[position], 0, 0)

    # Drag autoscroll: holding a dragged item near the top or bottom edge scrolls the bag,
    # so a move can reach any position. Qt sends no drag events while the cursor is still,
    # so a timer keeps scrolling until the drag leaves the edge, drops or is cancelled.
    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        kind = event.type()
        if kind == QEvent.Type.DragMove and isinstance(watched, QWidget):
            self._drag_y = watched.mapTo(self.scroll.viewport(), event.position().toPoint()).y()
            if self._drag_direction():
                self._drag_timer.start()
            else:
                self._drag_timer.stop()
        elif kind in (QEvent.Type.DragLeave, QEvent.Type.Drop):
            self._drag_timer.stop()
        return super().eventFilter(watched, event)

    def _drag_direction(self) -> int:
        if self._drag_y < DRAG_SCROLL_ZONE:
            return -1
        if self._drag_y > self.scroll.viewport().height() - DRAG_SCROLL_ZONE:
            return 1
        return 0

    def _drag_scroll_tick(self) -> None:
        bar = self.scroll.verticalScrollBar()
        bar.setValue(bar.value() + self._drag_direction() * DRAG_SCROLL_STEP)


def power_level(action: CombatActionOptionView) -> str:
    """"Cantrip" or the unlock level as a number; "" when the catalog gives none."""

    return next((value for name, value in action.stats if name == "Level"), "")


def _level_order(level: str) -> tuple[int, int]:
    return (0, 0) if level == "Cantrip" else (1, int(level) if level.isdigit() else 0)


def _power_detail(action: CombatActionOptionView) -> str:
    distance = next((value for name, value in action.stats if name == "Range"), "")
    label = action.resource_label
    if distance and distance not in label:
        label = " · ".join(part for part in (label, distance) if part)
    return label.replace(" | ", " · ")


class PowerEntry(QFrame):
    activated = Signal(str)

    def __init__(self, action: CombatActionOptionView, *, detail: str | None = None) -> None:
        super().__init__()
        self.action = action
        self.setObjectName("powerEntry")
        self.setProperty("available", action.available)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        status = action.status_label or ("Ready" if action.available else action.unavailable_reason)
        self.setAccessibleName(f"{action.name}, {action.kind}, {status}")
        self.hover_card: AbilityHoverCard | None = None
        self._hover_suppressed = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("powerEntryIcon")
        self.icon_label.setFixedSize(POWER_ICON_SIZE, POWER_ICON_SIZE)
        self.icon_label.setPixmap(
            QIcon(str(action_icon_path(action.key))).pixmap(POWER_ICON_SIZE - 2, POWER_ICON_SIZE - 2)
        )
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setEnabled(action.available)  # Qt draws its disabled (dimmed) pixmap
        layout.addWidget(self.icon_label)
        text = QVBoxLayout()
        text.setContentsMargins(0, 0, 0, 0)
        text.setSpacing(0)
        for object_name, value in (
            ("powerEntryName", action.name),
            ("powerEntryDetail", _power_detail(action) if detail is None else detail),
            ("powerEntryStatus", status),
        ):
            # Elides to the column's scroll viewport instead of running past its edge.
            label = ElidedLabel(value, object_name, tooltip_on_self=True)
            text.addWidget(label)
        self.status_label = label
        self.status_label.setProperty("ready", status.casefold() == "ready")
        layout.addLayout(text, 1)

    def _close_hover_card(self) -> None:
        if self.hover_card is not None:
            self.hover_card.close()
            self.hover_card.deleteLater()
            self.hover_card = None

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self._hover_suppressed:
            self.hover_card = AbilityHoverCard(self.action, self)
            self.hover_card.show_near(QCursor.pos())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._close_hover_card()
        self._hover_suppressed = False
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._hover_suppressed = True
        self._close_hover_card()
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.action.key)
        super().mousePressEvent(event)

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit(self.action.key)
            event.accept()
            return
        super().keyPressEvent(event)


class PowersCard(QFrame):
    """Abilities and Spells side by side; empty columns hide."""

    # Emits the catalog key; the receiver checks availability (Phase 6 wires it to combat).
    action_activated = Signal(str)
    rest_requested = Signal()

    def __init__(
        self,
        abilities: tuple[CombatActionOptionView, ...] = (),
        spells: tuple[CombatActionOptionView, ...] = (),
    ) -> None:
        super().__init__()
        self.setObjectName("powersCard")
        self.setProperty("codexCard", True)
        self.setAccessibleName("Abilities and spells")
        root = QVBoxLayout(self)
        root.setContentsMargins(8, 2, 8, 2)
        root.setSpacing(6)
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        root.addLayout(layout, 1)
        self.ability_column = self._column("Abilities", abilities)
        self.spell_column = self._column("Spells", spells)
        layout.addWidget(self.ability_column, 1)
        layout.addWidget(self.spell_column, 1)
        self.empty_label = QLabel("No abilities or spells yet")
        self.empty_label.setObjectName("powersCardEmpty")
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label, 1)
        self.ability_column.setVisible(bool(abilities))
        self.spell_column.setVisible(bool(spells))
        self.empty_label.setVisible(not abilities and not spells)
        # Outside combat only; the main window hides it while an encounter is active.
        self.rest_button = QToolButton()
        self.rest_button.setObjectName("powersCardRest")
        self.rest_button.setText("SHORT REST")
        self.rest_button.setAccessibleName("Take a short rest")
        self.rest_button.setToolTip("Take a short rest to recover outside combat")
        self.rest_button.clicked.connect(self.rest_requested)
        # Own footer row beneath both columns, so it never narrows them.
        root.addWidget(self.rest_button, 0, Qt.AlignmentFlag.AlignRight)

    def _column(self, title: str, actions: tuple[CombatActionOptionView, ...]) -> QWidget:
        column = QWidget()
        column.setObjectName("powersColumn")
        column.setAccessibleName(title)
        layout = QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(_heading(title, len(actions)))
        levels = sorted({power_level(action) for action in actions} - {""}, key=_level_order)
        column.level_buttons = {}  # type: ignore[attr-defined]
        if len(levels) > 1:
            # one level at a time, or All; replaces the old per-power "Unlock n" row
            picker = QHBoxLayout()
            picker.setContentsMargins(0, 0, 0, 0)
            picker.setSpacing(4)
            for level in ("All", *levels):
                button = QToolButton()
                button.setObjectName("powerLevelButton")
                button.setText(level if level in ("All", "Cantrip") else f"Lv {level}")
                button.setAccessibleName(f"Show {title.lower()}: {level if level in ('All', 'Cantrip') else f'level {level}'}")
                button.setCheckable(True)
                button.setChecked(level == "All")
                button.clicked.connect(lambda _c=False, c=column, value=level: self._show_level(c, value))
                picker.addWidget(button)
                column.level_buttons[level] = button  # type: ignore[attr-defined]
            picker.addStretch(1)
            layout.addLayout(picker)
        scroll = QScrollArea()
        scroll.setObjectName("powersColumnScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        entries = QWidget()
        entries.setObjectName("powersColumnEntries")
        entry_layout = QVBoxLayout(entries)
        entry_layout.setContentsMargins(0, 0, 0, 0)
        entry_layout.setSpacing(5)
        column.entries = []  # type: ignore[attr-defined]
        for action in actions:
            entry = PowerEntry(action)
            entry.activated.connect(self.action_activated)
            entry_layout.addWidget(entry)
            column.entries.append(entry)  # type: ignore[attr-defined]
        entry_layout.addStretch(1)
        scroll.setWidget(entries)
        layout.addWidget(scroll, 1)
        return column

    @staticmethod
    def _show_level(column: QWidget, level: str) -> None:
        for value, button in column.level_buttons.items():  # type: ignore[attr-defined]
            button.setChecked(value == level)
        for entry in column.entries:  # type: ignore[attr-defined]
            entry.setVisible(level == "All" or power_level(entry.action) == level)


class CodexCardRow(QWidget):
    """Inventory card and Powers card side by side at equal height."""

    def __init__(self, inventory: InventoryCard, powers: PowersCard) -> None:
        super().__init__()
        self.setObjectName("codexCardRow")
        self.inventory_card = inventory
        self.powers_card = powers
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        # the bag wraps to the width it gets, so the two cards share the row evenly
        layout.addWidget(inventory, 1)
        layout.addWidget(powers, 1)
