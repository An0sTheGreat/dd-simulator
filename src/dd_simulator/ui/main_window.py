"""State-backed interactive main window and in-application navigation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
import ctypes
from pathlib import Path
import math
import re
import sys
import zipfile

from PySide6.QtCore import QPoint, QSize, QThreadPool, QTimer, Qt, Signal
from PySide6.QtGui import QCloseEvent, QGuiApplication
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFrame,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSizePolicy,
    QSplitter,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from dd_simulator.state import (
    CombatAction,
    CombatCommand,
    GameStateError,
    GameStateService,
    ItemAction,
    ItemActionError,
    ItemCommand,
)
from dd_simulator.state.combat import CombatNarrationProvider
from dd_simulator.state.dialogue import DialogueNarrationProvider
from dd_simulator.state.turns import (
    ActionOutcomeProvider,
    ActionResolutionResult,
    SkillCheckResult,
)
from dd_simulator.state.travel import CampResult, TravelNarrationProvider, TravelResult
from dd_simulator.local_model import (
    CharacterRandomizationService,
    LocalModelActionResolver,
    LocalModelClient,
    LocalModelCombatNarrator,
    LocalModelDialogueNarrator,
    LocalModelModelInfo,
    LocalModelTravelNarrator,
    ModelEvaluation,
    ModelEvaluationService,
)
from dd_simulator.local_ai import (
    LOCAL_MODEL_ALIAS,
    LlamaCppRuntime,
    LocalAiConfiguration,
    default_model_directory,
)
from dd_simulator.ui.controllers.ui_controller import UiController
from dd_simulator.ui.models.presentation import DashboardView
from dd_simulator.ui.item_icons import ui_icon
from dd_simulator.ui.panels.campaign_panels import (
    CampaignBrowserPanel,
    CharacterCreationPanel,
)
from dd_simulator.ui.panels.navigation_pages import (
    CharacterSheetPage,
    NavigationPage,
    create_navigation_pages,
)
from dd_simulator.ui.panels.settings_panel import SettingsPanel
from dd_simulator.ui.panels.local_ai_setup_panel import LocalAiSetupPanel
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore
from dd_simulator.ui.audio import (
    DEFAULT_AMBIENCE_VOLUME,
    DEFAULT_MUSIC_VOLUME,
    MusicController,
)
from dd_simulator.ui.services.action_resolution_worker import ActionResolutionTask
from dd_simulator.ui.services.combat_resolution_worker import CombatResolutionTask
from dd_simulator.ui.services.travel_resolution_worker import TravelResolutionTask
from dd_simulator.ui.services.dialogue_resolution_worker import DialogueResolutionTask
from dd_simulator.ui.services.model_evaluation_worker import (
    ModelDiscoveryTask,
    ModelEvaluationTask,
    ModelLoadTask,
)
from dd_simulator.ui.services.randomization_worker import CampaignIntroTask
from dd_simulator.ui.services.local_ai_worker import (
    LocalAiActivationTask,
    RecommendedModelDownloadTask,
)
from dd_simulator.ui.themes.theme_schema import ThemeDefinition
from dd_simulator.ui.widgets.inventory_grid import EquipmentGrid, InventoryGrid
from dd_simulator.ui.widgets.codex_cards import (
    CARD_SLOT_SIZE,
    CARD_SLOT_SPACING,
    CARD_VISIBLE_ROWS,
    CodexCardRow,
    InventoryCard,
    PowersCard,
)
from dd_simulator.ui.widgets.codex_character import (
    PAPERDOLL_HEIGHT,
    CharacterStrip,
    PaperdollPanel,
    SkillDetailList,
)
from dd_simulator.ui.widgets.conversation_view import ConversationView
from dd_simulator.ui.widgets.crafting_page import CraftingPage
from dd_simulator.ui.widgets.scene_view import ElidedLabel, SceneView
from dd_simulator.ui.widgets.semantic_button import SemanticButton
from dd_simulator.ui.widgets.themed_frame import ThemedFrame
from dd_simulator.ui.widgets.combat_rewards_dialog import CombatRewardsDialog
from dd_simulator.ui.widgets.quest_rewards_dialog import QuestRewardsDialog
from dd_simulator.ui.widgets.crafting_results_dialog import CraftingResultsDialog
from dd_simulator.ui.widgets.level_up_dialog import LevelUpDialog
from dd_simulator.ui.widgets.themed_dialog import DraggableTitleBar
from dd_simulator.ui.widgets.world_map import (
    CampConfirmationDialog,
    TravelConfirmationDialog,
    WorldMapPanel,
)


WM_NCHITTEST = 0x0084
HTCLIENT = 1
HTCAPTION = 2
GWL_STYLE = -16
WS_THICKFRAME = 0x00040000
WS_MINIMIZEBOX = 0x00020000
WS_MAXIMIZEBOX = 0x00010000
WS_SYSMENU = 0x00080000
NATIVE_SNAP_STYLE = WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU
# Concept T: codex column about 724 px beside the scene at the 1600 px design width.
CONCEPT_T_SIZES = (724, 876)


class CodexColumn(QWidget):
    """Left column; scales the paperdoll and bag slots together to fit its height."""

    def bind(self, strip, paperdoll, inventory) -> None:  # type: ignore[no-untyped-def]
        self._parts = (strip, paperdoll, inventory)

    def fit(self) -> None:
        parts = getattr(self, "_parts", None)
        if parts is None:
            return
        strip, paperdoll, inventory = parts
        margins = self.layout().contentsMargins()
        spacing = self.layout().spacing()
        card_chrome = inventory.sizeHint().height() - inventory.scroll.height()
        free = (
            self.height() - margins.top() - margins.bottom() - 2 * spacing
            - strip.sizeHint().height() - card_chrome
        )
        # paperdoll height plus five bag rows, both linear in the scale
        rows = CARD_VISIBLE_ROWS * CARD_SLOT_SIZE
        fixed = CARD_VISIBLE_ROWS * CARD_SLOT_SPACING - CARD_SLOT_SPACING
        scale = math.floor(20 * (free - fixed) / (PAPERDOLL_HEIGHT + rows)) / 20
        paperdoll.set_scale(scale)
        inventory.set_scale(scale)

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        self.fit()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self.fit()


class SkillCheckPopup(QDialog):
    """Themed transient result; Qt.Popup supplies click-outside dismissal."""

    def __init__(self, result: SkillCheckResult, parent: QWidget) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setObjectName("skillCheckPopup")
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 16)
        header = QHBoxLayout()
        title = QLabel(f"{result.name.upper()} CHECK")
        title.setObjectName("skillCheckTitle")
        header.addWidget(title, 1)
        close_button = SemanticButton("×", role="secondary")
        close_button.setObjectName("skillCheckCloseButton")
        close_button.setFixedSize(30, 30)
        close_button.clicked.connect(self.close)
        header.addWidget(close_button)
        layout.addLayout(header)
        outcome = QLabel("SUCCESS" if result.success else "FAILURE")
        outcome.setObjectName("skillCheckOutcome")
        outcome.setProperty("checkState", "success" if result.success else "failure")
        outcome.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(outcome)
        layout.addWidget(QLabel(
            f"Player roll: {result.roll}\n"
            f"Modifier: {result.modifier:+d}\n"
            f"Total: {result.total}\n"
            f"Required to pass: {result.target}"
        ))

    def show_centered(self, parent: QWidget) -> None:
        self.adjustSize()
        center = parent.mapToGlobal(parent.rect().center())
        self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        self.show()
        self.raise_()


class MainWindow(QMainWindow):
    """Resizable, themed campaign shell and Version 1 adventure dashboard."""

    theme_requested = Signal(str)
    font_size_requested = Signal(int)

    def __init__(
        self,
        themes: Iterable[ThemeDefinition],
        dashboard: DashboardView,
        *,
        controller: UiController | None = None,
        preferences_store: UiPreferencesStore | None = None,
        game_state_service: GameStateService | None = None,
        character_randomizer: CharacterRandomizationService | None = None,
        action_resolver: ActionOutcomeProvider | None = None,
        combat_narrator: CombatNarrationProvider | None = None,
        travel_narrator: TravelNarrationProvider | None = None,
        dialogue_narrator: DialogueNarrationProvider | None = None,
        lm_client: LocalModelClient | None = None,
        model_evaluator: ModelEvaluationService | None = None,
        local_ai_configuration: LocalAiConfiguration | None = None,
        local_ai_runtime: LlamaCppRuntime | None = None,
        config_dir: Path | None = None,
        start_on_campaigns: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("mainWindow")
        self.setWindowTitle("D&D Simulator - Release 28")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMinimizeButtonHint, True)
        self.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        self.resize(1600, 900)
        self.setMinimumSize(1280, 720)
        self._native_snap_style_applied = False

        self._themes = list(themes)
        self.dashboard = dashboard
        self.controller = controller or UiController(self)
        self.preferences_store = preferences_store
        self.game_state_service = game_state_service
        self.character_randomizer = character_randomizer
        self.action_resolver = action_resolver
        self.combat_narrator = combat_narrator
        self.travel_narrator = travel_narrator
        self.dialogue_narrator = dialogue_narrator
        self.lm_client = lm_client
        self.model_evaluator = model_evaluator
        self._local_ai_setup_required = local_ai_configuration is not None
        self.local_ai_configuration = local_ai_configuration or LocalAiConfiguration(
            model_directory=str(default_model_directory())
        )
        self.local_ai_runtime = local_ai_runtime or LlamaCppRuntime(
            (config_dir or Path.cwd()) / "logs"
        )
        self.config_dir = Path(config_dir or Path.cwd())
        self._action_task: ActionResolutionTask | None = None
        self._combat_task: CombatResolutionTask | None = None
        self._travel_task: TravelResolutionTask | None = None
        self._dialogue_task: DialogueResolutionTask | None = None
        self._model_discovery_task: ModelDiscoveryTask | None = None
        self._model_evaluation_task: ModelEvaluationTask | None = None
        self._model_load_task: ModelLoadTask | None = None
        self._campaign_intro_task: CampaignIntroTask | None = None
        self._local_ai_download_task: RecommendedModelDownloadTask | None = None
        self._local_ai_activation_task: LocalAiActivationTask | None = None
        self._models_scanned = False
        self._discovered_models: tuple[LocalModelModelInfo, ...] = ()
        self.startup_readiness = "Startup checks pending."
        self._reward_dialog: CombatRewardsDialog | None = None
        self._quest_reward_dialog: QuestRewardsDialog | None = None
        self._crafting_result_dialog: CraftingResultsDialog | None = None
        self._level_up_dialog: LevelUpDialog | None = None
        self._skill_check_popup: SkillCheckPopup | None = None
        self._selected_inventory_item_id: str | None = None
        self.font_size_preference = 100
        self.reduced_motion_preference = False
        self.music_volume_preference = DEFAULT_MUSIC_VOLUME
        self.ambience_volume_preference = DEFAULT_AMBIENCE_VOLUME
        self.audio_muted_preference = False
        self.music = MusicController(self)
        self._audio_save_timer = QTimer(self)
        self._audio_save_timer.setSingleShot(True)
        self._audio_save_timer.setInterval(400)
        self._audio_save_timer.timeout.connect(self.save_ui_preferences)
        self._resource_animation_starts: dict[str, int] = {}
        self.current_page = "dashboard"
        self._dialog_dim_depth = 0
        self._last_turn_shown: int | None = None
        self.page_indices: dict[str, int] = {}
        self.theme_selector = QComboBox()
        self.theme_selector.setObjectName("themeSelector")
        self.theme_selector.setProperty("nativeTitleBarInteractive", True)
        self.theme_selector.setToolTip("Switch the interface theme")
        for theme in self._themes:
            self.theme_selector.addItem(theme.name, theme.theme_id)
        self.theme_selector.currentIndexChanged.connect(self._on_theme_changed)

        self.controller.navigation_requested.connect(self._show_navigation)
        self.controller.status_message.connect(self._show_status_message)
        self.controller.context_action_requested.connect(self._handle_context_action)
        self.controller.action_submitted.connect(self._handle_player_action_submission)

        self.root = QWidget()
        self.root.setObjectName("applicationRoot")
        self.root_layout = QVBoxLayout(self.root)
        self.root_layout.setContentsMargins(8, 8, 8, 8)
        self.root_layout.setSpacing(8)
        self.root_layout.addWidget(self._build_header())
        self._build_content_stack()
        self.setCentralWidget(self.root)

        self.dialog_dimmer = QFrame(self)
        self.dialog_dimmer.setObjectName("dialogDimmer")
        self.dialog_dimmer.setStyleSheet("background-color: rgba(0, 0, 0, 170);")
        self.dialog_dimmer.hide()

        self.statusBar().setObjectName("applicationStatusBar")
        self.statusBar().setSizeGripEnabled(True)
        self.statusBar().showMessage(
            "Ready - deterministic game systems and local AI narration available"
        )
        self._load_ui_preferences()
        if self._local_ai_setup_required and not self.local_ai_configuration.usable():
            self._show_navigation("local_ai_setup")
        elif start_on_campaigns and self.game_state_service is not None:
            self._show_navigation("settings")
        if self.game_state_service is not None:
            QTimer.singleShot(0, self._show_pending_combat_reward)
            QTimer.singleShot(0, self._show_pending_quest_reward)
            QTimer.singleShot(0, self._show_pending_crafting_result)
            QTimer.singleShot(400, self._show_pending_level_up)
        self.music.update(self.current_page, self.dashboard)

    def _build_content_stack(self) -> None:
        self.page_indices = {}
        self.content_stack = QStackedWidget()
        self.content_stack.setObjectName("mainContentStack")
        self.concept_splitter = self._build_concept_t()
        self.page_indices["dashboard"] = self.content_stack.addWidget(self.concept_splitter)
        self.page_indices["crafting"] = self.content_stack.addWidget(self._build_crafting_page())

        self.navigation_pages = create_navigation_pages(self.dashboard)
        for target, page in self.navigation_pages.items():
            page.back_requested.connect(lambda name="dashboard": self.controller.navigate(name))
            self.page_indices[target] = self.content_stack.addWidget(page)
        self.navigation_pages["character_sheet"].crafting_requested.connect(
            lambda: self.controller.navigate("crafting")
        )

        self.local_ai_setup_panel = LocalAiSetupPanel(self.local_ai_configuration)
        self.local_ai_setup_panel.configuration_requested.connect(
            self._configure_local_ai
        )
        self.local_ai_setup_panel.cancellation_requested.connect(
            lambda: self.controller.navigate("settings")
        )
        self.local_ai_setup_panel.operation_cancel_requested.connect(
            self._cancel_local_ai_operation
        )
        self.page_indices["local_ai_setup"] = self.content_stack.addWidget(
            self.local_ai_setup_panel
        )

        self.settings_panel = SettingsPanel(self._themes)
        self.settings_panel.show_startup_status(self.startup_readiness)
        self._models_scanned = False
        self.settings_panel.back_requested.connect(lambda: self.controller.navigate("dashboard"))
        self.settings_panel.reset_requested.connect(self._reset_ui_preferences)
        self.settings_panel.theme_requested.connect(self.theme_requested)
        self.settings_panel.font_size_requested.connect(self._on_font_size_changed)
        self.settings_panel.reduced_motion_requested.connect(
            self._on_reduced_motion_changed
        )
        self.settings_panel.select_reduced_motion(self.reduced_motion_preference)
        self.settings_panel.audio_requested.connect(self._on_audio_changed)
        self._apply_audio_preferences()
        self.settings_panel.checkpoint_create_requested.connect(self._create_checkpoint)
        self.settings_panel.checkpoint_load_requested.connect(self._load_checkpoint)
        self.settings_panel.repair_requested.connect(self._inspect_and_repair_campaign)
        self.settings_panel.replay_requested.connect(self._verify_checkpoint_replay)
        self.settings_panel.model_refresh_requested.connect(self._refresh_lm_models)
        self.settings_panel.model_requested.connect(self._select_lm_model)
        self.settings_panel.model_load_requested.connect(self._load_lm_model)
        self.settings_panel.model_evaluation_requested.connect(
            self._run_model_evaluation
        )
        self.settings_panel.local_ai_setup_requested.connect(
            lambda: self.controller.navigate("local_ai_setup")
        )
        self.settings_panel.diagnostic_export_requested.connect(
            self._export_diagnostic_logs
        )
        if self.game_state_service is not None:
            self.campaign_browser = CampaignBrowserPanel(
                self.game_state_service.list_campaigns()
            )
            self.campaign_browser.new_requested.connect(
                self._start_custom_character_creation
            )
            self.campaign_browser.preset_requested.connect(
                self._start_preset_character_creation
            )
            self.campaign_browser.load_requested.connect(self._load_campaign)
            self.campaign_browser.delete_requested.connect(self._delete_campaign)
        # Title row like every page; the two card columns scroll beneath it.
        settings_navigation = NavigationPage(
            "settingsNavigationPage", "SETTINGS", "Application, model, and campaign controls.",
            back=self.settings_panel.back_button,
        )
        self.settings_page = QWidget()
        self.settings_page.setObjectName("settingsPage")
        settings_columns_layout = QHBoxLayout(self.settings_page)
        settings_columns_layout.setContentsMargins(0, 0, 0, 0)
        settings_columns_layout.setSpacing(8)
        self.settings_panel.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )
        settings_columns_layout.addWidget(self.settings_panel, 1)
        if self.game_state_service is not None:
            self.campaign_browser.setSizePolicy(
                QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
            )
            settings_columns_layout.addWidget(self.campaign_browser, 1)
        else:
            settings_columns_layout.addStretch(1)
        self.settings_scroll = QScrollArea()
        self.settings_scroll.setObjectName("settingsScrollArea")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.settings_scroll.setWidget(self.settings_page)
        settings_navigation.layout.addWidget(self.settings_scroll, 1)
        self.page_indices["settings"] = self.content_stack.addWidget(settings_navigation)

        if self.game_state_service is not None:
            self.character_creation_panel = CharacterCreationPanel(self.character_randomizer)
            self.character_creation_panel.cancelled.connect(
                lambda: self.controller.navigate("settings")
            )
            self.character_creation_panel.completed.connect(
                self._complete_character_creation
            )
            self.character_creation_panel.model_refresh_requested.connect(
                self._refresh_lm_models
            )
            self.character_creation_panel.model_requested.connect(self._select_lm_model)
            self.character_creation_panel.model_load_requested.connect(self._load_lm_model)
            self.character_creation_panel.model_evaluation_requested.connect(
                self._run_model_evaluation
            )
            self.page_indices["character_creation"] = self.content_stack.addWidget(
                self.character_creation_panel
            )

        self.root_layout.insertWidget(1, self.content_stack, 1)
        self._connect_dashboard_interactions()

    def _connect_dashboard_interactions(self) -> None:
        grid = self.scene_view.choice_grid
        self.controller.validation_failed.connect(grid.show_validation_error)
        self.scene_view.submission_requested.connect(self.controller.submit_player_action)
        self.scene_view.cancellation_requested.connect(self._cancel_action_resolution)
        self.scene_view.retry_requested.connect(self._start_action_resolution)
        self.scene_view.combat_action_requested.connect(self._resolve_combat_action)
        self.scene_view.navigation_requested.connect(self.controller.navigate)
        self.powers_card.action_activated.connect(self._activate_power)
        self.powers_card.rest_requested.connect(
            lambda: self._resolve_combat_action(CombatCommand(CombatAction.RECOVER))
        )
        self.conversation_view.older_requested.connect(self._load_older_messages)
        map_page = self.navigation_pages.get("map")
        if map_page is not None:
            world_map = map_page.findChild(WorldMapPanel)
            if world_map is not None:
                world_map.travel_requested.connect(self._request_map_travel)
                world_map.camp_requested.connect(self._request_map_camp)
        people_page = self.navigation_pages.get("people")
        if people_page is not None and hasattr(people_page, "dialogue_requested"):
            people_page.dialogue_requested.connect(self._resolve_npc_dialogue)
        if people_page is not None and hasattr(people_page, "trade_requested"):
            people_page.trade_requested.connect(self._request_trade)
        self._connect_item_interactions()

    def _start_custom_character_creation(self) -> None:
        self.character_creation_panel.begin_creation()
        self.controller.navigate("character_creation")

    def _start_preset_character_creation(self, preset_id: str) -> None:
        self.character_creation_panel.begin_creation(preset_id)
        self.controller.navigate("character_creation")

    def _request_trade(self, npc_id: str, action: str, item_id: str) -> None:
        if self.game_state_service is None:
            self._show_status_message("Trading requires a state-backed campaign")
            return
        try:
            quote = self.game_state_service.quote_trade(npc_id, action, item_id)
        except GameStateError as exc:
            self._show_status_message(str(exc))
            return
        verb = {"buy": "Buy", "sell": "Sell", "barter": "Barter for"}.get(
            action, action.title()
        )
        answer = QMessageBox.question(
            self,
            "Confirm Trade",
            f"{verb} {quote.item_name} for {quote.total_price} gold?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._show_status_message("Trade cancelled")
            return
        try:
            result = self.game_state_service.complete_trade(npc_id, action, item_id)
            dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._show_status_message(str(exc))
            return
        self._reload_dashboard(dashboard, target_page="people")
        self._show_status_message(
            f"{result.summary} {result.remaining_currency} gold remains."
        )

    def _resolve_npc_dialogue(self, npc_id: str, response: str) -> None:
        if self.game_state_service is None:
            self._show_status_message("NPC dialogue requires a state-backed campaign")
            return
        if self._dialogue_task is not None or self._action_task is not None or self._combat_task is not None:
            self._show_status_message("Another game action is already being resolved")
            return
        task = DialogueResolutionTask(
            self.game_state_service, npc_id, response, self.dialogue_narrator
        )
        self._dialogue_task = task
        self._show_status_message("Resolving conversation with the local model...")
        people_page = self.navigation_pages.get("people")
        if people_page is not None and hasattr(people_page, "show_dialogue_status"):
            people_page.show_dialogue_status("Waiting for the local model to answer...")
        task.signals.succeeded.connect(
            lambda result, current=task: self._dialogue_resolution_succeeded(current, result)
        )
        task.signals.failed.connect(
            lambda message, current=task: self._dialogue_resolution_failed(current, message)
        )
        task.signals.finished.connect(
            lambda current=task: self._dialogue_resolution_finished(current)
        )
        QThreadPool.globalInstance().start(task)

    def _dialogue_resolution_succeeded(self, task: DialogueResolutionTask, result: object) -> None:
        if task is not self._dialogue_task or self.game_state_service is None:
            return
        try:
            dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._show_status_message(str(exc))
            return
        self._reload_dashboard(dashboard, target_page="people")
        people_page = self.navigation_pages.get("people")
        if people_page is not None and hasattr(people_page, "highlight_latest_turn"):
            people_page.highlight_latest_turn(  # type: ignore[attr-defined]
                reduced_motion=self.reduced_motion_preference
            )
        detail = getattr(result, "check_summary", "") or f"Relationship {getattr(result, 'relationship_delta', 0):+d}"
        updates = " ".join(getattr(result, "quest_updates", ()))
        self._show_status_message(f"{detail} {updates}".strip())
        self._show_skill_check(getattr(result, "skill_check", None))

    def _dialogue_resolution_failed(self, task: DialogueResolutionTask, message: str) -> None:
        if task is self._dialogue_task:
            self._show_status_message(message)
            people_page = self.navigation_pages.get("people")
            if people_page is not None and hasattr(people_page, "show_dialogue_status"):
                people_page.show_dialogue_status(message, error=True)

    def _dialogue_resolution_finished(self, task: DialogueResolutionTask) -> None:
        if task is self._dialogue_task:
            self._dialogue_task = None

    def _request_map_travel(self, route_id: str) -> None:
        if self.game_state_service is None or self.dashboard.world_map is None:
            self._show_status_message("Travel requires a state-backed campaign")
            return
        route = next(
            (value for value in self.dashboard.world_map.routes if value.id == route_id),
            None,
        )
        if route is None:
            self._show_status_message("That route is no longer available")
            return
        dialog = TravelConfirmationDialog(route, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._show_status_message("Travel cancelled")
            return
        self._start_travel_task(route_id=route_id)

    def _request_map_camp(self, duration_minutes: int) -> None:
        if self.game_state_service is None:
            self._show_status_message("Camping requires a state-backed campaign")
            return
        dialog = CampConfirmationDialog(duration_minutes, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._show_status_message("Camp cancelled")
            return
        self._start_travel_task(camp_duration=duration_minutes)

    def _start_travel_task(
        self,
        *,
        route_id: str | None = None,
        camp_duration: int | None = None,
    ) -> None:
        if self.game_state_service is None:
            return
        if self._travel_task is not None or self._combat_task is not None or self._action_task is not None or self._dialogue_task is not None:
            self._show_status_message("Another game action is already being resolved")
            return
        task = TravelResolutionTask(
            self.game_state_service,
            route_id=route_id,
            camp_duration=camp_duration,
            narrator=self.travel_narrator,
        )
        self._travel_task = task
        self._show_status_message(
            "Resolving journey..." if route_id is not None else "Making camp..."
        )
        task.signals.succeeded.connect(
            lambda result, current=task: self._travel_resolution_succeeded(current, result)
        )
        task.signals.failed.connect(
            lambda message, current=task: self._travel_resolution_failed(current, message)
        )
        task.signals.finished.connect(
            lambda current=task: self._travel_resolution_finished(current)
        )
        QThreadPool.globalInstance().start(task)

    def _travel_resolution_succeeded(
        self, task: TravelResolutionTask, result: object
    ) -> None:
        if task is not self._travel_task or self.game_state_service is None:
            return
        try:
            dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._travel_resolution_failed(task, str(exc))
            return
        if isinstance(result, TravelResult):
            self._reload_dashboard(
                dashboard,
                target_page="dashboard" if result.encounter_required else "map",
            )
            updates = " ".join(result.quest_updates)
        elif isinstance(result, CampResult):
            self._reload_dashboard(dashboard, target_page="map")
            updates = " ".join(result.deadline_updates)
        else:
            self._show_status_message("Travel returned an unexpected result")
            return
        self._show_status_message(
            result.summary + (f" {updates}" if updates else "")
        )

    def _travel_resolution_failed(
        self, task: TravelResolutionTask, message: str
    ) -> None:
        if task is self._travel_task:
            self._show_status_message(message)

    def _travel_resolution_finished(self, task: TravelResolutionTask) -> None:
        if task is self._travel_task:
            self._travel_task = None

    def _build_header(self) -> QFrame:
        header = DraggableTitleBar(maximizable=True)
        self.title_bar = header
        header.setObjectName("topHeader")
        header.setProperty("role", "header")
        header.setFixedHeight(54)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 6, 18, 6)

        left = QWidget()
        left.setObjectName("titleBarLeft")
        left.setFixedWidth(320)
        left_layout = QHBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        phase = QLabel("RELEASE 28")
        phase.setObjectName("phaseLabel")
        phase.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        left_layout.addWidget(phase)
        left_layout.addStretch(1)

        title_center = QWidget()
        title_center.setObjectName("titleBarCenter")
        title_layout = QHBoxLayout(title_center)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)
        # The ornaments give up their 150 px before the title starts to elide.
        title_ornament_left = QLabel()
        title_ornament_left.setObjectName("titleOrnamentLeft")
        title_ornament_left.setFixedHeight(24)
        title_ornament_left.setMaximumWidth(150)
        title_ornament_left.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        title_layout.addWidget(title_ornament_left, 1)
        self.application_title = ElidedLabel("", "applicationTitle", tooltip_on_self=True)
        self.application_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preset_campaign_badge = QLabel("- PRESET CAMPAIGN")
        self.preset_campaign_badge.setObjectName("presetCampaignBadge")
        self.preset_campaign_badge.setProperty("textRole", "muted")
        self.preset_campaign_badge.setVisible(False)
        title_group = QWidget()
        title_group.setObjectName("campaignTitleGroup")
        title_group_layout = QHBoxLayout(title_group)
        title_group_layout.setContentsMargins(0, 0, 0, 0)
        title_group_layout.setSpacing(8)
        title_group_layout.addStretch(1)
        title_group_layout.addWidget(self.application_title)
        title_group_layout.addWidget(self.preset_campaign_badge)
        title_group_layout.addStretch(1)
        title_layout.addWidget(title_group)
        title_ornament_right = QLabel()
        title_ornament_right.setObjectName("titleOrnamentRight")
        title_ornament_right.setFixedHeight(24)
        title_ornament_right.setMaximumWidth(150)
        title_ornament_right.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        title_layout.addWidget(title_ornament_right, 1)

        right = QWidget()
        right.setObjectName("titleBarRight")
        right.setFixedWidth(320)
        right_layout = QHBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)
        right_layout.addStretch(1)
        theme_label = QLabel("Theme")
        theme_label.setObjectName("themeLabel")
        theme_label.setBuddy(self.theme_selector)
        right_layout.addWidget(theme_label)
        right_layout.addWidget(self.theme_selector)
        for text, name, action in (
            ("−", "windowMinimizeButton", self.showMinimized),
            ("□", "windowMaximizeButton", self._toggle_maximized),
            ("×", "windowCloseButton", self.close),
        ):
            button = SemanticButton(text, role="secondary", object_name=name)
            button.setProperty("nativeTitleBarInteractive", True)
            button.setAccessibleName(name.removeprefix("window").removesuffix("Button"))
            button.setFixedSize(30, 28)
            button.clicked.connect(action)
            right_layout.addWidget(button)

        layout.addWidget(left)
        layout.addWidget(title_center, 1)
        layout.addWidget(right)
        self._update_application_title()
        return header

    def _update_application_title(self) -> None:
        campaign_name = self.dashboard.campaign_name.strip()
        visible_title = campaign_name or "D&D SIMULATOR"
        self.application_title.set_full_text(visible_title)
        self.preset_campaign_badge.setVisible(False)
        self.setWindowTitle(campaign_name or "D&D Simulator")

    def _toggle_maximized(self) -> None:
        self.showNormal() if self.isMaximized() else self.showMaximized()

    @staticmethod
    def _uses_native_windows_windowing() -> bool:
        return sys.platform == "win32" and QGuiApplication.platformName() == "windows"

    def _apply_native_snap_style(self) -> None:
        """Restore the Win32 styles required for Aero Snap on a frameless Qt window."""

        if self._native_snap_style_applied or not self._uses_native_windows_windowing():
            return
        user32 = ctypes.windll.user32
        get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
        get_style.restype = ctypes.c_ssize_t
        set_style.restype = ctypes.c_ssize_t
        hwnd = ctypes.c_void_p(int(self.winId()))
        current_style = int(get_style(hwnd, GWL_STYLE))
        set_style(hwnd, GWL_STYLE, current_style | NATIVE_SNAP_STYLE)
        frame_changed = 0x0020
        no_move = 0x0002
        no_size = 0x0001
        no_z_order = 0x0004
        no_activate = 0x0010
        self._native_snap_style_applied = bool(
            user32.SetWindowPos(
                hwnd,
                None,
                0,
                0,
                0,
                0,
                frame_changed | no_move | no_size | no_z_order | no_activate,
            )
        )

    def _native_title_hit_test(self, window_position: QPoint) -> int | None:
        """Return a native caption hit only for non-interactive header content."""

        header_position = self.title_bar.mapFrom(self, window_position)
        if not self.title_bar.rect().contains(header_position):
            return None
        child = self.title_bar.childAt(header_position)
        while child is not None and child is not self.title_bar:
            if child.property("nativeTitleBarInteractive"):
                return HTCLIENT
            child = child.parentWidget()
        return HTCAPTION

    def nativeEvent(self, event_type, message):  # type: ignore[no-untyped-def]
        if self._uses_native_windows_windowing() and bytes(event_type) == b"windows_generic_MSG":
            from ctypes import wintypes

            native_message = wintypes.MSG.from_address(int(message))
            if native_message.message == WM_NCHITTEST:
                packed_position = int(native_message.lParam)
                screen_x = ctypes.c_short(packed_position & 0xFFFF).value
                screen_y = ctypes.c_short((packed_position >> 16) & 0xFFFF).value
                hit = self._native_title_hit_test(
                    self.mapFromGlobal(QPoint(screen_x, screen_y))
                )
                if hit is not None:
                    return True, hit
        return super().nativeEvent(event_type, message)

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().showEvent(event)
        self._apply_native_snap_style()

    def set_dialog_dimmed(self, active: bool) -> None:
        self._dialog_dim_depth = max(0, self._dialog_dim_depth + (1 if active else -1))
        if self._dialog_dim_depth:
            self.dialog_dimmer.setGeometry(self.rect())
            self.dialog_dimmer.show()
            self.dialog_dimmer.raise_()
        else:
            self.dialog_dimmer.hide()

    def resizeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        super().resizeEvent(event)
        if hasattr(self, "dialog_dimmer"):
            self.dialog_dimmer.setGeometry(self.rect())

    def _build_concept_t(self) -> QSplitter:
        """Codex column (character, paperdoll and skills, cards) beside the scene."""

        dashboard = self.dashboard
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setObjectName("conceptTSplitter")
        splitter.setChildrenCollapsible(False)
        codex = CodexColumn()
        codex.setObjectName("conceptTCodex")
        layout = QVBoxLayout(codex)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        self.character_strip = CharacterStrip(dashboard)
        layout.addWidget(self.character_strip)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.paperdoll_panel = PaperdollPanel(
            dashboard.player, dashboard.equipment, attack_bonus=dashboard.player.attack_bonus
        )
        self.skill_detail_list = SkillDetailList(dashboard.skills)
        row.addWidget(self.paperdoll_panel)
        row.addWidget(self.skill_detail_list, 1)
        layout.addLayout(row)
        self.inventory_card = InventoryCard(
            dashboard.inventory,
            capacity=dashboard.inventory_capacity,
            equipment=dashboard.equipment,
        )
        self.powers_card = PowersCard(dashboard.abilities, dashboard.spells)
        self.codex_card_row = CodexCardRow(self.inventory_card, self.powers_card)
        layout.addWidget(self.codex_card_row, 1)
        codex.bind(self.character_strip, self.paperdoll_panel, self.inventory_card)

        self.scene_view = SceneView(
            dashboard.location,
            dashboard.quest,
            dashboard.narrative.suggested_actions,
            quest_list=dashboard.quest_list,
            combat=dashboard.combat,
            actor=(dashboard.player.name.split() or [None])[0],
        )
        self.scene_view.set_clock(dashboard.location.day, dashboard.location.turn_number)
        self.conversation_view = ConversationView(
            reduced_motion=self.reduced_motion_preference
        )
        self._show_conversation(dashboard.narrative)
        self.scene_view.set_conversation(self.conversation_view)
        combat = dashboard.combat
        self.powers_card.rest_button.setVisible(combat is None or combat.status != "active")

        splitter.addWidget(codex)
        splitter.addWidget(self.scene_view)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes(list(CONCEPT_T_SIZES))
        return splitter

    def _show_conversation(self, narrative) -> None:  # type: ignore[no-untyped-def]
        """First load shows the transcript; after a commit the new turns arrive via append_turn."""

        # ponytail: the last shown turn is not reset when another campaign loads, so its
        # later turns get the new-turn emphasis once; key it by campaign if that matters.
        last = self._last_turn_shown
        messages = tuple(narrative.messages)
        shown = tuple(m for m in messages if last is None or m.turn_number <= last)
        fresh = tuple(m for m in messages if last is not None and m.turn_number > last)
        self.conversation_view.set_messages(shown, narrative.has_older_messages)
        if fresh:
            self.conversation_view.append_turn(fresh)
        self._last_turn_shown = max((m.turn_number for m in messages), default=0)

    def _load_older_messages(self, before_turn: int) -> None:
        service = self.game_state_service
        campaign_id = service.campaigns.active_campaign_id() if service is not None else None
        if not campaign_id:
            self.conversation_view.older_load_failed()
            return
        try:
            older = service.older_messages(campaign_id, before_turn)
            first = min((m.turn_number for m in older), default=before_turn)
            has_older = bool(older) and bool(service.older_messages(campaign_id, first, 1))
        except GameStateError as exc:
            self.conversation_view.older_load_failed()
            self._show_status_message(str(exc))
            return
        self.conversation_view.prepend_messages(older, has_older)

    def _build_crafting_page(self) -> QWidget:
        # Temporary home until the crafting move into the Character Sheet.
        page = NavigationPage(
            "craftingNavigationPage",
            "CRAFTING RECIPES",
            "Ingredients and tool uses are consumed only after a successful deterministic attempt.",
        )
        # The page's own secondary back button, on the title row, returns to the sheet.
        back = page.back_button
        back.setText("Back")
        back.setObjectName("craftingBackButton")
        back.setToolTip("Return to the character sheet")
        page.back_requested.connect(lambda: self.controller.navigate("character_sheet"))
        self.crafting_page = CraftingPage(self.dashboard.crafting_recipes)
        self.crafting_page.craft_requested.connect(self._request_crafting)
        page.layout.addWidget(self.crafting_page, 1)
        return page

    def _activate_power(self, key: str) -> None:
        combat = self.dashboard.combat
        if combat is None or combat.status != "active":
            self._show_status_message("Abilities and spells are used during combat")
            return
        action = (
            CombatAction.SPELL
            if any(spell.key == key for spell in self.dashboard.spells)
            else CombatAction.ABILITY
        )
        self._resolve_combat_action(
            CombatCommand(
                action, target_id=self.scene_view.choice_grid.target_id, ability_key=key
            )
        )

    def _set_combat_pending(self, pending: bool) -> None:
        self.powers_card.setEnabled(not pending)
        if pending:
            for button in self.scene_view.choice_grid.choice_buttons:
                button.setEnabled(False)
        else:
            self.scene_view.set_combat(self.dashboard.combat)

    def _connect_item_interactions(self) -> None:
        for grid in self.content_stack.findChildren(InventoryGrid):
            grid.selection_changed.connect(
                self._inventory_selection_changed
            )
            grid.context_action_requested.connect(
                lambda index, action: self.controller.request_context_action(
                    "inventory",
                    index,
                    action,
                )
            )
            grid.move_requested.connect(self._move_inventory_item)
            grid.equipment_drop_requested.connect(
                self._unequip_equipment_to_inventory
            )
        for grid in self.content_stack.findChildren(EquipmentGrid):
            self._connect_equipment_grid(grid)
        self.inventory_card.auto_sort_requested.connect(self._auto_sort_inventory)

    def _connect_equipment_grid(self, grid: EquipmentGrid) -> None:
        grid.selection_changed.connect(
            lambda index: self.controller.select_item("equipment", index)
        )
        grid.context_action_requested.connect(
            lambda index, action: self.controller.request_context_action(
                "equipment",
                index,
                action,
            )
        )
        grid.inventory_drop_requested.connect(self._equip_inventory_to_equipment)

    def _bag_item(self, position: int):  # type: ignore[no-untyped-def]
        return next(
            (item for item in self.dashboard.inventory if item.position == position), None
        )

    def _request_crafting(self, recipe_id: str) -> None:
        if self.game_state_service is None:
            self._show_status_message("Crafting requires a state-backed campaign")
            return
        recipe = next(
            (value for value in self.dashboard.crafting_recipes if value.id == recipe_id), None
        )
        if recipe is None or not recipe.available:
            self._show_status_message(
                "That recipe is unavailable" if recipe is None else recipe.unavailable_reason
            )
            return
        ingredients = ", ".join(
            f"{value.required} x {value.name}" for value in recipe.ingredients
        ) or "no ingredients"
        answer = QMessageBox.question(
            self,
            "Confirm Crafting",
            f"Attempt {recipe.name}?\n\nRequires {ingredients}.\n"
            "Materials and tool uses are consumed only on success.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self._show_status_message("Crafting cancelled")
            return
        try:
            result = self.game_state_service.craft_recipe(recipe_id)
            dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._show_status_message(str(exc))
            return
        self._reload_dashboard(dashboard, target_page="crafting")
        self._show_status_message(result.summary)
        self._show_pending_crafting_result()

    def _inventory_selection_changed(self, index: int) -> None:
        item = self._bag_item(index)
        if item is not None:
            self._selected_inventory_item_id = item.id
        self.controller.select_item("inventory", index)

    def _move_inventory_item(self, source: int, destination: int) -> None:
        if self.game_state_service is None:
            return
        try:
            summary = self.game_state_service.move_inventory_item(source, destination)
            dashboard = self.game_state_service.load_active_dashboard()
        except (GameStateError, ItemActionError) as exc:
            self._show_status_message(str(exc))
            return
        self._refresh_item_views(dashboard)
        self._show_status_message(summary)

    def _unequip_equipment_to_inventory(self, source: int, destination: int) -> None:
        if self.game_state_service is None:
            return
        try:
            result = self.game_state_service.execute_item_command(
                ItemCommand(ItemAction.UNEQUIP, source, destination)
            )
            dashboard = self.game_state_service.load_active_dashboard()
        except (GameStateError, ItemActionError) as exc:
            self._show_status_message(str(exc))
            return
        self._refresh_item_views(dashboard)
        self._show_status_message(
            f"{result.summary} Placed in inventory slot {destination + 1}."
        )

    def _equip_inventory_to_equipment(self, source: int, destination: int) -> None:
        if self.game_state_service is None:
            return
        try:
            result = self.game_state_service.execute_item_command(
                ItemCommand(ItemAction.EQUIP, source, destination)
            )
            dashboard = self.game_state_service.load_active_dashboard()
        except (GameStateError, ItemActionError) as exc:
            self._show_status_message(str(exc))
            return
        self._selected_inventory_item_id = None
        self._refresh_item_views(dashboard)
        self._show_status_message(result.summary)

    def _auto_sort_inventory(self, sort_mode: str = "default") -> None:
        if self.game_state_service is None:
            return
        try:
            summary = self.game_state_service.auto_sort_inventory(sort_mode)
            dashboard = self.game_state_service.load_active_dashboard()
        except (GameStateError, ItemActionError) as exc:
            self._show_status_message(str(exc))
            return
        self._refresh_item_views(dashboard)
        self._show_status_message(summary)

    def _handle_context_action(self, collection: str, index: int, action: str) -> None:
        if action == "inspect":
            item = self._bag_item(index) if collection == "inventory" else None
            if item is not None:
                detail = item.description or item.name or "Empty inventory slot"
                self._show_status_message(f"{item.name or 'Empty'}: {detail}")
            elif collection == "equipment" and 0 <= index < len(self.dashboard.equipment):
                slot = self.dashboard.equipment[index]
                self._show_status_message(
                    f"{slot.slot_name}: {slot.item_name or 'empty'}"
                    + (f" ({slot.condition})" if slot.condition else "")
                )
            return
        if self.game_state_service is None:
            self._show_status_message("Inventory mutations require a state-backed campaign")
            return
        allowed = {
            ("inventory", "use"): ItemAction.USE,
            ("inventory", "equip"): ItemAction.EQUIP,
            ("inventory", "drop"): ItemAction.DROP,
            ("equipment", "unequip"): ItemAction.UNEQUIP,
        }
        item_action = allowed.get((collection, action))
        if item_action is None:
            self._show_status_message(f"{action.title()} is not valid for {collection}")
            return
        if item_action is ItemAction.DROP:
            item = self._bag_item(index)
            if item is None:
                self._show_status_message("That inventory slot is empty.")
                return
            answer = QMessageBox.question(
                self,
                "Drop item",
                f"Drop the entire {item.name} stack? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                self._show_status_message("Drop cancelled")
                return
        return_page = self.current_page
        try:
            result = self.game_state_service.execute_item_command(
                ItemCommand(item_action, index)
            )
            dashboard = self.game_state_service.load_active_dashboard()
        except (GameStateError, ItemActionError, IndexError) as exc:
            self._show_status_message(str(exc))
            return
        if item_action in {ItemAction.EQUIP, ItemAction.UNEQUIP}:
            self._refresh_item_views(dashboard)
        else:
            self._reload_dashboard(dashboard, target_page=return_page)
        self._show_status_message(result.summary)

    def _handle_player_action_submission(self, action: str) -> None:
        if self.action_resolver is None or self.game_state_service is None:
            self.scene_view.choice_grid.show_resolution_error("Action resolution is unavailable.")
            return
        self._start_action_resolution(action)

    def _start_combat(self) -> None:
        self._start_combat_task(None)

    def _resolve_combat_action(self, command: CombatCommand) -> None:
        self._start_combat_task(command)

    def _start_combat_task(self, command: CombatCommand | None) -> None:
        if self._combat_task is not None or self._action_task is not None or self._dialogue_task is not None:
            self._show_status_message("Another game action is already being resolved")
            return
        if self.game_state_service is None:
            self._show_status_message("Combat requires a state-backed campaign")
            return
        self._set_combat_pending(True)
        self._show_status_message(
            "Starting encounter..." if command is None else "Resolving combat turn..."
        )
        task = CombatResolutionTask(
            self.game_state_service,
            command=command,
            narrator=self.combat_narrator,
        )
        self._combat_task = task
        task.signals.succeeded.connect(
            lambda result, current=task: self._combat_resolution_succeeded(current, result)
        )
        task.signals.failed.connect(
            lambda message, current=task: self._combat_resolution_failed(current, message)
        )
        task.signals.finished.connect(
            lambda current=task: self._combat_resolution_finished(current)
        )
        QThreadPool.globalInstance().start(task)

    def _combat_resolution_succeeded(
        self, task: CombatResolutionTask, result: object
    ) -> None:
        if task is not self._combat_task or self.game_state_service is None:
            return
        try:
            dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._combat_resolution_failed(task, str(exc))
            return
        self._reload_dashboard(dashboard, target_page="dashboard")
        status = getattr(result, "status", "active")
        summaries = getattr(result, "summaries", ())
        detail = summaries[-1] if summaries else "Combat state updated"
        self._show_status_message(f"Combat {status}: {detail}")
        self._show_skill_check(getattr(result, "skill_check", None))
        if status != "active":
            self._show_pending_combat_reward()

    def _show_skill_check(self, result: SkillCheckResult | None) -> None:
        if result is None:
            return
        if self._skill_check_popup is not None:
            previous = self._skill_check_popup
            self._skill_check_popup = None
            self.set_dialog_dimmed(False)
            previous.close()
        popup = SkillCheckPopup(result, self)
        self._skill_check_popup = popup
        self.set_dialog_dimmed(True)

        def released(*_args: object) -> None:
            if self._skill_check_popup is popup:
                self._skill_check_popup = None
                self.set_dialog_dimmed(False)

        popup.destroyed.connect(released)
        popup.show_centered(self)

    def _show_pending_combat_reward(self) -> None:
        encounter = self.dashboard.combat
        if (
            self.game_state_service is None or encounter is None
            or encounter.reward is None or encounter.reward.acknowledged
            or encounter.status == "active"
            or (self._reward_dialog is not None and self._reward_dialog.isVisible())
        ):
            return
        dialog = CombatRewardsDialog(encounter, self.dashboard.player, self)
        self._reward_dialog = dialog
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.claim_item_requested.connect(self._claim_reward_item)
        dialog.claim_all_requested.connect(self._claim_all_rewards)
        dialog.continued.connect(self._continue_after_combat)
        dialog.destroyed.connect(
            lambda *_args: setattr(self, "_reward_dialog", None)
        )
        dialog.show()

    def _claim_reward_item(self, item_id: str) -> None:
        if self.game_state_service is None or self._reward_dialog is None:
            return
        try:
            self.game_state_service.claim_combat_reward_item(item_id)
            self.dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._reward_dialog.show_warning(str(exc))
            return
        self._reward_dialog.mark_claimed(item_id)

    def _claim_all_rewards(self, reward_id: str) -> None:
        if self.game_state_service is None or self._reward_dialog is None:
            return
        try:
            _claimed, remaining = self.game_state_service.claim_all_combat_rewards(
                reward_id
            )
            self.dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._reward_dialog.show_warning(str(exc))
            return
        reward = None if self.dashboard.combat is None else self.dashboard.combat.reward
        unclaimed_ids = set()
        if reward is not None:
            unclaimed_ids = {item.id for item in reward.items if not item.claimed}
        self._reward_dialog.mark_all_claimed(unclaimed_ids)
        if remaining:
            self._reward_dialog.show_warning(
                f"Inventory capacity prevented {remaining} reward item(s) from being claimed. "
                "They remain stored with this encounter."
            )

    def _continue_after_combat(self, reward_id: str) -> None:
        if self.game_state_service is None:
            return
        try:
            self.game_state_service.acknowledge_combat_reward(reward_id)
            dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._show_status_message(str(exc))
            return
        self._reload_dashboard(dashboard, target_page="dashboard")
        self._show_status_message("Encounter rewards saved; adventure resumed")

    def _show_pending_quest_reward(self) -> None:
        reward = self.dashboard.pending_quest_reward
        if (
            self.game_state_service is None or reward is None or reward.acknowledged
            or (self._quest_reward_dialog is not None and self._quest_reward_dialog.isVisible())
            or (self._reward_dialog is not None and self._reward_dialog.isVisible())
        ):
            return
        dialog = QuestRewardsDialog(reward, self)
        self._quest_reward_dialog = dialog
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.claim_item_requested.connect(self._claim_quest_reward_item)
        dialog.continued.connect(self._continue_after_quest)
        dialog.destroyed.connect(
            lambda *_args: setattr(self, "_quest_reward_dialog", None)
        )
        dialog.show()

    def _show_pending_crafting_result(self) -> None:
        result = self.dashboard.pending_crafting_result
        if (
            self.game_state_service is None or result is None or result.acknowledged
            or (
                self._crafting_result_dialog is not None
                and self._crafting_result_dialog.isVisible()
            )
            or (self._reward_dialog is not None and self._reward_dialog.isVisible())
            or (
                self._quest_reward_dialog is not None
                and self._quest_reward_dialog.isVisible()
            )
        ):
            return
        dialog = CraftingResultsDialog(result, self)
        self._crafting_result_dialog = dialog
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.continued.connect(self._continue_after_crafting)
        dialog.destroyed.connect(
            lambda *_args: setattr(self, "_crafting_result_dialog", None)
        )
        dialog.show()

    def _continue_after_crafting(self, result_id: str) -> None:
        if self.game_state_service is None:
            return
        try:
            self.game_state_service.acknowledge_crafting_result(result_id)
            dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._show_status_message(str(exc))
            return
        if self._crafting_result_dialog is not None:
            self._crafting_result_dialog.allow_close()
        self._reload_dashboard(dashboard, target_page="crafting")
        self._show_status_message("Crafting result recorded")

    def _claim_quest_reward_item(self, item_id: str) -> None:
        if self.game_state_service is None or self._quest_reward_dialog is None:
            return
        try:
            self.game_state_service.claim_quest_reward_item(item_id)
            self.dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._quest_reward_dialog.show_warning(str(exc))
            return
        self._quest_reward_dialog.mark_claimed(item_id)

    def _continue_after_quest(self, reward_id: str) -> None:
        if self.game_state_service is None:
            return
        try:
            self.game_state_service.acknowledge_quest_reward(reward_id)
            dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self._show_status_message(str(exc))
            return
        self._reload_dashboard(dashboard, target_page="dashboard")
        self._show_status_message("Quest rewards recorded")

    def _show_pending_level_up(self) -> None:
        if (
            self.game_state_service is None
            or self.dashboard.player.pending_ability_points <= 0
            or (self._level_up_dialog is not None and self._level_up_dialog.isVisible())
            or (self._reward_dialog is not None and self._reward_dialog.isVisible())
            or (
                self._quest_reward_dialog is not None
                and self._quest_reward_dialog.isVisible()
            )
            or (
                self._crafting_result_dialog is not None
                and self._crafting_result_dialog.isVisible()
            )
        ):
            return
        dialog = LevelUpDialog(self.dashboard.player, self)
        self._level_up_dialog = dialog
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.allocations_selected.connect(self._apply_level_up_choices)
        dialog.destroyed.connect(
            lambda *_args: setattr(self, "_level_up_dialog", None)
        )
        dialog.show()

    def _apply_level_up_choices(self, allocations: object) -> None:
        if self.game_state_service is None or not isinstance(allocations, dict):
            return
        try:
            dashboard = self.game_state_service.allocate_level_up_points(allocations)
        except GameStateError as exc:
            self._show_status_message(str(exc))
            return
        if self._level_up_dialog is not None:
            self._level_up_dialog.accept()
        self._reload_dashboard(dashboard, target_page="character_sheet")
        self._show_status_message("Level-up choices saved")

    def _combat_resolution_failed(
        self, task: CombatResolutionTask, message: str
    ) -> None:
        if task is self._combat_task:
            self._set_combat_pending(False)
            self._show_status_message(message)

    def _combat_resolution_finished(self, task: CombatResolutionTask) -> None:
        if task is self._combat_task:
            self._combat_task = None

    def _start_action_resolution(self, action: str) -> None:
        if self._action_task is not None or self._dialogue_task is not None:
            self._show_status_message("An action is already being resolved")
            return
        normalized = " ".join(action.split())
        if not normalized:
            self.scene_view.choice_grid.show_validation_error("Enter an action before sending.")
            return
        if (
            self.game_state_service is not None
            and self.game_state_service.action_requests_combat(normalized)
        ):
            self._start_combat_task(None)
            return
        if self._route_trade_action(normalized):
            return
        if self._route_npc_action(normalized):
            return
        if self.action_resolver is None or self.game_state_service is None:
            self.scene_view.choice_grid.show_resolution_error("Action resolution is unavailable.")
            return
        self.scene_view.choice_grid.show_resolution_pending(normalized)
        task = ActionResolutionTask(
            self.game_state_service,
            self.action_resolver,
            normalized,
        )
        self._action_task = task
        task.signals.succeeded.connect(
            lambda result, current=task: self._action_resolution_succeeded(current, result)
        )
        task.signals.failed.connect(
            lambda message, current=task: self._action_resolution_failed(current, message)
        )
        task.signals.cancelled.connect(
            lambda current=task: self._action_resolution_cancelled(current)
        )
        task.signals.finished.connect(
            lambda current=task: self._action_resolution_finished(current)
        )
        QThreadPool.globalInstance().start(task)

    def _route_trade_action(self, action: str) -> bool:
        if not re.search(
            r"\b(trade|barter|buy|purchase|sell|wares?|goods|stock|shop)\b",
            action,
            re.IGNORECASE,
        ):
            return False
        if self.game_state_service is not None:
            addressed_role = self.game_state_service.addressed_npc_role(action)
            npc_id = self.game_state_service.ensure_local_interaction_npc(
                action, merchant=True
            )
            if npc_id is not None:
                self._open_npc_conversation(npc_id, action)
                return True
            if addressed_role:
                return False
        merchants = [
            conversation
            for conversation in self.dashboard.npc_conversations
            if conversation.merchant is not None and conversation.npc.available
        ]
        if not merchants:
            return False
        lowered = action.casefold()
        conversation = next(
            (value for value in merchants if value.npc.name.casefold() in lowered),
            merchants[0],
        )
        self._open_npc_conversation(conversation.npc.id, action)
        return True

    def _route_npc_action(self, action: str) -> bool:
        if self.game_state_service is None or not re.search(
            r"\b(ask|tell|question|greet|speak|talk)\b", action, re.IGNORECASE
        ):
            return False
        npc_id = self.game_state_service.ensure_local_interaction_npc(action)
        if npc_id is None:
            return False
        self._open_npc_conversation(npc_id, action)
        return True

    def _open_npc_conversation(self, npc_id: str, action: str) -> None:
        if self.game_state_service is not None:
            self._reload_dashboard(
                self.game_state_service.load_active_dashboard(), target_page="people"
            )
        else:
            self.controller.navigate("people")
        page = self.navigation_pages.get("people")
        if page is not None and hasattr(page, "open_npc"):
            page.open_npc(npc_id)
        self._resolve_npc_dialogue(npc_id, action)

    def _cancel_action_resolution(self) -> None:
        if self._action_task is not None:
            self._action_task.cancel()

    def _action_resolution_succeeded(
        self,
        task: ActionResolutionTask,
        result: ActionResolutionResult,
    ) -> None:
        if task is not self._action_task or self.game_state_service is None:
            return
        try:
            dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self.scene_view.choice_grid.show_resolution_error(str(exc))
            return
        self._reload_dashboard(dashboard, target_page="dashboard")
        detail = "; ".join(result.state_summaries)
        self._show_status_message(
            "Turn committed" + (f": {detail}" if detail else "")
        )

    def _action_resolution_failed(
        self,
        task: ActionResolutionTask,
        message: str,
    ) -> None:
        if task is self._action_task:
            self.scene_view.choice_grid.show_resolution_error(message)
            self._show_status_message("Action was not committed")

    def _action_resolution_cancelled(self, task: ActionResolutionTask) -> None:
        if task is self._action_task:
            self.scene_view.choice_grid.show_resolution_cancelled()
            self._show_status_message("Action cancelled; no state was changed")

    def _action_resolution_finished(self, task: ActionResolutionTask) -> None:
        if task is self._action_task:
            self._action_task = None

    def _show_navigation(self, target: str) -> None:
        if target not in self.page_indices:
            self._show_status_message(f"Unknown navigation target: {target}")
            return
        self.current_page = target
        self.content_stack.setCurrentIndex(self.page_indices[target])
        self.scene_view.tabs.set_current(target)
        self._show_status_message(
            "Adventure dashboard"
            if target == "dashboard"
            else f"Opened {target.replace('_', ' ').title()}"
        )
        if (
            target in {"settings", "character_creation"}
            and self.isVisible()
            and not self._models_scanned
        ):
            self._refresh_lm_models()
        elif target == "character_creation" and self._discovered_models:
            self.character_creation_panel.set_models(
                self._discovered_models,
                self.lm_client.model_id if self.lm_client is not None else None,
            )
        self.music.update(target, self.dashboard)

    def _configure_local_ai(self, mode: str, directory: str, model_path: str) -> None:
        folder = Path(directory or default_model_directory()).expanduser()
        try:
            folder.mkdir(parents=True, exist_ok=True)
            probe = folder / ".dnd-simulator-write-test"
            probe.touch()
            probe.unlink()
        except OSError as exc:
            self.local_ai_setup_panel.show_status(
                f"The selected model folder is not writable: {exc}", error=True
            )
            return
        if mode.startswith("recommended:"):
            if self._local_ai_download_task is not None:
                return
            model_key = mode.partition(":")[2]
            self.local_ai_setup_panel.progress.setValue(0)
            self.local_ai_setup_panel.set_busy(
                True, "Downloading and verifying the selected model...", downloading=True
            )
            task = RecommendedModelDownloadTask(folder, model_key)
            self._local_ai_download_task = task
            task.signals.progress.connect(self.local_ai_setup_panel.progress.setValue)
            task.signals.succeeded.connect(
                lambda path, current=task: self._recommended_model_downloaded(current, path)
            )
            task.signals.failed.connect(
                lambda message, current=task: self._local_ai_task_failed(current, message)
            )
            task.signals.finished.connect(
                lambda current=task: self._local_ai_download_finished(current)
            )
            QThreadPool.globalInstance().start(task)
            return
        if mode == "llama_cpp":
            path = Path(model_path)
            if path.suffix.casefold() != ".gguf" or not path.is_file():
                self.local_ai_setup_panel.show_status(
                    "Select an existing .gguf model file.", error=True
                )
                return
            configuration = LocalAiConfiguration(
                mode="llama_cpp", model_directory=str(folder), model_path=str(path)
            )
        elif mode == "unsloth":
            api_key = self.local_ai_setup_panel.api_key.text().strip()
            if not api_key:
                self.local_ai_setup_panel.show_status(
                    "Enter the API key created in Unsloth Studio (Settings -> API).", error=True
                )
                return
            self.local_ai_runtime.stop()
            configuration = LocalAiConfiguration(
                mode="unsloth",
                model_directory=str(folder),
                unsloth_port=self.local_ai_setup_panel.unsloth_port.value(),
                api_key=api_key,
            )
        elif mode == "lm_studio":
            self.local_ai_runtime.stop()
            configuration = LocalAiConfiguration(
                mode="lm_studio", model_directory=str(folder)
            )
        else:
            self.local_ai_setup_panel.show_status("Unknown local AI setup option.", error=True)
            return
        self._activate_local_ai(configuration)

    def _recommended_model_downloaded(
        self, task: RecommendedModelDownloadTask, path: str
    ) -> None:
        if task is not self._local_ai_download_task:
            return
        self._activate_local_ai(LocalAiConfiguration(
            mode="llama_cpp",
            model_directory=str(Path(path).parent),
            model_path=path,
        ))

    def _activate_local_ai(self, configuration: LocalAiConfiguration) -> None:
        if self._local_ai_activation_task is not None:
            return
        self.local_ai_setup_panel.set_busy(
            True,
            "Starting and testing the local model..."
            if configuration.mode == "llama_cpp"
            else "Checking LM Studio and its loaded model..."
            if configuration.mode == "lm_studio"
            else "Checking Unsloth Studio and its loaded model...",
        )
        task = LocalAiActivationTask(configuration, self.local_ai_runtime)
        self._local_ai_activation_task = task
        task.signals.succeeded.connect(
            lambda config, endpoint, model_id, current=task:
                self._local_ai_activated(current, config, endpoint, model_id)
        )
        task.signals.failed.connect(
            lambda message, current=task: self._local_ai_task_failed(current, message)
        )
        task.signals.finished.connect(
            lambda current=task: self._local_ai_activation_finished(current)
        )
        QThreadPool.globalInstance().start(task)

    def _local_ai_activated(
        self,
        task: LocalAiActivationTask,
        configuration: object,
        endpoint: str,
        model_id: str,
    ) -> None:
        if task is not self._local_ai_activation_task or not isinstance(
            configuration, LocalAiConfiguration
        ):
            return
        completed = replace(configuration, setup_complete=True, model_id=model_id)
        client = LocalModelClient(
            endpoint, timeout_seconds=90, model_id=model_id,
            api_key=configuration.api_key or None,
            provider="openai" if configuration.mode == "llama_cpp" else configuration.mode,
        )
        self._finish_local_ai_setup(completed, client)

    def _finish_local_ai_setup(
        self,
        configuration: LocalAiConfiguration,
        client: LocalModelClient | None,
    ) -> None:
        self.local_ai_configuration = configuration
        self.lm_client = client
        if client is None:
            self.character_randomizer = None
            self.action_resolver = None
            self.combat_narrator = None
            self.travel_narrator = None
            self.dialogue_narrator = None
            self.model_evaluator = None
        else:
            self.character_randomizer = CharacterRandomizationService(client)
            self.action_resolver = LocalModelActionResolver(client)
            self.combat_narrator = LocalModelCombatNarrator(client)
            self.travel_narrator = LocalModelTravelNarrator(client)
            self.dialogue_narrator = LocalModelDialogueNarrator(client)
            self.model_evaluator = ModelEvaluationService(
                client, self.config_dir / "model-evaluations"
            )
        if self.preferences_store is not None:
            self.preferences_store.save_local_ai(configuration.to_mapping())
            if client is not None:
                self._save_model_preference(configuration.model_id)
        self.character_creation_panel.randomizer = self.character_randomizer
        self.local_ai_setup_panel.configuration = configuration
        self.local_ai_setup_panel.cancel_button.show()
        self.local_ai_setup_panel.set_busy(False, "Local AI setup completed successfully.")
        self._models_scanned = False
        self.controller.navigate("settings")
        if client is not None:
            self._refresh_lm_models()

    def _local_ai_task_failed(self, task: object, message: str) -> None:
        if not any(task is current for current in (
            self._local_ai_download_task, self._local_ai_activation_task
        )):
            return
        self.local_ai_setup_panel.set_busy(False, message)
        self.local_ai_setup_panel.show_status(message, error=True)

    def _local_ai_download_finished(self, task: RecommendedModelDownloadTask) -> None:
        if task is self._local_ai_download_task:
            self._local_ai_download_task = None

    def _local_ai_activation_finished(self, task: LocalAiActivationTask) -> None:
        if task is self._local_ai_activation_task:
            self._local_ai_activation_task = None

    def _cancel_local_ai_operation(self) -> None:
        if self._local_ai_download_task is not None:
            self._local_ai_download_task.cancel()
            self.local_ai_setup_panel.show_status(
                "Cancelling download; partial progress will be retained."
            )
        elif self._local_ai_activation_task is not None:
            self.local_ai_runtime.stop()
            self.local_ai_setup_panel.show_status("Cancelling local model startup...")

    def _model_panels(self) -> tuple[object, ...]:
        panels: list[object] = [self.settings_panel]
        if hasattr(self, "character_creation_panel"):
            panels.append(self.character_creation_panel)
        return tuple(panels)

    def _refresh_lm_models(self) -> None:
        if self.lm_client is None:
            for panel in self._model_panels():
                panel.show_model_status(  # type: ignore[attr-defined]
                    "Local model integration is unavailable in this application session.",
                    error=True,
                )
            return
        if any(
            task is not None
            for task in (
                self._model_discovery_task,
                self._model_evaluation_task,
                self._model_load_task,
            )
        ):
            return
        for panel in self._model_panels():
            panel.set_model_busy(  # type: ignore[attr-defined]
                True, "Scanning the local model server..."
            )
        task = ModelDiscoveryTask(self.lm_client)
        self._model_discovery_task = task
        task.signals.succeeded.connect(
            lambda models, current=task: self._model_discovery_succeeded(current, models)
        )
        task.signals.failed.connect(
            lambda message, current=task: self._model_task_failed(current, message)
        )
        task.signals.finished.connect(
            lambda current=task: self._model_discovery_finished(current)
        )
        QThreadPool.globalInstance().start(task)

    def _model_discovery_succeeded(self, task: ModelDiscoveryTask, models: object) -> None:
        if task is not self._model_discovery_task:
            return
        self._models_scanned = True
        self._discovered_models = tuple(models)  # type: ignore[arg-type]
        for panel in self._model_panels():
            panel.set_models(  # type: ignore[attr-defined]
                models,  # type: ignore[arg-type]
                self.lm_client.model_id if self.lm_client is not None else None,
            )

    def _model_task_failed(self, task: object, message: str) -> None:
        if not any(
            task is current
            for current in (
                self._model_discovery_task,
                self._model_evaluation_task,
                self._model_load_task,
            )
        ):
            return
        for panel in self._model_panels():
            panel.set_model_busy(False, message)  # type: ignore[attr-defined]
            panel.show_model_status(message, error=True)  # type: ignore[attr-defined]
        self._show_model_status_message(message)

    def _model_discovery_finished(self, task: ModelDiscoveryTask) -> None:
        if task is self._model_discovery_task:
            self._model_discovery_task = None
            for panel in self._model_panels():
                panel.set_model_busy(  # type: ignore[attr-defined]
                    False, panel.model_status.text()  # type: ignore[attr-defined]
                )

    def _select_lm_model(self, model_id: str) -> None:
        if self.lm_client is None:
            return
        self.lm_client.select_model(model_id)
        if self.preferences_store is not None:
            self._save_model_preference(model_id)
        for panel in self._model_panels():
            panel.show_model_status(  # type: ignore[attr-defined]
                f"Selected {model_id}. All local generation paths will use this model."
            )
        self._show_model_status_message(f"Local model selected: {model_id}")

    def _save_model_preference(self, model_id: str) -> None:
        if self.preferences_store is None:
            return
        if self.local_ai_configuration.mode == "unsloth":
            self.preferences_store.save_unsloth({"model_id": model_id})
        else:
            self.preferences_store.save_lm_studio({"model_id": model_id})

    def _load_lm_model(self, model_id: str) -> None:
        if self.lm_client is None or any(
            task is not None
            for task in (
                self._model_discovery_task,
                self._model_evaluation_task,
                self._model_load_task,
            )
        ):
            return
        for panel in self._model_panels():
            panel.set_model_busy(  # type: ignore[attr-defined]
                True, f"Unloading other models and loading {model_id} into the local model server..."
            )
        task = ModelLoadTask(self.lm_client, model_id)
        self._model_load_task = task
        task.signals.succeeded.connect(
            lambda instance_id, current=task: self._model_load_succeeded(
                current, str(instance_id)
            )
        )
        task.signals.failed.connect(
            lambda message, current=task: self._model_task_failed(current, message)
        )
        task.signals.finished.connect(
            lambda current=task: self._model_load_finished(current)
        )
        QThreadPool.globalInstance().start(task)

    def _model_load_succeeded(self, task: ModelLoadTask, instance_id: str) -> None:
        if task is not self._model_load_task:
            return
        self._models_scanned = False
        self._select_lm_model(instance_id)
        for panel in self._model_panels():
            panel.show_model_status(  # type: ignore[attr-defined]
                f"Loaded {instance_id}. Refreshing model status..."
            )

    def _model_load_finished(self, task: ModelLoadTask) -> None:
        if task is not self._model_load_task:
            return
        self._model_load_task = None
        if self._models_scanned:
            for panel in self._model_panels():
                panel.set_model_busy(  # type: ignore[attr-defined]
                    False, panel.model_status.text()  # type: ignore[attr-defined]
                )
        else:
            self._refresh_lm_models()

    def _run_model_evaluation(self, model_id: str) -> None:
        if self.model_evaluator is None:
            for panel in self._model_panels():
                panel.show_model_status(  # type: ignore[attr-defined]
                    "Model evaluation is unavailable in this application session.",
                    error=True,
                )
            return
        if any(
            task is not None
            for task in (
                self._model_evaluation_task,
                self._model_discovery_task,
                self._model_load_task,
            )
        ):
            return
        for panel in self._model_panels():
            panel.set_model_busy(  # type: ignore[attr-defined]
                True,
                "Running three isolated probes. Campaign state will not be read or changed...",
            )
        task = ModelEvaluationTask(self.model_evaluator, model_id)
        self._model_evaluation_task = task
        task.signals.succeeded.connect(
            lambda result, current=task: self._model_evaluation_succeeded(current, result)
        )
        task.signals.failed.connect(
            lambda message, current=task: self._model_task_failed(current, message)
        )
        task.signals.finished.connect(
            lambda current=task: self._model_evaluation_finished(current)
        )
        QThreadPool.globalInstance().start(task)

    def _model_evaluation_succeeded(
        self, task: ModelEvaluationTask, result: ModelEvaluation
    ) -> None:
        if task is not self._model_evaluation_task:
            return
        for panel in self._model_panels():
            panel.show_model_evaluation(result)  # type: ignore[attr-defined]
        self._show_model_status_message(result.recommendation)

    def _show_model_status_message(self, message: str) -> None:
        if self.current_page == "settings":
            self._show_status_message(message)

    def _model_evaluation_finished(self, task: ModelEvaluationTask) -> None:
        if task is self._model_evaluation_task:
            self._model_evaluation_task = None
            for panel in self._model_panels():
                panel.set_model_busy(  # type: ignore[attr-defined]
                    False, panel.model_status.text()  # type: ignore[attr-defined]
                )

    def _load_campaign(self, campaign_id: str) -> None:
        if self.game_state_service is None:
            return
        try:
            dashboard = self.game_state_service.load_campaign(campaign_id)
            self.game_state_service.select_campaign(campaign_id)
        except (GameStateError, KeyError) as exc:
            self._show_status_message(f"Campaign could not be loaded: {exc}")
            return
        self._reload_dashboard(dashboard)
        self._show_status_message(f"Loaded campaign for {dashboard.player.name}")

    def _delete_campaign(self, campaign_id: str) -> None:
        if self.game_state_service is None:
            return
        campaign = self.game_state_service.campaigns.get(campaign_id)
        if campaign is None:
            self._show_status_message("Campaign no longer exists")
            return
        answer = QMessageBox.question(
            self,
            "Delete Campaign?",
            f"Permanently delete '{campaign.name}' and its saved progress?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            replacement_id = self.game_state_service.delete_campaign(campaign_id)
            dashboard = self.game_state_service.load_campaign(replacement_id)
        except (GameStateError, KeyError) as exc:
            self._show_status_message(f"Campaign could not be deleted: {exc}")
            return
        self._reload_dashboard(dashboard, target_page="settings")
        self._show_status_message(f"Deleted campaign '{campaign.name}'")

    def _complete_character_creation(self, draft: object) -> None:
        if self.game_state_service is None:
            return
        try:
            campaign_id = self.game_state_service.complete_character_creation(  # type: ignore[arg-type]
                draft,
                opening_text="Generating your campaign... please wait!",
            )
            dashboard = self.game_state_service.load_campaign(campaign_id)
        except (GameStateError, ValueError) as exc:
            self.character_creation_panel.error_label.setText(str(exc))
            return
        self._reload_dashboard(dashboard)
        self._show_status_message(
            f"Created {dashboard.player.name}; campaign saved to the Game-State Ledger"
        )
        if self.character_randomizer is None:
            introduction = CharacterRandomizationService.fallback_intro(draft)  # type: ignore[arg-type]
            self._save_campaign_introduction(campaign_id, introduction)
            return
        task = CampaignIntroTask(self.character_randomizer, campaign_id, draft)  # type: ignore[arg-type]
        self._campaign_intro_task = task
        task.signals.succeeded.connect(self._campaign_intro_succeeded)
        task.signals.failed.connect(self._campaign_intro_failed)
        task.signals.finished.connect(self._campaign_intro_finished)
        QThreadPool.globalInstance().start(task)

    def _campaign_intro_succeeded(self, campaign_id: str, introduction: str) -> None:
        self._save_campaign_introduction(campaign_id, introduction)

    def _campaign_intro_failed(self, campaign_id: str, message: str) -> None:
        task = self._campaign_intro_task
        if task is None or task.campaign_id != campaign_id:
            return
        self._save_campaign_introduction(
            campaign_id,
            CharacterRandomizationService.fallback_intro(task.draft),
        )
        self._show_status_message(
            f"Local model opening unavailable; a local opening was saved. {message}"
        )

    def _campaign_intro_finished(self, campaign_id: str) -> None:
        if (
            self._campaign_intro_task is not None
            and self._campaign_intro_task.campaign_id == campaign_id
        ):
            self._campaign_intro_task = None

    def _save_campaign_introduction(self, campaign_id: str, introduction: str) -> None:
        if self.game_state_service is None:
            return
        try:
            self.game_state_service.replace_campaign_introduction(
                campaign_id, introduction
            )
            dashboard = self.game_state_service.load_campaign(campaign_id)
        except (GameStateError, KeyError, ValueError) as exc:
            self._show_status_message(f"Campaign opening could not be saved: {exc}")
            return
        self._reload_dashboard(dashboard)
        self._show_status_message("Campaign opening generated and autosaved")

    def _resource_values(self) -> dict[str, int]:
        values = {
            resource.resource_type: resource.current
            for resource in self.dashboard.sidebar_resources
        }
        values[self.dashboard.player.experience.resource_type] = (
            self.dashboard.player.experience.current
        )
        return values

    def _refresh_character_sheet(self, dashboard: DashboardView) -> None:
        old_page = self.navigation_pages.get("character_sheet")
        index = self.page_indices.get("character_sheet")
        if old_page is None or index is None:
            return
        new_page = CharacterSheetPage(dashboard)
        new_page.back_requested.connect(
            lambda name="dashboard": self.controller.navigate(name)
        )
        new_page.crafting_requested.connect(lambda: self.controller.navigate("crafting"))
        self.content_stack.removeWidget(old_page)
        old_page.deleteLater()
        self.content_stack.insertWidget(index, new_page)
        self.navigation_pages["character_sheet"] = new_page

    def _refresh_item_views(self, dashboard: DashboardView) -> None:
        """Refresh item-dependent widgets without rebuilding the complete UI tree."""

        current_page = self.current_page
        self.dashboard = dashboard
        self._update_application_title()
        self.inventory_card.set_inventory(
            dashboard.inventory,
            capacity=dashboard.inventory_capacity,
            equipment=dashboard.equipment,
        )
        # Strip (purse, carry, resources) and paperdoll (AC, slots) are rebuilt in place.
        for name, widget in (
            ("character_strip", CharacterStrip(dashboard)),
            ("paperdoll_panel", PaperdollPanel(
                dashboard.player, dashboard.equipment, attack_bonus=dashboard.player.attack_bonus
            )),
        ):
            old = getattr(self, name)
            old.parentWidget().layout().replaceWidget(old, widget)
            old.deleteLater()
            setattr(self, name, widget)
        self._connect_equipment_grid(self.paperdoll_panel)
        self._refresh_character_sheet(dashboard)
        self.content_stack.setCurrentIndex(self.page_indices.get(current_page, 0))
        QTimer.singleShot(0, lambda: self._restore_inventory_ui_state(None))

    def _reload_dashboard(
        self,
        dashboard: DashboardView,
        *,
        target_page: str = "dashboard",
    ) -> None:
        theme_id = str(self.theme_selector.currentData() or "high_fantasy")
        def event_signature(view: DashboardView) -> tuple[tuple[str, str, str], ...]:
            return tuple(
                (event.time_label, event.category, event.summary)
                for event in (*view.event_log, *view.recent_events)
            )
        events_changed = event_signature(dashboard) != event_signature(self.dashboard)
        journal = self.navigation_pages["journal"]
        event_filter = journal.event_log.current_filter()
        event_scroll = journal.event_log.scroll_state()
        recent_scroll = journal.recent_events.scroll_state()
        inventory_scroll = self.inventory_card.scroll.verticalScrollBar().value()
        splitter_sizes = {"concept_t": self.concept_splitter.sizes()}
        people_splitter = self.findChild(QSplitter, "peopleTradeConversationSplitter")
        if people_splitter is not None:
            splitter_sizes["people"] = people_splitter.sizes()
        people_page = self.navigation_pages.get("people")
        selected_npc_id = getattr(people_page, "selected_id", "")
        previous_resource_values = self._resource_values()
        combat_target = self.scene_view.choice_grid.target_id
        old_stack = self.content_stack
        self.root_layout.removeWidget(old_stack)
        old_stack.setParent(None)
        old_stack.deleteLater()
        self.dashboard = dashboard
        self._resource_animation_starts = previous_resource_values
        self._update_application_title()
        self._build_content_stack()
        self._resource_animation_starts = {}
        self.scene_view.select_target(combat_target)
        sizes = self._valid_sizes(splitter_sizes.get("concept_t"), self.concept_splitter.count())
        if sizes:
            self.concept_splitter.setSizes(sizes)
        people_splitter = self.findChild(QSplitter, "peopleTradeConversationSplitter")
        if people_splitter is not None:
            sizes = self._valid_sizes(splitter_sizes.get("people"), people_splitter.count())
            if sizes:
                people_splitter.setSizes(sizes)
        people_page = self.navigation_pages.get("people")
        if selected_npc_id and people_page is not None and hasattr(people_page, "open_npc"):
            people_page.open_npc(selected_npc_id)
        journal = self.navigation_pages["journal"]
        journal.event_log.set_current_filter(event_filter)
        if events_changed:
            QTimer.singleShot(0, journal.event_log.scroll_to_latest)
            QTimer.singleShot(0, journal.recent_events.scroll_to_latest)
        else:
            QTimer.singleShot(0, lambda: journal.event_log.restore_scroll_state(event_scroll))
            QTimer.singleShot(0, lambda: journal.recent_events.restore_scroll_state(recent_scroll))
        QTimer.singleShot(0, lambda: self._restore_inventory_ui_state(inventory_scroll))
        self.select_theme(theme_id)
        self._show_navigation(
            target_page if target_page in self.page_indices else "dashboard"
        )
        QTimer.singleShot(0, self._show_pending_quest_reward)
        QTimer.singleShot(0, self._show_pending_crafting_result)
        QTimer.singleShot(400, self._show_pending_level_up)

    def _restore_inventory_ui_state(self, scroll_value: int | None) -> None:
        if scroll_value is not None:
            bar = self.inventory_card.scroll.verticalScrollBar()
            bar.setValue(min(scroll_value, bar.maximum()))
        if self._selected_inventory_item_id is None:
            return
        item = next(
            (value for value in self.dashboard.inventory if value.id == self._selected_inventory_item_id),
            None,
        )
        if item is None or item.position is None:
            return
        self.inventory_card.scroll_to_position(item.position)
        self.inventory_card.grid.select_index(item.position)

    def _show_status_message(self, message: str) -> None:
        self.statusBar().showMessage(message, 5000)

    def show_startup_status(self, message: str) -> None:
        self.startup_readiness = message
        self.settings_panel.show_startup_status(message)

    def _export_diagnostic_logs(self) -> None:
        sources = tuple(
            path
            for folder in (self.config_dir / "logs", self.config_dir / "model-evaluations")
            if folder.is_dir()
            for path in folder.rglob("*")
            if path.is_file()
        )
        if not sources:
            self.settings_panel.show_reliability_status(
                "No diagnostic logs are available yet.", error=True
            )
            return
        selected, _filter = QFileDialog.getSaveFileName(
            self,
            "Export Diagnostic Logs",
            str(self.config_dir / "dnd-simulator-diagnostics.zip"),
            "ZIP archives (*.zip)",
        )
        if not selected:
            return
        destination = Path(selected)
        if destination.suffix.casefold() != ".zip":
            destination = destination.with_suffix(".zip")
        try:
            with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as archive:
                for source in sources:
                    archive.write(source, source.relative_to(self.config_dir))
        except OSError as exc:
            self.settings_panel.show_reliability_status(
                f"Diagnostic export failed: {exc}", error=True
            )
            return
        message = f"Diagnostic logs exported to {destination}."
        self.settings_panel.show_reliability_status(message)
        self._show_status_message(message)

    @staticmethod
    def _valid_sizes(value: object, expected: int) -> list[int] | None:
        if not isinstance(value, list) or len(value) != expected:
            return None
        if not all(isinstance(item, int) and item > 0 for item in value):
            return None
        return value

    def _load_ui_preferences(self) -> None:
        if self.preferences_store is None:
            return
        ui = self.preferences_store.load_ui()
        splitters = ui.get("splitters")
        if isinstance(splitters, dict):
            sizes = self._valid_sizes(splitters.get("concept_t"), self.concept_splitter.count())
            if sizes:
                self.concept_splitter.setSizes(sizes)
            people_splitter = self.findChild(QSplitter, "peopleTradeConversationSplitter")
            if people_splitter is not None:
                sizes = self._valid_sizes(splitters.get("people"), people_splitter.count())
                if sizes:
                    people_splitter.setSizes(sizes)
        page = ui.get("page")
        if isinstance(page, str):
            self._show_navigation(page if page in self.page_indices else "dashboard")
        font_size = ui.get("font_size")
        if isinstance(font_size, (int, str)):
            self.select_font_size(font_size)
        reduced_motion = ui.get("reduced_motion")
        if isinstance(reduced_motion, bool):
            self.reduced_motion_preference = reduced_motion
            self.settings_panel.select_reduced_motion(reduced_motion)
        event_filter = ui.get("event_filter")
        if isinstance(event_filter, int):
            self.navigation_pages["journal"].event_log.set_current_filter(event_filter)
        for key, attribute in (
            ("music_volume", "music_volume_preference"),
            ("ambience_volume", "ambience_volume_preference"),
        ):
            value = ui.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                setattr(self, attribute, min(100, max(0, value)))
        muted = ui.get("audio_muted")
        if isinstance(muted, bool):
            self.audio_muted_preference = muted
        self._apply_audio_preferences()

    def save_ui_preferences(self) -> None:
        if self.preferences_store is None:
            return
        self.preferences_store.save_ui(
            {
                "splitters": {
                    "concept_t": self.concept_splitter.sizes(),
                    "people": (
                        self.findChild(QSplitter, "peopleTradeConversationSplitter").sizes()
                        if self.findChild(QSplitter, "peopleTradeConversationSplitter")
                        is not None else [210, 500]
                    ),
                },
                "page": self.current_page,
                "font_size": self.font_size_preference,
                "reduced_motion": self.reduced_motion_preference,
                "event_filter": self.navigation_pages["journal"].event_log.current_filter(),
                "music_volume": self.music_volume_preference,
                "ambience_volume": self.ambience_volume_preference,
                "audio_muted": self.audio_muted_preference,
            }
        )

    def _create_checkpoint(self) -> None:
        if self.game_state_service is None:
            return
        label, accepted = QInputDialog.getText(
            self, "Create Campaign Checkpoint", "Checkpoint name:"
        )
        if not accepted:
            return
        try:
            checkpoint = self.game_state_service.create_checkpoint(label)
        except GameStateError as exc:
            self.settings_panel.show_reliability_status(str(exc), error=True)
            self._show_status_message(str(exc))
            return
        message = f"Checkpoint '{checkpoint.label}' saved and checksum-verified."
        self.settings_panel.show_reliability_status(message)
        self._show_status_message(message)

    def _choose_checkpoint(self, title: str) -> object | None:
        if self.game_state_service is None:
            return None
        try:
            checkpoints = self.game_state_service.list_checkpoints()
        except GameStateError as exc:
            self.settings_panel.show_reliability_status(str(exc), error=True)
            return None
        if not checkpoints:
            self.settings_panel.show_reliability_status(
                "Create a named checkpoint before using this operation.", error=True
            )
            return None
        labels = [f"{value.label} — {value.created_at}" for value in checkpoints]
        selected, accepted = QInputDialog.getItem(
            self, title, "Checkpoint:", labels, 0, False
        )
        if not accepted:
            return None
        return checkpoints[labels.index(selected)]

    def _load_checkpoint(self) -> None:
        checkpoint = self._choose_checkpoint("Load Campaign Checkpoint")
        if checkpoint is None or self.game_state_service is None:
            return
        answer = QMessageBox.question(
            self,
            "Restore checkpoint?",
            "This restores the campaign to the selected checkpoint. A recovery backup "
            "of the current ledger will be created first. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            dashboard = self.game_state_service.load_checkpoint(checkpoint.id)
        except GameStateError as exc:
            self.settings_panel.show_reliability_status(str(exc), error=True)
            self._show_status_message(str(exc))
            return
        self._reload_dashboard(dashboard, target_page="settings")
        message = f"Restored checkpoint '{checkpoint.label}' and rebuilt all panels."
        self.settings_panel.show_reliability_status(message)
        self._show_status_message(message)

    def _inspect_and_repair_campaign(self) -> None:
        if self.game_state_service is None:
            return
        try:
            issues = self.game_state_service.inspect_campaign_repair()
        except GameStateError as exc:
            self.settings_panel.show_reliability_status(str(exc), error=True)
            return
        if not issues:
            message = "Campaign integrity check passed; no repair is required."
            self.settings_panel.show_reliability_status(message)
            QMessageBox.information(self, "Campaign Repair", message)
            return
        details = "\n\n".join(
            f"• {issue.description}\n  Proposed: {issue.proposed_correction}"
            for issue in issues
        )
        answer = QMessageBox.question(
            self,
            "Apply safe campaign repairs?",
            details + "\n\nA recovery backup will be created before any correction.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            self.settings_panel.show_reliability_status("Repair inspection completed; no changes applied.")
            return
        try:
            result = self.game_state_service.repair_campaign()
            dashboard = self.game_state_service.load_active_dashboard()
        except GameStateError as exc:
            self.settings_panel.show_reliability_status(str(exc), error=True)
            QMessageBox.warning(self, "Campaign Repair", str(exc))
            return
        self._reload_dashboard(dashboard, target_page="settings")
        message = "Repair applied: " + " ".join(result.corrections)
        self.settings_panel.show_reliability_status(message)
        self._show_status_message(message)

    def _verify_checkpoint_replay(self) -> None:
        checkpoint = self._choose_checkpoint("Verify Campaign Replay")
        if checkpoint is None or self.game_state_service is None:
            return
        try:
            result = self.game_state_service.verify_checkpoint_replay(checkpoint.id)
        except GameStateError as exc:
            self.settings_panel.show_reliability_status(str(exc), error=True)
            return
        self.settings_panel.show_reliability_status(result.message, error=not result.valid)
        if result.valid:
            QMessageBox.information(self, "Replay Verification", result.message)
        else:
            QMessageBox.warning(self, "Replay Verification", result.message)

    def _reset_ui_preferences(self) -> None:
        self._flush_ui_preferences()
        self.concept_splitter.setSizes(list(CONCEPT_T_SIZES))
        people_splitter = self.findChild(QSplitter, "peopleTradeConversationSplitter")
        if people_splitter is not None:
            people_splitter.setSizes([210, 500])
        if self.preferences_store is not None:
            self.preferences_store.reset_ui()
        self.select_font_size(100)
        self.reduced_motion_preference = False
        self.settings_panel.select_reduced_motion(False)
        self.navigation_pages["journal"].event_log.set_current_filter(0)
        self.music_volume_preference = DEFAULT_MUSIC_VOLUME
        self.ambience_volume_preference = DEFAULT_AMBIENCE_VOLUME
        self.audio_muted_preference = False
        self._apply_audio_preferences()
        self.font_size_requested.emit(100)
        self.theme_requested.emit("high_fantasy")
        self.controller.navigate("dashboard")
        self._show_status_message("UI preferences restored to defaults")

    def _on_theme_changed(self, index: int) -> None:
        theme_id = self.theme_selector.itemData(index)
        if theme_id:
            self.theme_requested.emit(str(theme_id))

    def select_theme(self, theme_id: str) -> None:
        """Synchronize the picker without emitting a second request."""

        index = self.theme_selector.findData(theme_id)
        if index < 0:
            return
        if index != self.theme_selector.currentIndex():
            self.theme_selector.blockSignals(True)
            self.theme_selector.setCurrentIndex(index)
            self.theme_selector.blockSignals(False)
        self.settings_panel.select_theme(theme_id)
        for widget in self.findChildren(QWidget):
            refresh = getattr(widget, "refresh_theme_icon", None)
            if callable(refresh):
                refresh()

    def _on_font_size_changed(self, percent: int) -> None:
        self.select_font_size(percent)
        self.font_size_requested.emit(self.font_size_preference)
        self.save_ui_preferences()

    def _on_audio_changed(self, music: int, ambience: int, muted: bool) -> None:
        self.music_volume_preference = music
        self.ambience_volume_preference = ambience
        self.audio_muted_preference = muted
        self.music.set_volumes(music, ambience, muted)
        self._audio_save_timer.start()  # debounce: sliders emit on every tick

    def _flush_ui_preferences(self) -> None:
        if self._audio_save_timer.isActive():
            self._audio_save_timer.stop()
            self.save_ui_preferences()

    def _apply_audio_preferences(self) -> None:
        self.settings_panel.select_audio(
            self.music_volume_preference,
            self.ambience_volume_preference,
            self.audio_muted_preference,
        )
        self.music.set_volumes(
            self.music_volume_preference,
            self.ambience_volume_preference,
            self.audio_muted_preference,
        )

    def _on_reduced_motion_changed(self, enabled: bool) -> None:
        self.reduced_motion_preference = bool(enabled)
        self.settings_panel.select_reduced_motion(self.reduced_motion_preference)
        self.save_ui_preferences()

    def select_font_size(self, value: int | str) -> None:
        """Synchronize and retain a validated interface font-size preference."""

        legacy = {"small": 90, "default": 100, "large": 115}
        normalized = legacy.get(value, value)
        normalized = min(150, max(75, int(normalized))) if isinstance(normalized, int) else 100
        self.font_size_preference = normalized
        self.settings_panel.select_font_size(normalized)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._action_task is not None:
            self._action_task.cancel()
        if self._local_ai_download_task is not None:
            self._local_ai_download_task.cancel()
        self.local_ai_runtime.stop()
        self.music.stop()
        self._audio_save_timer.stop()
        self.save_ui_preferences()
        super().closeEvent(event)
