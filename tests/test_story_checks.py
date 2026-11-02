from __future__ import annotations

import pytest

from dd_simulator.state import ProposedStateChange
from dd_simulator.state.story_checks import roll_story_check, story_check_kind
from test_action_resolution import FixedProvider, outcome, seeded_service


@pytest.mark.parametrize(
    ("action", "check"),
    [
        ("Inspect the damaged cart", "Investigation"),
        ("Search the road for tracks", "Survival"),
        ("Climb the old watchtower", "Athletics"),
        ("Sneak past the guards", "Stealth"),
        ("Pick the lock on the chest", "Thievery"),
        ("Study the runes on the door", "Arcana"),
        ("Bandage the merchant's arm", "Medicine"),
        ("Listen at the door", "Perception"),
        ("Persuade the guard to let us pass", "Persuasion"),
        ("Speak with the merchant", None),
        ("Continue toward Greystone Keep", None),
    ],
)
def test_story_actions_map_to_checks(action: str, check: str | None) -> None:
    kind = story_check_kind(action)
    assert (kind[0] if kind else None) == check


def _roll(service, action: str):  # type: ignore[no-untyped-def]
    with service.database.connect() as connection:
        player = connection.execute(
            "SELECT characters.id, campaign_clock.turn_number FROM characters JOIN campaign_clock "
            "ON campaign_clock.campaign_id = characters.campaign_id WHERE characters.is_player = 1"
        ).fetchone()
        return roll_story_check(
            connection, str(service.campaigns.active_campaign_id()), str(player["id"]),
            int(player["turn_number"]) + 1, action,
        )


def test_story_check_is_rolled_by_code_shown_to_the_model_and_recorded() -> None:
    database, service = seeded_service()
    action = "Inspect the damaged cart"
    expected = _roll(service, action)
    assert expected is not None and expected == _roll(service, action)  # seeded: no rerolls
    assert expected.total == expected.roll + expected.modifier and expected.target == 12
    provider = FixedProvider(outcome())
    result = service.resolve_player_action(action, provider)
    assert result.skill_check == expected
    assert provider.context["skill_check"]["success"] is expected.success  # type: ignore[index]
    notes = [note for message in service.load_active_dashboard().narrative.messages for note in message.notes]
    assert any(note.text.startswith(f"Investigation {expected.total} vs DC 12") for note in notes)
    assert service.resolve_player_action("Continue toward Greystone Keep", FixedProvider(outcome())).skill_check is None
    database.close()


def test_a_failed_search_finds_nothing_even_if_the_model_says_so() -> None:
    database, service = seeded_service()
    loot = service.build_action_context()["available_loot"][0]
    action = next(
        text for text in (f"Search the ruined shed {n}" for n in range(200))
        if not _roll(service, text).success  # type: ignore[union-attr]
    )
    found = ProposedStateChange("discover_item", "loot_item", str(loot["id"]), None, True, "Found.")
    result = service.resolve_player_action(action, FixedProvider(outcome(found)))
    assert result.skill_check is not None and not result.skill_check.success
    names = {item.name for item in service.load_active_dashboard().inventory_preview}
    assert loot["name"] not in names
    database.close()
