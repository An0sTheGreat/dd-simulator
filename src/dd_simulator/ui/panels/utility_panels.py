"""Static minimap, resources, skills, and inventory previews."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QResizeEvent
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.state import CombatAction, CombatCommand

from dd_simulator.ui.models.presentation import (
    CombatEncounterView,
    LocationSummaryView,
    NpcView,
)
from dd_simulator.ui.panels.common import DashboardPanel, semantic_label
from dd_simulator.ui.panels.summary_panels import (
    _apply_location_catalog_visual,
    _apply_visual,
)
from dd_simulator.ui.widgets.full_click_combo import FullClickComboBox
from dd_simulator.ui.widgets.semantic_button import SemanticButton


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
