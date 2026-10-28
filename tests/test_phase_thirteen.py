from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from dd_simulator.lm_studio.travel_narrator import LMStudioTravelNarrator
from dd_simulator.state import GameStateDatabase, GameStateError, GameStateService
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID, seed_demo_campaign
from dd_simulator.ui.widgets.world_map import (
    CampConfirmationDialog,
    TravelConfirmationDialog,
    WorldMapPanel,
)


def travel_service(tmp_path: Path) -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase(tmp_path / "phase-thirteen.db")
    assert database.initialize() == LATEST_SCHEMA_VERSION == 21
    seed_demo_campaign(database)
    return database, GameStateService(database)


def test_schema_eleven_adds_routes_discovery_and_history(tmp_path: Path) -> None:
    database, service = travel_service(tmp_path)
    with database.connect() as connection:
        location_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(locations)")
        }
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert {
        "description", "biome", "discovered", "visit_count", "can_camp",
        "map_x", "map_y", "last_visited_at",
    } <= location_columns
    assert {"travel_routes", "travel_history", "camp_history"} <= tables
    dashboard = service.load_active_dashboard()
    assert dashboard.world_map is not None
    assert "location-ancient-ruins" not in {
        location.id for location in dashboard.world_map.locations
    }
    assert "location-ancient-ruins" not in {
        location["id"] for location in service.build_action_context()["known_locations"]
    }


def test_travel_spends_stamina_advances_clock_and_persists_arrival(tmp_path: Path) -> None:
    database, service = travel_service(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE travel_routes SET danger_rating = 0 WHERE id = 'route-road-keep'"
        )
        stamina_before = int(
            connection.execute(
                "SELECT current_value FROM character_resources "
                "WHERE resource_type = 'stamina'"
            ).fetchone()[0]
        )

    result = service.travel_to("route-road-keep")
    dashboard = service.load_active_dashboard()

    assert not result.encounter_required
    assert dashboard.location.name == "Greystone Keep"
    assert dashboard.location.time_label == "Morning, Day 17"
    assert dashboard.world_map is not None
    assert dashboard.world_map.current_location_id == "location-greystone-keep"
    with database.connect() as connection:
        stamina_after = int(
            connection.execute(
                "SELECT current_value FROM character_resources "
                "WHERE resource_type = 'stamina'"
            ).fetchone()[0]
        )
        history = connection.execute(
            "SELECT * FROM travel_history WHERE id = ?", (result.history_id,)
        ).fetchone()
        assert history["outcome"] == "arrived"
        assert history["arrived_minute"] == 600
        assert connection.execute(
            "SELECT COUNT(*) FROM events WHERE campaign_id = ? AND category = 'travel'",
            (DEMO_CAMPAIGN_ID,),
        ).fetchone()[0] >= 1
    assert stamina_after == stamina_before - 2
    assert any(message.kind == "player" and "Travel to" in message.text for message in dashboard.narrative.messages)


def test_unavailable_travel_narration_uses_deterministic_fallback(tmp_path: Path) -> None:
    _database, service = travel_service(tmp_path)

    class FailingNarrator:
        def narrate_travel(self, _context):  # type: ignore[no-untyped-def]
            raise RuntimeError("offline")

        def narrate_camp(self, _context):  # type: ignore[no-untyped-def]
            raise RuntimeError("offline")

    with service.database.transaction() as connection:
        connection.execute(
            "UPDATE travel_routes SET danger_rating = 0 WHERE id = 'route-road-keep'"
        )
    result = service.travel_to("route-road-keep", narrator=FailingNarrator())
    assert result.summary.startswith("The party travels 8 miles")


def test_generated_travel_narration_is_capped_at_125_words() -> None:
    response = {
        "choices": [{"message": {"content": '{"narration":"' + "word " * 150 + '"}'}}]
    }
    assert len(LMStudioTravelNarrator._parse(response).split()) == 125


def test_blocked_route_and_insufficient_stamina_roll_back(tmp_path: Path) -> None:
    database, service = travel_service(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE travel_routes SET danger_rating = 0 WHERE id = 'route-road-woods'"
        )
    service.travel_to("route-road-woods")
    with pytest.raises(GameStateError, match="blocked"):
        service.travel_to("route-woods-ridge")

    with database.transaction() as connection:
        connection.execute(
            "UPDATE character_resources SET current_value = 0 "
            "WHERE resource_type = 'stamina'"
        )
    with pytest.raises(GameStateError, match="does not have enough"):
        service.travel_to("route-road-woods")
    assert service.load_active_dashboard().location.name == "Whispering Woods"


def test_dangerous_route_starts_and_links_generated_encounter(tmp_path: Path) -> None:
    database, service = travel_service(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE travel_routes SET danger_rating = 10 WHERE id = 'route-road-ridge'"
        )
    result = service.travel_to("route-road-ridge")
    dashboard = service.load_active_dashboard()

    assert result.encounter_required
    assert dashboard.combat is not None
    assert dashboard.combat.status == "active"
    with database.connect() as connection:
        history = connection.execute(
            "SELECT outcome, encounter_id FROM travel_history WHERE id = ?",
            (result.history_id,),
        ).fetchone()
    assert history["outcome"] == "encounter"
    assert history["encounter_id"] == dashboard.combat.id


def test_camping_advances_time_recovers_resources_and_honors_location_rules(
    tmp_path: Path,
) -> None:
    database, service = travel_service(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE character_resources SET current_value = 0 "
            "WHERE resource_type = 'stamina'"
        )
    result = service.make_camp(duration_minutes=240)
    dashboard = service.load_active_dashboard()
    stamina = next(
        resource for resource in dashboard.player.resources
        if resource.resource_type == "stamina"
    )
    assert stamina.current == 7
    assert dashboard.location.time_label == "Afternoon, Day 17"
    with database.connect() as connection:
        assert connection.execute(
            "SELECT duration_minutes FROM camp_history WHERE id = ?", (result.history_id,)
        ).fetchone()[0] == 240

    with database.transaction() as connection:
        connection.execute("UPDATE travel_routes SET danger_rating = 0")
    service.travel_to("route-road-keep")
    with pytest.raises(GameStateError, match="not permitted"):
        service.make_camp(duration_minutes=480)


def test_map_panel_selects_direct_routes_and_exposes_camp_actions(tmp_path: Path) -> None:
    _database, service = travel_service(tmp_path)
    app = QApplication.instance() or QApplication([])
    dashboard = service.load_active_dashboard()
    panel = WorldMapPanel(dashboard.world_map)
    emitted_routes: list[str] = []
    emitted_camps: list[int] = []
    panel.travel_requested.connect(emitted_routes.append)
    panel.camp_requested.connect(emitted_camps.append)
    panel.resize(1200, 650)
    panel.show()
    app.processEvents()

    panel.select_location("location-greystone-keep")
    assert panel.selected_route is not None
    assert panel.selected_route.id == "route-road-keep"
    assert panel.travel_button.isEnabled()
    panel.travel_button.click()
    assert emitted_routes == ["route-road-keep"]
    camp_button = next(
        button for button in panel.findChildren(type(panel.travel_button))
        if button.objectName() == "mapCampButton"
    )
    camp_button.click()
    assert emitted_camps
    panel.close()


def test_travel_and_camp_confirmations_are_modal(tmp_path: Path) -> None:
    _database, service = travel_service(tmp_path)
    app = QApplication.instance() or QApplication([])
    route = service.load_active_dashboard().world_map.routes[0]  # type: ignore[union-attr]
    travel = TravelConfirmationDialog(route)
    camp = CampConfirmationDialog(480)
    travel.show()
    camp.show()
    app.processEvents()
    assert travel.isModal()
    assert camp.isModal()
    travel.close()
    camp.close()
