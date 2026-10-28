"""Per-turn notes for combat (damage, HP, ammunition, potions) and dialogue quests."""

from __future__ import annotations

import re
from pathlib import Path

from dd_simulator.state import CombatAction, CombatCommand
from dd_simulator.state.dialogue import DialogueNarration
from tests.test_combat import combat_service, training_enemy
from tests.test_dialogue_quest_trade_recovery import _service
from tests.test_turn_notes_paging import ID_PATTERN


def _notes(database, turn_number: int) -> list[tuple[str, str]]:  # type: ignore[no-untyped-def]
    with database.connect() as connection:
        rows = connection.execute(
            "SELECT kind, text FROM turn_notes WHERE turn_number = ? ORDER BY rowid",
            (turn_number,),
        ).fetchall()
    notes = [(row["kind"], row["text"]) for row in rows]
    assert not any(ID_PATTERN.search(text) for _kind, text in notes), notes
    return notes


def _last_turn(database) -> int:  # type: ignore[no-untyped-def]
    with database.connect() as connection:
        return int(connection.execute("SELECT MAX(turn_number) FROM narrative_messages").fetchone()[0])


def _enemy_id(service) -> str:  # type: ignore[no-untyped-def]
    return next(
        row.id for row in service.load_active_dashboard().combat.combatants  # type: ignore[union-attr]
        if row.side == "enemy"
    )


def test_combat_round_records_damage_dealt_and_taken() -> None:
    database, service = combat_service(20, 1, 15, 4, 15, 2)
    service.start_combat(enemies=(training_enemy(maximum_health=30),))
    service.execute_combat_command(CombatCommand(CombatAction.ATTACK, target_id=_enemy_id(service)))
    notes = _notes(database, _last_turn(database))
    assert re.search(r"Dealt \d+ damage", " ".join(text for _k, text in notes))
    assert any(kind == "other" and text.startswith("Dealt ") for kind, text in notes)
    assert any(kind == "resource" and re.fullmatch(r"\u2212\d+ HP", text) for kind, text in notes)
    database.close()


def test_bow_shot_records_ammunition_spent() -> None:
    database, service = combat_service(20, 1, 15, 4)
    with database.transaction() as connection:
        connection.execute("UPDATE inventory_items SET name = 'Shortbow', equip_slot = 'Main Hand' WHERE id = 'item-0'")
        connection.execute("UPDATE equipment_slots SET item_name = 'Shortbow' WHERE id = 'equipment-0'")
        connection.execute("UPDATE inventory_items SET quantity = 5 WHERE name = 'Arrows'")
    service.start_combat(enemies=(training_enemy(maximum_health=20, distance_feet=25),))
    service.execute_combat_command(CombatCommand(CombatAction.ATTACK, target_id=_enemy_id(service)))
    assert ("item", "\u22121 Arrows") in _notes(database, _last_turn(database))
    database.close()


def test_combat_potion_records_item_used() -> None:
    database, service = combat_service(20, 1, 1)
    service.start_combat(enemies=(training_enemy(maximum_health=20),))
    with database.transaction() as connection:
        connection.execute("UPDATE combatants SET current_health = 20 WHERE side = 'player'")
        connection.execute("UPDATE character_resources SET current_value = 20 WHERE resource_type = 'health'")
    service.execute_combat_command(CombatCommand(CombatAction.USE_ITEM))
    assert ("item", "Health Potion used") in _notes(database, _last_turn(database))
    database.close()


class _Narrator:
    def phrase_dialogue(self, *, context: dict[str, object]) -> DialogueNarration:
        return DialogueNarration(
            '"Find my stolen ledger and bring it back," the merchant says.',
            "They point toward the old road.",
            {
                "title": "The Missing Ledger",
                "summary": "Recover the merchant's ledger from the roadside thieves.",
                "objectives": [
                    {"text": "Find the thieves", "optional": False,
                     "trigger_type": "travel", "trigger_target": "thieves"},
                    {"text": "Return the ledger", "optional": False,
                     "trigger_type": "dialogue", "trigger_target": "Roadside Merchant"},
                ],
            },
        )


def test_dialogue_offered_quest_records_started_note(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    with database.transaction() as connection:
        connection.execute("UPDATE npcs SET offers_quest_id = NULL WHERE id = 'npc-roadside-merchant'")
    service.resolve_npc_dialogue("npc-roadside-merchant", "Do you have work for me?", narrator=_Narrator())
    assert ("quest", "Quest started \u00b7 The Missing Ledger") in _notes(database, _last_turn(database))


def test_dialogue_rumored_quest_records_started_note(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE quests SET status = 'rumored' WHERE id = "
            "(SELECT offers_quest_id FROM npcs WHERE id = 'npc-roadside-merchant')"
        )
        title = connection.execute(
            "SELECT title FROM quests WHERE id = "
            "(SELECT offers_quest_id FROM npcs WHERE id = 'npc-roadside-merchant')"
        ).fetchone()["title"]
    service.resolve_npc_dialogue("npc-roadside-merchant", "Any work?", narrator=_Narrator())
    assert ("quest", f"Quest started \u00b7 {title}") in _notes(database, _last_turn(database))
