import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel

from dd_simulator.ui.location_images import resolve_location_image
from dd_simulator.ui.models.presentation import LocationSummaryView
from dd_simulator.ui.panels.summary_panels import LocationSummaryPanel
from dd_simulator.ui.panels.utility_panels import MinimapPanel


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


def test_location_visual_panel_renders_packaged_catalog_art() -> None:
    app = QApplication.instance() or QApplication([])
    location = LocationSummaryView(
        name="The Lantern & Sheaf",
        region="Wheatmarch",
        time_label="Night",
        weather="Heavy rain",
        danger="Safe",
        route_status="Open",
        biome="tavern",
    )
    summary = LocationSummaryPanel(location)
    panel = MinimapPanel(location)

    preview = panel.findChild(QLabel, "locationVisualPlaceholder")
    assert preview is not None
    assert preview.property("visualState") == "catalog"
    assert preview.pixmap() is not None and not preview.pixmap().isNull()
    assert "tavern_base" in preview.toolTip()
    assert summary.findChild(QLabel, "locationVisualPlaceholder") is None
    panel.resize(640, 300)
    panel.show()
    app.processEvents()
    assert preview.pixmap().size() == preview.contentsRect().size()

    summary.deleteLater()
    panel.deleteLater()
    app.processEvents()
