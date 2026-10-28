from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dd_simulator.lm_studio.action_resolver import LMStudioActionResolver
from dd_simulator.lm_studio.errors import LMStudioConnectionError
from dd_simulator.state import GameStateDatabase, GameStateService
from dd_simulator.state.dialogue import DialogueNarration
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION
from dd_simulator.ui.models.presentation import EquipmentSlotView, InventorySlotView
from dd_simulator.ui.widgets.inventory_grid import equipped_comparisons


def _service(tmp_path: Path) -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase(tmp_path / "game-state.db")
    service = GameStateService(database)
    assert service.initialize() == LATEST_SCHEMA_VERSION
    service.ensure_demo_campaign()
    return database, service


def test_dialogue_quest_offer_is_committed_atomically(tmp_path: Path) -> None:
    database, service = _service(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE npcs SET offers_quest_id = NULL WHERE id = 'npc-roadside-merchant'"
        )

    class Narrator:
        def phrase_dialogue(self, *, context: dict[str, object]) -> DialogueNarration:
            return DialogueNarration(
                '"Find my stolen ledger and bring it back," the merchant says.',
                "They point toward the old road.",
                {
                    "title": "The Missing Ledger",
                    "summary": "Recover the merchant's ledger from the roadside thieves.",
                    "objectives": [
                        {
                            "text": "Find the roadside thieves",
                            "optional": False,
                            "trigger_type": "travel",
                            "trigger_target": "roadside thieves",
                        },
                        {
                            "text": "Return the ledger to the merchant",
                            "optional": False,
                            "trigger_type": "dialogue",
                            "trigger_target": "Roadside Merchant",
                        },
                    ],
                },
            )

    result = service.resolve_npc_dialogue(
        "npc-roadside-merchant", "Do you have work for me?", narrator=Narrator()
    )
    assert result.quest_updates == ("Quest discovered: The Missing Ledger.",)
    with database.connect() as connection:
        quest = connection.execute(
            "SELECT * FROM quests WHERE title = 'The Missing Ledger'"
        ).fetchone()
        assert quest is not None
        assert quest["status"] == "active"
        assert connection.execute(
            "SELECT COUNT(*) FROM quest_objectives WHERE quest_id = ?", (quest["id"],)
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT offers_quest_id FROM npcs WHERE id = 'npc-roadside-merchant'"
        ).fetchone()[0] == quest["id"]


def test_dialogue_skill_check_exposes_structured_roll_result(tmp_path: Path) -> None:
    _database, service = _service(tmp_path)

    result = service.resolve_npc_dialogue(
        "npc-roadside-merchant", "I persuade the merchant to tell me more."
    )

    assert result.skill_check is not None
    assert result.skill_check.name == "Persuasion"
    assert result.skill_check.total == result.skill_check.roll + result.skill_check.modifier
    assert result.skill_check.success == (
        result.skill_check.total >= result.skill_check.target
    )


def test_hand_comparison_defaults_main_and_exposes_offhand() -> None:
    candidate = InventorySlotView(
        "Dagger", equip_slot="Main Hand", compatible_slots=("Main Hand", "Off Hand")
    )
    main = InventorySlotView("Sword", equip_slot="Main Hand")
    off = InventorySlotView("Shield", equip_slot="Off Hand")
    default, alternate = equipped_comparisons(
        candidate,
        (
            EquipmentSlotView("Main Hand", "Sword", item=main),
            EquipmentSlotView("Off Hand", "Shield", item=off),
        ),
    )
    assert default is not None and default.name == "Sword"
    assert alternate is not None and alternate.name == "Shield"
    assert default.status == alternate.status == "Equipped"


def test_action_resolver_uses_safe_narration_after_two_format_failures() -> None:
    class Client:
        model_id = "test-model"

        def preferred_model_id(self) -> str:
            return self.model_id

        def uses_plain_json(self, _model: str) -> bool:
            return False

        def remember_plain_json(self, _model: str) -> None:
            return None

        def _json_request(self, _path: str, *, method: str, payload: dict):
            del method
            if "response_format" in payload:
                raise LMStudioConnectionError("LM Studio returned HTTP 400")
            if "format correction retry" in payload["messages"][0]["content"]:
                raise LMStudioConnectionError("Channel Error")
            return {"choices": [{"message": {"content": "The road opens ahead."}}]}

        def is_model_loaded(self, _model: str) -> bool:
            return True

    outcome = LMStudioActionResolver(Client()).resolve_action(  # type: ignore[arg-type]
        action="Continue down the road", context={"allowed_targets": {}, "inventory": []}
    )
    assert outcome.narration == "The road opens ahead."
    assert outcome.state_changes == ()
    assert len(outcome.suggested_actions) == 6
