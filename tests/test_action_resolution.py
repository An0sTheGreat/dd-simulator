from __future__ import annotations

import json
import os
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QThreadPool
from PySide6.QtTest import QSignalSpy

from dd_simulator.local_model import LocalModelResponseError
from dd_simulator.local_model.action_resolver import LocalModelActionResolver
from dd_simulator.app import build_application
from dd_simulator.state import (
    ActionCancelledError,
    ActionOutcome,
    ActionValidationError,
    GameStateDatabase,
    GameStateError,
    GameStateService,
    NarrativeSegment,
    ProposedStateChange,
)
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID, seed_demo_campaign
from dd_simulator.ui.item_icons import resolve_icon
from dd_simulator.ui.services.action_resolution_worker import ActionResolutionTask


def seeded_service() -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase.in_memory()
    database.initialize()
    seed_demo_campaign(database)
    return database, GameStateService(database)


def visible_item(service: GameStateService, name: str):  # type: ignore[no-untyped-def]
    return next(
        item for item in service.load_active_dashboard().inventory_preview
        if item.name == name
    )


def outcome(*changes: ProposedStateChange) -> ActionOutcome:
    return ActionOutcome(
        narration="The merchant nods as the moment unfolds.",
        state_changes=changes,
        quest_notes=("The roadside encounter continues.",),
        suggested_actions=(
            "Ask another question",
            "Inspect the cart",
            "Examine the road",
            "Check the signpost",
            "Listen carefully",
            "Continue toward the keep",
        ),
    )


class FixedProvider:
    def __init__(self, result: ActionOutcome) -> None:
        self.result = result
        self.action = ""
        self.context: dict[str, object] = {}

    def resolve_action(self, *, action: str, context: dict[str, object]) -> ActionOutcome:
        self.action = action
        self.context = context
        return self.result


def test_bounded_context_contains_stable_allowed_targets() -> None:
    database, service = seeded_service()
    with database.transaction() as connection:
        for index in range(20):
            connection.execute(
                "INSERT INTO events(id, campaign_id, time_label, category, summary, sequence) "
                "VALUES (?, ?, 'Earlier', 'test', ?, ?)",
                (f"extra-{index}", DEMO_CAMPAIGN_ID, "x" * 700, 100 + index),
            )

    context = service.build_action_context()

    assert context["campaign"]["id"] == DEMO_CAMPAIGN_ID  # type: ignore[index]
    assert "resource-health" in context["allowed_targets"]["resource_ids"]  # type: ignore[index]
    assert "item-2" in context["allowed_targets"]["inventory_item_ids"]  # type: ignore[index]
    assert len(context["recent_events"]) == 8  # type: ignore[arg-type]
    assert len(json.dumps(context)) < 18000


def test_narration_only_turn_commits_audit_narrative_and_event() -> None:
    database, service = seeded_service()
    provider = FixedProvider(outcome())

    result = service.resolve_player_action("  speak   with the merchant ", provider)

    assert provider.action == "speak with the merchant"
    assert result.state_summaries == ()
    dashboard = service.load_active_dashboard()
    assert dashboard.narrative.paragraphs == ("The merchant nods as the moment unfolds.",)
    assert dashboard.narrative.suggested_actions == (
        "Ask another question",
        "Inspect the cart",
        "Examine the road",
        "Check the signpost",
        "Listen carefully",
        "Continue toward the keep",
    )
    assert dashboard.narrative.player_action == "speak with the merchant"
    assert dashboard.recent_events[-1].category == "action"
    with database.connect() as connection:
        turn = connection.execute("SELECT * FROM action_turns").fetchone()
        clock = connection.execute(
            "SELECT turn_number FROM campaign_clock WHERE campaign_id = ?",
            (DEMO_CAMPAIGN_ID,),
        ).fetchone()
    assert turn["player_action"] == "speak with the merchant"
    assert turn["turn_number"] == 1
    assert clock["turn_number"] == 1


def test_free_text_only_routes_to_known_local_people() -> None:
    database, service = seeded_service()

    with database.connect() as connection:
        before = connection.execute(
            "SELECT COUNT(*) FROM npcs WHERE campaign_id = ?", (DEMO_CAMPAIGN_ID,)
        ).fetchone()[0]

    assert service.ensure_local_interaction_npc(
        "I head back up to the tavern to speak with some more people."
    ) is None
    assert service.ensure_local_interaction_npc(
        "I speak with the merchant."
    ) == "npc-roadside-merchant"

    with database.connect() as connection:
        after = connection.execute(
            "SELECT COUNT(*) FROM npcs WHERE campaign_id = ?", (DEMO_CAMPAIGN_ID,)
        ).fetchone()[0]
    assert after == before


def test_typed_narrative_segments_persist_in_order() -> None:
    database, service = seeded_service()
    provider = FixedProvider(
        ActionOutcome(
            narration="Rain gathers. A bad omen. Keep moving.",
            state_changes=(),
            quest_notes=(),
            suggested_actions=tuple(f"Option {index}" for index in range(1, 7)),
            narrative_segments=(
                NarrativeSegment("narrative", "Rain gathers along the road."),
                NarrativeSegment("monologue", "This feels like a bad omen."),
                NarrativeSegment("spoken", "Keep moving,"),
            ),
        )
    )

    service.resolve_player_action("I tighten my cloak", provider)

    narrative = service.load_active_dashboard().narrative
    assert narrative.player_action == "I tighten my cloak"
    assert tuple((segment.kind, segment.text) for segment in narrative.response_segments) == (
        ("narrative", "Rain gathers along the road."),
        ("monologue", "This feels like a bad omen."),
        ("spoken", "Keep moving,"),
    )
    with database.connect() as connection:
        stored = connection.execute(
            "SELECT response_segments_json FROM action_turns"
        ).fetchone()[0]
    assert [segment["kind"] for segment in json.loads(stored)] == [
        "narrative", "monologue", "spoken"
    ]


def test_resource_and_inventory_changes_share_one_turn_transaction() -> None:
    database, service = seeded_service()
    provider = FixedProvider(
        outcome(
            ProposedStateChange(
                "spend_resource", "resource", "resource-stamina",
                "current_value", 3, "Climbing costs stamina",
            ),
            ProposedStateChange(
                "use_item", "inventory_item", "item-7",
                None, True, "A torch is lit",
            ),
        )
    )

    result = service.resolve_player_action("light a torch and climb", provider)

    assert len(result.state_summaries) == 2
    dashboard = service.load_active_dashboard()
    stamina = next(value for value in dashboard.sidebar_resources if value.resource_type == "stamina")
    assert stamina.current == 25
    assert visible_item(service, "Torch").quantity == 3
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM action_turns").fetchone()[0] == 1


@pytest.mark.parametrize("amount", ["2", 2.0])
def test_integer_like_resource_amounts_are_normalized(amount: object) -> None:
    _database, service = seeded_service()
    provider = FixedProvider(outcome(ProposedStateChange(
        "spend_resource", "resource", "resource-stamina", None, amount, "effort"
    )))

    service.resolve_player_action("push through the heavy door", provider)

    stamina = next(
        value for value in service.load_active_dashboard().sidebar_resources
        if value.resource_type == "stamina"
    )
    assert stamina.current == 26


def test_explicit_pickup_fallback_adds_generated_item_to_inventory() -> None:
    _database, service = seeded_service()
    provider = FixedProvider(outcome())
    provider.result = LocalModelActionResolver._ensure_explicit_acquisition(
        provider.result, "I pick up the etched rune stone from the floor."
    )

    service.resolve_player_action("I pick up the etched rune stone from the floor.", provider)

    item = visible_item(service, "etched rune stone")
    assert item.quantity == 1
    assert item.description
    assert resolve_icon(item.name or "", item.rarity, item.category) is not None


def test_narrated_direct_gift_adds_generated_item_to_inventory() -> None:
    _database, service = seeded_service()
    gifted = ActionOutcome(
        narration="The smith gives you a polished rune stone.",
        state_changes=(),
        quest_notes=("The smith's gift may prove useful.",),
        suggested_actions=outcome().suggested_actions,
    )
    gifted = LocalModelActionResolver._ensure_explicit_acquisition(
        gifted, "I accept the smith's gift."
    )

    service.resolve_player_action("I accept the smith's gift.", FixedProvider(gifted))

    assert visible_item(service, "polished rune stone").quantity == 1


def test_combat_intent_detection_is_explicit_and_avoids_false_positives() -> None:
    assert GameStateService.action_requests_combat(
        "Prepare for combat by adopting a defensive stance"
    )
    assert GameStateService.action_requests_combat("I charge toward the goblin")
    assert not GameStateService.action_requests_combat("I charge the lantern")
    assert not GameStateService.action_requests_combat("I try to avoid combat")


def test_examine_item_validates_ownership_without_consuming_it() -> None:
    database, service = seeded_service()
    provider = FixedProvider(
        outcome(
            ProposedStateChange(
                "examine_item",
                "inventory_item",
                "item-2",
                None,
                True,
                "The player studies the potion.",
            )
        )
    )

    result = service.resolve_player_action("Examine the Health Potion", provider)

    assert result.state_summaries == (
        "Examined Health Potion: Restores health.",
    )
    assert visible_item(service, "Health Potion").quantity == 3


def test_equip_item_accepts_only_owned_equippable_inventory() -> None:
    database, service = seeded_service()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO inventory_items("
            "id, character_id, slot_index, name, quantity, rarity, item_type, equip_slot"
            ") VALUES ('item-spare-sword', 'demo-kaelen', 99, 'Longsword', 1, "
            "'common', 'equipment', 'Main Hand')"
        )
    context = service.build_action_context()
    assert "item-spare-sword" in context["allowed_targets"]["equippable_inventory_item_ids"]  # type: ignore[index]
    assert "item-3" not in context["allowed_targets"]["equippable_inventory_item_ids"]  # type: ignore[index]

    service.resolve_player_action(
        "Equip the Longsword",
        FixedProvider(
            outcome(
                ProposedStateChange(
                    "equip_item",
                    "inventory_item",
                    "item-spare-sword",
                    None,
                    True,
                    "The player equips the sword.",
                )
            )
        ),
    )
    dashboard = service.load_active_dashboard()
    assert dashboard.equipment[0].item_name == "Longsword"

    with pytest.raises(ActionValidationError, match="not equippable"):
        service.resolve_player_action(
            "Equip the Map Fragment",
            FixedProvider(
                outcome(
                    ProposedStateChange(
                        "equip_item",
                        "inventory_item",
                        "item-3",
                        None,
                        True,
                        "Invalid equipment request.",
                    )
                )
            ),
        )


def test_resource_restoration_requires_explicit_recovery_and_excludes_health() -> None:
    database, service = seeded_service()
    with database.transaction() as connection:
        connection.execute(
            "UPDATE character_resources SET current_value = 20 WHERE id = 'resource-stamina'"
        )
    restore_stamina = FixedProvider(
        outcome(
            ProposedStateChange(
                "restore_resource", "resource", "resource-stamina",
                "current_value", 4, "A short rest restores stamina",
            )
        )
    )

    with pytest.raises(ActionValidationError, match="explicit rest"):
        service.resolve_player_action("look around carefully", restore_stamina)

    service.resolve_player_action("pause to rest and catch my breath", restore_stamina)
    dashboard = service.load_active_dashboard()
    stamina = next(value for value in dashboard.sidebar_resources if value.resource_type == "stamina")
    assert stamina.current == 24

    restore_health = FixedProvider(
        outcome(
            ProposedStateChange(
                "restore_resource", "resource", "resource-health",
                "current_value", 2, "Health cannot change in this phase",
            )
        )
    )
    with pytest.raises(ActionValidationError, match="outside non-combat"):
        service.resolve_player_action("rest quietly", restore_health)


def test_invalid_late_change_rolls_back_earlier_changes_and_narration() -> None:
    database, service = seeded_service()
    original = service.load_active_dashboard().narrative
    provider = FixedProvider(
        outcome(
            ProposedStateChange(
                "spend_resource", "resource", "resource-stamina", None, 4, "cost"
            ),
            ProposedStateChange(
                "use_item", "inventory_item", "not-owned", None, True, "invalid"
            ),
        )
    )

    with pytest.raises(ActionValidationError, match="not owned"):
        service.resolve_player_action("attempt invalid combined action", provider)

    dashboard = service.load_active_dashboard()
    stamina = next(value for value in dashboard.sidebar_resources if value.resource_type == "stamina")
    assert stamina.current == 28
    assert dashboard.narrative == original
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM action_turns").fetchone()[0] == 0


def test_database_failure_rolls_back_complete_turn() -> None:
    database, service = seeded_service()
    provider = FixedProvider(
        outcome(
            ProposedStateChange(
                "spend_resource", "resource", "resource-stamina", None, 5, "effort"
            )
        )
    )
    with database.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER reject_action_turn BEFORE INSERT ON action_turns "
            "BEGIN SELECT RAISE(ABORT, 'turn rejected'); END"
        )

    with pytest.raises(GameStateError, match="turn rejected"):
        service.resolve_player_action("climb carefully", provider)

    dashboard = service.load_active_dashboard()
    stamina = next(value for value in dashboard.sidebar_resources if value.resource_type == "stamina")
    assert stamina.current == 28
    assert dashboard.narrative.title == "Greystone Road"
    with database.connect() as connection:
        assert connection.execute("SELECT turn_number FROM campaign_clock").fetchone()[0] == 0


def test_transcript_failure_rolls_back_complete_turn() -> None:
    database, service = seeded_service()
    original = service.load_active_dashboard().narrative
    with database.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER reject_transcript BEFORE INSERT ON narrative_messages "
            "WHEN NEW.turn_number > 0 BEGIN SELECT RAISE(ABORT, 'transcript rejected'); END"
        )

    with pytest.raises(GameStateError, match="transcript rejected"):
        service.resolve_player_action("look around", FixedProvider(outcome()))

    assert service.load_active_dashboard().narrative == original
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM action_turns").fetchone()[0] == 0
        assert connection.execute("SELECT turn_number FROM campaign_clock").fetchone()[0] == 0


def test_projection_returns_only_latest_forty_transcript_messages() -> None:
    _database, service = seeded_service()
    for index in range(22):
        service.resolve_player_action(f"Action {index}", FixedProvider(outcome()))

    messages = service.load_active_dashboard().narrative.messages
    assert len(messages) == 40
    assert messages[0].kind == "player"
    assert messages[0].text == "Action 2"
    assert messages[-2].kind == "player"
    assert messages[-2].text == "Action 21"
    assert messages[-1].kind == "narrative"


def test_provider_cannot_bypass_structural_turn_limits() -> None:
    database, service = seeded_service()
    oversized = ActionOutcome(
        narration="valid",
        state_changes=(),
        quest_notes=(),
        suggested_actions=tuple(f"option {index}" for index in range(4)),
    )

    with pytest.raises(ActionValidationError, match="suggested actions"):
        service.resolve_player_action("look around", FixedProvider(oversized))

    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM action_turns").fetchone()[0] == 0


def test_objective_and_time_changes_are_bounded_and_projected() -> None:
    database, service = seeded_service()
    provider = FixedProvider(
        outcome(
            ProposedStateChange(
                "complete_objective", "quest_objective", "objective-0",
                "completed", True, "The party reached the camp",
            ),
            ProposedStateChange(
                "advance_time", "campaign_clock", DEMO_CAMPAIGN_ID,
                "minute_of_day", 300, "Travel takes time",
            ),
        )
    )

    service.resolve_player_action("wait before continuing", provider)

    dashboard = service.load_active_dashboard()
    assert dashboard.location.name == "Greystone Road"
    assert dashboard.location.time_label == "Afternoon, Day 17"
    assert dashboard.quest.objectives[0].completed


def test_freeform_movement_requires_map_confirmation() -> None:
    database, service = seeded_service()
    with database.transaction() as connection:
        connection.execute(
            "INSERT INTO locations(id, campaign_id, name, region, route_status, is_current) "
            "VALUES ('location-ruins', ?, 'Flooded Ruins', 'Silvermarch', 'Route blocked by flood', 0)",
            (DEMO_CAMPAIGN_ID,),
        )
    provider = FixedProvider(
        outcome(
            ProposedStateChange(
                "move_character", "location", "location-ruins",
                "is_current", True, "Travel to the ruins",
            )
        )
    )

    with pytest.raises(ActionValidationError, match="confirmed through the Map"):
        service.resolve_player_action("travel to the flooded ruins", provider)

    assert service.load_active_dashboard().location.name == "Greystone Road"


def test_combat_is_rejected_before_model_call_and_cancel_prevents_commit() -> None:
    database, service = seeded_service()
    provider = FixedProvider(outcome())

    with pytest.raises(ActionValidationError, match="Combat"):
        service.resolve_player_action("attack the goblin", provider)
    assert provider.action == ""

    cancelled = False

    class CancellingProvider(FixedProvider):
        def resolve_action(self, *, action: str, context: dict[str, object]) -> ActionOutcome:
            nonlocal cancelled
            result = super().resolve_action(action=action, context=context)
            cancelled = True
            return result

    with pytest.raises(ActionCancelledError):
        service.resolve_player_action(
            "talk quietly",
            CancellingProvider(outcome()),
            cancelled=lambda: cancelled,
        )
    with database.connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM action_turns").fetchone()[0] == 0


def test_action_worker_reports_success_failure_and_prestart_cancellation() -> None:
    database, service = seeded_service()
    success = ActionResolutionTask(service, FixedProvider(outcome()), "look around")
    succeeded = QSignalSpy(success.signals.succeeded)
    finished = QSignalSpy(success.signals.finished)
    success.run()
    assert succeeded.count() == 1
    assert finished.count() == 1

    class FailedProvider:
        def resolve_action(self, **_kwargs):  # type: ignore[no-untyped-def]
            raise LocalModelResponseError("malformed turn")

    failed_task = ActionResolutionTask(service, FailedProvider(), "listen")  # type: ignore[arg-type]
    failed = QSignalSpy(failed_task.signals.failed)
    failed_task.run()
    assert failed.at(0) == ["malformed turn"]

    cancelled_task = ActionResolutionTask(service, FixedProvider(outcome()), "wait")
    cancelled = QSignalSpy(cancelled_task.signals.cancelled)
    cancelled_task.cancel()
    cancelled_task.run()
    assert cancelled.count() == 1


def test_state_backed_ui_resolves_and_refreshes_narration(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app, window, _manager = build_application([], config_dir=tmp_path)
    release = Event()

    class BlockingProvider(FixedProvider):
        def resolve_action(self, *, action: str, context: dict[str, object]) -> ActionOutcome:
            assert release.wait(3)
            return super().resolve_action(action=action, context=context)

    window.action_resolver = BlockingProvider(outcome())
    window.controller.navigate("dashboard")
    window.scene_view.choice_grid.action_input.setText("study the road")
    window.scene_view.choice_grid._request_submission()
    task = window._action_task
    assert task is not None
    release.set()
    assert QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()

    assert window._action_task is None
    assert window.dashboard.narrative.paragraphs == (
        "The merchant nods as the moment unfolds.",
    )
    assert window.dashboard.narrative.player_action == "study the road"
    # The conversation shows the player's line and the narration as this turn's rows.
    recent = window.conversation_view.recent_rows
    assert len(recent) >= 2
    assert any(
        row.role == "player" and "study the road" in row.text_label.text() for row in recent
    )
    assert all(row.property("recentTurn") is True for row in recent)
    assert "Turn committed" in window.statusBar().currentMessage()
    window.close()
    window.deleteLater()
    app.processEvents()


def test_state_backed_ui_failure_keeps_action_and_offers_retry(tmp_path) -> None:  # type: ignore[no-untyped-def]
    app, window, _manager = build_application([], config_dir=tmp_path)
    release = Event()

    class BlockingFailure:
        def resolve_action(self, **_kwargs):  # type: ignore[no-untyped-def]
            assert release.wait(3)
            raise LocalModelResponseError("Turn JSON was malformed.")

    window.action_resolver = BlockingFailure()
    window.controller.navigate("dashboard")
    grid = window.scene_view.choice_grid
    grid.action_input.setText("inspect the cart")
    grid._request_submission()
    task = window._action_task
    assert task is not None
    release.set()
    assert QThreadPool.globalInstance().waitForDone(5000)
    app.processEvents()

    assert window._action_task is None
    assert grid.action_input.text() == "inspect the cart"
    assert grid.retry_button.isVisibleTo(grid)
    assert "malformed" in grid.feedback.text()
    window.close()
    window.deleteLater()
    app.processEvents()
