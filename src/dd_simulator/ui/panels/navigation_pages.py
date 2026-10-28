"""Focused in-application pages opened by bottom navigation."""

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QCursor
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
    QVBoxLayout,
    QWidget,
)

from dd_simulator.ui.models.presentation import (
    CommerceItemView, ConversationView, DashboardView, EquipmentSlotView,
    InventorySlotView,
)
from dd_simulator.ui.item_icons import item_icon_label
from dd_simulator.ui.panels.activity_panels import EventLogPanel, RecentEventsPanel
from dd_simulator.ui.panels.common import highlight_recent_turn, semantic_label
from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.themed_frame import ThemedFrame
from dd_simulator.state.progression import saving_throw_proficiencies
from dd_simulator.ui.widgets.inventory_grid import ItemHoverCard, equipped_comparisons
from dd_simulator.ui.widgets.codex_cards import PowerEntry, codex_card, icon_row, plain_label
from dd_simulator.ui.widgets.codex_character import SkillDetailRow
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
        grid.addWidget(identity, 0, 0, 1, 2)

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
        grid.addWidget(attributes, 0, 2, 1, 2)

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

        powers, powers_layout = codex_card(
            "Abilities & Spells", "characterSheetSection", count=len(dashboard.combat_skills)
        )
        for action in dashboard.combat_skills:
            effect = next((value for key, value in action.stats if key == "Effect"), "")
            powers_layout.addWidget(PowerEntry(action, detail=effect or None))
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
        for slot in equipped:
            rarity = slot.item.rarity if slot.item else "common"
            category = slot.item.item_type if slot.item else "misc"
            equipment_layout.addWidget(icon_row(
                item_icon_label(str(slot.item_name), rarity=rarity, category=category, context=slot.slot_name, size=30),
                str(slot.item_name), slot.slot_name, rarity=rarity,
            ))
        if not equipped:
            equipment_layout.addWidget(plain_label("No equipment worn.", "pageCardMeta"))

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

        for column, cards in enumerate((
            (vitals, saves, appearance),
            (attacks, powers, role),
            (equipment, possessions),
            (skills,),
        )):
            grid.addLayout(_stack(*cards), 1, column)
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


def centered_third(content: QWidget, object_name: str = "centeredThird") -> QWidget:
    """Center a responsive control block at approximately one third page width."""

    host = QWidget()
    host.setObjectName(object_name)
    layout = QGridLayout(host)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    content.setMinimumWidth(0)
    content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    layout.addWidget(content, 0, 1)
    for column in range(3):
        layout.setColumnStretch(column, 1)
    return host


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
        self.people_splitter = QSplitter(Qt.Orientation.Vertical)
        self.people_splitter.setObjectName("peopleTradeConversationSplitter")
        self.people_splitter.setChildrenCollapsible(False)
        self.trade_host = QWidget()
        self.trade_host.setObjectName("peopleTradeRegion")
        self.trade_layout = QVBoxLayout(self.trade_host)
        self.trade_layout.setContentsMargins(0, 0, 0, 0)
        self.trade_host.setMinimumHeight(120)
        self.people_splitter.addWidget(self.trade_host)

        body_host = QWidget()
        body_host.setObjectName("peopleConversationRegion")
        body = QHBoxLayout(body_host)
        body.setContentsMargins(0, 0, 0, 0)
        selector = QVBoxLayout()
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
        if not conversations:
            selector.addWidget(semantic_label("No known NPCs are present.", text_role="muted"))
        selector.addStretch(1)
        selector_host = QWidget()
        selector_host.setLayout(selector)
        selector_host.setMaximumWidth(310)
        body.addWidget(selector_host)
        self.conversation_host = QWidget()
        self.conversation_layout = QVBoxLayout(self.conversation_host)
        self.conversation_layout.setContentsMargins(0, 0, 0, 0)
        body.addWidget(self.conversation_host, 1)
        body_host.setMinimumHeight(180)
        self.people_splitter.addWidget(body_host)
        self.people_splitter.setStretchFactor(0, 2)
        self.people_splitter.setStretchFactor(1, 5)
        self.people_splitter.setSizes([210, 500])
        self.layout.addWidget(self.people_splitter, 1)
        self.action_host = QWidget()
        self.action_host.setObjectName("npcBottomControls")
        self.action_layout = QVBoxLayout(self.action_host)
        self.action_layout.setContentsMargins(0, 0, 0, 0)
        self.action_layout.setSpacing(4)
        self.layout.addWidget(centered_third(self.action_host, "npcCenteredFooter"))
        self._render_selected()

    def _select_npc(self, npc_id: str) -> None:
        self.selected_id = npc_id
        self._render_selected()

    def open_npc(self, npc_id: str) -> None:
        if any(value.npc.id == npc_id for value in self.conversations):
            self._select_npc(npc_id)

    def _render_selected(self) -> None:
        self.latest_turn_widgets: list[QWidget] = []
        while self.conversation_layout.count():
            item = self.conversation_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        while self.action_layout.count():
            item = self.action_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        while self.trade_layout.count():
            item = self.trade_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        conversation = next(
            (value for value in self.conversations if value.npc.id == self.selected_id), None
        )
        if conversation is None:
            self.conversation_layout.addWidget(
                semantic_label("Select an available NPC to begin.", text_role="muted")
            )
            return
        npc = conversation.npc
        self.conversation_layout.addWidget(
            semantic_label(
                f"{npc.portrait_initials or '?'}   {npc.name} — {npc.title or npc.status.title()}",
                object_name="npcConversationTitle", text_role="heading",
            )
        )
        self.conversation_layout.addWidget(
            semantic_label(
                f"Disposition: {npc.status.title()}   Relationship: {npc.relationship_score:+d}",
                text_role="secondary",
            )
        )
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
            self.trade_layout.addWidget(centered_third(
                self._merchant_panel(conversation), "merchantCenteredContainer"
            ))
        else:
            self.trade_host.setVisible(False)
        scroll = QScrollArea()
        scroll.setObjectName("npcConversationScroll")
        scroll.setWidgetResizable(True)
        history = QWidget()
        history.setObjectName("npcConversationHistory")
        history_layout = QVBoxLayout(history)
        latest_player_index = max(
            (
                index
                for index, message in enumerate(conversation.messages)
                if message.kind == "player"
            ),
            default=-1,
        )
        for index, message in enumerate(conversation.messages):
            prefix = "You: " if message.kind == "player" else ""
            label = semantic_label(
                prefix + message.text,
                object_name=f"npc{message.kind.title()}Message{index}",
                text_role="playerAction" if message.kind == "player" else message.kind,
                word_wrap=True,
            )
            history_layout.addWidget(label)
            if index >= latest_player_index and latest_player_index >= 0:
                self.latest_turn_widgets.append(label)
        if not conversation.messages:
            history_layout.addWidget(
                semantic_label("The conversation has not begun.", text_role="muted")
            )
        history_layout.addStretch(1)
        scroll.setWidget(history)
        self.conversation_layout.addWidget(scroll, 1)
        if conversation.last_check:
            self.conversation_layout.addWidget(
                semantic_label(conversation.last_check, text_role="warning", word_wrap=True)
            )
        choices = QGridLayout()
        for index, response in enumerate(conversation.suggested_responses):
            button = SemanticButton(response, role="secondary", object_name="npcSuggestedResponse")
            button.setEnabled(npc.available)
            button.setToolTip(response)
            button.clicked.connect(
                lambda _checked=False, text=response: self.dialogue_requested.emit(self.selected_id, text)
            )
            choices.addWidget(button, index // 2, index % 2)
        choices_host = QWidget()
        choices_host.setLayout(choices)
        self.action_layout.addWidget(choices_host)
        row = QHBoxLayout()
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
        highlight_recent_turn(
            self,
            self.latest_turn_widgets,
            reduced_motion=reduced_motion,
        )

    def _merchant_panel(self, conversation: ConversationView) -> ThemedFrame:
        merchant = conversation.merchant
        assert merchant is not None
        panel = ThemedFrame("merchantTradePanel", role="section")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 7, 8, 7)
        layout.setSpacing(5)
        layout.addWidget(semantic_label(
            f"TRADE — {merchant.player_currency} GOLD",
            object_name="merchantTradeTitle", text_role="accent",
        ))
        scroll = QScrollArea()
        scroll.setObjectName("merchantTradeScroll")
        scroll.setWidgetResizable(True)
        content = QWidget()
        content.setObjectName("merchantTradeContent")
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        grid.addWidget(semantic_label("MERCHANT STOCK", text_role="secondary"), 0, 0, 1, 3)
        grid.addWidget(semantic_label("SELL FROM INVENTORY", text_role="secondary"), 0, 3, 1, 2)
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
        for row_index, item in enumerate(merchant.sellable_items, start=1):
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
            grid.addWidget(label, row_index, 3)
            grid.addWidget(sell, row_index, 4)
        grid.setColumnStretch(0, 2)
        grid.setColumnStretch(3, 2)
        scroll.setWidget(content)
        layout.addWidget(scroll)
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
