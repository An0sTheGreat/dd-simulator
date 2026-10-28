"""Phase 2c: character data for the Concept T left column."""

from __future__ import annotations

from pathlib import Path
import random

import pytest

from dd_simulator.local_model.action_resolver import LocalModelActionResolver
from dd_simulator.state import ActionValidationError, GameStateDatabase, GameStateService
from dd_simulator.state import projection
from dd_simulator.state.abilities import CLASS_LOADOUTS, sync_character_combat_catalog
from dd_simulator.state.character_creation import SKILL_DESCRIPTIONS, SKILLS
from dd_simulator.state.seed import DEMO_CAMPAIGN_ID, DEMO_CHARACTER_ID
from tests.test_action_resolution import FixedProvider, outcome, seeded_service
from tests.test_release_sixteen import _file_service, _write_png


def _with_class(character_class: str) -> tuple[GameStateDatabase, GameStateService]:
    database, service = seeded_service()
    with database.transaction() as connection:
        sync_character_combat_catalog(
            connection, DEMO_CHARACTER_ID, character_class=character_class, level=20
        )
    return database, service


def _fill_bag(database: GameStateDatabase, positions: list[int]) -> None:
    """Replace every bag item with ``Item NNN`` at each given position."""

    with database.transaction() as connection:
        connection.execute(
            "DELETE FROM inventory_items WHERE character_id = ? AND inventory_position "
            "IS NOT NULL AND id NOT IN (SELECT inventory_item_id FROM equipment_slots "
            "WHERE inventory_item_id IS NOT NULL)",
            (DEMO_CHARACTER_ID,),
        )
        connection.executemany(
            "INSERT INTO inventory_items(id, character_id, slot_index, name, "
            "inventory_position) VALUES (?, ?, ?, ?, ?)",
            (
                (f"item-fill-{position}", DEMO_CHARACTER_ID, 1000 + position,
                 f"Item {position:03d}", position)
                for position in positions
            ),
        )


def test_every_creatable_skill_has_a_description() -> None:
    assert set(SKILL_DESCRIPTIONS) == set(SKILLS)
    assert all(SKILL_DESCRIPTIONS[name].strip() for name in SKILLS)
    _database, service = seeded_service()
    skills = service.load_active_dashboard().skills
    assert skills and all(skill.description == SKILL_DESCRIPTIONS[skill.name] for skill in skills)


@pytest.mark.parametrize(
    ("character_class", "abilities", "spells"),
    [
        ("Fighter", CLASS_LOADOUTS["fighter"], ()),
        ("Wizard", (), CLASS_LOADOUTS["wizard"]),
        ("Custom hybrid class", ("power_strike", "second_wind"), ("fire_bolt", "arcane_ward")),
    ],
)
def test_abilities_and_spells_split_by_kind_in_catalog_order(
    character_class: str, abilities: tuple[str, ...], spells: tuple[str, ...]
) -> None:
    _database, service = _with_class(character_class)
    dashboard = service.load_active_dashboard()
    assert tuple(power.key for power in dashboard.abilities) == abilities
    assert tuple(power.key for power in dashboard.spells) == spells
    assert all(power.kind == "ability" for power in dashboard.abilities)
    assert all(power.kind == "spell" for power in dashboard.spells)
    assert tuple(power.key for power in dashboard.combat_skills) == CLASS_LOADOUTS[
        character_class.casefold()
    ]


def test_status_label_covers_ready_cooldown_and_limited_uses() -> None:
    database, service = _with_class("Fighter")
    with database.transaction() as connection:
        connection.execute(
            "UPDATE character_resources SET current_value = maximum_value "
            "WHERE character_id = ?",
            (DEMO_CHARACTER_ID,),
        )
        for key, cooldown, uses in (("shield_wall", 2, None), ("second_wind", 0, 1)):
            connection.execute(
                "UPDATE abilities SET cooldown_remaining = ?, "
                "current_uses = COALESCE(?, current_uses) "
                "WHERE character_id = ? AND action_key = ?",
                (cooldown, uses, DEMO_CHARACTER_ID, key),
            )
    labels = {
        power.key: (power.status_label, power.available)
        for power in service.load_active_dashboard().abilities
    }
    assert labels["power_strike"] == ("Ready", True)
    assert labels["shield_wall"] == ("Cooldown 2", False)
    assert labels["second_wind"] == ("1/2 uses", True)

    with database.transaction() as connection:
        connection.execute(
            "UPDATE abilities SET current_uses = 0 WHERE character_id = ? AND action_key = ?",
            (DEMO_CHARACTER_ID, "second_wind"),
        )
        connection.execute(
            "UPDATE character_resources SET current_value = 0 "
            "WHERE character_id = ? AND resource_type = ?",
            (DEMO_CHARACTER_ID, "stamina"),
        )
    labels = {
        power.key: (power.status_label, power.available)
        for power in service.load_active_dashboard().abilities
    }
    assert labels["second_wind"] == ("0/2 uses", False)
    assert labels["power_strike"] == ("Needs 5 stamina", False)


def test_inventory_lists_every_occupied_position_beyond_one_page() -> None:
    database, service = seeded_service()
    positions = [position * 2 for position in range(60)]  # 0..118, gaps included
    shuffled = positions[:]
    random.Random(7).shuffle(shuffled)
    _fill_bag(database, shuffled)

    dashboard = service.load_active_dashboard()
    assert [item.name for item in dashboard.inventory] == [
        f"Item {position:03d}" for position in positions
    ]
    assert dashboard.inventory_capacity == 320
    assert len(dashboard.inventory_preview) == 144  # paged view is unchanged


def test_full_bag_still_rejects_a_pickup_at_the_320_cap() -> None:
    database, service = seeded_service()
    _fill_bag(database, list(range(320)))
    assert len(service.load_active_dashboard().inventory) == 320

    action = "I pick up the etched rune stone from the floor."
    provider = FixedProvider(outcome())
    provider.result = LocalModelActionResolver._ensure_explicit_acquisition(
        provider.result, action
    )
    with pytest.raises(ActionValidationError, match="inventory is full"):
        service.resolve_player_action(action, provider)
    assert len(service.load_active_dashboard().inventory) == 320


def test_portrait_uses_confirmed_registry_portrait(tmp_path: Path) -> None:
    _database, service = _file_service(tmp_path)
    source = tmp_path / "portrait.png"
    _write_png(source, "#9f6a35")
    staged = service.visuals.stage_asset(
        campaign_id=DEMO_CAMPAIGN_ID, asset_kind="portrait", subject_type="character",
        subject_id=DEMO_CHARACTER_ID, source_path=source,
    )
    pending = service.load_active_dashboard().player.portrait_path
    assert Path(pending).parent.parent == projection.CODEX_PORTRAIT_ROOT  # not confirmed yet
    service.visuals.confirm_asset(staged.id)
    player = service.load_active_dashboard().player
    assert player.visual is not None and player.visual.path
    assert player.portrait_path == player.visual.path


def test_portrait_fallback_is_stable_and_follows_ancestry() -> None:
    database, service = seeded_service()
    first = service.load_active_dashboard().player.portrait_path
    second = GameStateService(database).load_active_dashboard().player.portrait_path
    assert first and first == second and Path(first).is_file()
    assert Path(first).parent.parent == projection.CODEX_PORTRAIT_ROOT

    for ancestry, pack in (
        ("Mountain Dwarf", "dwarf"), ("Goblin", "goblin"), ("Fey-touched elf", "fairy"),
        ("Tiefling", "demon"), ("Undead knight", "undead"), ("Human", "fantasy"),
    ):
        path = Path(projection.fallback_portrait("character-x", ancestry))
        assert path.parent.name == pack and path.is_file()


def test_portrait_is_empty_when_no_art_exists(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(projection, "CODEX_PORTRAIT_ROOT", tmp_path)
    _database, service = seeded_service()
    player = service.load_active_dashboard().player
    assert player.portrait_path == "" and player.portrait_initials
