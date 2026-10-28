from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtTest import QSignalSpy
from PySide6.QtWidgets import QApplication, QLineEdit

from dd_simulator.lm_studio.dialogue_narrator import LMStudioDialogueNarrator
from dd_simulator.lm_studio import LMStudioClient
from dd_simulator.state import GameStateDatabase, GameStateError, GameStateService
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION
from dd_simulator.state.migrations import MIGRATIONS
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID
from dd_simulator.ui.panels.navigation_pages import NpcNavigationPage
from dd_simulator.ui.widgets.semantic_button import SemanticButton


def _service(tmp_path: Path) -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase(tmp_path / "game-state.db")
    service = GameStateService(database)
    assert service.initialize() == LATEST_SCHEMA_VERSION == 21
    service.ensure_demo_campaign()
    return database, service


class _CompatibilityClient:
    model_id = "gemma-test"

    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    def _json_request(self, _path: str, *, method: str, payload: dict[str, object]):
        assert method == "POST"
        self.payloads.append(payload)
        if len(self.payloads) == 1:
            return {"choices": [{"message": {"content": "format drift"}}]}
        return {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "dialogue": {
                            "npc_text": "I have iron helms and a weathered leather cap.",
                            "reaction": "The merchant gestures toward a travel chest.",
                        }
                    })
                }
            }]
        }


def test_gemma_compatible_dialogue_retry_drops_strict_response_format() -> None:
    client = _CompatibilityClient()
    narrator = LMStudioDialogueNarrator(client)  # type: ignore[arg-type]
    speech, monologue = narrator.phrase_dialogue(
        context={"player_text": "Do you sell headgear?", "recent_conversation": []}
    )

    assert speech.startswith("I have iron helms")
    assert monologue.startswith("The merchant gestures")
    assert "response_format" in client.payloads[0]
    assert "response_format" not in client.payloads[1]


def test_dialogue_prose_is_capped_at_125_total_words() -> None:
    response = {"choices": [{"message": {"content": json.dumps({
        "speech": "word " * 100,
        "monologue": "thought " * 100,
    })}}]}
    speech, monologue = LMStudioDialogueNarrator._parse(
        response, allow_plain_text=False
    )
    assert len(speech.split()) + len(monologue.split()) == 125


def test_model_selection_prefers_lm_studio_loaded_instance(monkeypatch: pytest.MonkeyPatch) -> None:
    client = LMStudioClient()
    monkeypatch.setattr(
        client,
        "_json_request_url",
        lambda _url: {
            "models": [
                {"key": "installed-only", "loaded_instances": []},
                {
                    "key": "gemma-4-e4b-uncensored",
                    "loaded_instances": [{"id": "gemma-4-e4b-uncensored"}],
                },
            ]
        },
    )
    assert client.preferred_model_id() == "gemma-4-e4b-uncensored"


def test_failed_dialogue_generation_preserves_input_and_commits_nothing(tmp_path: Path) -> None:
    database, service = _service(tmp_path)

    class BrokenNarrator:
        def phrase_dialogue(self, *, context: dict[str, object]) -> tuple[str, str]:
            assert context["player_text"] == "Do you sell headgear?"
            raise RuntimeError("model response was malformed")

    with pytest.raises(GameStateError, match="input was not committed"):
        service.resolve_npc_dialogue(
            "npc-roadside-merchant",
            "Do you sell headgear?",
            narrator=BrokenNarrator(),
        )
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM npc_conversations").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM campaign_state_audits").fetchone()[0] == 0


def test_people_page_custom_and_suggested_responses_emit_submission(tmp_path: Path) -> None:
    app = QApplication.instance() or QApplication([])
    _database, service = _service(tmp_path)
    page = NpcNavigationPage(service.load_active_dashboard().npc_conversations)
    spy = QSignalSpy(page.dialogue_requested)

    suggested = page.findChildren(SemanticButton, "npcSuggestedResponse")
    assert len(suggested) == 6
    suggested[0].click()
    assert spy.count() == 1
    assert spy.at(0)[1] == suggested[0].text()

    entry = page.findChild(QLineEdit, "npcCustomResponseInput")
    send = page.findChild(SemanticButton, "npcDialogueSendButton")
    assert entry is not None and send is not None
    entry.setText("Do you sell headgear?")
    send.click()
    assert spy.count() == 2
    assert spy.at(1)[1] == "Do you sell headgear?"
    page.deleteLater()
    app.processEvents()


def test_checkpoint_replay_and_restore_exact_campaign_state(tmp_path: Path) -> None:
    _database, service = _service(tmp_path)
    before = service.load_active_dashboard()
    first_id = before.inventory_preview[0].id
    tenth_id = before.inventory_preview[10].id
    checkpoint = service.create_checkpoint("Before reorganizing the pack")
    assert checkpoint.backup_path.is_file()

    service.move_inventory_item(0, 10)
    moved = service.load_active_dashboard()
    assert moved.inventory_preview[10].id == first_id
    replay = service.verify_checkpoint_replay(checkpoint.id)
    assert replay.valid and replay.events_verified == 1

    restored = service.load_checkpoint(checkpoint.id)
    assert restored.inventory_preview[0].id == first_id
    assert restored.inventory_preview[10].id == tenth_id
    replay_after_restore = service.verify_checkpoint_replay(checkpoint.id)
    assert replay_after_restore.valid
    assert replay_after_restore.events_verified == 2


def test_safe_repair_reports_evidence_and_creates_recovery_backup(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE locations SET discovered = 0, visit_count = 0 "
            "WHERE campaign_id = ? AND is_current = 1",
            (DEMO_CAMPAIGN_ID,),
        )
        connection.execute(
            "UPDATE equipment_slots SET inventory_item_id = 'item-0' "
            "WHERE character_id = 'character-kaelen' AND slot_name = 'Main Hand'"
        )
        connection.execute(
            "UPDATE inventory_items SET inventory_position = 27 WHERE id = ?",
            ("item-0",),
        )

    issues = service.inspect_campaign_repair()
    assert {issue.code for issue in issues} >= {
        "current_location_hidden", "equipped_in_inventory"
    }
    result = service.repair_campaign()
    assert result.status == "applied"
    assert result.backup_path is not None and result.backup_path.is_file()
    assert result.before_checksum != result.after_checksum
    assert service.inspect_campaign_repair() == ()


def test_schema_upgrade_creates_pre_migration_backup(tmp_path: Path) -> None:
    path = tmp_path / "schema-14.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    for version, sql in MIGRATIONS[:14]:
        connection.executescript(sql)
        connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
    connection.commit()
    connection.close()

    database = GameStateDatabase(path)
    assert database.initialize() == 21
    backups = tuple((tmp_path / "backups" / "migrations").glob("pre-migration-v14-*.db"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] == 14


def test_schema_11_without_optional_demo_locations_migrates_safely(tmp_path: Path) -> None:
    path = tmp_path / "schema-11.db"
    connection = sqlite3.connect(path)
    connection.execute(
        "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, "
        "applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    for version, sql in MIGRATIONS[:11]:
        connection.executescript(sql)
        connection.execute("INSERT INTO schema_migrations(version) VALUES (?)", (version,))
    connection.execute("INSERT INTO campaigns(id, name) VALUES ('legacy', 'Legacy Campaign')")
    connection.execute(
        "INSERT INTO locations(id, campaign_id, name, region, weather, danger, "
        "route_status, is_current) VALUES "
        "('legacy-road', 'legacy', 'Legacy Road', 'Old Realm', '', '', '', 1)"
    )
    connection.execute(
        "INSERT INTO npcs(id, campaign_id, name, location_id, disposition, notes) VALUES "
        "('npc-roadside-merchant', 'legacy', 'Merchant', 'legacy-road', 'friendly', '')"
    )
    connection.commit()
    connection.close()

    database = GameStateDatabase(path)
    assert database.initialize() == LATEST_SCHEMA_VERSION
    assert database.integrity_check() == ("ok",)
    with database.connect() as migrated:
        assert migrated.execute(
            "SELECT name FROM campaigns WHERE id = 'legacy'"
        ).fetchone()[0] == "Legacy Campaign"
        assert migrated.execute(
            "SELECT reveals_location_id FROM npcs WHERE id = 'npc-roadside-merchant'"
        ).fetchone()[0] is None
