"""Application bootstrap for the D&D Simulator desktop shell."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
import os
import sys
from pathlib import Path
from typing import Sequence

from PySide6.QtCore import QTimer
from PySide6.QtGui import QColor, QFont, QImage
from PySide6.QtWidgets import QApplication, QLabel, QProgressBar, QPushButton, QWidget

from dd_simulator.state import (
    GameStateDatabase,
    GameStateError,
    GameStateService,
    ActionOutcome,
    ItemAction,
    ItemCommand,
    ProposedStateChange,
    CombatAction,
    CombatCommand,
    EnemySpec,
)
from dd_simulator.state.combat import CombatService
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION
from dd_simulator.state.quests import progress_quests
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID
from dd_simulator.local_model import (
    CharacterRandomizationService,
    LocalModelActionResolver,
    LocalModelClient,
    LocalModelCombatNarrator,
    LocalModelTravelNarrator,
    LocalModelDialogueNarrator,
    LocalModelModelInfo,
    ModelEvaluationService,
)
from dd_simulator.local_ai import LlamaCppRuntime, LocalAiConfiguration, LocalAiError
from dd_simulator.ui.fonts import register_application_fonts
from dd_simulator.ui.main_window import MainWindow
from dd_simulator.ui.models.presentation import DashboardView
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.item_icons import resolve_icon
from dd_simulator.ui.location_images import LOCATION_ARCHETYPES, LOCATION_ART_ROOT
from dd_simulator.state.turns import normalize_narrative_segment


APP_NAME = "D&D Simulator"
ORGANIZATION_NAME = "D&D Simulator"
LOGGER = logging.getLogger(__name__)
def default_config_dir() -> Path:
    """Return the per-user directory used for lightweight UI preferences."""

    override = os.environ.get("DDSIM_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    app_data = os.environ.get("APPDATA")
    if app_data:
        return Path(app_data) / "DnDSimulator"
    return Path.home() / ".dnd_simulator"


def load_dashboard_from_state(
    config_dir: Path,
) -> tuple[DashboardView, GameStateService, str | None]:
    """Load the active campaign without modifying a damaged on-disk ledger."""

    database = GameStateDatabase(config_dir / "game_state.db")
    service = GameStateService(database)
    try:
        service.initialize()
        return service.load_active_dashboard(), service, None
    except GameStateError as exc:
        LOGGER.exception("Could not open the on-disk Game-State Ledger")
        recovery_database = GameStateDatabase.in_memory()
        recovery_service = GameStateService(recovery_database)
        recovery_service.initialize()
        dashboard = recovery_service.load_active_dashboard()
        warning = (
            "The saved Game-State Ledger could not be opened. "
            "A temporary recovery campaign is active; the original file was not changed. "
            f"Details: {exc}"
        )
        return dashboard, recovery_service, warning


def build_application(
    argv: Sequence[str] | None = None,
    *,
    config_dir: Path | None = None,
) -> tuple[QApplication, MainWindow, ThemeManager]:
    """Create the Qt application, window, and theme manager."""

    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(ORGANIZATION_NAME)

    app = QApplication.instance()
    if app is None:
        app = QApplication(list(argv if argv is not None else sys.argv))
    register_application_fonts()
    base_application_font = app.property("dndBaseApplicationFont")
    if not isinstance(base_application_font, QFont):
        base_application_font = QFont(app.font())
        app.setProperty("dndBaseApplicationFont", base_application_font)

    themes_root = Path(__file__).parent / "ui" / "themes"
    resolved_config_dir = config_dir or default_config_dir()
    preferences_path = resolved_config_dir / "preferences.json"
    theme_manager = ThemeManager(
        themes_root=themes_root,
        preferences_path=preferences_path,
        default_theme_id="high_fantasy",
    )

    initial = theme_manager.load_preferred_theme()
    theme_manager.apply_loaded_theme(app, initial, persist=False)

    dashboard, game_state_service, state_warning = load_dashboard_from_state(
        resolved_config_dir
    )
    preferences_store = UiPreferencesStore(preferences_path)
    local_ai_configuration = LocalAiConfiguration.from_mapping(
        preferences_store.load_local_ai()
    )
    local_ai_runtime = LlamaCppRuntime(resolved_config_dir / "logs")
    lm_client: LocalModelClient | None = None
    if local_ai_configuration.usable() and local_ai_configuration.mode == "llama_cpp":
        try:
            endpoint = local_ai_runtime.start(Path(local_ai_configuration.model_path))
            lm_client = LocalModelClient(
                endpoint, timeout_seconds=90, model_id=local_ai_configuration.model_id,
                provider="openai",
            )
        except (OSError, LocalAiError):
            LOGGER.exception("Configured llama.cpp runtime could not start")
            local_ai_configuration = LocalAiConfiguration(
                model_directory=local_ai_configuration.model_directory
            )
    elif local_ai_configuration.usable() and local_ai_configuration.mode == "unsloth":
        model_preference = preferences_store.load_unsloth().get("model_id")
        lm_client = LocalModelClient(
            local_ai_configuration.unsloth_base_url,
            timeout_seconds=90,
            model_id=model_preference if isinstance(model_preference, str) else None,
            api_key=local_ai_configuration.api_key,
            provider="unsloth",
        )
    elif local_ai_configuration.mode == "lm_studio" and local_ai_configuration.setup_complete:
        model_preference = preferences_store.load_lm_studio().get("model_id")
        lm_client = LocalModelClient(
            "http://localhost:1234/v1",
            timeout_seconds=90,
            model_id=model_preference if isinstance(model_preference, str) else None,
            provider="lm_studio",
        )
    window = MainWindow(
        theme_manager.available_themes(),
        dashboard,
        preferences_store=preferences_store,
        game_state_service=game_state_service,
        character_randomizer=CharacterRandomizationService(lm_client) if lm_client else None,
        action_resolver=LocalModelActionResolver(lm_client) if lm_client else None,
        combat_narrator=LocalModelCombatNarrator(lm_client) if lm_client else None,
        travel_narrator=LocalModelTravelNarrator(lm_client) if lm_client else None,
        dialogue_narrator=LocalModelDialogueNarrator(lm_client) if lm_client else None,
        lm_client=lm_client,
        model_evaluator=(
            ModelEvaluationService(lm_client, resolved_config_dir / "model-evaluations")
            if lm_client else None
        ),
        local_ai_configuration=local_ai_configuration,
        local_ai_runtime=local_ai_runtime,
        config_dir=resolved_config_dir,
        start_on_campaigns=True,
    )
    launch_mode = "Packaged distribution" if getattr(sys, "frozen", False) else "Source checkout"
    window.show_startup_status(
        f"{launch_mode}. Storage ready at {resolved_config_dir}. "
        f"Database schema {game_state_service.database.schema_version()} ready."
    )
    if state_warning:
        window.statusBar().showMessage(state_warning)

    def apply_theme(theme_id: str) -> None:
        loaded = theme_manager.apply_theme(app, theme_id)
        window.select_theme(loaded.definition.theme_id)

    def apply_font_size(percent: int) -> None:
        normalized = min(150, max(75, int(percent)))
        scale = normalized / 100
        scaled_font = QFont(base_application_font)
        if base_application_font.pointSizeF() > 0:
            scaled_font.setPointSizeF(base_application_font.pointSizeF() * scale)
        elif base_application_font.pixelSize() > 0:
            scaled_font.setPixelSize(round(base_application_font.pixelSize() * scale))
        app.setFont(scaled_font)
        theme_manager.set_font_scale(app, scale)
        window.select_font_size(normalized)

    window.theme_requested.connect(apply_theme)
    window.font_size_requested.connect(apply_font_size)
    window.select_theme(initial.definition.theme_id)
    apply_font_size(window.font_size_preference)
    return app, window, theme_manager


def main() -> int:
    """Launch the desktop application."""

    config_dir = default_config_dir()
    log_dir = config_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=(
            logging.StreamHandler(),
            RotatingFileHandler(
                log_dir / "application.log",
                maxBytes=2_000_000,
                backupCount=3,
                encoding="utf-8",
            ),
        ),
    )
    if any(argument.startswith("--smoke-test") for argument in sys.argv):
        os.environ.setdefault("DDSIM_DISABLE_AUDIO", "1")  # smoke runs stay silent
    app, window, _theme_manager = build_application(config_dir=config_dir)
    window.show()
    if "--smoke-test-preset-campaign" in sys.argv:
        QTimer.singleShot(50, lambda: _run_character_creation_smoke(app, window, preset=True))
    elif "--smoke-test-release28" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_eight_smoke(app, window))
    elif "--smoke-test-release27" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-9-4" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-9-3" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-9-2" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-9" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-8-3" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-8-2" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-8-1" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-8" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-7" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-6" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-5" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-4" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-3" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-2" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26-1" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release26" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_six_smoke(app, window))
    elif "--smoke-test-release25-1" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_five_smoke(app, window))
    elif "--smoke-test-release25" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_five_smoke(app, window))
    elif "--smoke-test-release24" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_five_smoke(app, window))
    elif "--smoke-test-release23" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_three_smoke(app, window))
    elif "--smoke-test-release22" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_two_smoke(app, window))
    elif "--smoke-test-release21" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_one_smoke(app, window))
    elif "--smoke-test-release20" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_twenty_smoke(app, window))
    elif "--smoke-test-release19" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_nineteen_smoke(app, window))
    elif "--smoke-test-release18" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_eighteen_smoke(app, window))
    elif "--smoke-test-release17" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_seventeen_smoke(app, window))
    elif "--smoke-test-release16" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_sixteen_smoke(app, window))
    elif "--smoke-test-release15" in sys.argv:
        QTimer.singleShot(50, lambda: _run_release_fifteen_smoke(app, window))
    elif "--smoke-test-phase14" in sys.argv:
        QTimer.singleShot(50, lambda: _run_phase_fourteen_smoke(app, window))
    elif "--smoke-test-phase13" in sys.argv:
        QTimer.singleShot(50, lambda: _run_phase_thirteen_smoke(app, window))
    elif "--smoke-test-phase12" in sys.argv:
        QTimer.singleShot(50, lambda: _run_phase_twelve_smoke(app, window))
    elif "--smoke-test-phase11" in sys.argv:
        QTimer.singleShot(50, lambda: _run_phase_eleven_smoke(app, window))
    elif "--smoke-test-abilities" in sys.argv:
        QTimer.singleShot(50, lambda: _run_abilities_smoke(app, window))
    elif "--smoke-test-combat" in sys.argv:
        QTimer.singleShot(50, lambda: _run_combat_smoke(app, window))
    elif "--smoke-test-action-resolution" in sys.argv:
        QTimer.singleShot(50, lambda: _run_action_resolution_smoke(app, window))
    elif "--smoke-test-inventory-actions" in sys.argv:
        QTimer.singleShot(50, lambda: _run_inventory_action_smoke(app, window))
    elif "--smoke-test-character-creation" in sys.argv:
        QTimer.singleShot(50, lambda: _run_character_creation_smoke(app, window))
    elif "--smoke-test" in sys.argv:
        QTimer.singleShot(250, app.quit)
    return app.exec()


def _run_release_twenty_eight_smoke(app: QApplication, window: MainWindow) -> None:
    """Verify the packaged Concept T dashboard regions, conversation, journal and tooltips."""

    try:
        from dd_simulator.ui.widgets.inventory_grid import ItemHoverCard
        from dd_simulator.ui.widgets.skills_grid import AbilityHoverCard

        service = window.game_state_service
        if service is None or service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 28 database startup check failed")
        for region in (
            "character_strip", "paperdoll_panel", "skill_detail_list", "inventory_card",
            "powers_card", "scene_view", "conversation_view",
        ):
            if getattr(window, region, None) is None:
                raise RuntimeError(f"Packaged Concept T region is missing: {region}")
        messages = window.dashboard.narrative.messages
        if not messages or len(window.conversation_view.messages) != len(messages):
            raise RuntimeError("Packaged conversation does not show the demo messages")
        window._show_navigation("journal")  # noqa: SLF001 - packaged smoke boundary
        if window.current_page != "journal" or window.navigation_pages["journal"] is None:
            raise RuntimeError("Packaged Journal page did not open")
        item = next((slot for slot in window.dashboard.inventory if slot.name), None)
        if item is None or not window.dashboard.abilities:
            raise RuntimeError("Packaged dashboard has no item or ability for tooltips")
        ItemHoverCard(item, window)
        AbilityHoverCard(window.dashboard.abilities[0], window)
        campaign_id = service.campaigns.active_campaign_id()
        older = service.older_messages(campaign_id, window.dashboard.location.turn_number)
        if not isinstance(older, tuple):
            raise RuntimeError("Packaged older_messages did not return a tuple")
    except Exception:
        LOGGER.exception("Packaged Release 28 smoke test failed")
        app.exit(28)
        return
    window.close()
    app.quit()


def _run_release_twenty_six_smoke(app: QApplication, window: MainWindow) -> None:
    """Verify both packaged simple themes and the current dashboard boundary."""

    try:
        service = window.game_state_service
        if service is None or service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 26 database startup check failed")
        window._show_navigation("dashboard")  # noqa: SLF001 - packaged smoke boundary
        for theme_id in ("high_fantasy", "modern_proof"):
            window.theme_requested.emit(theme_id)
            app.processEvents()
            if app.property("themeId") != theme_id:
                raise RuntimeError(f"Packaged theme could not be applied: {theme_id}")
            if "QFrame#itemHoverSurface" not in app.styleSheet():
                raise RuntimeError(f"Packaged item tooltip surface is missing: {theme_id}")
        if len(window.inventory_card.grid.slots) < 25 or window.inventory_card.grid.columns != 5:
            raise RuntimeError("Packaged inventory card does not show a 5x5 bag")
        if "character_sheet" not in window.scene_view.tabs.buttons:
            raise RuntimeError("Packaged Character Sheet navigation is unavailable")
        if window.findChild(QWidget, "characterSheetSurface") is None:
            raise RuntimeError("Packaged Character Sheet is incomplete")
        if not window.dashboard.combat_skills or any(
            not action.stats for action in window.dashboard.combat_skills
        ):
            raise RuntimeError("Packaged ability card stats are incomplete")
        skill_names = (
            "Attack", "Strength", "Defense", "Ranged", "Survival", "Magic", "Herblore",
            "Crafting", "Warden's Mark", "Quick Shot", "Field Dressing", "Shield Wall",
        )
        skill_icons = {resolve_icon(name, category="skill").index for name in skill_names}
        if len(skill_icons) != len(skill_names):
            raise RuntimeError("Packaged skill icons are not distinct")
        if window.findChildren(QLabel, "resourceIcon"):
            raise RuntimeError("Resource icons remain in the packaged summary")
        if (
            "Qwen3-4B" not in window.local_ai_setup_panel.recommended_button.text()
            or "Gemma 4 E4B" not in window.local_ai_setup_panel.large_model_button.text()
        ):
            raise RuntimeError("Packaged local AI recommendations are incomplete")
        if window.scene_view.image_path is None:
            raise RuntimeError("Packaged location catalog image did not render")
        initial_point_size = app.font().pointSizeF()
        window.settings_panel.font_size_increase.click()
        app.processEvents()
        if app.font().pointSizeF() <= initial_point_size:
            raise RuntimeError("Packaged global font scaling did not apply")
        missing_location_art = [
            archetype
            for archetype in LOCATION_ARCHETYPES
            if not (LOCATION_ART_ROOT / archetype / f"{archetype}_base.png").is_file()
        ]
        if missing_location_art:
            raise RuntimeError(
                "Packaged location catalog is incomplete: "
                + ", ".join(sorted(missing_location_art))
            )
        if len(window.findChildren(QProgressBar, "codexResourceBar")) != 5:
            raise RuntimeError("Packaged resource bars are incomplete")
        if any(min(window_splitter.sizes()) <= 0 for window_splitter in (
            window.concept_splitter,
        )):
            raise RuntimeError("Packaged splitters are not resizable")
    except Exception:
        LOGGER.exception("Packaged Release 26 smoke test failed")
        app.exit(26)
        return
    window.close()
    app.quit()


def _run_release_twenty_five_smoke(app: QApplication, window: MainWindow) -> None:
    """Verify packaged semantic item icons, natural narration, and live splitters."""

    try:
        service = window.game_state_service
        if service is None or service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 25.1 database startup check failed")
        window.theme_requested.emit("high_fantasy")
        window._show_navigation("dashboard")  # noqa: SLF001 - packaged smoke boundary
        app.processEvents()
        if app.property("themeId") != "high_fantasy":
            raise RuntimeError("Packaged Modern Fantasy Simple theme could not be applied")
        potion = resolve_icon("Health Potion", "common", "potion", "healing")
        arrows = resolve_icon("Arrows", "common", "ammunition", "ranged")
        if potion is None or potion.index != 919 or arrows is None or arrows.subtype != "arrow":
            raise RuntimeError("Packaged semantic item manifest is unavailable")
        visible_icons = [
            label for label in window.findChildren(QLabel, "itemIcon")
            if label.pixmap() is not None and not label.pixmap().isNull()
        ]
        if not visible_icons:
            raise RuntimeError("Packaged Default item icons are unavailable")
        cleaned = normalize_narrative_segment(
            "narrative",
            "`The merchant nods. ‘Welcome, traveler!’ The cart creaks.`",
        )
        if tuple(value.kind for value in cleaned) != ("narrative",):
            raise RuntimeError("Packaged narrative model-kind preservation is unavailable")
        if any("`" in value.text for value in cleaned):
            raise RuntimeError("Packaged narration retained model backticks")
        spoken = normalize_narrative_segment(
            "spoken",
            '*My wares offer necessity and "delight" in equal measure.*',
        )
        if len(spoken) != 1 or spoken[0].kind != "spoken":
            raise RuntimeError("Packaged spoken narration was fragmented")
        if any(min(window_splitter.sizes()) <= 0 for window_splitter in (
            window.concept_splitter,
        )):
            raise RuntimeError("Packaged splitters are not resizable")
    except Exception:
        LOGGER.exception("Packaged Release 25.1 smoke test failed")
        app.exit(25)
        return
    window.close()
    app.quit()


def _run_release_twenty_three_smoke(app: QApplication, window: MainWindow) -> None:
    """Verify the packaged Character Creation reorganization and focus skills."""

    try:
        service = window.game_state_service
        if service is None or service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 23 database startup check failed")
        window._show_navigation("character_creation")  # noqa: SLF001
        panel = window.character_creation_panel
        app.processEvents()
        expected_tabs = (
            "1. Appearance, Identity, Skills & Role",
            "2. Equipment",
            "3. Campaign",
            "4. Final Review",
        )
        if tuple(
            panel.tabs.tabText(index).replace("&&", "&")
            for index in range(panel.tabs.count())
        ) != expected_tabs:
            raise RuntimeError("Packaged character-creation tabs are out of order")
        buttons = panel.findChildren(QPushButton, "focusSkillButton")
        if len(buttons) != 8:
            raise RuntimeError("Packaged focus-skill buttons are incomplete")
        for button in buttons[:3]:
            button.click()
        if sum(button.isChecked() for button in buttons) != 3 or any(
            button.isEnabled() and not button.isChecked() for button in buttons
        ):
            raise RuntimeError("Packaged focus-skill limit is incorrect")
        buttons[0].click()
        if not all(button.isEnabled() for button in buttons):
            raise RuntimeError("Packaged focus-skill reselection is blocked")
        for object_name in (
            "randomizeCampaignButton", "randomizeCampaignNameButton",
            "randomizeCharacterNameButton", "campaignCreationLeftForm",
            "campaignCreationRightForm", "characterCreationLeftForm",
            "characterCreationRightForm",
        ):
            if window.findChild(QWidget, object_name) is None:
                raise RuntimeError(f"Packaged Release 23 control is missing: {object_name}")
    except Exception:
        LOGGER.exception("Packaged Release 23 smoke test failed")
        app.exit(23)
        return
    window.close()
    app.quit()


def _run_release_twenty_two_smoke(app: QApplication, window: MainWindow) -> None:
    """Verify packaged skill progress and consolidated Settings navigation."""

    try:
        service = window.game_state_service
        if service is None or service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 22 database startup check failed")
        bars = window.skill_detail_list.findChildren(QProgressBar, "skillDetailXpBar")
        if len(bars) != len(window.dashboard.skills):
            raise RuntimeError("Packaged skill XP bars are incomplete")
        if window.findChild(QWidget, "bottomNavigationBar") is not None:
            raise RuntimeError("Packaged bottom navigation was not retired")
        if {"skills", "quests", "campaigns"} & set(window.page_indices):
            raise RuntimeError("Redundant packaged navigation pages remain registered")
        if (
            window.current_page != "settings"
            or not window.settings_page.isAncestorOf(window.campaign_browser)
            or abs(window.settings_panel.width() - window.campaign_browser.width()) >= 60
        ):
            raise RuntimeError("Packaged campaign controls are not in Settings")
    except Exception:
        LOGGER.exception("Packaged Release 22 smoke test failed")
        app.exit(22)
        return
    window.close()
    app.quit()


def _run_release_twenty_one_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged crafting, result acknowledgement, and People splitter layout."""

    try:
        service = window.game_state_service
        if service is None or service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 21 database startup check failed")
        dashboard = service.load_active_dashboard()
        recipe = next(value for value in dashboard.crafting_recipes if value.available)
        result = service.craft_recipe(recipe.id)
        dashboard = service.load_active_dashboard()
        if dashboard.pending_crafting_result is None:
            raise RuntimeError("Packaged crafting result did not persist")
        window._reload_dashboard(dashboard, target_page="people")  # noqa: SLF001
        window._show_pending_crafting_result()  # noqa: SLF001
        app.processEvents()
        for object_name in (
            "craftingUtilityPage", "craftingRecipeCard", "craftingResultsDialog",
            "peopleTradeConversationSplitter", "merchantCenteredContainer",
        ):
            if window.findChild(QWidget, object_name) is None:
                raise RuntimeError(f"Packaged Release 21 control is missing: {object_name}")
        trade = window.findChild(QWidget, "merchantTradePanel")
        people = window.navigation_pages["people"]
        if trade is None or abs(trade.width() * 3 - people.width()) >= 60:
            raise RuntimeError("Packaged Trade panel is not one-third People-page width")
        service.acknowledge_crafting_result(result.id)
        dialog = window.findChild(QWidget, "craftingResultsDialog")
        if dialog is not None:
            dialog.allow_close()
            dialog.close()
    except Exception:
        LOGGER.exception("Packaged Release 21 smoke test failed")
        app.exit(21)
        return
    window.close()
    app.quit()


def _run_release_twenty_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged commerce persistence and centered navigation controls."""

    try:
        service = window.game_state_service
        if service is None or service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 20 database startup check failed")
        dashboard = service.load_active_dashboard()
        conversation = next(
            value for value in dashboard.npc_conversations
            if value.npc.id == "npc-roadside-merchant"
        )
        if conversation.merchant is None or not conversation.merchant.stock:
            raise RuntimeError("Packaged merchant inventory is unavailable")
        offer = conversation.merchant.stock[0]
        before = dashboard.player.currency
        result = service.complete_trade(conversation.npc.id, "buy", offer.id)
        if result.remaining_currency >= before:
            raise RuntimeError("Packaged purchase did not debit authoritative currency")
        dashboard = service.load_active_dashboard()
        window._reload_dashboard(dashboard, target_page="people")  # noqa: SLF001
        app.processEvents()
        for object_name in (
            "merchantTradePanel", "npcCenteredFooter", "pageActionBar",
        ):
            if window.findChild(QWidget, object_name) is None:
                raise RuntimeError(f"Packaged Release 20 control is missing: {object_name}")
    except Exception:
        LOGGER.exception("Packaged Release 20 smoke test failed")
        app.exit(20)
        return
    app.quit()


def _run_release_nineteen_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged first-run status, model loading controls, and Settings layout."""

    try:
        service = window.game_state_service
        if service is None or service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 19 database startup check failed")
        if "Storage ready" not in window.settings_panel.startup_status.text():
            raise RuntimeError("Packaged Release 19 startup readiness is unavailable")
        window._models_scanned = True  # noqa: SLF001 - offline smoke fixture
        window.settings_panel.set_models(
            (LocalModelModelInfo("release-19-smoke-model", "Smoke Model", False),),
            None,
        )
        window.controller.navigate("settings")
        app.processEvents()
        if not window.settings_panel.model_load_button.isEnabled():
            raise RuntimeError("Installed model cannot be selected for loading")
        if abs(window.settings_panel.width() * 2 - window.settings_page.width()) >= 30:
            raise RuntimeError("Settings page is not constrained to the left half")
        for object_name in (
            "localModelSelector",
            "loadLocalModelButton",
            "startupReadinessStatus",
            "settingsScrollArea",
        ):
            if window.findChild(QWidget, object_name) is None:
                raise RuntimeError(f"Packaged Release 19 control is missing: {object_name}")
    except Exception:
        LOGGER.exception("Packaged Release 19 smoke test failed")
        app.exit(19)
        return
    app.quit()


def _run_release_eighteen_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged model controls and equipment rarity presentation offline."""

    try:
        if window.lm_client is None or window.model_evaluator is None:
            raise RuntimeError("Packaged Release 18 local model services are unavailable")
        window.lm_client.select_model("release-18-smoke-model")
        if window.lm_client.preferred_model_id() != "release-18-smoke-model":
            raise RuntimeError("Explicit model selection did not reach the shared client")
        for object_name in (
            "localModelSelector",
            "refreshLocalModelsButton",
            "evaluateLocalModelButton",
        ):
            if window.findChild(QWidget, object_name) is None:
                raise RuntimeError(f"Packaged model control is missing: {object_name}")
        equipment_slots = window.findChildren(QWidget, "equipmentSlot")
        equipped_with_item = next(
            (slot for slot in equipment_slots if slot.property("empty") is False),
            None,
        )
        if equipped_with_item is None or not equipped_with_item.property("rarity"):
            raise RuntimeError("Packaged equipment rarity presentation is unavailable")
        if 'QFrame#equipmentSlot[rarity="uncommon"]' not in app.styleSheet():
            raise RuntimeError("Packaged theme lacks equipment rarity selectors")
    except Exception:
        LOGGER.exception("Packaged Release 18 smoke test failed")
        app.exit(18)
        return
    app.quit()


def _run_release_seventeen_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged checkpoints, repair, replay, and People dialogue persistence."""

    try:
        service = window.game_state_service
        if service is None or service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 17 schema/service is unavailable")
        dashboard = service.load_active_dashboard()
        first_id = dashboard.inventory_preview[0].id
        checkpoint = service.create_checkpoint("Packaged Release 17 smoke")
        if not checkpoint.backup_path.is_file():
            raise RuntimeError("Packaged named checkpoint backup was not created")
        service.move_inventory_item(0, 10)
        replay = service.verify_checkpoint_replay(checkpoint.id)
        if not replay.valid or replay.events_verified < 1:
            raise RuntimeError("Packaged audit/checksum replay did not validate")
        dashboard = service.load_checkpoint(checkpoint.id)
        if dashboard.inventory_preview[0].id != first_id:
            raise RuntimeError("Packaged checkpoint did not restore exact inventory state")
        with service.database.transaction() as connection:
            connection.execute(
                "UPDATE locations SET discovered = 0, visit_count = 0 "
                "WHERE campaign_id = ? AND is_current = 1",
                (service.campaigns.active_campaign_id(),),
            )
        if not service.inspect_campaign_repair():
            raise RuntimeError("Packaged repair inspection did not identify a discrepancy")
        repair = service.repair_campaign()
        if repair.status != "applied" or service.inspect_campaign_repair():
            raise RuntimeError("Packaged safe repair did not restore campaign consistency")
        dialogue = service.resolve_npc_dialogue(
            "npc-roadside-merchant", "Do you sell any headgear?"
        )
        if not dialogue.player_text or not service.load_active_dashboard().npc_conversations:
            raise RuntimeError("Packaged People dialogue did not persist player-first history")
        for object_name in (
            "createCheckpointButton", "loadCheckpointButton",
            "repairCampaignButton", "verifyReplayButton",
        ):
            if window.findChild(QWidget, object_name) is None:
                raise RuntimeError(f"Packaged reliability control is missing: {object_name}")
    except Exception:
        LOGGER.exception("Packaged Release 17 smoke test failed")
        app.exit(17)
        return
    app.quit()


def _run_release_sixteen_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged Release 16 visual persistence and UI refinements."""

    try:
        service = window.game_state_service
        if service is None:
            raise RuntimeError("Packaged Release 16 state service is unavailable")
        if service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 16 compatibility smoke did not migrate")
        dashboard = service.load_active_dashboard()
        details = [
            label.text()
            for label in window.findChildren(QLabel, "equipmentItemDetails")
        ]
        if not any("Durability" in detail for detail in details):
            raise RuntimeError("Packaged equipped durability display did not load")
        if not any("Quantity" in detail for detail in details):
            raise RuntimeError("Packaged equipped ammunition quantity did not load")

        with service.database.connect() as connection:
            current_location = connection.execute(
                "SELECT id FROM locations WHERE campaign_id = ? AND is_current = 1",
                (service.campaigns.active_campaign_id(),),
            ).fetchone()
        if current_location is None or service.visuals.assets_root is None:
            raise RuntimeError("Packaged Visual Registry storage is unavailable")
        source = service.visuals.assets_root / "release16-smoke-source.png"
        image = QImage(24, 18, QImage.Format.Format_RGB32)
        image.fill(QColor("#4d6d3b"))
        if not image.save(str(source), "PNG"):
            raise RuntimeError("Packaged Visual Registry could not write its source image")
        campaign_id = service.campaigns.active_campaign_id()
        if campaign_id is None:
            raise RuntimeError("Packaged Visual Registry has no active campaign")
        staged = service.visuals.stage_asset(
            campaign_id=campaign_id,
            asset_kind="location",
            subject_type="location",
            subject_id=str(current_location["id"]),
            source_path=source,
            source="packaged-smoke",
        )
        confirmed = service.visuals.confirm_asset(staged.id)
        dashboard = service.load_active_dashboard()
        if dashboard.location.visual is None or dashboard.location.visual.id != confirmed.id:
            raise RuntimeError("Packaged confirmed location visual did not project")
        window._reload_dashboard(dashboard)
        app.processEvents()
        location_visual = window.findChild(QLabel, "locationVisualPlaceholder")
        if (
            location_visual is None
            or location_visual.property("visualState") != "confirmed"
            or location_visual.pixmap() is None
            or location_visual.pixmap().isNull()
        ):
            raise RuntimeError("Packaged confirmed location visual did not render")
    except Exception:
        LOGGER.exception("Packaged Release 16 smoke test failed")
        app.exit(16)
        return
    app.quit()


def _run_release_fifteen_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged Release 15 item details, compatibility, and skills layout."""

    try:
        service = window.game_state_service
        if service is None:
            raise RuntimeError("Packaged Release 15 state service is unavailable")
        if service.database.schema_version() != LATEST_SCHEMA_VERSION:
            raise RuntimeError("Packaged Release 15 compatibility smoke did not migrate")
        dashboard = service.load_active_dashboard()
        lockpick = next(item for item in dashboard.inventory_preview if item.name == "Lockpick")
        if lockpick.category != "tool" or not lockpick.description or lockpick.weight <= 0:
            raise RuntimeError("Packaged deterministic item details are incomplete")
        if window.findChild(QWidget, "playerSkillsRegion") is None or window.findChild(
            QWidget, "combatSkillsRegion"
        ) is None:
            raise RuntimeError("Packaged Release 15 Skills regions did not load")
        hover_card = window.findChild(QWidget, "itemHoverCard")
        if hover_card is None or len(hover_card.findChildren(QWidget, "itemHoverDetail")) != 7:
            raise RuntimeError("Packaged two-column item hover card did not load")
        font_button = window.settings_panel.font_size_increase
        if not font_button.isEnabled():
            raise RuntimeError("Packaged font-size preference is disabled")
        original_stylesheet = app.styleSheet()
        target_size = min(150, window.font_size_preference + 5)
        window.settings_panel.select_font_size(target_size)
        window.settings_panel.font_size_requested.emit(target_size)
        app.processEvents()
        if window.font_size_preference != target_size or app.styleSheet() == original_stylesheet:
            raise RuntimeError("Packaged font-size preference did not apply live")
        service.execute_item_command(
            ItemCommand(ItemAction.UNEQUIP, 0, destination_index=27)
        )
        service.execute_item_command(
            ItemCommand(ItemAction.EQUIP, 27, destination_index=1)
        )
        dashboard = service.load_active_dashboard()
        if dashboard.equipment[1].item_name != "Iron Dagger":
            raise RuntimeError("Packaged compatible inventory-to-equipment move failed")
        if dashboard.inventory_preview[27].name != "Oak Shield":
            raise RuntimeError("Packaged equipment replacement did not return to the bag")
    except Exception:
        LOGGER.exception("Packaged Release 15 smoke test failed")
        app.exit(15)
        return
    app.quit()


def _run_phase_fourteen_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged inventory separation, NPC dialogue, skills, and map repair."""

    try:
        service = window.game_state_service
        if service is None:
            raise RuntimeError("Packaged Phase 14 state service is unavailable")
        dashboard = service.load_active_dashboard()
        if len(dashboard.inventory_preview) != 36:
            raise RuntimeError("Packaged inventory did not project a 36-slot page")
        if any(item.name == "Iron Dagger" for item in dashboard.inventory_preview):
            raise RuntimeError("Packaged equipped item still appears in inventory")
        if dashboard.equipment[0].item_name != "Iron Dagger":
            raise RuntimeError("Packaged stable equipment link was lost")
        first_id = dashboard.inventory_preview[0].id
        service.move_inventory_item(0, 27)
        if service.load_active_dashboard().inventory_preview[27].id != first_id:
            raise RuntimeError("Packaged inventory drag mutation did not persist")
        service.auto_sort_inventory()
        service.execute_item_command(
            ItemCommand(ItemAction.UNEQUIP, 7, destination_index=27)
        )
        dashboard = service.load_active_dashboard()
        if dashboard.equipment[7].item_name is not None:
            raise RuntimeError("Packaged equipment drag did not clear the equipment slot")
        if dashboard.inventory_preview[27].name != "Silver Ring":
            raise RuntimeError("Packaged equipment drag ignored its inventory destination")
        service.auto_sort_inventory()
        dashboard = service.load_active_dashboard()
        if dashboard.equipment[0].item_name != "Iron Dagger" or any(
            item.name == "Iron Dagger" for item in dashboard.inventory_preview
        ):
            raise RuntimeError("Packaged Auto-Sort included equipped records")
        dialogue = service.resolve_npc_dialogue(
            "npc-roadside-merchant", "Ask what they know about this area."
        )
        dashboard = service.load_active_dashboard()
        if not dialogue.npc_text or not dashboard.npc_conversations:
            raise RuntimeError("Packaged NPC conversation did not persist")
        if not dashboard.combat_skills:
            raise RuntimeError("Packaged combat skills did not project")
        with service.database.transaction() as connection:
            connection.execute(
                "UPDATE locations SET is_current = 0 WHERE campaign_id = ?",
                (DEMO_CAMPAIGN_ID,),
            )
            connection.execute(
                "UPDATE locations SET is_current = 1, discovered = 0 "
                "WHERE id = 'location-greystone-keep'"
            )
        dashboard = service.load_active_dashboard()
        if dashboard.world_map is None or dashboard.world_map.current_location_id != "location-greystone-keep":
            raise RuntimeError("Packaged map did not highlight Greystone Keep")
        if "people" not in window.page_indices or "crafting" not in window.page_indices:
            raise RuntimeError("Packaged Phase 14 navigation did not load")
    except Exception:
        LOGGER.exception("Packaged Phase 14 smoke test failed")
        app.exit(10)
        return
    app.quit()


def _run_phase_thirteen_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged route travel, map projection, history, and camping."""

    try:
        service = window.game_state_service
        if service is None:
            raise RuntimeError("Packaged travel service is unavailable")
        with service.database.transaction() as connection:
            connection.execute(
                "UPDATE travel_routes SET danger_rating = 0 "
                "WHERE id = 'route-road-keep'"
            )
        result = service.travel_to("route-road-keep")
        dashboard = service.load_active_dashboard()
        if result.encounter_required or dashboard.location.name != "Greystone Keep":
            raise RuntimeError("Packaged route travel did not persist")
        if dashboard.world_map is None or dashboard.world_map.current_location_id != "location-greystone-keep":
            raise RuntimeError("Packaged world-map projection did not update")
        with service.database.connect() as connection:
            history = connection.execute(
                "SELECT destination_location_id FROM travel_history WHERE id = ?",
                (result.history_id,),
            ).fetchone()
        if history is None or history["destination_location_id"] != "location-greystone-keep":
            raise RuntimeError("Packaged travel history did not persist")
        service.travel_to("route-road-keep")
        camp = service.make_camp(duration_minutes=240)
        if not camp.summary or service.load_active_dashboard().location.name != "Greystone Road":
            raise RuntimeError("Packaged camp recovery did not persist")
    except Exception:
        LOGGER.exception("Packaged Phase 13 smoke test failed")
        app.exit(9)
        return
    app.quit()


def _run_phase_twelve_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged quest completion, rewards, claims, and projection."""

    try:
        service = window.game_state_service
        if service is None:
            raise RuntimeError("Packaged quest service is unavailable")
        campaign_id = service.campaigns.active_campaign_id()
        if not campaign_id:
            raise RuntimeError("Packaged quest smoke has no active campaign")
        with service.database.transaction() as connection:
            connection.execute(
                "UPDATE quests SET status = 'active', completed_at = NULL, selected = 1, "
                "reward_experience = 10, reward_currency = 5, "
                "reward_items_json = '[\"Moonstone\"]' WHERE id = 'quest-heirloom'"
            )
            connection.execute(
                "DELETE FROM quest_rewards WHERE quest_id = 'quest-heirloom'"
            )
            connection.execute(
                "UPDATE quest_objectives SET optional = 1 WHERE quest_id = 'quest-heirloom'"
            )
            connection.execute(
                "UPDATE quest_objectives SET optional = 0, completed = 0, current_count = 0, "
                "required_count = 1, trigger_type = 'custom_action', "
                "trigger_target = 'phase twelve' WHERE id = 'objective-0'"
            )
            updates = progress_quests(
                connection,
                campaign_id,
                "custom_action",
                detail="Complete the phase twelve packaged smoke objective.",
            )
        if not any("Quest completed" in update for update in updates):
            raise RuntimeError("Packaged quest objective did not complete")
        dashboard = service.load_active_dashboard()
        reward = dashboard.pending_quest_reward
        if reward is None or reward.experience != 10 or reward.currency != 5:
            raise RuntimeError("Packaged quest reward did not project")
        if not reward.items:
            raise RuntimeError("Packaged quest item reward did not project")
        service.claim_quest_reward_item(reward.items[0].id)
        service.acknowledge_quest_reward(reward.id)
        dashboard = service.load_active_dashboard()
        if dashboard.pending_quest_reward is not None:
            raise RuntimeError("Packaged quest reward acknowledgement did not persist")
        completed = next(quest for quest in dashboard.quest_list if quest.id == "quest-heirloom")
        if completed.status != "completed":
            raise RuntimeError("Packaged completed quest did not persist")
    except Exception:
        LOGGER.exception("Packaged Phase 12 smoke test failed")
        app.exit(8)
        return
    app.quit()


def _run_character_creation_smoke(
    app: QApplication, window: MainWindow, *, preset: bool = False
) -> None:
    """Exercise the packaged form, transaction, projection, and dashboard reload."""

    try:
        panel = window.character_creation_panel
        if preset:
            window.controller.navigate("settings")
            preset_item = window.campaign_browser.preset_list.item(0)
            if preset_item is None:
                raise RuntimeError("Packaged preset was not listed in Campaigns")
            window.campaign_browser.preset_list.itemClicked.emit(preset_item)
            if window.current_page != "character_creation":
                raise RuntimeError("Preset selection did not open character creation")
        else:
            window.controller.navigate("character_creation")
        panel.set_models(
            (
                LocalModelModelInfo(
                    "creation-smoke-model",
                    "Creation Smoke Model",
                    True,
                    "creation-smoke-instance",
                ),
            ),
            "creation-smoke-instance",
        )
        if preset:
            if panel.preset_selector.count() != 1:
                raise RuntimeError("Preset creation exposed an invalid campaign source")
            window.character_randomizer = None
        else:
            panel.campaign_name.setText("Packaged Character Smoke Test")
            panel.campaign_description.setPlainText(
                "A local smoke-test adventure begins at a guarded frontier inn."
            )
        panel.character_name.setText("Seren Vale")
        panel.age.setValue(24)
        panel.body.setPlainText("Tall and athletic")
        panel.face.setPlainText("Grey eyes and dark braided hair")
        panel.clothing.setPlainText("Weathered traveling clothes")
        panel.equipment_fields["primary_weapon"].setCurrentText("Longsword")
        panel.content_preferences.setPlainText("Exclude graphic injury")
        for skill in ("Attack", "Ranged", "Survival"):
            panel.skill_buttons[skill].click()
        panel.personality_buttons["Brave"].click()
        panel.ability_scores.update({
            "Strength": 10, "Dexterity": 15, "Constitution": 13,
            "Intelligence": 8, "Wisdom": 15, "Charisma": 10,
        })
        panel._update_ability_controls()
        panel.review_confirmed.setChecked(True)
        panel._complete()
        if window.dashboard.player.name != "Seren Vale":
            raise RuntimeError("Created character did not reach the dashboard")
        active = window.game_state_service.campaigns.active_campaign_id()
        if active is None:
            raise RuntimeError("Created campaign was not made active")
        reloaded = window.game_state_service.load_campaign(active)
        if reloaded.player.name != "Seren Vale":
            raise RuntimeError("Created character did not reload from SQLite")
        if preset and (
            not reloaded.is_preset_campaign
            or reloaded.campaign_name != "The Last Orrery of Sol"
            or len(reloaded.quest_list) != 5
            or "moon" not in " ".join(reloaded.narrative.paragraphs).casefold()
        ):
            raise RuntimeError("Packaged Last Orrery preset did not seed or project")
    except Exception:
        LOGGER.exception("Packaged character-creation smoke test failed")
        app.exit(2)
        return
    app.quit()


def _run_inventory_action_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise a packaged transactional item use and projection refresh."""

    try:
        result = window.game_state_service.execute_item_command(
            ItemCommand(ItemAction.USE, 7)
        )
        dashboard = window.game_state_service.load_active_dashboard()
        if result.item_name != "Torch" or dashboard.inventory_preview[7].quantity != 3:
            raise RuntimeError("Packaged inventory quantity did not update")
        if not any("Lit a Torch" in event.summary for event in dashboard.recent_events):
            raise RuntimeError("Packaged inventory event was not committed")
        window.game_state_service.execute_item_command(
            ItemCommand(ItemAction.UNEQUIP, 0)
        )
        equipped = window.game_state_service.execute_item_command(
            ItemCommand(ItemAction.EQUIP, 0)
        )
        dashboard = window.game_state_service.load_active_dashboard()
        if equipped.item_name != "Iron Dagger" or dashboard.equipment[0].item_name != "Iron Dagger":
            raise RuntimeError("Packaged inventory equip did not update")
    except Exception:
        LOGGER.exception("Packaged inventory-action smoke test failed")
        app.exit(3)
        return
    app.quit()


def _run_action_resolution_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise the packaged structured turn validator and atomic commit."""

    class SmokeProvider:
        def resolve_action(self, **_kwargs):  # type: ignore[no-untyped-def]
            return ActionOutcome(
                narration="The road remains quiet as the adventurer studies the horizon.",
                state_changes=(
                    ProposedStateChange(
                        operation="examine_item",
                        target_type="inventory_item",
                        target_id="item-13",
                        field=None,
                        value=True,
                        reason="The letter is examined without consuming it.",
                    ),
                    ProposedStateChange(
                        operation="spend_resource",
                        target_type="resource",
                        target_id="resource-stamina",
                        field="current_value",
                        value=2,
                        reason="Careful scouting requires effort.",
                    ),
                ),
                quest_notes=(),
                suggested_actions=(
                    "Continue scouting",
                    "Return to the merchant",
                    "Inspect the roadside",
                    "Listen for movement",
                    "Study the horizon",
                    "Rest briefly",
                ),
            )

    try:
        result = window.game_state_service.resolve_player_action(
            "Scout the road ahead",
            SmokeProvider(),
        )
        dashboard = window.game_state_service.load_active_dashboard()
        stamina = next(
            resource
            for resource in dashboard.sidebar_resources
            if resource.resource_type == "stamina"
        )
        if stamina.current != 26 or not result.turn_id.startswith("turn-"):
            raise RuntimeError("Packaged action state did not commit")
        if dashboard.recent_events[-1].category != "action":
            raise RuntimeError("Packaged action event did not reload")
        if len(dashboard.narrative.messages) < 2:
            raise RuntimeError("Packaged transcript did not reload")
        if dashboard.narrative.messages[-2].kind != "player":
            raise RuntimeError("Packaged transcript order was invalid")
        if not any("Examined Merchant Letter" in summary for summary in result.state_summaries):
            raise RuntimeError("Packaged item examination did not resolve")
    except Exception:
        LOGGER.exception("Packaged action-resolution smoke test failed")
        app.exit(4)
        return
    app.quit()


def _run_combat_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged initiative, combat, progression, and transcript persistence."""

    try:
        rolls = iter((20, 1, 20, 4, 4))
        window.game_state_service.combat = CombatService(
            window.game_state_service.database,
            roll=lambda _minimum, _maximum: next(rolls),
        )
        window.game_state_service.start_combat(
            enemies=(
                EnemySpec(
                    "Packaged Training Goblin",
                    maximum_health=6,
                    armor_class=10,
                    attack_bonus=2,
                    damage_die_size=4,
                    distance_feet=5,
                ),
            )
        )
        dashboard = window.game_state_service.load_active_dashboard()
        if dashboard.combat is None or dashboard.combat.status != "active":
            raise RuntimeError("Packaged combat encounter did not start")
        enemy = next(
            combatant for combatant in dashboard.combat.combatants
            if combatant.side == "enemy"
        )
        result = window.game_state_service.execute_combat_command(
            CombatCommand(CombatAction.ABILITY, target_id=enemy.id)
        )
        dashboard = window.game_state_service.load_active_dashboard()
        if result.status != "victory" or dashboard.combat is None:
            raise RuntimeError("Packaged combat did not reach victory")
        if dashboard.combat.combatants[-1].status != "defeated":
            raise RuntimeError("Packaged enemy state did not persist")
        stamina = next(
            resource for resource in dashboard.player.resources
            if resource.resource_type == "stamina"
        )
        if stamina.current != 23:
            raise RuntimeError("Packaged combat resource cost did not persist")
        if not any(message.kind == "combat" for message in dashboard.narrative.messages):
            raise RuntimeError("Packaged combat transcript did not persist")
        if dashboard.combat.reward is None or dashboard.combat.reward.experience <= 0:
            raise RuntimeError("Packaged encounter rewards did not persist")
    except Exception:
        LOGGER.exception("Packaged combat smoke test failed")
        app.exit(5)
        return
    app.quit()


def _run_phase_eleven_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged encounter generation, introduction, and preparation."""

    try:
        window.game_state_service.combat = CombatService(
            window.game_state_service.database,
            roll=lambda minimum, maximum: (minimum + maximum) // 2,
        )
        result = window.game_state_service.start_combat()
        dashboard = window.game_state_service.load_active_dashboard()
        if result.status != "active" or dashboard.combat is None:
            raise RuntimeError("Packaged generated encounter did not start")
        if not dashboard.combat.generated or dashboard.combat.intro_complete:
            raise RuntimeError("Packaged encounter introduction state was incorrect")
        if not dashboard.combat.introduction or not dashboard.combat.terrain:
            raise RuntimeError("Packaged generated encounter lacks scene context")
        if not all(
            combatant.archetype_key
            for combatant in dashboard.combat.combatants
            if combatant.side == "enemy"
        ):
            raise RuntimeError("Packaged enemy archetypes did not project")
        window.game_state_service.execute_combat_command(
            CombatCommand(CombatAction.PREPARE, preparation="scout")
        )
        dashboard = window.game_state_service.load_active_dashboard()
        if dashboard.combat is None or not dashboard.combat.intro_complete:
            raise RuntimeError("Packaged encounter preparation did not persist")
        if dashboard.combat.preparation_choice != "scout":
            raise RuntimeError("Packaged preparation choice did not reload")
        with window.game_state_service.database.connect() as connection:
            if connection.execute(
                "SELECT COUNT(*) FROM enemy_archetypes"
            ).fetchone()[0] < 8:
                raise RuntimeError("Packaged enemy catalog was not synchronized")
    except Exception:
        LOGGER.exception("Packaged Phase 11 smoke test failed")
        app.exit(7)
        return
    app.quit()


def _run_abilities_smoke(app: QApplication, window: MainWindow) -> None:
    """Exercise packaged class catalog, spell resources, and effect persistence."""

    try:
        with window.game_state_service.database.transaction() as connection:
            connection.execute(
                "UPDATE characters SET character_class = 'Mage' WHERE is_player = 1"
            )
        rolls = iter((20, 1, 3, 4, 1))
        window.game_state_service.combat = CombatService(
            window.game_state_service.database,
            roll=lambda _minimum, _maximum: next(rolls),
        )
        window.game_state_service.start_combat(
            enemies=(
                EnemySpec(
                    "Packaged Spell Target", maximum_health=30, armor_class=18,
                    attack_bonus=0, damage_die_size=4, distance_feet=5,
                ),
            )
        )
        dashboard = window.game_state_service.load_active_dashboard()
        if dashboard.combat is None:
            raise RuntimeError("Packaged spell encounter did not start")
        enemy = next(
            combatant for combatant in dashboard.combat.combatants
            if combatant.side == "enemy"
        )
        result = window.game_state_service.execute_combat_command(
            CombatCommand(
                CombatAction.SPELL, target_id=enemy.id,
                ability_key="magic_missile",
            )
        )
        dashboard = window.game_state_service.load_active_dashboard()
        mana = next(
            resource for resource in dashboard.player.resources
            if resource.resource_type == "mana"
        )
        slots = next(
            resource for resource in dashboard.player.resources
            if resource.resource_type == "spell_slots"
        )
        enemy = next(
            combatant for combatant in dashboard.combat.combatants  # type: ignore[union-attr]
            if combatant.side == "enemy"
        )
        if result.status != "active" or enemy.current_health != 21:
            raise RuntimeError("Packaged deterministic spell damage was incorrect")
        if mana.current != 14 or slots.current != 2:
            raise RuntimeError("Packaged spell resources did not persist")
        with window.game_state_service.database.connect() as connection:
            turn = connection.execute(
                "SELECT action_key FROM combat_turns WHERE action_key = 'magic_missile'"
            ).fetchone()
        if turn is None:
            raise RuntimeError("Packaged spell audit record did not persist")
    except Exception:
        LOGGER.exception("Packaged abilities smoke test failed")
        app.exit(6)
        return
    app.quit()
