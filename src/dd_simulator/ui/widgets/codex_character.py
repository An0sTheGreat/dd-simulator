"""Concept T left-column widgets: character strip, paperdoll and skill details."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.ui.models.presentation import (
    DashboardView,
    EquipmentSlotView,
    PlayerSummaryView,
    ResourceView,
    SkillView,
)
from dd_simulator.ui.power_icons import skill_icon_path
from dd_simulator.ui.widgets.inventory_grid import EquipmentGrid
from dd_simulator.ui.widgets.resource_bar import ResourceBar
from dd_simulator.ui.widgets.hover_card import HoverCardHost
from dd_simulator.ui.widgets.skills_grid import SkillHoverCard


def _label(text: str, object_name: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


def _amount(resource: ResourceView) -> str:
    return f"{resource.current:,} / {resource.maximum:,}"


class CharacterStrip(QFrame):
    """Name, class and campaign, purse and carry, and five slim resource bars."""

    def __init__(self, dashboard: DashboardView) -> None:
        super().__init__()
        self.setObjectName("characterStrip")
        player = dashboard.player
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        identity = QVBoxLayout()
        identity.setSpacing(0)
        self.name_label = _label(player.name, "characterStripName")
        line = f"Level {player.level} {player.character_class}"
        if dashboard.campaign_name.strip():
            line += f" · {dashboard.campaign_name.strip()}"
        self.class_label = _label(line.upper(), "characterStripClass")
        identity.addWidget(self.name_label)
        identity.addWidget(self.class_label)
        top.addLayout(identity, 1)
        purse = QVBoxLayout()
        purse.setSpacing(0)
        self.purse_label = _label(f"{player.currency:,} gold", "characterStripPurse")
        self.purse_label.setAccessibleName(f"{player.currency:,} gold")
        self.carry_label = _label(
            f"Carry {player.carry_weight} / {player.carry_capacity}", "characterStripCarry"
        )
        for label in (self.purse_label, self.carry_label):
            label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            purse.addWidget(label)
        top.addLayout(purse)

        bars = QHBoxLayout()
        bars.setContentsMargins(0, 0, 0, 0)
        bars.setSpacing(10)
        self.bars: list[ResourceBar] = []
        for resource in (*dashboard.sidebar_resources[:4], player.experience):
            cell = QGridLayout()
            cell.setContentsMargins(0, 0, 0, 0)
            cell.setVerticalSpacing(2)
            cell.addWidget(_label(resource.name, "codexResourceName"), 0, 0)
            value = _label(_amount(resource), "codexResourceValue")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            cell.addWidget(value, 0, 1)
            bar = ResourceBar(resource)
            bar.setObjectName("codexResourceBar")
            bar.setTextVisible(False)
            bar.setAccessibleName(f"{resource.name} {_amount(resource)}")
            cell.addWidget(bar, 1, 0, 1, 2)
            bars.addLayout(cell, 1)
            self.bars.append(bar)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addLayout(top)
        layout.addLayout(bars)


# Mockup geometry (concept-t-classic-messages.html): slot origins, portrait box and size.
PAPERDOLL_WIDTH, PAPERDOLL_HEIGHT = 330, 318
PAPERDOLL_SLOT_SIZE = 58
PAPERDOLL_ICON_SIZE = 34
PORTRAIT_GEOMETRY = (76, 76, 168, 228)
PORTRAIT_FRAME = 12
# name, caption, (x, y), (column, row) for keyboard navigation
PAPERDOLL_LAYOUT = (
    ("Ring", "Ring", (4, 4), (0, 0)),
    ("Head", "Head", (131, 4), (1, 0)),
    ("Neck", "Neck", (258, 4), (2, 0)),
    ("Main Hand", "Main hand", (4, 84), (0, 1)),
    ("Body", "Body", (4, 162), (0, 2)),
    ("Hands", "Hands", (4, 240), (0, 3)),
    ("Off Hand", "Off hand", (258, 84), (2, 1)),
    ("Ammunition", "Ammo", (258, 162), (2, 2)),
    ("Feet", "Feet", (258, 240), (2, 3)),
)
PAPERDOLL_SLOT_NAMES = tuple(entry[0] for entry in PAPERDOLL_LAYOUT)


class PaperdollPanel(EquipmentGrid):
    """Nine equipment slots around the portrait.

    An ``EquipmentGrid`` so selection, context actions, inventory drops and the main
    window's ``findChildren(EquipmentGrid)`` wiring work unchanged; only placement and
    keyboard navigation differ.
    """

    def __init__(
        self,
        player: PlayerSummaryView,
        slots: tuple[EquipmentSlotView, ...],
        *,
        attack_bonus: int | None = None,
    ) -> None:
        super().__init__(
            slots,
            columns=3,
            slot_names=PAPERDOLL_SLOT_NAMES,
            slot_size=PAPERDOLL_SLOT_SIZE,
        )
        self.setObjectName("paperdollPanel")
        self.setFixedSize(PAPERDOLL_WIDTH, PAPERDOLL_HEIGHT)
        self.portrait = QLabel(self)
        self.portrait.setObjectName("paperdollPortrait")
        self.portrait.setGeometry(*PORTRAIT_GEOMETRY)
        self.portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.portrait.lower()
        stats = [f"AC {player.armor_class}"]
        if attack_bonus is not None:
            stats.append(f"ATK {attack_bonus:+d}")
        stats.append(f"PROF +{player.proficiency_bonus}")
        inner = PORTRAIT_GEOMETRY[2] - 2 * PORTRAIT_FRAME
        inner_height = PORTRAIT_GEOMETRY[3] - 2 * PORTRAIT_FRAME
        self.stats_label = QLabel(" · ".join(stats), self.portrait)
        self.stats_label.setObjectName("paperdollStats")
        self.stats_label.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom
        )
        shade = round(inner_height * 0.4)
        self.stats_label.setGeometry(
            PORTRAIT_FRAME, PORTRAIT_FRAME + inner_height - shade, inner, shade
        )
        self.set_portrait(player)

    def set_portrait(self, player: PlayerSummaryView) -> None:
        width = PORTRAIT_GEOMETRY[2] - 2 * PORTRAIT_FRAME
        height = PORTRAIT_GEOMETRY[3] - 2 * PORTRAIT_FRAME
        source = QPixmap(player.portrait_path) if player.portrait_path else QPixmap()
        has_portrait = not source.isNull()
        self.portrait.setProperty("hasPortrait", has_portrait)
        if has_portrait:
            scaled = source.scaled(
                width,
                height,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            # Same crop as the mockup's "center 18% / cover".
            self.portrait.setPixmap(
                scaled.copy(
                    (scaled.width() - width) // 2,
                    round((scaled.height() - height) * 0.18),
                    width,
                    height,
                )
            )
            self.portrait.setAccessibleName(f"Portrait of {player.name}")
        else:
            self.portrait.setText(player.portrait_initials)
            self.portrait.setAccessibleName(f"Portrait placeholder for {player.name}")
        self.portrait.style().unpolish(self.portrait)
        self.portrait.style().polish(self.portrait)

    def set_slots(self, slots: tuple[EquipmentSlotView, ...]) -> None:
        super().set_slots(slots)
        # EquipmentGrid.__init__ calls this before our __init__ body runs.
        for caption in getattr(self, "captions", ()):
            caption.deleteLater()
        self.captions: list[QLabel] = []
        placement = {name.casefold(): (text, pos) for name, text, pos, _cell in PAPERDOLL_LAYOUT}
        for widget in self.slots:
            self.grid.removeWidget(widget)
            text, (x, y) = placement[widget.slot.slot_name.casefold()]
            widget.move(x, y)
            # Codex art comes from the theme's frame, not the legacy well artwork.
            widget.artwork_label.hide()
            widget.occupied_artwork_label.hide()
            widget.icon_label.setFixedSize(PAPERDOLL_ICON_SIZE, PAPERDOLL_ICON_SIZE)
            widget.refresh_theme_icon()
            caption = QLabel(text.upper(), self)
            caption.setObjectName("paperdollSlotCaption")
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            caption.setGeometry(x - 12, y + PAPERDOLL_SLOT_SIZE, PAPERDOLL_SLOT_SIZE + 24, 14)
            caption.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            self.captions.append(caption)
        if self.slots:
            self.setFixedSize(PAPERDOLL_WIDTH, PAPERDOLL_HEIGHT)

    def _move_focus(self, index: int, direction: str) -> None:
        cells = {name.casefold(): cell for name, _text, _pos, cell in PAPERDOLL_LAYOUT}
        source = self.slots_by_index.get(index)
        if source is None:
            return
        column, row = cells[source.slot.slot_name.casefold()]
        dx, dy = {"left": (-1, 0), "right": (1, 0), "up": (0, -1), "down": (0, 1)}[direction]
        candidates = []
        for slot in self.slots:
            c, r = cells[slot.slot.slot_name.casefold()]
            ahead = (c - column) * dx + (r - row) * dy
            if slot is source or slot.slot.item_name is None or ahead <= 0:
                continue
            candidates.append((ahead, abs(c - column) + abs(r - row), slot))
        if candidates:
            min(candidates, key=lambda value: value[:2])[2].setFocus()


class SkillDetailRow(HoverCardHost, QFrame):
    def __init__(self, skill: SkillView) -> None:
        super().__init__()
        self.skill = skill
        self.setObjectName("skillDetailRow")
        self.setProperty("locked", skill.locked)
        self.setProperty("recentlyIncreased", skill.recently_increased)
        self.setAccessibleName(f"{skill.name}, level {skill.level}")
        self.icon_label = QLabel()
        self.icon_label.setObjectName("skillDetailIcon")
        self.icon_label.setFixedSize(30, 30)
        self.icon_label.setPixmap(
            QPixmap(str(skill_icon_path(skill.name))).scaled(
                28,
                28,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.name_label = _label(skill.name, "skillDetailName")
        self.value_label = _label(str(skill.level), "skillDetailValue")
        self.description_label = _label(skill.description, "skillDetailDescription")
        self.xp_bar = QProgressBar()
        self.xp_bar.setObjectName("skillDetailXpBar")
        self.xp_bar.setTextVisible(False)
        self.xp_bar.setRange(0, max(1, skill.next_level_xp))
        self.xp_bar.setValue(min(skill.current_xp, self.xp_bar.maximum()))
        self.xp_bar.setFixedHeight(3)
        self.xp_bar.setAccessibleName(
            f"{skill.name} experience {skill.current_xp} of {skill.next_level_xp}"
        )

        heading = QHBoxLayout()
        heading.setContentsMargins(0, 0, 0, 0)
        heading.addWidget(self.name_label, 1)
        heading.addWidget(self.value_label)
        details = QVBoxLayout()
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(0)
        details.addLayout(heading)
        details.addWidget(self.description_label)
        details.addSpacing(2)
        details.addWidget(self.xp_bar)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        layout.addWidget(self.icon_label)
        layout.addLayout(details, 1)

    def build_hover_card(self) -> SkillHoverCard:
        return SkillHoverCard(self.skill, self)


class SkillDetailList(QWidget):
    """One row per skill: icon, name, value, one-line description and XP bar."""

    def __init__(self, skills: tuple[SkillView, ...]) -> None:
        super().__init__()
        self.setObjectName("skillDetailList")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        self.rows = [SkillDetailRow(skill) for skill in skills]
        for row in self.rows:
            layout.addWidget(row)
        layout.addStretch(1)
