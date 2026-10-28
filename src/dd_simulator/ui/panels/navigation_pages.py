"""Focused in-application pages opened by bottom navigation."""

from PySide6.QtCore import QEvent, QRect, Qt, Signal
from PySide6.QtGui import Qt as GuiQt, QCursor
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStyle,
    QStyleOptionButton,
    QStylePainter,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.ui.models.presentation import (
    CommerceItemView, ConversationView, DashboardView, EquipmentSlotView,
    InventorySlotView, NarrativeMessageView,
)
from dd_simulator.ui.item_icons import item_icon_label
from dd_simulator.ui.panels.activity_panels import EventLogPanel, RecentEventsPanel
from dd_simulator.ui.panels.common import semantic_label
from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.themed_frame import ThemedFrame
from dd_simulator.state.progression import saving_throw_proficiencies
from dd_simulator.ui.widgets.inventory_grid import ItemHoverCard, equipped_comparisons
from dd_simulator.ui.widgets.codex_cards import PowerEntry, _heading, codex_card, icon_row, plain_label
from dd_simulator.ui.widgets.codex_character import SkillDetailRow
from dd_simulator.ui.widgets.conversation_view import ConversationView as ConversationThread
from dd_simulator.ui.widgets.quest_list import QuestListWidget
from dd_simulator.ui.widgets.world_map import WorldMapPanel


class NavigationPage(ThemedFrame):
    back_requested = Signal()

    def __init__(
        self, object_name: str, title: str, description: str, *, back: QPushButton | None = None
    ) -> None:
        super().__init__(object_name, role="content")
        self.setAccessibleName(title)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 12, 14, 12)
        self.layout.setSpacing(8)
        if back is None:  # Settings brings its own back button and signal
            back = SemanticButton("Return to Adventure", role="secondary")
            back.setObjectName("navigationBackButton")
            back.clicked.connect(self.back_requested)
        self.back_button = back
        self.action_bar = page_action_bar(back)
        header = QHBoxLayout()
        header.addWidget(
            semantic_label(title, object_name="navigationPageTitle", text_role="heading"), 1
        )
        header.addWidget(self.action_bar)
        self.layout.addLayout(header)
        self.layout.addWidget(
            semantic_label(
                description, object_name="navigationPageSubtitle", text_role="secondary",
                word_wrap=True,
            )
        )


def page_action_bar(*buttons: QPushButton) -> QWidget:
    """One compact row of page actions, each button sized to its text."""

    bar = QWidget()
    bar.setObjectName("pageActionBar")
    # A fixed-size bar holds every button, including ones inserted later, at its text width.
    bar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    row = QHBoxLayout(bar)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    for button in buttons:
        row.addWidget(button)
    return bar


def _stack(*cards: QWidget) -> QVBoxLayout:
    """One sheet column; its last card takes the spare height so columns end level."""

    column = QVBoxLayout()
    column.setSpacing(8)
    for card in cards:
        column.addWidget(card)
    column.setStretch(len(cards) - 1, 1)
    return column


def _field(layout: QGridLayout, row: int, column: int, label: str, value: str, value_name: str) -> None:
    layout.addWidget(plain_label(label.upper(), "pageCardLabel"), row, column)
    # Vitals stay on one line so each column keeps its value's full width.
    wrap = value_name != "characterSheetVitalValue"
    layout.addWidget(plain_label(value, value_name, word_wrap=wrap), row + 1, column)
    layout.setColumnStretch(column, 1)


def _lines(layout: QVBoxLayout, rows: tuple[tuple[str, str], ...]) -> None:
    """Two-column label/value grid, each label beside its value."""

    grid = QGridLayout()
    grid.setHorizontalSpacing(12)
    grid.setVerticalSpacing(3)
    for row, (label, value) in enumerate(rows):
        name = plain_label(label.upper(), "pageCardLabel")
        grid.addWidget(name, row, 0, Qt.AlignmentFlag.AlignTop)
        grid.addWidget(plain_label(value, "pageCardValue", word_wrap=True), row, 1)
    grid.setColumnStretch(1, 1)
    layout.addLayout(grid)


def _two_columns(layout: QVBoxLayout, widgets: list[QWidget]) -> None:
    """Lay widgets out row by row in two equal columns."""

    grid = QGridLayout()
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(5)
    for index, widget in enumerate(widgets):
        grid.addWidget(widget, index // 2, index % 2)
    grid.setColumnStretch(0, 1)
    grid.setColumnStretch(1, 1)
    layout.addLayout(grid)


class CharacterSheetPage(NavigationPage):
    """Original, read-only 5E-inspired view of authoritative campaign state."""

    crafting_requested = Signal()

    def __init__(self, dashboard: DashboardView) -> None:
        super().__init__(
            "characterSheetNavigationPage",
            "CHARACTER SHEET",
            "A themed summary of the current character and their adventuring capabilities.",
        )
        player = dashboard.player
        scroll = QScrollArea()
        scroll.setObjectName("characterSheetScroll")
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        viewport = QWidget()
        viewport.setObjectName("characterSheetViewport")
        viewport_layout = QVBoxLayout(viewport)
        viewport_layout.setContentsMargins(0, 2, 0, 2)

        sheet = QWidget()
        sheet.setObjectName("characterSheetSurface")
        sheet.setAccessibleName(f"Character sheet for {player.name}")
        grid = QGridLayout(sheet)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(8)

        identity, identity_layout = codex_card("Identity", "characterSheetIdentity")
        identity_grid = QGridLayout()
        identity_grid.setHorizontalSpacing(14)
        identity_grid.setVerticalSpacing(1)
        for column, (label, value) in enumerate((
            ("Character", player.name),
            ("Ancestry", player.species or "Unknown"),
            ("Class", player.character_class),
            ("Level", str(player.level)),
            ("Background", player.background or "Unrecorded"),
        )):
            _field(identity_grid, 0, column, label, value, "characterSheetIdentityValue")
        identity_layout.addLayout(identity_grid)

        attributes, attributes_layout = codex_card("Ability Scores", "characterSheetAttributes")
        tiles = QHBoxLayout()
        tiles.setSpacing(5)
        for attribute in player.attributes[:6]:
            tile = ThemedFrame("characterSheetAttribute", role="section")
            tile_layout = QVBoxLayout(tile)
            tile_layout.setContentsMargins(2, 1, 2, 1)
            tile_layout.setSpacing(0)
            for text, name in (
                (attribute.name.upper(), "pageCardLabel"),
                (str(attribute.value), "characterSheetAttributeValue"),
                (f"{attribute.modifier:+d}", "characterSheetModifier"),
            ):
                label = plain_label(text, name)
                label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                tile_layout.addWidget(label)
            tiles.addWidget(tile, 1)
        attributes_layout.addLayout(tiles)
        grid.addLayout(_stack(identity, attributes), 0, 0, 1, 2)

        vitals, vitals_layout = codex_card("Combat Summary", "characterSheetSection")
        health = next(
            (resource for resource in player.resources if resource.resource_type == "health"),
            None,
        )
        # Each value in its own equal-stretch column under its label, with a real gutter:
        # at the default 2 px spacing the five values ran together.
        vitals_grid = QGridLayout()
        vitals_grid.setHorizontalSpacing(10)
        vitals_grid.setVerticalSpacing(0)
        for column, (label, value) in enumerate((
            ("Hit Points", f"{health.current} / {health.maximum}" if health else "—"),
            ("Armor", str(player.armor_class)),
            ("Initiative", f"{player.initiative_modifier:+d}"),
            ("Speed", f"{player.movement_feet} ft"),
            ("Proficiency", f"+{player.proficiency_bonus}"),
        )):
            _field(vitals_grid, 0, column, label, value, "characterSheetVitalValue")
        vitals_layout.addLayout(vitals_grid)
        if player.pending_ability_points:
            vitals_layout.addWidget(plain_label(
                f"LEVEL-UP CHOICE PENDING: {player.pending_ability_points} ability-score points",
                "pageCardNotice",
                word_wrap=True,
            ))

        saves, saves_layout = codex_card("Saving Throws", "characterSheetSection")
        proficient_saves = saving_throw_proficiencies(player.character_class)
        saves_grid = QGridLayout()
        saves_grid.setHorizontalSpacing(14)
        saves_grid.setVerticalSpacing(1)
        for index, attribute in enumerate(player.attributes[:6]):
            proficient = attribute.name.casefold() in proficient_saves
            bonus = attribute.modifier + (player.proficiency_bonus if proficient else 0)
            name = plain_label(attribute.name, "pageCardValue")
            value = plain_label(
                f"{bonus:+d}{' (proficient)' if proficient else ''}", "pageCardStat"
            )
            value.setProperty("proficient", proficient)
            saves_grid.addWidget(name, index % 3, (index // 3) * 2)
            saves_grid.addWidget(value, index % 3, (index // 3) * 2 + 1)
        saves_layout.addLayout(saves_grid)

        appearance, appearance_layout = codex_card("Appearance & Biography", "characterSheetSection")
        _lines(appearance_layout, (
            ("Age", str(player.age) if player.age else "Unrecorded"),
            ("Gender", player.gender_identity or "Unrecorded"),
            ("Pronouns", player.pronouns or "Unrecorded"),
            ("Body", player.body_description or "Unrecorded"),
            ("Face", player.face_description or "Unrecorded"),
            ("Clothing", player.clothing_style or "Unrecorded"),
            ("Biography/Backstory", player.biography or player.backstory or "Unrecorded"),
        ))

        weapons = tuple(
            slot.item for slot in dashboard.equipment if slot.item is not None and slot.item.damage
        )
        attacks, attacks_layout = codex_card("Weapon Attacks", "characterSheetSection", count=len(weapons))
        for weapon in weapons:
            attacks_layout.addWidget(icon_row(
                item_icon_label(str(weapon.name), rarity=weapon.rarity, category=weapon.item_type, size=30),
                str(weapon.name), weapon.damage, rarity=weapon.rarity,
            ))
        if not weapons:
            attacks_layout.addWidget(plain_label("No damaging weapon equipped.", "pageCardMeta"))

        # The second section of the Equipment card, beneath the worn items.
        powers = QWidget()
        powers.setObjectName("characterSheetPowers")
        powers.setAccessibleName("Abilities & Spells")
        powers_layout = QVBoxLayout(powers)
        powers_layout.setContentsMargins(0, 8, 0, 0)
        powers_layout.setSpacing(5)
        powers_layout.addWidget(_heading("Abilities & Spells", len(dashboard.combat_skills)))
        _two_columns(powers_layout, [
            PowerEntry(action, detail=next(
                (value for key, value in action.stats if key == "Effect"), ""
            ) or None)
            for action in dashboard.combat_skills
        ])
        if not dashboard.combat_skills:
            powers_layout.addWidget(plain_label("No abilities unlocked.", "pageCardMeta"))

        role, role_layout = codex_card("Role & Character", "characterSheetSection")
        _lines(role_layout, (
            ("Personality", ", ".join(player.personalities) or "Unrecorded"),
            ("Strength", player.primary_strength or "Unrecorded"),
            ("Flaw", player.meaningful_flaw or "Unrecorded"),
            ("Motivation", player.motivation or "Unrecorded"),
        ))

        equipped = tuple(slot for slot in dashboard.equipment if slot.item_name)
        equipment, equipment_layout = codex_card("Equipment", "characterSheetSection", count=len(equipped))
        worn = []
        for slot in equipped:
            rarity = slot.item.rarity if slot.item else "common"
            category = slot.item.item_type if slot.item else "misc"
            worn.append(icon_row(
                item_icon_label(str(slot.item_name), rarity=rarity, category=category, context=slot.slot_name, size=30),
                str(slot.item_name), slot.slot_name, rarity=rarity,
            ))
        _two_columns(equipment_layout, worn)
        if not equipped:
            equipment_layout.addWidget(plain_label("No equipment worn.", "pageCardMeta"))
        equipment_layout.addWidget(powers)

        carried = tuple(item for item in dashboard.inventory_preview if not item.is_empty)
        possessions, possessions_layout = codex_card(
            "Possessions & Currency", "characterSheetSection", count=len(carried)
        )
        possessions_layout.addWidget(plain_label(f"{player.currency:,} gold", "pageCardPurse"))
        names = [
            f"{item.name} ×{item.quantity}" if item.quantity > 1 else str(item.name)
            for item in carried
        ]
        possessions_layout.addWidget(
            plain_label(", ".join(names) if names else "No carried items.", "pageCardValue", word_wrap=True)
        )

        skills, skills_layout = codex_card("Skills", "characterSheetSection", count=len(dashboard.skills))
        for skill in dashboard.skills:
            row = SkillDetailRow(skill)
            # The sheet shows the total with bonuses, as it always has.
            row.value_label.setText(f"{skill.level + skill.bonus:+d}")
            skills_layout.addWidget(row)

        # The right half runs top to bottom on its own, so its columns are not held to
        # the height of the Identity and Ability Scores stack on the left.
        for column, cards in enumerate((
            (saves, appearance),
            (role, possessions),
        )):
            grid.addLayout(_stack(*cards), 1, column)
            grid.setColumnStretch(column, 1)
        for column, cards in ((2, (vitals, skills)), (3, (attacks, equipment))):
            grid.addLayout(_stack(*cards), 0, column, 2, 1)
            grid.setColumnStretch(column, 1)
        grid.setRowStretch(1, 1)

        viewport_layout.addWidget(sheet, 1)
        scroll.setWidget(viewport)
        self.layout.addWidget(scroll, 1)
        crafting = SemanticButton("Crafting", role="secondary")
        crafting.setObjectName("characterSheetCraftingButton")
        crafting.setAccessibleName("Open crafting")
        crafting.setToolTip("Craft items from known recipes")
        crafting.clicked.connect(self.crafting_requested)
        # Return to Adventure keeps the right edge on every page.
        self.action_bar.layout().insertWidget(0, crafting)


def centered_third(content: QWidget, object_name: str = "centeredThird", *, share: int = 1) -> QWidget:
    """Center a responsive control block at one third page width (``share=2``: one half)."""

    host = QWidget()
    host.setObjectName(object_name)
    layout = QGridLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    content.setMinimumWidth(0)
    content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    layout.addWidget(content, 0, 1)
    for column in range(3):
        layout.setColumnStretch(column, share if column == 1 else 1)
    return host


def _wrapper(content: QWidget, object_name: str) -> QWidget:
    host = QWidget()
    host.setObjectName(object_name)
    layout = QVBoxLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(content)
    return host


class WrappingButton(SemanticButton):
    """Button whose text wraps onto more lines instead of clipping at both ends."""

    def __init__(self, text: str, *, role: str, object_name: str) -> None:
        super().__init__(text, role=role, object_name=object_name)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def _text_width(self, width: int) -> int:
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.rect = QRect(0, 0, width, self.height())
        return self.style().subElementRect(QStyle.SubElement.SE_PushButtonContents, option, self).width()

    def _wrapped(self, width: int) -> str:
        metrics = self.fontMetrics()
        lines: list[str] = []
        for word in self.text().split():
            if lines and metrics.horizontalAdvance(f"{lines[-1]} {word}") <= width:
                lines[-1] += f" {word}"
            else:
                lines.append(word)
        return "\n".join(lines)

    def minimumSizeHint(self):  # type: ignore[no-untyped-def]  # noqa: N802
        hint = super().sizeHint()
        metrics = self.fontMetrics()
        longest = max((metrics.horizontalAdvance(word) for word in self.text().split()), default=0)
        hint.setWidth(hint.width() - metrics.horizontalAdvance(self.text()) + longest)
        return hint

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        lines = self._wrapped(self._text_width(width)).count("\n")
        return super().sizeHint().height() + lines * self.fontMetrics().lineSpacing()

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        option = QStyleOptionButton()
        self.initStyleOption(option)
        option.text = self._wrapped(self._text_width(self.width()))
        QStylePainter(self).drawControl(QStyle.ControlElement.CE_PushButton, option)


def _commerce_tooltip(item: CommerceItemView) -> str:
    details = [
        item.name,
        f"{item.rarity.title()} | Quantity: {item.quantity}",
    ]
    if item.durability is not None:
        details.append(f"Durability: {item.durability}/{item.maximum_durability or '?'}")
    if item.damage:
        details.append(f"Damage: {item.damage}")
    if item.healing:
        details.append(f"Healing: {item.healing} health")
    if item.description:
        details.append(item.description)
    return "\n".join(details)


def _commerce_inventory_view(item: CommerceItemView) -> InventorySlotView:
    return InventorySlotView(
        name=item.name, id=item.id, quantity=item.quantity, rarity=item.rarity,
        durability=item.durability, maximum_durability=item.maximum_durability,
        description=item.description, damage=item.damage, healing=item.healing,
        category=item.category, item_type=item.item_type, equip_slot=item.equip_slot,
        compatible_slots=item.compatible_slots, weight=item.weight,
        value_gp=item.value_gp, identified=item.identified,
    )


class CommerceHoverEntry(QWidget):
    """Trade entry using the same persistent card and comparisons as inventory."""

    def __init__(
        self, item: CommerceItemView, text: str,
        equipment: tuple[EquipmentSlotView, ...],
    ) -> None:
        super().__init__()
        self.item = _commerce_inventory_view(item)
        self.default_comparison, self.offhand_comparison = equipped_comparisons(
            self.item, equipment,
        )
        self.hover_card: ItemHoverCard | None = None
        self.comparison_card: ItemHoverCard | None = None
        self.using_offhand = False
        self.setMouseTracking(True)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        row.addWidget(item_icon_label(
            item.name, rarity=item.rarity,
            context=f"{item.description} {item.damage} healing {item.healing}",
            size=28, object_name="commerceItemIcon",
        ))
        label = semantic_label(text, text_role="body", word_wrap=True)
        label.setProperty("rarity", item.rarity.casefold())
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        row.addWidget(label, 1)

    def enterEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        hint = "Hold Left Ctrl: Compare Off Hand" if self.offhand_comparison else ""
        self.hover_card = ItemHoverCard(
            self.item, self, comparison_hint=hint, compared_with=self.default_comparison,
        )
        self.hover_card.show_near(QCursor.pos())
        self._show_comparison(False)
        app = QApplication.instance()
        if app is not None and self.offhand_comparison is not None:
            app.installEventFilter(self)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        for card in (self.hover_card, self.comparison_card):
            if card is not None:
                card.close()
                card.deleteLater()
        self.hover_card = None
        self.comparison_card = None
        super().leaveEvent(event)

    def _show_comparison(self, offhand: bool) -> None:
        item = self.offhand_comparison if offhand else self.default_comparison
        if item is None or self.hover_card is None:
            return
        if self.comparison_card is not None:
            self.comparison_card.close()
            self.comparison_card.deleteLater()
        self.using_offhand = offhand
        self.comparison_card = ItemHoverCard(item, self, equipped_comparison=True)
        self.comparison_card.show_beside(self.hover_card)

    def eventFilter(self, watched, event) -> bool:  # type: ignore[no-untyped-def]
        if self.offhand_comparison is not None and event.type() in {
            QEvent.Type.KeyPress, QEvent.Type.KeyRelease,
        } and event.key() == Qt.Key.Key_Control:
            offhand = event.type() == QEvent.Type.KeyPress
            if offhand != self.using_offhand:
                self._show_comparison(offhand)
        return super().eventFilter(watched, event)


def _commerce_entry(
    item: CommerceItemView, text: str, equipment: tuple[EquipmentSlotView, ...],
) -> QWidget:
    return CommerceHoverEntry(item, text, equipment)


class NpcNavigationPage(NavigationPage):
    dialogue_requested = Signal(str, str)
    trade_requested = Signal(str, str, str)

    def __init__(self, conversations: tuple[ConversationView, ...]) -> None:
        super().__init__(
            "npcsNavigationPage", "PEOPLE AT THIS LOCATION",
            "Choose someone to speak with. Suggested responses submit immediately; written responses use Send.",
        )
        self.conversations = conversations
        self.selected_id = conversations[0].npc.id if conversations else ""
        # One full-height row, left to right: Conversation (Your reply beneath it) |
        # Trade | People above Speaking with. The splitter divides Conversation and Trade.
        self.people_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.people_splitter.setObjectName("peopleTradeConversationSplitter")
        self.people_splitter.setChildrenCollapsible(False)
        self.trade_host = QWidget()
        self.trade_host.setObjectName("peopleTradeRegion")
        self.trade_layout = QVBoxLayout(self.trade_host)
        self.trade_layout.setContentsMargins(0, 0, 0, 0)
        self.trade_host.setMinimumWidth(240)

        body_host = QWidget()
        body_host.setObjectName("peopleConversationRegion")
        body = QHBoxLayout(body_host)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)
        self.selector_card, selector = codex_card(
            "People", "npcSelectorCard", count=len(conversations)
        )
        self.selection_buttons: dict[str, QPushButton] = {}
        for conversation in conversations:
            npc = conversation.npc
            button = SemanticButton(
                f"{npc.portrait_initials or '?'}  {npc.name}\n{npc.title or npc.status.title()}",
                role="secondary", object_name="npcSelectionButton",
            )
            button.setEnabled(npc.available)
            button.setToolTip(
                f"Disposition: {npc.status.title()}\nRelationship: {npc.relationship_score:+d}"
            )
            button.clicked.connect(
                lambda _checked=False, npc_id=npc.id: self._select_npc(npc_id)
            )
            selector.addWidget(button)
            self.selection_buttons[npc.id] = button
        if not conversations:
            selector.addWidget(plain_label("No known NPCs are present.", "pageCardMeta", word_wrap=True))
        # Cards keep their heading; _render_selected refills the inner hosts.
        self.conversation_card, card = codex_card("Conversation", "npcConversationCard")
        card.setAlignment(Qt.AlignmentFlag(0))  # the thread takes the height
        self.conversation_host = QWidget()
        self.conversation_layout = QVBoxLayout(self.conversation_host)
        self.conversation_layout.setContentsMargins(0, 0, 0, 0)
        card.addWidget(self.conversation_host, 1)
        self.action_host, card = codex_card("Your reply", "npcBottomControls")
        replies = QWidget()
        self.action_layout = QVBoxLayout(replies)
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        card.addWidget(replies)
        self.action_layout.setSpacing(4)
        # Your reply sits under the Conversation card, at its width.
        conversation_column = QWidget()
        column = QVBoxLayout(conversation_column)
        column.setContentsMargins(0, 0, 0, 0)
        column.setSpacing(8)
        column.addWidget(self.conversation_card, 1)
        column.addWidget(_wrapper(self.action_host, "npcCenteredFooter"))
        conversation_column.setMinimumWidth(320)
        self.people_splitter.addWidget(conversation_column)
        self.people_splitter.addWidget(self.trade_host)
        self.people_splitter.setStretchFactor(0, 5)
        self.people_splitter.setStretchFactor(1, 4)
        self.people_splitter.setSizes([500, 400])  # [conversation, trade]
        body.addWidget(self.people_splitter, 1)
        # Speaking with (its own height) above the People list (the rest), one right column.
        side = QVBoxLayout()
        side.setContentsMargins(0, 0, 0, 0)
        side.setSpacing(8)
        self.identity_card, card = codex_card("Speaking with", "npcIdentityCard")
        self.identity_host = QWidget()
        self.identity_layout = QVBoxLayout(self.identity_host)
        self.identity_layout.setContentsMargins(0, 0, 0, 0)
        card.addWidget(self.identity_host)
        side.addWidget(self.identity_card)
        side.addWidget(self.selector_card, 1)
        for column_card in (self.selector_card, self.identity_card):
            column_card.setFixedWidth(260)
        body.addLayout(side)
        self.layout.addWidget(body_host, 1)
        self._render_selected()

    def _select_npc(self, npc_id: str) -> None:
        self.selected_id = npc_id
        self._render_selected()

    def open_npc(self, npc_id: str) -> None:
        if any(value.npc.id == npc_id for value in self.conversations):
            self._select_npc(npc_id)

    def _render_selected(self) -> None:
        self.latest_rows: list[QWidget] = []
        for layout in (
            self.conversation_layout, self.action_layout, self.trade_layout, self.identity_layout,
        ):
            while layout.count():
                widget = layout.takeAt(0).widget()
                if widget is not None:
                    widget.deleteLater()
        for npc_id, button in self.selection_buttons.items():
            button.setProperty("selected", npc_id == self.selected_id)
            button.style().unpolish(button)
            button.style().polish(button)
        conversation = next(
            (value for value in self.conversations if value.npc.id == self.selected_id), None
        )
        if conversation is None:
            self.conversation_layout.addWidget(
                plain_label("Select an available NPC to begin.", "pageCardMeta", word_wrap=True)
            )
            return
        npc = conversation.npc
        identity = QWidget()
        identity_layout = QVBoxLayout(identity)
        identity_layout.setContentsMargins(0, 0, 0, 0)
        identity_layout.setSpacing(8)
        portrait = plain_label(npc.portrait_initials or "?", "conversationPortrait")
        portrait.setProperty("placeholder", True)
        portrait.setFixedSize(56, 56)
        portrait.setAlignment(Qt.AlignmentFlag.AlignCenter)
        portrait.setAccessibleName(f"{npc.name} portrait")
        identity_layout.addWidget(icon_row(portrait, npc.name, npc.title or npc.status.title()))
        _lines(identity_layout, (
            ("Disposition", npc.status.title()),
            ("Relationship", f"{npc.relationship_score:+d}"),
        ))
        self.identity_layout.addWidget(identity)
        self.dialogue_status = semantic_label(
            "",
            object_name="npcDialogueStatus",
            text_role="warning",
            word_wrap=True,
        )
        self.dialogue_status.setVisible(False)
        self.conversation_layout.addWidget(self.dialogue_status)
        if conversation.merchant is not None:
            self.trade_host.setVisible(True)
            self.trade_layout.addWidget(
                _wrapper(self._merchant_panel(conversation), "merchantCenteredContainer")
            )
        else:
            self.trade_host.setVisible(False)
        # The Adventure conversation's bubbles, without its fade into the scene art.
        self.thread = ConversationThread()
        self.thread.setAccessibleName(f"Conversation with {npc.name}")
        self.thread.viewport().setGraphicsEffect(None)
        self.conversation_layout.addWidget(self.thread, 1)
        self.thread.set_messages(
            (
                NarrativeMessageView(
                    message.kind, message.text,
                    speaker_name=npc.name if message.kind == "spoken" else "",
                )
                for message in conversation.messages
            ),
            False,
        )
        latest_player_index = max(
            (index for index, message in enumerate(conversation.messages) if message.kind == "player"),
            default=-1,
        )
        if latest_player_index >= 0:
            self.latest_rows = self.thread.rows[latest_player_index:]
        if not conversation.messages:
            self.conversation_layout.insertWidget(
                0, plain_label("The conversation has not begun.", "pageCardMeta")
            )
        if conversation.last_check:
            self.conversation_layout.addWidget(
                plain_label(conversation.last_check, "pageCardNotice", word_wrap=True)
            )
        choices = QGridLayout()
        choices.setContentsMargins(0, 0, 0, 0)  # the card's padding is enough; 720p needs the height
        for index, response in enumerate(conversation.suggested_responses):
            button = WrappingButton(response, role="secondary", object_name="npcSuggestedResponse")
            button.setEnabled(npc.available)
            button.setToolTip(GuiQt.convertFromPlainText(response))
            button.clicked.connect(
                lambda _checked=False, text=response: self.dialogue_requested.emit(self.selected_id, text)
            )
            choices.addWidget(button, index // 2, index % 2)
        choices_host = QWidget()
        choices_host.setLayout(choices)
        self.action_layout.addWidget(choices_host)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        entry = QLineEdit()
        entry.setObjectName("npcCustomResponseInput")
        entry.setPlaceholderText("Write a response...")
        send = SemanticButton("Send", role="primary", object_name="npcDialogueSendButton")
        send.clicked.connect(lambda: self.dialogue_requested.emit(self.selected_id, entry.text()))
        entry.returnPressed.connect(lambda: self.dialogue_requested.emit(self.selected_id, entry.text()))
        row.addWidget(entry, 1)
        row.addWidget(send)
        row_host = QWidget()
        row_host.setLayout(row)
        self.action_layout.addWidget(row_host)

    def highlight_latest_turn(self, *, reduced_motion: bool) -> None:
        if self.latest_rows:
            # The Adventure conversation's own three-second emphasis on the bubbles.
            self.thread.reduced_motion = reduced_motion
            self.thread._emphasize(self.latest_rows)  # noqa: SLF001

    def _merchant_panel(self, conversation: ConversationView) -> QFrame:
        merchant = conversation.merchant
        assert merchant is not None
        panel, layout = codex_card(
            f"Trade · {merchant.player_currency} gold", "merchantTradePanel"
        )
        layout.setAlignment(Qt.AlignmentFlag(0))  # the stock list takes the height
        scroll = QScrollArea()
        scroll.setObjectName("merchantTradeScroll")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("merchantTradeContent")
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        # One column: the stock list, then the sell list beneath it.
        grid.addWidget(plain_label("MERCHANT STOCK", "pageCardLabel"), 0, 0, 1, 3)
        sell_header = len(merchant.stock) + 1
        grid.addWidget(plain_label("SELL FROM INVENTORY", "pageCardLabel"), sell_header, 0, 1, 3)
        for row_index, item in enumerate(merchant.stock, start=1):
            grid.addWidget(
                _commerce_entry(
                    item,
                    f"{item.name} ×{item.quantity} — {item.buy_price} gp",
                    merchant.equipment,
                ),
                row_index,
                0,
            )
            buy = SemanticButton("Buy", role="primary", object_name="merchantBuyButton")
            buy.setToolTip(_commerce_tooltip(item))
            buy.clicked.connect(
                lambda _checked=False, item_id=item.id: self.trade_requested.emit(
                    self.selected_id, "buy", item_id
                )
            )
            barter = SemanticButton("Barter", role="secondary", object_name="merchantBarterButton")
            barter.setText(f"Barter {item.barter_price}")
            barter.setToolTip(_commerce_tooltip(item))
            barter.clicked.connect(
                lambda _checked=False, item_id=item.id: self.trade_requested.emit(
                    self.selected_id, "barter", item_id
                )
            )
            grid.addWidget(buy, row_index, 1)
            grid.addWidget(barter, row_index, 2)
        for row_index, item in enumerate(merchant.sellable_items, start=sell_header + 1):
            label = _commerce_entry(
                item,
                f"{item.name} ×{item.quantity} — {item.sell_price} gp",
                merchant.equipment,
            )
            sell = SemanticButton("Sell", role="secondary", object_name="merchantSellButton")
            sell.setToolTip(_commerce_tooltip(item))
            sell.clicked.connect(
                lambda _checked=False, item_id=item.id: self.trade_requested.emit(
                    self.selected_id, "sell", item_id
                )
            )
            grid.addWidget(label, row_index, 0)
            grid.addWidget(sell, row_index, 1)
        grid.setColumnStretch(0, 1)
        grid.setRowStretch(sell_header + 1 + len(merchant.sellable_items), 1)  # rows start at the top
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)
        return panel

    def show_dialogue_status(self, message: str, *, error: bool = False) -> None:
        if not hasattr(self, "dialogue_status"):
            return
        self.dialogue_status.setProperty("textRole", "danger" if error else "warning")
        self.dialogue_status.setText(message)
        self.dialogue_status.setVisible(bool(message))
        self.dialogue_status.style().unpolish(self.dialogue_status)
        self.dialogue_status.style().polish(self.dialogue_status)


class JournalPage(NavigationPage):
    """Quest log beside the filtered event log and the most recent events."""

    def __init__(self, dashboard: DashboardView) -> None:
        super().__init__(
            "journalNavigationPage",
            "JOURNAL",
            "Quests, objectives, and the recorded history of this campaign.",
        )
        self.quest_list = QuestListWidget(dashboard.quest_list)
        self.event_log = EventLogPanel(dashboard.event_log)
        self.recent_events = RecentEventsPanel(dashboard.recent_events)
        # The tall Journal columns start their entries at the top (same order and scrolling).
        for panel in (self.event_log, self.recent_events):
            panel.scroll_area.widget().layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        self.quest_panel, quest_layout = codex_card(
            "Quests", "journalQuestPanel", count=len(dashboard.quest_list)
        )
        quest_layout.setAlignment(Qt.AlignmentFlag(0))  # the quest list takes the height
        quest_layout.addWidget(self.quest_list, 1)
        columns = QHBoxLayout()
        columns.setSpacing(8)
        for widget, stretch in ((self.quest_panel, 4), (self.event_log, 5), (self.recent_events, 3)):
            columns.addWidget(widget, stretch)
        self.layout.addLayout(columns, 1)


def create_navigation_pages(dashboard: DashboardView) -> dict[str, NavigationPage]:
    pages: dict[str, NavigationPage] = {}

    map_page = NavigationPage(
        "mapNavigationPage",
        "MAP",
        "Known locations and the current route; undiscovered locations remain hidden.",
    )
    map_page.layout.addWidget(WorldMapPanel(dashboard.world_map), 1)
    pages["map"] = map_page

    people = NpcNavigationPage(dashboard.npc_conversations)
    pages["people"] = people

    pages["character_sheet"] = CharacterSheetPage(dashboard)
    pages["journal"] = JournalPage(dashboard)

    return pages
