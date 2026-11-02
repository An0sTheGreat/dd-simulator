"""Schema 24: turn notes sit on the message they were claimed with."""

from __future__ import annotations

from pathlib import Path

from dd_simulator.state import GameStateDatabase
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID
from dd_simulator.state.turns import ProposedStateChange
from tests.test_action_resolution import FixedProvider, outcome
from tests.test_combat_dialogue_notes import _Narrator
from tests.test_dialogue_quest_trade_recovery import _service


def _notes(message):  # type: ignore[no-untyped-def]
    return [(note.kind, note.text) for note in message.notes]


def test_people_exchange_keeps_the_action_notes_on_the_action_response(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    with database.transaction() as connection:
        connection.execute("UPDATE npcs SET offers_quest_id = NULL WHERE id = 'npc-roadside-merchant'")
    service.resolve_player_action(
        "Climb the wall",
        FixedProvider(outcome(ProposedStateChange(
            "spend_resource", "resource", "resource-stamina",
            "current_value", 3, "Climbing costs stamina",
        ))),
    )
    service.resolve_npc_dialogue("npc-roadside-merchant", "Do you have work for me?", narrator=_Narrator())

    messages = service.load_active_dashboard().narrative.messages
    turn = [message for message in messages if message.turn_number == messages[-1].turn_number]
    player_line = next(
        index for index, message in enumerate(turn)
        if message.kind == "player" and message.text == "Do you have work for me?"
    )
    action_response, npc_reply = turn[player_line - 1], turn[-1]
    # the climb also rolls an Athletics story check, noted on the same turn
    assert _notes(action_response)[0] == ("resource", "−3 stamina")
    assert _notes(action_response)[1][1].startswith("Athletics ")
    assert npc_reply.kind == "spoken"
    assert ("quest", "Quest started · The Missing Ledger") in _notes(npc_reply)
    assert ("resource", "−3 stamina") not in _notes(npc_reply)
    noted = [message for message in turn if message.notes]
    assert noted == [action_response, npc_reply]


def test_schema_24_migration_backs_up_and_keeps_old_notes_on_the_last_message(tmp_path: Path) -> None:
    from dd_simulator.state.seed import seed_demo_campaign

    path = tmp_path / "ledger.db"
    database = GameStateDatabase(path)
    database.initialize()
    seed_demo_campaign(database)
    with database.connect() as connection:
        turn = int(connection.execute(
            "SELECT MAX(turn_number) FROM narrative_messages WHERE campaign_id = ?",
            (DEMO_CAMPAIGN_ID,),
        ).fetchone()[0])
        connection.execute("ALTER TABLE turn_notes DROP COLUMN sequence")
        connection.execute(
            "INSERT INTO turn_notes(campaign_id, turn_number, kind, text) VALUES (?, ?, 'xp', '+5 XP')",
            (DEMO_CAMPAIGN_ID, turn),
        )
        connection.execute("DELETE FROM schema_migrations WHERE version = 24")

    assert GameStateDatabase(path).initialize() == 24
    assert list((tmp_path / "backups" / "migrations").glob("pre-migration-v23-*.db"))
    with database.connect() as connection:
        assert connection.execute("SELECT sequence FROM turn_notes").fetchone()[0] is None
    from dd_simulator.state import GameStateService

    messages = GameStateService(database).load_active_dashboard().narrative.messages
    last_turn = [message for message in messages if message.turn_number == turn]
    assert _notes(last_turn[-1]) == [("xp", "+5 XP")]
    assert not any(message.notes for message in last_turn[:-1])
