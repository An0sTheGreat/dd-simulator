"""Phase 2b: per-turn notes and transcript paging."""

from __future__ import annotations

import re

from dd_simulator.state.progression import award_character_experience
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID
from dd_simulator.state.turns import ProposedStateChange, claim_turn_notes
from tests.test_action_resolution import FixedProvider, outcome, seeded_service

ID_PATTERN = re.compile(r"(resource|objective|quest|npc|item|route|location|event)-[\w-]+")


def _notes_by_turn(service):  # type: ignore[no-untyped-def]
    messages = service.load_active_dashboard().narrative.messages
    return messages, {
        message.turn_number: message.notes for message in messages if message.notes
    }


def test_notes_group_on_last_message_of_their_turn_only() -> None:
    _database, service = seeded_service()
    service.resolve_player_action("Wait quietly", FixedProvider(outcome()))
    service.resolve_player_action(
        "Climb the wall",
        FixedProvider(outcome(ProposedStateChange(
            "spend_resource", "resource", "resource-stamina",
            "current_value", 3, "Climbing costs stamina",
        ))),
    )
    service.resolve_player_action("Wait again", FixedProvider(outcome()))

    messages, notes = _notes_by_turn(service)
    assert set(notes) == {2}
    assert [(note.kind, note.text) for note in notes[2]] == [("resource", "−3 stamina")]
    turn_two = [message for message in messages if message.turn_number == 2]
    assert turn_two[-1].notes and not any(message.notes for message in turn_two[:-1])


def test_quest_and_xp_notes_from_real_turns_without_internal_ids() -> None:
    database, service = seeded_service()
    service.resolve_player_action(
        "Reach the camp",
        FixedProvider(outcome(ProposedStateChange(
            "complete_objective", "quest_objective", "objective-0",
            "completed", True, "The party reached the camp",
        ))),
    )
    _messages, notes = _notes_by_turn(service)
    quest_notes = [note for note in notes[1] if note.kind == "quest"]
    assert quest_notes and re.fullmatch(r"Quest (updated|completed) · .+", quest_notes[0].text)

    with database.transaction() as connection:
        character_id = connection.execute(
            "SELECT id FROM characters WHERE campaign_id = ? AND is_player = 1",
            (DEMO_CAMPAIGN_ID,),
        ).fetchone()[0]
        award_character_experience(connection, character_id, 50)
        claim_turn_notes(connection, DEMO_CAMPAIGN_ID, 1)
    _messages, notes = _notes_by_turn(service)
    assert ("xp", "+50 XP") in [(note.kind, note.text) for note in notes[1]]
    for turn_notes in notes.values():
        for note in turn_notes:
            assert not ID_PATTERN.search(note.text), note.text


def test_item_note_from_dropped_item_turn() -> None:
    database, service = seeded_service()
    with database.connect() as connection:
        item = connection.execute(
            "SELECT id, name FROM inventory_items WHERE id NOT IN ("
            "SELECT inventory_item_id FROM equipment_slots WHERE inventory_item_id IS NOT NULL"
            ") AND name NOT IN (SELECT item_name FROM equipment_slots WHERE item_name IS NOT NULL) "
            "LIMIT 1"
        ).fetchone()
    service.resolve_player_action(
        f"Drop the {item['name']}",
        FixedProvider(outcome(ProposedStateChange(
            "drop_item", "inventory_item", str(item["id"]), None, True, "Dropped",
        ))),
    )
    _messages, notes = _notes_by_turn(service)
    assert [(note.kind, note.text) for note in notes[1]][0] == ("item", f"{item['name']} dropped")


def test_travel_turn_notes() -> None:
    database, service = seeded_service()
    with database.connect() as connection:
        route = connection.execute(
            "SELECT travel_routes.* FROM travel_routes JOIN locations "
            "ON locations.id = travel_routes.origin_location_id "
            "WHERE travel_routes.campaign_id = ? AND locations.is_current = 1 "
            "AND travel_routes.status = 'open' AND travel_routes.discovered = 1 LIMIT 1",
            (DEMO_CAMPAIGN_ID,),
        ).fetchone()
    service.travel.travel(DEMO_CAMPAIGN_ID, str(route["id"]))
    _messages, notes = _notes_by_turn(service)
    texts = [(note.kind, note.text) for note in notes[max(notes)]]
    assert texts[0][0] == "travel"
    assert re.fullmatch(r"Travelled [\d.]+ mi · \d+ (h|min)( \d+ min)?", texts[0][1])
    if int(route["stamina_cost"]):
        assert ("resource", f"−{route['stamina_cost']} stamina") in texts


def _play(service, count: int) -> None:  # type: ignore[no-untyped-def]
    for index in range(count):
        service.resolve_player_action(f"Action {index}", FixedProvider(outcome()))


def _opening_count(database) -> int:  # type: ignore[no-untyped-def]
    with database.connect() as connection:
        return int(connection.execute(
            "SELECT COUNT(*) FROM narrative_messages WHERE turn_number = 0"
        ).fetchone()[0])


def test_paging_exactly_forty_has_no_older_page() -> None:
    database, service = seeded_service()
    with database.transaction() as connection:  # two-message turns only
        connection.execute("DELETE FROM narrative_messages WHERE turn_number = 0")
    _play(service, 20)
    narrative = service.load_active_dashboard().narrative
    assert len(narrative.messages) == 40
    assert narrative.has_older_messages is False
    assert service.older_messages(DEMO_CAMPAIGN_ID, narrative.messages[0].turn_number) == ()


def test_paging_more_than_forty_pages_back_in_chronological_order() -> None:
    database, service = seeded_service()
    _play(service, 45)
    narrative = service.load_active_dashboard().narrative
    assert len(narrative.messages) == 40
    assert narrative.has_older_messages is True
    assert narrative.messages[0].text == "Action 25"
    older = service.older_messages(DEMO_CAMPAIGN_ID, narrative.messages[0].turn_number)
    assert len(older) == 40
    assert older[-1].text != narrative.messages[0].text
    oldest = service.older_messages(DEMO_CAMPAIGN_ID, older[0].turn_number)
    assert len(oldest) == _opening_count(database) + 10
    assert service.older_messages(DEMO_CAMPAIGN_ID, oldest[0].turn_number) == ()
    combined = [*oldest, *older, *narrative.messages]
    keys = [message.turn_number for message in combined]
    assert keys == sorted(keys)
    assert [m.text for m in combined if m.kind == "player"] == [f"Action {i}" for i in range(45)]


def test_schema_23_migration_backs_up_and_preserves_transcript(tmp_path) -> None:  # type: ignore[no-untyped-def]
    from dd_simulator.state.database import GameStateDatabase
    from dd_simulator.state.seed import seed_demo_campaign

    path = tmp_path / "ledger.db"
    database = GameStateDatabase(path)
    database.initialize()
    seed_demo_campaign(database)
    with database.connect() as connection:
        before = connection.execute("SELECT COUNT(*) FROM narrative_messages").fetchone()[0]
        connection.execute("DROP TABLE turn_notes")
        connection.execute("DELETE FROM schema_migrations WHERE version = 23")

    assert GameStateDatabase(path).initialize() == 23
    assert list((tmp_path / "backups" / "migrations").glob("pre-migration-v22-*.db"))
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM narrative_messages").fetchone()[0] == before
        assert connection.execute("SELECT COUNT(*) FROM turn_notes").fetchone()[0] == 0
