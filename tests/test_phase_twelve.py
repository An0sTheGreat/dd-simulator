from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dd_simulator.state import GameStateDatabase, GameStateService
from dd_simulator.state.migrations import LATEST_SCHEMA_VERSION
from dd_simulator.state.quests import check_deadlines, progress_quests
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID, seed_demo_campaign
from dd_simulator.ui.models.presentation import (
    ObjectiveView,
    QuestListItemView,
    QuestRewardItemView,
    QuestRewardView,
)
from dd_simulator.ui.widgets.quest_list import QuestListItem, QuestListWidget
from dd_simulator.ui.widgets.quest_rewards_dialog import QuestRewardsDialog


def phase_twelve_service(tmp_path: Path) -> tuple[GameStateDatabase, GameStateService]:
    database = GameStateDatabase(tmp_path / "phase-twelve.db")
    assert database.initialize() == LATEST_SCHEMA_VERSION == 21
    seed_demo_campaign(database)
    return database, GameStateService(database)


def test_schema_ten_records_quest_lifecycle_progress_and_rewards(tmp_path: Path) -> None:
    database, _service = phase_twelve_service(tmp_path)
    with database.connect() as connection:
        quest_columns = {row[1] for row in connection.execute("PRAGMA table_info(quests)")}
        objective_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(quest_objectives)")
        }
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {
        "quest_type", "started_day", "deadline_day", "completed_at", "failed_at",
        "abandoned_at", "reward_experience", "reward_currency", "reward_reputation",
        "reward_items_json", "follow_up_quest_id",
    } <= quest_columns
    assert {
        "trigger_type", "trigger_target", "current_count", "required_count",
        "completed_at",
    } <= objective_columns
    assert {"quest_updates", "quest_rewards", "quest_reward_items", "faction_reputation"} <= tables


def test_deterministic_progress_completes_once_and_persists_reward(tmp_path: Path) -> None:
    database, service = phase_twelve_service(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE quest_objectives SET optional = 1 WHERE quest_id = 'quest-heirloom'"
        )
        connection.execute(
            "UPDATE quest_objectives SET optional = 0, completed = 0, current_count = 0, "
            "required_count = 2, trigger_type = 'combat', trigger_target = 'goblin' "
            "WHERE id = 'objective-0'"
        )
        before_currency = int(
            connection.execute(
                "SELECT currency FROM characters WHERE campaign_id = ? AND is_player = 1",
                (DEMO_CAMPAIGN_ID,),
            ).fetchone()[0]
        )
        first = progress_quests(connection, DEMO_CAMPAIGN_ID, "combat", "goblin")
        second = progress_quests(connection, DEMO_CAMPAIGN_ID, "combat", "goblin")
        third = progress_quests(connection, DEMO_CAMPAIGN_ID, "combat", "goblin")

    assert first == ("Quest progress: Travel to the bandit camp (1/2).",)
    assert any("Quest completed: The Lost Heirloom" in value for value in second)
    assert third == ()
    dashboard = service.load_active_dashboard()
    completed = next(quest for quest in dashboard.quest_list if quest.id == "quest-heirloom")
    assert completed.status == "completed"
    assert dashboard.pending_quest_reward is not None
    assert dashboard.pending_quest_reward.experience == 150
    with database.connect() as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM quest_rewards WHERE quest_id = 'quest-heirloom'"
        ).fetchone()[0] == 1
        currency = int(
            connection.execute(
                "SELECT currency FROM characters WHERE campaign_id = ? AND is_player = 1",
                (DEMO_CAMPAIGN_ID,),
            ).fetchone()[0]
        )
    assert currency == before_currency + 50


def test_deadlines_failure_abandonment_and_follow_up_activation(tmp_path: Path) -> None:
    database, service = phase_twelve_service(tmp_path)
    with database.transaction() as connection:
        connection.execute(
            "UPDATE quests SET deadline_day = 17, deadline_minute = 1 "
            "WHERE id = 'quest-merchant'"
        )
        connection.execute(
            "UPDATE campaign_clock SET day = 17, minute_of_day = 2 WHERE campaign_id = ?",
            (DEMO_CAMPAIGN_ID,),
        )
        failures = check_deadlines(connection, DEMO_CAMPAIGN_ID)
        connection.execute(
            "INSERT INTO quests(id, campaign_id, title, status, quest_type, display_order) "
            "VALUES ('quest-follow-up', ?, 'A Revealed Path', 'rumored', 'follow_up', 9)",
            (DEMO_CAMPAIGN_ID,),
        )
        connection.execute(
            "UPDATE quests SET follow_up_quest_id = 'quest-follow-up' "
            "WHERE id = 'quest-heirloom'"
        )
        connection.execute(
            "UPDATE quest_objectives SET optional = 1 WHERE quest_id = 'quest-heirloom'"
        )
        connection.execute(
            "UPDATE quest_objectives SET optional = 0, completed = 0, current_count = 0, "
            "trigger_type = 'dialogue', trigger_target = 'aric' WHERE id = 'objective-0'"
        )
        progress_quests(
            connection, DEMO_CAMPAIGN_ID, "dialogue", detail="Tell Lord Aric the truth."
        )

    assert failures == ("Quest failed: A Favor for the Merchant (deadline passed).",)
    with database.connect() as connection:
        assert connection.execute(
            "SELECT status FROM quests WHERE id = 'quest-follow-up'"
        ).fetchone()[0] == "active"
        assert connection.execute(
            "SELECT status FROM quests WHERE id = 'quest-merchant'"
        ).fetchone()[0] == "failed"

    summary = service.abandon_quest("quest-follow-up")
    assert summary == "Quest abandoned: A Revealed Path."


def test_quest_cards_expand_inline_but_completed_cards_are_locked() -> None:
    app = QApplication.instance() or QApplication([])
    active = QuestListItemView(
        "Open Quest", "active", 0, 2, id="open",
        objectives=(ObjectiveView("Find the gate"), ObjectiveView("Enter the keep")),
    )
    completed = QuestListItemView(
        "Finished Quest", "completed", 1, 1, id="done",
        objectives=(ObjectiveView("Return home", completed=True),),
    )
    widget = QuestListWidget((active, completed))
    widget.resize(900, 500)
    widget.show()
    app.processEvents()
    cards = {card.quest.id: card for card in widget.findChildren(QuestListItem)}

    cards["open"].toggle()
    cards["done"].toggle()
    app.processEvents()

    assert cards["open"].expanded
    assert cards["open"].details.isVisible()
    assert not cards["done"].expanded
    assert not cards["done"].details.isVisible()
    assert cards["done"].property("completed") is True


def test_quest_completion_popup_exposes_rewards_and_claim_state() -> None:
    app = QApplication.instance() or QApplication([])
    reward = QuestRewardView(
        id="reward", quest_id="quest", quest_title="The Last Lantern",
        experience=200, currency=75, reputation=3, faction="Greystone",
        items=(QuestRewardItemView("item", "Moonstone", 1, "rare", "A pale gem."),),
    )
    dialog = QuestRewardsDialog(reward)
    dialog.show()
    app.processEvents()

    assert dialog.isModal()
    assert dialog.item_buttons["item"].isEnabled()
    dialog.mark_claimed("item")
    assert dialog.item_buttons["item"].text() == "Claimed"
    assert not dialog.item_buttons["item"].isEnabled()
    assert dialog.feedback.property("feedbackState") == "success"
    dialog.close()
