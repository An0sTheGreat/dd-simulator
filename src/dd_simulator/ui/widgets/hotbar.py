"""Quick-access hotbar: ten slots, keys 1-0, for favourite attacks, abilities and spells.

Right-click a slot to assign or clear it; left-click or its number key uses it in combat.
The main window persists the slot keys and resolves a use into a combat command.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCursor, QIcon
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMenu, QVBoxLayout

from dd_simulator.ui.models.presentation import CombatActionOptionView
from dd_simulator.ui.power_icons import action_icon_path, skill_icon_path
from dd_simulator.ui.widgets.skills_grid import AbilityHoverCard

HOTBAR_SLOTS = 10
HOTBAR_KEYS = tuple(str((index + 1) % 10) for index in range(HOTBAR_SLOTS))  # 1..9, 0
ATTACK_KEY = "attack"
SLOT_ICON_SIZE = 32


@dataclass(frozen=True, slots=True)
class HotbarAction:
    key: str
    name: str
    group: str  # "Attack", "Abilities" or "Spells"
    icon: Path
    available: bool = True
    option: CombatActionOptionView | None = None


def weapon_attack_option(
    weapons: tuple[tuple[str, str], ...] = (), attack_bonus: int | None = None
) -> CombatActionOptionView:
    """The weapon attack as a power, so its hover card reads like the abilities'."""

    names = ", ".join(name for name, _damage in weapons) or "Unarmed strike"
    stats = [("Type", "Weapon attack"), ("Weapon", names)]
    stats += [("Damage", damage if len(weapons) == 1 else f"{name}: {damage}") for name, damage in weapons]
    if attack_bonus is not None:
        stats.append(("Attack bonus", f"{attack_bonus:+d}"))
    stats += [("Cost", "None"), ("Target", "One enemy"), ("Uses", "Unlimited")]
    return CombatActionOptionView(
        key=ATTACK_KEY, name="Weapon Attack", kind="attack",
        description="Strike the selected enemy with your equipped weapon.",
        resource_label="No cost", available=True, stats=tuple(stats), status_label="Ready",
    )


def hotbar_actions(
    abilities: tuple[CombatActionOptionView, ...],
    spells: tuple[CombatActionOptionView, ...],
    attack: CombatActionOptionView | None = None,
) -> tuple[HotbarAction, ...]:
    """Everything a slot can hold: the weapon attack, then abilities, then spells."""

    attack = HotbarAction(
        ATTACK_KEY, "Weapon Attack", "Attack", skill_icon_path("Attack"),
        option=attack or weapon_attack_option(),
    )
    return (
        attack,
        *(HotbarAction(a.key, a.name, "Abilities", action_icon_path(a.key), a.available, a) for a in abilities),
        *(HotbarAction(s.key, s.name, "Spells", action_icon_path(s.key), s.available, s) for s in spells),
    )


def default_slots(actions: tuple[HotbarAction, ...]) -> list[str | None]:
    """First run: the attack, then each power in order, the rest empty."""

    keys: list[str | None] = [action.key for action in actions[:HOTBAR_SLOTS]]
    return keys + [None] * (HOTBAR_SLOTS - len(keys))


class HotbarSlot(QFrame):
    activated = Signal(int)
    assign_requested = Signal(int, object)  # slot index, catalog key or None to clear

    def __init__(self, index: int) -> None:
        super().__init__()
        self.index = index
        self.action: HotbarAction | None = None
        self.choices: tuple[HotbarAction, ...] = ()
        self.hover_card: AbilityHoverCard | None = None
        self._closing = False
        self.setObjectName("hotbarSlot")
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        self.icon_label = QLabel()
        self.icon_label.setObjectName("hotbarSlotIcon")
        self.icon_label.setFixedSize(SLOT_ICON_SIZE, SLOT_ICON_SIZE)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label, 0, Qt.AlignmentFlag.AlignCenter)
        self.key_label = QLabel(HOTBAR_KEYS[index], self)
        self.key_label.setObjectName("hotbarSlotKey")
        self.key_label.move(4, 2)
        self.set_action(None)

    def set_action(self, action: HotbarAction | None) -> None:
        self.action = action
        self.setProperty("empty", action is None)
        self.setProperty("available", action is not None and action.available)
        self.icon_label.setPixmap(
            QIcon(str(action.icon)).pixmap(SLOT_ICON_SIZE - 4, SLOT_ICON_SIZE - 4) if action else QIcon().pixmap(1, 1)
        )
        self.icon_label.setEnabled(action is not None and action.available)
        name = action.name if action else "Empty"
        # a filled slot shows the power's full hover card instead (enterEvent)
        self.setToolTip("" if action else f"{HOTBAR_KEYS[self.index]}: empty (right-click to assign)")
        self.setAccessibleName(f"Hotbar slot {HOTBAR_KEYS[self.index]}: {name}")
        self.style().unpolish(self)
        self.style().polish(self)

    def _close_hover_card(self) -> None:
        card, self.hover_card = self.hover_card, None
        if card is not None:
            # closing can synthesise an Enter on this slot; ignore it, or enter and
            # close ping-pong
            self._closing = True
            card.close()
            card.deleteLater()
            self._closing = False

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        showing = self.hover_card is not None and self.hover_card.isVisible()
        if self.action is not None and self.action.option is not None and not showing and not self._closing:
            self.hover_card = AbilityHoverCard(self.action.option, self)
            self.hover_card.show_near(QCursor.pos())
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._close_hover_card()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self._close_hover_card()
        if event.button() == Qt.MouseButton.LeftButton and self.action is not None:
            self.activated.emit(self.index)
        super().mousePressEvent(event)

    def build_menu(self) -> QMenu:
        menu = QMenu(self)
        menu.setObjectName("hotbarSlotMenu")
        groups: dict[str, QMenu] = {}
        for choice in self.choices:
            if choice.group == "Attack":
                target = menu
            else:
                target = groups.get(choice.group) or groups.setdefault(choice.group, menu.addMenu(choice.group))
            action = target.addAction(QIcon(str(choice.icon)), choice.name)
            action.triggered.connect(lambda _c=False, key=choice.key: self.assign_requested.emit(self.index, key))
        if self.action is not None:
            menu.addSeparator()
            menu.addAction("Clear slot").triggered.connect(
                lambda: self.assign_requested.emit(self.index, None)
            )
        return menu

    def contextMenuEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.build_menu().exec(event.globalPos())


class Hotbar(QFrame):
    """One row of ten slots across the codex column."""

    slot_used = Signal(str)  # catalog key, or ATTACK_KEY
    slots_changed = Signal(list)  # the ten keys (None for empty), to persist

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("hotbar")
        self.setAccessibleName("Quick access hotbar")
        self.keys: list[str | None] = [None] * HOTBAR_SLOTS
        self.actions: dict[str, HotbarAction] = {}
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self.slots = [HotbarSlot(index) for index in range(HOTBAR_SLOTS)]
        for slot in self.slots:
            slot.activated.connect(self.use_slot)
            slot.assign_requested.connect(self.assign)
            layout.addWidget(slot, 1)

    def set_actions(self, actions: tuple[HotbarAction, ...], keys: list[str | None] | None = None) -> None:
        """The character's current choices; ``keys`` restores saved slots."""

        self.actions = {action.key: action for action in actions}
        if keys is not None:
            self.keys = (list(keys) + [None] * HOTBAR_SLOTS)[:HOTBAR_SLOTS]
        for slot, key in zip(self.slots, self.keys):
            slot.choices = actions
            # a saved power this character lacks shows empty but keeps its place
            slot.set_action(self.actions.get(key) if key else None)

    def assign(self, index: int, key: str | None) -> None:
        if key is not None and key in self.keys:  # one slot per action: move it here
            self.keys[self.keys.index(key)] = None
        self.keys[index] = key
        self.set_actions(tuple(self.actions.values()))
        self.slots_changed.emit(list(self.keys))

    def use_slot(self, index: int) -> None:
        action = self.slots[index].action
        if action is not None:
            self.slot_used.emit(action.key)

    def use_key(self, key_text: str) -> bool:
        """A number key from the window; True when it named a slot."""

        if key_text in HOTBAR_KEYS:
            self.use_slot(HOTBAR_KEYS.index(key_text))
            return True
        return False
