from __future__ import annotations

import os
from pathlib import Path
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from dd_simulator.app import build_application, load_dashboard_from_state
from dd_simulator.state import GameStateDatabase, GameStateError, GameStateService
from dd_simulator.state.errors import IncompleteGameStateError
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION, MIGRATIONS
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID, seed_demo_campaign
from dd_simulator.ui.services.mock_data import build_phase_three_dashboard


def initialized_database(tmp_path: Path) -> GameStateDatabase:
    database = GameStateDatabase(tmp_path / "game_state.db")
    database.initialize()
    return database


def test_schema_migration_is_versioned_idempotent_and_healthy(tmp_path: Path) -> None:
    database = initialized_database(tmp_path)
    assert database.initialize() == LATEST_SCHEMA_VERSION
    assert database.schema_version() == LATEST_SCHEMA_VERSION
    assert database.integrity_check() == ("ok",)

    with database.connect() as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        narrative_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(narratives)")
        }
        turn_columns = {
            str(row[1]) for row in connection.execute("PRAGMA table_info(action_turns)")
        }

    assert {
        "campaigns",
        "characters",
        "character_attributes",
        "character_resources",
        "abilities",
        "status_effects",
        "inventory_items",
        "equipment_slots",
        "skills",
        "quests",
        "quest_objectives",
        "locations",
        "npcs",
        "events",
        "action_turns",
        "narrative_messages",
        "campaign_clock",
        "narratives",
        "journal_entries",
        "world_facts",
        "combat_encounters",
        "combatants",
        "combat_conditions",
        "combat_turns",
    } <= tables
    assert {"player_action", "response_segments_json"} <= narrative_columns
    assert "response_segments_json" in turn_columns


def test_transaction_rolls_back_all_changes(tmp_path: Path) -> None:
    database = initialized_database(tmp_path)

    with pytest.raises(RuntimeError, match="force rollback"):
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO campaigns(id, name) VALUES ('rollback', 'Rollback')"
            )
            raise RuntimeError("force rollback")

    with database.connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM campaigns WHERE id = 'rollback'"
        ).fetchone()[0]
    assert count == 0


def test_schema_v4_migrates_to_current_narrative_storage(tmp_path: Path) -> None:
    path = tmp_path / "schema-v4.db"
    connection = sqlite3.connect(path)
    for _version, sql in MIGRATIONS[:4]:
        connection.executescript(sql)
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    connection.executemany(
        "INSERT INTO schema_migrations(version) VALUES (?)",
        ((1,), (2,), (3,), (4,)),
    )
    connection.commit()
    connection.close()

    database = GameStateDatabase(path)
    assert database.initialize() == LATEST_SCHEMA_VERSION == 22
    with database.connect() as migrated:
        narrative_columns = {
            str(row[1]) for row in migrated.execute("PRAGMA table_info(narratives)")
        }
        turn_columns = {
            str(row[1]) for row in migrated.execute("PRAGMA table_info(action_turns)")
        }
    assert {"player_action", "response_segments_json"} <= narrative_columns
    assert "response_segments_json" in turn_columns
    with database.connect() as migrated:
        assert migrated.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'narrative_messages'"
        ).fetchone() is not None


def test_schema_v5_backfills_action_turns_into_transcript(tmp_path: Path) -> None:
    path = tmp_path / "schema-v5.db"
    connection = sqlite3.connect(path)
    for _version, sql in MIGRATIONS[:5]:
        connection.executescript(sql)
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    connection.executemany(
        "INSERT INTO schema_migrations(version) VALUES (?)",
        ((1,), (2,), (3,), (4,), (5,)),
    )
    connection.execute("INSERT INTO campaigns(id, name) VALUES ('old', 'Old')")
    connection.execute(
        "INSERT INTO action_turns("
        "id, campaign_id, turn_number, player_action, narration"
        ") VALUES ('old-turn', 'old', 1, 'Open the door', 'The door opens.')"
    )
    connection.commit()
    connection.close()

    database = GameStateDatabase(path)
    assert database.initialize() == 22
    with database.connect() as migrated:
        messages = migrated.execute(
            "SELECT kind, text FROM narrative_messages "
            "WHERE campaign_id = 'old' ORDER BY turn_number, sequence"
        ).fetchall()
    assert [tuple(message) for message in messages] == [
        ("player", "Open the door"),
        ("narrative", "The door opens."),
    ]


def test_schema_v6_preserves_transcript_and_adds_combat_ledger(tmp_path: Path) -> None:
    path = tmp_path / "schema-v6.db"
    connection = sqlite3.connect(path)
    for _version, sql in MIGRATIONS[:6]:
        connection.executescript(sql)
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    connection.executemany(
        "INSERT INTO schema_migrations(version) VALUES (?)",
        ((1,), (2,), (3,), (4,), (5,), (6,)),
    )
    connection.execute("INSERT INTO campaigns(id, name) VALUES ('old', 'Old')")
    connection.execute(
        "INSERT INTO narrative_messages("
        "id, campaign_id, turn_number, sequence, kind, text"
        ") VALUES ('old-message', 'old', 1, 0, 'narrative', 'Preserved text')"
    )
    connection.commit()
    connection.close()

    database = GameStateDatabase(path)
    assert database.initialize() == 22
    with database.connect() as migrated:
        assert migrated.execute(
            "SELECT text FROM narrative_messages WHERE id = 'old-message'"
        ).fetchone()[0] == "Preserved text"
        migrated.execute(
            "INSERT INTO narrative_messages("
            "id, campaign_id, turn_number, sequence, kind, text"
            ") VALUES ('combat-message', 'old', 2, 0, 'combat', 'Combat text')"
        )
        assert migrated.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name = 'combat_encounters'"
        ).fetchone() is not None


def test_demo_seed_is_idempotent_and_projection_matches_phase_four(tmp_path: Path) -> None:
    database = initialized_database(tmp_path)
    assert seed_demo_campaign(database) == DEMO_CAMPAIGN_ID
    assert seed_demo_campaign(database) == DEMO_CAMPAIGN_ID

    service = GameStateService(database)
    dashboard = service.load_active_dashboard()
    assert dashboard.player == build_phase_three_dashboard().player
    assert len(dashboard.inventory_preview) == 36
    assert all(item.name != "Iron Dagger" for item in dashboard.inventory_preview)
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM campaigns").fetchone()[0] == 1
        assert connection.execute("SELECT COUNT(*) FROM inventory_items").fetchone()[0] == 25


def test_campaign_repository_can_create_list_and_select_shells(tmp_path: Path) -> None:
    database = initialized_database(tmp_path)
    service = GameStateService(database)
    first = service.create_campaign("  The   Northern March  ")
    second = service.create_campaign("Ashfall")

    assert first.name == "The Northern March"
    assert not first.creation_complete
    assert {campaign.campaign_id for campaign in service.list_campaigns()} == {
        first.campaign_id,
        second.campaign_id,
    }
    assert service.campaigns.active_campaign_id() is None
    with pytest.raises(IncompleteGameStateError):
        service.select_campaign(second.campaign_id)
    assert service.campaigns.active_campaign_id() is None
    with pytest.raises(IncompleteGameStateError):
        service.load_campaign(first.campaign_id)
    with pytest.raises(KeyError):
        service.select_campaign("missing")


def test_constraints_and_foreign_keys_protect_authoritative_state(tmp_path: Path) -> None:
    database = initialized_database(tmp_path)
    with pytest.raises(GameStateError):
        with database.transaction() as connection:
            connection.execute(
                "INSERT INTO characters(id, campaign_id, name, level) "
                "VALUES ('orphan', 'missing', 'Orphan', 1)"
            )


def test_corrupt_ledger_is_preserved_and_uses_temporary_recovery(tmp_path: Path) -> None:
    ledger = tmp_path / "game_state.db"
    original = b"not a sqlite database"
    ledger.write_bytes(original)

    dashboard, service, warning = load_dashboard_from_state(tmp_path)

    assert dashboard.player.name == "Kaelen Stormborne"
    assert warning is not None
    assert "original file was not changed" in warning
    assert ledger.read_bytes() == original
    assert service.database.integrity_check() == ("ok",)


def test_application_bootstrap_creates_and_uses_game_state_ledger(tmp_path: Path) -> None:
    app, window, _theme_manager = build_application([], config_dir=tmp_path)

    assert (tmp_path / "game_state.db").is_file()
    assert window.dashboard.player == build_phase_three_dashboard().player
    assert len(window.dashboard.inventory_preview) == 36
    assert window.game_state_service.database.schema_version() == LATEST_SCHEMA_VERSION

    window.close()
    window.deleteLater()
    app.processEvents()
