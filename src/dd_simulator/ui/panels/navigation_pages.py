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
from dd_simulator.ui.widgets.quest_list import QuestListWidget
from dd_simulator.ui.widgets.world_map import WorldMapPanel


class NavigationPage(ThemedFrame):
    back_requested = Signal()

    def __init__(self, object_name: str, title: str, description: str) -> None:
        super().__init__(object_name, role="content")
        self.setAccessibleName(title)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 12, 14, 12)
        self.layout.setSpacing(8)
        self.layout.addWidget(
            semantic_label(title, object_name="navigationPageTitle", text_role="heading")
        )
        self.layout.addWidget(
            semantic_label(description, text_role="secondary", word_wrap=True)
        )

    def finish(self) -> None:
        back = SemanticButton("Return to Adventure", role="secondary")
        back.setObjectName("navigationBackButton")
        back.clicked.connect(self.back_requested)
        self.layout.addWidget(centered_third(back, "navigationFooter"))


def _sheet_section(title: str) -> tuple[ThemedFrame, QVBoxLayout]:
    section = ThemedFrame("characterSheetSection", role="section")
    section.setProperty("sheetSection", title.casefold().replace(" ", "_"))
    layout = QVBoxLayout(section)
    layout.setContentsMargins(9, 5, 9, 6)
    layout.setSpacing(2)
    layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    layout.addWidget(
        semantic_label(
            title.upper(), object_name="characterSheetSectionTitle", text_role="accent"
        )
    )
    return section, layout


class CharacterSheetPage(NavigationPage):
    """Original, read-only 5E-inspired view of authoritative campaign state."""

    crafting_requested = Signal()

    def __init__(self, dashboard: DashboardView) -> None:
        super().__init__(
            "characterSheetNavigationPage",
            "CHARACTER SHEET",
            "A themed summary of the current character and their adventuring capabilities.",
        )
        scroll = QScrollArea()
        scroll.setObjectName("characterSheetScroll")
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidgetResizable(True)

        viewport = QWidget()
        viewport.setObjectName("characterSheetViewport")
        centered = QGridLayout(viewport)
        centered.setContentsMargins(0, 2, 0, 2)
        centered.setColumnStretch(0, 1)
        centered.setColumnStretch(1, 3)
        centered.setColumnStretch(2, 1)

        sheet = ThemedFrame("characterSheetSurface", role="section")
        sheet.setAccessibleName(f"Character sheet for {dashboard.player.name}")
        page = QVBoxLayout(sheet)
        page.setContentsMargins(14, 12, 14, 14)
        page.setSpacing(8)

        identity = ThemedFrame("characterSheetIdentity", role="section")
        identity_grid = QGridLayout(identity)
        identity_grid.setContentsMargins(10, 8, 10, 8)
        identity_grid.setHorizontalSpacing(16)
        fields = (
            ("Character", dashboard.player.name),
            ("Ancestry", dashboard.player.species or "Unknown"),
            ("Class", dashboard.player.character_class),
            ("Level", str(dashboard.player.level)),
            ("Background", dashboard.player.background or "Unrecorded"),
        )
        for column, (label, value) in enumerate(fields):
            identity_grid.addWidget(
                semantic_label(label.upper(), text_role="muted"), 0, column
            )
            identity_grid.addWidget(
                semantic_label(value, object_name="characterSheetIdentityValue", text_role="body", word_wrap=True),
                1,
                column,
            )
            identity_grid.setColumnStretch(column, 1)
        page.addWidget(identity)

        attributes = QWidget()
        attributes.setObjectName("characterSheetAttributes")
        attribute_grid = QGridLayout(attributes)
        attribute_grid.setContentsMargins(0, 0, 0, 0)
        attribute_grid.setSpacing(5)
        for column, attribute in enumerate(dashboard.player.attributes[:6]):
            card = ThemedFrame("characterSheetAttribute", role="section")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(5, 4, 5, 5)
            card_layout.setSpacing(1)
            name = semantic_label(attribute.name.upper(), text_role="muted")
            name.setAlignment(Qt.AlignmentFlag.AlignCenter)
            value = semantic_label(str(attribute.value), object_name="characterSheetAttributeValue", text_role="heading")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            modifier = semantic_label(f"{attribute.modifier:+d}", object_name="characterSheetModifier", text_role="accent")
            modifier.setAlignment(Qt.AlignmentFlag.AlignCenter)
            card_layout.addWidget(name)
            card_layout.addWidget(value)
            card_layout.addWidget(modifier)
            attribute_grid.addWidget(card, 0, column)
            attribute_grid.setColumnStretch(column, 1)
        page.addWidget(attributes)

        columns = QHBoxLayout()
        columns.setSpacing(7)

        left = QVBoxLayout()
        vitals, vitals_layout = _sheet_section("Combat Summary")
        health = next(
            (
                resource
                for resource in dashboard.player.resources
                if resource.resource_type == "health"
            ),
            None,
        )
        vitals_grid = QGridLayout()
        vitals_grid.addWidget(semantic_label("Hit Points", text_role="muted"), 0, 0)
        vitals_grid.addWidget(
            semantic_label(
                f"{health.current} / {health.maximum}" if health else "—",
                object_name="characterSheetVitalValue",
                text_role="heading",
            ),
            1,
            0,
        )
        for index, (label, value) in enumerate((
            ("Armor", str(dashboard.player.armor_class)),
            ("Initiative", f"{dashboard.player.initiative_modifier:+d}"),
            ("Speed", f"{dashboard.player.movement_feet} ft"),
            ("Proficiency", f"+{dashboard.player.proficiency_bonus}"),
        ), start=1):
            vitals_grid.addWidget(semantic_label(label, text_role="muted"), 0, index)
            vitals_grid.addWidget(
                semantic_label(value, object_name="characterSheetVitalValue", text_role="heading"),
                1,
                index,
            )
        vitals_layout.addLayout(vitals_grid)
        left.addWidget(vitals)

        if dashboard.player.pending_ability_points:
            pending = semantic_label(
                f"LEVEL-UP CHOICE PENDING: "
                f"{dashboard.player.pending_ability_points} ability-score points",
                text_role="accent",
                word_wrap=True,
            )
            left.addWidget(pending)

        saves, saves_layout = _sheet_section("Saving Throws")
        proficient_saves = saving_throw_proficiencies(
            dashboard.player.character_class
        )
        for attribute in dashboard.player.attributes[:6]:
            proficient = attribute.name.casefold() in proficient_saves
            save_bonus = attribute.modifier + (
                dashboard.player.proficiency_bonus if proficient else 0
            )
            saves_layout.addWidget(
                semantic_label(
                    f"{attribute.name}: {save_bonus:+d}"
                    f"{' (proficient)' if proficient else ''}",
                    text_role="body",
                )
            )
        left.addWidget(saves)

        appearance, appearance_layout = _sheet_section("Appearance & Biography")
        appearance_rows = (
            ("Age", str(dashboard.player.age) if dashboard.player.age else "Unrecorded"),
            ("Gender", dashboard.player.gender_identity or "Unrecorded"),
            ("Pronouns", dashboard.player.pronouns or "Unrecorded"),
            ("Body", dashboard.player.body_description or "Unrecorded"),
            ("Face", dashboard.player.face_description or "Unrecorded"),
            ("Clothing", dashboard.player.clothing_style or "Unrecorded"),
            ("Biography/Backstory", dashboard.player.biography or dashboard.player.backstory or "Unrecorded"),
        )
        for label, value in appearance_rows:
            appearance_layout.addWidget(
                semantic_label(f"{label}: {value}", text_role="body", word_wrap=True)
            )
        left.addWidget(appearance)
        left.addStretch(1)

        middle = QVBoxLayout()
        attacks, attacks_layout = _sheet_section("Weapon Attacks")
        weapons = tuple(
            slot.item for slot in dashboard.equipment
            if slot.item is not None and slot.item.damage
        )
        for weapon in weapons:
            attacks_layout.addWidget(
                semantic_label(
                    f"{weapon.name}  •  {weapon.damage}", text_role="body", word_wrap=True
                )
            )
        if not weapons:
            attacks_layout.addWidget(semantic_label("No damaging weapon equipped.", text_role="muted"))
        middle.addWidget(attacks)

        abilities, abilities_layout = _sheet_section("Abilities & Spells")
        for action in dashboard.combat_skills:
            effect = next((value for key, value in action.stats if key == "Effect"), "")
            abilities_layout.addWidget(
                semantic_label(
                    f"{action.name}  •  {effect or action.resource_label}",
                    text_role="body",
                    word_wrap=True,
                )
            )
        if not dashboard.combat_skills:
            abilities_layout.addWidget(semantic_label("No abilities unlocked.", text_role="muted"))
        middle.addWidget(abilities)

        equipment, equipment_layout = _sheet_section("Equipment")
        equipped = tuple(slot for slot in dashboard.equipment if slot.item_name)
        for slot in equipped:
            equipment_layout.addWidget(
                semantic_label(
                    f"{slot.slot_name}: {slot.item_name}", text_role="body", word_wrap=True
                )
            )
        if not equipped:
            equipment_layout.addWidget(semantic_label("No equipment worn.", text_role="muted"))
        middle.addWidget(equipment)
        middle.addStretch(1)

        right = QVBoxLayout()
        skills, skills_layout = _sheet_section("Skills")
        for skill in dashboard.skills:
            skills_layout.addWidget(
                semantic_label(
                    f"{skill.name}: {skill.level + skill.bonus:+d}", text_role="body"
                )
            )
        right.addWidget(skills)

        role, role_layout = _sheet_section("Role & Character")
        role_rows = (
            ("Personality", ", ".join(dashboard.player.personalities) or "Unrecorded"),
            ("Strength", dashboard.player.primary_strength or "Unrecorded"),
            ("Flaw", dashboard.player.meaningful_flaw or "Unrecorded"),
            ("Motivation", dashboard.player.motivation or "Unrecorded"),
        )
        for label, value in role_rows:
            role_layout.addWidget(
                semantic_label(f"{label}: {value}", text_role="body", word_wrap=True)
            )
        right.addWidget(role)
        right.addStretch(1)

        left_host = QWidget(); left_host.setLayout(left)
        middle_host = QWidget(); middle_host.setLayout(middle)
        right_host = QWidget(); right_host.setLayout(right)
        columns.addWidget(left_host, 2)
        columns.addWidget(middle_host, 3)
        columns.addWidget(right_host, 2)
        page.addLayout(columns)

        possessions, possessions_layout = _sheet_section("Possessions & Currency")
        names = [
            f"{item.name} ×{item.quantity}" if item.quantity > 1 else str(item.name)
            for item in dashboard.inventory_preview if not item.is_empty
        ]
        possessions_layout.addWidget(
            semantic_label(
                ", ".join(names) if names else "No carried items.",
                text_role="body",
                word_wrap=True,
            )
        )
        possessions_layout.addWidget(
            semantic_label(f"Gold: {dashboard.player.currency}", text_role="accent")
        )
        page.addWidget(possessions)

        centered.addWidget(sheet, 0, 1)
        scroll.setWidget(viewport)
        self.layout.addWidget(scroll, 1)
        crafting = SemanticButton("Crafting", role="secondary")
        crafting.setObjectName("characterSheetCraftingButton")
        crafting.setAccessibleName("Open crafting")
        crafting.setToolTip("Craft items from known recipes")
        crafting.clicked.connect(self.crafting_requested)
        self.layout.addWidget(centered_third(crafting, "characterSheetCraftingFooter"))
        self.finish()


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
        back = SemanticButton("Return to Adventure", role="secondary")
        back.setObjectName("navigationBackButton")
        back.clicked.connect(self.back_requested)
        self.action_layout.addWidget(back)

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
        columns = QHBoxLayout()
        columns.setSpacing(8)
        for widget, stretch in ((self.quest_list, 4), (self.event_log, 5), (self.recent_events, 3)):
            columns.addWidget(widget, stretch)
        self.layout.addLayout(columns, 1)
        self.finish()


def create_navigation_pages(dashboard: DashboardView) -> dict[str, NavigationPage]:
    pages: dict[str, NavigationPage] = {}

    map_page = NavigationPage(
        "mapNavigationPage",
        "MAP",
        "Known locations and the current route; undiscovered locations remain hidden.",
    )
    map_page.layout.addWidget(WorldMapPanel(dashboard.world_map), 1)
    map_page.finish()
    pages["map"] = map_page

    people = NpcNavigationPage(dashboard.npc_conversations)
    pages["people"] = people

    pages["character_sheet"] = CharacterSheetPage(dashboard)
    pages["journal"] = JournalPage(dashboard)

    return pages
