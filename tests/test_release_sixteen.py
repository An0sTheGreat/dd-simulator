from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QColor, QImage
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel

from dd_simulator.state import GameStateDatabase, GameStateService
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID, DEMO_CHARACTER_ID
from dd_simulator.ui.models.presentation import EquipmentSlotView, EventView, InventorySlotView
from dd_simulator.ui.panels.activity_panels import EventLogPanel
from dd_simulator.ui.widgets.codex_character import PaperdollPanel
from dd_simulator.ui.widgets.scene_view import SceneView
from dd_simulator.ui.widgets.inventory_grid import EquipmentGrid, ItemHoverCard


def _write_png(path: Path, color: str) -> None:
    image = QImage(32, 24, QImage.Format.Format_RGB32)
    image.fill(QColor(color))
    assert image.save(str(path), "PNG")


def _file_service(tmp_path: Path) -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase(tmp_path / "game_state.db")
    service = GameStateService(database)
    assert service.initialize() == LATEST_SCHEMA_VERSION == 24
    service.load_active_dashboard()
    return database, service


def test_visual_registry_versions_confirms_reuses_and_restores_exact_location(
    tmp_path: Path,
) -> None:
    database, service = _file_service(tmp_path)
    first_source = tmp_path / "road-morning.png"
    second_source = tmp_path / "road-storm.png"
    _write_png(first_source, "#54843f")
    _write_png(second_source, "#374d68")
    location_id = "location-greystone-road"
    first_signature = service.visuals.current_state_signature(
        DEMO_CAMPAIGN_ID, "location", location_id
    )

    pending = service.visuals.stage_asset(
        campaign_id=DEMO_CAMPAIGN_ID,
        asset_kind="location",
        subject_type="location",
        subject_id=location_id,
        source_path=first_source,
        prompt_summary="Greystone Road in clear morning light.",
        width=32,
        height=24,
    )
    assert pending.status == "pending"
    assert service.load_active_dashboard().location.visual.status == "pending"  # type: ignore[union-attr]

    first = service.visuals.confirm_asset(pending.id)
    assert first.status == "confirmed" and first.canonical
    first_dashboard = service.load_active_dashboard()
    assert first_dashboard.location.visual is not None
    assert first_dashboard.location.visual.id == first.id
    assert Path(first_dashboard.location.visual.path).is_file()

    duplicate = service.visuals.stage_asset(
        campaign_id=DEMO_CAMPAIGN_ID,
        asset_kind="location",
        subject_type="location",
        subject_id=location_id,
        source_path=first_source,
    )
    assert duplicate.id == first.id
    assert "reused" in {entry.action for entry in service.visuals.history(first.id)}

    with database.transaction() as connection:
        original_weather = str(
            connection.execute(
                "SELECT weather FROM locations WHERE id = ?", (location_id,)
            ).fetchone()[0]
        )
        connection.execute(
            "UPDATE locations SET weather = 'Thunderstorm' WHERE id = ?",
            (location_id,),
        )
    second_signature = service.visuals.current_state_signature(
        DEMO_CAMPAIGN_ID, "location", location_id
    )
    assert second_signature != first_signature
    assert service.load_active_dashboard().location.visual.id == first.id  # type: ignore[union-attr]
    second_pending = service.visuals.stage_asset(
        campaign_id=DEMO_CAMPAIGN_ID,
        asset_kind="location",
        subject_type="location",
        subject_id=location_id,
        source_path=second_source,
        signature=second_signature,
    )
    assert service.load_active_dashboard().location.visual.status == "pending"  # type: ignore[union-attr]
    second = service.visuals.confirm_asset(second_pending.id)
    assert service.load_active_dashboard().location.visual.id == second.id  # type: ignore[union-attr]

    with database.transaction() as connection:
        connection.execute(
            "UPDATE locations SET weather = ? WHERE id = ?",
            (original_weather, location_id),
        )
    returned = service.load_active_dashboard().location.visual
    assert returned is not None
    assert returned.id == first.id
    assert returned.state_signature == first_signature

    resolved = service.visuals.resolve(
        campaign_id=DEMO_CAMPAIGN_ID,
        asset_kind="location",
        subject_type="location",
        subject_id=location_id,
    )
    assert resolved is not None and resolved.id == first.id and resolved.use_count == 1
    database.close()


def test_confirmed_portrait_and_location_visuals_bind_to_codex_and_scene(
    tmp_path: Path,
) -> None:
    app = QApplication.instance() or QApplication([])
    database, service = _file_service(tmp_path)
    portrait_source = tmp_path / "portrait.png"
    location_source = tmp_path / "location.png"
    _write_png(portrait_source, "#9f6a35")
    _write_png(location_source, "#406b38")
    for kind, subject_type, subject_id, source in (
        ("portrait", "character", DEMO_CHARACTER_ID, portrait_source),
        ("location", "location", "location-greystone-road", location_source),
    ):
        staged = service.visuals.stage_asset(
            campaign_id=DEMO_CAMPAIGN_ID,
            asset_kind=kind,
            subject_type=subject_type,
            subject_id=subject_id,
            source_path=source,
        )
        service.visuals.confirm_asset(staged.id)
    dashboard = service.load_active_dashboard()
    assert dashboard.player.visual is not None and dashboard.player.visual.status == "confirmed"
    assert dashboard.location.visual is not None and dashboard.location.visual.status == "confirmed"
    player_panel = PaperdollPanel(dashboard.player, dashboard.equipment)
    location_panel = SceneView(dashboard.location, dashboard.quest)
    portrait = player_panel.portrait

    # The paperdoll shows the confirmed portrait itself, not the codex fallback.
    assert dashboard.player.portrait_path == dashboard.player.visual.path
    assert portrait.property("hasPortrait") is True
    assert portrait.pixmap() is not None and not portrait.pixmap().isNull()
    center = portrait.pixmap().toImage().pixelColor(portrait.pixmap().rect().center())
    assert center.name() == "#9f6a35"
    # The scene paints the confirmed location art.
    assert location_panel.image_path == Path(dashboard.location.visual.path)

    player_panel.deleteLater()
    location_panel.deleteLater()
    app.processEvents()
    database.close()


def test_portrait_registry_keeps_canonical_and_tracks_active_state_metadata(
    tmp_path: Path,
) -> None:
    database, service = _file_service(tmp_path)
    canonical_source = tmp_path / "canonical-portrait.png"
    active_source = tmp_path / "armored-portrait.png"
    _write_png(canonical_source, "#8a5a37")
    _write_png(active_source, "#43566f")
    canonical_signature = service.visuals.current_state_signature(
        DEMO_CAMPAIGN_ID, "character", DEMO_CHARACTER_ID
    )
    canonical = service.visuals.confirm_asset(
        service.visuals.stage_asset(
            campaign_id=DEMO_CAMPAIGN_ID,
            asset_kind="portrait",
            subject_type="character",
            subject_id=DEMO_CHARACTER_ID,
            source_path=canonical_source,
            prompt_summary="Canonical adventurer portrait.",
            generation_seed="4242",
            reference_asset_ids=("reference-face",),
            attachment_references=("character-sheet",),
            appearance_lock={"eyes": "green", "hair": "auburn"},
        ).id
    )
    assert canonical.canonical and canonical.active
    assert canonical.asset_role == "canonical"
    assert canonical.generation_seed == "4242"
    assert canonical.reference_asset_ids == ("reference-face",)
    assert canonical.attachment_references == ("character-sheet",)
    assert canonical.appearance_lock["eyes"] == "green"

    active_signature = "equipped-heavy-armor-state"
    active = service.visuals.confirm_asset(
        service.visuals.stage_asset(
            campaign_id=DEMO_CAMPAIGN_ID,
            asset_kind="portrait",
            subject_type="character",
            subject_id=DEMO_CHARACTER_ID,
            source_path=active_source,
            signature=active_signature,
            negative_prompt="No helmet, no extra weapons.",
            lighting_style="torchlit",
        ).id
    )
    assert active.asset_role == "active"
    assert active.active and not active.canonical
    assert active.negative_prompt == "No helmet, no extra weapons."
    assert active.lighting_style == "torchlit"

    exact = service.visuals.resolve(
        campaign_id=DEMO_CAMPAIGN_ID,
        asset_kind="portrait",
        subject_type="character",
        subject_id=DEMO_CHARACTER_ID,
        signature=active_signature,
    )
    fallback = service.visuals.resolve(
        campaign_id=DEMO_CAMPAIGN_ID,
        asset_kind="portrait",
        subject_type="character",
        subject_id=DEMO_CHARACTER_ID,
        signature="an-unregistered-state",
    )
    assert exact is not None and exact.id == active.id
    assert fallback is not None and fallback.id == canonical.id
    assert fallback.state_signature == canonical_signature
    database.close()


def test_equipped_slots_keep_durability_in_hover_and_ammunition_badge() -> None:
    app = QApplication.instance() or QApplication([])
    dagger = InventorySlotView(
        "Iron Dagger",
        quantity=1,
        durability=82,
        maximum_durability=100,
        equip_slot="Main Hand",
        category="weapon",
    )
    arrows = InventorySlotView(
        "Arrows",
        quantity=20,
        equip_slot="Ammunition",
        category="ammunition",
    )
    grid = EquipmentGrid(
        (
            EquipmentSlotView("Main Hand", "Iron Dagger", item=dagger),
            EquipmentSlotView("Ammunition", "Arrows", item=arrows),
        ),
        columns=2,
    )
    dagger_card = ItemHoverCard(dagger, grid)
    assert dagger_card.rows["Durability"].text() == "82 / 100"
    assert "20" in [label.text() for label in grid.findChildren(QLabel, "itemQuantityBadge")]
    dagger_card.deleteLater()
    grid.deleteLater()
    app.processEvents()


def test_event_log_bottom_tracks_final_entry_without_trailing_spacer() -> None:
    app = QApplication.instance() or QApplication([])
    events = tuple(
        EventView(
            f"Day 17, event {index}",
            "system",
            f"Event {index}: " + "The campaign state advances with a readable record. " * 2,
        )
        for index in range(30)
    )
    panel = EventLogPanel(events)
    panel.resize(560, 220)
    panel.show()
    app.processEvents()
    assert panel.entries.alignment() == Qt.AlignmentFlag.AlignBottom
    bar = panel.scroll_area.verticalScrollBar()
    assert bar.maximum() > 0
    assert bar.value() == bar.maximum()
    assert all(
        panel.entries.itemAt(index).spacerItem() is None
        for index in range(panel.entries.count())
    )
    last = panel.entries.itemAt(panel.entries.count() - 1).widget()
    assert isinstance(last, QLabel)
    assert last.text().startswith("Event 29:")

    bar.setValue(bar.maximum() // 2)
    saved = panel.scroll_state()
    assert not saved[1]
    panel.restore_scroll_state(saved)
    assert bar.value() == saved[0]
    panel.deleteLater()
    app.processEvents()
