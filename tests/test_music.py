from __future__ import annotations

import json
import random
from dataclasses import replace
from pathlib import Path

import pytest

from dd_simulator.ui import audio
from dd_simulator.ui.audio import (
    BIOME_CONTEXTS,
    MusicController,
    context_tracks,
    load_manifest,
    next_track,
    select_ambience,
    select_context,
)
from dd_simulator.ui.location_images import LOCATION_ART_ROOT
from dd_simulator.ui.models.presentation import CombatantView, CombatEncounterView
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard

from test_phase_four_interactions import build_window, close_window


MANIFEST = load_manifest()


def _dashboard(biome: str = "road", time_label: str = "Morning", weather: str = "Clear", combat=None):
    base = build_phase_three_dashboard()
    location = replace(base.location, name="Somewhere", biome=biome, time_label=time_label, weather=weather)
    return replace(base, location=location, combat=combat)


def _combat(*archetypes: str, status: str = "active") -> CombatEncounterView:
    enemies = tuple(
        CombatantView(
            id=f"e{index}", name=key, side="enemy", status="active", current_health=5,
            maximum_health=5, armor_class=10, initiative=1, distance_feet=10,
            weapon_name="Club", morale=50, archetype_key=key,
        )
        for index, key in enumerate(archetypes)
    )
    return CombatEncounterView(
        id="c1", status=status, round_number=1, environment="", hazard="",
        starting_distance=30, end_reason="", combatants=enemies, recent_turns=(),
    )


def test_every_manifest_context_and_ambience_has_an_existing_packaged_file() -> None:
    contexts = MANIFEST["contexts"]
    assert set(contexts) == {
        "battle", "boss", "travel_road", "forest_wilderness", "town", "tavern_inn",
        "exploration_cave", "menu",
    }
    for context in contexts:
        for night in (False, True):
            tracks = context_tracks(MANIFEST, context, night)
            assert tracks and all(track.is_file() for track in tracks), context
    for group in MANIFEST["ambience"].values():
        for entries in group.values():
            assert all((audio.AUDIO_ROOT / entry["file"]).is_file() for entry in entries)
    # Package data must ship the folder.
    pyproject = (Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    assert '"ui/assets/audio/*/*"' in pyproject and '"ui/assets/audio/*.json"' in pyproject


def test_every_location_biome_maps_to_a_manifest_context() -> None:
    biomes = {path.name for path in LOCATION_ART_ROOT.iterdir() if path.is_dir()}
    assert biomes == set(BIOME_CONTEXTS)
    for biome in biomes:
        context = select_context("dashboard", _dashboard(biome))
        assert context == BIOME_CONTEXTS[biome]
        assert context_tracks(MANIFEST, context, False)


@pytest.mark.parametrize(
    ("biome", "expected"),
    [
        ("road", "travel_road"), ("forest", "forest_wilderness"), ("village", "town"),
        ("town", "town"), ("tavern", "tavern_inn"), ("inn", "tavern_inn"),
        ("cave", "exploration_cave"), ("dungeon", "exploration_cave"), ("castle", "town"),
        ("mountain", "travel_road"), ("swamp", "forest_wilderness"), ("unknown", "travel_road"),
    ],
)
def test_biome_selects_context(biome: str, expected: str) -> None:
    assert select_context("map", _dashboard(biome)) == expected


def test_combat_boss_and_menu_selection() -> None:
    assert select_context("dashboard", _dashboard("forest", combat=_combat("road_bandit"))) == "battle"
    assert select_context("dashboard", _dashboard(combat=_combat("road_bandit", "hill_ogre"))) == "boss"
    assert select_context("dashboard", _dashboard("forest", combat=_combat("hill_ogre", status="victory"))) == "forest_wilderness"
    for page in ("settings", "character_creation", "local_ai_setup"):
        assert select_context(page, _dashboard("forest")) == "menu"
    assert select_context("dashboard", None) == "menu"


def test_day_and_night_variants() -> None:
    day = context_tracks(MANIFEST, "forest_wilderness", False)
    night = context_tracks(MANIFEST, "forest_wilderness", True)
    assert [track.name for track in day] == ["music_forest_day.mp3"]
    assert [track.name for track in night] == ["music_forest_night.mp3"]
    assert audio.is_night("Night") and not audio.is_night("Evening")
    # Untimed contexts play the same track at any hour.
    assert context_tracks(MANIFEST, "menu", True) == context_tracks(MANIFEST, "menu", False)


def test_ambience_by_biome_and_weather() -> None:
    assert select_ambience(MANIFEST, "forest", "Clear", True).name == "amb_forest_night.wav"
    assert select_ambience(MANIFEST, "forest", "Heavy rain", False).name == "amb_rain.wav"
    assert select_ambience(MANIFEST, "cave", "Heavy rain", False).name == "amb_cave.wav"
    assert select_ambience(MANIFEST, "road", "Clear", False) is None


def test_battle_rotation_never_repeats_a_track() -> None:
    tracks = context_tracks(MANIFEST, "battle", False)
    assert len(tracks) == 7
    rng = random.Random(9)
    previous = None
    for _ in range(50):
        picked = next_track(tracks, previous, rng)
        assert picked != previous
        previous = picked


def test_disabled_controller_creates_no_players_and_updates_are_no_ops() -> None:
    controller = MusicController(enabled=False)
    controller.update("dashboard", _dashboard(combat=_combat("road_bandit")))
    controller.set_volumes(10, 20, True)
    controller.stop()
    assert controller.players == [] and controller.context == ""
    # The test run is offscreen, so the default also disables audio.
    assert MusicController().players == []


def test_audio_settings_round_trip_and_reset(tmp_path: Path) -> None:
    app, window, preferences_path = build_window(tmp_path)
    panel = window.settings_panel
    assert window.music.players == []
    assert panel.music_volume_slider.accessibleName() == "Music volume"
    assert panel.ambience_volume_slider.accessibleName() == "Ambience volume"
    assert panel.mute_checkbox.accessibleName() == "Mute music and ambience"
    panel.music_volume_slider.setValue(25)
    panel.ambience_volume_slider.setValue(70)
    panel.mute_checkbox.setChecked(True)
    saved = json.loads(preferences_path.read_text(encoding="utf-8"))["ui"]
    assert (saved["music_volume"], saved["ambience_volume"], saved["audio_muted"]) == (25, 70, True)
    close_window(app, window)

    app, restored, _ = build_window(tmp_path)
    panel = restored.settings_panel
    assert (panel.music_volume_slider.value(), panel.ambience_volume_slider.value()) == (25, 70)
    assert panel.mute_checkbox.isChecked()
    assert (restored.music.music_volume, restored.music.muted) == (25, True)
    restored._reset_ui_preferences()
    panel = restored.settings_panel
    assert panel.music_volume_slider.value() == audio.DEFAULT_MUSIC_VOLUME
    assert panel.ambience_volume_slider.value() == audio.DEFAULT_AMBIENCE_VOLUME
    assert not panel.mute_checkbox.isChecked() and not restored.music.muted
    close_window(app, restored)
