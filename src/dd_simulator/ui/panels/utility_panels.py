"""Static minimap, resources, skills, and inventory previews."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QCursor, QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QStackedWidget,
    QTabBar,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.state import CombatAction, CombatCommand

from dd_simulator.ui.models.presentation import (
    CombatEncounterView,
    CombatActionOptionView,
    CraftingRecipeView,
    EquipmentSlotView,
    InventorySlotView,
    LocationSummaryView,
    QuestListItemView,
    SkillView,
    NpcView,
)
from dd_simulator.ui.panels.common import DashboardPanel, semantic_label
from dd_simulator.ui.panels.summary_panels import (
    _apply_location_catalog_visual,
    _apply_visual,
)
from dd_simulator.ui.widgets.inventory_grid import (
    EQUIPMENT_SLOT_SPACING,
    EquipmentGrid,
    INVENTORY_PAGE_SIZE,
    INVENTORY_SLOT_SIZE,
    InventoryGrid,
)
from dd_simulator.ui.widgets.full_click_combo import FullClickComboBox
from dd_simulator.ui.widgets.quest_list import QuestListWidget
from dd_simulator.ui.widgets.skills_grid import CombatSkillsGrid, SkillsGrid
from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.crafting_page import CraftingPage


class CombatUtilityPage(QScrollArea):
    start_requested = Signal()
    action_requested = Signal(object)

    def __init__(self, encounter: CombatEncounterView | None) -> None:
        super().__init__()
        self.setObjectName("combatUtilityPage")
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("combatUtilityContent")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(6)
        self.action_buttons: list[SemanticButton] = []

        if encounter is None:
            layout.addWidget(
                semantic_label(
                    "No encounter is active. Start the deterministic roadside combat "
                    "demonstration when you are ready.",
                    text_role="muted",
                    word_wrap=True,
                )
            )
            start = SemanticButton(
                "Begin Encounter", role="primary", object_name="startCombatButton"
            )
            start.clicked.connect(self.start_requested)
            layout.addWidget(start)
            rest = SemanticButton("Take Short Rest", object_name="combatRestButton")
            rest.clicked.connect(
                lambda: self.action_requested.emit(CombatCommand(CombatAction.RECOVER))
            )
            layout.addWidget(rest)
            layout.addStretch(1)
            self.setWidget(content)
            return

        status = semantic_label(
            f"{encounter.status.upper()}  •  ROUND {encounter.round_number}",
            object_name="combatStatusLabel",
            text_role="accent",
        )
        layout.addWidget(status)
        layout.addWidget(
            semantic_label(
                encounter.environment,
                object_name="combatEnvironmentLabel",
                text_role="heading",
            )
        )
        if encounter.hazard:
            layout.addWidget(
                semantic_label(
                    f"Hazard: {encounter.hazard}", text_role="warning", word_wrap=True
                )
            )

        if encounter.generated and not encounter.intro_complete:
            layout.addWidget(
                semantic_label(
                    encounter.introduction,
                    object_name="encounterIntroduction",
                    text_role="body",
                    word_wrap=True,
                )
            )
            layout.addWidget(
                semantic_label(
                    f"Difficulty {encounter.difficulty_rating}  •  "
                    f"{encounter.awareness_state.replace('_', ' ').title()}  •  "
                    f"{encounter.terrain}",
                    text_role="warning",
                    word_wrap=True,
                )
            )
            for combatant in encounter.combatants:
                if combatant.side != "enemy":
                    continue
                traits: list[str] = []
                if combatant.abilities:
                    traits.append("Abilities: " + ", ".join(combatant.abilities))
                if combatant.resistances:
                    traits.append("Resists: " + ", ".join(combatant.resistances))
                if combatant.vulnerabilities:
                    traits.append("Vulnerable: " + ", ".join(combatant.vulnerabilities))
                layout.addWidget(
                    semantic_label(
                        f"{combatant.name} — {combatant.current_health} HP — "
                        f"AC {combatant.armor_class} — {combatant.distance_feet} ft"
                        + ("\n" + " | ".join(traits) if traits else ""),
                        object_name="encounterVisibleEnemy",
                        text_role="secondary",
                        word_wrap=True,
                    )
                )
            layout.addWidget(
                semantic_label(
                    "PREPARATION", object_name="utilitySectionTitle", text_role="accent"
                )
            )
            for label, choice in (
                ("Take Cover (+2 Armor)", "take_cover"),
                ("Scout (+1 Attack)", "scout"),
                ("Charge (Close 15 ft)", "charge"),
            ):
                button = SemanticButton(
                    label, role="primary" if choice == "scout" else "default",
                    object_name="combatPreparationButton",
                )
                button.setProperty("baseEnabled", True)
                button.clicked.connect(
                    lambda _checked=False, selected=choice:
                    self.action_requested.emit(
                        CombatCommand(CombatAction.PREPARE, preparation=selected)
                    )
                )
                layout.addWidget(button)
                self.action_buttons.append(button)
            layout.addStretch(1)
            self.setWidget(content)
            return

        initiative = QWidget()
        initiative.setObjectName("initiativeList")
        initiative_layout = QVBoxLayout(initiative)
        initiative_layout.setContentsMargins(0, 0, 0, 0)
        initiative_layout.setSpacing(3)
        for combatant in encounter.combatants:
            marker = "> " if combatant.active_turn and encounter.status == "active" else ""
            condition = (
                f" • {', '.join(combatant.conditions)}" if combatant.conditions else ""
            )
            row = semantic_label(
                f"{marker}{combatant.initiative:>2}  {combatant.name}  "
                f"{combatant.current_health}/{combatant.maximum_health} HP  "
                f"AC {combatant.armor_class}  {combatant.distance_feet} ft{condition}",
                object_name="combatantRow",
                text_role=(
                    "danger"
                    if combatant.current_health <= combatant.maximum_health * 0.25
                    else "default"
                ),
                word_wrap=True,
            )
            row.setProperty("activeTurn", combatant.active_turn)
            row.setProperty("combatSide", combatant.side)
            initiative_layout.addWidget(row)
        layout.addWidget(initiative)

        if encounter.status == "active":
            enemies = tuple(
                combatant
                for combatant in encounter.combatants
                if combatant.side == "enemy" and combatant.status == "active"
            )
            target_row = QHBoxLayout()
            target_row.addWidget(semantic_label("Target", text_role="muted"))
            self.target_selector = FullClickComboBox()
            self.target_selector.setObjectName("combatTargetSelector")
            self.target_selector.setEditable(False)
            for enemy in enemies:
                self.target_selector.addItem(
                    f"{enemy.name} — {enemy.current_health} HP — {enemy.distance_feet} ft",
                    enemy.id,
                )
            target_row.addWidget(self.target_selector, 1)
            layout.addLayout(target_row)

            controls = QGridLayout()
            controls.setSpacing(4)
            actions = (
                ("Attack", CombatAction.ATTACK),
                ("Advance", CombatAction.ADVANCE),
                ("Defend", CombatAction.DEFEND),
                ("Use Potion", CombatAction.USE_ITEM),
                ("Negotiate", CombatAction.NEGOTIATE),
                ("Flee", CombatAction.FLEE),
            )
            player_turn = any(
                combatant.side == "player" and combatant.active_turn
                for combatant in encounter.combatants
            )
            for index, (label, action) in enumerate(actions):
                button = SemanticButton(
                    label,
                    role="primary" if action is CombatAction.ATTACK else "default",
                    object_name="combatActionButton",
                )
                button.setProperty("combatAction", action.value)
                button.setEnabled(player_turn)
                button.setProperty("baseEnabled", player_turn)
                button.clicked.connect(
                    lambda _checked=False, selected=action: self._emit_action(selected)
                )
                controls.addWidget(button, index // 2, index % 2)
                self.action_buttons.append(button)
            layout.addLayout(controls)

            for kind, title, action in (
                ("ability", "CLASS ABILITY", CombatAction.ABILITY),
                ("spell", "SPELL", CombatAction.SPELL),
            ):
                options = tuple(
                    option for option in encounter.action_options if option.kind == kind
                )
                if not options:
                    continue
                layout.addWidget(
                    semantic_label(title, object_name="utilitySectionTitle", text_role="accent")
                )
                selector = FullClickComboBox()
                selector.setObjectName(f"combat{title.title().replace(' ', '')}Selector")
                selector.setEditable(False)
                for option in options:
                    selector.addItem(f"{option.name} — {option.resource_label}", option.key)
                    selector.setItemData(
                        selector.count() - 1,
                        option.unavailable_reason or option.description,
                        Qt.ItemDataRole.ToolTipRole,
                    )
                detail = semantic_label(
                    "", object_name="combatActionDetail", text_role="muted", word_wrap=True
                )
                button = SemanticButton(
                    "Use Ability" if kind == "ability" else "Cast Spell",
                    role="primary" if kind == "spell" else "default",
                    object_name="combatActionButton",
                )
                button.setProperty("combatAction", action.value)

                def update_choice(
                    index: int,
                    *, selected_options=options,
                    selected_detail=detail,
                    selected_button=button,
                    can_act=player_turn,
                ) -> None:
                    option = selected_options[index] if 0 <= index < len(selected_options) else None
                    if option is None:
                        selected_detail.setText("No action is selected.")
                        enabled = False
                    else:
                        text = option.description
                        if option.unavailable_reason:
                            text += f" Unavailable: {option.unavailable_reason}."
                        selected_detail.setText(text)
                        enabled = can_act and option.available
                    selected_button.setEnabled(enabled)
                    selected_button.setProperty("baseEnabled", enabled)

                selector.currentIndexChanged.connect(update_choice)
                button.clicked.connect(
                    lambda _checked=False, selected_action=action, selected_selector=selector:
                    self._emit_catalog_action(selected_action, selected_selector)
                )
                layout.addWidget(selector)
                layout.addWidget(detail)
                layout.addWidget(button)
                self.action_buttons.append(button)
                update_choice(selector.currentIndex())
        else:
            if encounter.end_reason:
                layout.addWidget(
                    semantic_label(encounter.end_reason, text_role="success", word_wrap=True)
                )
            start = SemanticButton(
                "Begin New Encounter", role="primary", object_name="startCombatButton"
            )
            start.clicked.connect(self.start_requested)
            layout.addWidget(start)
            rest = SemanticButton("Take Short Rest", object_name="combatRestButton")
            rest.clicked.connect(
                lambda: self.action_requested.emit(CombatCommand(CombatAction.RECOVER))
            )
            layout.addWidget(rest)

        if encounter.recent_turns:
            layout.addWidget(
                semantic_label("RECENT COMBAT", object_name="utilitySectionTitle", text_role="accent")
            )
            for turn in encounter.recent_turns[-4:]:
                layout.addWidget(
                    semantic_label(
                        f"R{turn.round_number} • {turn.summary}",
                        object_name="combatLogEntry",
                        text_role="muted",
                        word_wrap=True,
                    )
                )
        layout.addStretch(1)
        self.setWidget(content)

    def _emit_action(self, action: CombatAction) -> None:
        target_id = None
        if action in {CombatAction.ATTACK, CombatAction.ABILITY, CombatAction.NEGOTIATE} and hasattr(self, "target_selector"):
            target_id = str(self.target_selector.currentData() or "") or None
        self.action_requested.emit(CombatCommand(action, target_id=target_id))

    def _emit_catalog_action(
        self, action: CombatAction, selector: FullClickComboBox
    ) -> None:
        target_id = None
        if hasattr(self, "target_selector"):
            target_id = str(self.target_selector.currentData() or "") or None
        ability_key = str(selector.currentData() or "") or None
        self.action_requested.emit(
            CombatCommand(action, target_id=target_id, ability_key=ability_key)
        )

    def set_pending(self, pending: bool) -> None:
        for button in self.action_buttons:
            button.setEnabled(not pending and bool(button.property("baseEnabled")))


class MinimapPanel(DashboardPanel):
    def __init__(self, location: LocationSummaryView, npcs: tuple[NpcView, ...] = ()) -> None:
        super().__init__("minimapPanel", "")
        preview = ResponsiveLocationLabel(f"{location.name.upper()}\nLOCATION VISUAL")
        preview.setObjectName("locationVisualPlaceholder")
        preview.setAccessibleName(f"Location visual for {location.name}")
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setMinimumSize(180, 120)
        preview.setWordWrap(True)
        _apply_visual(
            preview,
            location.visual,
            fallback_text=f"{location.name.upper()}\nLOCATION VISUAL",
            target_size=QSize(320, 180),
        )
        if location.visual is None:
            _apply_location_catalog_visual(preview, location)
        self.content_layout.addWidget(preview, 1)


class ResponsiveLocationLabel(QLabel):
    """Aspect-preserving cover image that follows its splitter allocation."""

    def __init__(self, text: str = "") -> None:
        super().__init__(text)
        self._source_pixmap = None

    def set_source_pixmap(self, pixmap) -> None:  # type: ignore[no-untyped-def]
        self._source_pixmap = pixmap
        self._rescale()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._rescale()

    def _rescale(self) -> None:
        if self._source_pixmap is None or self._source_pixmap.isNull():
            return
        size = self.contentsRect().size()
        if size.isEmpty():
            return
        scaled = self._source_pixmap.scaled(
            size,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        x = max(0, (scaled.width() - size.width()) // 2)
        y = max(0, (scaled.height() - size.height()) // 2)
        QLabel.setPixmap(self, scaled.copy(x, y, size.width(), size.height()))


class MinimapCanvas(QFrame):
    """Theme-neutral minimap surface for live edge labels."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("minimapCanvas")


class UtilityContentPanel(DashboardPanel):
    tab_changed = Signal(int)
    combat_start_requested = Signal()
    combat_action_requested = Signal(object)
    inventory_auto_sort_requested = Signal(str)
    craft_requested = Signal(str)

    def __init__(
        self,
        skills: tuple[SkillView, ...],
        inventory: tuple[InventorySlotView, ...],
        equipment: tuple[EquipmentSlotView, ...],
        combat_skills: tuple[CombatActionOptionView, ...] = (),
        combat: CombatEncounterView | None = None,
        crafting_recipes: tuple[CraftingRecipeView, ...] = (),
    ) -> None:
        super().__init__("utilityContentStack", "ADVENTURER TOOLS")
        self.content_layout.setContentsMargins(10, 7, 10, 7)
        self.content_layout.setSpacing(4)

        tabs = QTabBar()
        tabs.setObjectName("utilityTabBar")
        for name in ("Combat", "Skills", "Inventory", "Crafting"):
            tabs.addTab(name)
        tabs.setCurrentIndex(1)
        tabs.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.content_layout.addWidget(tabs)
        self.tabs = tabs

        stack = QStackedWidget()
        stack.setObjectName("utilityPageStack")
        self.stack = stack

        self.combat_page = CombatUtilityPage(combat)
        self.combat_page.start_requested.connect(self.combat_start_requested)
        self.combat_page.action_requested.connect(self.combat_action_requested)
        stack.addWidget(self.combat_page)

        skills_page = QWidget()
        skills_page.setObjectName("skillsUtilityPage")
        skills_layout = QVBoxLayout(skills_page)
        skills_layout.setContentsMargins(0, 0, 0, 0)
        skills_layout.addWidget(semantic_label("PLAYER SKILLS", text_role="accent"))
        skills_layout.addWidget(SkillsGrid(skills, columns=2))
        skills_layout.addWidget(semantic_label("COMBAT ABILITIES & SPELLS", text_role="accent"))
        skills_layout.addWidget(CombatSkillsGrid(combat_skills))
        skills_layout.addStretch(1)
        stack.addWidget(skills_page)

        inventory_page = QWidget()
        inventory_page.setObjectName("inventoryUtilityPage")
        inventory_layout = QVBoxLayout(inventory_page)
        inventory_layout.setContentsMargins(0, 0, 4, 0)
        inventory_layout.setSpacing(3)
        inventory_header = QHBoxLayout()
        inventory_header.setContentsMargins(0, 0, 0, 0)
        inventory_header.addWidget(
            semantic_label("INVENTORY", object_name="utilitySectionTitle", text_role="accent")
        )
        inventory_header.addStretch(1)
        self.inventory_previous_button = SemanticButton(
            "<", role="secondary", object_name="inventoryPreviousPageButton"
        )
        self.inventory_previous_button.setAccessibleName("Previous inventory page")
        self.inventory_next_button = SemanticButton(
            ">", role="secondary", object_name="inventoryNextPageButton"
        )
        self.inventory_next_button.setAccessibleName("Next inventory page")
        for button in (self.inventory_previous_button, self.inventory_next_button):
            button.setFixedSize(28, 24)
            inventory_header.addWidget(button)
        inventory_layout.addLayout(inventory_header)
        self.inventory_items = inventory
        self.inventory_page = 0
        self.inventory_page_count = max(
            1, (len(inventory) + INVENTORY_PAGE_SIZE - 1) // INVENTORY_PAGE_SIZE
        )
        self.top_equipment_grid = EquipmentGrid(
            equipment,
            columns=5,
            slot_names=("Main Hand", "Off Hand", "Neck", "Ring", "Ammunition"),
            slot_size=INVENTORY_SLOT_SIZE,
            spacing=0,
        )
        self.left_equipment_grid = EquipmentGrid(
            equipment,
            columns=1,
            slot_names=("Head", "Body", "Hands", "Feet"),
            slot_size=INVENTORY_SLOT_SIZE,
            spacing=0,
        )
        # Compatibility alias for callers that only need an equipment grid handle.
        self.equipment_grid = self.top_equipment_grid

        self.inventory_grid = InventoryGrid(
            inventory[:INVENTORY_PAGE_SIZE],
            columns=6,
            slot_count=INVENTORY_PAGE_SIZE,
            equipment=equipment,
        )
        self.inventory_scroll = QScrollArea()
        self.inventory_scroll.setObjectName("inventoryUtilityScroll")
        self.inventory_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.inventory_scroll.setWidgetResizable(False)
        self.inventory_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.inventory_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self.inventory_scroll.setAlignment(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop
        )
        self.inventory_surface = QWidget()
        self.inventory_surface.setObjectName("inventoryEquipmentSurface")
        for child in (
            self.top_equipment_grid,
            self.left_equipment_grid,
            self.inventory_grid,
        ):
            child.setParent(self.inventory_surface)
        self._relayout_inventory_surface()
        self.inventory_scroll.setWidget(self.inventory_surface)
        inventory_layout.addWidget(self.inventory_scroll, 1)
        self.auto_sort_button = SemanticButton(
            "Auto-Sort", role="secondary", object_name="autoSortInventoryButton"
        )
        self.auto_sort_button.setToolTip("Choose how unequipped inventory is sorted")
        auto_sort_menu = QMenu(self.auto_sort_button)
        auto_sort_menu.setObjectName("autoSortInventoryMenu")
        for label, mode in (
            ("Default", "default"),
            ("Rarity", "rarity"),
            ("Type", "type"),
            ("Value", "value"),
        ):
            action = auto_sort_menu.addAction(label)
            action.triggered.connect(
                lambda _checked=False, value=mode: self.inventory_auto_sort_requested.emit(value)
            )
        self.auto_sort_menu = auto_sort_menu
        self.auto_sort_button.clicked.connect(
            lambda: self.auto_sort_menu.popup(QCursor.pos())
        )
        inventory_layout.addWidget(self.auto_sort_button)
        stack.addWidget(inventory_page)
        self.inventory_previous_button.clicked.connect(
            lambda: self.set_inventory_page(self.inventory_page - 1)
        )
        self.inventory_next_button.clicked.connect(
            lambda: self.set_inventory_page(self.inventory_page + 1)
        )
        self._refresh_inventory_page_controls()

        self.crafting_page = CraftingPage(crafting_recipes)
        self.crafting_page.craft_requested.connect(self.craft_requested)
        stack.addWidget(self.crafting_page)

        stack.setCurrentIndex(1)
        tabs.currentChanged.connect(self._change_tab)
        self.content_layout.addWidget(stack, 1)

    def _change_tab(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.tab_changed.emit(index)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if hasattr(self, "inventory_grid"):
            # Six is the visual maximum. Narrow windows return to four columns
            # and use the existing vertical scroll area.
            required_width = (
                7 * INVENTORY_SLOT_SIZE + EQUIPMENT_SLOT_SPACING + 24
            )
            self.inventory_grid.set_columns(
                6 if event.size().width() >= required_width else 4
            )
            if hasattr(self, "inventory_surface"):
                self._relayout_inventory_surface()

    def _relayout_inventory_surface(self) -> None:
        """Keep equipment anchored to the inventory grid at either column count."""

        gap = EQUIPMENT_SLOT_SPACING
        inventory_x = INVENTORY_SLOT_SIZE + gap
        inventory_y = INVENTORY_SLOT_SIZE + gap
        top_x = inventory_x + (
            self.inventory_grid.width() - self.top_equipment_grid.width()
        ) // 2
        left_x = inventory_x - gap - INVENTORY_SLOT_SIZE
        left_y = inventory_y + INVENTORY_SLOT_SIZE
        shift_x = max(0, -min(top_x, left_x))
        inventory_x += shift_x
        top_x += shift_x
        left_x += shift_x
        self.top_equipment_grid.move(top_x, 0)
        self.left_equipment_grid.move(left_x, left_y)
        self.inventory_grid.move(inventory_x, inventory_y)
        self.inventory_surface.setFixedSize(
            max(
                top_x + self.top_equipment_grid.width(),
                inventory_x + self.inventory_grid.width(),
            ),
            max(
                inventory_y + self.inventory_grid.height(),
                left_y + self.left_equipment_grid.height(),
            ),
        )

    def set_current_tab(self, index: int) -> None:
        if index == 4 and self.tabs.count() == 4:
            index = 3
        if index >= self.tabs.count():
            index = 1
        if 0 <= index < self.tabs.count():
            self.tabs.setCurrentIndex(index)

    def current_tab(self) -> int:
        return self.tabs.currentIndex()

    def set_inventory_page(self, page: int) -> None:
        self.inventory_page = max(0, min(page, self.inventory_page_count - 1))
        start = self.inventory_page * INVENTORY_PAGE_SIZE
        self.inventory_grid.set_items(
            self.inventory_items[start:start + INVENTORY_PAGE_SIZE],
            index_offset=start,
        )
        self._refresh_inventory_page_controls()

    def update_inventory_equipment(
        self,
        inventory: tuple[InventorySlotView, ...],
        equipment: tuple[EquipmentSlotView, ...],
    ) -> None:
        """Refresh item presentation in place after a deterministic item action."""

        self.inventory_items = inventory
        self.inventory_page_count = max(
            1, (len(inventory) + INVENTORY_PAGE_SIZE - 1) // INVENTORY_PAGE_SIZE
        )
        self.inventory_page = min(self.inventory_page, self.inventory_page_count - 1)
        self.top_equipment_grid.set_slots(equipment)
        self.left_equipment_grid.set_slots(equipment)
        self.inventory_grid.equipment = equipment
        self.set_inventory_page(self.inventory_page)
        self._relayout_inventory_surface()

    def current_inventory_page(self) -> int:
        return self.inventory_page

    def _refresh_inventory_page_controls(self) -> None:
        paged = self.inventory_page_count > 1
        self.inventory_previous_button.setVisible(paged)
        self.inventory_next_button.setVisible(paged)
        self.inventory_previous_button.setEnabled(self.inventory_page > 0)
        self.inventory_next_button.setEnabled(
            self.inventory_page + 1 < self.inventory_page_count
        )
