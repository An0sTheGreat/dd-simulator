import os
from dataclasses import replace
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QWidget

from dd_simulator.ui.location_images import resolve_location_image
from dd_simulator.ui.models.presentation import LocationSummaryView
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard
from dd_simulator.ui.themes.theme_manager import ThemeManager
from dd_simulator.ui.widgets.scene_view import SceneView


def _touch(root: Path, archetype: str, variant: str) -> Path:
    path = root / archetype / f"{archetype}_{variant}.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


def test_location_resolver_prefers_state_and_keeps_indoor_weather_out(tmp_path: Path) -> None:
    road_base = _touch(tmp_path, "road", "base")
    road_rain = _touch(tmp_path, "road", "rain")
    tavern_base = _touch(tmp_path, "tavern", "base")
    tavern_corruption = _touch(tmp_path, "tavern", "danger_corruption")

    assert resolve_location_image(
        name="Old Road", biome="road", time_label="Night", weather="Heavy rain",
        danger="Low danger", root=tmp_path,
    ) == road_rain
    assert resolve_location_image(
        name="The Lantern", biome="tavern", time_label="Night", weather="Heavy rain",
        danger="Safe", root=tmp_path,
    ) == tavern_base
    assert resolve_location_image(
        name="The Lantern", biome="tavern", time_label="Day", weather="Clear",
        danger="Root corruption", root=tmp_path,
    ) == tavern_corruption
    assert resolve_location_image(
        name="Unknown", biome="void", time_label="Day", weather="Clear",
        danger="Safe", root=tmp_path,
    ) is None
    assert road_base.is_file()


def test_location_resolver_supports_mountain_and_swamp_variants(tmp_path: Path) -> None:
    mountain_snow = _touch(tmp_path, "mountain", "snow")
    swamp_fire = _touch(tmp_path, "swamp", "danger_fire")
    swamp_night = _touch(tmp_path, "swamp", "night")

    assert resolve_location_image(
        name="Northern Ridge", biome="mountain", time_label="Day",
        weather="Heavy snow", danger="Low danger", root=tmp_path,
    ) == mountain_snow
    assert resolve_location_image(
        name="Blackwater Marsh", biome="swamp", time_label="Night",
        weather="Rain", danger="Wild fire", root=tmp_path,
    ) == swamp_fire
    assert resolve_location_image(
        name="Blackwater Marsh", biome="swamp", time_label="Night",
        weather="Clear", danger="Safe", root=tmp_path,
    ) == swamp_night


def test_scene_view_renders_packaged_catalog_art(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    # The theme makes the card scroll translucent; the quest card itself is hidden below,
    # since it overlays the art rather than being part of it.
    manager = ThemeManager(
        themes_root=Path(__file__).resolve().parents[1] / "src" / "dd_simulator" / "ui" / "themes",
        preferences_path=tmp_path / "prefs.json",
        default_theme_id="high_fantasy",
    )
    manager.apply_loaded_theme(app, manager.load_theme("high_fantasy"), persist=False)
    location = LocationSummaryView(
        name="The Lantern & Sheaf",
        region="Wheatmarch",
        time_label="Night",
        weather="Heavy rain",
        danger="Safe",
        route_status="Open",
        biome="tavern",
    )
    quest = build_phase_three_dashboard().quest
    panel = SceneView(location, quest)
    # No registry visual, so the packaged catalog variant is chosen.
    assert location.visual is None
    assert panel.image_path is not None and panel.image_path.stem == "tavern_base"
    assert panel.findChild(QLabel, "locationVisualPlaceholder") is None

    # The art covers the whole scene: every quadrant differs from a scene with no art.
    blank = SceneView(replace(location, biome="void"), quest)
    assert blank.image_path is None
    images = []
    for scene in (panel, blank):
        scene.findChild(QWidget, "questProgressCard").hide()
        scene.resize(640, 300)
        scene.show()
        app.processEvents()
        images.append(scene.grab().toImage())
    for x, y in ((160, 75), (480, 75), (160, 225), (480, 225)):
        assert images[0].pixelColor(x, y) != images[1].pixelColor(x, y)

    panel.deleteLater()
    blank.deleteLater()
    app.processEvents()
