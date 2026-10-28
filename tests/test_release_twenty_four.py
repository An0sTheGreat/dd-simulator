from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from dd_simulator.app import build_application
from dd_simulator.state import ActionOutcome, NarrativeSegment
from dd_simulator.state.turns import normalize_narrative_segment, sanitize_model_text
from dd_simulator.ui.item_icons import icon_records, resolve_icon
from dd_simulator.ui.models.presentation import NarrativeMessageView, NarrativeView
from dd_simulator.ui.panels.narrative_panels import NarrativePanel
from dd_simulator.ui.services.ui_preferences import UiPreferencesStore


class FixedProvider:
    def resolve_action(self, *, action: str, context: dict[str, object]) -> ActionOutcome:
        return ActionOutcome(
            narration='The merchant nods. "Safe travels."',
            state_changes=(),
            quest_notes=(),
            suggested_actions=tuple(f"Option {index}" for index in range(1, 7)),
            narrative_segments=(
                NarrativeSegment("narrative", "The merchant nods."),
                NarrativeSegment("spoken", '"Safe travels."'),
            ),
        )


def test_semantic_manifest_resolves_stable_rarity_appropriate_icons() -> None:
    records = icon_records()
    assert len(records) == 1686
    assert len({record.index for record in records}) == 1686

    common = resolve_icon("Iron Dagger", "common", "weapon", "main hand melee")
    legendary = resolve_icon("Iron Dagger", "legendary", "weapon", "main hand melee")
    lockpick = resolve_icon("Lockpick", "common", "tool", "unlock doors and chests")

    assert common is not None and common.category == "weapon" and common.visual_tier <= 1
    assert legendary is not None and legendary.category == "weapon" and legendary.visual_tier >= 3
    assert lockpick is not None and lockpick.category in {"key", "tool"}
    assert resolve_icon("Iron Dagger", "legendary", "weapon", "main hand melee") == legendary


def test_item_icons_survive_simple_themes_and_splitters_remain_live(tmp_path: Path) -> None:
    app, window, manager = build_application([], config_dir=tmp_path)
    assert manager.current_theme_id == "high_fantasy"
    assert {theme.theme_id for theme in manager.available_themes()} == {
        "high_fantasy", "modern_proof",
    }
    assert all(not splitter.childrenCollapsible() for splitter in (
        window.main_splitter,
        window.summary_splitter,
        window.narrative_splitter,
        window.lower_splitter,
        window.dashboard_rows_splitter,
    ))
    assert all(splitter.handleWidth() > 0 for splitter in (
        window.main_splitter,
        window.summary_splitter,
        window.narrative_splitter,
        window.lower_splitter,
        window.dashboard_rows_splitter,
    ))
    item_icons = window.findChildren(QLabel, "itemIcon")
    assert any(label.pixmap() is not None and not label.pixmap().isNull() for label in item_icons)
    assert window.navigation_buttons["map"].icon().isNull()

    window.theme_selector.setCurrentIndex(window.theme_selector.findData("modern_proof"))
    app.processEvents()
    assert manager.current_theme_id == "modern_proof"
    assert any(label.pixmap() is not None and not label.pixmap().isNull() for label in item_icons)
    assert window.navigation_buttons["map"].icon().isNull()

    window.close()
    window.deleteLater()
    app.processEvents()


def test_narrative_normalizer_preserves_model_segment_kind() -> None:
    segments = normalize_narrative_segment(
        "narrative",
        "`The merchant studies you. 'I'm listening, traveler!' Their cart creaks.`",
    )

    assert tuple(segment.kind for segment in segments) == ("narrative",)
    assert "I'm listening, traveler!" in segments[0].text
    assert all("`" not in segment.text for segment in segments)
    assert normalize_narrative_segment("spoken", "Safe travels.")[0].text == "Safe travels."

    merchant_line = (
        "*Good morning, traveler. Have you come for supplies or a bargain? "
        "My wares run the line between necessity and delight-though I'd wager "
        "most folk don't find much \"delight\" in bandit raids.*"
    )
    spoken = normalize_narrative_segment("spoken", merchant_line)
    assert len(spoken) == 1
    assert spoken[0].kind == "spoken"
    assert spoken[0].text == merchant_line.strip("*")

    app = QApplication.instance() or QApplication([])
    panel = NarrativePanel(NarrativeView(
        title="Greystone Road",
        paragraphs=(),
        dialogue="",
        prompt="What do you do next?",
        suggested_actions=tuple(f"Option {index}" for index in range(1, 7)),
        messages=(NarrativeMessageView("narrative", segments[0].text),),
    ))
    rendered = panel.findChildren(QLabel)
    assert any(label.property("textRole") == "narrative" for label in rendered)
    assert all("`" not in label.text() for label in rendered)
    panel.deleteLater()
    app.processEvents()


def test_model_text_sanitizer_removes_transport_markup_without_harming_quotes() -> None:
    raw = '```markdown\n### **Amara says, "The *Moon* moved."**\n```'
    assert sanitize_model_text(raw) == 'Amara says, "The Moon moved."'
    assert sanitize_model_text("<b>Safe</b> <script>text</script>") == "Safe text"


def test_committed_turn_reopens_and_return_to_adventure_keeps_latest_state(
    tmp_path: Path,
) -> None:
    UiPreferencesStore(tmp_path / "preferences.json").save_local_ai({
        "mode": "lm_studio", "setup_complete": True,
        "model_directory": str(tmp_path / "models"), "model_path": "",
    })
    app, window, _manager = build_application([], config_dir=tmp_path)
    window.game_state_service.resolve_player_action("Ask for directions", FixedProvider())
    window.close()
    window.deleteLater()
    app.processEvents()

    _app, reopened, _manager = build_application([], config_dir=tmp_path)
    assert reopened.current_page == "settings"
    assert reopened.dashboard.narrative.player_action == "Ask for directions"
    assert reopened.dashboard.narrative.response_segments[-1].text == '"Safe travels."'

    reopened.settings_panel.back_button.click()
    assert reopened.current_page == "dashboard"
    assert reopened.dashboard.narrative.player_action == "Ask for directions"

    reopened.close()
    reopened.deleteLater()
    app.processEvents()
